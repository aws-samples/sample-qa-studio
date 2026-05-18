"""Tests for the date assertion helper (Task 4)."""

import json

import pytest

from transform.date_compare import (
    DATE_OPERATORS,
    EqualsWithinPayload,
    NAIVE_MIXED_WARNING,
    evaluate_date_assertion,
)
from transform.date_parser import DateParseError


# ── DATE_OPERATORS contract ──────────────────────────────────────────────


def test_supported_operators_locked_in():
    """Frozen contract: any change to this set is intentional and tested."""
    assert DATE_OPERATORS == {
        "before", "after", "equals", "not_equals", "equals_within",
    }


# ── before / after / equals / not_equals ────────────────────────────────


class TestBefore:
    def test_actual_before_expected_succeeds(self):
        success, logs = evaluate_date_assertion("2024-01-02", "2024-01-05", "before")
        assert success is True
        assert logs == ""

    def test_actual_after_expected_fails(self):
        success, logs = evaluate_date_assertion("2024-01-05", "2024-01-02", "before")
        assert success is False
        assert "is not before" in logs
        assert "2024-01-05" in logs and "2024-01-02" in logs

    def test_equal_dates_fails(self):
        success, _ = evaluate_date_assertion("2024-01-02", "2024-01-02", "before")
        assert success is False


class TestAfter:
    def test_actual_after_expected_succeeds(self):
        success, _ = evaluate_date_assertion("2024-01-05", "2024-01-02", "after")
        assert success is True

    def test_actual_before_expected_fails(self):
        success, logs = evaluate_date_assertion("2024-01-02", "2024-01-05", "after")
        assert success is False
        assert "is not after" in logs

    def test_equal_dates_fails(self):
        success, _ = evaluate_date_assertion("2024-01-02", "2024-01-02", "after")
        assert success is False


class TestEquals:
    def test_equal_dates_succeeds(self):
        success, _ = evaluate_date_assertion("2024-01-02", "2024-01-02", "equals")
        assert success is True

    def test_different_dates_fails(self):
        success, logs = evaluate_date_assertion("2024-01-02", "2024-01-05", "equals")
        assert success is False
        assert "does not equal" in logs

    def test_same_instant_different_offsets_succeeds(self):
        # 15:00 +02:00 = 13:00 +00:00
        success, _ = evaluate_date_assertion(
            "2024-01-02T15:00:00+02:00", "2024-01-02T13:00:00+00:00", "equals"
        )
        assert success is True


class TestNotEquals:
    def test_different_dates_succeeds(self):
        success, _ = evaluate_date_assertion("2024-01-02", "2024-01-05", "not_equals")
        assert success is True

    def test_equal_dates_fails(self):
        success, logs = evaluate_date_assertion("2024-01-02", "2024-01-02", "not_equals")
        assert success is False
        assert "expected inequality" in logs


# ── equals_within ────────────────────────────────────────────────────────


def _payload(date: str, tolerance: int, unit: str) -> str:
    return json.dumps({"date": date, "tolerance": tolerance, "unit": unit})


class TestEqualsWithin:
    def test_within_tolerance_succeeds(self):
        success, logs = evaluate_date_assertion(
            "2024-01-02T15:03:00+00:00",
            _payload("2024-01-02T15:00:00+00:00", 5, "minutes"),
            "equals_within",
        )
        assert success is True
        assert logs == ""

    def test_at_exact_tolerance_boundary_succeeds(self):
        # Exactly 5 minutes — operator is <= so this should pass.
        success, _ = evaluate_date_assertion(
            "2024-01-02T15:05:00+00:00",
            _payload("2024-01-02T15:00:00+00:00", 5, "minutes"),
            "equals_within",
        )
        assert success is True

    def test_outside_tolerance_fails(self):
        success, logs = evaluate_date_assertion(
            "2024-01-02T15:10:00+00:00",
            _payload("2024-01-02T15:00:00+00:00", 5, "minutes"),
            "equals_within",
        )
        assert success is False
        assert "exceeds tolerance" in logs

    def test_zero_tolerance_behaves_like_equals(self):
        ok, _ = evaluate_date_assertion(
            "2024-01-02T15:00:00+00:00",
            _payload("2024-01-02T15:00:00+00:00", 0, "seconds"),
            "equals_within",
        )
        assert ok is True
        ok, _ = evaluate_date_assertion(
            "2024-01-02T15:00:01+00:00",
            _payload("2024-01-02T15:00:00+00:00", 0, "seconds"),
            "equals_within",
        )
        assert ok is False

    def test_tolerance_in_days(self):
        success, _ = evaluate_date_assertion(
            "2024-01-04",
            _payload("2024-01-02", 3, "days"),
            "equals_within",
        )
        assert success is True

    def test_negative_diff_within_tolerance_succeeds(self):
        # actual is BEFORE expected — abs() means symmetric tolerance.
        success, _ = evaluate_date_assertion(
            "2024-01-02T14:57:00+00:00",
            _payload("2024-01-02T15:00:00+00:00", 5, "minutes"),
            "equals_within",
        )
        assert success is True


