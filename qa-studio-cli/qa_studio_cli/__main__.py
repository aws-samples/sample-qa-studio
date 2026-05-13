"""Entry point for ``python -m qa_studio_cli``.

Mirrors what the ``qa-studio`` console script does, just reached by a
different invocation. The TUI's subprocess runner spawns the CLI via
``python -m qa_studio_cli run …`` — using the same Python interpreter
as the TUI — so we don't rely on the ``qa-studio`` entry point being
on PATH.
"""

from qa_studio_cli.cli import cli


if __name__ == "__main__":
    cli()
