"""Unit tests for StepExecutor._compare operator logic.

Tests all validation operators (string, number, boolean) used in
validation and assertion steps. The _compare method is a @staticmethod
so it can be tested without Nova Act dependencies.
"""

import pytest

from qa_studio_cli.runner.step_executor import StepExecutor


# ---------------------------------------------------------------------------
# String operators
# ---------------------------------------------------------------------------


class TestStringExact:
    """Operator: exact — case-sensitive string equality."""

    def test_equal_strings(self):
        assert StepExecutor._compare("string", "exact", "Dashboard", "Dashboard") is True

    def test_different_strings(self):
        assert StepExecutor._compare("string", "exact", "Dashboard", "Settings") is False

    def test_case_mismatch_fails(self):
        assert StepExecutor._compare("string", "exact", "dashboard", "Dashboard") is False

    def test_strips_whitespace(self):
        assert StepExecutor._compare("string", "exact", "  hello  ", "  hello  ") is True

    def test_strips_surrounding_quotes(self):
        assert StepExecutor._compare("string", "exact", '"hello"', "hello") is True
        assert StepExecutor._compare("string", "exact", "'hello'", "hello") is True

    def test_empty_strings(self):
        assert StepExecutor._compare("string", "exact", "", "") is True

    def test_none_actual(self):
        assert StepExecutor._compare("string", "exact", "hello", None) is False

    def test_both_empty_with_none(self):
        assert StepExecutor._compare("string", "exact", "", None) is True


class TestStringExactCaseInsensitive:
    """Operator: exact_case_insensitive — case-insensitive string equality."""

    def test_same_case(self):
        assert StepExecutor._compare("string", "exact_case_insensitive", "Active", "Active") is True

    def test_different_case(self):
        assert StepExecutor._compare("string", "exact_case_insensitive", "active", "ACTIVE") is True

    def test_mixed_case(self):
        assert StepExecutor._compare("string", "exact_case_insensitive", "AcTiVe", "active") is True

    def test_different_strings(self):
        assert StepExecutor._compare("string", "exact_case_insensitive", "active", "inactive") is False


class TestStringContains:
    """Operator: contains — case-sensitive substring check."""

    def test_substring_present(self):
        assert StepExecutor._compare("string", "contains", "saved", "Changes saved successfully") is True

    def test_substring_absent(self):
        assert StepExecutor._compare("string", "contains", "deleted", "Changes saved successfully") is False

    def test_case_mismatch_fails(self):
        assert StepExecutor._compare("string", "contains", "Saved", "changes saved successfully") is False

    def test_full_match(self):
        assert StepExecutor._compare("string", "contains", "hello", "hello") is True

    def test_empty_expected(self):
        assert StepExecutor._compare("string", "contains", "", "anything") is True

    def test_special_regex_chars_escaped(self):
        assert StepExecutor._compare("string", "contains", "price: $9.99", "The price: $9.99 is final") is True

    def test_regex_pattern_not_interpreted(self):
        assert StepExecutor._compare("string", "contains", ".*", "hello") is False


class TestStringContainsCaseInsensitive:
    """Operator: contains_case_insensitive — case-insensitive substring check."""

    def test_substring_different_case(self):
        assert StepExecutor._compare("string", "contains_case_insensitive", "invalid email", "INVALID EMAIL address") is True

    def test_substring_absent(self):
        assert StepExecutor._compare("string", "contains_case_insensitive", "password", "Invalid email address") is False

    def test_special_regex_chars_escaped(self):
        assert StepExecutor._compare("string", "contains_case_insensitive", "Price: $9.99", "the price: $9.99 is final") is True


class TestStringNotEqual:
    """Operator: not_equal — string inequality."""

    def test_different_strings(self):
        assert StepExecutor._compare("string", "not_equal", "Guest", "Admin") is True

    def test_same_strings(self):
        assert StepExecutor._compare("string", "not_equal", "Guest", "Guest") is False

    def test_empty_vs_nonempty(self):
        assert StepExecutor._compare("string", "not_equal", "", "something") is True

    def test_none_actual_vs_nonempty(self):
        assert StepExecutor._compare("string", "not_equal", "hello", None) is True

    def test_none_actual_vs_empty(self):
        assert StepExecutor._compare("string", "not_equal", "", None) is False


class TestStringUnknownOperator:
    """Unknown string operators fall back to exact match."""

    def test_unknown_operator_falls_back_to_exact(self):
        assert StepExecutor._compare("string", "unknown_op", "hello", "hello") is True
        assert StepExecutor._compare("string", "unknown_op", "hello", "world") is False


