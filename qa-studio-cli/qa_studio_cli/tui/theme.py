"""QA Studio TUI theme.

Defines a single Textual ``Theme`` — ``qa-studio-dark`` — registered
and activated by :class:`qa_studio_cli.tui.app.QAStudioTUIApp` on
mount.

Palette
-------
Built on the canonical Dracula palette (MIT-licensed, widely
documented at https://draculatheme.com/). Colour values are public
facts reused by countless editors and terminals; nothing here is
derived from any AGPL source. The palette was chosen because it
gives a calm dark background with a vivid green accent, which
matches the visual feel we wanted for the CLI's interactive mode.

Mapping rationale
-----------------
* ``primary`` — green (#50fa7b). Drives focus rings and hero accents.
* ``accent``  — purple (#bd93f9). Used in ``styles.tcss`` for panel
  separators; picking a hue distinct from ``primary`` keeps the
  separators from competing with interactive focus.
* ``secondary`` — cyan (#8be9fd). Reserved for informational chrome.
* ``warning`` / ``error`` / ``success`` — standard Dracula yellow /
  red / green.
* ``background`` / ``surface`` / ``panel`` — three steps of dark
  blue-grey so nested panels have a visible but subtle depth.

``$text-muted``, ``$boost``, etc. are derived by Textual from the
slots above plus ``luminosity_spread`` / ``text_alpha``; we leave
them at Textual's defaults to keep the derivation predictable.
"""

from __future__ import annotations

from textual.theme import Theme

THEME_NAME = "qa-studio-dark"

# Dracula palette (public, MIT). Kept as named constants so the
# theme definition below reads like a palette-to-slot mapping rather
# than a wall of hex. Public because other TUI components (e.g. the
# border-pulse animation) legitimately need to reference specific
# palette hues without re-deriving them from the Textual Theme slots.
DRACULA_BACKGROUND = "#282a36"
DRACULA_CURRENT_LINE = "#44475a"  # used for ``panel``
DRACULA_FOREGROUND = "#f8f8f2"
DRACULA_CYAN = "#8be9fd"
DRACULA_GREEN = "#50fa7b"
DRACULA_PINK = "#ff79c6"
DRACULA_PURPLE = "#bd93f9"
DRACULA_RED = "#ff5555"
DRACULA_YELLOW = "#f1fa8c"

# One step lighter than background for card-style surfaces. Sits
# between the background and the ``current-line`` panel tone.
_SURFACE = "#343746"


QA_STUDIO_DARK_THEME: Theme = Theme(
    name=THEME_NAME,
    primary=DRACULA_GREEN,
    secondary=DRACULA_CYAN,
    accent=DRACULA_PURPLE,
    warning=DRACULA_YELLOW,
    error=DRACULA_RED,
    success=DRACULA_GREEN,
    foreground=DRACULA_FOREGROUND,
    background=DRACULA_BACKGROUND,
    surface=_SURFACE,
    panel=DRACULA_CURRENT_LINE,
    dark=True,
    variables={
        # Pink is the Dracula "highlight" hue — nice for selection
        # backgrounds. Textual falls back to ``$accent`` otherwise,
        # which would make selections purple-on-purple against panels.
        "input-selection-background": f"{DRACULA_PINK} 35%",
        # Footer keys on pink keeps them readable and distinct from
        # primary/accent without requiring an extra slot.
        "footer-key-foreground": DRACULA_PINK,
    },
)
"""Module-level singleton — safe to import and re-register; Textual's
``register_theme`` overwrites any existing entry with the same name.
"""
