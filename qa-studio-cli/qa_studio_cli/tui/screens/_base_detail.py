"""Shared parts of the detail screens (use case, suite, execution).

* :class:`ProgressiveLoadMixin` — fan the section fetches out in parallel and
  render each section as soon as its call returns, with a ``Loading… N/M``
  status line and per-section error messages that never block the others.
* :func:`step_field_lines` — the "every populated field, priority fields
  first" listing used by the step-detail panes.

Screens keep their own layout, bindings and render methods; they supply the
sections and the widget a section error goes to.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, ClassVar, Dict, Iterable, List, Sequence, Tuple

from textual.widgets import Static

#: (section name, fetch with no arguments, render(fetched value))
Section = Tuple[str, Callable[[], Any], Callable[[Any], None]]


class ProgressiveLoadMixin:
    """Progressive, per-section loading for a detail screen.

    Subclasses set :attr:`_SECTION_NAMES` and :attr:`STATUS_SELECTOR` and may
    override :meth:`section_error_selector`.  The load pulse comes from
    ``LoadPulseMixin`` on the screen.
    """

    _SECTION_NAMES: ClassVar[Sequence[str]]
    #: Selector of the top-level ``Static`` status line.
    STATUS_SELECTOR: ClassVar[str]

    def section_error_selector(self, name: str) -> str:
        """Where a failed section's message goes (default: the status line)."""
        return self.STATUS_SELECTOR

    async def _load_sections(self, sections: Iterable[Section]) -> bool:
        """Fetch + render every section; ``True`` when all of them succeeded.

        On full success the status line is cleared; otherwise it keeps
        whatever the failing sections wrote.
        """
        self._loaded_sections: Dict[str, Any] = {}
        self._sections_done = 0
        status = self.query_one(self.STATUS_SELECTOR, Static)
        status.update(f"Loading… 0/{len(self._SECTION_NAMES)}")

        self._start_load_pulse()
        try:
            await asyncio.gather(*(self._fetch_and_render(*section) for section in sections))
        finally:
            # Stop (and reset the colour) even on cancellation.
            self._stop_load_pulse()

        complete = set(self._loaded_sections) == set(self._SECTION_NAMES)
        if complete:
            status.update("")
        return complete

    async def _fetch_and_render(self, name: str, fetch: Callable[[], Any], render: Callable[[Any], None]) -> None:
        """One section's pipeline; failures stay inside the section.

        The fetch runs via ``asyncio.to_thread`` so the event loop keeps
        painting the sections that already arrived.
        """
        try:
            data = await asyncio.to_thread(fetch)
        except Exception as exc:  # noqa: BLE001
            self._render_section_error(name, str(exc))
            self._advance_load_progress()
            return
        try:
            render(data)
        except Exception as exc:  # noqa: BLE001 — a render bug must not kill the screen
            self._render_section_error(name, f"render failed: {exc}")
            self._advance_load_progress()
            return
        self._loaded_sections[name] = data
        self._advance_load_progress()

    def _advance_load_progress(self) -> None:
        """Bump the ``Loading… N/M`` counter; the final text is set by :meth:`_load_sections`."""
        self._sections_done += 1
        total = len(self._SECTION_NAMES)
        if self._sections_done >= total:
            return
        self.query_one(self.STATUS_SELECTOR, Static).update(f"Loading… {self._sections_done}/{total}")

    def _render_section_error(self, name: str, message: str) -> None:
        self.query_one(self.section_error_selector(name), Static).update(
            f"[b red]Failed to load {name}:[/] {message}"
        )


def is_empty_value(value: Any) -> bool:
    """``None``, blank strings and empty collections; ``False`` and ``0`` are values."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def format_field_value(value: Any) -> str:
    """Scalars inline; dicts / lists pretty-printed as JSON on the next line."""
    if isinstance(value, (dict, list)):
        try:
            formatted = json.dumps(value, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            formatted = repr(value)
        return "\n" + formatted
    return str(value)


def step_field_lines(
    step: Dict[str, Any],
    priority: Sequence[str],
    format_value: Callable[[str, Any], str] = lambda _key, value: format_field_value(value),
) -> List[str]:
    """``[cyan]key[/]: value`` for every populated field, ``priority`` keys first, then alphabetical."""
    lines: List[str] = []
    seen: set[str] = set()
    for key in priority:
        if key in step and not is_empty_value(step[key]):
            lines.append(f"[cyan]{key}[/]: {format_value(key, step[key])}")
            seen.add(key)
    for key in sorted(step):
        if key in seen or is_empty_value(step[key]):
            continue
        lines.append(f"[cyan]{key}[/]: {format_value(key, step[key])}")
    return lines
