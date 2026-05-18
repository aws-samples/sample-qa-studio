"""Integration tests for the date branch in execute_validation_step (Task 5).

Uses a mocked NovaAct that returns canned date strings, mirroring the
operator coverage from test_assertion_step_date.py.
"""

import json
from unittest.mock import MagicMock

import pytest

from models import ExecutionStep
from transform.date_compare import NAIVE_MIXED_WARNING
from validation_step import execute_validation_step


def _make_step(
    *,
    operator: str,
    validation_value: str,
    instruction: str = "Get the date",
) -> ExecutionStep:
    return ExecutionStep(
        pk="EXECUTION#e1",
        sk="EXECUTION_STEP#s1",
        step_id="s1",
        sort=1,
        instruction=instruction,
        artefact="",
        logs=[],
        created_at="2024-01-01T00:00:00+00:00",
        secret_key="",
        step_type="validation",
        validation_type="date",
        validation_operator=operator,
        validation_value=validation_value,
        capture_variable="",
        value_type="",
        assertion_variable="",
    )


def _make_nova(extracted_value: str) -> MagicMock:
    """Mock NovaAct whose act_get returns ``extracted_value`` as parsed_response."""
    nova = MagicMock()
    response = MagicMock()
    response.parsed_response = extracted_value
    response.metadata = MagicMock()
    response.metadata.act_id = "act-123"
    nova.act_get.return_value = response
    return nova


# ── Happy path per operator ──────────────────────────────────────────────


class TestHappyPath:
    def test_before_succeeds(self):
        nova = _make_nova("2024-01-02")
        step = _make_step(operator="before", validation_value="2024-01-05")
        _, success, logs, actual = execute_validation_step(nova, step)
        assert success is True
        assert logs == ""
        assert actual == "2024-01-02"
        nova.act_get.assert_called_once()

    def test_after_succeeds(self):
        nova = _make_nova("2024-01-05")
        step = _make_step(operator="after", validation_value="2024-01-02")
        _, success, _, _ = execute_validation_step(nova, step)
        assert success is True

    def test_equals_succeeds(self):
        nova = _make_nova("2024-01-02")
        step = _make_step(operator="equals", validation_value="2024-01-02")
        _, success, _, _ = execute_validation_step(nova, step)
        assert success is True

    def test_not_equals_succeeds(self):
        nova = _make_nova("2024-01-02")
        step = _make_step(operator="not_equals", validation_value="2024-01-05")
        _, success, _, _ = execute_validation_step(nova, step)
        assert success is True


class TestFailures:
    def test_before_fails_when_actual_after_expected(self):
        nova = _make_nova("2024-01-05")
        step = _make_step(operator="before", validation_value="2024-01-02")
        _, success, logs, _ = execute_validation_step(nova, step)
        assert success is False
        assert "is not before" in logs

    def test_equals_fails_for_different_dates(self):
        nova = _make_nova("2024-01-02")
        step = _make_step(operator="equals", validation_value="2024-01-05")
        _, success, logs, _ = execute_validation_step(nova, step)
        assert success is False
        assert "does not equal" in logs


# ── equals_within end-to-end ─────────────────────────────────────────────


class TestEqualsWithin:
    def test_within_tolerance(self):
        payload = json.dumps(
            {"date": "2024-01-02T15:00:00+00:00", "tolerance": 5, "unit": "minutes"}
        )
        nova = _make_nova("2024-01-02T15:03:00+00:00")
        step = _make_step(operator="equals_within", validation_value=payload)
        _, success, logs, _ = execute_validation_step(nova, step)
        assert success is True
        assert logs == ""

    def test_outside_tolerance(self):
        payload = json.dumps(
            {"date": "2024-01-02T15:00:00+00:00", "tolerance": 5, "unit": "minutes"}
        )
        nova = _make_nova("2024-01-02T15:10:00+00:00")
        step = _make_step(operator="equals_within", validation_value=payload)
        _, success, logs, _ = execute_validation_step(nova, step)
        assert success is False
        assert "exceeds tolerance" in logs

    def test_malformed_json_fails_step_with_clear_log(self):
        nova = _make_nova("2024-01-02")
        step = _make_step(operator="equals_within", validation_value="not-json")
        _, success, logs, _ = execute_validation_step(nova, step)
        assert success is False
        assert "must be JSON" in logs
        assert logs.startswith("Date validation error")


# ── Naive-vs-aware warning surfaces in step logs ────────────────────────


class TestNaiveAwareWarning:
    def test_naive_extracted_with_aware_expected(self):
        nova = _make_nova("2024-01-02T15:00:00")  # naive
        step = _make_step(
            operator="equals", validation_value="2024-01-02T15:00:00+00:00"
        )
        _, success, logs, _ = execute_validation_step(nova, step)
        assert success is True
        assert NAIVE_MIXED_WARNING in logs

    def test_warning_does_not_overwrite_failure_log(self):
        nova = _make_nova("2024-01-02T15:00:00")
        step = _make_step(
            operator="equals", validation_value="2024-01-05T15:00:00+00:00"
        )
        _, success, logs, _ = execute_validation_step(nova, step)
        assert success is False
        assert NAIVE_MIXED_WARNING in logs
        assert "does not equal" in logs


# ── Error paths ──────────────────────────────────────────────────────────


class TestErrors:
    def test_unknown_date_operator_fails_step(self):
        nova = _make_nova("2024-01-02")
        step = _make_step(operator="between", validation_value="2024-01-02")
        _, success, logs, _ = execute_validation_step(nova, step)
        assert success is False
        assert "Unknown date operator" in logs

    def test_ambiguous_extracted_value_fails_step(self):
        nova = _make_nova("01/02/2024")  # ambiguous, no format
        step = _make_step(operator="equals", validation_value="2024-01-02")
        _, success, logs, _ = execute_validation_step(nova, step)
        assert success is False
        assert "ambiguous" in logs

    def test_ambiguous_expected_value_fails_step(self):
        nova = _make_nova("2024-01-02")
        step = _make_step(operator="equals", validation_value="01/02/2024")
        _, success, logs, _ = execute_validation_step(nova, step)
        assert success is False
        assert "ambiguous" in logs

    def test_none_extracted_value_treated_as_empty_string(self):
        nova = MagicMock()
        response = MagicMock()
        response.parsed_response = None
        response.metadata = MagicMock(act_id="act-123")
        nova.act_get.return_value = response

        step = _make_step(operator="equals", validation_value="2024-01-02")
        _, success, logs, _ = execute_validation_step(nova, step)
        # Empty string is not a valid date — step fails with the empty-string error.
        assert success is False
        assert "Empty" in logs or "ambiguous" in logs


# ── Schema choice ────────────────────────────────────────────────────────


class TestSchemaChoice:
    def test_uses_string_schema(self):
        """Date validation_type should call act_get with STRING_SCHEMA, since
        Nova has no native date schema; QA Studio parses on its side."""
        from utils import STRING_SCHEMA
        nova = _make_nova("2024-01-02")
        step = _make_step(operator="equals", validation_value="2024-01-02")
        execute_validation_step(nova, step)
        # The schema kwarg is the string schema.
        _, kwargs = nova.act_get.call_args
        assert kwargs.get("schema") is STRING_SCHEMA
