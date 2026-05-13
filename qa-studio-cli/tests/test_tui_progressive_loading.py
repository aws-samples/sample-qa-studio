"""Progressive-render regression guard for :class:`UsecaseDetailScreen`.

The detail screen loads six sub-resources in parallel and renders
each as its API call returns, rather than blocking the first paint
on the sum of all six round-trips. This test pins that behaviour
so a future regression back to a serial-then-bulk-render pattern
gets flagged in CI.

Strategy
--------
We gate the ``list_executions`` API call with a ``threading.Event``.
While the gate is closed, the slow call is stuck on the thread pool.
Because the fast sections run concurrently via ``asyncio.gather``,
they should finish and render *before* the gated call returns. The
test asserts exactly that:

1. Mount the screen with a gated ``list_executions``.
2. Pump the event loop enough ticks for the fast sections to settle.
3. Assert metadata (``#detail-metadata``) already shows the usecase
   name while the ``Loading… N/M`` counter still reflects an
   unfinished section.
4. Release the gate and drain — final state should match the
   happy-path rendering.
"""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest

pytest.importorskip("textual")

from textual.widgets import Static  # noqa: E402

from qa_studio_cli.tui.api import TuiApi  # noqa: E402
from qa_studio_cli.tui.app import QAStudioTUIApp  # noqa: E402
from qa_studio_cli.tui.screens.usecase_detail import UsecaseDetailScreen  # noqa: E402


def _make_gated_api(slow_gate: threading.Event) -> MagicMock:
    """API stub with all sections fast except ``list_executions``,
    which blocks until ``slow_gate.set()`` is called on the main thread.
    """

    def slow_list_executions(*_args, **_kwargs):
        # 5s is far longer than the test needs — it's a safety cap
        # so a bug that forgets to set the gate fails fast instead
        # of hanging CI.
        released = slow_gate.wait(timeout=5.0)
        assert released, "gate never released — check test drove the mock correctly"
        return []

    api = MagicMock(spec=TuiApi)
    api.list_usecases.return_value = []
    api.get_usecase.return_value = {
        "name": "ProgressiveRender",
        "starting_url": "https://example.com/",
        "test_platform": "web",
    }
    api.get_steps.return_value = []
    api.get_variables.return_value = {}
    api.get_headers.return_value = {}
    api.get_secrets.return_value = []
    api.list_executions.side_effect = slow_list_executions
    return api


class TestProgressiveRender:
    def test_metadata_renders_before_executions_resolve(self):
        """Fast sections must paint while a slow section is still pending."""

        slow_gate = threading.Event()

        async def _run():
            api = _make_gated_api(slow_gate)
            app = QAStudioTUIApp(tui_api=api)
            try:
                async with app.run_test() as pilot:
                    # Let the initial usecases-list screen settle, then
                    # push the detail screen that we actually want to
                    # observe.
                    await pilot.pause()
                    app.push_screen(UsecaseDetailScreen(usecase_id="u-1"))
                    # A handful of pumps is enough for the fast
                    # ``asyncio.to_thread`` sections to complete and for
                    # their render callbacks to apply — the slow
                    # section is still blocked on ``slow_gate``.
                    for _ in range(4):
                        await pilot.pause()

                    screen = app.screen
                    assert isinstance(screen, UsecaseDetailScreen)

                    # Metadata is the section that matters most to the
                    # user — assert it's visible before the slow call
                    # finishes. This is the core progressive-render
                    # guarantee.
                    metadata_text = str(
                        screen.query_one("#detail-metadata", Static).renderable
                    )
                    assert "ProgressiveRender" in metadata_text, (
                        "metadata should render while executions is still pending"
                    )

                    # The status widget should reflect that loading is
                    # not yet complete. The exact count depends on how
                    # many fast sections have drained; we just insist
                    # at least one is still pending.
                    status_text = str(
                        screen.query_one("#detail-status", Static).renderable
                    )
                    assert "Loading" in status_text, (
                        "status should still show a loading counter while "
                        "the slow section is gated"
                    )
                    # ``Loading… N/6`` where N < 6 — we check the shape
                    # rather than a specific N so scheduling jitter
                    # doesn't cause flakes.
                    assert "/6" in status_text

                    # Release the slow call and drain. Once everything
                    # finishes the status should clear (success path
                    # in ``_load_detail``).
                    slow_gate.set()
                    for _ in range(4):
                        await pilot.pause()

                    final_status = str(
                        screen.query_one("#detail-status", Static).renderable
                    )
                    assert final_status == "", (
                        "status should be cleared once every section resolved"
                    )
            finally:
                # Belt-and-braces: make sure we never leave the gated
                # worker hanging even if an assertion failed above.
                slow_gate.set()

        asyncio.run(_run())
