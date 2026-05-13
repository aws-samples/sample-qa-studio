"""Async subprocess wrapper for the TUI's live-tail run view.

Spawns ``python -m qa_studio_cli run ...`` and exposes its stdout /
stderr as an async iterator of ``(stream_name, line)`` tuples. Owns
the optional :class:`OverrideFiles` so secrets / headers tempfiles
are unlinked in a ``finally`` regardless of how the run ended.

Separated from any Textual imports so it's unit-testable with a
plain ``asyncio`` harness against a tiny Python snippet.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import AsyncIterator, List, Optional, Tuple

from qa_studio_cli.tui.override_writer import OverrideFiles


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    duration_seconds: float


def build_argv(
    *,
    usecase_id: Optional[str] = None,
    suite_id: Optional[str] = None,
    extra_flags: List[str],
    local_only: bool = True,
    verbose: bool = False,
    output_format: str = "json",
) -> List[str]:
    """Assemble the argv for ``python -u -m qa_studio_cli run``.

    Exactly one of ``usecase_id`` / ``suite_id`` must be supplied — the
    runner's ``qa-studio run`` command takes ``--usecase-id`` *or*
    ``--suite-id`` (but not both), and we surface the same constraint
    here so the TUI fails fast rather than letting the subprocess
    error out.

    The ``-u`` flag forces unbuffered stdout/stderr on the child so
    log lines appear in the live-tail as soon as they're written —
    without it, Python block-buffers pipes and the TUI looks frozen
    until the buffer fills or the process exits. ``PYTHONUNBUFFERED``
    in the env is a belt-and-braces defence for nested Python
    subprocesses the runner might spawn.

    The TUI always runs with ``--local-only`` by default (per spec);
    the Run forms expose a checkbox to create a remote execution
    record instead. ``verbose`` defaults to ``False`` (INFO-level
    logs); tick the Verbose checkbox for DEBUG. Callers supply
    ``extra_flags`` already formatted (``--var k=v``,
    ``--headers-file PATH``, etc.).
    """
    if bool(usecase_id) == bool(suite_id):
        raise ValueError(
            "build_argv requires exactly one of usecase_id or suite_id"
        )

    argv = [sys.executable, "-u", "-m", "qa_studio_cli", "run"]
    if usecase_id:
        argv.extend(["--usecase-id", usecase_id])
    else:
        argv.extend(["--suite-id", suite_id])
    if local_only:
        argv.append("--local-only")
    if verbose:
        argv.append("--verbose")
    argv.extend(["--format", output_format])
    argv.extend(extra_flags)
    return argv


class RunnerProcess:
    """Thin async wrapper around a spawned ``qa-studio run``.

    Lifecycle:

    1. Construct with ``argv`` + the :class:`OverrideFiles` that the
       argv references.
    2. ``await start()`` — spawns the child.
    3. ``async for stream, line in stream():`` — until EOF on both.
    4. ``result = await wait()`` — resolves once the child has exited.
    5. ``await aclose()`` — unlinks tempfiles. Idempotent. Always call
       in a finally block.

    ``terminate()`` can be invoked at any time to send SIGTERM; a
    grace period elapses before SIGKILL.
    """

    def __init__(self, argv: List[str], override_files: OverrideFiles):
        self._argv = argv
        self._override_files = override_files
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._started_at: Optional[float] = None
        self._closed = False

    @property
    def argv(self) -> List[str]:
        return list(self._argv)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._proc is not None:
            raise RuntimeError("RunnerProcess.start() called twice")
        self._started_at = time.monotonic()

        # Belt-and-braces unbuffered output: the argv already carries
        # ``-u`` but nested Python subprocesses the runner might spawn
        # inherit ``PYTHONUNBUFFERED`` from the env and honour it too.
        env = dict(os.environ)
        env.setdefault("PYTHONUNBUFFERED", "1")

        # Start the child in its own POSIX session so we can signal
        # the whole group on terminate.  NovaAct launches Chromium via
        # Playwright; SIGTERM to the Python runner alone does not
        # propagate to Chromium, which keeps Playwright blocked and
        # the runner alive.  ``start_new_session=True`` asks Popen to
        # call ``setsid()`` in the child; subsequent ``os.killpg`` on
        # the child's pgid signals every descendant.  On Windows
        # ``start_new_session`` is a no-op; we document this as a
        # known limitation (POC targets macOS/Linux).
        self._proc = await asyncio.create_subprocess_exec(
            *self._argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )

    async def stream(self) -> AsyncIterator[Tuple[str, str]]:
        """Yield ``(stream_name, line)`` tuples until the child exits.

        ``stream_name`` is ``"stdout"`` or ``"stderr"``; ``line`` has
        the trailing newline stripped. Lines from the two streams are
        interleaved in arrival order — the TUI typically prepends a
        ``[stderr]`` marker to stderr lines when rendering.

        The stream naturally ends when both pipes close. It **also**
        ends when the main process has exited and no new output has
        arrived for a short grace window — this covers the case where
        a grandchild (Chromium, in practice) inherits the pipes and
        holds them open past the runner's own exit. Without the grace
        window the TUI would hang forever showing "Running…" even
        though the runner printed its final status line and exited.
        """
        if self._proc is None:
            raise RuntimeError("RunnerProcess.stream() called before start()")
        assert self._proc.stdout is not None
        assert self._proc.stderr is not None

        queue: asyncio.Queue[Tuple[str, str] | None] = asyncio.Queue()

        async def _pump(name: str, reader: asyncio.StreamReader) -> None:
            try:
                while True:
                    line = await reader.readline()
                    if not line:
                        await queue.put(None)
                        return
                    await queue.put((name, line.decode(errors="replace").rstrip("\n")))
            except asyncio.CancelledError:
                # Grace period expired and the outer loop cancelled us;
                # push a sentinel so the drain loop can terminate even
                # if our cancellation races with a final queue.get().
                await queue.put(None)
                raise

        task_out = asyncio.create_task(_pump("stdout", self._proc.stdout))
        task_err = asyncio.create_task(_pump("stderr", self._proc.stderr))

        pending_end_markers = 2
        # Idle budget only starts consuming after the main process has
        # exited. Before that we wait indefinitely for data.
        idle_after_exit = 0.0
        POLL_INTERVAL = 0.5
        EXIT_GRACE_SECONDS = 2.0

        try:
            while pending_end_markers > 0:
                try:
                    item = await asyncio.wait_for(
                        queue.get(), timeout=POLL_INTERVAL
                    )
                except asyncio.TimeoutError:
                    # No output in the last POLL_INTERVAL. If the main
                    # process has exited, start burning through the
                    # grace budget; otherwise keep waiting.
                    if self._proc.returncode is not None:
                        idle_after_exit += POLL_INTERVAL
                        if idle_after_exit >= EXIT_GRACE_SECONDS:
                            # Process exited and no output for the
                            # grace window → pipes are held by an
                            # orphaned grandchild. Give up and let
                            # the finally-block cancel the pumps.
                            break
                    continue

                # Real data received — reset the grace budget so a
                # slow-but-progressing shutdown keeps streaming.
                idle_after_exit = 0.0

                if item is None:
                    pending_end_markers -= 1
                    continue
                yield item
        finally:
            # Both pump tasks naturally end when their stream closes;
            # if we bailed on the grace window they're still awaiting
            # their respective readlines. Cancel + await to reap.
            for task in (task_out, task_err):
                if not task.done():
                    task.cancel()
            for task in (task_out, task_err):
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    async def wait(self) -> RunResult:
        """Block until the child exits; return exit code + duration."""
        if self._proc is None:
            raise RuntimeError("RunnerProcess.wait() called before start()")
        exit_code = await self._proc.wait()
        duration = (
            time.monotonic() - self._started_at
            if self._started_at is not None
            else 0.0
        )
        return RunResult(exit_code=exit_code, duration_seconds=duration)

    async def terminate(self, grace_seconds: float = 5.0) -> None:
        """Send SIGTERM to the child's process group; escalate to SIGKILL
        after ``grace_seconds``.

        The child runs in its own session (see ``start``), so
        ``os.killpg`` signals the Python runner *and* every browser
        process Playwright spawned — without this, Chromium keeps
        Playwright blocked and the runner never exits.

        Safe to call multiple times — no-op once the child has
        exited."""
        if self._proc is None or self._proc.returncode is not None:
            return

        self._signal_group(signal.SIGTERM)

        try:
            await asyncio.wait_for(self._proc.wait(), timeout=grace_seconds)
        except asyncio.TimeoutError:
            if self._proc.returncode is None:
                self._signal_group(signal.SIGKILL)
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    # Extremely rare — SIGKILL ignored. Leave the
                    # process for the OS to reap; don't hang the TUI.
                    pass

    def _signal_group(self, sig: signal.Signals) -> None:
        """Send ``sig`` to the child's process group.

        Falls back to signalling just the child when ``os.killpg``
        can't locate a group (e.g. Windows, or the child already
        exited). Never raises — termination is best-effort.
        """
        if self._proc is None or self._proc.returncode is not None:
            return
        try:
            pgid = os.getpgid(self._proc.pid)
        except (ProcessLookupError, PermissionError, OSError, AttributeError):
            # ``os.getpgid`` doesn't exist on Windows; AttributeError
            # covers that case. Fall back to signalling just the
            # child process.
            try:
                self._proc.send_signal(sig)
            except ProcessLookupError:
                pass
            return
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            # Group already gone, or we lost permission (shouldn't
            # happen for processes we spawned). Single-process
            # fallback.
            try:
                self._proc.send_signal(sig)
            except ProcessLookupError:
                pass

    async def aclose(self) -> None:
        """Unlink tempfiles. Idempotent — always safe to call in a
        finally block regardless of whether ``start()`` succeeded."""
        if self._closed:
            return
        self._closed = True
        self._override_files.cleanup()
