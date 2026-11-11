"""Execution detail screen.

Shows everything the API knows about a single execution: status +
timestamps + duration in the header, an error banner when applicable,
and a vertical-split steps view where the left-hand table carries the
step status / duration and the right-hand pane renders the full step
payload (actual vs expected values, error messages, logs, etc.).

Mirrors the Steps tab on :class:`UsecaseDetailScreen` — the same
split, the same live-updating detail pane — because executions *are*
usecase steps with results attached.
"""

from __future__ import annotations

from typing import Any, Dict, List

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

from qa_studio_cli.tui.app_header import TAB_USECASES, AppHeader
from qa_studio_cli.tui.border_pulse import LoadPulseMixin
from qa_studio_cli.tui.screens._base_detail import ProgressiveLoadMixin, format_field_value, step_field_lines
from qa_studio_cli.tui.step_render import (
    format_duration,
    render_validation_block,
    status_cell,
    step_type_cell,
)


_STEP_DETAIL_PLACEHOLDER = "Select a step (arrow keys) to see its full details."


class ExecutionDetailScreen(ProgressiveLoadMixin, LoadPulseMixin, Screen):
    """Single-execution detail view."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("r", "refresh", "Refresh"),
    ]

    LOAD_PULSE_TARGET = "AppHeader"

    def __init__(self, usecase_id: str, execution_id: str):
        super().__init__()
        self._usecase_id = usecase_id
        self._execution_id = execution_id
        self._ordered_steps: List[Dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        yield AppHeader(active=TAB_USECASES)
        yield Static("Loading…", id="execution-status", markup=True)
        with Vertical(id="execution-body"):
            yield Static("", id="execution-metadata", markup=True)
            yield Static("", id="execution-error", markup=True)
            with Horizontal(id="execution-steps-split"):
                yield DataTable(
                    id="execution-steps-table",
                    cursor_type="row",
                    zebra_stripes=True,
                )
                with VerticalScroll(id="execution-step-detail-scroll"):
                    yield Static(
                        _STEP_DETAIL_PLACEHOLDER,
                        id="execution-step-detail-text",
                        markup=True,
                    )
        yield Footer()

    def on_mount(self) -> None:
        table: DataTable = self.query_one("#execution-steps-table", DataTable)
        table.add_columns("#", "Type", "Status", "Duration", "Instruction")
        self._install_load_pulse()
        self._start_load_pulse()
        self._load_detail()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        self._start_load_pulse()
        self._load_detail()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "execution-steps-table":
            return
        if event.row_key is None or event.row_key.value is None:
            return
        try:
            idx = int(event.row_key.value) - 1
        except (TypeError, ValueError):
            return
        if idx < 0 or idx >= len(self._ordered_steps):
            return
        self._render_step_detail(self._ordered_steps[idx])

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    #
    # Loading strategy: fetch the two rendered sub-resources
    # (execution metadata and steps) in parallel and render each one
    # as its API call returns. Previously this screen called a
    # composite endpoint that did four serial HTTP calls — two of them
    # (``variables`` / ``headers``) were fetched but never rendered,
    # so they've been dropped here. Time-to-first-paint is now bounded
    # by the faster of the two remaining calls, and the slower one
    # fills in without blocking the first.
    #
    # Identical shape to ``UsecaseDetailScreen._load_detail`` — see
    # that module for the full rationale.

    _SECTION_NAMES = ("metadata", "steps")

    STATUS_SELECTOR = "#execution-status"

    def section_error_selector(self, name: str) -> str:
        # Metadata errors go where the user looks for status; steps errors
        # must not replace the (still useful) step detail pane.
        return "#execution-metadata" if name == "metadata" else self.STATUS_SELECTOR

    @work(exclusive=True)
    async def _load_detail(self) -> None:
        """Fan out the metadata + steps fetches; render each on completion."""
        api = self.app.tui_api
        usecase_id, execution_id = self._usecase_id, self._execution_id
        await self._load_sections([
            ("metadata", lambda: api.get_execution_metadata(usecase_id, execution_id), self._render_metadata_and_error),
            ("steps", lambda: api.get_execution_steps(usecase_id, execution_id), self._render_steps),
        ])

    def _render_metadata_and_error(self, execution: Dict[str, Any]) -> None:
        """Header block and error banner share one execution record."""
        self._render_metadata(execution)
        self._render_error(execution)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_metadata(self, execution: Dict[str, Any]) -> None:
        usecase_name = execution.get("usecase_name") or self._usecase_id
        status = execution.get("status") or "—"
        trigger = execution.get("trigger_type") or "—"
        created = execution.get("created_at") or "—"
        started = execution.get("started_at") or "—"
        ended = execution.get("ended_at") or "—"
        by = execution.get("triggered_by") or "—"

        duration = execution.get("duration_seconds") or execution.get("duration")
        duration_str = (
            format_duration(float(duration))
            if duration is not None
            else "—"
        )

        text = (
            f"[b]{usecase_name}[/] — execution {status_cell(status)}\n"
            f"[cyan]ID:[/] {self._execution_id}   [cyan]Trigger:[/] {trigger}   "
            f"[cyan]By:[/] {by}   [cyan]Duration:[/] {duration_str}\n"
            f"[cyan]Created:[/] {created}   [cyan]Started:[/] {started}   [cyan]Ended:[/] {ended}"
        )
        self.query_one("#execution-metadata", Static).update(text)

    def _render_error(self, execution: Dict[str, Any]) -> None:
        """Show the top-level error message on a red banner when set."""
        message = execution.get("error_message") or execution.get("error")
        widget: Static = self.query_one("#execution-error", Static)
        if message:
            widget.update(f"[b red]Error:[/] {message}")
            widget.styles.display = "block"
        else:
            widget.update("")
            widget.styles.display = "none"

    def _render_steps(self, steps: List[Dict[str, Any]]) -> None:
        table: DataTable = self.query_one("#execution-steps-table", DataTable)
        table.clear()

        self._ordered_steps = sorted(steps, key=lambda s: s.get("sort", 0))
        for i, step in enumerate(self._ordered_steps, start=1):
            step_type = step.get("step_type") or step.get("stepType") or "—"
            status = step.get("status") or "—"
            instruction = step.get("instruction") or ""
            if len(instruction) > 80:
                instruction = instruction[:77] + "…"
            duration = step.get("duration") or 0.0
            try:
                duration_num = float(duration)
            except (TypeError, ValueError):
                duration_num = 0.0
            duration_str = (
                format_duration(duration_num) if duration_num > 0 else "—"
            )
            table.add_row(
                str(i),
                step_type_cell(step_type),
                status_cell(status),
                duration_str,
                instruction,
                key=str(i),
            )

        detail: Static = self.query_one("#execution-step-detail-text", Static)
        if not self._ordered_steps:
            detail.update("[dim]No steps recorded for this execution.[/]")
        else:
            detail.update(_STEP_DETAIL_PLACEHOLDER)

    def _render_step_detail(self, step: Dict[str, Any]) -> None:
        """Render a single step's full payload into the right-hand pane.

        Fields with empty values are hidden — identical policy to the
        usecase detail's Steps tab. Priority fields (instruction,
        status, duration, error / actual / expected) are pinned to the
        top; everything else follows alphabetically. Lists and dicts
        are pretty-printed as JSON.
        """

        def _format_value(key: str, value: Any) -> str:
            if key == "status":
                return status_cell(str(value))
            if key in {"duration", "duration_seconds"}:
                try:
                    return format_duration(float(value))
                except (TypeError, ValueError):
                    return str(value)
            return format_field_value(value)

        lines: List[str] = []

        # Prominent validation block at the top — mirrors the web
        # ``ValidationResult`` component. Only renders when the step
        # has a ``validation_type``; everything else is still handled
        # below.
        validation_block = render_validation_block(
            validation_type=str(step.get("validation_type") or ""),
            validation_operator=str(step.get("validation_operator") or ""),
            validation_value=str(step.get("validation_value") or ""),
            actual_value=(
                str(step["actual_value"])
                if step.get("actual_value") is not None
                else None
            ),
            status=str(step.get("status") or ""),
        )
        if validation_block:
            lines.append(validation_block)
            lines.append("")  # spacer before the field list

        priority = [
            "instruction",
            "step_type",
            "status",
            "duration",
            "actual_value",
            "expected_value",
            "error_message",
        ]
        lines.extend(step_field_lines(step, priority=priority, format_value=_format_value))

        if not lines:
            lines.append("[dim]Step has no populated fields.[/]")

        self.query_one("#execution-step-detail-text", Static).update(
            "\n".join(lines)
        )
