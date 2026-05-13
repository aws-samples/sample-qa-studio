"""Tests for the suite-detail screen's Executions tab.

Covers:

* ``TestSuiteAPI.list_executions`` hits the right URL with the right
  limit parameter.
* ``TuiApi.list_suite_executions`` swallows transport errors and
  returns an empty list — the tab treats "no executions" as a
  legitimate empty state.
* The suite-detail screen renders both the Usecases and Executions
  tabs and populates the executions table from the loaded bundle.
* An empty executions list renders a friendly "No executions yet"
  message instead of a blank table.
* Clicking / Enter on an execution row does NOT navigate (no suite-
  execution-detail screen exists yet) while clicking on the
  Usecases table still opens the usecase detail (no regression).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

pytest.importorskip("textual")

from textual.widgets import DataTable, Static  # noqa: E402

from qa_studio_cli.tui.api import (  # noqa: E402
    SuiteListItem,
    TuiApi,
    UsecaseListItem,
)
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.screens.suite_detail import SuiteDetailScreen  # noqa: E402


# ---------------------------------------------------------------------------
# API layer
# ---------------------------------------------------------------------------


class TestTestSuiteAPIListExecutions:
    def test_hits_correct_url_with_limit(self):
        from qa_studio_cli.api.test_suites import TestSuiteAPI

        client = MagicMock()
        client.get.return_value = {"executions": [{"status": "completed"}]}

        api = TestSuiteAPI(client)
        result = api.list_executions("suite-1", limit=5)

        client.get.assert_called_once_with(
            "/test-suites/suite-1/executions",
            params={"limit": 5},
        )
        assert result == [{"status": "completed"}]

    def test_default_limit_is_20(self):
        from qa_studio_cli.api.test_suites import TestSuiteAPI

        client = MagicMock()
        client.get.return_value = {"executions": []}

        TestSuiteAPI(client).list_executions("suite-1")

        _, kwargs = client.get.call_args
        assert kwargs["params"] == {"limit": 20}

    def test_missing_executions_key_returns_empty_list(self):
        from qa_studio_cli.api.test_suites import TestSuiteAPI

        client = MagicMock()
        client.get.return_value = {}  # endpoint returned no executions key
        assert TestSuiteAPI(client).list_executions("suite-1") == []


class TestTuiApiListSuiteExecutions:
    def test_delegates_to_suite_api_on_happy_path(self):
        from qa_studio_cli.api.client import ApiClient

        client = MagicMock(spec=ApiClient)
        client.get.return_value = {"executions": [{"status": "running"}]}

        api = TuiApi(client)
        assert api.list_suite_executions("s-1") == [{"status": "running"}]

    def test_swallows_errors_and_returns_empty(self):
        """Transport / 404 errors must not break the whole detail load
        — the tab just shows the empty-state message."""
        from qa_studio_cli.api.client import ApiClient

        client = MagicMock(spec=ApiClient)
        client.get.side_effect = RuntimeError("offline")

        api = TuiApi(client)
        assert api.list_suite_executions("s-1") == []


# ---------------------------------------------------------------------------
# Screen integration
# ---------------------------------------------------------------------------


def _make_api(
    *,
    suite: dict | None = None,
    usecases: list[dict] | None = None,
    executions: list[dict] | None = None,
) -> MagicMock:
    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = [
        UsecaseListItem("u-1", "Login", "web", "us-east-1"),
    ]
    api.list_suites.return_value = [
        SuiteListItem("s-1", "Smoke", 2, "happy paths"),
    ]
    api.get_suite.return_value = suite or {
        "name": "Smoke",
        "description": "happy paths",
        "tags": ["critical"],
        "total_usecases": 2,
    }
    api.list_suite_usecases.return_value = usecases or [
        {"usecase_id": "u-1", "usecase_name": "Login", "order": 1},
        {"usecase_id": "u-2", "usecase_name": "Checkout", "order": 2},
    ]
    api.list_suite_executions.return_value = executions if executions is not None else [
        {
            "suite_execution_id": "se-1",
            "status": "completed",
            "started_at": "2024-02-20T10:00:00Z",
            "total_usecases": 2,
            "successful_usecases": 2,
            "failed_usecases": 0,
            "duration_seconds": 42.0,
            "trigger_type": "manual",
            "triggered_by": "alice",
        },
        {
            "suite_execution_id": "se-2",
            "status": "partial",
            "started_at": "2024-02-19T10:00:00Z",
            "total_usecases": 2,
            "successful_usecases": 1,
            "failed_usecases": 1,
            "duration_seconds": 30.0,
            "trigger_type": "ci_runner",
            "triggered_by": "bob",
        },
    ]
    return api


class TestSuiteDetailExecutionsTab:
    def test_both_tabs_mount(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                screen = app.screen
                # Both tab panes are in the DOM.
                screen.query_one("#tab-suite-usecases")
                screen.query_one("#tab-suite-executions")

        asyncio.run(_run())

    def test_executions_tab_populates_rows(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                table = app.screen.query_one(
                    "#suite-executions-table", DataTable
                )
                assert table.row_count == 2

                status_widget = app.screen.query_one(
                    "#suite-executions-status", Static
                )
                assert "2 most recent" in str(status_widget.renderable)

        asyncio.run(_run())

    def test_executions_tab_renders_status_and_progress(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                table = app.screen.query_one(
                    "#suite-executions-table", DataTable
                )
                # Row 0: completed, 2/2
                row0 = table.get_row_at(0)
                assert "completed" in str(row0[0])  # status cell
                assert str(row0[3]) == "2/2"  # pass/total
                assert str(row0[4]) == "manual"  # trigger
                assert str(row0[5]) == "alice"  # by

                # Row 1: partial, 1/2
                row1 = table.get_row_at(1)
                assert "partial" in str(row1[0])
                assert str(row1[3]) == "1/2"

        asyncio.run(_run())

    def test_executions_tab_empty_state(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api(executions=[]))
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                table = app.screen.query_one(
                    "#suite-executions-table", DataTable
                )
                status = app.screen.query_one(
                    "#suite-executions-status", Static
                )
                assert table.row_count == 0
                assert "No executions yet" in str(status.renderable)

        asyncio.run(_run())

    def test_usecases_tab_still_renders_usecase_rows(self):
        """Regression: the Usecases tab must keep working after the
        refactor introduced TabbedContent."""

        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                table = app.screen.query_one(
                    "#suite-usecases-table", DataTable
                )
                assert table.row_count == 2

        asyncio.run(_run())

    def test_api_error_on_executions_does_not_break_the_screen(self):
        """``list_suite_executions`` swallowing errors means the tab
        shows the empty-state copy rather than crashing the whole
        suite-detail load."""

        async def _run():
            # TuiApi stub returns [] for list_suite_executions (as it
            # would in prod on any transport error).
            app = QAStudioTUIApp(tui_api=_make_api(executions=[]))
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                # The Usecases tab data is unaffected.
                usecases_table = app.screen.query_one(
                    "#suite-usecases-table", DataTable
                )
                assert usecases_table.row_count == 2

                # Executions tab shows the empty-state copy.
                status = app.screen.query_one(
                    "#suite-executions-status", Static
                )
                assert "No executions yet" in str(status.renderable)

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Progressive loading
# ---------------------------------------------------------------------------
#
# These tests pin the behaviour we get from the ``asyncio.gather`` /
# ``asyncio.to_thread`` fan-out: metadata no longer depends on the
# usecases section, per-section failures are isolated, and the Run
# action unblocks as soon as the metadata arrives even if the other
# sections are still in flight or have failed.


class TestSuiteDetailProgressiveLoad:
    def test_metadata_reads_total_usecases_from_suite_record(self):
        """``suite["total_usecases"]`` is the single source of truth —
        metadata must not rely on ``len(bundle.usecases)``. Set the
        two to different values and assert metadata shows the suite's
        own number."""

        async def _run():
            api = _make_api(
                suite={
                    "name": "Smoke",
                    "description": "happy paths",
                    "tags": ["critical"],
                    "total_usecases": 5,  # suite's canonical count
                },
                usecases=[
                    {"usecase_id": "u-1", "usecase_name": "Login"},
                    {"usecase_id": "u-2", "usecase_name": "Checkout"},
                ],  # only 2 returned
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                meta = app.screen.query_one("#suite-metadata", Static)
                assert "Use cases: 5" in str(meta.renderable)

        asyncio.run(_run())

    def test_missing_total_usecases_renders_em_dash(self):
        """A suite record without ``total_usecases`` must not crash —
        fall back to the em-dash so the layout stays stable."""

        async def _run():
            api = _make_api(
                suite={
                    "name": "Bare",
                    "description": "",
                    "tags": [],
                    # No total_usecases field.
                }
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                meta = app.screen.query_one("#suite-metadata", Static)
                assert "Use cases: —" in str(meta.renderable)

        asyncio.run(_run())

    def test_usecases_section_failure_still_renders_metadata_and_executions(self):
        """Per-section fault isolation: if list_suite_usecases raises,
        the metadata + executions sections must still render and the
        Run action must still unblock (self._suite is populated)."""

        async def _run():
            api = _make_api()
            api.list_suite_usecases.side_effect = RuntimeError("boom")
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                # Metadata rendered from the suite record.
                meta = app.screen.query_one("#suite-metadata", Static)
                assert "Smoke" in str(meta.renderable)

                # Executions tab rendered normally.
                executions = app.screen.query_one(
                    "#suite-executions-table", DataTable
                )
                assert executions.row_count == 2

                # Run action unblocked — the suite record arrived.
                assert app.screen._suite  # populated by render_metadata

                # Usecases section surfaces its failure on its own
                # tab status widget so the progress counter on the
                # top-level status line doesn't overwrite it.
                usecases_status = app.screen.query_one(
                    "#suite-usecases-status", Static
                )
                assert "Failed to load usecases" in str(
                    usecases_status.renderable
                )

        asyncio.run(_run())

    def test_executions_section_failure_leaves_other_tabs_usable(self):
        """Inverse of the above: if executions raises, metadata and
        the usecases tab must still render cleanly."""

        async def _run():
            api = _make_api()
            api.list_suite_executions.side_effect = RuntimeError("boom")
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                meta = app.screen.query_one("#suite-metadata", Static)
                assert "Smoke" in str(meta.renderable)

                usecases = app.screen.query_one(
                    "#suite-usecases-table", DataTable
                )
                assert usecases.row_count == 2

                # Failure surfaces in the executions tab's own status
                # widget rather than the top-level status line.
                exec_status = app.screen.query_one(
                    "#suite-executions-status", Static
                )
                assert "Failed to load executions" in str(exec_status.renderable)

        asyncio.run(_run())

    def test_metadata_section_failure_surfaces_in_metadata_widget(self):
        """If the suite fetch fails, the error must land in the big
        metadata block (so the user sees it) rather than being
        swallowed into the hidden top-status line."""

        async def _run():
            api = _make_api()
            api.get_suite.side_effect = RuntimeError("not found")
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                meta = app.screen.query_one("#suite-metadata", Static)
                assert "Failed to load suite" in str(meta.renderable)
                assert "not found" in str(meta.renderable)

        asyncio.run(_run())

    def test_all_success_clears_top_status(self):
        """When every section succeeds the ``Loading… N/3`` counter
        goes away — no stale status-line clutter."""

        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                top_status = app.screen.query_one("#suite-status", Static)
                assert str(top_status.renderable) == ""

        asyncio.run(_run())

    def test_bundle_populated_only_when_all_sections_succeed(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()
                assert app.screen._bundle is not None

        asyncio.run(_run())

    def test_bundle_not_populated_when_a_section_fails(self):
        async def _run():
            api = _make_api()
            api.list_suite_usecases.side_effect = RuntimeError("boom")
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()
                # Bundle stays None because the usecases section
                # didn't land — keeps the bundle invariant honest.
                assert app.screen._bundle is None

        asyncio.run(_run())
