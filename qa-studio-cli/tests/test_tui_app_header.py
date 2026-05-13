"""Tests for the shared :class:`AppHeader` widget.

Three layers:

1. **Static shape** — the logo must stay a clean 3×33 rectangle.
   Hand-authored ASCII art drifts easily; this test pins it so an
   accidental edit fails CI instead of silently producing a ragged
   block.

2. **Mount-time integration** — pushing a screen into the app should
   produce exactly one ``AppHeader``, the version widget should
   render ``v{__version__}``, the active-tab argument should
   translate into the ``-active`` CSS class on the right tab, and
   the identity row should render whatever
   :func:`get_display_identity` returns.

3. **Click navigation** — clicking a tab should dispatch the same
   app action (``action_show_usecases`` / ``action_show_suites``)
   that the ``1`` / ``2`` keyboard bindings already use.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("textual")

from textual.widgets import Static  # noqa: E402

from qa_studio_cli import __version__  # noqa: E402
from qa_studio_cli.tui.api import TuiApi  # noqa: E402
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.app_header import (  # noqa: E402
    TAB_SUITES,
    TAB_USECASES,
    AppHeader,
)
from qa_studio_cli.tui.screens.suites_list import SuitesListScreen  # noqa: E402


# --- Static shape -------------------------------------------------------

class TestAppHeaderLogo:
    def test_logo_has_three_rows(self):
        rows = AppHeader.LOGO.splitlines()
        assert len(rows) == 3, f"expected 3 rows, got {len(rows)}"

    def test_rows_are_same_width(self):
        rows = AppHeader.LOGO.splitlines()
        widths = {len(row) for row in rows}
        assert len(widths) == 1, (
            f"rows have varying widths: {widths} — logo must be a rectangle"
        )

    def test_logo_fits_in_compact_terminals(self):
        max_width = max(len(row) for row in AppHeader.LOGO.splitlines())
        # Header also carries version + tabs on the right. 33 logo + ~25
        # right column + 2 padding ≈ 60 cols total, well under 80.
        assert max_width <= 40, f"logo wider than expected: {max_width}"

    def test_tab_constants_are_stable(self):
        # Screens pass these as class attributes — renaming them would
        # silently stop the active-tab highlight from working.
        assert TAB_USECASES == "usecases"
        assert TAB_SUITES == "suites"


# --- App integration ----------------------------------------------------

def _make_app_with_empty_api() -> QAStudioTUIApp:
    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = []
    api.list_suites.return_value = []
    return QAStudioTUIApp(tui_api=api)


class TestAppHeaderOnScreens:
    def test_landing_screen_mounts_exactly_one_app_header(self):
        async def _run():
            app = _make_app_with_empty_api()
            async with app.run_test() as pilot:
                await pilot.pause()
                headers = app.screen.query(AppHeader)
                assert len(headers) == 1

        asyncio.run(_run())

    def test_version_rendered_in_header(self):
        async def _run():
            app = _make_app_with_empty_api()
            async with app.run_test() as pilot:
                await pilot.pause()
                header = app.screen.query_one(AppHeader)
                version_widget = header.query_one(
                    "#app-header-version", Static
                )
                assert str(version_widget.renderable) == f"v{__version__}"

        asyncio.run(_run())

    def test_usecases_tab_active_on_landing(self):
        """Landing screen is the usecases list — ``Usecases`` tab
        should carry the ``-active`` class, ``Test Suites`` should not."""

        async def _run():
            app = _make_app_with_empty_api()
            async with app.run_test() as pilot:
                await pilot.pause()
                header = app.screen.query_one(AppHeader)
                usecases = header.query_one("#tab-usecases", Static)
                suites = header.query_one("#tab-suites", Static)
                assert usecases.has_class("-active")
                assert not suites.has_class("-active")

        asyncio.run(_run())

    def test_suites_tab_active_on_suites_screen(self):
        async def _run():
            app = _make_app_with_empty_api()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuitesListScreen())
                await pilot.pause()
                header = app.screen.query_one(AppHeader)
                usecases = header.query_one("#tab-usecases", Static)
                suites = header.query_one("#tab-suites", Static)
                assert suites.has_class("-active")
                assert not usecases.has_class("-active")

        asyncio.run(_run())


# --- Click dispatch -----------------------------------------------------

class TestAppHeaderClickDispatch:
    def test_clicking_suites_tab_switches_to_suites_screen(self):
        """End-to-end: from the landing (usecases) screen, click the
        ``Test Suites`` tab and confirm the app actually navigates."""

        async def _run():
            app = _make_app_with_empty_api()
            async with app.run_test() as pilot:
                await pilot.pause()
                header = app.screen.query_one(AppHeader)
                suites_tab = header.query_one("#tab-suites", Static)
                # ``pilot.click`` targets the widget at its region —
                # more realistic than calling on_click directly.
                await pilot.click(suites_tab)
                await pilot.pause()
                await pilot.pause()

                # After the click, the active screen should be the
                # suites list. We assert via class name to keep the
                # import footprint of this test module tight.
                assert type(app.screen).__name__ == "SuitesListScreen"

        asyncio.run(_run())

    def test_clicking_usecases_tab_from_suites_returns_home(self):
        async def _run():
            app = _make_app_with_empty_api()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuitesListScreen())
                await pilot.pause()

                header = app.screen.query_one(AppHeader)
                usecases_tab = header.query_one("#tab-usecases", Static)
                await pilot.click(usecases_tab)
                await pilot.pause()
                await pilot.pause()

                assert type(app.screen).__name__ == "UsecasesListScreen"

        asyncio.run(_run())


# --- Identity row -------------------------------------------------------
#
# The identity row renders whatever
# :func:`qa_studio_cli.auth.identity.get_display_identity` returns.  We
# patch that function so the tests don't depend on the developer's
# machine having (or not having) a ``~/.qa-studio/token.json``.


class TestAppHeaderIdentityRow:
    def test_identity_widget_rendered_when_identity_available(self):
        async def _run():
            with patch(
                "qa_studio_cli.tui.app_header.get_display_identity",
                return_value="alice@example.com",
            ):
                app = _make_app_with_empty_api()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    header = app.screen.query_one(AppHeader)
                    identity_widget = header.query_one(
                        "#app-header-identity", Static
                    )
                    assert (
                        str(identity_widget.renderable) == "alice@example.com"
                    )

        asyncio.run(_run())

    def test_identity_widget_empty_when_no_identity(self):
        """No crash, no placeholder text — the row is reserved but blank."""

        async def _run():
            with patch(
                "qa_studio_cli.tui.app_header.get_display_identity",
                return_value=None,
            ):
                app = _make_app_with_empty_api()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    header = app.screen.query_one(AppHeader)
                    identity_widget = header.query_one(
                        "#app-header-identity", Static
                    )
                    assert str(identity_widget.renderable) == ""

        asyncio.run(_run())

    def test_identity_resolver_exception_is_swallowed(self):
        """A raising resolver must not crash the header — the identity
        row falls back to empty and the rest of the TUI keeps working."""

        async def _run():
            with patch(
                "qa_studio_cli.tui.app_header.get_display_identity",
                side_effect=RuntimeError("boom"),
            ):
                app = _make_app_with_empty_api()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    header = app.screen.query_one(AppHeader)
                    identity_widget = header.query_one(
                        "#app-header-identity", Static
                    )
                    assert str(identity_widget.renderable) == ""

        asyncio.run(_run())
