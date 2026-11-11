"""Shared body of the flat list screens (use cases, test suites).

Fetches the items off the event loop on mount and renders them in a
``DataTable``.  Enter opens the detail screen; ``r`` refreshes; ``/`` focuses
the filter input; ``R`` (shift+r) runs the highlighted row.  The filter is a
client-side, case-insensitive substring match against name and id.

Subclasses set the class attributes (widget-id prefix, tab, texts, columns)
and implement the explicit hooks: :meth:`load_items`, :meth:`item_id`,
:meth:`row_cells`, :meth:`detail_screen_for` and :meth:`start_run`.  Detail and
run screens are imported lazily inside those hooks (avoids circular imports
at module load).
"""

from __future__ import annotations

from typing import Any, ClassVar, List, Sequence

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, Static

from qa_studio_cli.tui.app_header import AppHeader
from qa_studio_cli.tui.border_pulse import LoadPulseMixin


class BaseListScreen(LoadPulseMixin, Screen):
    """Filterable, refreshable list of items with Open and Run actions."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("slash", "focus_filter", "Filter"),
        Binding("R", "run", "Run"),
        Binding("enter", "open_detail", "Open", show=False),
    ]

    # Pulse target is the app-wide header — one loading bar always
    # visible at the top instead of a per-section divider.
    LOAD_PULSE_TARGET = "AppHeader"

    #: Widget ids are ``{ID_PREFIX}-status`` / ``-filter-row`` / ``-filter`` / ``-table``.
    ID_PREFIX: ClassVar[str]
    #: AppHeader tab and the ``app.set_tab_count`` key.
    TAB: ClassVar[str]
    TAB_COUNT_KEY: ClassVar[str]
    COLUMNS: ClassVar[Sequence[str]]
    LOADING_TEXT: ClassVar[str]
    LOAD_ERROR_TEXT: ClassVar[str]       # prefix: "{LOAD_ERROR_TEXT}: {exc}"
    EMPTY_TEXT: ClassVar[str]
    NO_HIGHLIGHT_TEXT: ClassVar[str]
    HIDDEN_NOUN: ClassVar[str]           # "No matches — {total} {HIDDEN_NOUN} hidden by filter."
    COUNT_NOUN: ClassVar[str]            # "{total} {COUNT_NOUN}. Enter to open, ..."

    def __init__(self) -> None:
        super().__init__()
        # Full unfiltered result from the API; filtering is client-side
        # against this snapshot, so typing in the filter is instant.
        self._all_items: List[Any] = []

    # -- hooks ---------------------------------------------------------

    def load_items(self) -> List[Any]:
        """Fetch the items (runs in a worker thread)."""
        raise NotImplementedError

    def item_id(self, item: Any) -> str:
        raise NotImplementedError

    def row_cells(self, item: Any) -> Sequence[str]:
        """One cell per entry of :attr:`COLUMNS`."""
        raise NotImplementedError

    def detail_screen_for(self, row_key: str) -> Screen:
        raise NotImplementedError

    def start_run(self, row_key: str) -> None:
        """Kick off the run preparation for the row (usually a worker)."""
        raise NotImplementedError

    # -- layout --------------------------------------------------------

    def _widget_id(self, suffix: str) -> str:
        return f"{self.ID_PREFIX}-{suffix}"

    def compose(self) -> ComposeResult:
        yield AppHeader(active=self.TAB)
        yield Static(self.LOADING_TEXT, id=self._widget_id("status"))
        with Horizontal(id=self._widget_id("filter-row")):
            yield Input(
                placeholder="Filter by name or id (press / to focus)…",
                id=self._widget_id("filter"),
            )
        table = DataTable(id=self._widget_id("table"), cursor_type="row", zebra_stripes=True)
        table.add_columns(*self.COLUMNS)
        yield table
        yield Footer()

    def on_mount(self) -> None:
        # Focus the table immediately so global bindings (``1``, ``2``,
        # ``r``) are not swallowed by the filter Input while the first
        # fetch is in flight; ``/`` focuses the filter explicitly.
        self.query_one(DataTable).focus()
        self._install_load_pulse()
        self._start_load_pulse()
        self._load_items()

    # -- actions -------------------------------------------------------

    def action_refresh(self) -> None:
        self._start_load_pulse()
        self._load_items()

    def action_focus_filter(self) -> None:
        self.query_one(f"#{self._widget_id('filter')}", Input).focus()

    def _highlighted_key(self) -> str | None:
        table = self.query_one(DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return None
        return table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value or None

    def action_open_detail(self) -> None:
        row_key = self._highlighted_key()
        if row_key:
            self.app.push_screen(self.detail_screen_for(row_key))

    def action_run(self) -> None:
        """Run the highlighted row without a detour via the detail screen."""
        table = self.query_one(DataTable)
        if table.cursor_row is None or table.row_count == 0:
            self.app.notify(self.NO_HIGHLIGHT_TEXT, severity="warning", timeout=3)
            return
        row_key = self._highlighted_key()
        if not row_key:
            return
        # Name the row the user picked in the toast, not an opaque id.
        name = next((item.name for item in self._all_items if self.item_id(item) == row_key), row_key)
        self.app.notify(f"Preparing run for {name}…", severity="information", timeout=2)
        self.start_run(row_key)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Mouse / Enter → open the row that was selected."""
        row_key = event.row_key.value
        if row_key:
            self.app.push_screen(self.detail_screen_for(row_key))

    # -- filtering -----------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != self._widget_id("filter"):
            return
        self._render_rows(self._filter(event.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in the filter moves focus to the table."""
        if event.input.id != self._widget_id("filter"):
            return
        table = self.query_one(DataTable)
        if table.row_count > 0:
            table.focus()

    def _filter(self, query: str) -> List[Any]:
        query = (query or "").strip().lower()
        if not query:
            return list(self._all_items)
        return [
            item for item in self._all_items
            if query in item.name.lower() or query in self.item_id(item).lower()
        ]

    # -- data ----------------------------------------------------------

    @work(thread=True, exclusive=True)
    def _load_items(self) -> None:
        try:
            items = self.load_items()
        except Exception as exc:  # noqa: BLE001 — surface any API/transport error
            self.app.call_from_thread(self._on_load_error, f"{self.LOAD_ERROR_TEXT}: {exc}")
            return
        self.app.call_from_thread(self._on_load_success, items)

    def _on_run_prep_error(self, message: str) -> None:
        self.app.notify(message, severity="error", timeout=6)

    def _on_load_success(self, items: List[Any]) -> None:
        self._stop_load_pulse()
        self._all_items = items
        try:
            # Keeps the header's ``[ Tab (N) ]`` badge in sync.
            self.app.set_tab_count(self.TAB_COUNT_KEY, len(items))
        except AttributeError:
            # Older test harnesses mount list screens on apps without
            # the count cache; the header then stays countless.
            pass
        # A refresh must not wipe the active filter.
        current_filter = self.query_one(f"#{self._widget_id('filter')}", Input).value
        self._render_rows(self._filter(current_filter))

    def _render_rows(self, items: List[Any]) -> None:
        table: DataTable = self.query_one(DataTable)
        status: Static = self.query_one(f"#{self._widget_id('status')}", Static)

        table.clear()
        for item in items:
            # Explicit key: without it Textual stores None as RowKey.value
            # and row selection cannot map back to the item.
            table.add_row(*self.row_cells(item), key=self.item_id(item))

        total = len(self._all_items)
        shown = len(items)
        if total == 0:
            status.update(self.EMPTY_TEXT)
        elif shown == 0:
            status.update(f"No matches — {total} {self.HIDDEN_NOUN} hidden by filter.")
        elif shown == total:
            status.update(f"{total} {self.COUNT_NOUN}. Enter to open, R to run, r to refresh, / to filter.")
        else:
            status.update(f"{shown} of {total} shown. R to run, / to edit filter, r to refresh.")

    def _on_load_error(self, message: str) -> None:
        self._stop_load_pulse()
        status: Static = self.query_one(f"#{self._widget_id('status')}", Static)
        status.update(f"[b red]{message}[/]")
