"""Tests for the transform operation framework and math evaluator."""

import pytest

from qa_studio_cli.runner.transform.math_evaluator import UnsafeExpressionError, safe_eval_math
from qa_studio_cli.runner.transform.base import TRANSFORM_OPERATIONS
from qa_studio_cli.runner.transform.math_op import MathOperation


class TestSafeEvalMathArithmetic:
    """Test all allowed arithmetic operators."""

    def test_addition(self):
        assert safe_eval_math("2 + 3") == 5

    def test_subtraction(self):
        assert safe_eval_math("10 - 4") == 6

    def test_multiplication(self):
        assert safe_eval_math("3 * 7") == 21

    def test_division(self):
        assert safe_eval_math("10 / 4") == 2.5

    def test_modulo(self):
        assert safe_eval_math("10 % 3") == 1

    def test_power(self):
        assert safe_eval_math("2 ** 10") == 1024

    def test_unary_minus(self):
        assert safe_eval_math("-5") == -5

    def test_unary_plus(self):
        assert safe_eval_math("+5") == 5

    def test_integer_result(self):
        assert safe_eval_math("6 + 4") == 10
        assert isinstance(safe_eval_math("6 + 4"), int)

    def test_float_result(self):
        assert safe_eval_math("1.5 + 2.5") == 4.0


class TestSafeEvalMathPrecedence:
    """Test operator precedence and parentheses."""

    def test_precedence_mul_over_add(self):
        assert safe_eval_math("2 + 3 * 4") == 14

    def test_parentheses_override(self):
        assert safe_eval_math("(2 + 3) * 4") == 20

    def test_nested_parentheses(self):
        assert safe_eval_math("((1 + 2) * (3 + 4))") == 21

    def test_complex_expression(self):
        assert safe_eval_math("(10 - 2) * 3 + 4 / 2") == 26.0


class TestSafeEvalMathVariables:
    """Test variable substitution."""

    def test_single_variable(self):
        assert safe_eval_math("price", {"price": 42}) == 42

    def test_variable_in_expression(self):
        assert safe_eval_math("price * 1.2", {"price": 100}) == 120.0

    def test_multiple_variables(self):
        assert safe_eval_math("a + b", {"a": 3, "b": 7}) == 10

    def test_unknown_variable_raises(self):
        with pytest.raises(ValueError, match="Unknown variable.*'x'"):
            safe_eval_math("x + 1")

    def test_string_variable_raises(self):
        with pytest.raises(ValueError, match="must be numeric"):
            safe_eval_math("x + 1", {"x": "hello"})

    def test_list_variable_raises(self):
        with pytest.raises(ValueError, match="must be numeric"):
            safe_eval_math("x + 1", {"x": [1, 2]})

    def test_bool_variable_raises(self):
        with pytest.raises(ValueError, match="must be numeric"):
            safe_eval_math("x + 1", {"x": True})


class TestSafeEvalMathRejection:
    """Test that disallowed AST nodes are rejected."""

    def test_rejects_function_call(self):
        with pytest.raises(UnsafeExpressionError, match="Disallowed"):
            safe_eval_math("abs(-1)")

    def test_rejects_attribute_access(self):
        with pytest.raises(UnsafeExpressionError, match="Disallowed"):
            safe_eval_math("os.system")

    def test_rejects_subscript(self):
        with pytest.raises(UnsafeExpressionError, match="Disallowed"):
            safe_eval_math("x[0]", {"x": 1})

    def test_rejects_import(self):
        with pytest.raises(UnsafeExpressionError):
            safe_eval_math("__import__('os')")

    def test_rejects_comprehension(self):
        with pytest.raises(UnsafeExpressionError):
            safe_eval_math("[x for x in range(10)]")

    def test_rejects_lambda(self):
        with pytest.raises(UnsafeExpressionError, match="Disallowed"):
            safe_eval_math("lambda: 1")

    def test_rejects_string_constant(self):
        with pytest.raises(UnsafeExpressionError, match="Non-numeric"):
            safe_eval_math("'hello'")

    def test_rejects_boolean_constant(self):
        with pytest.raises(UnsafeExpressionError, match="Non-numeric"):
            safe_eval_math("True")

    def test_rejects_none_constant(self):
        with pytest.raises(UnsafeExpressionError, match="Non-numeric"):
            safe_eval_math("None")

    def test_rejects_invalid_syntax(self):
        with pytest.raises(UnsafeExpressionError, match="Invalid expression syntax"):
            safe_eval_math("2 +")

    def test_division_by_zero(self):
        with pytest.raises(ZeroDivisionError):
            safe_eval_math("1 / 0")

    def test_rejects_nested_exponentiation(self):
        """Nested exponents where each individual exponent ≤ 1000 but the
        intermediate result is astronomical (reviewer catch)."""
        with pytest.raises(UnsafeExpressionError):
            safe_eval_math("2 ** (2 ** (2 ** 10))")

    def test_rejects_large_base_exponentiation(self):
        """Large base with moderate exponent should be caught."""
        with pytest.raises(UnsafeExpressionError):
            safe_eval_math("9999 ** 500")

    def test_rejects_result_magnitude_overflow(self):
        """Even without Pow, multiplication chains that overflow should be caught."""
        # 10**308 is near the float limit; the magnitude check should catch it
        with pytest.raises(UnsafeExpressionError, match="magnitude too large"):
            safe_eval_math("10 ** 999")


class TestMathOperation:
    """Test the MathOperation transform class."""

    def test_registered(self):
        assert "math" in TRANSFORM_OPERATIONS
        assert isinstance(TRANSFORM_OPERATIONS["math"], MathOperation)

    def test_validate_and_execute(self):
        op = TRANSFORM_OPERATIONS["math"]
        result = op.validate_and_execute({"expression": "2 + 3 * 4"})
        assert result == 14

    def test_missing_expression_raises(self):
        op = TRANSFORM_OPERATIONS["math"]
        with pytest.raises(Exception):  # pydantic ValidationError
            op.validate_and_execute({})
