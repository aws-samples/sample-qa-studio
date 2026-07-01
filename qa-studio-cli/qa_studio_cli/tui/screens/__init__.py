"""Textual screens for the QA Studio TUI.

One screen per logical view. Each screen is self-contained (mount,
compose, bindings) and communicates with siblings via
``App.push_screen`` / ``App.pop_screen``.
"""
