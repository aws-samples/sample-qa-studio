"""Error sanitization utilities."""

import re


def sanitize_error_message(message: str) -> str:
    """Sanitize error messages by removing sensitive data.

    Removes:
    - URLs with query parameters (e.g., ?token=abc123)
    - Email addresses
    - API keys and tokens in URLs
    """
    if not message:
        return message

    # Remove query parameters from URLs
    sanitized = re.sub(
        r'(https?://[^\s?]+)\?[^\s]*',
        r'\1?[REDACTED]',
        message,
    )

    # Remove email addresses
    sanitized = re.sub(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        '[EMAIL_REDACTED]',
        sanitized,
    )

    # Remove common sensitive patterns in URLs
    sanitized = re.sub(
        r'/(token|key|secret|password|auth)/[^\s/]+',
        r'/\1/[REDACTED]',
        sanitized,
    )

    return sanitized
