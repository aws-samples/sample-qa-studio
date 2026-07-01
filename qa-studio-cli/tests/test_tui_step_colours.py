"""Unit tests for the per-step-type colour mapping."""

import pytest

pytest.importorskip("textual")

from qa_studio_cli.tui.screens.usecase_detail import (  # noqa: E402
    _STEP_TYPE_COLOURS,
    _step_type_cell,
)


class TestStepTypeColours:
    def test_every_known_step_type_has_a_colour(self):
        """The runner's ``StepExecutor.dispatch`` branches on these
        ten keys — if any is missing from the map the Steps table
        would render a blank cell which is a silent UX regression."""
        expected = {
            "navigation",
            "validation",
            "assertion",
            "network_assertion",
            "retrieve_value",
            "url",
            "secret",
            "download",
            "browser",
            "transform",
        }
        assert set(_STEP_TYPE_COLOURS) == expected

    def test_colours_are_unique(self):
        """Each step type gets its own colour so a user can tell two
        adjacent rows of different types apart at a glance."""
        values = list(_STEP_TYPE_COLOURS.values())
        assert len(values) == len(set(values))

    def test_known_type_wraps_with_markup(self):
        cell = _step_type_cell("navigation")
        assert cell.startswith("[cyan]")
        assert cell.endswith("[/]")
        assert "navigation" in cell

    def test_unknown_type_falls_back_to_white(self):
        cell = _step_type_cell("some_new_type")
        assert cell.startswith("[white]")
        assert "some_new_type" in cell

    def test_case_insensitive_match(self):
        """API payloads sometimes arrive in mixed case — the map
        lookup lowercases to stay robust."""
        cell = _step_type_cell("Navigation")
        assert cell.startswith("[cyan]")
