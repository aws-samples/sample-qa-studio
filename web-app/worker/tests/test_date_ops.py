"""Tests for date transform operations (Task 2)."""

import pytest
from pydantic import ValidationError

# Importing the package triggers registration of all operations.
import transform  # noqa: F401
from transform.base import TRANSFORM_OPERATIONS
from transform.date_parser import DateParseError


def _exec(name: str, args: dict):
    """Shorthand: validate_and_execute for a named operation."""
    return TRANSFORM_OPERATIONS[name].validate_and_execute(args)


# ── parse_date ───────────────────────────────────────────────────────────


class TestParseDate:
    def test_iso_input_returns_canonical_iso(self):
        assert _exec("parse_date", {"value": "2024-01-02"}) == "2024-01-02T00:00:00+00:00"

    def test_iso_with_offset_normalized_to_utc(self):
        result = _exec("parse_date", {"value": "2024-01-02T15:00:00+02:00"})
        assert result == "2024-01-02T13:00:00+00:00"

    def test_epoch_seconds_input(self):
        # 1704207845 = 2024-01-02 15:04:05 UTC
        assert _exec("parse_date", {"value": "1704207845"}) == "2024-01-02T15:04:05+00:00"

    def test_explicit_format_eu(self):
        result = _exec("parse_date", {"value": "02/01/2024", "format": "%d/%m/%Y"})
        assert result == "2024-01-02T00:00:00+00:00"

    def test_explicit_format_us(self):
        result = _exec("parse_date", {"value": "01/02/2024", "format": "%m/%d/%Y"})
        assert result == "2024-01-02T00:00:00+00:00"

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
        result = _exec("format_date", {
            "iso_value": "2024-01-02T00:00:00+00:00",
            "format": "%d/%m/%Y",
        })
        assert result == "02/01/2024"

    def test_format_to_us_with_time(self):
        result = _exec("format_date", {
            "iso_value": "2024-01-02T15:30:00+00:00",
            "format": "%m/%d/%Y %I:%M %p",
        })
        assert result == "01/02/2024 03:30 PM"

    def test_format_to_long_month(self):
        result = _exec("format_date", {
            "iso_value": "2024-01-02",
            "format": "%B %d, %Y",
        })
        assert result == "January 02, 2024"

    def test_format_offset_input_renders_in_utc(self):
        # Input is 15:00 +02:00 → 13:00 UTC; strftime works on the UTC datetime.
        result = _exec("format_date", {
            "iso_value": "2024-01-02T15:00:00+02:00",
            "format": "%H:%M",
        })
        assert result == "13:00"

    def test_non_canonical_input_rejected(self):
        # format_date does not accept regional inputs — caller must parse_date first.
        with pytest.raises(DateParseError, match="ambiguous"):
            _exec("format_date", {"iso_value": "01/02/2024", "format": "%Y-%m-%d"})

    def test_missing_format_raises(self):
        with pytest.raises(ValidationError):
            _exec("format_date", {"iso_value": "2024-01-02"})


# ── add_duration ─────────────────────────────────────────────────────────


class TestAddDuration:
    def test_add_days(self):
        result = _exec("add_duration", {
            "iso_value": "2024-01-02",
            "amount": 3,
            "unit": "days",
        })
        assert result == "2024-01-05T00:00:00+00:00"

    def test_subtract_with_negative_amount(self):
        result = _exec("add_duration", {
            "iso_value": "2024-01-05",
            "amount": -3,
            "unit": "days",
        })
        assert result == "2024-01-02T00:00:00+00:00"

    def test_add_hours_crosses_day_boundary(self):
        result = _exec("add_duration", {
            "iso_value": "2024-01-02T22:00:00+00:00",
            "amount": 5,
            "unit": "hours",
        })
        assert result == "2024-01-03T03:00:00+00:00"

    def test_add_weeks(self):
        result = _exec("add_duration", {
            "iso_value": "2024-01-02",
            "amount": 2,
            "unit": "weeks",
        })
        assert result == "2024-01-16T00:00:00+00:00"

    def test_add_minutes_and_seconds(self):
        result = _exec("add_duration", {
            "iso_value": "2024-01-02T12:00:00+00:00",
            "amount": 90,
            "unit": "minutes",
        })
        assert result == "2024-01-02T13:30:00+00:00"

    def test_leap_day_boundary(self):
        # 2024 is a leap year; Feb 28 + 1 day = Feb 29.
        result = _exec("add_duration", {
            "iso_value": "2024-02-28",
            "amount": 1,
            "unit": "days",
        })
        assert result == "2024-02-29T00:00:00+00:00"

    def test_zero_amount_is_identity(self):
        result = _exec("add_duration", {
            "iso_value": "2024-01-02T00:00:00+00:00",
            "amount": 0,
            "unit": "days",
        })
        assert result == "2024-01-02T00:00:00+00:00"

    def test_invalid_unit_raises(self):
        with pytest.raises(ValidationError):
            _exec("add_duration", {
                "iso_value": "2024-01-02",
                "amount": 1,
                "unit": "months",  # months explicitly excluded in v1
            })

    def test_missing_amount_raises(self):
        with pytest.raises(ValidationError):
            _exec("add_duration", {"iso_value": "2024-01-02", "unit": "days"})


