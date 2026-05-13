"""Pulsing border animation for "work-in-progress" indicators.

Used by screens that kick off a multi-step load: while the load is in
flight, the border between the header block and the content area
pulses between two theme-aware colours; when everything has resolved,
the pulse stops and the border returns to its idle colour.

Why a standalone helper (and not a Textual CSS class toggle)
-----------------------------------------------------------
Two discrete classes toggling on a timer produces a *blink*, which
reads as "something is wrong" more than "something is loading".
Smooth colour interpolation — which is what you get from
:meth:`textual.color.Color.blend` — reads as a calm "alive" state.
Textual 0.89 doesn't expose ``border_bottom_color`` as a directly
animatable attribute (that arrived later), so we drive the colour
manually with ``set_interval`` and overwrite ``border_bottom`` with a
``(style, Color)`` tuple on each tick. Cheap, predictable, and easy
to stop.

Lifecycle contract
------------------
* ``start()`` — idempotent. Calling twice without an intervening
  ``stop()`` is a no-op so callers don't have to track state.
* ``stop()`` — idempotent. Always returns the border to ``color_a``
  (the idle colour) so the widget has a predictable final frame.
* The internal ``set_interval`` timer is owned by the target widget,
  so when the widget is unmounted Textual cancels the timer for us.
  We still guard ``_apply`` against unmounted widgets defensively in
  case ``stop`` is invoked from an async teardown race.
"""

from __future__ import annotations

import math
from typing import ClassVar, Optional, Union

from textual.color import Color
from textual.timer import Timer
from textual.widget import Widget

from qa_studio_cli.tui.theme import DRACULA_GREEN, DRACULA_PURPLE

ColorLike = Union[str, Color]

_VALID_EDGES = ("bottom", "top", "left", "right")


def _to_color(value: ColorLike) -> Color:
    """Normalise a string or Color into a ``textual.color.Color``."""
    if isinstance(value, Color):
        return value
    return Color.parse(value)


def pulse_factor(elapsed: float, period: float) -> float:
    """Return a smooth 0 → 1 → 0 factor for time ``elapsed`` within ``period``.

    Pulled out as a pure function so the animation curve is
    independently testable — the rest of :class:`BorderPulse` is
    timer-driven and awkward to assert on directly. Uses a shifted
    sine so the curve starts at 0, peaks at ``period/2`` and returns
    to 0 at ``period``, giving a breathing rhythm rather than a
    sharp flash.
    """
    if period <= 0:
        return 0.0
    # ``(1 - cos(2πt/T)) / 2`` — always in [0, 1], zero at multiples of T.
    return (1.0 - math.cos(2.0 * math.pi * elapsed / period)) / 2.0


