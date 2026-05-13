"""Smoke tests for the Textual app shell.

Skipped when the ``[tui]`` extra is not installed. The async tests
wrap ``App.run_test`` in ``asyncio.run`` so we avoid an extra
``pytest-asyncio`` dev dependency for this commit.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

pytest.importorskip("textual")

from qa_studio_cli.tui.api import TuiApi  # noqa: E402
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.screens.usecases_list import UsecasesListScreen  # noqa: E402


def _make_app_with_empty_api() -> QAStudioTUIApp:
    """Build the app with a TuiApi that returns an empty usecase list
    so tests don't hit any real HTTP."""
    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = []
    return QAStudioTUIApp(tui_api=api)


class TestAppShell:
    def test_app_has_expected_title(self):
        app = QAStudioTUIApp()
        assert app.TITLE == "QA Studio"
        assert "local-only" in app.SUB_TITLE

    def test_app_binds_quit_and_help(self):
        app = QAStudioTUIApp()
        keys = {binding.key for binding in app.BINDINGS}
        assert "q" in keys
        # Textual normalizes "?" to "question_mark"
        assert "question_mark" in keys

    def test_initial_screen_is_usecases_list(self):
        async def _run():
            app = _make_app_with_empty_api()
            async with app.run_test() as pilot:
                # Allow the worker to finish populating the list
                await pilot.pause()
                assert isinstance(app.screen, UsecasesListScreen)

        asyncio.run(_run())

    def test_q_binding_quits_cleanly(self):
        async def _run():
            app = _make_app_with_empty_api()
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("q")
                await pilot.pause()
            assert app.return_code == 0

        asyncio.run(_run())

    def test_tui_api_attached_on_mount(self):
        async def _run():
            api = MagicMock(spec=TuiApi)
            api.list_usecases.return_value = []
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app.tui_api is api

        asyncio.run(_run())
