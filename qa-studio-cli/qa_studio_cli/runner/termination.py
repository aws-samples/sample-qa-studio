"""SIGTERM handling for ``qa-studio run``.

Python's default SIGTERM disposition kills the interpreter without running any
``finally`` block, so a cancelled CI job or a stopped cloud worker leaked its
AgentCore browser and left the execution ``running`` forever.  This module
turns the signal into :class:`RunnerTerminated`, raised in the **main
thread**.  :func:`qa_studio_cli.runner.deadline.run_bounded` keeps the main
thread free for exactly that: the run body executes on a worker thread, the
main thread only waits, catches the exception and terminates the run's
:class:`~qa_studio_cli.runner.deadline.RunDeadline` so the engine's existing
deadline checks and ``finally`` blocks stop the run and tear everything down.

Env contract with the parent (the MicroVM supervisor, a CI runner, the TUI):

``QA_STUDIO_TERMINATION_REASON``
    ``terminated`` (default: a user stop, a cancelled job) or ``timeout`` (the
    parent enforces a run ceiling and is about to kill us).  The execution's
    ``error_message`` starts with ``terminated:`` or ``timeout:`` accordingly.
``QA_STUDIO_MAX_DURATION_SECONDS``
    Optional, integer.  The parent's ceiling, named in the ``timeout:`` message.

Both are read when the signal arrives, not when the handler is installed.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import threading
from typing import Iterator, Literal, Mapping

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

TERMINATION_REASON_ENV = "QA_STUDIO_TERMINATION_REASON"
MAX_DURATION_ENV = "QA_STUDIO_MAX_DURATION_SECONDS"

REASON_TERMINATED = "terminated"
REASON_TIMEOUT = "timeout"

TerminationReason = Literal["terminated", "timeout"]


class Termination(BaseModel):
    """Why the parent stopped the run, and the message the execution records."""

    model_config = ConfigDict(frozen=True)

    reason: TerminationReason
    message: str


class RunnerTerminated(BaseException):
    """SIGTERM arrived.

    A ``BaseException`` (like ``KeyboardInterrupt``) so the runner's many
    ``except Exception`` blocks cannot mistake it for a test failure.
    """

    def __init__(self, termination: Termination):
        super().__init__(termination.message)
        self.termination = termination


def resolve_termination(environ: Mapping[str, str] = os.environ) -> Termination:
    """Map the env contract to a :class:`Termination`.

    Unknown reasons and unparsable ceilings are logged and ignored, never
    fatal — the run is being stopped either way.
    """
    reason = environ.get(TERMINATION_REASON_ENV, REASON_TERMINATED)
    if reason != REASON_TIMEOUT:
        if reason != REASON_TERMINATED:
            logger.warning(
                "%s=%r is not a known reason; reporting the run as terminated",
                TERMINATION_REASON_ENV, reason,
            )
        return Termination(reason=REASON_TERMINATED, message="terminated: run stopped by SIGTERM")

    message = "timeout: run exceeded the configured ceiling"
    raw_ceiling = environ.get(MAX_DURATION_ENV)
    if raw_ceiling is not None:
        try:
            message += f" of {int(raw_ceiling)}s"
        except ValueError:
            logger.warning("%s=%r is not an integer; omitting the ceiling", MAX_DURATION_ENV, raw_ceiling)
    return Termination(reason=REASON_TIMEOUT, message=message)


@contextlib.contextmanager
def sigterm_raises() -> Iterator[None]:
    """Raise :class:`RunnerTerminated` in the main thread on SIGTERM.

    The previous disposition is restored on exit.  Signal handlers can only be
    installed from the main thread; elsewhere this is a logged no-op so a
    library caller keeps the default behaviour instead of crashing.
    """
    if threading.current_thread() is not threading.main_thread():
        logger.warning("Not on the main thread; SIGTERM keeps its default disposition")
        yield
        return

    def _handler(signum: int, _frame) -> None:
        raise RunnerTerminated(resolve_termination())

    previous = signal.signal(signal.SIGTERM, _handler)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)
