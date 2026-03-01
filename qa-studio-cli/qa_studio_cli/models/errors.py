"""Custom exception classes for the QA Studio CLI."""


class AuthError(Exception):
    """Raised when authentication fails or tokens are invalid."""

    def __init__(self, message: str):
        """
        Initialize authentication error.

        Args:
            message: Descriptive error message
        """
        super().__init__(message)
        self.message = message


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""

    def __init__(self, message: str):
        """
        Initialize configuration error.

        Args:
            message: Descriptive error message
        """
        super().__init__(message)
        self.message = message