# ---------------------------------------------------------------------------
# Number operators
# ---------------------------------------------------------------------------


class TestNumberEquals:
    """Operator: equals — numeric equality."""

    def test_equal_integers(self):
        assert StepExecutor._compare("number", "equals", "3", "3") is True

    def test_equal_floats(self):
        assert StepExecutor._compare("number", "equals", "3.14", "3.14") is True

    def test_int_vs_float(self):
        assert StepExecutor._compare("number", "equals", "3", "3.0") is True

    def test_not_equal(self):
        assert StepExecutor._compare("number", "equals", "3", "4") is False

    def test_none_actual_defaults_to_zero(self):
        assert StepExecutor._compare("number", "equals", "0", None) is True

    def test_non_numeric_returns_false(self):
        assert StepExecutor._compare("number", "equals", "abc", "3") is False

    def test_non_numeric_actual_returns_false(self):
        assert StepExecutor._compare("number", "equals", "3", "abc") is False


class TestNumberGreaterThen:
    """Operator: greater_then — strictly greater than."""

    def test_greater(self):
        assert StepExecutor._compare("number", "greater_then", "0", "5") is True

    def test_equal_fails(self):
        assert StepExecutor._compare("number", "greater_then", "5", "5") is False

    def test_less_fails(self):
        assert StepExecutor._compare("number", "greater_then", "10", "5") is False

    def test_negative_numbers(self):
        assert StepExecutor._compare("number", "greater_then", "-5", "-2") is True

    def test_float_comparison(self):
        assert StepExecutor._compare("number", "greater_then", "3.14", "3.15") is True


class TestNumberLessThen:
    """Operator: less_then — strictly less than."""

    def test_less(self):
        assert StepExecutor._compare("number", "less_then", "5", "3") is True

    def test_equal_fails(self):
        assert StepExecutor._compare("number", "less_then", "5", "5") is False

    def test_greater_fails(self):
        assert StepExecutor._compare("number", "less_then", "5", "10") is False


class TestNumberGreaterOrEqualThen:
    """Operator: greater_or_equal_then — greater than or equal."""

    def test_greater(self):
        assert StepExecutor._compare("number", "greater_or_equal_then", "9.99", "10.00") is True

    def test_equal(self):
        assert StepExecutor._compare("number", "greater_or_equal_then", "9.99", "9.99") is True

    def test_less_fails(self):
        assert StepExecutor._compare("number", "greater_or_equal_then", "9.99", "5.00") is False


class TestNumberLessOrEqualThen:
    """Operator: less_or_equal_then — less than or equal."""

    def test_less(self):
        assert StepExecutor._compare("number", "less_or_equal_then", "3000", "2500") is True

    def test_equal(self):
        assert StepExecutor._compare("number", "less_or_equal_then", "3000", "3000") is True

    def test_greater_fails(self):
        assert StepExecutor._compare("number", "less_or_equal_then", "3000", "3500") is False


class TestNumberUnknownOperator:
    """Unknown number operators fall back to equals."""

    def test_unknown_operator_falls_back_to_equals(self):
        assert StepExecutor._compare("number", "unknown_op", "5", "5") is True
        assert StepExecutor._compare("number", "unknown_op", "5", "6") is False


# ---------------------------------------------------------------------------
# Boolean operators
# ---------------------------------------------------------------------------


class TestBoolExact:
    """Operator: exact (bool) — boolean comparison."""

    def test_true_matches_true(self):
        assert StepExecutor._compare("bool", "exact", "true", True) is True

    def test_false_matches_false(self):
        assert StepExecutor._compare("bool", "exact", "false", False) is True

    def test_true_vs_false(self):
        assert StepExecutor._compare("bool", "exact", "true", False) is False

    def test_false_vs_true(self):
        assert StepExecutor._compare("bool", "exact", "false", True) is False

    def test_case_insensitive_expected(self):
        assert StepExecutor._compare("bool", "exact", "True", True) is True
        assert StepExecutor._compare("bool", "exact", "TRUE", True) is True

    def test_string_true_actual(self):
        assert StepExecutor._compare("bool", "exact", "true", "true") is True
        assert StepExecutor._compare("bool", "exact", "true", "True") is True

    def test_none_actual_is_false(self):
        assert StepExecutor._compare("bool", "exact", "false", None) is True
        assert StepExecutor._compare("bool", "exact", "true", None) is False

    def test_non_true_string_is_false(self):
        assert StepExecutor._compare("bool", "exact", "false", "anything") is True
        assert StepExecutor._compare("bool", "exact", "true", "anything") is False
