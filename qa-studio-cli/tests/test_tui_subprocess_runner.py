"""Unit tests for :mod:`qa_studio_cli.tui.subprocess_runner`.

Uses a small ``-c`` Python snippet as the child process so we don't
need ``qa-studio run`` to be executable in the test environment.
"""

import asyncio
import sys
from pathlib import Path

import pytest

from qa_studio_cli.tui.override_writer import OverrideFiles, write_overrides
from qa_studio_cli.tui.subprocess_runner import (
    RunnerProcess,
    build_argv,
)


class TestBuildArgv:
    def test_defaults_include_local_only_but_not_verbose(self):
        argv = build_argv(usecase_id="u-1", extra_flags=[])
        assert "--local-only" in argv
        # Default is INFO-level logging — ``--verbose`` is opt-in via
        # the Run form checkbox, not on by default.
        assert "--verbose" not in argv
        assert "--usecase-id" in argv
        assert argv[argv.index("--usecase-id") + 1] == "u-1"
        assert argv[0] == sys.executable

    def test_verbose_flag_added_when_explicitly_enabled(self):
        argv = build_argv(usecase_id="u-1", extra_flags=[], verbose=True)
        assert "--verbose" in argv

    def test_suite_id_builds_suite_argv(self):
        argv = build_argv(suite_id="s-1", extra_flags=[])
        assert "--suite-id" in argv
        assert argv[argv.index("--suite-id") + 1] == "s-1"
        assert "--usecase-id" not in argv

    def test_rejects_missing_id(self):
        with pytest.raises(ValueError, match="exactly one"):
            build_argv(extra_flags=[])

    def test_rejects_both_ids(self):
        with pytest.raises(ValueError, match="exactly one"):
            build_argv(usecase_id="u-1", suite_id="s-1", extra_flags=[])

    def test_python_unbuffered_flag_is_present(self):
        """Regression: without ``-u`` the child block-buffers its
        stdout/stderr pipes and the live-tail looks frozen until the
        process exits. See subprocess_runner docstring for context."""
        argv = build_argv(usecase_id="u-1", extra_flags=[])
        # ``-u`` must sit between the interpreter and ``-m``.
        i = argv.index("-u")
        j = argv.index("-m")
        assert i == 1
        assert j == 2

    def test_extra_flags_appended_verbatim(self):
        argv = build_argv(
            usecase_id="u-1",
            extra_flags=[
                "--var", "k=v",
                "--headers-file", "/tmp/h.json",
                "--secrets-file", "/tmp/s.json",
            ],
        )
        # Original order preserved after the preamble.
        tail = argv[-6:]
        assert tail == [
            "--var", "k=v",
            "--headers-file", "/tmp/h.json",
            "--secrets-file", "/tmp/s.json",
        ]

    def test_local_only_can_be_disabled(self):
        argv = build_argv(usecase_id="u-1", extra_flags=[], local_only=False)
        assert "--local-only" not in argv

    def test_format_option_passed_through(self):
        argv = build_argv(usecase_id="u-1", extra_flags=[], output_format="human")
        i = argv.index("--format")
        assert argv[i + 1] == "human"


# ---------------------------------------------------------------------------
# RunnerProcess
# ---------------------------------------------------------------------------


def _asyncio_run(coro):
    return asyncio.run(coro)


def _snippet_argv(body: str) -> list[str]:
    return [sys.executable, "-c", body]


class TestRunnerProcessLifecycle:
    def test_stream_yields_stdout_and_stderr_lines(self):
        async def _run():
            body = (
                "import sys;"
                "print('hello stdout');"
                "print('hello stderr', file=sys.stderr);"
                "print('done');"
            )
            proc = RunnerProcess(
                argv=_snippet_argv(body),
                override_files=OverrideFiles(),
            )
            await proc.start()
            collected: list[tuple[str, str]] = []
            async for stream, line in proc.stream():
                collected.append((stream, line))
            result = await proc.wait()
            await proc.aclose()

            assert result.exit_code == 0
            stdout_lines = [line for s, line in collected if s == "stdout"]
            stderr_lines = [line for s, line in collected if s == "stderr"]
            assert "hello stdout" in stdout_lines
            assert "done" in stdout_lines
            assert "hello stderr" in stderr_lines

        _asyncio_run(_run())

    def test_wait_returns_nonzero_exit_for_failing_child(self):
        async def _run():
            proc = RunnerProcess(
                argv=_snippet_argv("import sys; sys.exit(3)"),
                override_files=OverrideFiles(),
            )
            await proc.start()
            async for _ in proc.stream():
                pass
            result = await proc.wait()
            await proc.aclose()
            assert result.exit_code == 3
            assert result.duration_seconds >= 0.0

        _asyncio_run(_run())

    def test_aclose_is_idempotent(self):
        async def _run():
            proc = RunnerProcess(argv=_snippet_argv("pass"), override_files=OverrideFiles())
            await proc.start()
            async for _ in proc.stream():
                pass
            await proc.wait()
            await proc.aclose()
            await proc.aclose()  # must not raise

        _asyncio_run(_run())

    def test_start_twice_raises(self):
        async def _run():
            proc = RunnerProcess(argv=_snippet_argv("pass"), override_files=OverrideFiles())
            await proc.start()
            with pytest.raises(RuntimeError):
                await proc.start()
            async for _ in proc.stream():
                pass
            await proc.wait()
            await proc.aclose()

        _asyncio_run(_run())

    def test_stream_before_start_raises(self):
        async def _run():
            proc = RunnerProcess(argv=_snippet_argv("pass"), override_files=OverrideFiles())
            with pytest.raises(RuntimeError):
                async for _ in proc.stream():
                    pass

        _asyncio_run(_run())


