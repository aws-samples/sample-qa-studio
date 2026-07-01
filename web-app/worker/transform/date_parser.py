"""Centralized date parser for transform and validation surfaces.

Two parsing modes:

1. **Auto-detect** (no ``format`` arg): accepts only unambiguous formats —
   ISO 8601 / RFC 3339, Unix epoch seconds (10-digit), Unix epoch
   milliseconds (13-digit). Anything else fails with a clear message.

2. **Explicit format**: uses Python ``strptime`` with the supplied format
   (e.g. ``"%d/%m/%Y"``).

All results are returned as UTC ``datetime`` objects. The second tuple
element ``was_naive_input`` is ``True`` when the input string carried no
timezone information, so callers can warn on naive-vs-aware mixes per
the spec (``transform-dates``, R4) without making the parser itself
aware of comparison semantics.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone


class DateParseError(ValueError):
    """Raised when a date string cannot be parsed."""


_EPOCH_SECONDS_RE = re.compile(r"^\d{10}$")
_EPOCH_MILLIS_RE = re.compile(r"^\d{13}$")


def parse_to_utc(value: str, format: str | None = None) -> tuple[datetime, bool]:
    """Parse a date string into a UTC datetime.

    Args:
        value: The date string to parse. Leading/trailing whitespace is
            stripped before parsing.
        format: Optional Python ``strptime`` format. If ``None``, only
            ISO 8601 / RFC 3339 and Unix epoch (10-digit seconds,
            13-digit milliseconds) are accepted.

    Returns:
        A tuple ``(utc_datetime, was_naive_input)``. ``was_naive_input``
        is ``True`` when the parsed value carried no offset; the
        datetime is anchored to UTC regardless.

    Raises:
        DateParseError: On non-string, empty, ambiguous-without-format,
            or strptime-mismatch input.
    """
    if not isinstance(value, str):
        raise DateParseError(f"Expected str, got {type(value).__name__}")

    cleaned = value.strip()
    if not cleaned:
        raise DateParseError("Empty date string")

    if format is not None:
        return _parse_with_format(cleaned, format)
    return _auto_detect(cleaned)


def _auto_detect(value: str) -> tuple[datetime, bool]:
    """Try the auto-detect chain: epoch → ISO 8601.

    Epoch is checked first because Python 3.11+ ``fromisoformat`` is lenient
    enough to accept some all-digit strings as ISO 8601 basic format
    (e.g. ``"8796093022200"`` → year 8796). Pure 10- and 13-digit strings
    are unambiguously epoch values.
    """
    if _EPOCH_SECONDS_RE.match(value):
        return datetime.fromtimestamp(int(value), tz=timezone.utc), False

    if _EPOCH_MILLIS_RE.match(value):
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc), False

    iso_attempt = _try_iso(value)
    if iso_attempt is not None:
        return iso_attempt

    raise DateParseError(
        f"Date string '{value}' is ambiguous; provide a format argument "
        f"or use ISO 8601 (e.g. '2024-01-02' or '2024-01-02T15:04:05Z')."
    )


def _try_iso(value: str) -> tuple[datetime, bool] | None:
    """Attempt ISO 8601 parsing; return None on failure (no exception).

    Normalizes a trailing ``Z`` to ``+00:00`` for compatibility with older
    Python versions; harmless on 3.11+.
    """
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc), True
    return dt.astimezone(timezone.utc), False


def _parse_with_format(value: str, format: str) -> tuple[datetime, bool]:
    """Parse with explicit strptime format and normalize to UTC."""
    try:
        dt = datetime.strptime(value, format)
    except ValueError as exc:
        raise DateParseError(
            f"Date string '{value}' does not match format '{format}': {exc}"
        ) from exc

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc), True
    return dt.astimezone(timezone.utc), False