# ── equals_within payload validation ─────────────────────────────────────


class TestEqualsWithinPayloadErrors:
    def test_malformed_json_raises_value_error(self):
        with pytest.raises(ValueError, match="must be JSON"):
            evaluate_date_assertion(
                "2024-01-02", "not-json{{{", "equals_within"
            )

    def test_missing_date_field_raises(self):
        with pytest.raises(ValueError, match="invalid shape"):
            evaluate_date_assertion(
                "2024-01-02",
                json.dumps({"tolerance": 5, "unit": "minutes"}),
                "equals_within",
            )

    def test_missing_tolerance_field_raises(self):
        with pytest.raises(ValueError, match="invalid shape"):
            evaluate_date_assertion(
                "2024-01-02",
                json.dumps({"date": "2024-01-02", "unit": "minutes"}),
                "equals_within",
            )

    def test_missing_unit_field_raises(self):
        with pytest.raises(ValueError, match="invalid shape"):
            evaluate_date_assertion(
                "2024-01-02",
                json.dumps({"date": "2024-01-02", "tolerance": 5}),
                "equals_within",
            )

    def test_negative_tolerance_raises(self):
        with pytest.raises(ValueError, match="invalid shape"):
            evaluate_date_assertion(
                "2024-01-02",
                _payload("2024-01-02", -1, "minutes"),
                "equals_within",
            )

    def test_unsupported_unit_raises(self):
        with pytest.raises(ValueError, match="invalid shape"):
            evaluate_date_assertion(
                "2024-01-02",
                _payload("2024-01-02", 1, "months"),
                "equals_within",
            )

    def test_json_array_at_top_level_raises(self):
        with pytest.raises(ValueError, match="must be an object"):
            evaluate_date_assertion(
                "2024-01-02",
                json.dumps(["2024-01-02", 5, "minutes"]),
                "equals_within",
            )


# ── Naive-vs-aware warning ───────────────────────────────────────────────


class TestNaiveAwareWarning:
    def test_naive_actual_aware_expected_warns(self):
        success, logs = evaluate_date_assertion(
            "2024-01-02T15:00:00",                # naive
            "2024-01-02T15:00:00+00:00",          # aware
            "equals",
        )
        assert success is True
        assert NAIVE_MIXED_WARNING in logs

    def test_aware_actual_naive_expected_warns(self):
        success, logs = evaluate_date_assertion(
            "2024-01-02T15:00:00+00:00",
            "2024-01-02T15:00:00",
            "equals",
        )
        assert success is True
        assert NAIVE_MIXED_WARNING in logs

    def test_both_naive_no_warning(self):
        success, logs = evaluate_date_assertion(
            "2024-01-02T15:00:00", "2024-01-02T15:00:00", "equals",
        )
        assert success is True
        assert logs == ""

    def test_both_aware_no_warning(self):
        success, logs = evaluate_date_assertion(
            "2024-01-02T15:00:00+00:00", "2024-01-02T15:00:00+00:00", "equals",
        )
        assert success is True
        assert logs == ""

    def test_warning_present_alongside_failure(self):
        success, logs = evaluate_date_assertion(
            "2024-01-02T15:00:00",
            "2024-01-05T15:00:00+00:00",
            "equals",
        )
        assert success is False
        assert NAIVE_MIXED_WARNING in logs
        assert "does not equal" in logs

    def test_warning_in_equals_within_when_mixed(self):
        success, logs = evaluate_date_assertion(
            "2024-01-02T15:03:00",  # naive
            _payload("2024-01-02T15:00:00+00:00", 5, "minutes"),
            "equals_within",
        )
        assert success is True
        assert NAIVE_MIXED_WARNING in logs


# ── Operator and parse error surface ─────────────────────────────────────


class TestErrorSurface:
    def test_unknown_operator_raises(self):
        with pytest.raises(ValueError, match="Unknown date operator"):
            evaluate_date_assertion("2024-01-02", "2024-01-02", "between")

    def test_ambiguous_actual_raises_parse_error(self):
        with pytest.raises(DateParseError, match="ambiguous"):
            evaluate_date_assertion("01/02/2024", "2024-01-02", "equals")

    def test_ambiguous_expected_raises_parse_error(self):
        with pytest.raises(DateParseError, match="ambiguous"):
            evaluate_date_assertion("2024-01-02", "01/02/2024", "equals")
