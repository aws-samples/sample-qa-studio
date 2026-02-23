"""Tests for log filters: ThreadLogFilter and NovaActLogFilter.

Includes property-based tests (hypothesis) and unit tests.
"""

import logging
import threading

import pytest
from hypothesis import given, settings, strategies as st

from src.utils.log_filters import NovaActLogFilter, ThreadLogFilter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(logger_name: str = "test", thread_id: int | None = None) -> logging.LogRecord:
    """Create a minimal LogRecord, optionally overriding the thread id."""
    record = logging.LogRecord(
        name=logger_name,
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test message",
        args=None,
        exc_info=None,
    )
    if thread_id is not None:
        record.thread = thread_id
    return record


# ---------------------------------------------------------------------------
# Property-based tests – ThreadLogFilter  (Task 1.2)
# ---------------------------------------------------------------------------

class TestThreadLogFilterProperties:
    """Property 3: Thread-based log isolation.

    **Validates: Requirements 3.1, 3.2**
    """

    @settings(max_examples=100)
    @given(
        filter_thread=st.integers(min_value=1),
        record_thread=st.integers(min_value=1),
    )
    def test_accepts_iff_thread_matches(self, filter_thread: int, record_thread: int):
        """# Feature: runner-log-capture, Property 3: Thread-based log isolation

        For any thread IDs, the filter accepts the record iff
        record.thread == filter's thread_id.
        """
        f = ThreadLogFilter(filter_thread)
        record = _make_record(thread_id=record_thread)

        result = f.filter(record)

        assert result == (record_thread == filter_thread)


# ---------------------------------------------------------------------------
# Property-based tests – NovaActLogFilter  (Task 1.3)
# ---------------------------------------------------------------------------

# Strategy: printable logger names that never start with 'nova_act'
_non_nova_act_name = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
).filter(lambda n: not n.startswith("nova_act"))

# Strategy: names that DO start with 'nova_act' (optionally with a suffix)
_nova_act_name = st.builds(
    lambda suffix: f"nova_act{suffix}",
    st.from_regex(r"(\.[a-z_]+)*", fullmatch=True),
)


class TestNovaActLogFilterProperties:
    """Property 4: NovaActLogFilter rejects nova_act hierarchy.

    **Validates: Requirements 5.1**
    """

    @settings(max_examples=100)
    @given(name=_nova_act_name)
    def test_rejects_nova_act_names(self, name: str):
        """# Feature: runner-log-capture, Property 4: NovaActLogFilter rejects nova_act hierarchy

        Any logger name starting with 'nova_act' must be rejected.
        """
        f = NovaActLogFilter()
        record = _make_record(logger_name=name)

        assert f.filter(record) is False

    @settings(max_examples=100)
    @given(name=_non_nova_act_name)
    def test_accepts_non_nova_act_names(self, name: str):
        """# Feature: runner-log-capture, Property 4: NovaActLogFilter rejects nova_act hierarchy

        Any logger name NOT starting with 'nova_act' must be accepted.
        """
        f = NovaActLogFilter()
        record = _make_record(logger_name=name)

        assert f.filter(record) is True


# ---------------------------------------------------------------------------
# Unit tests  (Task 1.4)
# ---------------------------------------------------------------------------

class TestThreadLogFilterUnit:
    """Unit tests for ThreadLogFilter."""

    def test_thread_filter_accepts_matching_thread(self):
        current = threading.get_ident()
        f = ThreadLogFilter(current)
        record = _make_record(thread_id=current)

        assert f.filter(record) is True

    def test_thread_filter_rejects_different_thread(self):
        current = threading.get_ident()
        other = current + 1  # guaranteed different
        f = ThreadLogFilter(current)
        record = _make_record(thread_id=other)

        assert f.filter(record) is False


class TestNovaActLogFilterUnit:
    """Unit tests for NovaActLogFilter."""

    def test_nova_act_filter_rejects_nova_act_logger(self):
        f = NovaActLogFilter()
        record = _make_record(logger_name="nova_act")

        assert f.filter(record) is False

    def test_nova_act_filter_rejects_nova_act_sublogger(self):
        f = NovaActLogFilter()
        record = _make_record(logger_name="nova_act.browser")

        assert f.filter(record) is False

    def test_nova_act_filter_accepts_other_loggers(self):
        f = NovaActLogFilter()

        for name in ("myapp", "urllib3", "root", "botocore", ""):
            record = _make_record(logger_name=name)
            assert f.filter(record) is True, f"Expected acceptance for logger '{name}'"
