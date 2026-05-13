"""Shared three-row app header.

Used on every TUI screen to keep the QA Studio brand, the installed
CLI version, and the top-level navigation tabs in a fixed place
across the whole application. Replaces the earlier single-row
``AppHeaderBar`` (brand + version) plus Textual's built-in ``Header``
widget (screen title + subtitle) — one block of chrome instead of
two.

Layout::

    ┌──────────┬──────────────────────────────────┐
    │ LOGO (3) │                          v0.2.0  │  ← row 1: version
    │ LOGO (3) │                   user@acme.com  │  ← row 2: identity
    │ LOGO (3) │ [ Usecases ]  [ Test Suites ]    │  ← row 3: nav tabs
    └──────────┴──────────────────────────────────┘
    ══════════ thick accent bar (pulse target) ═══

The thick accent bar at the bottom edge is also the target of
``LoadPulseMixin``: every screen's loader drives the same bar, so
the "something is loading" signal sits in a single fixed place above
everything else instead of hiding inside a per-section divider.

The identity row renders whichever auth source the CLI will actually
use for API calls — see :func:`qa_studio_cli.auth.identity.get_display_identity`.
It stays a reserved 1-row slot even when no identity is available so
the layout doesn't shift between authenticated and unauthenticated
states.
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from qa_studio_cli import __version__
from qa_studio_cli.auth.identity import get_display_identity


# Identifiers passed to :class:`AppHeader` so the header knows which
# tab to highlight. Screens share an active tab with their own child
# screens (e.g. a usecase detail still highlights ``Usecases``) so
# context stays stable as the user drills in and back out.
TAB_USECASES = "usecases"
TAB_SUITES = "suites"


class AppHeader(Horizontal):
    """Three-row brand + navigation header, shared across every screen."""

    # Three-row logo. Each row is 33 characters wide — important so
    # the block renders as a true rectangle and doesn't wobble when
    # concatenated with surrounding chrome. Hand-crafted line-based
    # rendering of ``QA Studio`` using the rounded box-drawing family.
    # The ``╲`` inside row 2 of Q is what distinguishes it from O —
    # both letters share the same outer box, so without the diagonal
    # the logo reads as "OA Studio".
    LOGO = (
        "╭─╮ ╭─╮   ╭─╮ ╶┬╴ ╷ ╷ ╭─╮ ╶┬╴ ╭─╮\n"
        "│╲│ ├─┤   ╰─╮  │  │ │ │ │  │  │ │\n"
        "╰─╯ ╵ ╵   ╰─╯  ╵  ╰─╯ ╰─╯ ╶┴╴ ╰─╯"
    )

    DEFAULT_CSS = """
    AppHeader {
        height: 4;
        background: $surface;
        padding: 0 1;
        /* Thick accent border on the *top* edge — this is the pulse
         * target, so the "something is loading" signal sits at the
         * very top of the screen, above everything else. Widget is
         * ``height: 4`` so the 3-row logo clears the 1-row border
         * without being clipped. */
        border-top: thick $accent;
    }
    AppHeader > #app-header-logo {
        width: auto;
        height: 3;
        color: $primary;
        padding: 0 2 0 0;
    }
    AppHeader > #app-header-right {
        width: 1fr;
        height: 3;
    }
    AppHeader #app-header-version {
        width: 100%;
        height: 1;
        content-align: right middle;
        color: $text-muted;
    }
    AppHeader #app-header-identity {
        width: 100%;
        height: 1;
        content-align: right middle;
        color: $text-muted;
    }
    AppHeader #app-header-tabs {
        width: 100%;
        height: 1;
    }
    AppHeader .app-header-tab {
        width: auto;
        padding: 0 2;
        color: $text-muted;
    }
    AppHeader .app-header-tab.-active {
        color: $primary;
        text-style: bold;
    }
    """

    def __init__(self, active: str | None = None) -> None:
        """
        Args:
            active: Either :data:`TAB_USECASES`, :data:`TAB_SUITES`,
                or ``None`` (no tab highlighted). Passed from each
                screen to keep the header stateless about which
                subclass it sits inside.
        """
        super().__init__()
        self._active = active

    def compose(self) -> ComposeResult:
        yield Static(self.LOGO, id="app-header-logo")
        with Vertical(id="app-header-right"):
            yield Static(f"v{__version__}", id="app-header-version")
            # Identity row is always mounted (even when empty) so the
            # three-row right column keeps its fixed height regardless
            # of whether auth is configured. Populated in on_mount —
            # resolving the identity touches the filesystem so we
            # defer it off the compose hot path.
            yield Static("", id="app-header-identity")
            with Horizontal(id="app-header-tabs"):
                # Labels are intentionally placeholder here — filled
                # in on_mount via ``refresh_tab_labels`` so the tab
                # count (``[ Usecases (42) ]``) comes from the app's
                # shared cache. Without this two-phase setup the
                # first-paint label would always be countless.
                yield Static(
                    self._format_tab_label("Usecases", count=None),
                    classes="app-header-tab",
                    id="tab-usecases",
                )
                yield Static(
                    self._format_tab_label("Test Suites", count=None),
                    classes="app-header-tab",
                    id="tab-suites",
                )

    def on_mount(self) -> None:
        # Apply the active-tab class after the widgets exist. We can't
        # do this in ``compose`` because ``add_class`` touches live
        # DOM state.
        if self._active == TAB_USECASES:
            self.query_one("#tab-usecases", Static).add_class("-active")
        elif self._active == TAB_SUITES:
            self.query_one("#tab-suites", Static).add_class("-active")

        # Populate the identity row. ``get_display_identity`` never
        # raises on missing-config / missing-token paths, so a bare
        # call is safe here; any truly unexpected failure (e.g. a
        # corrupt pydantic model) falls back to an empty row rather
        # than crashing the whole header.
        try:
            identity = get_display_identity()
        except Exception:  # noqa: BLE001 — header must never crash
            identity = None
        if identity:
            self.query_one("#app-header-identity", Static).update(identity)

        # Render tab labels from whatever counts the app already has
        # cached. If either count is still unknown, kick off a
        # background fetch so the badge fills in without the user
        # having to visit that tab first.
        self.refresh_tab_labels()
        if self._needs_count_fetch():
            self._fetch_missing_counts()

    def refresh_tab_labels(self) -> None:
        """Re-render both tab labels from the app's count cache.

        Called after :meth:`QAStudioTUIApp.set_tab_count` updates the
        shared cache — every mounted header re-reads the cache and
        updates its own label. Preserves the ``-active`` class on
        whichever tab was highlighted (``update`` only changes
        renderable text, not classes).
        """
        counts = self._safe_tab_counts()
        try:
            usecases = self.query_one("#tab-usecases", Static)
            suites = self.query_one("#tab-suites", Static)
        except Exception:  # noqa: BLE001 — widget not mounted yet
            return
        usecases.update(
            self._format_tab_label("Usecases", counts.get("usecases"))
        )
        suites.update(
            self._format_tab_label("Test Suites", counts.get("suites"))
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_tab_label(name: str, count: int | None) -> str:
        """Build the ``[ Name (N) ]`` string.

        When the count is unknown we fall back to the bare ``[ Name ]``
        rather than ``(?)`` — a missing badge reads as "loading", an
        explicit question mark reads as "broken".
        """
        if count is None:
            return f"[ {name} ]"
        return f"[ {name} ({count}) ]"

    def _safe_tab_counts(self) -> dict[str, int | None]:
        """Read the app's tab-count cache defensively.

        Tests sometimes mount :class:`AppHeader` via an app that
        doesn't expose a ``tab_counts`` attribute (older fixtures,
        standalone-widget tests). Fall back to a cache-miss in that
        case so the header still renders.
        """
        return getattr(self.app, "tab_counts", {}) or {}

    def _needs_count_fetch(self) -> bool:
        counts = self._safe_tab_counts()
        return counts.get("usecases") is None or counts.get("suites") is None

    @work(thread=True, group="app-header-tab-counts", exclusive=True)
    def _fetch_missing_counts(self) -> None:
        """Populate any missing entries in the app's count cache.

        Piggy-backs on the existing ``list_*`` endpoints rather than
        introducing a dedicated count endpoint — a list is small
        enough that ``len()`` of the result is cheap, and adding
        server-side counts is out of scope for a cosmetic header
        badge. Errors are swallowed (the badge is purely informational).
        """
        api = getattr(self.app, "tui_api", None)
        counts = self._safe_tab_counts()
        if api is None:
            return

        if counts.get("usecases") is None:
            try:
                items = api.list_usecases()
            except Exception:  # noqa: BLE001 — cosmetic; do not crash
                items = None
            if items is not None:
                self.app.call_from_thread(
                    self.app.set_tab_count, "usecases", len(items)
                )

        if counts.get("suites") is None:
            try:
                items = api.list_suites()
            except Exception:  # noqa: BLE001
                items = None
            if items is not None:
                self.app.call_from_thread(
                    self.app.set_tab_count, "suites", len(items)
                )

    def on_click(self, event) -> None:
        """Clicks on either tab dispatch to the same app actions that
        the ``1`` / ``2`` keyboard bindings already use. Keeps the two
        navigation paths in one place.
        """
        widget_id = event.widget.id if event.widget else None
        if widget_id == "tab-usecases":
            self.app.action_show_usecases()
        elif widget_id == "tab-suites":
            self.app.action_show_suites()
