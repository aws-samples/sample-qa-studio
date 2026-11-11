"""Test suite detail screen.

Fans the three sub-resource fetches (suite, usecases, executions)
out in parallel and renders each as soon as its call returns —
same shape as :class:`UsecaseDetailScreen`. Shows metadata at the
top and two tabs:

* **Usecases** — the use cases belonging to the suite, ordered by
  their configured position. Enter / click opens the use case detail.
* **Executions** — the suite's recent runs, newest first, with a
  colour-coded status. Read-only: clicking a row is a no-op for now;
  drilling into a suite-execution detail screen lands in a later
  commit.

``R`` (shift+r) triggers a new run; ``r`` reloads all three
sections. A per-section fetch failure is surfaced inline without
aborting the rest of the load.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static, TabbedContent, TabPane

from qa_studio_cli.tui.app_header import TAB_SUITES, AppHeader
from qa_studio_cli.tui.border_pulse import LoadPulseMixin
from qa_studio_cli.tui.screens._base_detail import ProgressiveLoadMixin
from qa_studio_cli.tui.step_render import format_duration, status_cell


@dataclass
class _SuiteBundle:
    suite: Dict[str, Any]
    usecases: List[Dict[str, Any]]
    executions: List[Dict[str, Any]]


class SuiteDetailScreen(ProgressiveLoadMixin, LoadPulseMixin, Screen):
    """Single-suite detail view."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("r", "refresh", "Refresh"),
        Binding("R", "run", "Run"),
        Binding("enter", "open_usecase", "Open use case", show=False),
    ]

    LOAD_PULSE_TARGET = "AppHeader"

    def __init__(self, suite_id: str):
        super().__init__()
        self._suite_id = suite_id
        # Populated after the metadata section arrives; consulted by
        # the Run action so the form can show the suite's name and
        # cached usecase count without re-hitting the API. Set eagerly
        # (inside ``_render_metadata``) so Run unblocks as soon as the
        # suite record lands, independent of the usecases/executions
        # sections.
        self._suite: Dict[str, Any] = {}
        # Full bundle assembled only when every section succeeded —
        # kept separate from ``_suite`` so Run doesn't need all three
        # sections to have landed successfully.
        self._bundle: Optional[_SuiteBundle] = None

    def compose(self) -> ComposeResult:
        yield AppHeader(active=TAB_SUITES)
        yield Static("Loading…", id="suite-status")
        with Vertical(id="suite-body"):
            yield Static("", id="suite-metadata", markup=True)
            with TabbedContent(id="suite-tabs"):
                with TabPane("Usecases", id="tab-suite-usecases"):
                    yield Static(
                        "",
                        id="suite-usecases-status",
                        markup=True,
                    )
                    yield Static(
                        "Use cases in this suite (Enter to open):",
                        id="suite-usecases-label",
                    )
                    yield DataTable(
                        id="suite-usecases-table",
                        zebra_stripes=True,
                        cursor_type="row",
                    )
                with TabPane("Executions", id="tab-suite-executions"):
                    yield Static(
                        "",
                        id="suite-executions-status",
                        markup=True,
                    )
                    yield DataTable(
                        id="suite-executions-table",
                        zebra_stripes=True,
                        cursor_type="row",
                    )
        yield Footer()

    def on_mount(self) -> None:
        usecases_table: DataTable = self.query_one(
            "#suite-usecases-table", DataTable
        )
        usecases_table.add_columns("Order", "Name", "ID")

        executions_table: DataTable = self.query_one(
            "#suite-executions-table", DataTable
        )
        executions_table.add_columns(
            "Status", "Created", "Duration", "Pass/Total", "Trigger", "By", "ID"
        )

        # Build the pulse via the mixin — the fan-out loader below
        # starts/stops it around ``asyncio.gather`` so ``on_mount``
        # only needs to install.
        self._install_load_pulse()
        self._load_detail()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        self._load_detail()

    def action_open_usecase(self) -> None:
        table: DataTable = self.query_one("#suite-usecases-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return
        row_key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
        usecase_id = row_key.value
        if not usecase_id:
            return
        from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen

        self.app.push_screen(UsecaseDetailScreen(usecase_id=usecase_id))

    def action_run(self) -> None:
        """Open the suite Run form pre-filled from the loaded suite."""
        if not self._suite:
            self.app.notify(
                "Suite not loaded yet — try again in a moment.",
                severity="warning",
                timeout=2,
            )
            return
        from qa_studio_cli.tui.screens.suite_run_form import SuiteRunFormScreen

        self.app.push_screen(
            SuiteRunFormScreen(suite_id=self._suite_id, suite=self._suite)
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter / click on the Usecases table opens the use-case detail.

        The Executions table is read-only for now — selection there is
        a no-op until a dedicated suite-execution detail screen lands.
        We match on the DataTable id so a row-selected event from the
        executions table doesn't accidentally open a usecase detail
        with a suite-execution-id as the usecase id.
        """
        if event.data_table.id != "suite-usecases-table":
            return
        usecase_id = event.row_key.value if event.row_key else None
        if not usecase_id:
            return
        from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen

        self.app.push_screen(UsecaseDetailScreen(usecase_id=usecase_id))

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Focus the DataTable inside the newly-activated tab.

        Without this, switching to the Executions tab leaves focus
        on the tab header so arrow keys don't reach the table.
        Mirrors the same fix on :class:`UsecaseDetailScreen`.
        """
        tab_to_table = {
            "tab-suite-usecases": "#suite-usecases-table",
            "tab-suite-executions": "#suite-executions-table",
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
    # Loading strategy: fan the three sub-resource fetches out in
    # parallel and render each section as soon as its API call
    # returns. Mirrors :meth:`UsecaseDetailScreen._load_detail`; see
    # that module for the full rationale. Caller-visible contract:
    #
    # * ``self._suite`` is populated as soon as the metadata section
    #   arrives — Run unblocks without waiting for the slower
    #   executions call.
    # * ``self._bundle`` is populated only when *every* section
    #   succeeded — preserved for future consumers that want an
    #   all-or-nothing snapshot (the current Run path only needs
    #   ``self._suite``).
    # * A per-section failure is rendered inline in that section's
    #   status area without aborting the others.
    # * ``@work(exclusive=True)`` on the top-level async worker keeps
    #   the refresh-during-load semantics intact: a second invocation
    #   cancels the first.

    _SECTION_NAMES = ("suite", "usecases", "executions")

    STATUS_SELECTOR = "#suite-status"

    _SECTION_ERROR_SELECTORS = {
        # The metadata block has no tab; tab sections write to their own
        # status widget so the error survives later progress updates.
        "suite": "#suite-metadata",
        "usecases": "#suite-usecases-status",
        "executions": "#suite-executions-status",
    }

    def section_error_selector(self, name: str) -> str:
        return self._SECTION_ERROR_SELECTORS.get(name, self.STATUS_SELECTOR)

    @work(exclusive=True)
    async def _load_detail(self) -> None:
        """Fan out all sub-resource fetches; render each on completion."""
        suite_id = self._suite_id
        api = self.app.tui_api
        # A refresh must not let the previous run's bundle leak through.
        self._bundle = None
        self._suite = {}
        complete = await self._load_sections([
            ("suite", lambda: api.get_suite(suite_id), self._render_metadata),
            ("usecases", lambda: api.list_suite_usecases(suite_id), self._render_usecases),
            ("executions", lambda: api.list_suite_executions(suite_id), self._render_suite_executions),
        ])
        if complete:
            self._bundle = _SuiteBundle(
                suite=self._loaded_sections["suite"],
                usecases=self._loaded_sections["usecases"],
                executions=self._loaded_sections["executions"],
            )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_metadata(self, suite: Dict[str, Any]) -> None:
        """Render the suite metadata block from the suite record alone.

        The usecase count is read from the suite's own
        ``total_usecases`` field — the single source of truth on the
        record, maintained by the backend on add/remove. This removes
        the dependency on the ``usecases`` section so metadata can
        render as soon as the suite call returns.

        Also populates ``self._suite`` so the Run action unblocks
        immediately, without waiting for the other two sections.
        """
        self._suite = suite

        name = suite.get("name", self._suite_id)
        description = suite.get("description") or "—"
        tags = suite.get("tags") or []
        tags_str = ", ".join(tags) if tags else "—"
        usecase_count = suite.get("total_usecases")
        usecase_count_str = "—" if usecase_count is None else str(usecase_count)

        text = (
            f"[b]{name}[/]\n"
            f"ID: {self._suite_id}   Use cases: {usecase_count_str}   "
            f"Tags: {tags_str}\n"
            f"Description: {description}"
        )
        self.query_one("#suite-metadata", Static).update(text)

    def _render_usecases(self, usecases: List[Dict[str, Any]]) -> None:
        table: DataTable = self.query_one("#suite-usecases-table", DataTable)
        table.clear()

        # Suite membership usually carries an ``order`` field — sort by
        # it when present so rendering matches the configured run order.
        def sort_key(uc: Dict[str, Any]) -> int:
            return int(uc.get("order") or uc.get("sort") or 0)

        ordered = sorted(usecases, key=sort_key)
        for i, uc in enumerate(ordered, start=1):
            uc_id = str(uc.get("usecaseId") or uc.get("usecase_id") or uc.get("id") or "")
            name = str(uc.get("usecaseName") or uc.get("usecase_name") or uc.get("name") or "—")
            # Explicit key → the row resolves back to the correct
            # usecase id on selection (avoids the None-key pitfall).
            table.add_row(str(i), name, uc_id, key=uc_id or f"_row_{i}")

    def _render_suite_executions(
        self, executions: List[Dict[str, Any]]
    ) -> None:
        """Render the recent-suite-executions DataTable.

        Defensive field reads: suite execution records can vary in
        shape across historical runs, so every column falls back to
        an em-dash when the expected field is missing rather than
        crashing the entire suite-detail render.
        """
        table: DataTable = self.query_one("#suite-executions-table", DataTable)
        status_widget: Static = self.query_one(
            "#suite-executions-status", Static
        )
        table.clear()

        if not executions:
            status_widget.update(
                "[dim]No executions yet. Press R to trigger one.[/]"
            )
            return

        status_widget.update(
            f"[dim]Showing {len(executions)} most recent execution(s).[/]"
        )

        for item in executions:
            total = item.get("total_usecases")
            successful = item.get("successful_usecases")
            pass_total = (
                f"{successful}/{total}"
                if total is not None and successful is not None
                else "—"
            )

            duration_str = "—"
            duration = item.get("duration_seconds") or item.get("duration")
            try:
                if duration is not None and float(duration) > 0:
                    duration_str = format_duration(float(duration))
            except (TypeError, ValueError):
                pass

            created = (
                item.get("created_at")
                or item.get("started_at")
                or "—"
            )

            suite_execution_id = str(
                item.get("suite_execution_id") or item.get("id") or ""
            )

            table.add_row(
                status_cell(str(item.get("status") or "—")),
                str(created),
                duration_str,
                pass_total,
                str(item.get("trigger_type") or "—"),
                str(item.get("triggered_by") or "—"),
                suite_execution_id,
                key=suite_execution_id or None,
            )
