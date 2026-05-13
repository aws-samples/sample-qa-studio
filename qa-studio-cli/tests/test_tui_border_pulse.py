"""Tests for :mod:`qa_studio_cli.tui.border_pulse` and its integration
with :class:`UsecaseDetailScreen`.

Three layers:

1. Pure math — ``pulse_factor`` is a deterministic function of time
   and period; we lock the key waypoints (0, half-period, full period)
   so future refactors can't silently flip the curve shape.

2. Lifecycle — ``start`` / ``stop`` are idempotent and ``stop``
   returns the widget's border to the configured idle colour. These
   are driven through a real Textual app because ``set_interval``
   needs a running message pump.

3. Progressive-load integration — while the usecase detail screen is
   loading, the pulse timer is active; once all sections have resolved
   the timer is stopped. We gate the slow section with a
   ``threading.Event`` to make the "mid-load" window observable from
   the test, same pattern as in ``test_tui_progressive_loading.py``.
"""

import asyncio
import math
import threading
from unittest.mock import MagicMock

import pytest

pytest.importorskip("textual")

from textual.app import App, ComposeResult  # noqa: E402
from textual.color import Color  # noqa: E402
from textual.widgets import Static  # noqa: E402

from qa_studio_cli.tui.api import TuiApi  # noqa: E402
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.border_pulse import BorderPulse, pulse_factor  # noqa: E402
from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen  # noqa: E402


# --- Pure curve math ---------------------------------------------------

class TestPulseFactor:
    """Lock the shape of the pulse curve.

    Small numerical deltas guard against someone swapping the
    cosine for something else (e.g. a sawtooth) without noticing.
    """

    def test_zero_elapsed_gives_zero_factor(self):
        assert pulse_factor(0.0, 1.8) == pytest.approx(0.0, abs=1e-9)

    def test_half_period_peaks_at_one(self):
        assert pulse_factor(0.9, 1.8) == pytest.approx(1.0, abs=1e-9)

    def test_full_period_returns_to_zero(self):
        assert pulse_factor(1.8, 1.8) == pytest.approx(0.0, abs=1e-9)

    def test_bounded_in_unit_interval(self):
        # Sweep the first full period; factor must stay in [0, 1].
        # This is what makes ``Color.blend(a, b, factor)`` safe.
        for step in range(0, 181, 5):
            t = step / 100.0  # 0.00 … 1.80
            value = pulse_factor(t, 1.8)
            assert 0.0 - 1e-9 <= value <= 1.0 + 1e-9

    def test_zero_period_returns_zero(self):
        # Degenerate configuration — guard against ZeroDivisionError.
        assert pulse_factor(0.5, 0.0) == 0.0


# --- Constructor validation --------------------------------------------

class TestBorderPulseConstruction:
    def test_rejects_invalid_edge(self):
        # Catch typos at construction rather than silently animating
        # the wrong border (or nothing at all).
        dummy_widget = MagicMock()
        with pytest.raises(ValueError):
            BorderPulse(dummy_widget, "#000", "#fff", edge="middle")

    def test_rejects_non_positive_period(self):
        dummy_widget = MagicMock()
        with pytest.raises(ValueError):
            BorderPulse(dummy_widget, "#000", "#fff", period=0)

    def test_rejects_non_positive_interval(self):
        dummy_widget = MagicMock()
        with pytest.raises(ValueError):
            BorderPulse(dummy_widget, "#000", "#fff", interval=-0.01)


# --- Lifecycle (needs a running Textual app) ---------------------------

class _PulseHost(App):
    """Minimal app that owns a single bordered Static.

    Used by lifecycle tests so ``set_interval`` has a real message
    pump to attach to — a bare ``MagicMock`` widget can't own a
    ``Timer``.
    """

    CSS = """
    #target { border-bottom: solid red; height: 3; }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="target")


class TestBorderPulseLifecycle:
    def test_start_sets_running_and_stop_clears_it(self):
        async def _run():
            app = _PulseHost()
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one("#target", Static)
                pulse = BorderPulse(
                    widget,
                    color_a="#111111",
                    color_b="#ffffff",
                    interval=0.05,
                )
                assert pulse.is_running is False

                pulse.start()
                assert pulse.is_running is True

                pulse.stop()
                assert pulse.is_running is False

        asyncio.run(_run())

    def test_start_is_idempotent(self):
        async def _run():
            app = _PulseHost()
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one("#target", Static)
                pulse = BorderPulse(
                    widget, color_a="#111111", color_b="#ffffff"
                )
                pulse.start()
                # Capture timer identity — a second ``start()`` must
                # not replace it (otherwise we'd leak the first one).
                first_timer = pulse._timer
                pulse.start()
                assert pulse._timer is first_timer
                pulse.stop()

        asyncio.run(_run())

    def test_stop_resets_border_to_color_a(self):
        async def _run():
            app = _PulseHost()
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one("#target", Static)
                pulse = BorderPulse(
                    widget,
                    color_a="#112233",
                    color_b="#ffeedd",
                    interval=0.02,
                )
                pulse.start()
                # Let a few ticks run so the border is somewhere
                # between the two colours.
                for _ in range(3):
                    await pilot.pause()
                pulse.stop()
                # After stop, border_bottom must be exactly color_a —
                # a predictable final frame is the whole point of the
                # ``_apply(color_a)`` call in ``stop``.
                style, final_color = widget.styles.border_bottom
                assert style == "thick"
                assert final_color == Color.parse("#112233")

        asyncio.run(_run())


# --- Integration with the detail screen --------------------------------

def _gated_api(slow_gate: threading.Event) -> MagicMock:
    """API stub — all sections fast except list_executions, which
    blocks on the gate. Mirrors ``test_tui_progressive_loading.py``."""

    def slow_list_executions(*_args, **_kwargs):
        released = slow_gate.wait(timeout=5.0)
        assert released, "gate never released"
        return []

    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = []
    api.get_usecase.return_value = {
        "name": "Pulsing",
        "starting_url": "https://example.com/",
        "test_platform": "web",
    }
    api.get_steps.return_value = []
    api.get_variables.return_value = {}
    api.get_headers.return_value = {}
    api.get_secrets.return_value = []
    api.list_executions.side_effect = slow_list_executions
    return api


class TestBorderPulseDuringLoad:
    def test_pulse_runs_during_load_and_stops_after(self):
        """While any section is pending, ``is_running`` is True;
        once everything resolves it flips back to False."""

        slow_gate = threading.Event()

        async def _run():
            api = _gated_api(slow_gate)
            app = QAStudioTUIApp(tui_api=api)
            try:
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                    # Drain enough pumps for on_mount to build the
                    # pulse and _load_detail to call start().
                    for _ in range(4):
                        await pilot.pause()

                    screen = app.screen
                    assert isinstance(screen, UsecaseDetailScreen)
                    assert screen._load_pulse is not None

                    # Mid-load: slow section still gated, so the
                    # pulse must still be running.
                    assert screen._load_pulse.is_running is True, (
                        "pulse should be active while at least one "
                        "section is still pending"
                    )

                    # Release the slow call and drain; the ``finally``
                    # in _load_detail must stop the pulse.
                    slow_gate.set()
                    for _ in range(4):
                        await pilot.pause()

                    assert screen._load_pulse.is_running is False, (
                        "pulse should be stopped once every section resolved"
                    )
            finally:
                slow_gate.set()

        asyncio.run(_run())
