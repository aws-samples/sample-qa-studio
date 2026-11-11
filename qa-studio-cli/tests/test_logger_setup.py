"""Tests for logger setup utility."""

import logging

import pytest

from qa_studio_cli.utils.logger import configure_nova_act_logging, setup_logging


@pytest.fixture(autouse=True)
def _no_user_nova_act_level(monkeypatch):
    """Default: the user has not exported NOVA_ACT_LOG_LEVEL."""
    monkeypatch.delenv("NOVA_ACT_LOG_LEVEL", raising=False)


class TestSetupLogging:
    """Tests for setup_logging."""

    def test_verbose_sets_debug_level(self):
        setup_logging(verbose=True)
        handler = logging.getLogger().handlers[-1]
        assert handler.level == logging.DEBUG

    def test_non_verbose_sets_warning_level(self):
        setup_logging(verbose=False)
        handler = logging.getLogger().handlers[-1]
        assert handler.level == logging.WARNING

    def test_root_logger_stays_at_debug(self):
        setup_logging(verbose=False)
        assert logging.getLogger().level == logging.DEBUG

    def test_clears_existing_handlers(self):
        root = logging.getLogger()
        root.addHandler(logging.StreamHandler())
        setup_logging(verbose=False)
        # setup_logging clears handlers and adds exactly one
        assert len(root.handlers) == 1

    def test_adds_nova_act_and_safety_filters(self):
        setup_logging(verbose=False)
        handler = logging.getLogger().handlers[-1]
        filter_names = [type(f).__name__ for f in handler.filters]
        assert "NovaActLogFilter" in filter_names
        assert "NoisyLibraryFilter" in filter_names
        assert "SecretRedactionFilter" in filter_names

    def test_console_format_matches_progress_lines(self):
        setup_logging(verbose=True)
        handler = logging.getLogger().handlers[-1]
        record = logging.LogRecord(
            "qa", logging.WARNING, __file__, 1, "Failed to update step status", None, None,
        )
        record.created = 1_700_000_000.0
        rendered = handler.format(record)
        assert rendered.endswith("] WARNING Failed to update step status")
        assert rendered.startswith("[")
        # [HH:MM:SS] — no date in the console timestamp
        assert len(rendered.split("]")[0]) == len("[HH:MM:SS")

    def test_setup_logging_configures_nova_act_quiet(self, monkeypatch):
        import os
        setup_logging(verbose=False)
        assert os.environ["NOVA_ACT_LOG_LEVEL"] == str(logging.WARNING)

    def test_setup_logging_configures_nova_act_verbose(self, monkeypatch):
        import os
        setup_logging(verbose=True)
        assert os.environ["NOVA_ACT_LOG_LEVEL"] == str(logging.INFO)


class TestConfigureNovaActLogging:
    """Nova Act's loggers bypass our root handler; the env var + explicit level tame them."""

    def test_quiet_sets_env_var_to_warning_when_absent(self):
        import os
        configure_nova_act_logging(verbose=False)
        assert os.environ["NOVA_ACT_LOG_LEVEL"] == str(logging.WARNING)

    def test_verbose_sets_env_var_to_info_when_absent(self):
        import os
        configure_nova_act_logging(verbose=True)
        assert os.environ["NOVA_ACT_LOG_LEVEL"] == str(logging.INFO)

    def test_user_set_env_var_is_respected(self, monkeypatch):
        import os
        monkeypatch.setenv("NOVA_ACT_LOG_LEVEL", "10")
        configure_nova_act_logging(verbose=False)
        assert os.environ["NOVA_ACT_LOG_LEVEL"] == "10"

    def test_existing_nova_act_loggers_are_lowered_when_quiet(self):
        module_logger = logging.getLogger("nova_act.foo")
        module_logger.setLevel(logging.INFO)
        top_logger = logging.getLogger("nova_act")
        top_logger.setLevel(logging.INFO)
        configure_nova_act_logging(verbose=False)
        assert module_logger.level == logging.WARNING
        assert top_logger.level == logging.WARNING

    def test_existing_nova_act_loggers_are_info_when_verbose(self):
        module_logger = logging.getLogger("nova_act.trace")
        module_logger.setLevel(logging.WARNING)
        configure_nova_act_logging(verbose=True)
        assert module_logger.level == logging.INFO

    def test_unrelated_loggers_untouched(self):
        other = logging.getLogger("nova_actor.not_nova")
        other.setLevel(logging.INFO)
        mine = logging.getLogger("qa_studio_cli.runner.engine")
        mine.setLevel(logging.DEBUG)
        configure_nova_act_logging(verbose=False)
        assert other.level == logging.INFO
        assert mine.level == logging.DEBUG

    def test_placeholder_entries_are_skipped(self):
        # Creating "nova_act.a.b" leaves a PlaceHolder for "nova_act.a" in loggerDict.
        logging.getLogger("nova_act.a.b")
        assert isinstance(logging.Logger.manager.loggerDict.get("nova_act.a"), logging.PlaceHolder)
        configure_nova_act_logging(verbose=False)  # must not raise
