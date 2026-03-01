"""Custom exception classes for the CI/CD runner."""

import re


class RunnerError(Exception):
    """Base exception for all runner errors."""
    pass


class AuthenticationError(RunnerError):
    """OAuth authentication failed."""
    
    def __init__(self, message: str):
        """
        Initialize authentication error.
        
        Args:
            message: Descriptive error message
        """
        super().__init__(message)
        self.message = message


class APIError(RunnerError):
    """API request failed."""
    
    def __init__(self, message: str, status_code: int, response: dict):
        """
        Initialize API error.
        
        Args:
            message: Descriptive error message
            status_code: HTTP status code
            response: Response body as dict
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response


class ConfigurationError(RunnerError):
    """Configuration validation failed."""
    
    def __init__(self, message: str):
        """
        Initialize configuration error.
        
        Args:
            message: Descriptive error message
        """
        super().__init__(message)
        self.message = message


class ExecutionError(RunnerError):
    """Test execution failed."""
    
    def __init__(self, message: str):
        """
        Initialize execution error.
        
        Args:
            message: Descriptive error message
        """
        super().__init__(message)
        self.message = message



def sanitize_error_message(message: str) -> str:
    """
    Sanitize error messages by removing sensitive data.
    
    Removes:
    - URLs with query parameters (e.g., ?token=abc123)
    - Email addresses
    - API keys and tokens in URLs
    
    Args:
        message: Raw error message
    
    Returns:
        Sanitized error message with sensitive data removed
    """
    if not message:
        return message
    
    # Remove query parameters from URLs
    sanitized = re.sub(
        r'(https?://[^\s?]+)\?[^\s]*',
        r'\1?[REDACTED]',
        message
    )
    
    # Remove email addresses
    sanitized = re.sub(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        '[EMAIL_REDACTED]',
        sanitized
    )
    
    # Remove common sensitive patterns in URLs
    # e.g., /token/abc123 -> /token/[REDACTED]
    sanitized = re.sub(
        r'/(token|key|secret|password|auth)/[^\s/]+',
        r'/\1/[REDACTED]',
        sanitized
    )
    
    return sanitized