class BorderPulse:
    """Animate a widget's border edge by blending between two colours.

    Parameters
    ----------
    widget:
        The widget whose border will be animated. Must already be
        mounted at ``start()`` time so the style assignment takes.
    color_a, color_b:
        The two colours to blend between. ``color_a`` is the "idle"
        colour that the border returns to on stop; ``color_b`` is
        the peak colour of each pulse.
    edge:
        Which border edge to animate. One of ``"bottom"`` (default),
        ``"top"``, ``"left"``, ``"right"``.
    style:
        Border line style, applied unchanged on every tick (Textual
        requires a full ``(style, Color)`` tuple — no "colour-only"
        form in 0.89). Defaults to ``"thick"`` so the pulse reads
        as a genuinely filled bar at the top of the screen rather
        than a line; caller may override with ``"solid"`` / ``"heavy"``
        / etc. for a different weight.
    period:
        Seconds for one full pulse cycle (0 → peak → 0). Slow enough
        that the animation reads as calm, fast enough to clearly
        signal activity — ~1.8s works well in dense TUIs.
    interval:
        Frame interval for the timer, in seconds. 60 ms ≈ 17 fps,
        which is enough for a smooth blend without spamming redraws
        on remote sessions.
    """

    def __init__(
        self,
        widget: Widget,
        color_a: ColorLike,
        color_b: ColorLike,
        *,
        edge: str = "bottom",
        style: str = "thick",
        period: float = 1.8,
        interval: float = 0.06,
    ) -> None:
        if edge not in _VALID_EDGES:
            raise ValueError(
                f"edge must be one of {_VALID_EDGES}, got {edge!r}"
            )
        if period <= 0:
            raise ValueError(f"period must be positive, got {period!r}")
        if interval <= 0:
            raise ValueError(f"interval must be positive, got {interval!r}")

        self._widget = widget
        self._color_a = _to_color(color_a)
        self._color_b = _to_color(color_b)
        self._style = style
        self._period = period
        self._interval = interval
        self._attr = f"border_{edge}"

        self._timer: Optional[Timer] = None
        self._elapsed = 0.0

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._timer is not None

    def start(self) -> None:
        """Begin pulsing. No-op if already running."""
        if self._timer is not None:
            return
        self._elapsed = 0.0
        # Paint the first frame immediately so the idle colour doesn't
        # linger for up to ``interval`` seconds before the animation
        # visibly kicks in.
        self._apply(self._color_a)
        self._timer = self._widget.set_interval(self._interval, self._tick)

    def stop(self) -> None:
        """Stop pulsing and reset the border to the idle colour."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._apply(self._color_a)

    # ------------------------------------------------------------------
    # Tick logic (package-private for tests)
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        self._elapsed += self._interval
        factor = pulse_factor(self._elapsed, self._period)
        blended = self._color_a.blend(self._color_b, factor)
        self._apply(blended)

    def _apply(self, color: Color) -> None:
        """Write the border tuple, swallowing mount-race errors.

        When the owning screen is dismissed mid-pulse, the widget may
        be detached before ``stop()`` lands. Textual will cancel the
        timer on its own but a final tick can still be in flight, so
        we guard the style assignment.
        """
        try:
            setattr(self._widget.styles, self._attr, (self._style, color))
        except Exception:  # noqa: BLE001 — defensive: unmounted widget
            pass


class LoadPulseMixin:
    """Drop-in mixin that gives a Textual ``Screen`` a BorderPulse
    loading indicator with a single class-level selector.

    Usage
    -----
    >>> class MyScreen(LoadPulseMixin, Screen):
    ...     LOAD_PULSE_TARGET = "#my-metadata"
    ...
    ...     def on_mount(self) -> None:
    ...         # ... build widgets ...
    ...         self._install_load_pulse()
    ...         self._start_load_pulse()
    ...         self._begin_loading()
    ...
    ...     def _on_load_success(self, data):
    ...         self._stop_load_pulse()
    ...         # ... render ...

    Contract
    --------
    * ``LOAD_PULSE_TARGET`` — CSS selector for the widget whose border
      should pulse. Required; empty string raises at install time.
    * ``LOAD_PULSE_EDGE``, ``LOAD_PULSE_COLOR_A``, ``LOAD_PULSE_COLOR_B``
      — sensible defaults (bottom edge, Dracula purple → green) that
      match our theme. Override per-screen only when you need a
      different accent.
    * ``_install_load_pulse`` must be called once from ``on_mount``
      after widgets exist. Trying to start/stop before install is a
      silent no-op so lifecycle hazards (e.g. race on screen dismiss)
      don't bubble up as errors.

    Why not auto-install via ``on_mount``? Ordering matters: some
    screens focus widgets or add columns before they want the pulse
    visible. Making the call explicit keeps the sequence readable
    rather than hiding it inside MRO magic.
    """

    # Class-level defaults — override in the subclass. Kept in the
    # mixin (not duplicated across screens) so a future palette change
    # touches exactly one file.
    LOAD_PULSE_TARGET: ClassVar[str] = ""
    LOAD_PULSE_EDGE: ClassVar[str] = "top"
    LOAD_PULSE_COLOR_A: ClassVar[ColorLike] = DRACULA_PURPLE
    LOAD_PULSE_COLOR_B: ClassVar[ColorLike] = DRACULA_GREEN

    # Declared at class level so type checkers know the attribute
    # exists before ``_install_load_pulse`` runs; the actual instance
    # attribute is assigned in ``_install_load_pulse``.
    _load_pulse: Optional[BorderPulse] = None

    def _install_load_pulse(self) -> None:
        """Build the pulse against the configured target widget.

        Call once from the screen's ``on_mount``. Safe to call
        multiple times — subsequent calls stop the existing pulse
        and rebuild (useful if the target widget is recreated on
        refresh, which isn't our current pattern but keeps the
        method future-proof).
        """
        if not self.LOAD_PULSE_TARGET:
            raise ValueError(
                f"{type(self).__name__}: LOAD_PULSE_TARGET must be set "
                f"(e.g. '#my-metadata') to use LoadPulseMixin"
            )
        if self._load_pulse is not None:
            self._load_pulse.stop()
        # ``self.query_one`` is provided by the Screen base class;
        # mypy can't see that through a bare mixin, so we cast via a
        # tolerant ``getattr``. Runtime behaviour is unchanged.
        query_one = getattr(self, "query_one")
        self._load_pulse = BorderPulse(
            query_one(self.LOAD_PULSE_TARGET),
            color_a=self.LOAD_PULSE_COLOR_A,
            color_b=self.LOAD_PULSE_COLOR_B,
            edge=self.LOAD_PULSE_EDGE,
        )

    def _start_load_pulse(self) -> None:
        """Start pulsing. No-op if the pulse wasn't installed — makes
        the call safe inside handlers that might fire before mount
        (e.g. an immediate ``action_refresh``)."""
        if self._load_pulse is not None:
            self._load_pulse.start()

    def _stop_load_pulse(self) -> None:
        """Stop pulsing and reset the border to the idle colour. Same
        no-op semantics as ``_start_load_pulse`` for symmetry."""
        if self._load_pulse is not None:
            self._load_pulse.stop()
