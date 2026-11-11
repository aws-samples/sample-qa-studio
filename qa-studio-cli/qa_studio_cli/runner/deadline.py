"""Whole-run stop control for ``qa-studio run``: ``--timeout`` and SIGTERM.

Every run has a :class:`RunDeadline`.  ``--timeout`` gives it a time limit
(unset by default: unlimited); SIGTERM terminates it early (see
:mod:`qa_studio_cli.runner.termination`).  Either way the run stops in two
layers:

1. **Cooperative stop.**  The runner checks the deadline before each use case
   and the engine checks it before each step.  On expiry the current use case
   is failed with :attr:`RunDeadline.message` (remote runs mark the step and
   the execution failed through the normal status API), the remaining use cases
   are skipped, browsers are torn down by the usual ``finally`` blocks, and the
   process exits with :attr:`RunDeadline.exit_code`.
2. **Hard stop.**  A single step can block far longer than that (a stuck
   ``nova.act``).  :func:`run_bounded` therefore runs the whole run in a worker
   thread and waits at most ``remaining + HARD_STOP_GRACE_SECONDS`` (time
   limit) or ``TERMINATION_GRACE_SECONDS`` (SIGTERM).  If the thread is still
   busy then, it runs the registered cleanups (browser teardowns, marking
   in-flight executions failed) and exits with :attr:`RunDeadline.exit_code`
   without waiting for the stuck thread.

The run body always runs on the worker thread, also without ``--timeout``:
the main thread must be free to receive SIGTERM as :class:`RunnerTerminated`
at a known place.  No ``signal.alarm``: it only works on the main thread and
Nova Act / Playwright run on worker threads.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import math
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from qa_studio_cli.runner import progress
from qa_studio_cli.runner.termination import (
    REASON_TIMEOUT,
    RunnerTerminated,
    Termination,
    sigterm_raises,
)
from qa_studio_cli.utils.errors import sanitize_error_message

logger = logging.getLogger(__name__)

#: Exit code of a run stopped by ``--timeout`` or by a parent that reports a
#: timeout (0 = passed, 1 = test failed, 2 = runner error).
EXIT_TIMEOUT = 3

#: Exit code of a run stopped by SIGTERM (128 + 15, the shell convention).
EXIT_TERMINATED = 143

#: How long the hard stop waits past the deadline for the cooperative stop
#: (the step that is running when the deadline passes) to finish.
HARD_STOP_GRACE_SECONDS = 30.0

#: How long a SIGTERM waits for the cooperative stop before the hard stop.
#: Parents SIGKILL after their own grace (supervisor 30 s, TUI 5 s), so this
#: plus the hard stop's own API calls must stay well below that.
TERMINATION_GRACE_SECONDS = 10.0

#: Upper bound of a single ``Thread.join`` so a pending signal handler always
#: gets to run between joins, whatever the interpreter's join semantics.
JOIN_POLL_SECONDS = 0.5


class RunDeadline:
    """When the run must stop, plus the cleanups a hard stop must run.

    ``seconds=None`` is a run without a time limit; it still expires when
    :meth:`terminate` is called (SIGTERM).  Thread-safe: the engine registers
    cleanups from worker threads while the watchdog may run them from the
    main thread.
    """

    def __init__(self, seconds: Optional[int], clock: Callable[[], float] = time.monotonic):
        if seconds is not None and seconds <= 0:
            raise ValueError("timeout must be a positive number of seconds")
        self.seconds = seconds
        self._clock = clock
        self._expires_at = math.inf if seconds is None else clock() + seconds
        self._lock = threading.Lock()
        self._ids = itertools.count()
        self._cleanups: Dict[int, Callable[[], None]] = {}
        self._executions: Dict[Tuple[str, str], Any] = {}
        self._termination: Optional[Termination] = None

    @classmethod
    def start(cls, seconds: Optional[int]) -> "RunDeadline":
        """A deadline starting now; unlimited when no timeout was given."""
        return cls(seconds)

    @property
    def terminated(self) -> bool:
        """``True`` once :meth:`terminate` was called (SIGTERM)."""
        return self._termination is not None

    @property
    def message(self) -> str:
        """Why the run stopped — meaningful once :meth:`expired` is true."""
        if self._termination is not None:
            return self._termination.message
        return f"Run timed out after {self.seconds}s (--timeout)"

    @property
    def exit_code(self) -> int:
        """Process exit code for an unsuccessful run stopped by this deadline."""
        if self._termination is not None and self._termination.reason != REASON_TIMEOUT:
            return EXIT_TERMINATED
        return EXIT_TIMEOUT

    def terminate(self, termination: Termination) -> None:
        """Expire the deadline now because the parent asked us to stop.

        The first termination wins; a repeated SIGTERM does not rewrite the
        reason the execution already reports.
        """
        with self._lock:
            if self._termination is None:
                self._termination = termination

    def remaining(self) -> float:
        if self.terminated:
            return 0.0
        return max(0.0, self._expires_at - self._clock())

    def expired(self) -> bool:
        return self.terminated or self._clock() >= self._expires_at

    # -- hard-stop registry ------------------------------------------------

    def add_cleanup(self, fn: Callable[[], None]) -> int:
        """Register a cleanup for the hard stop; returns a token for removal."""
        with self._lock:
            token = next(self._ids)
            self._cleanups[token] = fn
            return token

    def remove_cleanup(self, token: Optional[int]) -> None:
        if token is None:
            return
        with self._lock:
            self._cleanups.pop(token, None)

    def track_execution(self, execution_api: Any, usecase_id: str, execution_id: str) -> None:
        """Mark a remote execution in flight; a hard stop fails it."""
        with self._lock:
            self._executions[(usecase_id, execution_id)] = execution_api

    def untrack_execution(self, usecase_id: str, execution_id: str) -> None:
        with self._lock:
            self._executions.pop((usecase_id, execution_id), None)

    def hard_stop_cleanup(self) -> None:
        """Fail every in-flight execution, then run every cleanup.

        Each action is best effort: one failure never prevents the others.
        An execution the API already considers terminal (409/400) is logged.
        """
        with self._lock:
            executions = list(self._executions.items())
            cleanups = list(self._cleanups.values())
            self._executions.clear()
            self._cleanups.clear()
        for (usecase_id, execution_id), execution_api in executions:
            try:
                asyncio.run(execution_api.update_status(
                    usecase_id=usecase_id, execution_id=execution_id,
                    status="failed", error_message=self.message,
                ))
            except Exception as e:
                logger.warning(
                    "Failed to mark execution %s failed (%s): %s",
                    execution_id, self.message, sanitize_error_message(str(e)),
                )
        for cleanup in cleanups:
            try:
                cleanup()
            except Exception as e:
                logger.warning("Stop cleanup raised: %s", sanitize_error_message(str(e)))


def _exit_now(code: int) -> None:
    """Exit without joining the stuck worker thread (tests patch this)."""
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def _join(worker: threading.Thread, seconds: float) -> None:
    """``worker.join(seconds)`` in :data:`JOIN_POLL_SECONDS` slices.

    A pending SIGTERM handler runs between slices and its exception propagates
    out of here.  ``seconds`` may be ``math.inf``.
    """
    end = time.monotonic() + seconds
    while worker.is_alive():
        left = end - time.monotonic()
        if left <= 0:
            return
        worker.join(min(left, JOIN_POLL_SECONDS))


def _run_and_wait(
    worker: threading.Thread,
    deadline: RunDeadline,
    grace_seconds: float,
    termination_grace_seconds: float,
) -> None:
    """Start the run body and wait until it finished or the stop grace passed.

    SIGTERM (as :class:`RunnerTerminated`, raised anywhere in here — even
    inside ``worker.start()``) terminates ``deadline`` so the body stops
    cooperatively, then gets ``termination_grace_seconds`` to do so.  A second
    SIGTERM during that grace ends the wait at once.  The caller holds
    :func:`sigterm_raises`.
    """
    try:
        worker.start()
        while worker.is_alive() and not deadline.expired():
            # Re-check the deadline every slice (its clock is injectable).
            _join(worker, min(deadline.remaining(), JOIN_POLL_SECONDS))
        if worker.is_alive():
            _join(worker, grace_seconds)
    except RunnerTerminated as stop:
        deadline.terminate(stop.termination)
        progress.run_terminated(deadline.message)
        logger.warning("SIGTERM received: %s", deadline.message)
        try:
            _join(worker, termination_grace_seconds)
        except RunnerTerminated:
            logger.warning("Second SIGTERM received; stopping without further grace")


def run_bounded(
    deadline: RunDeadline,
    fn: Callable[[], Any],
    grace_seconds: float = HARD_STOP_GRACE_SECONDS,
    termination_grace_seconds: float = TERMINATION_GRACE_SECONDS,
) -> Any:
    """Run ``fn`` under ``deadline`` (see the module docstring).

    ``fn`` runs on a daemon thread; its return value or exception (including
    ``SystemExit`` from the runner's ``sys.exit``) is re-raised here.  The
    SIGTERM handler is installed before the thread starts and stays active
    until the run finished or the hard stop exits.  If the thread outlives the
    deadline plus its grace, the hard stop runs and the process exits with
    :attr:`RunDeadline.exit_code`.
    """
    outcome: Dict[str, Any] = {}

    def _target() -> None:
        try:
            outcome["value"] = fn()
        except BaseException as e:  # noqa: BLE001 — re-raised on the caller's thread
            outcome["error"] = e

    worker = threading.Thread(target=_target, name="qa-studio-run", daemon=True)
    with sigterm_raises():
        _run_and_wait(worker, deadline, grace_seconds, termination_grace_seconds)
        if worker.is_alive():
            if not deadline.terminated:
                progress.run_timed_out(deadline.message)
            deadline.hard_stop_cleanup()
            _exit_now(deadline.exit_code)
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")
