"""Tests for logger setup utility."""

import logging

from qa_studio_cli.utils.logger import setup_logging


class TestSetupLogging:
    """Tests for setup_logging."""

    def test_verbose_sets_debug_level(self):
        setup_logging(verbose=True)
        handler = logging.getLogger().handlers[-1]
        assert handler.level == logging.DEBUG

    def test_non_verbose_sets_info_level(self):
        setup_logging(verbose=False)
        handler = logging.getLogger().handlers[-1]
        assert handler.level == logging.INFO

    def test_clears_existing_handlers(self):
        root = logging.getLogger()
        root.addHandler(logging.StreamHandler())
        count_before = len(root.handlers)
        setup_logging(verbose=False)
        # setup_logging clears handlers and adds exactly one
        assert len(root.handlers) == 1

    def test_adds_nova_act_filter(self):
        setup_logging(verbose=False)
        handler = logging.getLogger().handlers[-1]
        filter_names = [type(f).__name__ for f in handler.filters]
        assert "NovaActLogFilter" in filter_names
