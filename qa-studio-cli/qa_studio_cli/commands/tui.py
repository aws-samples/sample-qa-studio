"""``qa-studio tui`` — launch the interactive terminal UI.

Click-level entry point. Responsible for gating on the two
preconditions before starting Textual:

1. ``[tui]`` extras installed — shows a pip-install hint otherwise.
2. Valid token — shows a ``qa-studio login`` hint otherwise.

Both checks live here (not inside the Textual app) so the user sees
the error in their shell, not inside a half-started TUI. See
``.kiro/specs/cli-tui/`` for requirements and design rationale.
"""

import functools

import click

from qa_studio_cli.auth.token_manager import get_valid_token
from qa_studio_cli.config.manager import config_exists
from qa_studio_cli.models.errors import AuthError


def _require_config(fn):
    """Mirror of ``cli.require_config`` — imported separately so this
    module has no dependency on the root CLI assembly."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not config_exists():
            click.echo(
                "Configuration not found. Run 'qa-studio configure' first.",
                err=True,
            )
            raise SystemExit(1)
        return fn(*args, **kwargs)
    return wrapper


@click.command()
@_require_config
def tui() -> None:
    """Interactive terminal UI. Local-only execution.

    For CI/CD and scripted use, keep using the existing subcommands
    (``qa-studio run``, ``qa-studio tests``, ``qa-studio suites``).
    """
    # Gate 1 — optional extra.
    try:
        from qa_studio_cli.tui.app import QAStudioTUIApp
    except ImportError as exc:
        click.echo(
            "Textual dependencies not installed. "
            "Run: pip install qa-studio[tui]",
            err=True,
        )
        # Surface the underlying error in debug contexts without
        # pretending the command succeeded.
        click.echo(f"(cause: {exc})", err=True)
        raise SystemExit(1)

    # Gate 2 — authentication. We reject before starting Textual so
    # the user sees the hint in their shell, not in a flash-of-TUI.
    try:
        get_valid_token()
    except AuthError as exc:
        click.echo(f"Authentication required: {exc.message}", err=True)
        click.echo("Run: qa-studio login", err=True)
        raise SystemExit(1)

    QAStudioTUIApp().run()
