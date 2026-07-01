"""Integration tests for :class:`BorderPulse` on the four additional
screens wired up in this change set:

* ``UsecasesListScreen``
* ``SuitesListScreen``
* ``SuiteDetailScreen``
* ``ExecutionDetailScreen``

The ``UsecaseDetailScreen`` integration already has its own coverage
in :mod:`tests.test_tui_border_pulse`; we don't repeat it here.

Strategy
--------
Each screen uses a ``@work(thread=True)`` loader with a main-thread
success/error callback. We gate the primary API call with a
``threading.Event`` so the mid-load state (pulse running) is
observable from the test. Once the gate is released and the event
loop has drained, the pulse must be stopped.

Assertions are deliberately thin — the full pulse contract
(idempotent start/stop, color-reset, tick math) is covered in
:mod:`tests.test_tui_border_pulse`. Here we only verify each
screen's wiring.
"""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest

pytest.importorskip("textual")

from qa_studio_cli.tui.api import TuiApi  # noqa: E402
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.screens.execution_detail import (  # noqa: E402
    ExecutionDetailScreen,
)
from qa_studio_cli.tui.screens.suite_detail import SuiteDetailScreen  # noqa: E402
from qa_studio_cli.tui.screens.suites_list import SuitesListScreen  # noqa: E402
from qa_studio_cli.tui.screens.usecases_list import UsecasesListScreen  # noqa: E402


# --- Shared helpers -----------------------------------------------------

def _wait_for_gate(slow_gate: threading.Event) -> None:
    """Block the calling (worker) thread on the gate with a safety cap.

    5s is well above the test's needs — it exists so a bug that
    forgets to release the gate fails fast instead of hanging CI.
    """
    released = slow_gate.wait(timeout=5.0)
    assert released, "gate never released — check the test drove the mock correctly"


def _assert_pulse_cycle(pulse_attr_owner, slow_gate: threading.Event, pilot) -> None:
    """Shared mid-load → post-load assertion.

    Kept out-of-class so each screen-specific test stays a terse
    arrange-act-assert block.
    """
    assert pulse_attr_owner._load_pulse is not None, (
        "screen didn't instantiate BorderPulse on mount"
    )
    assert pulse_attr_owner._load_pulse.is_running is True, (
        "pulse should be running while the API call is gated"
    )


async def _drain_pumps(pilot, count: int = 4) -> None:
    """Enough event-loop ticks for the worker callback to land and
    for the pulse stop() call to settle on the main thread."""
    for _ in range(count):
        await pilot.pause()


# --- UsecasesListScreen -------------------------------------------------

class TestPulseOnUsecasesList:
    def test_pulse_runs_during_load_and_stops_after(self):
        slow_gate = threading.Event()

        def slow_list_usecases():
            _wait_for_gate(slow_gate)
            return []

        async def _run():
            api = MagicMock(spec=TuiApi)
            api.list_usecases.side_effect = slow_list_usecases
            app = QAStudioTUIApp(tui_api=api)
            try:
                async with app.run_test() as pilot:
                    # The landing screen IS UsecasesListScreen — no
                    # push needed. Drain pumps for mount + worker
                    # scheduling.
                    await _drain_pumps(pilot, count=3)

                    screen = app.screen
                    assert isinstance(screen, UsecasesListScreen)
                    _assert_pulse_cycle(screen, slow_gate, pilot)

                    slow_gate.set()
                    await _drain_pumps(pilot)

                    assert screen._load_pulse.is_running is False, (
                        "pulse should be stopped once the list finished loading"
                    )
            finally:
                slow_gate.set()

        asyncio.run(_run())


# --- SuitesListScreen ---------------------------------------------------

class TestPulseOnSuitesList:
    def test_pulse_runs_during_load_and_stops_after(self):
        slow_gate = threading.Event()

        def slow_list_suites():
            _wait_for_gate(slow_gate)
            return []

        async def _run():
            api = MagicMock(spec=TuiApi)
            # The landing screen still loads its own usecases list, so
            # give it a fast empty return; the *suites* call is the
            # one we gate.
            api.list_usecases.return_value = []
            api.list_suites.side_effect = slow_list_suites
            app = QAStudioTUIApp(tui_api=api)
            try:
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.push_screen(SuitesListScreen())
                    await _drain_pumps(pilot, count=3)

                    screen = app.screen
                    assert isinstance(screen, SuitesListScreen)
                    _assert_pulse_cycle(screen, slow_gate, pilot)

                    slow_gate.set()
                    await _drain_pumps(pilot)

                    assert screen._load_pulse.is_running is False
            finally:
                slow_gate.set()

        asyncio.run(_run())


# --- SuiteDetailScreen --------------------------------------------------

class TestPulseOnSuiteDetail:
    def test_pulse_runs_during_load_and_stops_after(self):
        slow_gate = threading.Event()

        def slow_get_suite(_suite_id):
            _wait_for_gate(slow_gate)
            return {"name": "Gated suite"}

        async def _run():
            api = MagicMock(spec=TuiApi)
            api.list_usecases.return_value = []
            api.get_suite.side_effect = slow_get_suite
            api.list_suite_usecases.return_value = []
            app = QAStudioTUIApp(tui_api=api)
            try:
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.push_screen(SuiteDetailScreen(suite_id="s-1"))
                    await _drain_pumps(pilot, count=3)

                    screen = app.screen
                    assert isinstance(screen, SuiteDetailScreen)
                    _assert_pulse_cycle(screen, slow_gate, pilot)

                    slow_gate.set()
                    await _drain_pumps(pilot)

                    assert screen._load_pulse.is_running is False
            finally:
                slow_gate.set()

        asyncio.run(_run())


# --- ExecutionDetailScreen ---------------------------------------------

class TestPulseOnExecutionDetail:
    def test_pulse_runs_during_load_and_stops_after(self):
        slow_gate = threading.Event()

        def slow_get_metadata(_usecase_id, _execution_id):
            _wait_for_gate(slow_gate)
            return {"status": "succeeded"}

        async def _run():
            api = MagicMock(spec=TuiApi)
            api.list_usecases.return_value = []
            # ExecutionDetailScreen now drives metadata + steps
            # independently via asyncio.gather. Gate the metadata
            # call — the pulse runs while either section is pending,
            # so gating one is enough to observe the mid-load state.
            # Steps returns immediately.
            api.get_execution_metadata.side_effect = slow_get_metadata
            api.get_execution_steps.return_value = []
            app = QAStudioTUIApp(tui_api=api)
            try:
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.push_screen(
                        ExecutionDetailScreen(
                            usecase_id="u-1", execution_id="e-1"
                        )
                    )
                    await _drain_pumps(pilot, count=3)

                    screen = app.screen
                    assert isinstance(screen, ExecutionDetailScreen)
                    _assert_pulse_cycle(screen, slow_gate, pilot)

                    slow_gate.set()
                    await _drain_pumps(pilot)

                    assert screen._load_pulse.is_running is False
            finally:
                slow_gate.set()

        asyncio.run(_run())