class TestRunnerProcessTermination:
    def test_terminate_kills_long_running_child(self):
        async def _run():
            # A child that would run for hours if left alone.
            proc = RunnerProcess(
                argv=_snippet_argv("import time; time.sleep(3600)"),
                override_files=OverrideFiles(),
            )
            await proc.start()
            # Don't consume the stream — just terminate it.
            await proc.terminate(grace_seconds=2.0)
            result = await proc.wait()
            await proc.aclose()
            # SIGTERM typically surfaces as -15 on POSIX; tolerate
            # either a negative "signal killed" code or a non-zero
            # exit.
            assert result.exit_code != 0

        _asyncio_run(_run())

    def test_terminate_before_start_is_noop(self):
        async def _run():
            proc = RunnerProcess(argv=_snippet_argv("pass"), override_files=OverrideFiles())
            # No start() called; terminate must not raise.
            await proc.terminate()

        _asyncio_run(_run())

    def test_terminate_kills_grandchildren_via_process_group(self):
        """Regression for "terminate not working" with Playwright:

        If the runner spawns a grandchild (Chromium, in reality) that
        ignores SIGTERM from its parent, signalling only the parent
        leaves the grandchild alive and the parent waiting on it.
        Sending to the **process group** catches both.

        This test simulates the shape with a tiny Python script that
        forks a sleep-grandchild and then waits on it. SIGTERM to
        just the parent's PID doesn't help — only killpg does.
        """
        import os as _os
        import time as _time

        async def _run():
            # Parent spawns a detached sleeper, then blocks on os.wait.
            body = (
                "import os, sys, time;"
                "pid = os.fork();"
                "import time as _t;"
                "(_t.sleep(3600) if pid == 0 else os.wait())"
            )
            proc = RunnerProcess(
                argv=_snippet_argv(body),
                override_files=OverrideFiles(),
            )
            await proc.start()
            # Give the child a moment to fork.
            await asyncio.sleep(0.2)

            started = _time.monotonic()
            await proc.terminate(grace_seconds=3.0)
            result = await proc.wait()
            elapsed = _time.monotonic() - started
            await proc.aclose()

            # The whole thing must finish within the grace window,
            # otherwise terminate would have hit SIGKILL-after-grace.
            assert elapsed < 4.0, f"terminate took {elapsed:.1f}s"
            assert result.exit_code != 0

        _asyncio_run(_run())


class TestOverrideFileCleanup:
    def test_aclose_unlinks_tempfiles(self, tmp_path):
        async def _run():
            files = write_overrides({"X": "y"}, {"pw": "v"})
            headers = files.headers_path
            secrets = files.secrets_path
            assert headers.exists()
            assert secrets.exists()

            proc = RunnerProcess(argv=_snippet_argv("pass"), override_files=files)
            await proc.start()
            async for _ in proc.stream():
                pass
            await proc.wait()
            await proc.aclose()

            assert not headers.exists()
            assert not secrets.exists()

        _asyncio_run(_run())


class TestStreamExitsWhenGrandchildHoldsPipes:
    """Regression: Chromium (grandchild of the runner) inherits the
    stdio pipes and keeps them open past the runner's own exit. The
    stream must still complete so the TUI can transition to "done"."""

    def test_stream_completes_after_main_exit_despite_open_pipes(self):
        import time as _time

        async def _run():
            # Parent: print one line and exit. The child inherits FD 1
            # / 2 and sits there for 10s holding them open — simulates
            # Chromium continuing to "exist" briefly after Nova Act
            # has already told Python the run is done.
            body = (
                "import os, sys, time;"
                "print('main exiting');"
                "pid = os.fork();"
                "(time.sleep(10) if pid == 0 else sys.exit(0))"
            )
            proc = RunnerProcess(
                argv=_snippet_argv(body),
                override_files=OverrideFiles(),
            )
            await proc.start()

            started = _time.monotonic()
            lines: list[tuple[str, str]] = []
            async for stream, line in proc.stream():
                lines.append((stream, line))
            elapsed = _time.monotonic() - started
            result = await proc.wait()
            await proc.aclose()

            # The main process's output must have been received.
            assert any("main exiting" in l for _, l in lines)
            # The exit code must be 0 (main process exited cleanly).
            assert result.exit_code == 0
            # The stream must complete within the grace window
            # (2s) + a small buffer, NOT after 10s (the grandchild's
            # sleep). If this regresses we'd see elapsed ~= 10.
            assert elapsed < 5.0, f"stream hung for {elapsed:.1f}s — grandchild pipe regression"

            # Kill the grandchild so the test doesn't leak it.
            import os
            import signal as _signal
            # Best-effort — the process group already has the sleeper.
            try:
                os.killpg(os.getpgid(proc._proc.pid), _signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass

        _asyncio_run(_run())