# ── date_diff ────────────────────────────────────────────────────────────


class TestDateDiff:
    def test_positive_diff_in_days(self):
        result = _exec("date_diff", {
            "a": "2024-01-05",
            "b": "2024-01-02",
            "unit": "days",
        })
        assert result == 3

    def test_negative_diff_when_a_before_b(self):
        result = _exec("date_diff", {
            "a": "2024-01-02",
            "b": "2024-01-05",
            "unit": "days",
        })
        assert result == -3

    def test_zero_diff_for_same_date(self):
        result = _exec("date_diff", {
            "a": "2024-01-02T00:00:00+00:00",
            "b": "2024-01-02T00:00:00+00:00",
            "unit": "seconds",
        })
        assert result == 0

    def test_truncates_toward_zero_positive(self):
        # 36 hours = 1 full day + 12 hours; in days that's 1, not 2.
        result = _exec("date_diff", {
            "a": "2024-01-03T12:00:00+00:00",
            "b": "2024-01-02T00:00:00+00:00",
            "unit": "days",
        })
        assert result == 1

    def test_truncates_toward_zero_negative(self):
        # -36 hours / 24 = -1.5; truncates toward zero → -1.
        result = _exec("date_diff", {
            "a": "2024-01-02T00:00:00+00:00",
            "b": "2024-01-03T12:00:00+00:00",
            "unit": "days",
        })
        assert result == -1

    def test_diff_in_hours(self):
        result = _exec("date_diff", {
            "a": "2024-01-02T15:00:00+00:00",
            "b": "2024-01-02T10:00:00+00:00",
            "unit": "hours",
        })
        assert result == 5

    def test_diff_in_weeks(self):
        result = _exec("date_diff", {
            "a": "2024-01-15",
            "b": "2024-01-01",
            "unit": "weeks",
        })
        assert result == 2

    def test_diff_handles_offsets_correctly(self):
        # 15:00 +02:00 = 13:00 UTC; 13:00 UTC - 13:00 UTC = 0.
        result = _exec("date_diff", {
            "a": "2024-01-02T15:00:00+02:00",
            "b": "2024-01-02T13:00:00+00:00",
            "unit": "minutes",
        })
        assert result == 0

    def test_invalid_unit_raises(self):
        with pytest.raises(ValidationError):
            _exec("date_diff", {
                "a": "2024-01-02",
                "b": "2024-01-01",
                "unit": "months",
            })


# ── to_epoch ─────────────────────────────────────────────────────────────


class TestToEpoch:
    def test_default_unit_is_seconds(self):
        # 2024-01-02T00:00:00 UTC = 1704153600
        assert _exec("to_epoch", {"value": "2024-01-02T00:00:00+00:00"}) == 1704153600

    def test_seconds_explicit(self):
        result = _exec("to_epoch", {
            "value": "2024-01-02T00:00:00+00:00",
            "unit": "seconds",
        })
        assert result == 1704153600

    def test_millis(self):
        result = _exec("to_epoch", {
            "value": "2024-01-02T00:00:00+00:00",
            "unit": "millis",
        })
        assert result == 1704153600000

    def test_naive_input_anchored_to_utc(self):
        # Naive 2024-01-02T00:00:00 → treated as UTC anchor.
        result = _exec("to_epoch", {"value": "2024-01-02T00:00:00"})
        assert result == 1704153600

    def test_offset_input_converted_to_utc(self):
        # 02:00 +02:00 = 00:00 UTC.
        result = _exec("to_epoch", {"value": "2024-01-02T02:00:00+02:00"})
        assert result == 1704153600

    def test_round_trip_with_parse_date(self):
        # parse_date → to_epoch should be lossless at second granularity.
        epoch_in = 1704207845
        iso = _exec("parse_date", {"value": str(epoch_in)})
        epoch_out = _exec("to_epoch", {"value": iso})
        assert epoch_out == epoch_in

    def test_invalid_unit_raises(self):
        with pytest.raises(ValidationError):
            _exec("to_epoch", {"value": "2024-01-02", "unit": "minutes"})


# ── Composition with existing assertion path ────────────────────────────


class TestCompositionWithNumberAssertion:
    """End-to-end-ish: to_epoch + existing number comparator pattern.

    This is the path the spec recommends for "is A older than B" — convert
    both to epoch via to_epoch, then compare with the existing number
    operators in assertion_step. We can't run the assertion step here
    (different module), but we can prove the values come out comparable.
    """

    def test_two_dates_yield_comparable_epochs(self):
        epoch_earlier = _exec("to_epoch", {"value": "2024-01-02"})
        epoch_later = _exec("to_epoch", {"value": "2024-01-05"})
        assert epoch_later > epoch_earlier
