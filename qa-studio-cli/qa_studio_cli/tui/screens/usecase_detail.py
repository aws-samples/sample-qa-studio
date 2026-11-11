"""Use case detail screen.

Loads the full set of sub-resources in a background worker (single
fetch per screen open, refresh on ``r``). Renders metadata at the top
and five tabs: Steps, Variables, Headers, Secrets, Executions. The
Executions tab is a placeholder — populated in a later commit.

The **Steps** tab is a vertically-split view: a table of steps on the
left and a live-updating detail pane on the right. Moving the cursor
in the table updates the detail pane with the full step payload so the
user can inspect long instructions, assert values, and other fields
that are truncated in the table.

Run and Edit actions are not wired in this commit; they land in
commits (e) and (f) respectively. Their footer hints are already
shown so the navigation feels complete.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static, TabbedContent, TabPane

from qa_studio_cli.tui.api import ExecutionListItem
from qa_studio_cli.tui.app_header import TAB_USECASES, AppHeader
from qa_studio_cli.tui.border_pulse import LoadPulseMixin
from qa_studio_cli.tui.screens._base_detail import ProgressiveLoadMixin, step_field_lines
from qa_studio_cli.tui.step_render import (
    STEP_TYPE_COLOURS,
    format_duration,
    render_validation_block,
    status_cell,
    step_type_cell,
)


_STEPS_PLACEHOLDER = "Select a step (arrow keys) to see its full details."


# Backwards-compatible aliases for existing tests that imported the
# private names directly from this module before the helpers moved
# into ``step_render``. New code should import from ``step_render``.
_STEP_TYPE_COLOURS = STEP_TYPE_COLOURS
_step_type_cell = step_type_cell
_format_duration = format_duration


@dataclass
class _DetailBundle:
    """Pre-fetched payload for a single detail screen load."""

    usecase: Dict[str, Any]
    steps: List[Dict[str, Any]]
    variables: Dict[str, str]
    headers: Dict[str, str]
    secrets: List[Dict[str, Any]]
    executions: List["ExecutionListItem"]


class UsecaseDetailScreen(ProgressiveLoadMixin, LoadPulseMixin, Screen):
    """Single-usecase detail view."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("r", "refresh", "Refresh"),
        # Run / Edit bindings show in the footer. Run pushes the
        # parametrisation form; Edit opens the use case in the web
        # app (if ``web_url`` is configured).
        Binding("R", "run", "Run"),
        Binding("e", "edit", "Edit in browser"),
    ]

    # Pulse the header/content divider while the six-section load is
    # in flight. Colours come from the mixin's class defaults.
    LOAD_PULSE_TARGET = "AppHeader"

    def __init__(self, usecase_id: str):
        super().__init__()
        self._usecase_id = usecase_id
        # Populated when the background fetch completes; consulted by
        # the RowHighlighted handler to look up the full payload for
        # the row the user is hovering on.
        self._ordered_steps: List[Dict[str, Any]] = []
        # The full fetched bundle — needed by the Run form so it can
        # pre-fill the parameter inputs without re-hitting the API.
        self._bundle: Optional[_DetailBundle] = None

    def compose(self) -> ComposeResult:
        yield AppHeader(active=TAB_USECASES)
        yield Static("Loading…", id="detail-status")
        with Vertical(id="detail-body"):
            yield Static("", id="detail-metadata", markup=True)
            with TabbedContent(id="detail-tabs"):
                with TabPane("Steps", id="tab-steps"):
                    with Horizontal(id="steps-split"):
                        yield DataTable(
                            id="steps-table",
                            cursor_type="row",
                            zebra_stripes=True,
                        )
                        with VerticalScroll(id="step-detail-scroll"):
                            yield Static(
                                _STEPS_PLACEHOLDER,
                                id="step-detail-text",
                                markup=True,
                            )
                with TabPane("Variables", id="tab-variables"):
                    yield DataTable(id="variables-table", zebra_stripes=True)
                with TabPane("Headers", id="tab-headers"):
                    yield DataTable(id="headers-table", zebra_stripes=True)
                with TabPane("Secrets", id="tab-secrets"):
                    yield DataTable(id="secrets-table", zebra_stripes=True)
                with TabPane("Executions", id="tab-executions"):
                    yield Static("", id="executions-status", markup=True)
                    yield DataTable(
                        id="executions-table",
                        zebra_stripes=True,
                        cursor_type="row",
                    )
        yield Footer()

    def on_mount(self) -> None:
        # Configure tables once; rows are filled after the fetch.
        self.query_one("#steps-table", DataTable).add_columns("#", "Type", "Instruction")
        self.query_one("#variables-table", DataTable).add_columns("Key", "Value")
        self.query_one("#headers-table", DataTable).add_columns("Name", "Value")
        self.query_one("#secrets-table", DataTable).add_columns("Key", "Value")
        self.query_one("#executions-table", DataTable).add_columns(
            "Status", "Created", "Duration", "Trigger", "By", "ID"
        )
        # Build the pulse via the mixin — target + colours come from
        # the class-level selectors on ``LoadPulseMixin``.
        self._install_load_pulse()
        self._load_detail()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        self._load_detail()

    def action_run(self) -> None:
        """Open the Run form pre-filled from the loaded bundle."""
        if self._bundle is None:
            self.app.notify(
                "Use case not loaded yet — try again in a moment.",
                severity="warning",
                timeout=2,
            )
            return
        # Lazy import to avoid circular-ish load at module import.
        from qa_studio_cli.tui.screens.run_form import RunFormScreen

        self.app.push_screen(
            RunFormScreen(
                usecase_id=self._usecase_id,
                usecase=self._bundle.usecase,
                variables=self._bundle.variables,
                headers=self._bundle.headers,
                secrets=self._bundle.secrets,
            )
        )

    def action_edit(self) -> None:
        """Open the use case in the web app's detail page.

        Requires ``web_url`` to be set in ``~/.qa-studio/config.json``
        (configurable via ``qa-studio configure``). When unset, shows
        a notification pointing at the config command rather than
        silently doing nothing.
        """
        # Lazy imports keep the keybinding cost minimal — we only
        # touch these on the rare Edit press, and ``webbrowser`` in
        # particular imports subprocess machinery.
        import webbrowser

        from qa_studio_cli.config.manager import load_config

        try:
            config = load_config()
        except Exception as exc:  # noqa: BLE001
            self.app.notify(
                f"Could not load config: {exc}",
                severity="error",
                timeout=4,
            )
            return

        if not config.web_url:
            self.app.notify(
                "Web URL not configured. Run `qa-studio configure` "
                "and set the Web URL to enable Edit in browser.",
                severity="warning",
                timeout=6,
            )
            return

        url = f"{config.web_url}/usecase/{self._usecase_id}"
        opened = webbrowser.open(url)
        if opened:
            self.app.notify(
                f"Opened {url} in the default browser.",
                severity="information",
                timeout=3,
            )
        else:
            # ``webbrowser.open`` returns False on headless envs /
            # failed launches. Show the URL so the user can paste it
            # manually.
            self.app.notify(
                f"Could not open a browser. Paste this URL manually: {url}",
                severity="warning",
                timeout=10,
            )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Live-update the Steps detail pane when the cursor moves.

        This handler fires for every DataTable on the screen, so we
        filter on the table id — we only want to react to the steps
        table, not to moves inside the Variables / Headers / Secrets
        tables.
        """
        if event.data_table.id != "steps-table":
            return
        if event.row_key is None or event.row_key.value is None:
            return

        # Row keys are the 1-based sort index as a string; we use them
        # to index back into the stored ordered list.
        try:
            idx = int(event.row_key.value) - 1
        except (TypeError, ValueError):
            return
        if idx < 0 or idx >= len(self._ordered_steps):
            return

        self._render_step_detail(self._ordered_steps[idx])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter / click on the Executions table opens the execution
        detail. Other tables (Steps / Variables / Headers / Secrets)
        are read-only — selection there is a no-op."""
        if event.data_table.id != "executions-table":
            return
        execution_id = event.row_key.value if event.row_key else None
        if not execution_id:
            return
        # Lazy import to keep module load graph shallow.
        from qa_studio_cli.tui.screens.execution_detail import (
            ExecutionDetailScreen,
        )

        self.app.push_screen(
            ExecutionDetailScreen(
                usecase_id=self._usecase_id,
                execution_id=execution_id,
            )
        )

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Focus the DataTable inside the newly-activated tab.

        Without this, switching to a tab leaves focus on the tab
        header so arrow keys and Enter don't reach the table — the
        user has to press Tab again. For the Executions tab in
        particular that made "click to open a past run" feel broken.
        """
        tab_to_table = {
            "tab-steps": "#steps-table",
            "tab-variables": "#variables-table",
            "tab-headers": "#headers-table",
            "tab-secrets": "#secrets-table",
            "tab-executions": "#executions-table",
        }
        pane_id = event.pane.id if event.pane else None
        selector = tab_to_table.get(pane_id or "")
        if not selector:
            return
        try:
            table = self.query_one(selector, DataTable)
        except Exception:
            return  # widget not mounted yet
        if table.row_count > 0:
            table.focus()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    #
    # Loading strategy: fan the six sub-resource fetches out in
    # parallel and render each section as soon as its API call
    # returns. This replaces a previous serial-fetch-then-bulk-render
    # pattern that blocked the first paint on the sum of all six
    # round-trips.
    #
    # Three behaviours the caller-visible contract still guarantees:
    #
    # * ``self._bundle`` is populated only when *every* section
    #   succeeded — preserves the pre-existing "Run needs the whole
    #   usecase" invariant enforced by :meth:`action_run`.
    # * A per-section failure is rendered inline in that section's
    #   status widget without aborting the others. Today's serial
    #   loader lost everything on any single failure — progressive
    #   rendering is strictly an improvement on that edge case.
    # * ``@work(exclusive=True)`` on the top-level async worker keeps
    #   the refresh-during-load semantics intact: a second invocation
    #   cancels the first.

    _SECTION_NAMES = (
        "usecase",
        "steps",
        "variables",
        "headers",
        "secrets",
        "executions",
    )

    STATUS_SELECTOR = "#detail-status"

    def section_error_selector(self, name: str) -> str:
        # Metadata errors replace the big metadata block; the rest go to
        # the status line so the user is not hunting for the message.
        return "#detail-metadata" if name == "usecase" else self.STATUS_SELECTOR

    @work(exclusive=True)
    async def _load_detail(self) -> None:
        """Fan out all sub-resource fetches; render each on completion."""
        usecase_id = self._usecase_id
        api = self.app.tui_api
        # A refresh must not let the previous run's bundle leak through.
        self._bundle = None
        complete = await self._load_sections([
            ("usecase", lambda: api.get_usecase(usecase_id), self._render_metadata),
            ("steps", lambda: api.get_steps(usecase_id), self._render_steps),
            ("variables", lambda: api.get_variables(usecase_id), self._render_variables),
            ("headers", lambda: api.get_headers(usecase_id), self._render_headers),
            ("secrets", lambda: api.get_secrets(usecase_id), self._render_secrets),
            ("executions", lambda: api.list_executions(usecase_id), self._render_executions),
        ])
        # The Run action needs the whole use case: bundle only on full success.
        if complete:
            self._bundle = _DetailBundle(**self._loaded_sections)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_metadata(self, usecase: Dict[str, Any]) -> None:
        """Render the full usecase metadata above the tabs.

        Shows every field the API exposes that's interesting to a
        developer reading the detail view — not just what fits on two
        lines. Missing fields render as an em-dash so the layout stays
        stable across usecases with varying shape.
        """
        name = usecase.get("name") or self._usecase_id

        active = usecase.get("active")
        if active is True:
            status = "[green]●[/] Active"
        elif active is False:
            status = "[dim]○ Inactive[/]"
        else:
            status = ""

        platform = usecase.get("test_platform") or usecase.get("platform") or "web"
        region = usecase.get("executing_region") or "—"
        model = usecase.get("model_id") or "—"
        starting_url = usecase.get("starting_url") or "—"
        description = usecase.get("description") or "[dim]—[/]"

        tags = usecase.get("tags") or []
        tags_str = ", ".join(tags) if tags else "[dim]—[/]"

        created_at = usecase.get("created_at") or "—"
        updated_at = usecase.get("updated_at") or "—"
        created_by = usecase.get("created_by") or "—"

        # Mobile-only fields — shown only when the platform is mobile
        # so the block stays compact for the common web case.
        mobile_lines: List[str] = []
        if platform == "mobile":
            app_package = usecase.get("app_package") or usecase.get("bundle_id") or "—"
            device_arn = usecase.get("device_arn") or "—"
            mobile_lines.append(f"[cyan]App:[/] {app_package}   [cyan]Device ARN:[/] {device_arn}")

        lines = [
            f"[b]{name}[/]  {status}".rstrip(),
            f"[cyan]ID:[/] {self._usecase_id}   [cyan]Platform:[/] {platform}   "
            f"[cyan]Region:[/] {region}   [cyan]Model:[/] {model}",
            f"[cyan]Starting URL:[/] {starting_url}",
            f"[cyan]Description:[/] {description}",
            f"[cyan]Tags:[/] {tags_str}",
            *mobile_lines,
            f"[cyan]Created:[/] {created_at} [cyan]by[/] {created_by}   [cyan]Updated:[/] {updated_at}",
        ]

        self.query_one("#detail-metadata", Static).update("\n".join(lines))

    def _render_steps(self, steps: List[Dict[str, Any]]) -> None:
        table: DataTable = self.query_one("#steps-table", DataTable)
        table.clear()

        self._ordered_steps = sorted(steps, key=lambda s: s.get("sort", 0))
        for i, step in enumerate(self._ordered_steps, start=1):
            step_type = step.get("step_type") or step.get("stepType") or "—"
            instruction = step.get("instruction", "")
            # Truncate long instructions in the table view; full
            # value is rendered in the detail pane below.
            if len(instruction) > 80:
                instruction = instruction[:77] + "…"
            # Explicit key = 1-based sort index so RowHighlighted can
            # map back to the full step payload without None-key
            # pitfalls (see usecases_list fix).
            table.add_row(
                str(i),
                _step_type_cell(step_type),
                instruction,
                key=str(i),
            )

        # Reset the detail pane when the list changes.
        detail = self.query_one("#step-detail-text", Static)
        if self._ordered_steps:
            detail.update(_STEPS_PLACEHOLDER)
        else:
            detail.update("This use case has no steps defined.")

    def _render_step_detail(self, step: Dict[str, Any]) -> None:
        """Render a single step's full payload into the bottom pane.

        Fields with empty values (``None``, ``""``, ``[]``, ``{}``) are
        hidden so the pane only shows what's actually set on the step.
        Scalar values are shown inline; lists / dicts are pretty-printed
        as JSON so the user can inspect nested payloads (network
        assertions, transforms, etc.) without losing structure.
        ``step_type`` and ``instruction`` are pinned to the top when
        present; every other field follows alphabetically.
        """

        lines: List[str] = []

        # Prominent validation block at the top — mirrors the web
        # ``ValidationResult``. Definition-only here (no actual value;
        # that's an execution concern).
        validation_block = render_validation_block(
            validation_type=str(step.get("validation_type") or ""),
            validation_operator=str(step.get("validation_operator") or ""),
            validation_value=str(step.get("validation_value") or ""),
        )
        if validation_block:
            lines.append(validation_block)
            lines.append("")

        lines.extend(step_field_lines(step, priority=["step_type", "instruction"]))

        if not lines:
            lines.append("[dim]Step has no populated fields.[/]")

        self.query_one("#step-detail-text", Static).update("\n".join(lines))

    def _render_variables(self, variables: Dict[str, str]) -> None:
        table: DataTable = self.query_one("#variables-table", DataTable)
        table.clear()
        for key in sorted(variables):
            table.add_row(key, variables[key])

    def _render_headers(self, headers: Dict[str, str]) -> None:
        table: DataTable = self.query_one("#headers-table", DataTable)
        table.clear()
        for name in sorted(headers):
            table.add_row(name, headers[name])

    def _render_secrets(self, secrets: List[Dict[str, Any]]) -> None:
        table: DataTable = self.query_one("#secrets-table", DataTable)
        table.clear()
        # API returns ``[{"key": "...", "value": ""}, ...]``.  Values
        # are always blanked on the wire for security; we never render
        # a real secret value in the TUI.
        for entry in sorted(secrets, key=lambda s: s.get("key", "")):
            key = entry.get("key", "—")
            table.add_row(key, "••••••")

    def _render_executions(self, executions: List[ExecutionListItem]) -> None:
        """Render the recent-executions DataTable with colored status.

        API returns newest-first; we preserve that order so the most
        recent run is at the top.
        """
        table: DataTable = self.query_one("#executions-table", DataTable)
        status_widget: Static = self.query_one("#executions-status", Static)
        table.clear()

        if not executions:
            status_widget.update(
                "[dim]No executions yet. Press R to trigger one.[/]"
            )
            return

        status_widget.update(
            f"[dim]Showing {len(executions)} most recent execution(s). Enter opens the execution detail.[/]"
        )

        for item in executions:
            duration = (
                format_duration(item.duration_seconds)
                if item.duration_seconds > 0
                else "—"
            )
            table.add_row(
                status_cell(item.status),
                item.created_at,
                duration,
                item.trigger_type,
                item.triggered_by,
                item.execution_id,
                key=item.execution_id or None,
            )
