"""Pure helpers of qa_studio_cli.tui.screens._base_detail."""
import pytest

pytest.importorskip("textual")

from qa_studio_cli.tui.screens._base_detail import (  # noqa: E402
    format_field_value,
    is_empty_value,
    step_field_lines,
)


@pytest.mark.parametrize("value,empty", [
    (None, True), ("", True), ("  ", True), ([], True), ({}, True),
    (False, False), (0, False), ("x", False), ([1], False),
])
def test_is_empty_value(value, empty):
    assert is_empty_value(value) is empty


def test_format_field_value_pretty_prints_collections():
    assert format_field_value(3) == "3"
    assert format_field_value({"a": 1}) == '\n{\n  "a": 1\n}'


def test_priority_first_then_alphabetical_skipping_empty():
    step = {"zeta": "z", "instruction": "Click", "alpha": "", "beta": 0, "step_type": "navigation"}
    assert step_field_lines(step, priority=["step_type", "instruction"]) == [
        "[cyan]step_type[/]: navigation",
        "[cyan]instruction[/]: Click",
        "[cyan]beta[/]: 0",
        "[cyan]zeta[/]: z",
    ]


def test_custom_formatter_gets_the_key():
    lines = step_field_lines({"status": "ok"}, priority=[], format_value=lambda k, v: f"{k}={v}")
    assert lines == ["[cyan]status[/]: status=ok"]
