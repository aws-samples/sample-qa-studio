"""Tests for built-in transform operations (Task 4)."""

import pytest

from qa_studio_cli.runner.transform.base import TRANSFORM_OPERATIONS


def _exec(name: str, args: dict):
    """Shorthand: validate_and_execute for a named operation."""
    return TRANSFORM_OPERATIONS[name].validate_and_execute(args)


# ── Numeric operations ──────────────────────────────────────────────────────

class TestRound:
    def test_round_default(self):
        assert _exec("round", {"value": 3.7}) == 4

    def test_round_digits(self):
        assert _exec("round", {"value": 3.14159, "digits": 2}) == 3.14

    def test_round_negative(self):
        assert _exec("round", {"value": -2.5}) == -2


class TestFloor:
    def test_floor_positive(self):
        assert _exec("floor", {"value": 3.9}) == 3

    def test_floor_negative(self):
        assert _exec("floor", {"value": -1.1}) == -2

    def test_floor_integer(self):
        assert _exec("floor", {"value": 5.0}) == 5


class TestCeil:
    def test_ceil_positive(self):
        assert _exec("ceil", {"value": 3.1}) == 4

    def test_ceil_negative(self):
        assert _exec("ceil", {"value": -1.9}) == -1

    def test_ceil_integer(self):
        assert _exec("ceil", {"value": 5.0}) == 5


class TestAbs:
    def test_abs_negative(self):
        assert _exec("abs", {"value": -42}) == 42

    def test_abs_positive(self):
        assert _exec("abs", {"value": 42}) == 42

    def test_abs_zero(self):
        assert _exec("abs", {"value": 0}) == 0


class TestMin:
    def test_min_basic(self):
        assert _exec("min", {"values": [3, 1, 2]}) == 1

    def test_min_single(self):
        assert _exec("min", {"values": [7]}) == 7

    def test_min_empty_raises(self):
        with pytest.raises(ValueError, match="at least one"):
            _exec("min", {"values": []})


class TestMax:
    def test_max_basic(self):
        assert _exec("max", {"values": [3, 1, 2]}) == 3

    def test_max_negative(self):
        assert _exec("max", {"values": [-5, -1, -3]}) == -1

    def test_max_empty_raises(self):
        with pytest.raises(ValueError, match="at least one"):
            _exec("max", {"values": []})


# ── String operations ───────────────────────────────────────────────────────

class TestConcat:
    def test_concat_basic(self):
        assert _exec("concat", {"values": ["hello", " ", "world"]}) == "hello world"

    def test_concat_empty(self):
        assert _exec("concat", {"values": []}) == ""

    def test_concat_single(self):
        assert _exec("concat", {"values": ["only"]}) == "only"


class TestUpper:
    def test_upper(self):
        assert _exec("upper", {"value": "hello"}) == "HELLO"

    def test_upper_empty(self):
        assert _exec("upper", {"value": ""}) == ""

    def test_upper_already(self):
        assert _exec("upper", {"value": "ABC"}) == "ABC"


class TestLower:
    def test_lower(self):
        assert _exec("lower", {"value": "HELLO"}) == "hello"

    def test_lower_empty(self):
        assert _exec("lower", {"value": ""}) == ""


class TestTrim:
    def test_trim(self):
        assert _exec("trim", {"value": "  hello  "}) == "hello"

    def test_trim_empty(self):
        assert _exec("trim", {"value": ""}) == ""

    def test_trim_tabs_newlines(self):
        assert _exec("trim", {"value": "\t\nhello\n\t"}) == "hello"


class TestReplace:
    def test_replace_basic(self):
        assert _exec("replace", {"value": "hello world", "old": "world", "new": "there"}) == "hello there"

    def test_replace_multiple(self):
        assert _exec("replace", {"value": "aaa", "old": "a", "new": "b"}) == "bbb"

    def test_replace_not_found(self):
        assert _exec("replace", {"value": "hello", "old": "xyz", "new": "abc"}) == "hello"


