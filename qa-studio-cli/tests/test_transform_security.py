"""Security tests for transform operations: format-string injection and the
exponentiation cap.

Moved from web-app/worker/tests/test_security.py when the worker started
using this package (codebase-health B4).
"""

import pytest

from qa_studio_cli.runner.transform.math_evaluator import UnsafeExpressionError, safe_eval_math
from qa_studio_cli.runner.transform.base import TRANSFORM_OPERATIONS


class TestFormatStringInjection:
    """Verify that format templates reject attribute/index access."""

    def test_rejects_attribute_access(self):
        op = TRANSFORM_OPERATIONS["format"]
        with pytest.raises(ValueError, match="attribute or index"):
            op.validate_and_execute({"template": "{0.__class__}", "args": ["x"]})

    def test_rejects_index_access(self):
        op = TRANSFORM_OPERATIONS["format"]
        with pytest.raises(ValueError, match="attribute or index"):
            op.validate_and_execute({"template": "{0[key]}", "args": ["x"]})

    def test_rejects_mro_attack(self):
        op = TRANSFORM_OPERATIONS["format"]
        with pytest.raises(ValueError, match="attribute or index"):
            op.validate_and_execute({"template": "{0.__class__.__mro__}", "args": ["x"]})

    def test_allows_positional(self):
        op = TRANSFORM_OPERATIONS["format"]
        result = op.validate_and_execute({"template": "Hello {}", "args": ["world"]})
        assert result == "Hello world"

    def test_allows_numbered_positional(self):
        op = TRANSFORM_OPERATIONS["format"]
        result = op.validate_and_execute({"template": "{0} + {1}", "args": ["a", "b"]})
        assert result == "a + b"


class TestExponentiationCap:
    """Verify that exponentiation is capped to prevent DoS."""

    def test_allows_reasonable_exponent(self):
        assert safe_eval_math("2 ** 10") == 1024

    def test_allows_max_exponent(self):
        safe_eval_math("2 ** 1000")  # should not raise

    def test_rejects_huge_exponent(self):
        with pytest.raises(UnsafeExpressionError, match="too large"):
            safe_eval_math("2 ** 1001")

    def test_rejects_negative_huge_exponent(self):
        with pytest.raises(UnsafeExpressionError, match="too large"):
            safe_eval_math("2 ** -1001")

    def test_rejects_nested_exponentiation(self):
        """9 ** 9 ** 9 — right-associative, so 9 ** (9**9) where 9**9 = 387420489 > 1000."""
        with pytest.raises(UnsafeExpressionError, match="too large"):
            safe_eval_math("9 ** 9 ** 9")
