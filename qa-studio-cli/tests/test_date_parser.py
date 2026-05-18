"""Tests for the centralized date parser, CLI mirror (Task 3).

Adds hypothesis fuzzing on top of the worker-side parametrized tests,
since hypothesis is a dev dependency on the CLI side.
"""

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings, strategies as st

from qa_studio_cli.runner.transform.date_parser import DateParseError, parse_to_utc

UTC = timezone.utc


# ── Auto-detect: ISO 8601 ────────────────────────────────────────────────


class TestAutoDetectIso:
    def test_date_only(self):
        dt, naive = parse_to_utc("2024-01-02")
        assert dt == datetime(2024, 1, 2, tzinfo=UTC)
        assert naive is True

    def test_datetime_naive(self):
        dt, naive = parse_to_utc("2024-01-02T15:04:05")
        assert dt == datetime(2024, 1, 2, 15, 4, 5, tzinfo=UTC)
        assert naive is True

    def test_datetime_with_z_suffix(self):
        dt, naive = parse_to_utc("2024-01-02T15:04:05Z")
        assert dt == datetime(2024, 1, 2, 15, 4, 5, tzinfo=UTC)
        assert naive is False

    def test_datetime_with_positive_offset(self):
        dt, naive = parse_to_utc("2024-01-02T15:04:05+02:00")
        assert dt == datetime(2024, 1, 2, 13, 4, 5, tzinfo=UTC)
        assert naive is False

    def test_datetime_with_negative_offset(self):
        dt, naive = parse_to_utc("2024-01-02T10:00:00-05:00")
        assert dt == datetime(2024, 1, 2, 15, 0, 0, tzinfo=UTC)
        assert naive is False

    def test_datetime_with_microseconds(self):
        dt, naive = parse_to_utc("2024-01-02T15:04:05.123456+00:00")
        assert dt == datetime(2024, 1, 2, 15, 4, 5, 123456, tzinfo=UTC)
        assert naive is False

    def test_datetime_with_space_separator(self):
        dt, naive = parse_to_utc("2024-01-02 15:04:05")
        assert dt == datetime(2024, 1, 2, 15, 4, 5, tzinfo=UTC)
        assert naive is True


# ── Auto-detect: Unix epoch ──────────────────────────────────────────────


class TestAutoDetectEpoch:
    def test_epoch_seconds(self):
        dt, naive = parse_to_utc("1704207845")
        assert dt == datetime(2024, 1, 2, 15, 4, 5, tzinfo=UTC)
        assert naive is False

    def test_epoch_millis(self):
        dt, naive = parse_to_utc("1704207845123")
        assert dt == datetime(2024, 1, 2, 15, 4, 5, 123000, tzinfo=UTC)
        assert naive is False

    def test_epoch_seconds_min_boundary(self):
        dt, _ = parse_to_utc("1000000000")
        assert dt.year == 2001 and dt.month == 9

    def test_epoch_takes_precedence_over_iso_basic_format(self):
        # Regression: Python 3.11+ fromisoformat is lenient enough to parse
        # some 13-digit all-digit strings as ISO basic datetimes (e.g.
        # "8796093022200" → year 8796). Epoch detection must run first.
        dt, naive = parse_to_utc("8796093022200")
        assert dt == datetime.fromtimestamp(8796093022.200, tz=UTC)
        assert dt.year < 9000
        assert naive is False


# ── Ambiguous input must fail without a format ───────────────────────────


class TestAmbiguousFails:
    @pytest.mark.parametrize("value", [
        "01/02/2024",
        "02/01/2024",
        "January 2, 2024",
        "Jan 2 2024",
        "2 Jan 2024",
        "02-01-2024",
        "2024",
        "abc",
        "12345",
        "123456789",
        "12345678901",
        "12345678901234",
    ])
    def test_no_format_no_match_raises(self, value):
        with pytest.raises(DateParseError) as exc_info:
            parse_to_utc(value)
        assert value in str(exc_info.value)
        assert "ambiguous" in str(exc_info.value).lower()


# ── Empty / non-string input ─────────────────────────────────────────────


class TestInvalidInput:
    def test_empty_string(self):
        with pytest.raises(DateParseError, match="Empty"):
            parse_to_utc("")

    def test_whitespace_only(self):
        with pytest.raises(DateParseError, match="Empty"):
            parse_to_utc("   ")

    @pytest.mark.parametrize("value", [12345, None, 3.14, ["2024"]])
    def test_non_string_raises(self, value):
        with pytest.raises(DateParseError, match="Expected str"):
            parse_to_utc(value)  # type: ignore[arg-type]


# ── Explicit format path ─────────────────────────────────────────────────


