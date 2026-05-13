"""Tests for :func:`render_validation_block` + its use in the detail panes."""

import asyncio
from unittest.mock import MagicMock

import pytest

pytest.importorskip("textual")

from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.api import TuiApi  # noqa: E402
from qa_studio_cli.tui.step_render import render_validation_block  # noqa: E402


# ---------------------------------------------------------------------------
# Pure unit tests
# ---------------------------------------------------------------------------


class TestRenderValidationBlock:
    def test_empty_type_returns_empty_string(self):
        assert render_validation_block(
            validation_type="",
            validation_operator="exact",
            validation_value="x",
        ) == ""

    def test_definition_only_block(self):
        """No ``actual_value`` — just show the expected side."""
        block = render_validation_block(
            validation_type="string",
            validation_operator="contains",
            validation_value="welcome",
        )
        assert "Text" in block
        assert "Contains" in block
        assert "welcome" in block
        assert "∋" in block

    def test_execution_block_green_on_success(self):
        block = render_validation_block(
            validation_type="string",
            validation_operator="exact",
            validation_value="Welcome",
            actual_value="Welcome",
            status="success",
        )
        assert "[b green]Welcome[/]" in block
        assert "=" in block

    def test_execution_block_red_on_failure(self):
        block = render_validation_block(
            validation_type="string",
            validation_operator="exact",
            validation_value="Welcome",
            actual_value="Error",
            status="failed",
        )
        assert "[b red]Error[/]" in block

    def test_unknown_operator_falls_back_to_question_mark(self):
        block = render_validation_block(
            validation_type="string",
            validation_operator="brand_new_op",
            validation_value="x",
        )
        assert "?" in block

    def test_number_greater_than_uses_correct_symbol(self):
        block = render_validation_block(
            validation_type="number",
            validation_operator="greater_then",
            validation_value="10",
            actual_value="42",
            status="success",
        )
        assert "Number" in block
        assert "Greater Than" in block
        assert ">" in block

    def test_boolean_type_label(self):
        block = render_validation_block(
            validation_type="bool",
            validation_operator="exact",
            validation_value="true",
        )
        assert "Boolean" in block

    def test_empty_actual_rendered_as_placeholder(self):
        """An empty ``actual_value`` shouldn't collapse to a blank
        cell — we show ``(empty)`` dim so the user knows the runner
        got nothing back."""
        block = render_validation_block(
            validation_type="string",
            validation_operator="exact",
            validation_value="x",
            actual_value="",
            status="failed",
        )
        assert "(empty)" in block


# ---------------------------------------------------------------------------
# Screen integration
# ---------------------------------------------------------------------------


def _make_api_with_validation_step(status: str = "success") -> MagicMock:
    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = []
    api.get_usecase.return_value = {
        "name": "Checkout",
        "starting_url": "https://shop.example.com/",
        "executing_region": "us-east-1",
        "model_id": "nova-act-v1.0",
        "test_platform": "web",
    }
    api.get_steps.return_value = [
        {
            "sort": 1,
            "step_type": "assertion",
            "instruction": "See the order confirmation",
            "validation_type": "string",
            "validation_operator": "contains",
            "validation_value": "Thank you",
        },
    ]
    api.get_variables.return_value = {}
    api.get_headers.return_value = {}
    api.get_secrets.return_value = []
    api.list_executions.return_value = []
    # ExecutionDetailScreen now drives the two rendered sections
    # independently via the split endpoints. Keep the composite mock
    # set as well so anything still touching it has a predictable
    # payload.
    _execution_steps = [
        {
            "sort": 1,
            "step_type": "assertion",
            "status": status,
            "instruction": "See the order confirmation",
            "validation_type": "string",
            "validation_operator": "contains",
            "validation_value": "Thank you",
            "actual_value": "Thank you for your order",
        },
    ]
    _execution_metadata = {
        "id": "e-1",
        "status": status,
    }
    api.get_execution_metadata.return_value = _execution_metadata
    api.get_execution_steps.return_value = _execution_steps
    api.get_execution_detail.return_value = {
        **_execution_metadata,
        "steps": _execution_steps,
    }
    return api


class TestExecutionStepDetailShowsValidation:
    def test_validation_block_renders_at_top_of_detail_pane(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api_with_validation_step(
                status="success"
            ))
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.execution_detail import (
                    ExecutionDetailScreen,
                )

                app.push_screen(ExecutionDetailScreen("u-1", "e-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import Static

                text = str(
                    app.screen.query_one(
                        "#execution-step-detail-text", Static
                    ).renderable
                )
                # Header + comparison are present before the generic
                # field list (``step_type``, ``instruction``, etc.).
                assert "Text" in text
                assert "Contains" in text
                assert "Thank you for your order" in text

                # Ordering sanity — validation block is above the
                # step_type/instruction lines.
                validation_idx = text.find("Contains")
                step_type_idx = text.find("step_type")
                assert validation_idx < step_type_idx

        asyncio.run(_run())


class TestUsecaseStepDetailShowsValidation:
    def test_definition_validation_block_visible(self):
        async def _run():
            app = QAStudioTUIApp(
                tui_api=_make_api_with_validation_step(status="success")
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import (
                    UsecaseDetailScreen,
                )

                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                await pilot.pause()
                await pilot.pause()

                from textual.widgets import Static

                text = str(
                    app.screen.query_one("#step-detail-text", Static).renderable
                )
                assert "Text" in text
                assert "Contains" in text
                # No actual_value in the usecase context — block is
                # the two-line definition variant.
                assert "Thank you" in text

        asyncio.run(_run())