class TestSubstring:
    def test_substring_basic(self):
        assert _exec("substring", {"value": "hello world", "start": 0, "end": 5}) == "hello"

    def test_substring_no_end(self):
        assert _exec("substring", {"value": "hello world", "start": 6}) == "world"

    def test_substring_out_of_range(self):
        assert _exec("substring", {"value": "hi", "start": 0, "end": 100}) == "hi"

    def test_substring_empty(self):
        assert _exec("substring", {"value": "hello", "start": 2, "end": 2}) == ""


class TestLength:
    def test_length_basic(self):
        assert _exec("length", {"value": "hello"}) == 5

    def test_length_empty(self):
        assert _exec("length", {"value": ""}) == 0

    def test_length_unicode(self):
        assert _exec("length", {"value": "café"}) == 4


# ── Coercion operations ────────────────────────────────────────────────────

class TestToNumber:
    def test_to_number_int(self):
        assert _exec("to_number", {"value": "42"}) == 42.0

    def test_to_number_float(self):
        assert _exec("to_number", {"value": "3.14"}) == 3.14

    def test_to_number_invalid(self):
        with pytest.raises(ValueError, match="Cannot convert"):
            _exec("to_number", {"value": "abc"})


class TestToString:
    def test_to_string(self):
        assert _exec("to_string", {"value": "42"}) == "42"

    def test_to_string_empty(self):
        assert _exec("to_string", {"value": ""}) == ""


class TestToInt:
    def test_to_int_from_int_string(self):
        assert _exec("to_int", {"value": "42"}) == 42

    def test_to_int_from_float_string(self):
        assert _exec("to_int", {"value": "3.9"}) == 3

    def test_to_int_invalid(self):
        with pytest.raises(ValueError, match="Cannot convert"):
            _exec("to_int", {"value": "abc"})


# ── Pattern operations ──────────────────────────────────────────────────────

class TestRegexExtract:
    def test_extract_basic(self):
        assert _exec("regex_extract", {"value": "Order #12345", "pattern": r"#(\d+)", "group": 1}) == "12345"

    def test_extract_group_0(self):
        assert _exec("regex_extract", {"value": "abc123", "pattern": r"\d+"}) == "123"

    def test_extract_no_match(self):
        with pytest.raises(ValueError, match="did not match"):
            _exec("regex_extract", {"value": "hello", "pattern": r"\d+"})

    def test_extract_invalid_regex(self):
        with pytest.raises(ValueError, match="Invalid regex"):
            _exec("regex_extract", {"value": "hello", "pattern": r"[invalid"})

    def test_extract_invalid_group(self):
        with pytest.raises(ValueError, match="Group.*not found"):
            _exec("regex_extract", {"value": "abc123", "pattern": r"\d+", "group": 5})


# ── Format operation ────────────────────────────────────────────────────────

class TestFormat:
    def test_format_basic(self):
        assert _exec("format", {"template": "Order #{}", "args": ["12345"]}) == "Order #12345"

    def test_format_multiple(self):
        assert _exec("format", {"template": "{} + {} = {}", "args": ["1", "2", "3"]}) == "1 + 2 = 3"

    def test_format_no_args(self):
        assert _exec("format", {"template": "hello"}) == "hello"


# ── Registry completeness ──────────────────────────────────────────────────

class TestRegistry:
    EXPECTED_OPS = {
        "math", "round", "floor", "ceil", "abs", "min", "max",
        "concat", "upper", "lower", "trim", "replace", "substring", "length",
        "to_number", "to_string", "to_int", "regex_extract", "format",
    }

    def test_all_operations_registered(self):
        assert set(TRANSFORM_OPERATIONS.keys()) == self.EXPECTED_OPS

    @pytest.mark.parametrize("name", sorted(EXPECTED_OPS))
    def test_each_operation_has_args_model(self, name):
        op = TRANSFORM_OPERATIONS[name]
        assert hasattr(op, "args_model")
        assert op.args_model is not None
