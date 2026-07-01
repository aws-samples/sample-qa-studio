"""Tests for ``Edit in browser`` on :class:`UsecaseDetailScreen`."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("textual")

from qa_studio_cli.models.config import CLIConfig  # noqa: E402
from qa_studio_cli.tui.api import TuiApi  # noqa: E402
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402


def _make_api() -> MagicMock:
    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = []
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


def _config(web_url: str | None = None) -> CLIConfig:
    return CLIConfig(
        api_url="https://api.example.com",
        cognito_domain="https://auth.example.com",
        client_id="cid",
        web_url=web_url,
    )


class TestEditInBrowser:
    """Covers the three branches of ``action_edit``:
    config missing, web_url missing, happy path."""

    def test_e_without_web_url_does_not_open_browser(self):
        """``web_url`` unset → notify + skip. ``webbrowser.open`` must
        not be called so we don't open a garbage URL."""

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

                with (
                    patch(
                        "qa_studio_cli.tui.screens.usecase_detail.load_config",
                        create=True,  # imported inside the action
                        return_value=_config(web_url=None),
                    ),
                    patch("webbrowser.open") as mock_open,
                ):
                    # Fall through the lazy import — easier path: patch
                    # qa_studio_cli.config.manager.load_config since the
                    # action's body imports that module.
                    with patch(
                        "qa_studio_cli.config.manager.load_config",
                        return_value=_config(web_url=None),
                    ):
                        await pilot.press("e")
                        await pilot.pause()

                    mock_open.assert_not_called()

        asyncio.run(_run())

    def test_e_with_web_url_opens_browser_at_correct_path(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import (
                    UsecaseDetailScreen,
                )

                app.push_screen(UsecaseDetailScreen(usecase_id="u-abc"))
                await pilot.pause()
                await pilot.pause()

                with (
                    patch(
                        "qa_studio_cli.config.manager.load_config",
                        return_value=_config(web_url="https://app.example.com"),
                    ),
                    patch("webbrowser.open", return_value=True) as mock_open,
                ):
                    await pilot.press("e")
                    await pilot.pause()

                # Exactly one call with the right URL.
                mock_open.assert_called_once_with(
                    "https://app.example.com/usecase/u-abc"
                )

        asyncio.run(_run())

    def test_e_handles_webbrowser_failure_without_crashing(self):
        """If ``webbrowser.open`` returns ``False`` (headless env,
        broken browser) the app must stay alive and notify instead."""

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

                with (
                    patch(
                        "qa_studio_cli.config.manager.load_config",
                        return_value=_config(web_url="https://app.example.com"),
                    ),
                    patch("webbrowser.open", return_value=False),
                ):
                    await pilot.press("e")
                    await pilot.pause()

                # App still running on the detail screen — no crash.
                assert isinstance(app.screen, UsecaseDetailScreen)

        asyncio.run(_run())
