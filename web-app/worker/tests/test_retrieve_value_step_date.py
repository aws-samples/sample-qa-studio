"""Tests for the retrieve_value step's value_type=date branch."""

from unittest.mock import MagicMock

import pytest

from models import ExecutionStep
from retrieve_value_step import execute_retrieve_value_step


def _make_step(
    *,
    value_type: str = "date",
    value_format: str | None = None,
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
        step_type="retrieve_value",
        validation_type="",
        validation_operator="",
        validation_value="",
        capture_variable="captured_date",
        value_type=value_type,
        assertion_variable="",
        value_format=value_format,
    )


def _make_nova(extracted_value) -> MagicMock:
    """Mock NovaAct whose act_get returns the given parsed_response."""
    nova = MagicMock()
    response = MagicMock()
    response.parsed_response = extracted_value
    response.metadata = MagicMock()
    response.metadata.act_id = "act-123"
    nova.act_get.return_value = response
    return nova


# ── value_type=date with auto-detect (ISO/epoch) ────────────────────────


class TestDateAutoDetect:
    def test_iso_date_auto_canonicalized(self):
        nova = _make_nova("2024-01-02")
        step = _make_step()  # no value_format
        _, success, logs, retrieved = execute_retrieve_value_step(nova, step)
        assert success is True
        assert retrieved == "2024-01-02T00:00:00+00:00"
        assert logs == ""

    def test_iso_datetime_with_offset_normalized_to_utc(self):
        nova = _make_nova("2024-01-02T15:00:00+02:00")
        step = _make_step()
        _, success, _, retrieved = execute_retrieve_value_step(nova, step)
        assert success is True
        # 15:00 +02:00 = 13:00 UTC
        assert retrieved == "2024-01-02T13:00:00+00:00"

    def test_epoch_seconds_auto_canonicalized(self):
        nova = _make_nova("1704207845")
        step = _make_step()
        _, success, _, retrieved = execute_retrieve_value_step(nova, step)
        assert success is True
        assert retrieved == "2024-01-02T15:04:05+00:00"


# ── value_type=date with explicit format ────────────────────────────────


class TestDateWithFormat:
    def test_eu_slash_canonicalized_to_utc_iso(self):
        nova = _make_nova("02/01/2024")
        step = _make_step(value_format="%d/%m/%Y")
        _, success, _, retrieved = execute_retrieve_value_step(nova, step)
        assert success is True
        assert retrieved == "2024-01-02T00:00:00+00:00"

    def test_us_long_month_canonicalized(self):
        nova = _make_nova("January 2, 2024")
        step = _make_step(value_format="%B %d, %Y")
        _, success, _, retrieved = execute_retrieve_value_step(nova, step)
        assert success is True
        assert retrieved == "2024-01-02T00:00:00+00:00"

    def test_format_strips_surrounding_quotes(self):
        # AI sometimes returns quoted strings; the parser handles that.
        nova = _make_nova('"02/01/2024"')
        step = _make_step(value_format="%d/%m/%Y")
        _, success, _, retrieved = execute_retrieve_value_step(nova, step)
        assert success is True
        assert retrieved == "2024-01-02T00:00:00+00:00"


# ── Failure paths ───────────────────────────────────────────────────────


class TestDateFailures:
    def test_ambiguous_input_without_format_fails(self):
        nova = _make_nova("01/02/2024")  # ambiguous (US or EU?)
        step = _make_step()  # no format
        _, success, logs, retrieved = execute_retrieve_value_step(nova, step)
        assert success is False
        assert "Date parse failed" in logs
        assert "ambiguous" in logs
        # Retrieved value falls back to the cleaned raw string for visibility.
        assert retrieved == "01/02/2024"

    def test_format_mismatch_fails(self):
        nova = _make_nova("not-a-date")
        step = _make_step(value_format="%Y-%m-%d")
        _, success, logs, _ = execute_retrieve_value_step(nova, step)
        assert success is False
        assert "Date parse failed" in logs

    def test_none_extracted_value_fails(self):
        nova = MagicMock()
        response = MagicMock()
        response.parsed_response = None
        response.metadata = MagicMock(act_id="act-123")
        nova.act_get.return_value = response

        step = _make_step()
        _, success, logs, _ = execute_retrieve_value_step(nova, step)
        assert success is False
        assert "No value retrieved" in logs


# ── Existing branches still work (regression guard) ────────────────────


class TestExistingBranchesUnaffected:
    def test_string_retrieve_still_works(self):
        nova = _make_nova("hello")
        step = _make_step(value_type="string")
        _, success, _, retrieved = execute_retrieve_value_step(nova, step)
        assert success is True
        assert retrieved == "hello"

    def test_number_retrieve_still_works(self):
        nova = _make_nova(42)
        step = _make_step(value_type="number")
        _, success, _, retrieved = execute_retrieve_value_step(nova, step)
        assert success is True
        assert retrieved == "42"

    def test_bool_retrieve_still_works(self):
        nova = _make_nova(True)
        step = _make_step(value_type="bool")
        _, success, _, retrieved = execute_retrieve_value_step(nova, step)
        assert success is True
        assert retrieved == "True"


# ── Schema choice ────────────────────────────────────────────────────────


class TestSchemaChoice:
    def test_date_uses_string_schema(self):
        from utils import STRING_SCHEMA
        nova = _make_nova("2024-01-02")
        step = _make_step()
        execute_retrieve_value_step(nova, step)
        _, kwargs = nova.act_get.call_args
        assert kwargs.get("schema") is STRING_SCHEMA
