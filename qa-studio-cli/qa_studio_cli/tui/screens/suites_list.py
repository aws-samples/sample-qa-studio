"""Test suites list screen.

Mirrors :class:`UsecasesListScreen` — flat DataTable with an async
fetch on mount, Enter opens the suite detail screen, ``r`` refreshes,
``/`` focuses the filter, ``R`` (shift+r) runs the highlighted suite
without a detour via the detail screen. Filter is case-insensitive
substring match against name and id.
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, Static

from qa_studio_cli.tui.api import SuiteListItem
from qa_studio_cli.tui.app_header import TAB_SUITES, AppHeader
from qa_studio_cli.tui.border_pulse import LoadPulseMixin


class SuitesListScreen(LoadPulseMixin, Screen):
    """Flat list of test suites the user has access to."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("slash", "focus_filter", "Filter"),
        Binding("R", "run", "Run"),
        Binding("enter", "open_detail", "Open", show=False),
    ]

    TITLE = "Test suites"

    LOAD_PULSE_TARGET = "AppHeader"

    def __init__(self) -> None:
        super().__init__()
        self._all_items: list[SuiteListItem] = []

    def compose(self) -> ComposeResult:
        yield AppHeader(active=TAB_SUITES)
        yield Static("Loading test suites…", id="suites-status")
        with Horizontal(id="suites-filter-row"):
            yield Input(
                placeholder="Filter by name or id (press / to focus)…",
                id="suites-filter",
            )
        table = DataTable(id="suites-table", cursor_type="row", zebra_stripes=True)
        table.add_columns("Name", "ID", "Tests", "Description")
        yield table
        yield Footer()

    def on_mount(self) -> None:
        # Focus the table immediately so global bindings don't get
        # swallowed by the filter Input. See usecases_list for the
        # full rationale.
        self.query_one(DataTable).focus()
        self._install_load_pulse()
        self._start_load_pulse()
        self._load_suites()

    def action_refresh(self) -> None:
        self._start_load_pulse()
        self._load_suites()

    def action_focus_filter(self) -> None:
        self.query_one("#suites-filter", Input).focus()

    def action_open_detail(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return
        row_key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
        suite_id = row_key.value
        if not suite_id:
            return
        from qa_studio_cli.tui.screens.suite_detail import SuiteDetailScreen

        self.app.push_screen(SuiteDetailScreen(suite_id=suite_id))

    def action_run(self) -> None:
        """Run the highlighted test suite without a detour via the
        detail screen.

        Mirrors the ``R`` binding on :class:`SuiteDetailScreen` —
        same data contract, same destination. Only needs the suite
        record (not its member use cases) because
        :class:`SuiteRunFormScreen` only reads the suite's metadata.
        """
        table = self.query_one(DataTable)
        if table.cursor_row is None or table.row_count == 0:
            self.app.notify(
                "No test suite highlighted — arrow-key to a row first.",
                severity="warning",
                timeout=3,
            )
            return
        row_key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
        suite_id = row_key.value
        if not suite_id:
            return

        name = next(
            (item.name for item in self._all_items if item.suite_id == suite_id),
            suite_id,
        )
        self.app.notify(
            f"Preparing run for {name}…",
            severity="information",
            timeout=2,
        )
        self._prepare_run(suite_id)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        suite_id = event.row_key.value
        if not suite_id:
            return
        from qa_studio_cli.tui.screens.suite_detail import SuiteDetailScreen

        self.app.push_screen(SuiteDetailScreen(suite_id=suite_id))

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "suites-filter":
            return
        self._render_rows(self._filter(event.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "suites-filter":
            return
        table = self.query_one(DataTable)
        if table.row_count > 0:
            table.focus()

    def _filter(self, query: str) -> list[SuiteListItem]:
        query = (query or "").strip().lower()
        if not query:
            return list(self._all_items)
        return [
            item
            for item in self._all_items
            if query in item.name.lower() or query in item.suite_id.lower()
        ]

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    @work(thread=True, exclusive=True)
    def _load_suites(self) -> None:
        try:
            items = self.app.tui_api.list_suites()
        except Exception as exc:  # noqa: BLE001
            self.app.call_from_thread(
                self._on_load_error, f"Failed to load test suites: {exc}"
            )
            return
        self.app.call_from_thread(self._on_load_success, items)

    @work(thread=True, group="run-prep")
    def _prepare_run(self, suite_id: str) -> None:
        """Fetch the suite record off the event loop and push
        :class:`SuiteRunFormScreen` on success.

        Single call — a suite's Run form only reads the suite's
        metadata. Separate worker group from ``_load_suites`` so a
        run preparation never cancels an in-flight refresh.
        """
        try:
            suite = self.app.tui_api.get_suite(suite_id)
        except Exception as exc:  # noqa: BLE001
            self.app.call_from_thread(
                self._on_run_prep_error,
                f"Could not prepare run: {exc}",
            )
            return

        self.app.call_from_thread(self._on_run_prep_success, suite_id, suite)

    def _on_run_prep_success(self, suite_id: str, suite: dict) -> None:
        from qa_studio_cli.tui.screens.suite_run_form import SuiteRunFormScreen

        self.app.push_screen(SuiteRunFormScreen(suite_id=suite_id, suite=suite))

    def _on_run_prep_error(self, message: str) -> None:
        self.app.notify(message, severity="error", timeout=6)

    def _on_load_success(self, items: list[SuiteListItem]) -> None:
        self._stop_load_pulse()
        self._all_items = items
        try:
            self.app.set_tab_count("suites", len(items))
        except AttributeError:
            # See UsecasesListScreen._on_load_success for the
            # rationale — keeps legacy test harnesses working.
            pass
        current_filter = self.query_one("#suites-filter", Input).value
        self._render_rows(self._filter(current_filter))

    def _render_rows(self, items: list[SuiteListItem]) -> None:
        table: DataTable = self.query_one(DataTable)
        status: Static = self.query_one("#suites-status", Static)

        table.clear()
        for item in items:
            description = item.description
            if len(description) > 60:
                description = description[:57] + "…"
            # Explicit key → RowKey.value == suite_id (see usecases_list
            # for the full rationale).
            table.add_row(
                item.name,
                item.suite_id,
                str(item.total_usecases),
                description,
                key=item.suite_id,
            )

        total = len(self._all_items)
        shown = len(items)
        if total == 0:
            status.update("No test suites found.")
        elif shown == 0:
            status.update(f"No matches — {total} suite(s) hidden by filter.")
        elif shown == total:
            status.update(
                f"{total} test suite(s). Enter to open, R to run, r to refresh, / to filter."
            )
        else:
            status.update(f"{shown} of {total} shown. R to run, / to edit filter, r to refresh.")

    def _on_load_error(self, message: str) -> None:
        self._stop_load_pulse()
        status: Static = self.query_one("#suites-status", Static)
        status.update(f"[b red]{message}[/]")
