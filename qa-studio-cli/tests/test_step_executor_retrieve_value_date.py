"""Tests for the value_type=date branch in StepExecutor._execute_retrieve_value."""

from unittest.mock import MagicMock

import pytest

from qa_studio_cli.runner.step_executor import StepExecutor


def _make_executor(nova=None) -> StepExecutor:
    return StepExecutor(nova or MagicMock())


def _make_nova(extracted_value) -> MagicMock:
    nova = MagicMock()
    response = MagicMock()
    response.parsed_response = extracted_value
    response.metadata = MagicMock(act_id="act-123")
    nova.act_get.return_value = response
    return nova


def _retrieve_step(
    *,
    value_type: str = "date",
    value_format: str | None = None,
    instruction: str = "Get the date",
) -> dict:
    step: dict = {
        "step_type": "retrieve_value",
        "instruction": instruction,
        "capture_variable": "captured_date",
        "value_type": value_type,
        "value_source": "screen",
    }
    if value_format is not None:
        step["value_format"] = value_format
    return step


# ── Auto-detect (no format) ──────────────────────────────────────────────


class TestDateAutoDetect:
    def test_iso_date_canonicalized(self):
        nova = _make_nova("2024-01-02")
        executor = _make_executor(nova)
        result = executor._execute_retrieve_value(_retrieve_step())
        assert result.success is True
        assert result.actual_value == "2024-01-02T00:00:00+00:00"

    def test_iso_with_offset_normalized_to_utc(self):
        nova = _make_nova("2024-01-02T15:00:00+02:00")
        executor = _make_executor(nova)
        result = executor._execute_retrieve_value(_retrieve_step())
        assert result.success is True
        assert result.actual_value == "2024-01-02T13:00:00+00:00"

    def test_epoch_seconds_canonicalized(self):
        nova = _make_nova("1704207845")
        executor = _make_executor(nova)
        result = executor._execute_retrieve_value(_retrieve_step())
        assert result.success is True
        assert result.actual_value == "2024-01-02T15:04:05+00:00"


# ── Explicit format ──────────────────────────────────────────────────────


class TestDateWithFormat:
    def test_eu_slash(self):
        nova = _make_nova("02/01/2024")
        executor = _make_executor(nova)
        result = executor._execute_retrieve_value(
            _retrieve_step(value_format="%d/%m/%Y"),
        )
        assert result.success is True
        assert result.actual_value == "2024-01-02T00:00:00+00:00"

    def test_us_long_month(self):
        nova = _make_nova("January 2, 2024")
        executor = _make_executor(nova)
        result = executor._execute_retrieve_value(
            _retrieve_step(value_format="%B %d, %Y"),
        )
        assert result.success is True
        assert result.actual_value == "2024-01-02T00:00:00+00:00"

    def test_strips_quoted_output(self):
        # Sometimes the AI returns the value in quotes; the parser handles that.
        nova = _make_nova('"02/01/2024"')
        executor = _make_executor(nova)
        result = executor._execute_retrieve_value(
            _retrieve_step(value_format="%d/%m/%Y"),
        )
        assert result.success is True
        assert result.actual_value == "2024-01-02T00:00:00+00:00"


# ── Failure paths ────────────────────────────────────────────────────────


class TestDateFailures:
    def test_ambiguous_input_without_format_fails(self):
        nova = _make_nova("01/02/2024")
        executor = _make_executor(nova)
        result = executor._execute_retrieve_value(_retrieve_step())
        assert result.success is False
        assert "Date parse failed" in result.logs
        assert "ambiguous" in result.logs
        assert result.actual_value == "01/02/2024"

    def test_format_mismatch_fails(self):
        nova = _make_nova("not-a-date")
        executor = _make_executor(nova)
        result = executor._execute_retrieve_value(
            _retrieve_step(value_format="%Y-%m-%d"),
        )
        assert result.success is False
        assert "Date parse failed" in result.logs

    def test_none_extraction_fails(self):
        nova = MagicMock()
        response = MagicMock()
        response.parsed_response = None
        response.metadata = MagicMock(act_id="act-123")
        nova.act_get.return_value = response

        executor = _make_executor(nova)
        result = executor._execute_retrieve_value(_retrieve_step())
        assert result.success is False
        assert "No value retrieved" in result.logs


# ── Schema choice ────────────────────────────────────────────────────────


class TestSchemaChoice:
    def test_date_uses_string_schema(self):
        from qa_studio_cli.runner.step_executor import STRING_SCHEMA
        nova = _make_nova("2024-01-02")
        executor = _make_executor(nova)
        executor._execute_retrieve_value(_retrieve_step())
        _, kwargs = nova.act_get.call_args
        assert kwargs.get("schema") is STRING_SCHEMA


# ── Existing branches still work (regression guard) ────────────────────


class TestExistingBranchesUnaffected:
    def test_string_retrieve_still_works(self):
        nova = _make_nova("hello")
        executor = _make_executor(nova)
        result = executor._execute_retrieve_value(_retrieve_step(value_type="string"))
        assert result.success is True
        assert result.actual_value == "hello"

    def test_number_retrieve_still_works(self):
        nova = _make_nova(42)
        executor = _make_executor(nova)
        result = executor._execute_retrieve_value(_retrieve_step(value_type="number"))
        assert result.success is True
        assert result.actual_value == "42"
