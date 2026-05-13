"""Tests for the suite Run form + variables parser."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("textual")

from qa_studio_cli.tui.api import TuiApi  # noqa: E402
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.screens.suite_run_form import (  # noqa: E402
    parse_variables_textarea,
)


# ---------------------------------------------------------------------------
# Pure parser
# ---------------------------------------------------------------------------


class TestParseVariablesTextarea:
    def test_empty_text_returns_empty(self):
        result, errors = parse_variables_textarea("")
        assert result == {}
        assert errors == []

    def test_happy_path(self):
        result, errors = parse_variables_textarea("email=a@x\npassword=hunter2\n")
        assert result == {"email": "a@x", "password": "hunter2"}
        assert errors == []

    def test_blank_and_whitespace_lines_skipped(self):
        result, errors = parse_variables_textarea(
            "\nemail=a@x\n\n   \npassword=hunter2\n"
        )
        assert result == {"email": "a@x", "password": "hunter2"}
        assert errors == []

    def test_value_containing_equals_preserved(self):
        """Only the first ``=`` is a separator — values can carry
        equals (query strings, base64 padding, etc.)."""
        result, errors = parse_variables_textarea("token=abc=def=ghi")
        assert result == {"token": "abc=def=ghi"}
        assert errors == []

    def test_line_without_equals_is_reported(self):
        result, errors = parse_variables_textarea("email=a@x\nbad line\npw=x")
        assert result == {"email": "a@x", "pw": "x"}
        assert len(errors) == 1
        assert "Line 2" in errors[0]

    def test_line_with_empty_key_is_reported(self):
        result, errors = parse_variables_textarea("=orphan")
        assert result == {}
        assert len(errors) == 1
        assert "empty key" in errors[0]


# ---------------------------------------------------------------------------
# Screen integration
# ---------------------------------------------------------------------------


def _make_api() -> MagicMock:
    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = []
    api.list_suites.return_value = []
    api.get_suite.return_value = {
        "name": "Smoke",
        "description": "happy paths",
        "tags": ["critical"],
        "total_usecases": 3,
    }
    api.list_suite_usecases.return_value = [
        {"usecase_id": "u-1", "usecase_name": "Login", "order": 1},
    ]
    return api


class TestSuiteRunFormScreen:
    def test_R_on_suite_detail_opens_the_run_form(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.suite_detail import (
                    SuiteDetailScreen,
                )

                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()

                await pilot.press("R")
                await pilot.pause()

                from qa_studio_cli.tui.screens.suite_run_form import (
                    SuiteRunFormScreen,
                )
                assert isinstance(app.screen, SuiteRunFormScreen)

        asyncio.run(_run())

    def test_submit_with_overrides_builds_correct_argv(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.suite_detail import (
                    SuiteDetailScreen,
                )

                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()
                await pilot.press("R")
                await pilot.pause()

                from textual.widgets import Input, TextArea

                base_url_input = app.screen.query_one(
                    "#suite-input-base-url", Input
                )
                base_url_input.value = "https://staging.example.com"

                variables_textarea = app.screen.query_one(
                    "#suite-input-variables", TextArea
                )
                variables_textarea.text = "email=dev@x\npw=hunter2\n"
                await pilot.pause()

                # Prevent the LiveTail worker from spawning a real
                # subprocess — we only want to verify the argv.
                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen

                with patch.object(LiveTailScreen, "on_mount", lambda self: None):
                    await pilot.press("ctrl+s")
                    await pilot.pause()

                assert isinstance(app.screen, LiveTailScreen)
                argv = app.screen._runner.argv

                # Targets the suite, not a usecase.
                assert "--suite-id" in argv
                assert argv[argv.index("--suite-id") + 1] == "s-1"
                assert "--usecase-id" not in argv

                # Variables threaded through as repeated --var flags.
                var_positions = [i for i, a in enumerate(argv) if a == "--var"]
                assert len(var_positions) == 2
                var_pairs = {argv[i + 1] for i in var_positions}
                assert var_pairs == {"email=dev@x", "pw=hunter2"}

                # Base URL override.
                assert "--base-url" in argv
                assert argv[argv.index("--base-url") + 1] == (
                    "https://staging.example.com"
                )

        asyncio.run(_run())

    def test_invalid_variable_line_blocks_submit(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.suite_detail import (
                    SuiteDetailScreen,
                )

                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()
                await pilot.press("R")
                await pilot.pause()

                from textual.widgets import TextArea
                from qa_studio_cli.tui.screens.suite_run_form import (
                    SuiteRunFormScreen,
                )

                app.screen.query_one(
                    "#suite-input-variables", TextArea
                ).text = "not a valid line"
                await pilot.pause()

                await pilot.press("ctrl+s")
                await pilot.pause()

                # Still on the form — submit rejected.
                assert isinstance(app.screen, SuiteRunFormScreen)

        asyncio.run(_run())

    def test_cancel_returns_to_detail(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.suite_detail import (
                    SuiteDetailScreen,
                )

                app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                await pilot.pause()
                await pilot.pause()
                await pilot.press("R")
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()

                assert isinstance(app.screen, SuiteDetailScreen)

        asyncio.run(_run())
