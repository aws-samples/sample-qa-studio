"""Tests for SuiteLogCapture.

Includes property-based tests (hypothesis) and unit tests.
Tasks 2.2, 2.3, 2.4.
"""

import logging
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings, strategies as st

from src.execution.suite_log_capture import SuiteLogCapture


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Logger names: printable, non-empty, no newlines (newlines break line-based parsing)
_logger_name = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P"), blacklist_characters="\n\r"),
    min_size=1,
    max_size=50,
)

# Log messages: printable, non-empty, no newlines
_log_message = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), blacklist_characters="\n\r"),
    min_size=1,
    max_size=100,
)

_log_level = st.sampled_from([logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL])


# ---------------------------------------------------------------------------
# Property-based tests – Suite log captures all log records (Task 2.2)
# ---------------------------------------------------------------------------

class TestSuiteLogCaptureAllRecords:
    """Property 1: Suite log captures all log records.

    **Validates: Requirements 1.2, 3.3, 5.2**
    """

    @settings(max_examples=100)
    @given(
        records=st.lists(
            st.tuples(_logger_name, _log_message, _log_level),
            min_size=1,
            max_size=20,
        ),
    )
    def test_all_log_records_captured(self, records):
        """# Feature: runner-log-capture, Property 1: Suite log captures all log records

        For any set of logger names and messages emitted while the suite handler
        is active, every record must appear in the suite log file.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            suite_id = "prop-test-suite"
            capture = SuiteLogCapture(suite_id)
            capture.log_dir = Path(tmpdir) / suite_id
            capture.log_path = capture.log_dir / "suite_logs.txt"

            root_logger = logging.getLogger()
            original_level = root_logger.level
            root_logger.setLevel(logging.DEBUG)

            path = capture.start()
            assert path is not None

            try:
                for logger_name, message, level in records:
                    test_logger = logging.getLogger(logger_name)
                    test_logger.log(level, message)

                capture.stop()

                content = capture.log_path.read_text()
                for logger_name, message, _level in records:
                    assert message in content, (
                        f"Message '{message}' from logger '{logger_name}' not found in suite log"
                    )
            finally:
                if capture._handler:
                    logging.getLogger().removeHandler(capture._handler)
                    capture._handler.close()
                    capture._handler = None
                root_logger.setLevel(original_level)


# ---------------------------------------------------------------------------
# Property-based tests – Suite log format consistency (Task 2.3)
# ---------------------------------------------------------------------------

# Pattern: <timestamp> - <logger_name> - <LEVEL> - <message>
# Timestamp format from %(asctime)s: e.g. "2024-01-15 10:30:00,123"
_LOG_LINE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} - .+ - (DEBUG|INFO|WARNING|ERROR|CRITICAL) - .+$"
)


class TestSuiteLogFormatConsistency:
    """Property 2: Suite log format consistency.

    **Validates: Requirements 1.3**
    """

    @settings(max_examples=100)
    @given(
        records=st.lists(
            st.tuples(_logger_name, _log_message, _log_level),
            min_size=1,
            max_size=10,
        ),
    )
    def test_log_format_matches_pattern(self, records):
        """# Feature: runner-log-capture, Property 2: Suite log format consistency

        For any log record written to the suite log file, each line must match
        the pattern: <timestamp> - <logger_name> - <LEVEL> - <message>.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            suite_id = "format-test-suite"
            capture = SuiteLogCapture(suite_id)
            capture.log_dir = Path(tmpdir) / suite_id
            capture.log_path = capture.log_dir / "suite_logs.txt"

            root_logger = logging.getLogger()
            original_level = root_logger.level
            root_logger.setLevel(logging.DEBUG)

            path = capture.start()
            assert path is not None

            try:
                for logger_name, message, level in records:
                    test_logger = logging.getLogger(logger_name)
                    test_logger.log(level, message)

                capture.stop()

                content = capture.log_path.read_text().strip()
                lines = content.split("\n")

                assert len(lines) >= len(records)

                for line in lines:
                    assert _LOG_LINE_PATTERN.match(line), (
                        f"Line does not match expected format: '{line}'"
                    )
            finally:
                if capture._handler:
                    logging.getLogger().removeHandler(capture._handler)
                    capture._handler.close()
                    capture._handler = None
                root_logger.setLevel(original_level)


# ---------------------------------------------------------------------------
# Unit tests (Task 2.4)
# ---------------------------------------------------------------------------

class TestSuiteLogCaptureUnit:
    """Unit tests for SuiteLogCapture."""

    def test_start_creates_log_file_and_handler(self, tmp_path):
        """Verify start() creates the log file and adds a handler to root logger."""
        capture = SuiteLogCapture("unit-test-suite")
        capture.log_dir = tmp_path / "unit-test-suite"
        capture.log_path = capture.log_dir / "suite_logs.txt"

        root_logger = logging.getLogger()
        initial_count = len(root_logger.handlers)

        path = capture.start()

        try:
            assert path is not None
            assert path == capture.log_path
            assert capture.log_dir.exists()
            assert len(root_logger.handlers) == initial_count + 1
            assert capture._handler in root_logger.handlers
        finally:
            capture.stop()

    def test_stop_removes_handler_and_flushes(self, tmp_path):
        """Verify stop() removes the handler from root logger and flushes content."""
        capture = SuiteLogCapture("stop-test-suite")
        capture.log_dir = tmp_path / "stop-test-suite"
        capture.log_path = capture.log_dir / "suite_logs.txt"

        root_logger = logging.getLogger()
        original_level = root_logger.level
        root_logger.setLevel(logging.DEBUG)

        capture.start()
        handler = capture._handler
        assert handler in root_logger.handlers

        # Emit a log so the file has content
        logging.getLogger("test").info("flush check")

        result = capture.stop()
        root_logger.setLevel(original_level)

        assert handler not in root_logger.handlers
        assert capture._handler is None
        assert result is not None
        assert "flush check" in capture.log_path.read_text()

    def test_start_returns_none_on_directory_failure(self, tmp_path):
        """Mock Path.mkdir to raise OSError, verify start() returns None."""
        capture = SuiteLogCapture("fail-test-suite")
        capture.log_dir = tmp_path / "fail-test-suite"
        capture.log_path = capture.log_dir / "suite_logs.txt"

        with patch.object(type(capture.log_dir), "mkdir", side_effect=OSError("disk full")):
            result = capture.start()

        assert result is None
        assert capture._handler is None

    def test_log_path_uses_suite_execution_id(self):
        """Verify the log path structure uses suite_execution_id correctly."""
        suite_id = "my-suite-exec-42"
        capture = SuiteLogCapture(suite_id)

        expected_dir = Path.home() / ".ci_runner" / suite_id
        expected_path = expected_dir / "suite_logs.txt"

        assert capture.log_dir == expected_dir
        assert capture.log_path == expected_path
        assert capture.suite_execution_id == suite_id
