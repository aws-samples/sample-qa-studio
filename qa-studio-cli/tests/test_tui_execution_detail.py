"""Tests for ``ExecutionDetailScreen`` + ``TuiApi.get_execution_detail``."""

import asyncio
from unittest.mock import MagicMock

import pytest

pytest.importorskip("textual")

from qa_studio_cli.tui.api import TuiApi  # noqa: E402
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402


# ---------------------------------------------------------------------------
# TuiApi.get_execution_detail
# ---------------------------------------------------------------------------


class TestGetExecutionDetail:
    def test_composes_four_endpoints(self):
        client = MagicMock()
        responses = {
            "/usecase/u-1/executions/e-1": {
                "id": "e-1", "status": "success",
            },
            "/usecase/u-1/executions/e-1/steps": {
                "steps": [{"sort": 1, "status": "success"}]
            },
            "/usecase/u-1/executions/e-1/variables": {
                "variables": [{"key": "env", "value": "dev"}]
            },
            "/usecase/u-1/executions/e-1/headers": {
                "headers": {"X-Trace": "abc"}
            },
        }
        client.get.side_effect = lambda path, **_: responses[path]

        api = TuiApi(client)
        result = api.get_execution_detail("u-1", "e-1")

        assert result["status"] == "success"
        assert result["steps"] == [{"sort": 1, "status": "success"}]
        assert result["variables"] == {"env": "dev"}
        assert result["headers"] == {"X-Trace": "abc"}

    def test_sub_resource_failures_fall_back_to_empty(self):
        """Older executions may not have every endpoint wired — the
        top-level fetch must still return a usable payload."""
        client = MagicMock()

        def _get(path, **_):
            if path == "/usecase/u-1/executions/e-1":
                return {"status": "success"}
            raise RuntimeError("404 not found")

        client.get.side_effect = _get

        api = TuiApi(client)
        result = api.get_execution_detail("u-1", "e-1")
        assert result["status"] == "success"
        assert result["steps"] == []
        assert result["variables"] == {}
        assert result["headers"] == {}

    def test_execution_variables_dict_form_preserved(self):
        """When the server returns pre-merged ``execution_variables``
        as a dict, we use it as-is rather than re-merging."""
        client = MagicMock()
        responses = {
            "/usecase/u-1/executions/e-1": {"status": "success"},
            "/usecase/u-1/executions/e-1/steps": {"steps": []},
            "/usecase/u-1/executions/e-1/variables": {
                "execution_variables": {"env": "prod", "region": "eu-west-1"}
            },
            "/usecase/u-1/executions/e-1/headers": {"headers": {}},
        }
        client.get.side_effect = lambda path, **_: responses[path]

        api = TuiApi(client)
        result = api.get_execution_detail("u-1", "e-1")
        assert result["variables"] == {"env": "prod", "region": "eu-west-1"}


# ---------------------------------------------------------------------------
# ExecutionDetailScreen
# ---------------------------------------------------------------------------


def _make_api_with_execution(
    execution: dict | None = None,
    executions_list: list | None = None,
) -> MagicMock:
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
    api.list_executions.return_value = executions_list or []

    # Tests pass a single composite ``execution`` dict (historical
    # shape). The screen now uses the split endpoints, so we derive
    # both return values from that one fixture: steps come off the
    # top-level ``steps`` key, metadata is everything else. The
    # composite mock stays set because ``TestGetExecutionDetail``
    # tests the composite method directly.
    exec_payload = execution or {
        "id": "e-1",
        "status": "success",
        "trigger_type": "OnDemandHeadless",
        "triggered_by": "alice",
        "duration_seconds": 42,
        "steps": [],
    }
    steps = exec_payload.get("steps", []) or []
    metadata = {k: v for k, v in exec_payload.items() if k != "steps"}
    api.get_execution_metadata.return_value = metadata
    api.get_execution_steps.return_value = steps
    api.get_execution_detail.return_value = exec_payload
    return api


