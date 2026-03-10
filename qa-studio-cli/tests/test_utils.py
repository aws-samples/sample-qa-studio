"""Tests for utility modules: url, variables, errors, log_filters, logger."""

from unittest.mock import patch, MagicMock
import logging

from qa_studio_cli.utils.url import apply_base_url_override
from qa_studio_cli.utils.variables import merge_variables
from qa_studio_cli.utils.errors import sanitize_error_message
from qa_studio_cli.utils.log_filters import NovaActLogFilter


class TestApplyBaseUrlOverride:
    """Tests for apply_base_url_override."""

    def test_replaces_origin_preserves_path(self):
        result = apply_base_url_override(
            "https://staging.example.com/login", "http://localhost:3000"
        )
        assert result == "http://localhost:3000/login"

    def test_preserves_query_params(self):
        result = apply_base_url_override(
            "https://staging.example.com/page?foo=bar&baz=1",
            "http://localhost:3000",
        )
        assert result == "http://localhost:3000/page?foo=bar&baz=1"

    def test_preserves_fragment(self):
        result = apply_base_url_override(
            "https://staging.example.com/page#section",
            "http://localhost:3000",
        )
        assert result == "http://localhost:3000/page#section"

    def test_empty_path(self):
        result = apply_base_url_override(
            "https://staging.example.com", "http://localhost:3000"
        )
        assert result == "http://localhost:3000"

    def test_override_with_port(self):
        result = apply_base_url_override(
            "https://prod.example.com/api/v1", "http://localhost:8080"
        )
        assert result == "http://localhost:8080/api/v1"


class TestMergeVariables:
    """Tests for merge_variables."""

    def test_cli_overrides_api(self):
        result = merge_variables({"a": "1", "b": "2"}, {"b": "3"})
        assert result == {"a": "1", "b": "3"}

    def test_empty_overrides(self):
        result = merge_variables({"a": "1"}, {})
        assert result == {"a": "1"}

    def test_empty_api_vars(self):
        result = merge_variables({}, {"x": "y"})
        assert result == {"x": "y"}

    def test_both_empty(self):
        result = merge_variables({}, {})
        assert result == {}

    def test_no_mutation(self):
        api = {"a": "1"}
        cli = {"b": "2"}
        result = merge_variables(api, cli)
        assert result == {"a": "1", "b": "2"}
        assert api == {"a": "1"}  # original unchanged


class TestSanitizeErrorMessage:
    """Tests for sanitize_error_message."""

    def test_strips_url_query_params(self):
        msg = "Request to https://api.example.com/auth?token=secret123 failed"
        result = sanitize_error_message(msg)
        assert "secret123" not in result
        assert "?[REDACTED]" in result

    def test_strips_email(self):
        msg = "User user@example.com not found"
        result = sanitize_error_message(msg)
        assert "user@example.com" not in result
        assert "[EMAIL_REDACTED]" in result

    def test_strips_sensitive_url_paths(self):
        msg = "Error at /token/abc123def"
        result = sanitize_error_message(msg)
        assert "abc123def" not in result

    def test_preserves_safe_text(self):
        msg = "Step 3 failed: element not found"
        result = sanitize_error_message(msg)
        assert "Step 3 failed" in result

    def test_empty_string(self):
        assert sanitize_error_message("") == ""


class TestNovaActLogFilter:
    """Tests for NovaActLogFilter."""

    def test_allows_non_nova_act_records(self):
        f = NovaActLogFilter()
        record = logging.LogRecord(
            name="qa_studio_cli.runner",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True

    def test_rejects_nova_act_records(self):
        f = NovaActLogFilter()
        record = logging.LogRecord(
            name="nova_act.internal",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="internal debug",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False

    def test_rejects_nova_act_root(self):
        f = NovaActLogFilter()
        record = logging.LogRecord(
            name="nova_act",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="root log",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False
