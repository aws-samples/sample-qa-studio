"""Tests for date transform operations, CLI mirror (Task 3)."""

import pytest
from pydantic import ValidationError

# Importing the package triggers registration.
import qa_studio_cli.runner.transform  # noqa: F401
from qa_studio_cli.runner.transform.base import TRANSFORM_OPERATIONS
from qa_studio_cli.runner.transform.date_parser import DateParseError


def _exec(name: str, args: dict):
    return TRANSFORM_OPERATIONS[name].validate_and_execute(args)


# ── parse_date ───────────────────────────────────────────────────────────


class TestParseDate:
    def test_iso_input_returns_canonical_iso(self):
        assert _exec("parse_date", {"value": "2024-01-02"}) == "2024-01-02T00:00:00+00:00"

    def test_iso_with_offset_normalized_to_utc(self):
        assert _exec("parse_date", {"value": "2024-01-02T15:00:00+02:00"}) == \
            "2024-01-02T13:00:00+00:00"

    def test_epoch_seconds_input(self):
        assert _exec("parse_date", {"value": "1704207845"}) == "2024-01-02T15:04:05+00:00"

    def test_explicit_format_eu(self):
        assert _exec("parse_date", {"value": "02/01/2024", "format": "%d/%m/%Y"}) == \
            "2024-01-02T00:00:00+00:00"

    def test_explicit_format_us(self):
        assert _exec("parse_date", {"value": "01/02/2024", "format": "%m/%d/%Y"}) == \
            "2024-01-02T00:00:00+00:00"

    def test_ambiguous_input_without_format_raises(self):
        with pytest.raises(DateParseError, match="ambiguous"):
            _exec("parse_date", {"value": "01/02/2024"})

    def test_format_mismatch_raises(self):
        with pytest.raises(DateParseError, match="does not match format"):
            _exec("parse_date", {"value": "abc", "format": "%Y-%m-%d"})

    def test_missing_value_raises(self):
        with pytest.raises(ValidationError):
            _exec("parse_date", {"format": "%Y-%m-%d"})


# ── format_date ──────────────────────────────────────────────────────────


class TestFormatDate:
    def test_format_to_eu_slash(self):
        assert _exec("format_date", {
            "iso_value": "2024-01-02T00:00:00+00:00",
            "format": "%d/%m/%Y",
        }) == "02/01/2024"

    def test_format_to_us_with_time(self):
        assert _exec("format_date", {
            "iso_value": "2024-01-02T15:30:00+00:00",
            "format": "%m/%d/%Y %I:%M %p",
        }) == "01/02/2024 03:30 PM"

    def test_format_to_long_month(self):
        assert _exec("format_date", {
            "iso_value": "2024-01-02",
            "format": "%B %d, %Y",
        }) == "January 02, 2024"

    def test_format_offset_input_renders_in_utc(self):
        assert _exec("format_date", {
            "iso_value": "2024-01-02T15:00:00+02:00",
            "format": "%H:%M",
        }) == "13:00"

    def test_non_canonical_input_rejected(self):
        with pytest.raises(DateParseError, match="ambiguous"):
            _exec("format_date", {"iso_value": "01/02/2024", "format": "%Y-%m-%d"})

    def test_missing_format_raises(self):
        with pytest.raises(ValidationError):
            _exec("format_date", {"iso_value": "2024-01-02"})


# ── add_duration ─────────────────────────────────────────────────────────


class TestAddDuration:
    def test_add_days(self):
        assert _exec("add_duration", {
            "iso_value": "2024-01-02", "amount": 3, "unit": "days",
        }) == "2024-01-05T00:00:00+00:00"

    def test_subtract_with_negative_amount(self):
        assert _exec("add_duration", {
            "iso_value": "2024-01-05", "amount": -3, "unit": "days",
        }) == "2024-01-02T00:00:00+00:00"

    def test_add_hours_crosses_day_boundary(self):
        assert _exec("add_duration", {
            "iso_value": "2024-01-02T22:00:00+00:00", "amount": 5, "unit": "hours",
        }) == "2024-01-03T03:00:00+00:00"

    def test_add_weeks(self):
        assert _exec("add_duration", {
            "iso_value": "2024-01-02", "amount": 2, "unit": "weeks",
        }) == "2024-01-16T00:00:00+00:00"

    def test_add_minutes(self):
        assert _exec("add_duration", {
            "iso_value": "2024-01-02T12:00:00+00:00", "amount": 90, "unit": "minutes",
        }) == "2024-01-02T13:30:00+00:00"

    def test_leap_day_boundary(self):
        assert _exec("add_duration", {
            "iso_value": "2024-02-28", "amount": 1, "unit": "days",
        }) == "2024-02-29T00:00:00+00:00"

    def test_zero_amount_is_identity(self):
        assert _exec("add_duration", {
            "iso_value": "2024-01-02T00:00:00+00:00", "amount": 0, "unit": "days",
        }) == "2024-01-02T00:00:00+00:00"

    def test_invalid_unit_raises(self):
        with pytest.raises(ValidationError):
            _exec("add_duration", {
                "iso_value": "2024-01-02", "amount": 1, "unit": "months",
            })

    def test_missing_amount_raises(self):
        with pytest.raises(ValidationError):
            _exec("add_duration", {"iso_value": "2024-01-02", "unit": "days"})


