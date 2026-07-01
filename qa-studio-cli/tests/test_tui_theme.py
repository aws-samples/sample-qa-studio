"""Tests for the qa-studio-dark Textual theme.

Two layers:

1. Pure assertions on the module-level ``QA_STUDIO_DARK_THEME``
   singleton — palette values, dark flag, name. These run without a
   Textual app and protect against accidental palette regressions.

2. One integration test that mounts :class:`QAStudioTUIApp` and
   verifies the theme is registered and active after ``on_mount``.
   Follows the same ``asyncio.run`` pattern as
   ``tests/test_tui_app.py`` to avoid pulling in pytest-asyncio.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

pytest.importorskip("textual")

from qa_studio_cli.tui.api import TuiApi  # noqa: E402
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.theme import QA_STUDIO_DARK_THEME, THEME_NAME  # noqa: E402


# --- Palette assertions --------------------------------------------------

class TestThemeDefinition:
    """Guard the palette against silent drift.

    The concrete hex values matter: designers sign off on the visual
    feel and tests elsewhere (e.g. ``styles.tcss`` usage) assume
    contrast levels that come out of these specific colours. If a
    value needs to change, update the test deliberately alongside
    the theme module.
    """

    def test_name_is_qa_studio_dark(self):
        assert QA_STUDIO_DARK_THEME.name == THEME_NAME == "qa-studio-dark"

    def test_is_dark_theme(self):
        assert QA_STUDIO_DARK_THEME.dark is True

    def test_primary_is_dracula_green(self):
        # Green is the brand accent — drives focus rings and
        # primary buttons.
        assert QA_STUDIO_DARK_THEME.primary.lower() == "#50fa7b"

    def test_accent_distinct_from_primary(self):
        # styles.tcss uses $accent for separators; keeping it
        # different from $primary stops focus highlights and panel
        # borders from blending together.
        assert QA_STUDIO_DARK_THEME.accent is not None
        assert (
            QA_STUDIO_DARK_THEME.accent.lower()
            != QA_STUDIO_DARK_THEME.primary.lower()
        )

    def test_background_is_dracula_base(self):
        assert QA_STUDIO_DARK_THEME.background.lower() == "#282a36"

    def test_foreground_is_dracula_fg(self):
        assert QA_STUDIO_DARK_THEME.foreground.lower() == "#f8f8f2"

    def test_error_and_warning_are_set(self):
        # These feed into toast/notification chrome; regressions
        # here are hard to notice visually until something fails.
        assert QA_STUDIO_DARK_THEME.error is not None
        assert QA_STUDIO_DARK_THEME.warning is not None

    def test_selection_variable_configured(self):
        # Explicit variables we set in theme.py — the rest are left
        # to Textual's derivation so we don't over-specify here.
        assert (
            "input-selection-background" in QA_STUDIO_DARK_THEME.variables
        )


# --- App integration -----------------------------------------------------

def _make_app_with_empty_api() -> QAStudioTUIApp:
    """Minimal app that won't hit the network during mount."""
    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = []
    return QAStudioTUIApp(tui_api=api)


class TestThemeActivation:
    """Verify the theme reaches the live app, not just the module."""

    def test_theme_registered_on_mount(self):
        async def _run():
            app = _make_app_with_empty_api()
            async with app.run_test() as pilot:
                await pilot.pause()
                assert THEME_NAME in app.available_themes
                registered = app.get_theme(THEME_NAME)
                assert registered is QA_STUDIO_DARK_THEME

        asyncio.run(_run())

    def test_theme_is_active_after_mount(self):
        async def _run():
            app = _make_app_with_empty_api()
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app.theme == THEME_NAME

        asyncio.run(_run())
