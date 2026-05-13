"""Progressive-render regression guard for :class:`ExecutionDetailScreen`.

The execution detail screen now fans out its two rendered sections
(``get_execution_metadata`` and ``get_execution_steps``) in parallel
via ``asyncio.gather`` and paints each as its call returns, instead
of waiting on the old composite ``get_execution_detail`` that did
four serial HTTP calls. This test locks that behaviour in place.

Strategy
--------
Mirror of :mod:`tests.test_tui_progressive_loading` for the usecase
detail. We gate ``get_execution_steps`` with a ``threading.Event`` so
the mid-load window is observable: while the gate is closed, the
(fast) metadata section must already be rendered and the status line
must still read ``Loading… N/2``. Once the gate is released and the
event loop drains, the status clears.
"""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest

pytest.importorskip("textual")

from textual.widgets import Static  # noqa: E402

from qa_studio_cli.tui.api import TuiApi  # noqa: E402
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.screens.execution_detail import (  # noqa: E402
    ExecutionDetailScreen,
)


def _make_gated_api(slow_gate: threading.Event) -> MagicMock:
    """Metadata fast, steps gated. That way the fast section renders
    while the slow one is still blocked — the exact state the test
    wants to observe."""

    def slow_get_steps(*_args, **_kwargs):
        released = slow_gate.wait(timeout=5.0)
        assert released, "gate never released — check test drove the mock correctly"
        return []

    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = []
    api.get_execution_metadata.return_value = {
        "id": "e-1",
        "usecase_name": "ProgressiveExecution",
        "status": "success",
        "trigger_type": "ci_runner",
        "triggered_by": "alice",
    }
    api.get_execution_steps.side_effect = slow_get_steps
    return api


class TestExecutionProgressiveRender:
    def test_metadata_renders_before_steps_resolve(self):
        slow_gate = threading.Event()

        async def _run():
            api = _make_gated_api(slow_gate)
            app = QAStudioTUIApp(tui_api=api)
            try:
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.push_screen(ExecutionDetailScreen("u-1", "e-1"))
                    # A handful of pumps is enough for the fast
                    # ``asyncio.to_thread`` metadata call to complete
                    # and for its render to apply; steps is still
                    # gated on ``slow_gate``.
                    for _ in range(4):
                        await pilot.pause()

                    screen = app.screen
                    assert isinstance(screen, ExecutionDetailScreen)

                    # Metadata (fast) should already be painted with the
                    # execution's usecase_name before steps resolves.
                    metadata_text = str(
                        screen.query_one(
                            "#execution-metadata", Static
                        ).renderable
                    )
                    assert "ProgressiveExecution" in metadata_text, (
                        "metadata should render while steps is still pending"
                    )

                    # Status widget should reflect ongoing work. The
                    # exact count depends on scheduling jitter; we
                    # insist only on the ``Loading… N/2`` shape.
                    status_text = str(
                        screen.query_one(
                            "#execution-status", Static
                        ).renderable
                    )
                    assert "Loading" in status_text, (
                        "status should still show a loading counter while "
                        "steps is gated"
                    )
                    assert "/2" in status_text

                    # Release the gate and drain. A clean load clears
                    # the status line.
                    slow_gate.set()
                    for _ in range(4):
                        await pilot.pause()

                    final_status = str(
                        screen.query_one(
                            "#execution-status", Static
                        ).renderable
                    )
                    assert final_status == "", (
                        "status should be cleared once both sections resolved"
                    )
            finally:
                # Ensure we never leave the gated worker hanging if
                # an assertion failed above.
                slow_gate.set()

        asyncio.run(_run())
