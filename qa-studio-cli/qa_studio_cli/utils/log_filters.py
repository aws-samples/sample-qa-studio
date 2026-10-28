"""Logging filters for thread isolation, nova-act suppression, and redaction."""

import logging
import re
import threading
from typing import Set


class ThreadLogFilter(logging.Filter):
    """Only accept log records from a specific thread."""

    def __init__(self, thread_id: int):
        super().__init__()
        self.thread_id = thread_id

    def filter(self, record: logging.LogRecord) -> bool:
        return record.thread == self.thread_id


class NovaActLogFilter(logging.Filter):
    """Reject log records from the nova_act logger hierarchy."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith("nova_act")


# AWS SDK / HTTP libraries whose DEBUG output contains credentials:
# botocore logs the full SigV4 canonical request, including the
# ``x-amz-security-token`` header (temporary STS credentials).
NOISY_LOGGER_PREFIXES = ("botocore", "boto3", "urllib3", "s3transfer")


class NoisyLibraryFilter(logging.Filter):
    """Drop records below WARNING from AWS SDK and HTTP client libraries."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True
        return not any(
            record.name == prefix or record.name.startswith(prefix + ".")
            for prefix in NOISY_LOGGER_PREFIXES
        )


# Values shorter than this are not masked: replacing very short strings
# (e.g. "1") throughout every log line would make logs unreadable.
MIN_REGISTERED_SECRET_LENGTH = 4
REDACTED = "***"

_registered_secrets: Set[str] = set()
_registry_lock = threading.Lock()

_REDACTION_PATTERNS = [
    # Authorization: Bearer <token>
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*"), r"\1" + REDACTED),
    # Any JWT (header.payload.signature), e.g. Cognito access/id tokens
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), REDACTED),
    # STS session token as a header (``x-amz-security-token: ...``) or
    # presigned-URL query parameter (``X-Amz-Security-Token=...``)
    (re.compile(r"(x-amz-security-token\s*[:=]\s*)[^\s&\"',}]+", re.IGNORECASE), r"\1" + REDACTED),
    # SigV4 signatures (presigned URLs and Authorization headers)
    (re.compile(r"((?:X-Amz-)?Signature\s*=\s*)[0-9a-fA-F]{16,}"), r"\1" + REDACTED),
    # Credential-bearing key/value pairs in JSON, dict reprs, or env style
    (
        re.compile(
            r"""(["']?(?:client_secret|secret_access_key|SecretAccessKey|"""
            r"""aws_secret_access_key|SessionToken|session_token|password|"""
            r"""access_token|id_token|refresh_token)["']?\s*[:=]\s*["']?)"""
            r"""[^\s"',}]+""",
            re.IGNORECASE,
        ),
        r"\1" + REDACTED,
    ),
]


def register_secret_value(value: str) -> None:
    """Register a resolved secret so it is masked in all subsequent logs."""
    if not value or len(value) < MIN_REGISTERED_SECRET_LENGTH:
        return
    with _registry_lock:
        _registered_secrets.add(value)


def clear_registered_secrets() -> None:
    """Forget all registered secret values (used between runs and in tests)."""
    with _registry_lock:
        _registered_secrets.clear()


def redact(text: str) -> str:
    """Mask registered secret values and known credential patterns in text."""
    with _registry_lock:
        secrets = sorted(_registered_secrets, key=len, reverse=True)
    for secret in secrets:
        text = text.replace(secret, REDACTED)
    for pattern, replacement in _REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class SecretRedactionFilter(logging.Filter):
    """Mask secrets and credentials in a record's rendered message.

    The record is rewritten in place (``msg`` replaced, ``args`` cleared), so
    every handler that sees the record afterwards also gets the masked text.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True
