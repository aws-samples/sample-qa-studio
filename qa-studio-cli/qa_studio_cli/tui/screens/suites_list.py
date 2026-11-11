"""Test suites list screen.

Flat, filterable list of the suites the user can access (behaviour in
:class:`BaseListScreen`): Enter opens :class:`SuiteDetailScreen`, ``R`` runs
the highlighted suite via :class:`SuiteRunFormScreen`.
"""

from __future__ import annotations

from textual import work

from qa_studio_cli.tui.api import SuiteListItem
from qa_studio_cli.tui.app_header import TAB_SUITES
from qa_studio_cli.tui.screens._base_list import BaseListScreen


class SuitesListScreen(BaseListScreen):
    """Flat list of test suites the user has access to."""

    TITLE = "Test suites"
    ID_PREFIX = "suites"
    TAB = TAB_SUITES
    TAB_COUNT_KEY = "suites"
    COLUMNS = ("Name", "ID", "Tests", "Description")
    LOADING_TEXT = "Loading test suites…"
    LOAD_ERROR_TEXT = "Failed to load test suites"
    EMPTY_TEXT = "No test suites found."
    NO_HIGHLIGHT_TEXT = "No test suite highlighted — arrow-key to a row first."
    HIDDEN_NOUN = "suite(s)"
    COUNT_NOUN = "test suite(s)"

    def load_items(self) -> list[SuiteListItem]:
        return self.app.tui_api.list_suites()

    def item_id(self, item: SuiteListItem) -> str:
        return item.suite_id

    def row_cells(self, item: SuiteListItem) -> tuple[str, ...]:
        description = item.description
        if len(description) > 60:
            description = description[:57] + "…"
        return (item.name, item.suite_id, str(item.total_usecases), description)

    def detail_screen_for(self, row_key: str):
        from qa_studio_cli.tui.screens.suite_detail import SuiteDetailScreen

        return SuiteDetailScreen(suite_id=row_key)

    def start_run(self, row_key: str) -> None:
        self._prepare_run(row_key)

    @work(thread=True, group="run-prep")
    def _prepare_run(self, suite_id: str) -> None:
        """Fetch the suite record (all the Run form reads) and open the form.

        Separate worker group from the list load, so preparing a run never
        cancels an in-flight refresh.
        """
        try:
            suite = self.app.tui_api.get_suite(suite_id)
        except Exception as exc:  # noqa: BLE001
            self.app.call_from_thread(self._on_run_prep_error, f"Could not prepare run: {exc}")
            return
        self.app.call_from_thread(self._on_run_prep_success, suite_id, suite)

    def _on_run_prep_success(self, suite_id: str, suite: dict) -> None:
        from qa_studio_cli.tui.screens.suite_run_form import SuiteRunFormScreen

        self.app.push_screen(SuiteRunFormScreen(suite_id=suite_id, suite=suite))
