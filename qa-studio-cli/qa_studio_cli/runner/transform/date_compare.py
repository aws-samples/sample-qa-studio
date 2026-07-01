"""Date assertion helper.

Mirror of ``web-app/worker/transform/date_compare.py``. The two
implementations MUST stay in lockstep — see
``tests/test_transform_registry_consistency.py`` for the cross-package
check that includes :data:`DATE_OPERATORS`.

The :mod:`qa_studio_cli.runner.transform.date_parser` module handles
parsing. This module layers operator dispatch, the ``equals_within``
JSON payload, and the naive-vs-aware warning on top, so the CLI's
assertion and validation step paths share a single comparison surface
(matching the worker's pattern).

Public entry point is :func:`evaluate_date_assertion`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Callable, Literal

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from qa_studio_cli.runner.transform.date_parser import parse_to_utc

NAIVE_MIXED_WARNING = (
    "Comparing naive datetime (assumed UTC) with TZ-aware datetime. "
    "If this is unintended, ensure both values use the same TZ convention."
)

DATE_OPERATORS = frozenset({"before", "after", "equals", "not_equals", "equals_within"})

_SECONDS_PER_UNIT: dict[str, int] = {
    "seconds": 1,
    "minutes": 60,
    "hours": 60 * 60,
    "days": 60 * 60 * 24,
    "weeks": 60 * 60 * 24 * 7,
}

_OPERATOR_FN: dict[str, Callable[[datetime, datetime], bool]] = {
    "before": lambda a, e: a < e,
    "after": lambda a, e: a > e,
    "equals": lambda a, e: a == e,
    "not_equals": lambda a, e: a != e,
}

_OPERATOR_FAILURE_MSG: dict[str, str] = {
    "before": "Date assertion failed: '{actual}' is not before '{expected}'",
    "after": "Date assertion failed: '{actual}' is not after '{expected}'",
    "equals": "Date assertion failed: '{actual}' does not equal '{expected}'",
    "not_equals": "Date assertion failed: '{actual}' equals '{expected}' (expected inequality)",
}


class EqualsWithinPayload(BaseModel):
    """JSON shape for the ``equals_within`` tolerance encoding (spec R6).

    Example::

        {"date": "2024-01-02T15:00:00+00:00", "tolerance": 5, "unit": "minutes"}
    """

    date: str
    tolerance: int = Field(ge=0)
    unit: Literal["seconds", "minutes", "hours", "days", "weeks"]


def evaluate_date_assertion(
    actual: str,
    validation_value: str,
    operator: str,
) -> tuple[bool, str]:
    """Evaluate a date comparison.

    Args:
        actual: The actual date string to compare (from runtime variables
            or AI extraction).
        validation_value: The expected value. For most operators this is
            a date string. For ``equals_within`` it is a JSON string
            with the shape declared by :class:`EqualsWithinPayload`.
        operator: One of the values in :data:`DATE_OPERATORS`.

    Returns:
        ``(success, logs)``. ``logs`` is empty on success unless the
        comparison mixed a naive value with a TZ-aware value, in which
        case it contains :data:`NAIVE_MIXED_WARNING`. On failure, ``logs``
        contains a description and (if applicable) the warning.

    Raises:
        DateParseError: For unparseable date strings (passed through from
            ``parse_to_utc``).
        ValueError: For unknown operators or invalid ``equals_within``
            payloads.
    """
    if operator not in DATE_OPERATORS:
        raise ValueError(
            f"Unknown date operator: '{operator}'. Expected one of "
            f"{sorted(DATE_OPERATORS)}."
        )

    actual_dt, actual_naive = parse_to_utc(actual)

    if operator == "equals_within":
        expected_dt, expected_naive, tolerance = _parse_equals_within_payload(validation_value)
        delta = abs(actual_dt - expected_dt)
        success = delta <= tolerance
        failure_log = (
            ""
            if success
            else (
                f"Date assertion failed: |{actual} - {validation_value}| "
                f"= {delta} exceeds tolerance {tolerance}"
            )
        )
    else:
        expected_dt, expected_naive = parse_to_utc(validation_value)
        success = _OPERATOR_FN[operator](actual_dt, expected_dt)
        failure_log = (
            ""
            if success
            else _OPERATOR_FAILURE_MSG[operator].format(
                actual=actual, expected=validation_value
            )
        )

    warning = NAIVE_MIXED_WARNING if (actual_naive ^ expected_naive) else ""
    logs = " ".join(part for part in (warning, failure_log) if part)
    return success, logs


def _parse_equals_within_payload(payload_str: str) -> tuple[datetime, bool, timedelta]:
    """Parse JSON validation_value for the ``equals_within`` operator.

    Returns:
        ``(expected_dt, was_naive_input, tolerance_timedelta)``

    Raises:
        ValueError: On malformed JSON, missing fields, invalid types,
            negative tolerance, or unsupported unit.
    """
    try:
        raw = json.loads(payload_str)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"equals_within validation_value must be JSON; got '{payload_str}'"
        ) from exc

    if not isinstance(raw, dict):
        raise ValueError(
            f"equals_within validation_value JSON must be an object; got {type(raw).__name__}"
        )

    try:
        payload = EqualsWithinPayload(**raw)
    except PydanticValidationError as exc:
        raise ValueError(
            f"equals_within validation_value has invalid shape: {exc.errors()}"
        ) from exc

    expected_dt, was_naive = parse_to_utc(payload.date)
    tolerance = timedelta(seconds=payload.tolerance * _SECONDS_PER_UNIT[payload.unit])
    return expected_dt, was_naive, tolerance
