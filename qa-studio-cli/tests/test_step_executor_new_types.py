"""Tests for browser and transform step execution in the CLI runner.

These tests exercise the pure-logic parts (transform operations, math evaluator)
without requiring NovaAct or a browser.
"""

import json
import sys

import pytest


# The step_executor module imports nova_act at module level, which isn't
# installed in the test environment.  We mock it so we can import the module.
sys.modules.setdefault("nova_act", type(sys)("nova_act"))
nova_act_mod = sys.modules["nova_act"]
nova_act_mod.NovaAct = type("NovaAct", (), {})
nova_act_mod.BOOL_SCHEMA = {"type": "boolean"}
nova_act_mod.Workflow = type("Workflow", (), {})

from qa_studio_cli.runner.step_executor import StepExecutor, _safe_eval_math


class TestSafeEvalMath:
    """Test the CLI's math evaluator (mirrors worker's)."""

    def test_basic_arithmetic(self):
        assert _safe_eval_math("2 + 3 * 4") == 14

    def test_parentheses(self):
        assert _safe_eval_math("(2 + 3) * 4") == 20

    def test_power(self):
        assert _safe_eval_math("2 ** 10") == 1024

    def test_unary_minus(self):
        assert _safe_eval_math("-5 + 3") == -2

    def test_rejects_function_call(self):
        with pytest.raises(ValueError, match="Disallowed"):
            _safe_eval_math("abs(-1)")

    def test_rejects_string(self):
        with pytest.raises(ValueError, match="Non-numeric"):
            _safe_eval_math("'hello'")

    def test_rejects_boolean(self):
        with pytest.raises(ValueError, match="Non-numeric"):
            _safe_eval_math("True")

    def test_string_variable_raises(self):
        with pytest.raises(ValueError, match="must be numeric"):
            _safe_eval_math("x + 1", {"x": "hello"})

    def test_list_variable_raises(self):
        with pytest.raises(ValueError, match="must be numeric"):
            _safe_eval_math("x + 1", {"x": [1, 2]})

    def test_rejects_nested_exponentiation(self):
        """Nested exponents where each individual exponent ≤ 1000 but the
        intermediate result is astronomical (reviewer catch)."""
        with pytest.raises(ValueError):
            _safe_eval_math("2 ** (2 ** (2 ** 10))")

    def test_rejects_large_base_exponentiation(self):
        """Large base with moderate exponent should be caught."""
        with pytest.raises(ValueError):
            _safe_eval_math("9999 ** 500")

    def test_rejects_result_magnitude_overflow(self):
        """Result exceeding 1e308 should be caught."""
        with pytest.raises(ValueError, match="magnitude too large"):
            _safe_eval_math("10 ** 999")


class TestRunTransform:
    """Test the CLI's transform operation dispatch."""

    def _run(self, op, args):
        return StepExecutor._run_transform(op, args)

    def test_math(self):
        assert self._run("math", {"expression": "10 + 5"}) == 15

    def test_floor(self):
        assert self._run("floor", {"value": "9.99"}) == 9

    def test_ceil(self):
        assert self._run("ceil", {"value": "1.1"}) == 2

    def test_round(self):
        assert self._run("round", {"value": "3.14159", "digits": "2"}) == 3.14

    def test_abs(self):
        assert self._run("abs", {"value": "-42"}) == 42

    def test_min(self):
        assert self._run("min", {"values": [3, 1, 2]}) == 1

    def test_max(self):
        assert self._run("max", {"values": [3, 1, 2]}) == 3

    def test_concat(self):
        assert self._run("concat", {"values": ["a", "b", "c"]}) == "abc"

    def test_upper(self):
        assert self._run("upper", {"value": "hello"}) == "HELLO"

    def test_lower(self):
        assert self._run("lower", {"value": "HELLO"}) == "hello"

    def test_trim(self):
        assert self._run("trim", {"value": "  hi  "}) == "hi"

    def test_replace(self):
        assert self._run("replace", {"value": "hello world", "old": "world", "new": "there"}) == "hello there"

    def test_substring(self):
        assert self._run("substring", {"value": "hello", "start": 1, "end": 3}) == "el"

    def test_substring_no_end(self):
        assert self._run("substring", {"value": "hello", "start": 2}) == "llo"

    def test_length(self):
        assert self._run("length", {"value": "hello"}) == 5

    def test_to_number(self):
        assert self._run("to_number", {"value": "3.14"}) == 3.14

    def test_to_string(self):
        assert self._run("to_string", {"value": "42"}) == "42"

    def test_to_int(self):
        assert self._run("to_int", {"value": "3.9"}) == 3

    def test_regex_extract(self):
        assert self._run("regex_extract", {"value": "Order #123", "pattern": r"#(\d+)", "group": 1}) == "123"

    def test_format(self):
        assert self._run("format", {"template": "Hi {}", "args": ["world"]}) == "Hi world"

    def test_unknown_operation(self):
        with pytest.raises(ValueError, match="Unknown"):
            self._run("eval", {})


class TestTransformOperationConsistency:
    """Verify the CLI supports the same operations as the worker."""

    EXPECTED_OPS = {
        "math", "round", "floor", "ceil", "abs", "min", "max",
        "concat", "upper", "lower", "trim", "replace", "substring", "length",
        "to_number", "to_string", "to_int", "regex_extract", "format",
    }

    @pytest.mark.parametrize("op", sorted(EXPECTED_OPS))
    def test_operation_does_not_raise_unknown(self, op):
        """Each known operation should not raise 'Unknown transform operation'."""
        # We just need to verify the match arm exists — the operation may fail
        # due to missing args, but it should NOT raise "Unknown".
        try:
            StepExecutor._run_transform(op, {"value": "1", "values": [1], "expression": "1",
                                              "template": "{}", "args": ["x"],
                                              "pattern": ".", "old": "a", "new": "b",
                                              "start": 0, "end": 1, "digits": 0, "group": 0})
        except ValueError as e:
            assert "Unknown" not in str(e), f"Operation '{op}' not recognized"
