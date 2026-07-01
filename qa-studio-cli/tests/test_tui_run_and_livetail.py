"""Tests for ``RunFormScreen`` and ``LiveTailScreen``.

Skipped when the ``[tui]`` extra is not installed. LiveTail tests use
a tiny Python ``-c`` snippet as the child so no real ``qa-studio run``
execution happens.
"""

import asyncio
import sys
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("textual")

from qa_studio_cli.tui.api import TuiApi  # noqa: E402
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.override_writer import OverrideFiles  # noqa: E402
from qa_studio_cli.tui.subprocess_runner import RunnerProcess  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api() -> MagicMock:
    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = []
    api.get_usecase.return_value = {
        "name": "Checkout",
        "starting_url": "https://shop.example.com/checkout",
        "executing_region": "us-east-1",
        "model_id": "nova-act-v1.0",
        "test_platform": "web",
    }
    api.get_steps.return_value = []
    api.get_variables.return_value = {"email": "default@x.com"}
    api.get_headers.return_value = {"X-Trace": "abc"}
    api.get_secrets.return_value = [{"key": "admin_pw", "value": ""}]
    api.list_executions.return_value = []
    return api


def _snippet_runner(body: str) -> RunnerProcess:
    argv = [sys.executable, "-c", body]
    return RunnerProcess(argv=argv, override_files=OverrideFiles())


# ---------------------------------------------------------------------------
# RunFormScreen
# ---------------------------------------------------------------------------


class TestRunFormScreen:
    def test_R_opens_form_prefilled_from_bundle(self):
        """Pressing ``R`` on the detail screen pushes RunFormScreen and
        pre-fills every declared field with its default."""

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

                # Press uppercase R — Textual binds it literally.
                await pilot.press("R")
                await pilot.pause()

                from qa_studio_cli.tui.screens.run_form import RunFormScreen

                assert isinstance(app.screen, RunFormScreen)

                from textual.widgets import Input

                # Starting URL input pre-filled.
                starting = app.screen.query_one(
                    "#input-starting_url-url", Input
                )
                assert starting.value == "https://shop.example.com/checkout"

                # Variable "email" pre-filled with its declared default.
                email = app.screen.query_one("#input-variable-email", Input)
                assert email.value == "default@x.com"

                # Secret field present with empty default + password=True.
                pw = app.screen.query_one("#input-secret-admin_pw", Input)
                assert pw.value == ""
                assert pw.password is True

        asyncio.run(_run())

    def test_R_before_bundle_loaded_shows_warning(self):
        """If the user hits R before the fetch completes, we surface a
        warning notification instead of opening a half-built form."""

        async def _run():
            api = _make_api()
            # Delay the fetch by blocking on a call we never resolve.
            done = asyncio.Event()

            def slow_get_usecase(usecase_id):
                import time
                time.sleep(0.1)
                return {"name": "slow"}

            api.get_usecase.side_effect = slow_get_usecase

            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.usecase_detail import (
                    UsecaseDetailScreen,
                )

                app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                # Press R immediately, before the worker finishes.
                await pilot.press("R")
                await pilot.pause()

                # Still on the detail screen; no RunFormScreen pushed.
                assert isinstance(app.screen, UsecaseDetailScreen)

        asyncio.run(_run())

    def test_cancel_button_returns_to_detail(self):
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

                from qa_studio_cli.tui.screens.run_form import RunFormScreen

                assert isinstance(app.screen, RunFormScreen)

                # Esc cancels.
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(app.screen, UsecaseDetailScreen)

        asyncio.run(_run())

    def test_submit_builds_correct_argv_and_opens_livetail(self):
        """Change the email variable, submit, assert the pushed
        LiveTailScreen's RunnerProcess argv contains the override."""

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

                from qa_studio_cli.tui.screens.run_form import RunFormScreen

                assert isinstance(app.screen, RunFormScreen)

                # Change the email variable input.
                from textual.widgets import Input

                email_input = app.screen.query_one(
                    "#input-variable-email", Input
                )
                email_input.value = "dev@example.com"
                await pilot.pause()

                # Prevent the LiveTail worker from actually running the
                # subprocess — we only want to verify the argv that
                # got threaded through.
                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen

                with patch.object(LiveTailScreen, "on_mount", lambda self: None):
                    await pilot.press("ctrl+s")
                    await pilot.pause()

                assert isinstance(app.screen, LiveTailScreen)
                argv = app.screen._runner.argv
                # Variable override threaded through.
                assert "--var" in argv
                assert "email=dev@example.com" in argv
                # Usecase id present.
                assert "--usecase-id" in argv
                assert "u-1" in argv
                # Local-only preserved.
                assert "--local-only" in argv
                # Verbose is opt-in via the checkbox — default submit
                # must NOT pass --verbose.
                assert "--verbose" not in argv
                # Live-tail is for humans — format stays on "human"
                # so the runner prints the pretty summary at the end
                # rather than a JSON blob.
                i = argv.index("--format")
                assert argv[i + 1] == "human"

        asyncio.run(_run())

    def test_verbose_checkbox_adds_verbose_flag(self):
        """With the Verbose checkbox ticked, the subprocess argv
        must include ``--verbose`` (DEBUG-level logs)."""

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
                from qa_studio_cli.tui.screens.run_form import RunFormScreen

                assert isinstance(app.screen, RunFormScreen)
                # Tick the checkbox.
                app.screen.query_one("#verbose-toggle", Checkbox).value = True
                await pilot.pause()

                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen

                with patch.object(LiveTailScreen, "on_mount", lambda self: None):
                    await pilot.press("ctrl+s")
                    await pilot.pause()

                assert isinstance(app.screen, LiveTailScreen)
                assert "--verbose" in app.screen._runner.argv

    def test_local_only_default_is_on(self):
        """Default form submit must still pass ``--local-only`` so
        behaviour is unchanged for existing users."""
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

                assert "--local-only" in app.screen._runner.argv

        asyncio.run(_run())

    def test_unticking_local_only_drops_the_flag(self):
        """Unticking the checkbox enables the remote execution path —
        the subprocess argv must not carry ``--local-only``."""
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
                from qa_studio_cli.tui.screens.run_form import RunFormScreen
                assert isinstance(app.screen, RunFormScreen)
                app.screen.query_one("#local-only-toggle", Checkbox).value = False
                await pilot.pause()

                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen
                with patch.object(LiveTailScreen, "on_mount", lambda self: None):
                    await pilot.press("ctrl+s")
                    await pilot.pause()

                assert "--local-only" not in app.screen._runner.argv

        asyncio.run(_run())

    def test_remote_with_header_override_is_rejected(self):
        """Header / secret overrides are local-only at the CLI layer.
        If the user unticks local-only AND has entered a header
        override, the submit must be blocked at the form so the error
        surfaces in the TUI rather than a few seconds into the run."""
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

                from textual.widgets import Checkbox, Input
                from qa_studio_cli.tui.screens.run_form import RunFormScreen

                assert isinstance(app.screen, RunFormScreen)
                # Change the X-Trace header from its default.
                header_input = app.screen.query_one(
                    "#input-header-X-Trace", Input
                )
                header_input.value = "changed"
                # Untick local-only.
                app.screen.query_one("#local-only-toggle", Checkbox).value = False
                await pilot.pause()

                await pilot.press("ctrl+s")
                await pilot.pause()

                # Submit rejected — still on the form.
                assert isinstance(app.screen, RunFormScreen)

        asyncio.run(_run())

    def test_remote_without_header_overrides_submits(self):
        """Unticking local-only with no header / secret overrides
        should submit cleanly (no validation error)."""
        async def _run():
            api = _make_api()
            # Clean bundle — empty defaults that won't trigger an
            # override on submit.
            api.get_headers.return_value = {}
            api.get_secrets.return_value = []
            app = QAStudioTUIApp(tui_api=api)
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
                from qa_studio_cli.tui.screens.run_form import RunFormScreen

                assert isinstance(app.screen, RunFormScreen)
                app.screen.query_one("#local-only-toggle", Checkbox).value = False
                await pilot.pause()

                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen
                with patch.object(LiveTailScreen, "on_mount", lambda self: None):
                    await pilot.press("ctrl+s")
                    await pilot.pause()

                # Transitioned to the live tail — submit was accepted.
                assert isinstance(app.screen, LiveTailScreen)
                argv = app.screen._runner.argv
                assert "--local-only" not in argv
                # No header/secret files created.
                assert "--headers-file" not in argv
                assert "--secrets-file" not in argv

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# LiveTailScreen
# ---------------------------------------------------------------------------


