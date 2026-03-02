"""Unified exception hierarchy for QA Studio CLI and runner."""


class QAStudioError(Exception):
    """Base exception for all QA Studio errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class AuthError(QAStudioError):
    """Raised when authentication fails or tokens are invalid."""

    pass


class ConfigError(QAStudioError):
    """Raised when configuration is missing or invalid."""

    pass


class ApiError(QAStudioError):
    """Raised when the backend API returns a non-success HTTP status code."""

    def __init__(self, status_code: int, message: str, error_code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code

    def __str__(self) -> str:
        if self.error_code:
            return f"[{self.status_code}] {self.message} ({self.error_code})"
        return f"[{self.status_code}] {self.message}"


class ExecutionError(QAStudioError):
    """Raised when test execution fails (runner-specific)."""

    pass