# ── date_diff ────────────────────────────────────────────────────────────


class TestDateDiff:
    def test_positive_diff_in_days(self):
        assert _exec("date_diff", {
            "a": "2024-01-05", "b": "2024-01-02", "unit": "days",
        }) == 3

    def test_negative_diff_when_a_before_b(self):
        assert _exec("date_diff", {
            "a": "2024-01-02", "b": "2024-01-05", "unit": "days",
        }) == -3

    def test_zero_diff_for_same_date(self):
        assert _exec("date_diff", {
            "a": "2024-01-02T00:00:00+00:00",
            "b": "2024-01-02T00:00:00+00:00",
            "unit": "seconds",
        }) == 0

    def test_truncates_toward_zero_positive(self):
        assert _exec("date_diff", {
            "a": "2024-01-03T12:00:00+00:00",
            "b": "2024-01-02T00:00:00+00:00",
            "unit": "days",
        }) == 1

    def test_truncates_toward_zero_negative(self):
        assert _exec("date_diff", {
            "a": "2024-01-02T00:00:00+00:00",
            "b": "2024-01-03T12:00:00+00:00",
            "unit": "days",
        }) == -1

    def test_diff_in_hours(self):
        assert _exec("date_diff", {
            "a": "2024-01-02T15:00:00+00:00",
            "b": "2024-01-02T10:00:00+00:00",
            "unit": "hours",
        }) == 5

    def test_diff_in_weeks(self):
        assert _exec("date_diff", {
            "a": "2024-01-15", "b": "2024-01-01", "unit": "weeks",
        }) == 2

    def test_diff_handles_offsets_correctly(self):
        # 15:00 +02:00 = 13:00 UTC; 13:00 UTC - 13:00 UTC = 0.
        assert _exec("date_diff", {
            "a": "2024-01-02T15:00:00+02:00",
            "b": "2024-01-02T13:00:00+00:00",
            "unit": "minutes",
        }) == 0

    def test_invalid_unit_raises(self):
        with pytest.raises(ValidationError):
            _exec("date_diff", {
                "a": "2024-01-02", "b": "2024-01-01", "unit": "months",
            })


# ── to_epoch ─────────────────────────────────────────────────────────────


class TestToEpoch:
    def test_default_unit_is_seconds(self):
        assert _exec("to_epoch", {"value": "2024-01-02T00:00:00+00:00"}) == 1704153600

    def test_seconds_explicit(self):
        assert _exec("to_epoch", {
            "value": "2024-01-02T00:00:00+00:00", "unit": "seconds",
        }) == 1704153600

    def test_millis(self):
        assert _exec("to_epoch", {
            "value": "2024-01-02T00:00:00+00:00", "unit": "millis",
        }) == 1704153600000

    def test_naive_input_anchored_to_utc(self):
        assert _exec("to_epoch", {"value": "2024-01-02T00:00:00"}) == 1704153600

    def test_offset_input_converted_to_utc(self):
        assert _exec("to_epoch", {"value": "2024-01-02T02:00:00+02:00"}) == 1704153600

    def test_round_trip_with_parse_date(self):
        epoch_in = 1704207845
        iso = _exec("parse_date", {"value": str(epoch_in)})
        assert _exec("to_epoch", {"value": iso}) == epoch_in

    def test_invalid_unit_raises(self):
        with pytest.raises(ValidationError):
            _exec("to_epoch", {"value": "2024-01-02", "unit": "minutes"})


# ── Composition with existing assertion path ────────────────────────────


class TestCompositionWithNumberAssertion:
    def test_two_dates_yield_comparable_epochs(self):
        epoch_earlier = _exec("to_epoch", {"value": "2024-01-02"})
        epoch_later = _exec("to_epoch", {"value": "2024-01-05"})
        assert epoch_later > epoch_earlier
