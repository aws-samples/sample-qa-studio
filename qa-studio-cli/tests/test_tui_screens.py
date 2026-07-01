"""Textual screen tests for the Usecases list + detail screens.

Skipped if the ``[tui]`` extra is not installed.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

pytest.importorskip("textual")

from qa_studio_cli.tui.api import TuiApi, UsecaseListItem, SuiteListItem, ExecutionListItem  # noqa: E402
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen  # noqa: E402
from qa_studio_cli.tui.screens.usecases_list import UsecasesListScreen  # noqa: E402


def _make_api(items: list[UsecaseListItem] | None = None) -> MagicMock:
    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = items or []
    api.get_usecase.return_value = {
        "name": "Checkout",
        "description": "Verifies the end-to-end checkout flow",
        "starting_url": "https://shop.example.com/checkout",
        "executing_region": "us-east-1",
        "model_id": "nova-act-v1.0",
        "test_platform": "web",
        "active": True,
        "tags": ["critical", "smoke"],
        "created_at": "2024-01-10T10:00:00Z",
        "updated_at": "2024-02-20T15:30:00Z",
        "created_by": "alice",
    }
    api.get_steps.return_value = [
        {"sort": 1, "step_type": "navigate", "instruction": "Go to /"},
        {"sort": 2, "step_type": "assert", "instruction": "See title"},
    ]
    api.get_variables.return_value = {"email": "x@example.com"}
    api.get_headers.return_value = {"X-Test": "1"}
    api.get_secrets.return_value = [{"key": "admin_pw", "value": ""}]
    api.list_executions.return_value = []
    return api


class TestUsecasesListScreen:
    def test_renders_rows_for_each_usecase(self):
        async def _run():
            api = _make_api(
                [
                    UsecaseListItem("u-1", "Login", "web", "us-east-1"),
                    UsecaseListItem("u-2", "Checkout", "web", "us-east-1"),
                ]
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                # Wait an extra tick for the worker thread to populate
                # the table.
                await pilot.pause()
                screen = app.screen
                assert isinstance(screen, UsecasesListScreen)
                from textual.widgets import DataTable

                table = screen.query_one(DataTable)
                assert table.row_count == 2

        asyncio.run(_run())

    def test_empty_list_shows_friendly_message(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api([]))
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                from textual.widgets import Static

                status = app.screen.query_one("#usecases-status", Static)
                assert "No use cases" in str(status.renderable)

        asyncio.run(_run())

    def test_api_error_surfaces_in_status(self):
        async def _run():
            api = MagicMock(spec=TuiApi)
            api.list_usecases.side_effect = RuntimeError("boom")
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                from textual.widgets import Static

                status = app.screen.query_one("#usecases-status", Static)
                assert "Failed to load" in str(status.renderable)

        asyncio.run(_run())


class TestUsecaseDetailScreen:
    def test_renders_metadata_and_tab_rows(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                screen = app.screen
                assert isinstance(screen, UsecaseDetailScreen)

                from textual.widgets import DataTable, Static

                meta = screen.query_one("#detail-metadata", Static)
                rendered = str(meta.renderable)
                assert "Checkout" in rendered
                assert "shop.example.com" in rendered

                assert screen.query_one("#steps-table", DataTable).row_count == 2
                assert screen.query_one("#variables-table", DataTable).row_count == 1
                assert screen.query_one("#headers-table", DataTable).row_count == 1
                assert screen.query_one("#secrets-table", DataTable).row_count == 1

        asyncio.run(_run())

    def test_metadata_shows_all_expanded_fields(self):
        """Regression: the expanded header must include description,
        tags, active status, creator, and timestamps."""
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import Static
                rendered = str(
                    app.screen.query_one("#detail-metadata", Static).renderable
                )
                assert "Verifies the end-to-end" in rendered  # description
                assert "critical" in rendered                 # tags
                assert "smoke" in rendered
                assert "Active" in rendered                   # status
                assert "alice" in rendered                    # created_by
                assert "2024-01-10" in rendered               # created_at
                assert "2024-02-20" in rendered               # updated_at

        asyncio.run(_run())

    def test_metadata_graceful_on_missing_fields(self):
        """A sparse payload (only a name) must not crash the screen."""
        async def _run():
            api = _make_api()
            api.get_usecase.return_value = {"name": "Bare"}
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import Static
                rendered = str(
                    app.screen.query_one("#detail-metadata", Static).renderable
                )
                assert "Bare" in rendered
                # Missing tags / description fall back to an em-dash.
                assert "—" in rendered

        asyncio.run(_run())

    def test_secrets_values_are_masked(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable

                table = app.screen.query_one("#secrets-table", DataTable)
                # Column 1 is "Value" — must not be the raw value from the API.
                _, value_cell = (
                    table.get_row_at(0)[0],
                    table.get_row_at(0)[1],
                )
                assert "•" in str(value_cell)

        asyncio.run(_run())

    def test_escape_pops_back_to_list(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(app.screen, UsecasesListScreen)

        asyncio.run(_run())

    def test_executions_tab_renders_rows(self):
        async def _run():
            api = _make_api()
            api.list_executions.return_value = [
                ExecutionListItem(
                    execution_id="e-1",
                    status="success",
                    created_at="2024-02-20T10:00:00Z",
                    duration_seconds=42.0,
                    trigger_type="ci_runner",
                    triggered_by="alice",
                ),
                ExecutionListItem(
                    execution_id="e-2",
                    status="failed",
                    created_at="2024-02-19T10:00:00Z",
                    duration_seconds=5.0,
                    trigger_type="OnDemandHeadless",
                    triggered_by="bob",
                ),
            ]
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable

                table = app.screen.query_one("#executions-table", DataTable)
                assert table.row_count == 2

        asyncio.run(_run())

    def test_executions_tab_empty_shows_friendly_message(self):
        async def _run():
            api = _make_api()
            api.list_executions.return_value = []
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable, Static

                table = app.screen.query_one("#executions-table", DataTable)
                status = app.screen.query_one("#executions-status", Static)
                assert table.row_count == 0
                assert "No executions yet" in str(status.renderable)

        asyncio.run(_run())



class TestSuitesListScreen:
    def test_renders_rows_for_each_suite(self):
        async def _run():
            api = _make_api()
            api.list_suites.return_value = [
                SuiteListItem("s-1", "Smoke", 3, "happy paths"),
                SuiteListItem("s-2", "Regression", 42, "full"),
            ]
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                # Jump to the Suites section via the global "2" binding.
                await pilot.press("2")
                await pilot.pause()
                await pilot.pause()

                from qa_studio_cli.tui.screens.suites_list import SuitesListScreen
                assert isinstance(app.screen, SuitesListScreen)

                from textual.widgets import DataTable
                table = app.screen.query_one(DataTable)
                assert table.row_count == 2

        asyncio.run(_run())

    def test_empty_list_shows_friendly_message(self):
        async def _run():
            api = _make_api()
            api.list_suites.return_value = []
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("2")
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import Static
                status = app.screen.query_one("#suites-status", Static)
                assert "No test suites" in str(status.renderable)

        asyncio.run(_run())


class TestSuiteDetailScreen:
    def test_renders_metadata_and_usecase_rows(self):
        async def _run():
            api = _make_api()
            api.get_suite.return_value = {
                "name": "Smoke",
                "description": "happy paths",
                "tags": ["critical", "auth"],
            }
            api.list_suite_usecases.return_value = [
                {"usecase_id": "u-1", "usecase_name": "Login", "order": 1},
                {"usecase_id": "u-2", "usecase_name": "Checkout", "order": 2},
            ]
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.suite_detail import SuiteDetailScreen
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable, Static
                meta = app.screen.query_one("#suite-metadata", Static)
                text = str(meta.renderable)
                assert "Smoke" in text
                assert "critical" in text

                table = app.screen.query_one("#suite-usecases-table", DataTable)
                assert table.row_count == 2

        asyncio.run(_run())


class TestGlobalNavigation:
    def test_two_switches_to_suites_one_switches_back(self):
        async def _run():
            api = _make_api()
            api.list_suites.return_value = []
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("2")
                await pilot.pause()
                from qa_studio_cli.tui.screens.suites_list import SuitesListScreen
                assert isinstance(app.screen, SuitesListScreen)

                await pilot.press("1")
                await pilot.pause()
                assert isinstance(app.screen, UsecasesListScreen)

        asyncio.run(_run())

    def test_two_from_detail_pops_stack_and_switches(self):
        async def _run():
            api = _make_api()
            api.list_suites.return_value = []
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                # Drill into a use case detail, then hit "2".
                from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen
                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                assert isinstance(app.screen, UsecaseDetailScreen)

                await pilot.press("2")
                await pilot.pause()

                from qa_studio_cli.tui.screens.suites_list import SuitesListScreen
                assert isinstance(app.screen, SuitesListScreen)
                # Stack is ``[_default, SuitesListScreen]`` — no leftover
                # UsecaseDetail or UsecasesListScreen underneath.
                assert len(app.screen_stack) == 2

        asyncio.run(_run())



class TestOpenOpensCorrectRow:
    """Regression tests for the "opens the wrong one" bug.

    Textual's DataTable silently stores ``None`` as ``RowKey.value``
    when ``add_row`` is called without a ``key=`` argument, which means
    a mapping keyed by ``row_key.value`` collapses to a single entry.
    We fixed the screens to pass the usecase/suite id as the explicit
    row key; these tests lock that in.
    """

    def test_enter_on_second_usecase_opens_second_usecase(self):
        async def _run():
            api = _make_api(
                [
                    UsecaseListItem("u-1", "Login", "web", "us-east-1"),
                    UsecaseListItem("u-2", "Checkout", "web", "us-east-1"),
                    UsecaseListItem("u-3", "Profile", "web", "us-east-1"),
                ]
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                # Move cursor to the second row and press Enter.
                await pilot.press("down")
                await pilot.press("enter")
                await pilot.pause()

                from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen
                assert isinstance(app.screen, UsecaseDetailScreen)
                assert app.screen._usecase_id == "u-2"

        asyncio.run(_run())

    def test_enter_on_third_usecase_opens_third_usecase(self):
        async def _run():
            api = _make_api(
                [
                    UsecaseListItem("u-1", "Login", "web", "us-east-1"),
                    UsecaseListItem("u-2", "Checkout", "web", "us-east-1"),
                    UsecaseListItem("u-3", "Profile", "web", "us-east-1"),
                ]
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                await pilot.press("down")
                await pilot.press("down")
                await pilot.press("enter")
                await pilot.pause()

                from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen
                assert isinstance(app.screen, UsecaseDetailScreen)
                assert app.screen._usecase_id == "u-3"

        asyncio.run(_run())

    def test_enter_on_second_suite_opens_second_suite(self):
        async def _run():
            api = _make_api()
            api.list_suites.return_value = [
                SuiteListItem("s-1", "Smoke", 3, "happy"),
                SuiteListItem("s-2", "Regression", 42, "full"),
                SuiteListItem("s-3", "Auth only", 6, "auth"),
            ]
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("2")
                await pilot.pause()
                await pilot.pause()
                await pilot.press("down")
                await pilot.press("enter")
                await pilot.pause()

                from qa_studio_cli.tui.screens.suite_detail import SuiteDetailScreen
                assert isinstance(app.screen, SuiteDetailScreen)
                assert app.screen._suite_id == "s-2"

        asyncio.run(_run())

    def test_enter_on_second_usecase_row_inside_suite_opens_correct_usecase(self):
        """Inside SuiteDetailScreen, pressing Enter on the second row
        of the member-usecases table must open that usecase."""
        async def _run():
            api = _make_api()
            api.list_suite_usecases.return_value = [
                {"usecase_id": "u-1", "usecase_name": "Login", "order": 1},
                {"usecase_id": "u-2", "usecase_name": "Checkout", "order": 2},
                {"usecase_id": "u-3", "usecase_name": "Profile", "order": 3},
            ]
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.suite_detail import SuiteDetailScreen
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                # Focus the suite's usecase table, move to second row.
                from textual.widgets import DataTable
                table = app.screen.query_one("#suite-usecases-table", DataTable)
                table.focus()
                await pilot.pause()
                await pilot.press("down")
                await pilot.press("enter")
                await pilot.pause()

                from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen
                assert isinstance(app.screen, UsecaseDetailScreen)
                assert app.screen._usecase_id == "u-2"

        asyncio.run(_run())



class TestStepsSplitView:
    """Steps tab — cursor moves reveal the selected step's detail below."""

    def _api_with_three_steps(self):
        api = _make_api()
        api.get_steps.return_value = [
            {
                "sort": 1,
                "step_type": "navigate",
                "instruction": "Go to the homepage and wait for the hero section to load",
            },
            {
                "sort": 2,
                "step_type": "assert",
                "instruction": "See the title 'Welcome'",
                "assert_value": "Welcome",
            },
            {
                "sort": 3,
                "step_type": "network_assertion",
                "instruction": "Capture /api/products",
                "config": {"patterns": [{"urlPattern": "/api/products"}]},
            },
        ]
        return api

    def test_first_step_auto_selected_on_open(self):
        """Textual auto-selects row 0 when the table populates, so the
        detail pane shows the first step's payload immediately — no
        keypress required. This is desirable UX; the true "no
        selection" placeholder only appears when the list is empty
        (covered by ``test_no_steps_shows_empty_state``)."""
        async def _run():
            app = QAStudioTUIApp(tui_api=self._api_with_three_steps())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen

                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import Static
                detail = app.screen.query_one("#step-detail-text", Static)
                text = str(detail.renderable)
                # First step is the navigate step — its fields show.
                assert "navigate" in text
                assert "homepage" in text

        asyncio.run(_run())

    def test_highlighting_row_updates_detail_pane(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=self._api_with_three_steps())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen

                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable, Static

                table = app.screen.query_one("#steps-table", DataTable)
                table.focus()
                await pilot.pause()

                # Move to the second row (step #2, assert step).
                await pilot.press("down")
                await pilot.pause()

                detail_text = str(
                    app.screen.query_one("#step-detail-text", Static).renderable
                )
                assert "assert" in detail_text
                # The second step's instruction + assert_value must be
                # present in the detail pane.
                assert "Welcome" in detail_text

        asyncio.run(_run())

    def test_detail_pane_shows_full_untruncated_instruction(self):
        """Regression: table truncates long instructions at 80 chars;
        the detail pane must show the full text."""
        async def _run():
            app = QAStudioTUIApp(tui_api=self._api_with_three_steps())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen

                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable, Static

                table = app.screen.query_one("#steps-table", DataTable)
                table.focus()
                await pilot.pause()
                # First row is the long-instruction navigate step.
                await pilot.pause()

                detail_text = str(
                    app.screen.query_one("#step-detail-text", Static).renderable
                )
                # The full instruction (> 40 chars) must be present.
                assert "wait for the hero section to load" in detail_text

        asyncio.run(_run())

    def test_nested_config_renders_as_json(self):
        """network_assertion has a nested ``config`` dict — the detail
        pane should pretty-print it, not ``str()`` it."""
        async def _run():
            app = QAStudioTUIApp(tui_api=self._api_with_three_steps())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen

                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable, Static

                table = app.screen.query_one("#steps-table", DataTable)
                table.focus()
                await pilot.pause()
                await pilot.press("down")
                await pilot.press("down")  # third row — network_assertion
                await pilot.pause()

                detail_text = str(
                    app.screen.query_one("#step-detail-text", Static).renderable
                )
                # Pretty JSON uses keys on their own lines.
                assert '"patterns"' in detail_text
                assert '"urlPattern"' in detail_text

        asyncio.run(_run())

    def test_no_steps_shows_empty_state(self):
        async def _run():
            api = _make_api()
            api.get_steps.return_value = []
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen

                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import Static
                detail = app.screen.query_one("#step-detail-text", Static)
                assert "no steps" in str(detail.renderable).lower()

        asyncio.run(_run())

    def test_empty_step_fields_are_hidden(self):
        """Regression: None / ""/ [] / {} fields must not render as
        ``label: —`` — they should be omitted entirely so the pane is
        only the set fields."""
        async def _run():
            api = _make_api()
            api.get_steps.return_value = [
                {
                    "sort": 1,
                    "step_type": "assert",
                    "instruction": "See the title",
                    "assert_value": "Welcome",
                    # Fields that should NOT appear:
                    "selector": "",
                    "description": None,
                    "tags": [],
                    "config": {},
                },
            ]
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen

                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import Static
                text = str(
                    app.screen.query_one("#step-detail-text", Static).renderable
                )

                # Non-empty fields present.
                assert "step_type" in text
                assert "assert" in text
                assert "Welcome" in text

                # Empty-valued labels absent.
                assert "selector" not in text
                assert "description" not in text
                assert "tags" not in text
                assert "config" not in text

        asyncio.run(_run())

    def test_false_and_zero_are_not_treated_as_empty(self):
        """Bool False and numeric 0 are meaningful values; they must
        still render."""
        async def _run():
            api = _make_api()
            api.get_steps.return_value = [
                {
                    "sort": 1,
                    "step_type": "assert",
                    "instruction": "Check",
                    "optional": False,
                    "retry_count": 0,
                },
            ]
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen

                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import Static
                text = str(
                    app.screen.query_one("#step-detail-text", Static).renderable
                )
                assert "optional" in text
                assert "False" in text
                assert "retry_count" in text
                assert "0" in text

        asyncio.run(_run())



