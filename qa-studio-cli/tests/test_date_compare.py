"""Tests for the date assertion helper, CLI mirror (Task 6)."""

import json

import pytest

from qa_studio_cli.runner.transform.date_compare import (
    DATE_OPERATORS,
    EqualsWithinPayload,
    NAIVE_MIXED_WARNING,
    evaluate_date_assertion,
)
from qa_studio_cli.runner.transform.date_parser import DateParseError


def test_supported_operators_locked_in():
    assert DATE_OPERATORS == {
        "before", "after", "equals", "not_equals", "equals_within",
    }


# ── before / after / equals / not_equals ────────────────────────────────


class TestBefore:
    def test_actual_before_expected_succeeds(self):
        success, logs = evaluate_date_assertion("2024-01-02", "2024-01-05", "before")
        assert success is True and logs == ""

    def test_actual_after_expected_fails(self):
        success, logs = evaluate_date_assertion("2024-01-05", "2024-01-02", "before")
        assert success is False
        assert "is not before" in logs

    def test_equal_dates_fails(self):
        success, _ = evaluate_date_assertion("2024-01-02", "2024-01-02", "before")
        assert success is False


class TestAfter:
    def test_actual_after_expected_succeeds(self):
        success, _ = evaluate_date_assertion("2024-01-05", "2024-01-02", "after")
        assert success is True

    def test_actual_before_expected_fails(self):
        success, logs = evaluate_date_assertion("2024-01-02", "2024-01-05", "after")
        assert success is False and "is not after" in logs


class TestEquals:
    def test_equal_dates_succeeds(self):
        success, _ = evaluate_date_assertion("2024-01-02", "2024-01-02", "equals")
        assert success is True

    def test_different_dates_fails(self):
        success, logs = evaluate_date_assertion("2024-01-02", "2024-01-05", "equals")
        assert success is False and "does not equal" in logs

    def test_same_instant_different_offsets_succeeds(self):
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
        assert success is False and "expected inequality" in logs


# ── equals_within ────────────────────────────────────────────────────────


def _payload(date: str, tolerance: int, unit: str) -> str:
    return json.dumps({"date": date, "tolerance": tolerance, "unit": unit})


class TestEqualsWithin:
    def test_within_tolerance_succeeds(self):
        success, _ = evaluate_date_assertion(
            "2024-01-02T15:03:00+00:00",
            _payload("2024-01-02T15:00:00+00:00", 5, "minutes"),
            "equals_within",
        )
        assert success is True

    def test_at_exact_tolerance_boundary_succeeds(self):
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
        assert success is False and "exceeds tolerance" in logs

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

    def test_negative_diff_within_tolerance_succeeds(self):
        success, _ = evaluate_date_assertion(
            "2024-01-02T14:57:00+00:00",
            _payload("2024-01-02T15:00:00+00:00", 5, "minutes"),
            "equals_within",
        )
        assert success is True


# ── equals_within payload errors ─────────────────────────────────────────


class TestEqualsWithinPayloadErrors:
    def test_malformed_json(self):
        with pytest.raises(ValueError, match="must be JSON"):
            evaluate_date_assertion("2024-01-02", "not-json", "equals_within")

    def test_missing_date_field(self):
        with pytest.raises(ValueError, match="invalid shape"):
            evaluate_date_assertion(
                "2024-01-02",
                json.dumps({"tolerance": 5, "unit": "minutes"}),
                "equals_within",
            )

    def test_negative_tolerance(self):
        with pytest.raises(ValueError, match="invalid shape"):
            evaluate_date_assertion(
                "2024-01-02",
                _payload("2024-01-02", -1, "minutes"),
                "equals_within",
            )

    def test_unsupported_unit(self):
        with pytest.raises(ValueError, match="invalid shape"):
            evaluate_date_assertion(
                "2024-01-02",
                _payload("2024-01-02", 1, "months"),
                "equals_within",
            )

    def test_array_instead_of_object(self):
        with pytest.raises(ValueError, match="must be an object"):
            evaluate_date_assertion(
                "2024-01-02",
                json.dumps(["2024-01-02", 5, "minutes"]),
                "equals_within",
            )


# ── Naive-vs-aware warning ───────────────────────────────────────────────


class TestNaiveAwareWarning:
    def test_naive_vs_aware_warns_succeeds(self):
        success, logs = evaluate_date_assertion(
            "2024-01-02T15:00:00", "2024-01-02T15:00:00+00:00", "equals"
        )
        assert success is True and NAIVE_MIXED_WARNING in logs

    def test_both_naive_no_warning(self):
        success, logs = evaluate_date_assertion(
            "2024-01-02T15:00:00", "2024-01-02T15:00:00", "equals"
        )
        assert success is True and logs == ""

    def test_warning_present_alongside_failure(self):
        success, logs = evaluate_date_assertion(
            "2024-01-02T15:00:00", "2024-01-05T15:00:00+00:00", "equals"
        )
        assert success is False
        assert NAIVE_MIXED_WARNING in logs and "does not equal" in logs


# ── Error surface ────────────────────────────────────────────────────────


class TestErrorSurface:
    def test_unknown_operator(self):
        with pytest.raises(ValueError, match="Unknown date operator"):
            evaluate_date_assertion("2024-01-02", "2024-01-02", "between")

    def test_ambiguous_actual(self):
        with pytest.raises(DateParseError, match="ambiguous"):
            evaluate_date_assertion("01/02/2024", "2024-01-02", "equals")

    def test_ambiguous_expected(self):
        with pytest.raises(DateParseError, match="ambiguous"):
            evaluate_date_assertion("2024-01-02", "01/02/2024", "equals")
