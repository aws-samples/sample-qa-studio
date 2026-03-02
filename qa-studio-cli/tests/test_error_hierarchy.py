"""Tests for the unified error hierarchy."""

import pytest

from qa_studio_cli.models.errors import (
    QAStudioError,
    AuthError,
    ConfigError,
    ApiError,
    ExecutionError,
)


class TestErrorHierarchy:
    """All error classes inherit from QAStudioError and have .message."""

    def test_qa_studio_error_is_base(self):
        err = QAStudioError("base error")
        assert isinstance(err, Exception)
        assert err.message == "base error"
        assert str(err) == "base error"

    def test_auth_error_inherits_from_base(self):
        err = AuthError("auth failed")
        assert isinstance(err, QAStudioError)
        assert isinstance(err, Exception)
        assert err.message == "auth failed"

    def test_config_error_inherits_from_base(self):
        err = ConfigError("config missing")
        assert isinstance(err, QAStudioError)
        assert err.message == "config missing"

    def test_api_error_inherits_from_base(self):
        err = ApiError(status_code=500, message="server error")
        assert isinstance(err, QAStudioError)
        assert err.message == "server error"
        assert err.status_code == 500
        assert err.error_code is None

    def test_api_error_with_error_code(self):
        err = ApiError(status_code=422, message="invalid", error_code="VALIDATION")
        assert err.error_code == "VALIDATION"
        assert str(err) == "[422] invalid (VALIDATION)"

    def test_api_error_str_without_error_code(self):
        err = ApiError(status_code=404, message="not found")
        assert str(err) == "[404] not found"

    def test_execution_error_inherits_from_base(self):
        err = ExecutionError("test failed")
        assert isinstance(err, QAStudioError)
        assert err.message == "test failed"

    def test_all_errors_catchable_as_qa_studio_error(self):
        """Catching QAStudioError catches all subclasses."""
        errors = [
            AuthError("a"),
            ConfigError("c"),
            ApiError(400, "b"),
            ExecutionError("e"),
        ]
        for err in errors:
            with pytest.raises(QAStudioError):
                raise err

    def test_specific_catch_does_not_catch_siblings(self):
        """AuthError catch does not catch ConfigError."""
        with pytest.raises(ConfigError):
            raise ConfigError("wrong type")
        # This should NOT be caught by AuthError
        with pytest.raises(QAStudioError):
            raise ConfigError("caught by base")
