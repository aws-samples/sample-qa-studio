"""Smoke tests for ``python -m qa_studio_cli`` entry point.

The TUI's subprocess runner spawns ``python -m qa_studio_cli run …``
so the package must be runnable as a module (i.e. expose a
``__main__.py``). A regression would surface as "No module named
qa_studio_cli.__main__" inside the Live Tail — these tests guard
against that.
"""

import subprocess
import sys


class TestPythonMInvocation:
    def test_help_returns_zero_and_shows_usage(self):
        """``python -m qa_studio_cli --help`` exits 0 and mentions 'tui'."""
        result = subprocess.run(
            [sys.executable, "-m", "qa_studio_cli", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        # Click emits the usage banner + subcommand list; `tui` is one
        # of them (registered in cli.py).
        assert "tui" in result.stdout
        assert "run" in result.stdout

    def test_run_without_args_fails_loudly(self):
        """Invoking ``run`` without --usecase-id / --suite-id should
        return a non-zero exit — confirms the argv reaches Click and
        the command runs, even if invalid."""
        result = subprocess.run(
            [sys.executable, "-m", "qa_studio_cli", "run"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        # Error message includes Click's UsageError text.
        assert "Either --suite-id or --usecase-id" in (
            result.stdout + result.stderr
        )
