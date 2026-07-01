"""Security tests for browser and transform step types."""

import json
from unittest.mock import MagicMock

import pytest

from models import ExecutionStep
from browser_step import execute_browser_step, _validate_navigate_url
from transform.math_evaluator import UnsafeExpressionError, safe_eval_math
from transform.base import TRANSFORM_OPERATIONS


def _make_step(**overrides) -> ExecutionStep:
    defaults = dict(
        pk="EXECUTION#e1", sk="EXECUTION_STEP#s1", step_id="s1", sort=1,
        instruction="", artefact="", logs=[], created_at="2026-01-01",
        secret_key="", step_type="browser", validation_type="",
        validation_operator="", validation_value="", capture_variable="",
        value_type="", assertion_variable="",
    )
    defaults.update(overrides)
    return ExecutionStep(**defaults)


def _make_nova():
    nova = MagicMock()
    nova.page = MagicMock()
    nova.page.url = "https://example.com"
    return nova


class TestSSRFProtection:
    """Verify that navigate blocks internal/metadata URLs."""

    def test_blocks_metadata_endpoint(self):
        error = _validate_navigate_url("http://169.254.169.254/latest/meta-data/")
        assert error is not None
        assert "blocked" in error.lower()

    def test_blocks_metadata_ipv6(self):
        error = _validate_navigate_url("http://[fd00::1]/")
        assert error is not None

    def test_blocks_localhost(self):
        error = _validate_navigate_url("http://127.0.0.1/admin")
        assert error is not None

    def test_blocks_rfc1918_10(self):
        error = _validate_navigate_url("http://10.0.0.1/internal")
        assert error is not None

    def test_blocks_rfc1918_172(self):
        error = _validate_navigate_url("http://172.16.0.1/")
        assert error is not None

    def test_blocks_rfc1918_192(self):
        error = _validate_navigate_url("http://192.168.1.1/")
        assert error is not None

    def test_blocks_file_scheme(self):
        error = _validate_navigate_url("file:///etc/passwd")
        assert error is not None
        assert "scheme" in error.lower()

    def test_blocks_ftp_scheme(self):
        error = _validate_navigate_url("ftp://evil.com/file")
        assert error is not None

    def test_blocks_javascript_scheme(self):
        error = _validate_navigate_url("javascript:alert(1)")
        assert error is not None

    def test_allows_https(self):
        error = _validate_navigate_url("https://example.com/page")
        assert error is None

    def test_allows_http(self):
        error = _validate_navigate_url("http://example.com/page")
        assert error is None

    def test_allows_public_ip(self):
        error = _validate_navigate_url("http://8.8.8.8/")
        assert error is None

    def test_blocks_via_execute(self):
        """End-to-end: navigate to metadata IP fails the step."""
        nova = _make_nova()
        step = _make_step(
            browser_action="navigate",
            browser_args=json.dumps({"url": "http://169.254.169.254/latest/"}),
        )
        _, success, logs = execute_browser_step(nova, step)
        assert not success
        assert "blocked" in logs.lower()
        nova.go_to_url.assert_not_called()


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
