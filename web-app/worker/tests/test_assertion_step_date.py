"""Integration tests for the date branch in execute_assertion_step (Task 4)."""

import json

import pytest

from assertion_step import execute_assertion_step
from models import ExecutionStep
from transform.date_compare import NAIVE_MIXED_WARNING


def _make_step(
    *,
    operator: str,
    validation_value: str,
    assertion_variable: str = "captured_date",
) -> ExecutionStep:
    """Build an ExecutionStep with required fields and date-assertion config."""
    return ExecutionStep(
        pk="exec#test",
        sk="step#1",
        step_id="step-1",
        sort=1,
        instruction="",
        artefact="",
        logs=[],
        created_at="2024-01-01T00:00:00+00:00",
        secret_key="",
        step_type="assertion",
        validation_type="date",
        validation_operator=operator,
        validation_value=validation_value,
        capture_variable="",
        value_type="",
        assertion_variable=assertion_variable,
    )


# ── Happy path per operator ──────────────────────────────────────────────


class TestHappyPath:
    def test_before_succeeds(self):
        step = _make_step(operator="before", validation_value="2024-01-05")
        result, success, logs, actual = execute_assertion_step(
            step, {"captured_date": "2024-01-02"}
        )
        assert success is True
        assert logs == ""
        assert actual == "2024-01-02"
        assert result is not None  # SimpleNamespace returned

    def test_after_succeeds(self):
        step = _make_step(operator="after", validation_value="2024-01-02")
        _, success, _, _ = execute_assertion_step(
            step, {"captured_date": "2024-01-05"}
        )
        assert success is True

    def test_equals_succeeds(self):
        step = _make_step(operator="equals", validation_value="2024-01-02")
        _, success, _, _ = execute_assertion_step(
            step, {"captured_date": "2024-01-02"}
        )
        assert success is True

    def test_not_equals_succeeds(self):
        step = _make_step(operator="not_equals", validation_value="2024-01-05")
        _, success, _, _ = execute_assertion_step(
            step, {"captured_date": "2024-01-02"}
        )
        assert success is True


class TestVariableVsVariableComparison:
    """Both sides come from runtime variables; the worker is expected to
    have already template-resolved validation_value before invoking us."""

    def test_after_with_resolved_variable_value(self):
        # Simulating: validation_value originally was "{{ order_date_before }}"
        # and the template parser resolved it to the date string before the
        # step was dispatched.
        step = _make_step(
            operator="after",
            validation_value="2024-01-02T10:00:00+00:00",  # resolved
        )
        _, success, _, _ = execute_assertion_step(
            step, {"captured_date": "2024-01-02T15:30:00+00:00"}
        )
        assert success is True


# ── equals_within end-to-end ────────────────────────────────────────────


class TestEqualsWithin:
    def test_within_tolerance(self):
        payload = json.dumps(
            {"date": "2024-01-02T15:00:00+00:00", "tolerance": 5, "unit": "minutes"}
        )
        step = _make_step(operator="equals_within", validation_value=payload)
        _, success, logs, _ = execute_assertion_step(
            step, {"captured_date": "2024-01-02T15:03:00+00:00"}
        )
        assert success is True
        assert logs == ""

    def test_outside_tolerance(self):
        payload = json.dumps(
            {"date": "2024-01-02T15:00:00+00:00", "tolerance": 5, "unit": "minutes"}
        )
        step = _make_step(operator="equals_within", validation_value=payload)
        _, success, logs, _ = execute_assertion_step(
            step, {"captured_date": "2024-01-02T15:10:00+00:00"}
        )
        assert success is False
        assert "exceeds tolerance" in logs

    def test_malformed_json_fails_step_with_clear_log(self):
        step = _make_step(operator="equals_within", validation_value="not-json")
        _, success, logs, _ = execute_assertion_step(
            step, {"captured_date": "2024-01-02"}
        )
        assert success is False
        assert "must be JSON" in logs
        assert logs.startswith("Date assertion error")


