"""Use cases list screen.

Flat, filterable list of every use case the user can access (behaviour in
:class:`BaseListScreen`): Enter opens :class:`UsecaseDetailScreen`, ``R`` runs
the highlighted row via :class:`RunFormScreen`, mirroring the detail screen.
"""

from __future__ import annotations

from textual import work

from qa_studio_cli.tui.api import UsecaseListItem
from qa_studio_cli.tui.app_header import TAB_USECASES
from qa_studio_cli.tui.screens._base_list import BaseListScreen


class UsecasesListScreen(BaseListScreen):
    """Flat list of every use case the user has access to."""

    TITLE = "Use cases"
    ID_PREFIX = "usecases"
    TAB = TAB_USECASES
    TAB_COUNT_KEY = "usecases"
    COLUMNS = ("Name", "ID", "Platform", "Region")
    LOADING_TEXT = "Loading use cases…"
    LOAD_ERROR_TEXT = "Failed to load use cases"
    EMPTY_TEXT = "No use cases found."
    NO_HIGHLIGHT_TEXT = "No use case highlighted — arrow-key to a row first."
    HIDDEN_NOUN = "use case(s)"
    COUNT_NOUN = "use case(s)"

    def load_items(self) -> list[UsecaseListItem]:
        return self.app.tui_api.list_usecases()

    def item_id(self, item: UsecaseListItem) -> str:
        return item.usecase_id

    def row_cells(self, item: UsecaseListItem) -> tuple[str, ...]:
        return (item.name, item.usecase_id, item.platform, item.region)

    def detail_screen_for(self, row_key: str):
        from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen

        return UsecaseDetailScreen(usecase_id=row_key)

    def start_run(self, row_key: str) -> None:
        self._prepare_run(row_key)

    @work(thread=True, group="run-prep")
    def _prepare_run(self, usecase_id: str) -> None:
        """Fetch the four Run-form inputs (use case, variables, headers,
        secrets) and open the form; no partial form is ever pushed.

        Sequential fetches: a user-triggered action already gated on network
        latency (~1–2 s total) does not justify parallel machinery.
        """
        api = self.app.tui_api
        try:
            usecase = api.get_usecase(usecase_id)
            variables = api.get_variables(usecase_id)
            headers = api.get_headers(usecase_id)
            secrets = api.get_secrets(usecase_id)
        except Exception as exc:  # noqa: BLE001 — any API/transport error
            self.app.call_from_thread(self._on_run_prep_error, f"Could not prepare run: {exc}")
            return
        self.app.call_from_thread(
            self._on_run_prep_success, usecase_id, usecase, variables, headers, secrets,
        )

    def _on_run_prep_success(
        self, usecase_id: str, usecase: dict, variables: dict, headers: dict, secrets: list,
    ) -> None:
        # Lazy import: keeps the form's subprocess machinery off every
        # startup path through this module.
        from qa_studio_cli.tui.screens.run_form import RunFormScreen

        self.app.push_screen(RunFormScreen(
            usecase_id=usecase_id, usecase=usecase, variables=variables, headers=headers, secrets=secrets,
        ))