class TestListFiltering:
    """Client-side name/id substring filter on the two list screens."""

    def test_usecases_filter_by_name(self):
        async def _run():
            api = _make_api(
                [
                    UsecaseListItem("u-1", "Login", "web", "us-east-1"),
                    UsecaseListItem("u-2", "Checkout", "web", "us-east-1"),
                    UsecaseListItem("u-3", "Profile edit", "web", "us-east-1"),
                ]
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable, Input

                filter_input = app.screen.query_one("#usecases-filter", Input)
                filter_input.value = "check"
                # Input.Changed fires on assignment; give it a tick.
                await pilot.pause()

                table = app.screen.query_one(DataTable)
                assert table.row_count == 1

        asyncio.run(_run())

    def test_usecases_filter_by_id(self):
        async def _run():
            api = _make_api(
                [
                    UsecaseListItem("uc-abc", "Login", "web", "us-east-1"),
                    UsecaseListItem("uc-xyz", "Checkout", "web", "us-east-1"),
                ]
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable, Input

                app.screen.query_one("#usecases-filter", Input).value = "xyz"
                await pilot.pause()

                table = app.screen.query_one(DataTable)
                assert table.row_count == 1

        asyncio.run(_run())

    def test_usecases_filter_is_case_insensitive(self):
        async def _run():
            api = _make_api(
                [
                    UsecaseListItem("u-1", "LOGIN", "web", "us-east-1"),
                ]
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable, Input

                app.screen.query_one("#usecases-filter", Input).value = "login"
                await pilot.pause()

                table = app.screen.query_one(DataTable)
                assert table.row_count == 1

        asyncio.run(_run())

    def test_usecases_empty_filter_shows_all(self):
        async def _run():
            api = _make_api(
                [
                    UsecaseListItem("u-1", "Login", "web", "us-east-1"),
                    UsecaseListItem("u-2", "Checkout", "web", "us-east-1"),
                ]
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable, Input

                filter_input = app.screen.query_one("#usecases-filter", Input)
                filter_input.value = "xxx"
                await pilot.pause()
                assert app.screen.query_one(DataTable).row_count == 0

                filter_input.value = ""
                await pilot.pause()
                assert app.screen.query_one(DataTable).row_count == 2

        asyncio.run(_run())

    def test_slash_focuses_usecase_filter(self):
        async def _run():
            api = _make_api(
                [UsecaseListItem("u-1", "Login", "web", "us-east-1")]
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                await pilot.press("slash")
                await pilot.pause()

                from textual.widgets import Input

                filter_input = app.screen.query_one("#usecases-filter", Input)
                assert filter_input.has_focus

        asyncio.run(_run())

    def test_suites_filter_by_name(self):
        async def _run():
            api = _make_api()
            api.list_suites.return_value = [
                SuiteListItem("s-1", "Smoke", 3, "happy"),
                SuiteListItem("s-2", "Regression", 42, "full"),
                SuiteListItem("s-3", "Smoke (auth)", 6, "auth only"),
            ]
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("2")
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable, Input

                app.screen.query_one("#suites-filter", Input).value = "smoke"
                await pilot.pause()

                # Two suites match "smoke" — regression is hidden.
                assert app.screen.query_one(DataTable).row_count == 2

        asyncio.run(_run())