# ── Naive-vs-aware warning surfaces in step logs ────────────────────────


class TestNaiveAwareWarning:
    def test_naive_actual_with_aware_expected_warns_but_passes(self):
        step = _make_step(
            operator="equals", validation_value="2024-01-02T15:00:00+00:00"
        )
        _, success, logs, _ = execute_assertion_step(
            step, {"captured_date": "2024-01-02T15:00:00"}  # naive
        )
        assert success is True
        assert NAIVE_MIXED_WARNING in logs

    def test_warning_does_not_overwrite_failure_log(self):
        step = _make_step(
            operator="equals", validation_value="2024-01-05T15:00:00+00:00"
        )
        _, success, logs, _ = execute_assertion_step(
            step, {"captured_date": "2024-01-02T15:00:00"}
        )
        assert success is False
        assert NAIVE_MIXED_WARNING in logs
        assert "does not equal" in logs


# ── Error paths ──────────────────────────────────────────────────────────


class TestErrors:
    def test_unknown_date_operator_fails_step(self):
        step = _make_step(operator="between", validation_value="2024-01-02")
        _, success, logs, _ = execute_assertion_step(
            step, {"captured_date": "2024-01-02"}
        )
        assert success is False
        assert "Unknown date operator" in logs

    def test_ambiguous_captured_value_fails_step(self):
        step = _make_step(operator="equals", validation_value="2024-01-02")
        _, success, logs, _ = execute_assertion_step(
            step, {"captured_date": "01/02/2024"}  # ambiguous, no format
        )
        assert success is False
        assert "ambiguous" in logs

    def test_ambiguous_expected_value_fails_step(self):
        step = _make_step(operator="equals", validation_value="01/02/2024")
        _, success, logs, _ = execute_assertion_step(
            step, {"captured_date": "2024-01-02"}
        )
        assert success is False
        assert "ambiguous" in logs

    def test_missing_runtime_variable_uses_existing_branch(self):
        # This is existing behavior — the date branch is never reached if
        # the variable lookup fails first. Documenting it here so we
        # notice if future refactors break it.
        step = _make_step(operator="equals", validation_value="2024-01-02")
        _, success, logs, actual = execute_assertion_step(step, {})
        assert success is False
        assert "not found" in logs
        assert actual == "VARIABLE_NOT_FOUND"


# ── Existing branches still work (regression guard) ────────────────────


class TestExistingBranchesUnaffected:
    def test_string_exact_still_works(self):
        step = ExecutionStep(
            pk="exec", sk="step", step_id="s1", sort=1, instruction="",
            artefact="", logs=[], created_at="", secret_key="",
            step_type="assertion",
            validation_type="string", validation_operator="exact",
            validation_value="hello",
            capture_variable="", value_type="",
            assertion_variable="captured",
        )
        _, success, logs, _ = execute_assertion_step(step, {"captured": "hello"})
        assert success is True

    def test_number_greater_than_still_works(self):
        step = ExecutionStep(
            pk="exec", sk="step", step_id="s1", sort=1, instruction="",
            artefact="", logs=[], created_at="", secret_key="",
            step_type="assertion",
            validation_type="number", validation_operator="greater_then",
            validation_value="5",
            capture_variable="", value_type="",
            assertion_variable="captured",
        )
        _, success, _, _ = execute_assertion_step(step, {"captured": "10"})
        assert success is True

    def test_unknown_validation_type_still_fails_clearly(self):
        step = ExecutionStep(
            pk="exec", sk="step", step_id="s1", sort=1, instruction="",
            artefact="", logs=[], created_at="", secret_key="",
            step_type="assertion",
            validation_type="banana", validation_operator="equals",
            validation_value="x",
            capture_variable="", value_type="",
            assertion_variable="captured",
        )
        _, success, logs, _ = execute_assertion_step(step, {"captured": "x"})
        assert success is False
        assert "Unknown validation type" in logs
