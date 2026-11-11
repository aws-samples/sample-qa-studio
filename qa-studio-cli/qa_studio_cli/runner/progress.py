"""User-facing progress lines for ``qa-studio run``.

This module is the *only* place that prints "what is happening right now"
during a run.  It is deliberately independent of the ``logging`` module: the
console logging handler is WARNING by default (DEBUG with ``--verbose``), so a
future ``logger.info`` can never leak into — or disappear from — the default
output.

Stream contract
---------------
* Progress lines go to **stderr** (``click.echo(..., err=True)``).
* **stdout** is reserved for the result: the ``--format json`` document or the
  human summary.  ``qa-studio run … 2>/dev/null | jq .status`` therefore works.

Line formats are a user-facing contract and are documented in
``docs/ci-cd-integration.md``; change the constants below and the docs
together.  Every line is passed through ``log_filters.redact`` because
progress bypasses the logging ``SecretRedactionFilter``.

Timestamps are ``HH:MM:SS`` (no date) so they interleave cleanly with the
``[HH:MM:SS] LEVEL message`` logging lines in verbose mode.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import click

from qa_studio_cli.utils.log_filters import redact

TIME_FORMAT = "%H:%M:%S"

TEST_STARTED_FORMAT = '[{time}] Executing Test "{name}"'
TEST_STARTED_EXECUTION_SUFFIX = " (execution {execution_id})"
STEP_STARTED_FORMAT = "[{time}] {label}: {instruction}"
STEP_VALIDATION_SUFFIX = " ({validation_value})"
SUITE_PREFIX_FORMAT = "[{test_name}] "
RUN_TIMED_OUT_FORMAT = "[{time}] ERROR {message}"


def _now() -> datetime:
    """Wall clock for the timestamp prefix; tests monkeypatch this."""
    return datetime.now()


def _emit(line: str) -> None:
    click.echo(redact(line), err=True)


def step_label(step: Dict[str, Any]) -> str:
    """``Step 7`` or ``Step 7 (row 2/3)`` for a (possibly repeat-expanded) step."""
    label = f"Step {step.get('sort', 0)}"
    row_index = step.get("repeat_row_index")
    if row_index is not None:
        label += f" (row {row_index}/{step.get('repeat_row_total', '?')})"
    return label


def test_started(name: str, *, execution_id: Optional[str] = None) -> None:
    """Announce that a test (use case) is starting.

    ``execution_id`` is given for remote runs — it is how the run is found in
    the web UI.
    """
    line = TEST_STARTED_FORMAT.format(time=_now().strftime(TIME_FORMAT), name=name)
    if execution_id:
        line += TEST_STARTED_EXECUTION_SUFFIX.format(execution_id=execution_id)
    _emit(line)


def step_started(
    step: Dict[str, Any],
    instruction: str,
    *,
    test_name: Optional[str] = None,
) -> None:
    """Announce that a step is starting.

    ``instruction`` is the *resolved* instruction (templates expanded) — the
    engine resolves before calling, so ``step["instruction"]`` is not used.
    ``step`` should likewise be the resolved step so a ``validation_value``
    shows expanded values.  ``test_name`` prefixes the line in suite runs,
    where several tests may interleave.
    """
    label = step_label(step)
    if test_name is not None:
        label = SUITE_PREFIX_FORMAT.format(test_name=test_name) + label
    line = STEP_STARTED_FORMAT.format(
        time=_now().strftime(TIME_FORMAT), label=label, instruction=instruction,
    )
    validation_value = step.get("validation_value")
    if validation_value:
        line += STEP_VALIDATION_SUFFIX.format(validation_value=validation_value)
    _emit(line)


def _run_stopped(message: str) -> None:
    _emit(RUN_TIMED_OUT_FORMAT.format(time=_now().strftime(TIME_FORMAT), message=message))


def run_timed_out(message: str) -> None:
    """Announce that ``--timeout`` stopped the run (exit code 3)."""
    _run_stopped(message)


def run_terminated(message: str) -> None:
    """Announce that SIGTERM stopped the run (exit code 143, or 3 when the
    parent reports a timeout).  Same line shape as :func:`run_timed_out`."""
    _run_stopped(message)
