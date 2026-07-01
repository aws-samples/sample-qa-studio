"""Root Textual application for ``qa-studio tui``.

Constructs the shared API helper on startup (so screens don't need to
reassemble auth / config), registers global bindings, and pushes
``UsecasesListScreen`` as the initial screen.
"""

from __future__ import annotations

from typing import Dict, Optional

from textual.app import App
from textual.binding import Binding

from qa_studio_cli.tui.api import TuiApi, build_api_client
from qa_studio_cli.tui.app_header import AppHeader
from qa_studio_cli.tui.theme import QA_STUDIO_DARK_THEME, THEME_NAME


class QAStudioTUIApp(App):
    """QA Studio terminal UI.

    App-level concerns only: title, global bindings, shared services,
    initial screen. Screen-specific logic lives in
    ``qa_studio_cli.tui.screens.*``.
    """

    TITLE = "QA Studio"
    SUB_TITLE = "interactive mode (local-only execution)"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("1", "show_usecases", "Use cases", show=True),
        Binding("2", "show_suites", "Suites", show=True),
        Binding("question_mark", "help", "Help", show=True),
    ]

    CSS_PATH = "styles.tcss"

    def __init__(self, tui_api: TuiApi | None = None):
        """
        Args:
            tui_api: Optional pre-built ``TuiApi`` — intended for tests
                so they don't need a real config / token. Production
                callers leave this ``None`` and the app builds one.
        """
        super().__init__()
        self._injected_api = tui_api
        # Per-tab totals rendered in the AppHeader's nav labels
        # (e.g. ``[ Usecases (42) ]``). ``None`` means "not yet
        # known" — the header renders the bare label in that case
        # and kicks off a background fetch. Populated both from the
        # list screens (on successful load) and from the header's
        # own lazy fetch, whichever arrives first.
        self._tab_counts: Dict[str, Optional[int]] = {
            "usecases": None,
            "suites": None,
        }

    @property
    def tab_counts(self) -> Dict[str, Optional[int]]:
        """Read-only view of the cached tab counts. The header reads
        this on every render; list screens push updates through
        :meth:`set_tab_count` so the cache is always in sync with the
        most recently loaded list."""
        return self._tab_counts

    def set_tab_count(self, tab: str, count: int) -> None:
        """Store ``count`` for ``tab`` and refresh any visible
        :class:`AppHeader` so the label reflects the new number.

        Callers run on the Textual event-loop thread — the list
        screens invoke this from ``_on_load_success`` which is
        already marshalled via ``call_from_thread``. No extra
        thread-hopping required here.
        """
        if tab not in self._tab_counts:
            return
        self._tab_counts[tab] = count
        # Every screen renders its own AppHeader; ``query`` walks the
        # whole DOM so a count update is reflected everywhere at once
        # (a detail screen and the list share the same header class).
        for header in self.query(AppHeader):
            header.refresh_tab_labels()

    def on_mount(self) -> None:
        # Register and activate our dark theme before the first screen
        # is pushed so initial paints already use the right palette.
        # ``register_theme`` is idempotent — re-running it overwrites
        # by name — so this is safe even if a parent test framework
        # mounts the app more than once.
        self.register_theme(QA_STUDIO_DARK_THEME)
        self.theme = THEME_NAME

        # Build the API helper lazily on mount so config/token errors
        # surface as Textual notifications rather than crashing during
        # app construction.  Tests inject a pre-built TuiApi to avoid
        # touching the real config file.
        if self._injected_api is not None:
            self.tui_api = self._injected_api
        else:
            self.tui_api = TuiApi(build_api_client())

        # Lazy import to keep the module graph shallow.
        from qa_studio_cli.tui.screens.usecases_list import UsecasesListScreen

        self.push_screen(UsecasesListScreen())

    # ------------------------------------------------------------------
    # Global navigation
    # ------------------------------------------------------------------
    #
    # "1" and "2" always return to the corresponding list screen, even
    # from deep within a detail stack.  We use ``switch_screen`` after
    # popping detail screens so the back-stack doesn't accumulate.

    def action_show_usecases(self) -> None:
        from qa_studio_cli.tui.screens.usecases_list import UsecasesListScreen

        if isinstance(self.screen, UsecasesListScreen):
            return  # already here — no-op keeps the focus stable
        self._reset_to(UsecasesListScreen())

    def action_show_suites(self) -> None:
        from qa_studio_cli.tui.screens.suites_list import SuitesListScreen

        if isinstance(self.screen, SuitesListScreen):
            return
        self._reset_to(SuitesListScreen())

    def _reset_to(self, new_screen) -> None:
        """Swap the top of the stack with ``new_screen`` after popping
        any detail screens above the current list.

        ``screen_stack[0]`` is Textual's internal ``_default`` screen
        and must never be popped. We pop until the stack has exactly
        one user-pushed screen on top of ``_default`` (len == 2), then
        ``switch_screen`` replaces that top.
        """
        while len(self.screen_stack) > 2:
            self.pop_screen()
        self.switch_screen(new_screen)

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    def action_help(self) -> None:
        """Keybindings overlay — wired in a later commit. No-op stub
        for now so the binding is visible in the footer."""
        self.bell()
