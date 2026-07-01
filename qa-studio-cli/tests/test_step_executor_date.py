"""Integration tests for the validation_type=date branch in the CLI runner (Task 6).

Covers both ``_execute_assertion`` (variable-vs-value) and
``_execute_validation`` (Nova-extraction-vs-value) paths.
"""

import json
from unittest.mock import MagicMock

import pytest

from qa_studio_cli.runner.step_executor import StepExecutor
from qa_studio_cli.runner.transform.date_compare import NAIVE_MIXED_WARNING


def _make_executor(nova=None) -> StepExecutor:
    return StepExecutor(nova or MagicMock())


def _make_nova(extracted_value: str) -> MagicMock:
    nova = MagicMock()
    response = MagicMock()
    response.parsed_response = extracted_value
    response.metadata = MagicMock(act_id="act-123")
    nova.act_get.return_value = response
    return nova


def _date_step(
    *,
    operator: str,
    validation_value: str,
    step_type: str = "assertion",
    assertion_variable: str = "captured_date",
    instruction: str = "Get the date",
) -> dict:
    return {
        "step_type": step_type,
        "validation_type": "date",
        "validation_operator": operator,
        "validation_value": validation_value,
        "assertion_variable": assertion_variable,
        "instruction": instruction,
    }


# ── _execute_assertion: variable-vs-value ───────────────────────────────


class TestAssertionPath:
    def test_before_succeeds(self):
        executor = _make_executor()
        step = _date_step(operator="before", validation_value="2024-01-05")
        result = executor._execute_assertion(step, {"captured_date": "2024-01-02"})
        assert result.success is True
        assert result.logs == ""
        assert result.actual_value == "2024-01-02"

    def test_after_succeeds(self):
        executor = _make_executor()
        step = _date_step(operator="after", validation_value="2024-01-02")
        result = executor._execute_assertion(step, {"captured_date": "2024-01-05"})
        assert result.success is True

    def test_equals_fails(self):
        executor = _make_executor()
        step = _date_step(operator="equals", validation_value="2024-01-05")
        result = executor._execute_assertion(step, {"captured_date": "2024-01-02"})
        assert result.success is False
        assert "does not equal" in result.logs

    def test_not_equals_succeeds(self):
        executor = _make_executor()
        step = _date_step(operator="not_equals", validation_value="2024-01-05")
        result = executor._execute_assertion(step, {"captured_date": "2024-01-02"})
        assert result.success is True

    def test_equals_within_inside_tolerance(self):
        payload = json.dumps(
            {"date": "2024-01-02T15:00:00+00:00", "tolerance": 5, "unit": "minutes"}
        )
        executor = _make_executor()
        step = _date_step(operator="equals_within", validation_value=payload)
        result = executor._execute_assertion(
            step, {"captured_date": "2024-01-02T15:03:00+00:00"}
        )
        assert result.success is True

    def test_equals_within_malformed_json_fails_step(self):
        executor = _make_executor()
        step = _date_step(operator="equals_within", validation_value="not-json")
        result = executor._execute_assertion(step, {"captured_date": "2024-01-02"})
        assert result.success is False
        assert "must be JSON" in result.logs
        assert result.logs.startswith("Date assertion error")

    def test_naive_aware_warning_in_logs(self):
        executor = _make_executor()
        step = _date_step(
            operator="equals", validation_value="2024-01-02T15:00:00+00:00"
        )
        result = executor._execute_assertion(
            step, {"captured_date": "2024-01-02T15:00:00"}  # naive
        )
        assert result.success is True
        assert NAIVE_MIXED_WARNING in result.logs

    def test_unknown_operator_fails(self):
        executor = _make_executor()
        step = _date_step(operator="between", validation_value="2024-01-02")
        result = executor._execute_assertion(step, {"captured_date": "2024-01-02"})
        assert result.success is False
        assert "Unknown date operator" in result.logs

    def test_ambiguous_value_fails(self):
        executor = _make_executor()
        step = _date_step(operator="equals", validation_value="2024-01-02")
        result = executor._execute_assertion(step, {"captured_date": "01/02/2024"})
        assert result.success is False
        assert "ambiguous" in result.logs

    def test_missing_variable_uses_existing_branch(self):
        executor = _make_executor()
        step = _date_step(operator="equals", validation_value="2024-01-02")
        result = executor._execute_assertion(step, {})
        assert result.success is False
        assert "not found" in result.logs
        assert result.actual_value == "VARIABLE_NOT_FOUND"


