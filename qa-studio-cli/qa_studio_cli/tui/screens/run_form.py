"""Run-parameters form screen.

Converts the :class:`FieldSpec` list produced by
:mod:`qa_studio_cli.tui.form_builder` into a scrollable form of
``Input`` widgets, collects the entered values on submit, diffs
against the defaults, writes any override files via
:mod:`qa_studio_cli.tui.override_writer`, builds the CLI argv via
:mod:`qa_studio_cli.tui.subprocess_runner`, and pushes the
:class:`LiveTailScreen` with a ready-to-start process handle.

Nothing on this screen touches the API directly — the pre-fetched
data arrives via the constructor from :class:`UsecaseDetailScreen`.
"""

from __future__ import annotations

from typing import Any, Dict, List

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Input, Label, Select, Static

from qa_studio_cli.runner.browser.local import LOCAL_BROWSER_OPTIONS
from qa_studio_cli.tui.app_header import TAB_USECASES, AppHeader
from qa_studio_cli.tui.form_builder import (
    FieldSpec,
    build_fields,
    compute_overrides,
)
from qa_studio_cli.tui.override_writer import OverrideFiles, write_overrides
from qa_studio_cli.tui.subprocess_runner import RunnerProcess, build_argv


def _input_id(key: str) -> str:
    """Map a FieldSpec key (``"variable:email"``) to a CSS-safe id
    (``"input-variable-email"``)."""
    return "input-" + key.replace(":", "-")


