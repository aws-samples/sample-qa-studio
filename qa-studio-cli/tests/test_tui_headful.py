"""Tests for the --headful / headful toggle across provisioner, CLI, TUI."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from click.testing import CliRunner

from qa_studio_cli.cli import cli


# ---------------------------------------------------------------------------
# Provisioner + BrowserSelection
# ---------------------------------------------------------------------------


class TestProvisionerHeadless:
    def test_default_none_omits_headless_kwarg(self):
        """None means 'defer to the engine's HEADLESS env-var default'
        — CI behaviour stays unchanged."""
        from qa_studio_cli.runner.browser.local import LocalBrowserProvisioner

        handle = LocalBrowserProvisioner().provision({"starting_url": "x"})
        assert "headless" not in handle.nova_kwargs

    def test_explicit_false_forces_headful(self):
        from qa_studio_cli.runner.browser.local import LocalBrowserProvisioner

        handle = LocalBrowserProvisioner(headless=False).provision(
            {"starting_url": "x"}
        )
        assert handle.nova_kwargs["headless"] is False

    def test_explicit_true_forces_headless(self):
        from qa_studio_cli.runner.browser.local import LocalBrowserProvisioner

        handle = LocalBrowserProvisioner(headless=True).provision(
            {"starting_url": "x"}
        )
        assert handle.nova_kwargs["headless"] is True


class TestBrowserSelectionCarriesHeadless:
    def test_default_is_none(self):
        from qa_studio_cli.runner.browser import BrowserSelection

        assert BrowserSelection().headless is None

    def test_accepts_explicit_false(self):
        from qa_studio_cli.runner.browser import BrowserSelection

        assert BrowserSelection(headless=False).headless is False


# ---------------------------------------------------------------------------
# CLI flag
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_modules():
    mock_runner = MagicMock()
    mock_runner.run_usecase = MagicMock(side_effect=SystemExit(0))
    mock_runner.run_runner = MagicMock(side_effect=SystemExit(0))
    mock_logger = MagicMock()
    mock_logger.setup_logging = MagicMock()
    with patch.dict(
        "sys.modules",
        {
            "qa_studio_cli.runner.main": mock_runner,
            "qa_studio_cli.utils.logger": mock_logger,
        },
    ):
        yield mock_runner


class TestHeadfulFlag:
    def test_default_is_false(self, runner, mock_modules):
        result = runner.invoke(cli, ["run", "--usecase-id", "u1"])
        assert result.exit_code == 0
        assert mock_modules.run_usecase.call_args[1]["headful"] is False

    def test_headful_flag_sets_true(self, runner, mock_modules):
        result = runner.invoke(
            cli, ["run", "--usecase-id", "u1", "--headful"]
        )
        assert result.exit_code == 0
        assert mock_modules.run_usecase.call_args[1]["headful"] is True

    def test_headful_with_non_local_browser_rejected(self, runner):
        result = runner.invoke(
            cli,
            [
                "run", "--usecase-id", "u1",
                "--browser", "cdp-external",
                "--cdp-endpoint-url", "wss://example",
                "--headful",
            ],
        )
        assert result.exit_code != 0
        assert "--browser=local" in result.output


# ---------------------------------------------------------------------------
# TUI form
# ---------------------------------------------------------------------------


pytest.importorskip("textual")

from qa_studio_cli.tui.api import TuiApi  # noqa: E402
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402


def _make_api() -> MagicMock:
    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = []
    api.list_suites.return_value = []
    api.get_usecase.return_value = {
        "name": "Checkout",
        "starting_url": "https://shop.example.com/",
        "executing_region": "us-east-1",
        "model_id": "nova-act-v1.0",
        "test_platform": "web",
    }
    api.get_steps.return_value = []
    api.get_variables.return_value = {}
    api.get_headers.return_value = {}
    api.get_secrets.return_value = []
    api.list_executions.return_value = []
    return api


class TestHeadfulCheckboxOnRunForm:
    def test_default_submit_adds_headful_flag(self):
        """TUI users typically want to see the run — default ON."""
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import (
                    UsecaseDetailScreen,
                )
                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()
                await pilot.press("R")
                await pilot.pause()

                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen
                with patch.object(LiveTailScreen, "on_mount", lambda self: None):
                    await pilot.press("ctrl+s")
                    await pilot.pause()

                assert "--headful" in app.screen._runner.argv

        asyncio.run(_run())

    def test_unticking_headful_drops_the_flag(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import (
                    UsecaseDetailScreen,
                )
                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()
                await pilot.press("R")
                await pilot.pause()

                from textual.widgets import Checkbox
                app.screen.query_one("#headful-toggle", Checkbox).value = False
                await pilot.pause()

                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen
                with patch.object(LiveTailScreen, "on_mount", lambda self: None):
                    await pilot.press("ctrl+s")
                    await pilot.pause()

                assert "--headful" not in app.screen._runner.argv

        asyncio.run(_run())

    def test_remote_run_strips_headful(self):
        """Remote runs happen in the cloud — --headful has no meaning
        locally, so don't pass it even when the checkbox is ticked."""
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import (
                    UsecaseDetailScreen,
                )
                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()
                await pilot.press("R")
                await pilot.pause()

                from textual.widgets import Checkbox
                # Default: headful=True, local_only=True → --headful
                # expected. Untick local-only → --headful gone.
                app.screen.query_one("#local-only-toggle", Checkbox).value = False
                await pilot.pause()

                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen
                with patch.object(LiveTailScreen, "on_mount", lambda self: None):
                    await pilot.press("ctrl+s")
                    await pilot.pause()

                assert "--headful" not in app.screen._runner.argv

        asyncio.run(_run())