class TestLiveTailScreen:
    def test_successful_run_shows_passed_status(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen

                runner = _snippet_runner("print('hello'); print('done')")
                app.push_screen(LiveTailScreen(runner))

                # Wait for the worker to process the child.
                for _ in range(40):
                    await pilot.pause()
                    if app.screen._done:
                        break

                assert app.screen._done is True
                assert app.screen._result.exit_code == 0

                from textual.widgets import Static

                status = str(
                    app.screen.query_one("#livetail-status", Static).renderable
                )
                assert "PASSED" in status

        asyncio.run(_run())

    def test_failing_run_shows_failed_status(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen

                runner = _snippet_runner("import sys; sys.exit(7)")
                app.push_screen(LiveTailScreen(runner))

                for _ in range(40):
                    await pilot.pause()
                    if app.screen._done:
                        break

                assert app.screen._done is True
                assert app.screen._result.exit_code == 7

                from textual.widgets import Static

                status = str(
                    app.screen.query_one("#livetail-status", Static).renderable
                )
                assert "FAILED" in status
                assert "7" in status

        asyncio.run(_run())

    def test_escape_before_done_shows_warning_and_does_not_pop(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen

                # Long-running child — we'll terminate it ourselves.
                runner = _snippet_runner("import time; time.sleep(30)")
                app.push_screen(LiveTailScreen(runner))
                await pilot.pause()
                await pilot.pause()

                assert isinstance(app.screen, LiveTailScreen)

                # Try to escape while still running.
                await pilot.press("escape")
                await pilot.pause()

                # Still on LiveTailScreen; not popped.
                assert isinstance(app.screen, LiveTailScreen)

                # Clean up: terminate + wait for completion.
                await app.screen.action_terminate()
                for _ in range(40):
                    await pilot.pause()
                    if app.screen._done:
                        break

        asyncio.run(_run())

    def test_escape_after_done_pops(self):
        async def _run():
            app = QAStudioTUIApp(tui_api=_make_api())
            async with app.run_test() as pilot:
                await pilot.pause()
                from qa_studio_cli.tui.screens.live_tail import LiveTailScreen
                from qa_studio_cli.tui.screens.usecases_list import (
                    UsecasesListScreen,
                )

                runner = _snippet_runner("pass")
                app.push_screen(LiveTailScreen(runner))

                for _ in range(40):
                    await pilot.pause()
                    if app.screen._done:
                        break

                await pilot.press("escape")
                await pilot.pause()

                # Popped back down to the initial screen.
                assert isinstance(app.screen, UsecasesListScreen)

        asyncio.run(_run())