class TestExecutionDetailScreen:
    def test_renders_metadata_and_steps(self):
        async def _run():
            api = _make_api_with_execution(
                execution={
                    "id": "e-1",
                    "usecase_name": "Checkout",
                    "status": "success",
                    "trigger_type": "ci_runner",
                    "triggered_by": "alice",
                    "duration_seconds": 42,
                    "steps": [
                        {
                            "sort": 1,
                            "step_type": "navigation",
                            "status": "success",
                            "instruction": "Go to /",
                            "duration": 3,
                        },
                        {
                            "sort": 2,
                            "step_type": "assertion",
                            "status": "failed",
                            "instruction": "See title",
                            "duration": 1,
                            "error_message": "Title not found",
                        },
                    ],
                }
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.execution_detail import (
                    ExecutionDetailScreen,
                )

                app.push_screen(ExecutionDetailScreen("u-1", "e-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable, Static

                meta = str(
                    app.screen.query_one("#execution-metadata", Static).renderable
                )
                assert "Checkout" in meta
                assert "alice" in meta
                assert "ci_runner" in meta

                table = app.screen.query_one("#execution-steps-table", DataTable)
                assert table.row_count == 2

        asyncio.run(_run())

    def test_error_message_shown_when_failed(self):
        async def _run():
            api = _make_api_with_execution(
                execution={
                    "id": "e-1",
                    "status": "failed",
                    "error_message": "Connection refused",
                    "steps": [],
                }
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.execution_detail import (
                    ExecutionDetailScreen,
                )

                app.push_screen(ExecutionDetailScreen("u-1", "e-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import Static

                banner = str(
                    app.screen.query_one("#execution-error", Static).renderable
                )
                assert "Connection refused" in banner

        asyncio.run(_run())

    def test_step_detail_updates_on_cursor_move(self):
        async def _run():
            api = _make_api_with_execution(
                execution={
                    "id": "e-1",
                    "status": "success",
                    "steps": [
                        {
                            "sort": 1,
                            "step_type": "navigation",
                            "status": "success",
                            "instruction": "Go to home",
                            "duration": 3,
                        },
                        {
                            "sort": 2,
                            "step_type": "assertion",
                            "status": "failed",
                            "instruction": "See welcome",
                            "error_message": "expected 'Welcome' got 'Error'",
                            "duration": 1,
                        },
                    ],
                }
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.execution_detail import (
                    ExecutionDetailScreen,
                )

                app.push_screen(ExecutionDetailScreen("u-1", "e-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import DataTable, Static

                table = app.screen.query_one("#execution-steps-table", DataTable)
                table.focus()
                await pilot.pause()
                # Move to second row (the failed assertion).
                await pilot.press("down")
                await pilot.pause()

                text = str(
                    app.screen.query_one(
                        "#execution-step-detail-text", Static
                    ).renderable
                )
                assert "expected 'Welcome' got 'Error'" in text

        asyncio.run(_run())

    def test_enter_on_execution_row_opens_execution_detail(self):
        """From the usecase detail's Executions tab: Enter on a row
        pushes ``ExecutionDetailScreen`` for that execution."""
        async def _run():
            from qa_studio_cli.tui.api import ExecutionListItem

            api = _make_api_with_execution(
                executions_list=[
                    ExecutionListItem(
                        execution_id="e-1",
                        status="success",
                        created_at="2024-02-20T10:00:00Z",
                        duration_seconds=10,
                        trigger_type="ci_runner",
                        triggered_by="alice",
                    ),
                ]
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import (
                    UsecaseDetailScreen,
                )

                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                # Activate the Executions tab.
                from textual.widgets import DataTable, TabbedContent

                tabs = app.screen.query_one("#detail-tabs", TabbedContent)
                tabs.active = "tab-executions"
                await pilot.pause()

                table = app.screen.query_one("#executions-table", DataTable)
                table.focus()
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()

                from qa_studio_cli.tui.screens.execution_detail import (
                    ExecutionDetailScreen,
                )
                assert isinstance(app.screen, ExecutionDetailScreen)
                assert app.screen._execution_id == "e-1"

        asyncio.run(_run())
