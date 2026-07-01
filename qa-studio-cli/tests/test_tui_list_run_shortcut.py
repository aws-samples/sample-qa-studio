"""Tests for the ``R`` (shift+r) Run shortcut on the list screens.

Mirrors the behaviour of the ``R`` binding on the detail screens but
from the top-level list — user can trigger a run without first
opening the detail page. Covers:

* Happy path — R with a highlighted row fetches the sub-resources
  and pushes the matching Run form.
* No-row guard — R on an empty table emits a warning notification
  and never pushes a form.
* Fetch failure — any API error during prep surfaces as an error
  notification; the user stays on the list.
* Status-hint text advertises the new shortcut so it's discoverable
  without reading release notes.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

pytest.importorskip("textual")

from qa_studio_cli.tui.api import (  # noqa: E402
    SuiteListItem,
    TuiApi,
    UsecaseListItem,
)
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.screens.suites_list import SuitesListScreen  # noqa: E402
from qa_studio_cli.tui.screens.usecases_list import (  # noqa: E402
    UsecasesListScreen,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_usecase_api(
    items: list[UsecaseListItem] | None = None, *, fail_prep: bool = False
) -> MagicMock:
    """Build a TuiApi double for the usecases list + prep flow.

    The ``fail_prep`` flag flips the first prep call
    (``get_usecase``) to raise so we can exercise the error path
    without disturbing the initial list-render path.
    """
    api = MagicMock(spec=TuiApi)
    # ``items is None`` check — not ``items or default`` — because an
    # explicitly empty list is a legitimate test case (empty-list
    # screen) that the shorter expression would silently replace with
    # the fallback.
    if items is None:
        items = [
            UsecaseListItem("u-1", "Login", "web", "us-east-1"),
            UsecaseListItem("u-2", "Checkout", "web", "us-east-1"),
        ]
    api.list_usecases.return_value = items
    api.list_suites.return_value = []

    if fail_prep:
        api.get_usecase.side_effect = RuntimeError("boom")
    else:
        api.get_usecase.return_value = {
            "name": "Login",
            "starting_url": "https://example.com/login",
            "test_platform": "web",
        }
    api.get_variables.return_value = {"email": "x@example.com"}
    api.get_headers.return_value = {}
    api.get_secrets.return_value = []
    return api


def _make_suite_api(
    items: list[SuiteListItem] | None = None, *, fail_prep: bool = False
) -> MagicMock:
    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = []
    if items is None:
        items = [
            SuiteListItem("s-1", "Smoke", 3, "happy paths"),
            SuiteListItem("s-2", "Regression", 42, "full"),
        ]
    api.list_suites.return_value = items
    if fail_prep:
        api.get_suite.side_effect = RuntimeError("boom")
    else:
        api.get_suite.return_value = {
            "name": "Smoke",
            "total_usecases": 3,
        }
    return api


# ---------------------------------------------------------------------------
# UsecasesListScreen
# ---------------------------------------------------------------------------


class TestUsecasesListRunShortcut:
    def test_R_on_highlighted_row_pushes_run_form(self):
        async def _run():
            api = _make_usecase_api()
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()

                assert isinstance(app.screen, UsecasesListScreen)

                await pilot.press("R")
                # One pause schedules the worker; another pause lets
                # the call_from_thread finish and push the screen.
                await pilot.pause()
                await pilot.pause()

                from qa_studio_cli.tui.screens.run_form import RunFormScreen

                assert isinstance(app.screen, RunFormScreen)
                # The four sub-resources must have been requested for
                # the highlighted (first) row.
                api.get_usecase.assert_called_once_with("u-1")
                api.get_variables.assert_called_once_with("u-1")
                api.get_headers.assert_called_once_with("u-1")
                api.get_secrets.assert_called_once_with("u-1")

        asyncio.run(_run())

    def test_R_on_empty_list_is_a_noop(self):
        """No rows → notify and stay on the list; never call the prep API."""

        async def _run():
            api = _make_usecase_api(items=[])
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()

                await pilot.press("R")
                await pilot.pause()
                await pilot.pause()

                # Still on the list.
                assert isinstance(app.screen, UsecasesListScreen)
                # Never reached the prep pipeline.
                api.get_usecase.assert_not_called()

        asyncio.run(_run())

    def test_R_with_failing_prep_keeps_user_on_list(self):
        async def _run():
            api = _make_usecase_api(fail_prep=True)
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()

                await pilot.press("R")
                await pilot.pause()
                await pilot.pause()

                # The form was never pushed — API error surfaces as a
                # notification and the user remains on the list.
                assert isinstance(app.screen, UsecasesListScreen)

        asyncio.run(_run())

    def test_status_hint_advertises_R(self):
        async def _run():
            api = _make_usecase_api()
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import Static

                status = app.screen.query_one("#usecases-status", Static)
                text = str(status.renderable)
                assert "R to run" in text

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# SuitesListScreen
# ---------------------------------------------------------------------------


class TestSuitesListRunShortcut:
    def test_R_on_highlighted_row_pushes_suite_run_form(self):
        async def _run():
            api = _make_suite_api()
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                # Jump to the Suites section via the global "2" binding.
                await pilot.press("2")
                await pilot.pause()
                await pilot.pause()

                assert isinstance(app.screen, SuitesListScreen)

                await pilot.press("R")
                await pilot.pause()
                await pilot.pause()

                from qa_studio_cli.tui.screens.suite_run_form import (
                    SuiteRunFormScreen,
                )

                assert isinstance(app.screen, SuiteRunFormScreen)
                api.get_suite.assert_called_once_with("s-1")

        asyncio.run(_run())

    def test_R_on_empty_list_is_a_noop(self):
        async def _run():
            api = _make_suite_api(items=[])
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("2")
                await pilot.pause()
                await pilot.pause()

                await pilot.press("R")
                await pilot.pause()
                await pilot.pause()

                assert isinstance(app.screen, SuitesListScreen)
                api.get_suite.assert_not_called()

        asyncio.run(_run())

    def test_R_with_failing_prep_keeps_user_on_list(self):
        async def _run():
            api = _make_suite_api(fail_prep=True)
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("2")
                await pilot.pause()
                await pilot.pause()

                await pilot.press("R")
                await pilot.pause()
                await pilot.pause()

                assert isinstance(app.screen, SuitesListScreen)

        asyncio.run(_run())

    def test_status_hint_advertises_R(self):
        async def _run():
            api = _make_suite_api()
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("2")
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import Static

                status = app.screen.query_one("#suites-status", Static)
                text = str(status.renderable)
                assert "R to run" in text

        asyncio.run(_run())
