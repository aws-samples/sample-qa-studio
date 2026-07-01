"""Tests for the ``[ Usecases (N) ] [ Test Suites (M) ]`` tab counts
in :class:`AppHeader`.

Covers:

* The app's shared ``tab_counts`` cache is seeded with ``None`` for
  both tabs and can be updated via :meth:`set_tab_count`.
* A ``set_tab_count`` update refreshes every visible ``AppHeader``
  instance immediately — no screen navigation required.
* List screens push their fetched ``len(items)`` through
  ``set_tab_count`` on successful load.
* When the app opens a screen without a pre-populated cache, the
  header's lazy-fetch worker fills in the counts from the API so
  both badges render even before the user visits the other tab.
* Clicks on the tabs still dispatch correctly after the label text
  changes (the handler matches on widget id, not label text).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

pytest.importorskip("textual")

from textual.widgets import Static  # noqa: E402

from qa_studio_cli.tui.api import (  # noqa: E402
    SuiteListItem,
    TuiApi,
    UsecaseListItem,
)
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.app_header import AppHeader  # noqa: E402
from qa_studio_cli.tui.screens.suites_list import SuitesListScreen  # noqa: E402
from qa_studio_cli.tui.screens.usecases_list import UsecasesListScreen  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_api(
    *,
    usecases: list[UsecaseListItem] | None = None,
    suites: list[SuiteListItem] | None = None,
) -> MagicMock:
    api = MagicMock(spec=TuiApi)
    # ``is None`` check so an explicitly empty list isn't silently
    # replaced with the default sample data (the same bug caught
    # earlier in tests/test_tui_list_run_shortcut.py).
    if usecases is None:
        usecases = [
            UsecaseListItem("u-1", "Login", "web", "us-east-1"),
            UsecaseListItem("u-2", "Checkout", "web", "us-east-1"),
            UsecaseListItem("u-3", "Profile", "web", "us-east-1"),
        ]
    if suites is None:
        suites = [
            SuiteListItem("s-1", "Smoke", 3, "happy paths"),
            SuiteListItem("s-2", "Regression", 42, "full"),
        ]
    api.list_usecases.return_value = usecases
    api.list_suites.return_value = suites
    return api


def _label_text(screen, tab_id: str) -> str:
    """Return the current renderable text for a tab Static."""
    return str(screen.query_one(f"#{tab_id}", Static).renderable)


# ---------------------------------------------------------------------------
# App-level cache
# ---------------------------------------------------------------------------


class TestAppTabCountsCache:
    def test_defaults_to_none_for_both_tabs(self):
        api = _make_api(usecases=[], suites=[])
        app = QAStudioTUIApp(tui_api=api)
        # ``__init__`` seeds the cache before mount.
        assert app.tab_counts == {"usecases": None, "suites": None}

    def test_set_tab_count_updates_cache(self):
        api = _make_api(usecases=[], suites=[])
        app = QAStudioTUIApp(tui_api=api)
        app.set_tab_count("usecases", 7)
        assert app.tab_counts["usecases"] == 7
        assert app.tab_counts["suites"] is None

    def test_set_tab_count_ignores_unknown_tabs(self):
        """Defensive — a typo like ``set_tab_count("users", 1)``
        must not poison the cache with a new key that the header
        doesn't know how to render."""
        api = _make_api(usecases=[], suites=[])
        app = QAStudioTUIApp(tui_api=api)
        app.set_tab_count("users", 1)
        assert "users" not in app.tab_counts


# ---------------------------------------------------------------------------
# Label rendering
# ---------------------------------------------------------------------------


class TestAppHeaderLabelRendering:
    def test_unknown_counts_render_bare_labels(self):
        async def _run():
            # ``list_*`` raise → lazy fetch can't populate counts,
            # labels should stay bare rather than flashing ``(?)``.
            api = MagicMock(spec=TuiApi)
            api.list_usecases.side_effect = RuntimeError("offline")
            api.list_suites.side_effect = RuntimeError("offline")
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                header = app.screen.query_one(AppHeader)
                # Depending on timing, the lazy fetch may or may not
                # have returned by the time we check — because both
                # API calls raise, neither count will be populated
                # regardless. The bare label is the correct render.
                assert _label_text(header, "tab-usecases") == "[ Usecases ]"
                assert _label_text(header, "tab-suites") == "[ Test Suites ]"

        asyncio.run(_run())

    def test_known_counts_render_in_parens(self):
        async def _run():
            api = _make_api(usecases=[], suites=[])  # will push 0/0
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                # Seed the cache directly, then refresh visible header.
                app.set_tab_count("usecases", 12)
                app.set_tab_count("suites", 4)
                header = app.screen.query_one(AppHeader)
                assert _label_text(header, "tab-usecases") == "[ Usecases (12) ]"
                assert _label_text(header, "tab-suites") == "[ Test Suites (4) ]"

        asyncio.run(_run())

    def test_set_tab_count_refreshes_all_visible_headers(self):
        """The update path used by list screens and the lazy fetch
        must propagate to whichever ``AppHeader`` is mounted —
        including a detail screen's header, not just the list's."""

        async def _run():
            api = _make_api(usecases=[], suites=[])
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                # Navigate to suites, which has its own AppHeader.
                app.push_screen(SuitesListScreen())
                await pilot.pause()
                await pilot.pause()

                app.set_tab_count("usecases", 99)
                header = app.screen.query_one(AppHeader)
                assert _label_text(header, "tab-usecases") == "[ Usecases (99) ]"

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# List screens push counts on successful load
# ---------------------------------------------------------------------------


