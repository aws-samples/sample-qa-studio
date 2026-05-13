"""Tests for ``qa-studio tui`` — the Click entry point.

Covers the two preconditions the command checks before starting
Textual: ``[tui]`` extra installed, and a valid token resolvable.
The Textual app itself is smoke-tested separately in
``test_tui_app.py``.
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from qa_studio_cli.cli import cli
from qa_studio_cli.models.errors import AuthError


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def _config_present():
    """Fixture: pretend a config file exists for the _require_config gate."""
    with patch("qa_studio_cli.commands.tui.config_exists", return_value=True):
        yield


class TestTuiConfigGate:
    """The command must fail before Textual import when no config exists."""

    def test_missing_config_prints_hint_and_exits(self, runner):
        with patch("qa_studio_cli.commands.tui.config_exists", return_value=False):
            result = runner.invoke(cli, ["tui"])
        assert result.exit_code != 0
        assert "qa-studio configure" in result.output


class TestTuiTextualImportGate:
    """If the [tui] extra isn't installed we show a pip hint, not a traceback."""

    def test_missing_textual_prints_install_hint(self, runner, _config_present):
        # Forcing the lazy import to fail: inject None into sys.modules so the
        # inner ``from qa_studio_cli.tui.app import QAStudioTUIApp`` raises.
        with patch.dict("sys.modules", {"qa_studio_cli.tui.app": None}):
            result = runner.invoke(cli, ["tui"])
        assert result.exit_code != 0
        assert "pip install qa-studio[tui]" in result.output


class TestTuiAuthGate:
    """Authentication is checked before the Textual app starts."""

    def test_auth_error_prints_login_hint(self, runner, _config_present):
        fake_app = MagicMock()
        with (
            patch.dict(
                "sys.modules",
                {"qa_studio_cli.tui.app": MagicMock(QAStudioTUIApp=fake_app)},
            ),
            patch(
                "qa_studio_cli.commands.tui.get_valid_token",
                side_effect=AuthError("Token expired"),
            ),
        ):
            result = runner.invoke(cli, ["tui"])
        assert result.exit_code != 0
        assert "Authentication required" in result.output
        assert "qa-studio login" in result.output
        # App must NOT be constructed when auth fails
        fake_app.assert_not_called()


class TestTuiHappyPath:
    """With both gates green, the Textual app is constructed and run."""

    def test_starts_textual_app_when_all_gates_pass(self, runner, _config_present):
        fake_instance = MagicMock()
        fake_app_class = MagicMock(return_value=fake_instance)
        with (
            patch.dict(
                "sys.modules",
                {"qa_studio_cli.tui.app": MagicMock(QAStudioTUIApp=fake_app_class)},
            ),
            patch(
                "qa_studio_cli.commands.tui.get_valid_token",
                return_value="valid-token",
            ),
        ):
            result = runner.invoke(cli, ["tui"])

        # App constructed exactly once, .run() called exactly once.
        fake_app_class.assert_called_once_with()
        fake_instance.run.assert_called_once_with()
        assert result.exit_code == 0


class TestTuiRegistration:
    """The command is discoverable via ``qa-studio --help``."""

    def test_tui_listed_in_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "tui" in result.output
