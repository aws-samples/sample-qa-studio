"""Shared renderers for step-type cells and duration strings.

Used by both :class:`UsecaseDetailScreen` (steps definition) and
:class:`ExecutionDetailScreen` (steps as executed). Keeping the
colour map in one place stops the two screens from drifting when a
new step type is added.
"""

from __future__ import annotations

from typing import Dict


#: Per-step-type colours for the Steps tables across detail screens.
#: Keys are lowercase to match API payloads; unknown types fall
#: through to a neutral default so a new server-side step type doesn't
#: render blank.
STEP_TYPE_COLOURS: Dict[str, str] = {
    "navigation":        "cyan",
    "validation":        "blue",
    "assertion":         "green",
    "network_assertion": "bright_cyan",
    "retrieve_value":    "magenta",
    "url":               "bright_blue",
    "secret":            "yellow",
    "download":          "orange1",
    "browser":           "purple",
    "transform":         "bright_magenta",
}


#: Colours for execution / step status values.  Any unknown status
#: falls back to ``white`` rather than rendering blank.
STATUS_COLOURS: Dict[str, str] = {
    "success":   "green",
    "failed":    "red",
    "error":     "red",
    "stopped":   "yellow",
    "running":   "cyan",
    "executing": "cyan",
    "pending":   "yellow",
    "skipped":   "dim",
    # Suite-execution-specific terminal statuses — a suite is
    # ``completed`` when every usecase succeeded and ``partial``
    # when the run finished with a mix of pass/fail.
    "completed": "green",
    "partial":   "yellow",
}


def step_type_cell(step_type: str) -> str:
    """Rich-markup-wrapped step type for rendering in a DataTable cell."""
    colour = STEP_TYPE_COLOURS.get(step_type.lower(), "white")
    return f"[{colour}]{step_type}[/]"


def status_cell(status: str) -> str:
    """Rich-markup-wrapped status cell."""
    colour = STATUS_COLOURS.get(status.lower(), "white")
    return f"[{colour}]{status}[/]"


def format_duration(seconds: float) -> str:
    """Compact duration renderer — matches the runner's ``SummaryFormatter``."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes}m"


# ---------------------------------------------------------------------------
# Validation block — mirrors the web ``ValidationResult`` component so the
# TUI's step detail pane surfaces the same comparison at a glance.
# ---------------------------------------------------------------------------


#: Human-facing labels for the stored validation types.
VALIDATION_TYPE_LABELS: Dict[str, str] = {
    "bool": "Boolean",
    "string": "Text",
    "number": "Number",
}

#: Human-facing labels for the stored operators. Keys match the API
#: values (``exact``, ``greater_then`` etc.) verbatim.
OPERATOR_LABELS: Dict[str, str] = {
    "exact": "Equals",
    "equals": "Equals",
    "exact_case_insensitive": "Equals (case insensitive)",
    "contains": "Contains",
    "contains_case_insensitive": "Contains (case insensitive)",
    "not_equal": "Not Equal",
    "greater_then": "Greater Than",
    "less_then": "Less Than",
    "greater_or_equal_then": "Greater Than or Equal",
    "less_or_equal_then": "Less Than or Equal",
}

#: Unicode comparison symbols — same choices as the web component.
OPERATOR_SYMBOLS: Dict[str, str] = {
    "exact": "=",
    "equals": "=",
    "exact_case_insensitive": "≈",
    "contains": "∋",
    "contains_case_insensitive": "∋",
    "not_equal": "≠",
    "greater_then": ">",
    "less_then": "<",
    "greater_or_equal_then": "≥",
    "less_or_equal_then": "≤",
}


def render_validation_block(
    *,
    validation_type: str,
    validation_operator: str,
    validation_value: str,
    actual_value: str | None = None,
    status: str | None = None,
) -> str:
    """Build a Rich-markup snippet describing a step's validation.

    Returned string is a two- or three-line block ready to be handed
    to a ``Static.update()`` call (or prepended to a larger block):

    - Header line — ``<type> (<operator label>)`` in dim text.
    - Comparison line — when ``actual_value`` is supplied (execution
      context), colours the actual value green on ``status=='success'``
      and red otherwise; shows ``actual <symbol> expected``. When the
      actual is ``None`` (usecase definition, no run yet), the line
      just shows ``<symbol> <expected>``.

    Returns an empty string when ``validation_type`` is empty so
    callers can unconditionally prepend the result to the pane.
    """
    if not validation_type:
        return ""

    type_label = VALIDATION_TYPE_LABELS.get(
        validation_type.lower(), validation_type
    )
    op_label = OPERATOR_LABELS.get(
        validation_operator.lower(), validation_operator
    )
    symbol = OPERATOR_SYMBOLS.get(validation_operator.lower(), "?")
    expected = validation_value if validation_value != "" else "[dim](empty)[/]"

    lines: list[str] = [f"[dim]{type_label} ({op_label})[/]"]

    if actual_value is None:
        lines.append(f"  [dim]{symbol}[/]  [b]{expected}[/]")
    else:
        colour = "green" if (status or "").lower() == "success" else "red"
        shown_actual = actual_value if actual_value != "" else "[dim](empty)[/]"
        lines.append(
            f"  [b {colour}]{shown_actual}[/]  [dim]{symbol}[/]  "
            f"[b]{expected}[/]"
        )

    return "\n".join(lines)
