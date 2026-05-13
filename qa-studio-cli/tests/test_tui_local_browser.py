"""Tests for the local-browser selection feature."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from click.testing import CliRunner

from qa_studio_cli.cli import cli


# ---------------------------------------------------------------------------
# Registry + provisioner
# ---------------------------------------------------------------------------


class TestLocalBrowserRegistry:
    def test_registry_has_expected_default_entries(self):
        from qa_studio_cli.runner.browser.local import (
            LOCAL_BROWSER_OPTIONS,
            list_local_browsers,
        )

        keys = list_local_browsers()
        # Chromium must be first (default) and present.
        assert keys[0] == "chromium"
        assert "chrome" in keys
        assert "chrome-profile" in keys

        # Every entry carries a non-empty label + description.
        for key in keys:
            opt = LOCAL_BROWSER_OPTIONS[key]
            assert opt.label
            assert opt.description

    def test_provisioner_default_is_chromium(self):
        from qa_studio_cli.runner.browser.local import LocalBrowserProvisioner

        provisioner = LocalBrowserProvisioner()
        assert provisioner.browser_key == "chromium"

    def test_provisioner_rejects_unknown_key(self):
        from qa_studio_cli.runner.browser.local import LocalBrowserProvisioner

        with pytest.raises(ValueError, match="Unknown local browser"):
            LocalBrowserProvisioner(browser_key="firefox")

    def test_chromium_nova_kwargs_stay_clean(self):
        from qa_studio_cli.runner.browser.local import LocalBrowserProvisioner

        handle = LocalBrowserProvisioner().provision({"starting_url": "x"})
        # Default leaves nova_kwargs as just the starting_page — no
        # chrome_channel, no use_default_chrome_browser.
        assert handle.nova_kwargs == {"starting_page": "x"}

    def test_chrome_sets_chrome_channel(self):
        from qa_studio_cli.runner.browser.local import LocalBrowserProvisioner

        handle = LocalBrowserProvisioner(browser_key="chrome").provision(
            {"starting_url": "x"}
        )
        assert handle.nova_kwargs.get("chrome_channel") == "chrome"

    def test_chrome_profile_sets_use_default_chrome_browser(self, tmp_path):
        """On macOS the provisioner copies the profile to a working
        directory and points NovaAct at that copy (NovaAct refuses
        the system default dir for CDP)."""
        from qa_studio_cli.runner.browser import local as local_mod

        src = tmp_path / "system_chrome"
        src.mkdir()
        (src / "Local State").write_text("{}")
        (src / "Default").mkdir()

        dst = tmp_path / "copy"

        with (
            patch.object(local_mod.sys, "platform", "darwin"),
            patch.object(
                local_mod, "default_chrome_user_data_dir", return_value=src
            ),
            patch.object(local_mod, "CHROME_PROFILE_COPY_DIR", dst),
        ):
            handle = local_mod.LocalBrowserProvisioner(
                browser_key="chrome-profile"
            ).provision({"starting_url": "x"})

        assert handle.nova_kwargs["use_default_chrome_browser"] is True
        assert handle.nova_kwargs["clone_user_data_dir"] is False
        # Points at the copy, NOT the original.
        assert handle.nova_kwargs["user_data_dir"] == str(dst)
        assert dst.exists()
        assert (dst / "Local State").exists()

    def test_chrome_profile_reuses_existing_copy(self, tmp_path):
        """Subsequent runs skip the copy step — it's slow and Chrome's
        own state accumulates inside the copy across runs."""
        from qa_studio_cli.runner.browser import local as local_mod

        src = tmp_path / "system_chrome"
        src.mkdir()
        (src / "Local State").write_text("{}")

        dst = tmp_path / "copy"
        dst.mkdir()
        sentinel = dst / "Already-there"
        sentinel.write_text("existing")

        with (
            patch.object(local_mod.sys, "platform", "darwin"),
            patch.object(
                local_mod, "default_chrome_user_data_dir", return_value=src
            ),
            patch.object(local_mod, "CHROME_PROFILE_COPY_DIR", dst),
        ):
            local_mod.LocalBrowserProvisioner(
                browser_key="chrome-profile"
            ).provision({"starting_url": "x"})

        # Sentinel file still there — copy was not overwritten.
        assert sentinel.exists()

    def test_chrome_profile_rejects_non_macos(self, tmp_path):
        from qa_studio_cli.runner.browser import local as local_mod

        with patch.object(local_mod.sys, "platform", "linux"):
            with pytest.raises(RuntimeError, match="macOS-only"):
                local_mod.LocalBrowserProvisioner(
                    browser_key="chrome-profile"
                ).provision({"starting_url": "x"})

    def test_chrome_profile_missing_source_raises(self, tmp_path):
        from qa_studio_cli.runner.browser import local as local_mod

        with (
            patch.object(local_mod.sys, "platform", "darwin"),
            patch.object(
                local_mod,
                "default_chrome_user_data_dir",
                return_value=tmp_path / "does-not-exist",
            ),
            patch.object(local_mod, "CHROME_PROFILE_COPY_DIR", tmp_path / "dst"),
        ):
            with pytest.raises(RuntimeError, match="Launch Chrome"):
                local_mod.LocalBrowserProvisioner(
                    browser_key="chrome-profile"
                ).provision({"starting_url": "x"})

    def test_default_chrome_user_data_dir_detects_macos(self):
        from qa_studio_cli.runner.browser import local as local_mod

        with patch.object(local_mod.sys, "platform", "darwin"):
            path = local_mod.default_chrome_user_data_dir()
        assert path is not None
        assert "Google/Chrome" in str(path).replace("\\", "/")

    def test_default_chrome_user_data_dir_detects_linux(self):
        from qa_studio_cli.runner.browser import local as local_mod

        with patch.object(local_mod.sys, "platform", "linux"):
            path = local_mod.default_chrome_user_data_dir()
        assert path is not None
        assert "google-chrome" in str(path)

    def test_default_chrome_user_data_dir_detects_windows(self):
        from qa_studio_cli.runner.browser import local as local_mod

        with (
            patch.object(local_mod.sys, "platform", "win32"),
            patch.dict(
                local_mod.os.environ,
                {"LOCALAPPDATA": r"C:\Users\dev\AppData\Local"},
            ),
        ):
            path = local_mod.default_chrome_user_data_dir()
        assert path is not None
        assert "User Data" in str(path)

    def test_unknown_platform_raises_clear_error_on_provision(self):
        from qa_studio_cli.runner.browser import local as local_mod

        with patch.object(local_mod.sys, "platform", "plan9"):
            with pytest.raises(RuntimeError, match="macOS-only"):
                local_mod.LocalBrowserProvisioner(
                    browser_key="chrome-profile"
                ).provision({"starting_url": "x"})


# ---------------------------------------------------------------------------
# BrowserSelection carries the choice
# ---------------------------------------------------------------------------


class TestBrowserSelectionCarriesLocalChoice:
    def test_default_is_chromium(self):
        from qa_studio_cli.runner.browser import BrowserSelection

        selection = BrowserSelection()
        assert selection.local_browser == "chromium"

    def test_accepts_chrome_profile(self):
        from qa_studio_cli.runner.browser import BrowserSelection

        selection = BrowserSelection(local_browser="chrome-profile")
        assert selection.local_browser == "chrome-profile"


# ---------------------------------------------------------------------------
# CLI flag wiring
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


class TestLocalBrowserFlag:
    def test_default_is_chromium(self, runner, mock_modules):
        result = runner.invoke(cli, ["run", "--usecase-id", "u1"])
        assert result.exit_code == 0
        kwargs = mock_modules.run_usecase.call_args[1]
        assert kwargs["local_browser"] == "chromium"

    def test_accepts_chrome(self, runner, mock_modules):
        result = runner.invoke(
            cli,
            ["run", "--usecase-id", "u1", "--local-browser", "chrome"],
        )
        assert result.exit_code == 0
        assert mock_modules.run_usecase.call_args[1]["local_browser"] == "chrome"

    def test_accepts_chrome_profile(self, runner, mock_modules):
        result = runner.invoke(
            cli,
            ["run", "--usecase-id", "u1", "--local-browser", "chrome-profile"],
        )
        assert result.exit_code == 0
        assert (
            mock_modules.run_usecase.call_args[1]["local_browser"]
            == "chrome-profile"
        )

    def test_rejects_unknown_choice(self, runner):
        result = runner.invoke(
            cli,
            ["run", "--usecase-id", "u1", "--local-browser", "firefox"],
        )
        assert result.exit_code != 0
        # Click's error message for invalid choice mentions the value.
        assert "firefox" in (result.output + (result.stderr or ""))

    def test_rejected_with_non_local_browser_mode(self, runner):
        result = runner.invoke(
            cli,
            [
                "run", "--usecase-id", "u1",
                "--browser", "cdp-external",
                "--cdp-endpoint-url", "wss://example",
                "--local-browser", "chrome",
            ],
        )
        assert result.exit_code != 0
        assert "--browser=local" in result.output


# ---------------------------------------------------------------------------
# TUI form wiring
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


class TestBrowserSelectOnRunForm:
    def test_default_submit_omits_local_browser(self):
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

                assert "--local-browser" not in app.screen._runner.argv

        asyncio.run(_run())

    def test_chrome_profile_selection_adds_flag(self):
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

                from textual.widgets import Select
                from qa_studio_cli.tui.screens.run_form import RunFormScreen
                assert isinstance(app.screen, RunFormScreen)
                select = app.screen.query_one("#browser-select", Select)
                select.value = "chrome-profile"
                await pilot.pause()

                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen
                with patch.object(LiveTailScreen, "on_mount", lambda self: None):
                    await pilot.press("ctrl+s")
                    await pilot.pause()

                argv = app.screen._runner.argv
                assert "--local-browser" in argv
                assert argv[argv.index("--local-browser") + 1] == "chrome-profile"

        asyncio.run(_run())

    def test_remote_run_skips_local_browser_even_when_selected(self):
        """Unticking 'Local only' makes the browser choice moot — the
        cloud runs the browser. Avoid surprising the user by smuggling
        a flag the remote path would reject."""
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

                from textual.widgets import Checkbox, Select
                app.screen.query_one("#browser-select", Select).value = "chrome"
                app.screen.query_one("#local-only-toggle", Checkbox).value = False
                await pilot.pause()

                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen
                with patch.object(LiveTailScreen, "on_mount", lambda self: None):
                    await pilot.press("ctrl+s")
                    await pilot.pause()

                assert "--local-browser" not in app.screen._runner.argv

        asyncio.run(_run())