class TestListScreensPushCount:
    def test_usecases_load_pushes_count(self):
        async def _run():
            api = _make_api()  # default 3 usecases
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                # The initial screen is UsecasesListScreen; its
                # successful load must seed the usecases count.
                assert app.tab_counts["usecases"] == 3
                header = app.screen.query_one(AppHeader)
                assert _label_text(header, "tab-usecases") == "[ Usecases (3) ]"

        asyncio.run(_run())

    def test_suites_load_pushes_count(self):
        async def _run():
            api = _make_api()  # default 2 suites
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SuitesListScreen())
                await pilot.pause()
                await pilot.pause()
                assert app.tab_counts["suites"] == 2
                header = app.screen.query_one(AppHeader)
                assert _label_text(header, "tab-suites") == "[ Test Suites (2) ]"

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Lazy fetch for counts of tabs the user hasn't visited
# ---------------------------------------------------------------------------


class TestHeaderLazyFetch:
    def test_header_populates_suites_count_without_visiting_suites(self):
        """Landing on the usecases list should still show a badge on
        the Test Suites tab — the header kicks off its own fetch for
        any count the cache is still missing.
        """

        async def _run():
            api = _make_api(
                usecases=[
                    UsecaseListItem("u-1", "Login", "web", "us-east-1"),
                ],
                suites=[
                    SuiteListItem("s-1", "Smoke", 3, "x"),
                    SuiteListItem("s-2", "Regression", 42, "y"),
                    SuiteListItem("s-3", "Nightly", 1, "z"),
                ],
            )
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                # One pause for the list-screen worker, another for
                # the header's lazy-fetch worker + DOM refresh.
                await pilot.pause()
                await pilot.pause()
                await pilot.pause()
                assert app.tab_counts["suites"] == 3
                header = app.screen.query_one(AppHeader)
                assert _label_text(header, "tab-suites") == "[ Test Suites (3) ]"

        asyncio.run(_run())

    def test_lazy_fetch_skips_when_cache_already_populated(self):
        """If the cache already has both counts (e.g. user has
        visited both lists already), the header's lazy-fetch worker
        must not fire a redundant API call.
        """

        async def _run():
            api = _make_api(usecases=[], suites=[])
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                # Seed both counts directly — simulates the user
                # having already visited both lists.
                app.set_tab_count("usecases", 10)
                app.set_tab_count("suites", 20)
                api.list_usecases.reset_mock()
                api.list_suites.reset_mock()
                # Push a fresh screen so a new AppHeader mounts.
                app.push_screen(SuitesListScreen())
                await pilot.pause()
                await pilot.pause()

                # SuitesListScreen itself calls list_suites on mount,
                # but the *header* should NOT call it a second time
                # for its lazy fetch — the cache is fully seeded.
                # A non-trivial assertion because the header also
                # shouldn't call list_usecases at all.
                api.list_usecases.assert_not_called()

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Regression — click dispatch is id-based, not label-based
# ---------------------------------------------------------------------------


class TestClickStillWorksAfterLabelChange:
    def test_clicking_suites_tab_still_navigates(self):
        async def _run():
            api = _make_api()
            app = QAStudioTUIApp(tui_api=api)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                header = app.screen.query_one(AppHeader)
                # Label now includes a count — click dispatch must
                # still match on the widget id.
                assert "(" in _label_text(header, "tab-suites")
                suites_tab = header.query_one("#tab-suites", Static)
                await pilot.click(suites_tab)
                await pilot.pause()
                await pilot.pause()
                assert isinstance(app.screen, SuitesListScreen)

        asyncio.run(_run())
