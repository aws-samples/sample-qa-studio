"""Unit tests for setup_logging() in src/utils/logger.py."""

import logging

from src.utils.logger import setup_logging
from src.utils.log_filters import NovaActLogFilter


class TestSetupLogging:
    """Tests for setup_logging() modifications."""

    def _cleanup_root_logger(self):
        """Reset root logger to avoid test pollution."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            handler.close()
            root.removeHandler(handler)

    def test_setup_logging_attaches_nova_act_filter(self):
        """Verify NovaActLogFilter is attached to the console StreamHandler."""
        self._cleanup_root_logger()

        setup_logging(verbose=False)

        try:
            root = logging.getLogger()
            stream_handlers = [
                h for h in root.handlers if isinstance(h, logging.StreamHandler)
            ]
            assert len(stream_handlers) == 1

            nova_filters = [
                f for f in stream_handlers[0].filters
                if isinstance(f, NovaActLogFilter)
            ]
            assert len(nova_filters) == 1
        finally:
            self._cleanup_root_logger()

    def test_setup_logging_sets_root_level_debug(self):
        """Verify root logger level is set to DEBUG regardless of verbose flag."""
        self._cleanup_root_logger()

        setup_logging(verbose=False)

        try:
            root = logging.getLogger()
            assert root.level == logging.DEBUG
        finally:
            self._cleanup_root_logger()

    def test_setup_logging_verbose_sets_handler_debug(self):
        """Verify console handler level is DEBUG when verbose=True."""
        self._cleanup_root_logger()

        setup_logging(verbose=True)

        try:
            root = logging.getLogger()
            stream_handlers = [
                h for h in root.handlers if isinstance(h, logging.StreamHandler)
            ]
            assert stream_handlers[0].level == logging.DEBUG
        finally:
            self._cleanup_root_logger()

    def test_setup_logging_non_verbose_sets_handler_info(self):
        """Verify console handler level is INFO when verbose=False."""
        self._cleanup_root_logger()

        setup_logging(verbose=False)

        try:
            root = logging.getLogger()
            stream_handlers = [
                h for h in root.handlers if isinstance(h, logging.StreamHandler)
            ]
            assert stream_handlers[0].level == logging.INFO
        finally:
            self._cleanup_root_logger()