# ── _execute_validation: Nova-extraction-vs-value ───────────────────────


class TestValidationPath:
    def test_before_succeeds(self):
        nova = _make_nova("2024-01-02")
        executor = _make_executor(nova)
        step = _date_step(
            step_type="validation", operator="before", validation_value="2024-01-05",
        )
        result = executor._execute_validation(step)
        assert result.success is True
        assert result.actual_value == "2024-01-02"
        nova.act_get.assert_called_once()

    def test_uses_string_schema(self):
        from qa_studio_cli.runner.step_executor import STRING_SCHEMA
        nova = _make_nova("2024-01-02")
        executor = _make_executor(nova)
        step = _date_step(
            step_type="validation", operator="equals", validation_value="2024-01-02",
        )
        executor._execute_validation(step)
        _, kwargs = nova.act_get.call_args
        assert kwargs.get("schema") is STRING_SCHEMA

    def test_equals_within_inside_tolerance(self):
        payload = json.dumps(
            {"date": "2024-01-02T15:00:00+00:00", "tolerance": 5, "unit": "minutes"}
        )
        nova = _make_nova("2024-01-02T15:03:00+00:00")
        executor = _make_executor(nova)
        step = _date_step(
            step_type="validation", operator="equals_within", validation_value=payload,
        )
        result = executor._execute_validation(step)
        assert result.success is True

    def test_equals_within_outside_tolerance(self):
        payload = json.dumps(
            {"date": "2024-01-02T15:00:00+00:00", "tolerance": 5, "unit": "minutes"}
        )
        nova = _make_nova("2024-01-02T15:10:00+00:00")
        executor = _make_executor(nova)
        step = _date_step(
            step_type="validation", operator="equals_within", validation_value=payload,
        )
        result = executor._execute_validation(step)
        assert result.success is False
        assert "exceeds tolerance" in result.logs

    def test_naive_aware_warning_in_logs(self):
        nova = _make_nova("2024-01-02T15:00:00")  # naive
        executor = _make_executor(nova)
        step = _date_step(
            step_type="validation",
            operator="equals",
            validation_value="2024-01-02T15:00:00+00:00",
        )
        result = executor._execute_validation(step)
        assert result.success is True
        assert NAIVE_MIXED_WARNING in result.logs

    def test_unknown_operator_fails(self):
        nova = _make_nova("2024-01-02")
        executor = _make_executor(nova)
        step = _date_step(
            step_type="validation", operator="between", validation_value="2024-01-02",
        )
        result = executor._execute_validation(step)
        assert result.success is False
        assert "Unknown date operator" in result.logs

    def test_ambiguous_extracted_value_fails(self):
        nova = _make_nova("01/02/2024")
        executor = _make_executor(nova)
        step = _date_step(
            step_type="validation", operator="equals", validation_value="2024-01-02",
        )
        result = executor._execute_validation(step)
        assert result.success is False
        assert "ambiguous" in result.logs


# ── Existing branches still work (regression guard) ────────────────────


class TestExistingBranchesUnaffected:
    def test_string_assertion_still_works(self):
        executor = _make_executor()
        step = {
            "step_type": "assertion",
            "validation_type": "string",
            "validation_operator": "exact",
            "validation_value": "hello",
            "assertion_variable": "captured",
        }
        result = executor._execute_assertion(step, {"captured": "hello"})
        assert result.success is True

    def test_number_assertion_still_works(self):
        executor = _make_executor()
        step = {
            "step_type": "assertion",
            "validation_type": "number",
            "validation_operator": "greater_then",
            "validation_value": "5",
            "assertion_variable": "captured",
        }
        result = executor._execute_assertion(step, {"captured": "10"})
        assert result.success is True
