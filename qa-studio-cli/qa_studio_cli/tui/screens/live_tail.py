"""Live-tail screen for an in-flight run.

Owns a single :class:`RunnerProcess`, drives it in an async worker,
and appends every stdout/stderr line to a ``RichLog`` as it arrives.
When the child exits, shows the final status and keeps the screen
open so the user can read the log before pressing Esc to go back.

Esc is intercepted while a run is still in progress — the user must
press ``k`` (or Ctrl+C) to terminate first, mirroring the
"don't lose the run by accident" contract from the spec.
"""

from __future__ import annotations

from typing import Optional

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, RichLog, Static

from qa_studio_cli.tui.app_header import TAB_USECASES, AppHeader
from qa_studio_cli.tui.subprocess_runner import RunnerProcess, RunResult


class LiveTailScreen(Screen):
    """Screen that runs a :class:`RunnerProcess` and tails its output."""

    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("k", "terminate", "Terminate", show=True),
        Binding("ctrl+c", "terminate", "Terminate", show=False),
    ]

    TITLE = "Run in progress"

    def __init__(self, runner: RunnerProcess):
        super().__init__()
        self._runner = runner
        self._done = False
        self._result: Optional[RunResult] = None

    def compose(self) -> ComposeResult:
        yield AppHeader(active=TAB_USECASES)
        yield Static("Starting…", id="livetail-status", markup=True)
        yield Static("", id="livetail-command", markup=False)
        yield RichLog(
            id="livetail-log",
            highlight=False,
            markup=False,
            wrap=True,
            max_lines=10000,
        )
        yield Footer()

    def on_mount(self) -> None:
        # Show the exact argv — paths only; the file *contents* never
        # appear here (R-SEC-1 in the spec).
        command_label: Static = self.query_one("#livetail-command", Static)
        command_label.update(" ".join(self._runner.argv))
        self._pump()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def action_terminate(self) -> None:
        if self._done:
            return
        self.query_one("#livetail-status", Static).update(
            "[yellow]Terminating…[/]"
        )
        await self._runner.terminate()

    async def action_back(self) -> None:
        if not self._done:
            self.app.bell()
            self.app.notify(
                "Run still in progress — press k to terminate first.",
                severity="warning",
                timeout=3,
            )
            return
        self.app.pop_screen()

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    @work(exclusive=True)
    async def _pump(self) -> None:
        log: RichLog = self.query_one("#livetail-log", RichLog)
        status: Static = self.query_one("#livetail-status", Static)

        status.update("[cyan]Running…[/]")
        try:
            await self._runner.start()
        except Exception as exc:  # noqa: BLE001
            status.update(f"[red]Failed to start:[/] {exc}")
            self._done = True
            await self._runner.aclose()
            return

        try:
            async for stream, line in self._runner.stream():
                text = Text()
                if stream == "stderr":
                    text.append("[stderr] ", style="red")
                text.append(line)
                log.write(text)
            self._result = await self._runner.wait()
        finally:
            await self._runner.aclose()

        self._done = True
        self._render_final_status()

    def _render_final_status(self) -> None:
        result = self._result
        status: Static = self.query_one("#livetail-status", Static)
        if result is None:
            status.update("[red]Run ended with no result.[/]")
            return
        duration = f"({result.duration_seconds:.1f}s)"
        if result.exit_code == 0:
            status.update(f"[green]✓ PASSED[/] {duration}  [dim]Esc to go back[/]")
        else:
            status.update(
                f"[red]✗ FAILED[/] (exit {result.exit_code}) {duration}  "
                "[dim]Esc to go back[/]"
            )
