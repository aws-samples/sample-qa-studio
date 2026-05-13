"""Run-parameters form for a test suite.

Simpler than :class:`RunFormScreen` (for a single usecase) because a
suite doesn't declare its own variables — the overrides it applies
are suite-wide and are just passed through to every member use case
by the runner. No header / secret overrides on this form either;
those live with individual use cases and would add 0600-tempfile
plumbing that doesn't pay off for the suite path.

Submit writes no tempfiles, builds the argv, and pushes
``LiveTailScreen``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Input, Label, Static, TextArea

from qa_studio_cli.tui.app_header import TAB_SUITES, AppHeader
from qa_studio_cli.tui.override_writer import OverrideFiles
from qa_studio_cli.tui.subprocess_runner import RunnerProcess, build_argv


def parse_variables_textarea(text: str) -> Tuple[Dict[str, str], List[str]]:
    """Parse a multi-line ``KEY=VALUE`` textarea into a dict.

    Returns ``(variables, errors)``. Empty lines and pure-whitespace
    lines are skipped. A line without ``=`` or with an empty key is
    reported in ``errors``; the caller surfaces that as a notification
    rather than submitting a half-parsed overrides map.
    """
    variables: Dict[str, str] = {}
    errors: List[str] = []

    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if "=" not in line:
            errors.append(f"Line {i}: missing '=' — {line!r}")
            continue
        key, _, value = line.partition("=")
        if not key.strip():
            errors.append(f"Line {i}: empty key — {line!r}")
            continue
        variables[key.strip()] = value
    return variables, errors


class SuiteRunFormScreen(Screen):
    """Parametrisation form for a local suite run."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Cancel", show=True),
        Binding("ctrl+s", "submit", "Run", show=True),
    ]

    TITLE = "Run suite"

    def __init__(self, suite_id: str, suite: Dict[str, Any]):
        super().__init__()
        self._suite_id = suite_id
        self._suite_name = suite.get("name") or suite_id
        self._total_usecases = int(suite.get("total_usecases") or 0)

    def compose(self) -> ComposeResult:
        yield AppHeader(active=TAB_SUITES)
        yield Static(
            f"Parameters for [b]{self._suite_name}[/]  "
            f"([dim]ID: {self._suite_id} · {self._total_usecases} use case(s)[/])",
            id="suite-run-title",
            markup=True,
        )
        yield Static(
            "[dim]Overrides are applied to every use case in the suite. "
            "Press Ctrl+S to run, Esc to cancel.[/]",
            id="suite-run-hint",
            markup=True,
        )
        with VerticalScroll(id="suite-run-scroll"):
            with Vertical(id="suite-run-fields"):
                with Horizontal(classes="form-row"):
                    yield Label("Base URL", classes="form-label")
                    yield Input(
                        value="",
                        placeholder="https://staging.example.com (optional)",
                        id="suite-input-base-url",
                    )
                with Horizontal(classes="form-row"):
                    yield Label("Region", classes="form-label")
                    yield Input(
                        value="",
                        placeholder="(leave blank to use each use case's region)",
                        id="suite-input-region",
                    )
                with Horizontal(classes="form-row"):
                    yield Label("Model ID", classes="form-label")
                    yield Input(
                        value="",
                        placeholder="(leave blank to use each use case's model)",
                        id="suite-input-model-id",
                    )
                with Horizontal(classes="form-row"):
                    yield Label("Timeout (s)", classes="form-label")
                    yield Input(
                        value="3600", id="suite-input-timeout"
                    )
                yield Label(
                    "Variables (one KEY=VALUE per line; blank lines skipped)",
                    id="suite-variables-label",
                )
                yield TextArea(
                    text="",
                    id="suite-input-variables",
                )
                yield Checkbox(
                    "Local only (no remote execution record)",
                    value=True,
                    id="suite-local-only-toggle",
                )
                yield Checkbox(
                    "Verbose logging (DEBUG)",
                    value=False,
                    id="suite-verbose-toggle",
                )
        with Horizontal(id="suite-run-actions"):
            yield Button("Cancel", id="suite-cancel-button")
            yield Button("Run", id="suite-submit-button", variant="primary")
        yield Footer()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "suite-submit-button":
            self.action_submit()
        elif event.button.id == "suite-cancel-button":
            self.app.pop_screen()

    def action_submit(self) -> None:
        # Parse + validate the variables textarea first so the user
        # fixes the typo rather than discovering it from a subprocess
        # error a few seconds later.
        variables, errors = parse_variables_textarea(
            self.query_one("#suite-input-variables", TextArea).text
        )
        if errors:
            self.app.notify(
                "Invalid variable lines:\n" + "\n".join(errors),
                severity="error",
                timeout=8,
            )
            return

        base_url = self.query_one("#suite-input-base-url", Input).value.strip()
        region = self.query_one("#suite-input-region", Input).value.strip()
        model_id = self.query_one("#suite-input-model-id", Input).value.strip()
        timeout = self.query_one("#suite-input-timeout", Input).value.strip()
        local_only = self.query_one("#suite-local-only-toggle", Checkbox).value
        verbose = self.query_one("#suite-verbose-toggle", Checkbox).value

        extra: List[str] = []
        for name, value in variables.items():
            extra.extend(["--var", f"{name}={value}"])
        if base_url:
            extra.extend(["--base-url", base_url])
        if region:
            extra.extend(["--region", region])
        if model_id:
            extra.extend(["--model-id", model_id])
        # Only pass --timeout when the user changed it from the
        # default — keeps the live-tail command line tidy.
        if timeout and timeout != "3600":
            extra.extend(["--timeout", timeout])

        argv = build_argv(
            suite_id=self._suite_id,
            extra_flags=extra,
            local_only=local_only,
            verbose=verbose,
            output_format="human",
        )
        proc = RunnerProcess(argv=argv, override_files=OverrideFiles())

        from qa_studio_cli.tui.screens.live_tail import LiveTailScreen

        self.app.push_screen(LiveTailScreen(proc))
