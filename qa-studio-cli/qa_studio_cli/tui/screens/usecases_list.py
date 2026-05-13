"""Use cases list screen.

Fetches all use cases from the API on mount, renders them in a
``DataTable``. Enter on a row opens the detail screen; ``r`` refreshes;
``/`` focuses the filter input; ``R`` (shift+r) runs the highlighted
row, mirroring the Run action on the detail screen. The filter is a
client-side, case-insensitive substring match against the name and
id columns.
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, Static

from qa_studio_cli.tui.api import UsecaseListItem
from qa_studio_cli.tui.app_header import TAB_USECASES, AppHeader
from qa_studio_cli.tui.border_pulse import LoadPulseMixin


class UsecasesListScreen(LoadPulseMixin, Screen):
    """Flat list of every use case the user has access to."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("slash", "focus_filter", "Filter"),
        Binding("R", "run", "Run"),
        Binding("enter", "open_detail", "Open", show=False),
    ]

    TITLE = "Use cases"

    # Pulse target is the app-wide header — keeps one loading bar
    # always visible at the top instead of a per-section divider.
    LOAD_PULSE_TARGET = "AppHeader"

    def __init__(self) -> None:
        super().__init__()
        # Full unfiltered result from the API; filtering is purely
        # client-side against this snapshot so typing in the filter is
        # instant (no extra HTTP hit per keystroke).
        self._all_items: list[UsecaseListItem] = []

    def compose(self) -> ComposeResult:
        yield AppHeader(active=TAB_USECASES)
        yield Static("Loading use cases…", id="usecases-status")
        with Horizontal(id="usecases-filter-row"):
            yield Input(
                placeholder="Filter by name or id (press / to focus)…",
                id="usecases-filter",
            )
        table = DataTable(id="usecases-table", cursor_type="row", zebra_stripes=True)
        table.add_columns("Name", "ID", "Platform", "Region")
        yield table
        yield Footer()

    def on_mount(self) -> None:
        # Focus the table immediately so global bindings (``1``, ``2``,
        # ``r``) don't get swallowed by the filter Input while the
        # initial fetch is in flight. User presses ``/`` to explicitly
        # edit the filter; Enter in the filter moves focus back to
        # the table.
        self.query_one(DataTable).focus()
        self._install_load_pulse()
        self._start_load_pulse()
        self._load_usecases()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        self._start_load_pulse()
        self._load_usecases()

    def action_focus_filter(self) -> None:
        self.query_one("#usecases-filter", Input).focus()

    def action_open_detail(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return
        row_key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
        usecase_id = row_key.value
        if not usecase_id:
            return
        # Lazy import to avoid circular-import during module load.
        from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen

        self.app.push_screen(UsecaseDetailScreen(usecase_id=usecase_id))

    def action_run(self) -> None:
        """Run the highlighted use case without a detour via the detail
        screen.

        Mirrors the ``R`` binding on :class:`UsecaseDetailScreen` —
        same data contract, same destination — but fetches the four
        sub-resources the Run form needs (usecase + variables +
        headers + secrets) on demand instead of reusing a
        pre-populated bundle. Steps and executions are skipped: they
        are not inputs to the form.
        """
        table = self.query_one(DataTable)
        if table.cursor_row is None or table.row_count == 0:
            self.app.notify(
                "No use case highlighted — arrow-key to a row first.",
                severity="warning",
                timeout=3,
            )
            return
        row_key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
        usecase_id = row_key.value
        if not usecase_id:
            return

        # Look up the row's display name so the progress / error
        # messages name the use case the user actually picked instead
        # of an opaque id.
        name = next(
            (item.name for item in self._all_items if item.usecase_id == usecase_id),
            usecase_id,
        )
        self.app.notify(
            f"Preparing run for {name}…",
            severity="information",
            timeout=2,
        )
        self._prepare_run(usecase_id)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Mouse / Enter → open the row that was selected.

        We use ``event.row_key`` directly rather than delegating to
        ``action_open_detail`` so a click opens the row that was
        clicked, not whatever the keyboard cursor happens to be on.
        """
        usecase_id = event.row_key.value
        if not usecase_id:
            return
        from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen

        self.app.push_screen(UsecaseDetailScreen(usecase_id=usecase_id))

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "usecases-filter":
            return
        self._render_rows(self._filter(event.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in the filter input moves focus to the table so the
        user can navigate the filtered result without reaching for
        the mouse."""
        if event.input.id != "usecases-filter":
            return
        table = self.query_one(DataTable)
        if table.row_count > 0:
            table.focus()

    def _filter(self, query: str) -> list[UsecaseListItem]:
        query = (query or "").strip().lower()
        if not query:
            return list(self._all_items)
        return [
            item
            for item in self._all_items
            if query in item.name.lower() or query in item.usecase_id.lower()
        ]

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    @work(thread=True, exclusive=True)
    def _load_usecases(self) -> None:
        """Worker: fetch the list from the API off the event loop."""
        try:
            items = self.app.tui_api.list_usecases()
        except Exception as exc:  # noqa: BLE001 — surface any API/transport error
            self.app.call_from_thread(
                self._on_load_error, f"Failed to load use cases: {exc}"
            )
            return

        self.app.call_from_thread(self._on_load_success, items)

    @work(thread=True, group="run-prep")
    def _prepare_run(self, usecase_id: str) -> None:
        """Fetch the four Run-form inputs off the event loop and push
        :class:`RunFormScreen` on success.

        Sequential fetches: each sub-resource is a few hundred ms and
        the total interactive cost (~1–2 s) is acceptable. A previous
        draft tried to parallelise via ``asyncio.gather`` but the
        added machinery wasn't worth it for a user-triggered action
        that already gates on network latency.

        Failures surface as a toast notification; no partial form is
        ever pushed, so the user either sees the filled-in form or an
        actionable error — never a half-loaded screen.
        """
        api = self.app.tui_api
        try:
            usecase = api.get_usecase(usecase_id)
            variables = api.get_variables(usecase_id)
            headers = api.get_headers(usecase_id)
            secrets = api.get_secrets(usecase_id)
        except Exception as exc:  # noqa: BLE001 — any API/transport error
            self.app.call_from_thread(
                self._on_run_prep_error,
                f"Could not prepare run: {exc}",
            )
            return

        self.app.call_from_thread(
            self._on_run_prep_success,
            usecase_id,
            usecase,
            variables,
            headers,
            secrets,
        )

    def _on_run_prep_success(
        self,
        usecase_id: str,
        usecase: dict,
        variables: dict,
        headers: dict,
        secrets: list,
    ) -> None:
        # Lazy import to avoid pulling the form's subprocess machinery
        # into every startup path through this module.
        from qa_studio_cli.tui.screens.run_form import RunFormScreen

        self.app.push_screen(
            RunFormScreen(
                usecase_id=usecase_id,
                usecase=usecase,
                variables=variables,
                headers=headers,
                secrets=secrets,
            )
        )

    def _on_run_prep_error(self, message: str) -> None:
        self.app.notify(message, severity="error", timeout=6)

    def _on_load_success(self, items: list[UsecaseListItem]) -> None:
        self._stop_load_pulse()
        self._all_items = items
        # Keep the header's ``[ Usecases (N) ]`` badge in sync with
        # whatever the list just loaded. ``set_tab_count`` also
        # refreshes any visible header so the new number paints in
        # without the user having to switch tabs.
        try:
            self.app.set_tab_count("usecases", len(items))
        except AttributeError:
            # Older test harnesses mount list screens on apps that
            # don't expose the count cache; the header simply stays
            # countless in that case.
            pass
        # Respect whatever the user has typed so far in the filter —
        # a refresh shouldn't wipe the active filter.
        current_filter = self.query_one("#usecases-filter", Input).value
        self._render_rows(self._filter(current_filter))

    def _render_rows(self, items: list[UsecaseListItem]) -> None:
        table: DataTable = self.query_one(DataTable)
        status: Static = self.query_one("#usecases-status", Static)

        table.clear()
        for item in items:
            # Use the usecase id as the row key so row selection
            # (event.row_key.value / coordinate_to_cell_key().row_key.value)
            # resolves back to the right usecase.  Without an explicit
            # key, Textual stores ``None`` as ``RowKey.value`` for every
            # row, which silently breaks the mapping.
            table.add_row(
                item.name,
                item.usecase_id,
                item.platform,
                item.region,
                key=item.usecase_id,
            )

        total = len(self._all_items)
        shown = len(items)
        if total == 0:
            status.update("No use cases found.")
        elif shown == 0:
            status.update(f"No matches — {total} use case(s) hidden by filter.")
        elif shown == total:
            status.update(
                f"{total} use case(s). Enter to open, R to run, r to refresh, / to filter."
            )
        else:
            status.update(f"{shown} of {total} shown. R to run, / to edit filter, r to refresh.")

    def _on_load_error(self, message: str) -> None:
        self._stop_load_pulse()
        status: Static = self.query_one("#usecases-status", Static)
        status.update(f"[b red]{message}[/]")