class TestExplicitFormat:
    def test_eu_slash(self):
        dt, naive = parse_to_utc("02/01/2024", format="%d/%m/%Y")
        assert dt == datetime(2024, 1, 2, tzinfo=UTC)
        assert naive is True

    def test_us_slash(self):
        dt, naive = parse_to_utc("01/02/2024", format="%m/%d/%Y")
        assert dt == datetime(2024, 1, 2, tzinfo=UTC)
        assert naive is True

    def test_long_month(self):
        dt, naive = parse_to_utc("January 2, 2024", format="%B %d, %Y")
        assert dt == datetime(2024, 1, 2, tzinfo=UTC)
        assert naive is True

    def test_eu_dot(self):
        dt, naive = parse_to_utc("02.01.2024", format="%d.%m.%Y")
        assert dt == datetime(2024, 1, 2, tzinfo=UTC)
        assert naive is True

    def test_with_24h_time(self):
        dt, naive = parse_to_utc("02/01/2024 15:30", format="%d/%m/%Y %H:%M")
        assert dt == datetime(2024, 1, 2, 15, 30, tzinfo=UTC)
        assert naive is True

    def test_with_12h_time(self):
        dt, naive = parse_to_utc("01/02/2024 3:30 PM", format="%m/%d/%Y %I:%M %p")
        assert dt == datetime(2024, 1, 2, 15, 30, tzinfo=UTC)
        assert naive is True

    def test_with_offset_in_format(self):
        dt, naive = parse_to_utc("2024-01-02 15:30 +0200", format="%Y-%m-%d %H:%M %z")
        assert dt == datetime(2024, 1, 2, 13, 30, tzinfo=UTC)
        assert naive is False

    def test_format_mismatch_raises(self):
        with pytest.raises(DateParseError, match="does not match format"):
            parse_to_utc("not-a-date", format="%Y-%m-%d")

    def test_format_mismatch_includes_value_and_format(self):
        with pytest.raises(DateParseError) as exc_info:
            parse_to_utc("01/02/2024", format="%Y-%m-%d")
        assert "01/02/2024" in str(exc_info.value)
        assert "%Y-%m-%d" in str(exc_info.value)

    def test_leading_trailing_whitespace_stripped(self):
        dt, _ = parse_to_utc("  02/01/2024  ", format="%d/%m/%Y")
        assert dt == datetime(2024, 1, 2, tzinfo=UTC)


# ── Naive vs aware flag ──────────────────────────────────────────────────


class TestNaiveFlag:
    @pytest.mark.parametrize("value,expected_naive", [
        ("2024-01-02", True),
        ("2024-01-02T15:04:05", True),
        ("2024-01-02T15:04:05Z", False),
        ("2024-01-02T15:04:05+00:00", False),
        ("2024-01-02T15:04:05-05:00", False),
        ("1704207845", False),
        ("1704207845123", False),
    ])
    def test_naive_flag(self, value, expected_naive):
        _, naive = parse_to_utc(value)
        assert naive is expected_naive


# ── Timezone normalization ───────────────────────────────────────────────


class TestTimezoneNormalization:
    def test_aware_input_converted_to_utc(self):
        dt, _ = parse_to_utc("2024-01-02T15:00:00+02:00")
        assert dt.hour == 13
        assert dt.tzinfo == UTC

    def test_naive_input_anchored_to_utc(self):
        dt, naive = parse_to_utc("2024-01-02T15:00:00")
        assert dt.tzinfo == UTC
        assert naive is True

    def test_strptime_aware_converted_to_utc(self):
        dt, naive = parse_to_utc("02/01/2024 15:00 -0500", format="%d/%m/%Y %H:%M %z")
        assert dt.hour == 20
        assert dt.tzinfo == UTC
        assert naive is False


# ── Property-based fuzzing ───────────────────────────────────────────────


class TestPropertyBased:
    """Round-trip and invariant properties that must hold for all inputs."""

    @given(st.datetimes(
        min_value=datetime(1970, 1, 2),  # avoid pre-epoch edge cases
        max_value=datetime(2100, 1, 1),
        timezones=st.just(UTC),
    ))
    @settings(max_examples=200, deadline=None)
    def test_iso_round_trip_aware(self, dt):
        """An aware UTC datetime → ISO → parse should return the same datetime."""
        parsed, naive = parse_to_utc(dt.isoformat())
        assert parsed == dt
        assert naive is False

    @given(st.datetimes(
        min_value=datetime(1970, 1, 2),
        max_value=datetime(2100, 1, 1),
    ))
    @settings(max_examples=200, deadline=None)
    def test_iso_round_trip_naive(self, dt):
        """A naive datetime → ISO → parse should return the UTC-anchored value."""
        parsed, naive = parse_to_utc(dt.isoformat())
        assert parsed == dt.replace(tzinfo=UTC)
        assert naive is True

    @given(st.integers(min_value=1_000_000_000, max_value=9_999_999_999))
    @settings(max_examples=200, deadline=None)
    def test_epoch_seconds_round_trip(self, epoch):
        """A 10-digit epoch second value parses back to the same instant."""
        parsed, naive = parse_to_utc(str(epoch))
        assert parsed == datetime.fromtimestamp(epoch, tz=UTC)
        assert naive is False

    @given(st.integers(min_value=1_000_000_000_000, max_value=9_999_999_999_999))
    @settings(max_examples=200, deadline=None)
    def test_epoch_millis_round_trip(self, epoch_ms):
        """A 13-digit epoch millisecond value parses back to the expected instant."""
        parsed, naive = parse_to_utc(str(epoch_ms))
        expected = datetime.fromtimestamp(epoch_ms / 1000, tz=UTC)
        # Compare with millisecond tolerance (datetime.fromtimestamp loses
        # sub-microsecond precision around float boundaries).
        assert abs((parsed - expected).total_seconds()) < 0.001
        assert naive is False

    @given(st.text(min_size=1, max_size=20).filter(
        lambda s: not s.strip().isdigit() and "-" not in s and "T" not in s
    ))
    @settings(max_examples=100, deadline=None)
    def test_random_garbage_raises(self, value):
        """Strings that aren't ISO, epoch, or empty raise DateParseError."""
        # Either DateParseError (bad format) or empty-string variant.
        with pytest.raises(DateParseError):
            parse_to_utc(value)