class RunFormScreen(Screen):
    """Parametrisation form for a single local run."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Cancel", show=True),
        Binding("ctrl+s", "submit", "Run", show=True),
    ]

    TITLE = "Run parameters"

    def __init__(
        self,
        usecase_id: str,
        usecase: Dict[str, Any],
        variables: Dict[str, str],
        headers: Dict[str, str],
        secrets: List[Dict[str, Any]],
    ):
        super().__init__()
        self._usecase_id = usecase_id
        self._usecase_name = usecase.get("name") or usecase_id
        self._fields: List[FieldSpec] = build_fields(
            usecase, variables, headers, secrets
        )
        # Populated during compose so submit() can read values.
        self._inputs: Dict[str, Input] = {}

    def compose(self) -> ComposeResult:
        yield AppHeader(active=TAB_USECASES)
        yield Static(
            f"Parameters for [b]{self._usecase_name}[/]  ([dim]ID: {self._usecase_id}[/])",
            id="run-form-title",
            markup=True,
        )
        yield Static(
            "[dim]Leave a secret field empty to use the stored value. "
            "Press Ctrl+S to run, Esc to cancel.[/]",
            id="run-form-hint",
            markup=True,
        )
        with VerticalScroll(id="run-form-scroll"):
            with Vertical(id="run-form-fields"):
                for spec in self._fields:
                    widget = Input(
                        value=spec.default,
                        password=spec.is_secret,
                        id=_input_id(spec.key),
                        placeholder=(
                            "(leave blank to use stored value)"
                            if spec.is_secret
                            else ""
                        ),
                    )
                    self._inputs[spec.key] = widget
                    with Horizontal(classes="form-row"):
                        yield Label(spec.label, classes="form-label")
                        yield widget
                # Browser selector — surfaces the local browser
                # registry so adding entries there auto-populates the
                # form. Only honoured when ``Local only`` is ticked
                # (remote/cloud runs pick the browser elsewhere).
                yield Label(
                    "Browser (local only)",
                    id="browser-select-label",
                )
                yield Select(
                    options=[
                        (option.label, option.key)
                        for option in LOCAL_BROWSER_OPTIONS.values()
                    ],
                    value="chromium",
                    allow_blank=False,
                    id="browser-select",
                )

                # Runner-behaviour toggles.
                #
                # ``local_only`` default True keeps the TUI behaviour
                # unchanged for existing users — untick it to have the
                # cloud backend create a remote execution record that
                # shows up in the web UI's history.  Header / secret
                # overrides require local mode (enforced at the CLI
                # layer) and are validated in ``action_submit``.
                yield Checkbox(
                    "Local only (no remote execution record)",
                    value=True,
                    id="local-only-toggle",
                )
                yield Checkbox(
                    "Show browser window (headful)",
                    value=True,
                    id="headful-toggle",
                )
                yield Checkbox(
                    "Verbose logging (DEBUG)",
                    value=False,
                    id="verbose-toggle",
                )
        with Horizontal(id="run-form-actions"):
            yield Button("Cancel", id="cancel-button")
            yield Button("Run", id="submit-button", variant="primary")
        yield Footer()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit-button":
            self.action_submit()
        elif event.button.id == "cancel-button":
            self.app.pop_screen()

    def action_submit(self) -> None:
        entered = {
            spec.key: self._inputs[spec.key].value for spec in self._fields
        }
        overrides = compute_overrides(self._fields, entered)

        local_only = self.query_one("#local-only-toggle", Checkbox).value
        verbose = self.query_one("#verbose-toggle", Checkbox).value

        # Header / secret overrides are only supported on the local
        # path (enforced at the runner CLI level — see
        # ``runtime-header-secret-overrides`` spec). If the user
        # entered any of those but unticked local-only, reject the
        # submit with a clear message rather than letting the
        # subprocess fail a few seconds in.
        if not local_only and (overrides.headers or overrides.secrets):
            self.app.notify(
                "Header and secret overrides require 'Local only'. "
                "Either clear those fields or tick the box.",
                severity="error",
                timeout=6,
            )
            return

        # Only write the 0600 tempfiles when they'll actually be used.
        if local_only:
            override_files = write_overrides(overrides.headers, overrides.secrets)
        else:
            override_files = OverrideFiles()

        # Build the argv.  Order matches what a user would type by
        # hand — easier to recognise in the live-tail header line.
        extra: List[str] = []
        for name, value in overrides.variables.items():
            extra.extend(["--var", f"{name}={value}"])
        if override_files.headers_path is not None:
            extra.extend(["--headers-file", str(override_files.headers_path)])
        if override_files.secrets_path is not None:
            extra.extend(["--secrets-file", str(override_files.secrets_path)])
        if overrides.base_url:
            extra.extend(["--base-url", overrides.base_url])
        for name, value in overrides.runner_flags.items():
            flag_name = "--" + name.replace("_", "-")
            extra.extend([flag_name, value])

        # Browser selection — only relevant for local-only runs. On
        # remote the cloud worker chooses the browser. We pass the
        # flag only when the user picked something other than the
        # default so the live-tail command stays tidy for the common
        # case.
        browser_key = self.query_one("#browser-select", Select).value
        if (
            local_only
            and isinstance(browser_key, str)
            and browser_key != "chromium"
        ):
            extra.extend(["--local-browser", browser_key])

        # Headful toggle — same local-only gate. The runner's engine
        # otherwise defaults to headless via the HEADLESS env var, so
        # passing --headful when the box is ticked flips that to a
        # visible browser window.
        headful = self.query_one("#headful-toggle", Checkbox).value
        if local_only and headful:
            extra.append("--headful")

        argv = build_argv(
            usecase_id=self._usecase_id,
            extra_flags=extra,
            local_only=local_only,
            verbose=verbose,
            # The live-tail is for humans — pretty output beats a JSON
            # blob at the end of the run. CI / scripted callers still
            # get JSON via ``qa-studio run`` directly.
            output_format="human",
        )
        proc = RunnerProcess(argv=argv, override_files=override_files)

        # Lazy import to avoid a cycle: LiveTail imports RunnerProcess,
        # which this screen already depends on.
        from qa_studio_cli.tui.screens.live_tail import LiveTailScreen

        self.app.push_screen(LiveTailScreen(proc))
