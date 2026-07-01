"""Tests for the `qa-studio run` command (Task 6)."""

import sys
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from qa_studio_cli.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


def _mock_runner_and_logger():
    """Create mock modules for runner.main and utils.logger."""
    mock_runner = MagicMock()
    mock_runner.run_usecase = MagicMock(side_effect=SystemExit(0))
    mock_runner.run_runner = MagicMock(side_effect=SystemExit(0))

    mock_logger = MagicMock()
    mock_logger.setup_logging = MagicMock()

    return mock_runner, mock_logger


@pytest.fixture
def mock_modules():
    """Patch sys.modules so lazy imports resolve to mocks."""
    mock_runner, mock_logger = _mock_runner_and_logger()
    with patch.dict("sys.modules", {
        "qa_studio_cli.runner.main": mock_runner,
        "qa_studio_cli.utils.logger": mock_logger,
    }):
        yield mock_runner, mock_logger


class TestRunCommandValidation:
    """Mutually exclusive options and variable parsing."""

    def test_requires_either_suite_or_usecase(self, runner):
        result = runner.invoke(cli, ["run"])
        assert result.exit_code != 0
        assert "Either --suite-id or --usecase-id is required" in result.output

    def test_rejects_both_suite_and_usecase(self, runner):
        result = runner.invoke(
            cli, ["run", "--suite-id", "s1", "--usecase-id", "u1"]
        )
        assert result.exit_code != 0
        assert "Cannot use both --suite-id and --usecase-id" in result.output

    def test_rejects_malformed_variable(self, runner):
        result = runner.invoke(
            cli, ["run", "--usecase-id", "u1", "--var", "no-equals-sign"]
        )
        assert result.exit_code != 0
        assert "key=value" in result.output

    def test_accepts_valid_variable(self, runner, mock_modules):
        """Variable parsing should split on first '=' only."""
        mock_runner, _ = mock_modules
        result = runner.invoke(
            cli, ["run", "--usecase-id", "u1", "--var", "key=val=ue"],
        )
        mock_runner.run_usecase.assert_called_once()
        assert mock_runner.run_usecase.call_args[1]["variables"] == {"key": "val=ue"}

    def test_accepts_multiple_variables(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        result = runner.invoke(
            cli, ["run", "--usecase-id", "u1", "--var", "a=1", "--var", "b=2"],
        )
        mock_runner.run_usecase.assert_called_once()
        assert mock_runner.run_usecase.call_args[1]["variables"] == {"a": "1", "b": "2"}


class TestRunCommandMissingDeps:
    """Lazy import gate shows install instructions when runner deps missing."""

    def test_shows_install_instructions_on_import_error(self, runner):
        with patch.dict("sys.modules", {"qa_studio_cli.runner.main": None}):
            result = runner.invoke(cli, ["run", "--usecase-id", "u1"])
            assert "Runner dependencies not installed" in result.output
            assert "pip install qa-studio[runner]" in result.output


class TestRunCommandDispatch:
    """Verify correct delegation to run_usecase vs run_runner."""

    def test_dispatches_to_run_usecase(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        result = runner.invoke(
            cli,
            [
                "run", "--usecase-id", "uc-123",
                "--local-only", "--verbose",
                "--base-url", "http://localhost:3000",
                "--region", "eu-west-1",
                "--model-id", "nova-act-v2.0",
                "--timeout", "1800",
                "--format", "human",
            ],
        )
        mock_runner.run_usecase.assert_called_once()
        kw = mock_runner.run_usecase.call_args[1]
        assert kw["usecase_id"] == "uc-123"
        assert kw["local_only"] is True
        assert kw["base_url"] == "http://localhost:3000"
        assert kw["region"] == "eu-west-1"
        assert kw["model_id"] == "nova-act-v2.0"
        assert kw["timeout"] == 1800
        assert kw["output_format"] == "human"

    def test_dispatches_to_run_runner(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        result = runner.invoke(
            cli,
            [
                "run", "--suite-id", "suite-456",
                "--keep-artifacts",
                "--token-file", "/tmp/token.json",
            ],
        )
        mock_runner.run_runner.assert_called_once()
        kw = mock_runner.run_runner.call_args[1]
        assert kw["suite_id"] == "suite-456"
        assert kw["keep_artifacts"] is True
        assert kw["token_file"] == "/tmp/token.json"
        assert kw["local_only"] is False

    def test_default_format_is_json(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        runner.invoke(cli, ["run", "--usecase-id", "u1"])
        assert mock_runner.run_usecase.call_args[1]["output_format"] == "json"

    def test_default_timeout_is_3600(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        runner.invoke(cli, ["run", "--usecase-id", "u1"])
        assert mock_runner.run_usecase.call_args[1]["timeout"] == 3600

    def test_token_file_passed_to_usecase(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        runner.invoke(
            cli, ["run", "--usecase-id", "u1", "--token-file", "/tmp/t.json"],
        )
        assert mock_runner.run_usecase.call_args[1]["token_file"] == "/tmp/t.json"

    def test_verbose_triggers_setup_logging(self, runner, mock_modules):
        _, mock_logger = mock_modules
        runner.invoke(cli, ["run", "--usecase-id", "u1", "--verbose"])
        mock_logger.setup_logging.assert_called_once_with(True)

    def test_non_verbose_passes_false(self, runner, mock_modules):
        _, mock_logger = mock_modules
        runner.invoke(cli, ["run", "--usecase-id", "u1"])
        mock_logger.setup_logging.assert_called_once_with(False)


class TestRunCommandFormatChoice:
    """--format only accepts json or human."""

    def test_rejects_invalid_format(self, runner):
        result = runner.invoke(
            cli, ["run", "--usecase-id", "u1", "--format", "xml"]
        )
        assert result.exit_code != 0

    def test_accepts_json_format(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        runner.invoke(cli, ["run", "--usecase-id", "u1", "--format", "json"])
        mock_runner.run_usecase.assert_called_once()

    def test_accepts_human_format(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        runner.invoke(cli, ["run", "--usecase-id", "u1", "--format", "human"])
        mock_runner.run_usecase.assert_called_once()


class TestBrowserFlagValidation:
    """--browser / --cdp-endpoint-url / --cdp-headers-file validation."""

    def test_browser_defaults_to_local(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        result = runner.invoke(cli, ["run", "--usecase-id", "u1"])
        assert result.exit_code == 0
        mock_runner.run_usecase.assert_called_once()

    def test_browser_invalid_choice_rejected(self, runner):
        result = runner.invoke(
            cli, ["run", "--usecase-id", "u1", "--browser", "firefox"]
        )
        assert result.exit_code != 0
        # click produces its own "invalid choice" error
        assert "Invalid value" in result.output or "invalid choice" in result.output.lower()

    def test_cdp_external_requires_endpoint_url(self, runner):
        result = runner.invoke(
            cli, ["run", "--usecase-id", "u1", "--browser", "cdp-external"]
        )
        assert result.exit_code != 0
        assert "--cdp-endpoint-url is required" in result.output

    def test_cdp_flags_without_browser_choice_rejected(self, runner):
        result = runner.invoke(
            cli,
            [
                "run",
                "--usecase-id",
                "u1",
                "--cdp-endpoint-url",
                "wss://x.test/",
            ],
        )
        assert result.exit_code != 0
        assert "require --browser=cdp-external" in result.output

    def test_cdp_external_with_endpoint_passes_through(self, runner, mock_modules):
        # T2.6 unblocked --browser=cdp-external — the flag now flows through
        # to run_usecase, which constructs an ExecutionEngine with a matching
        # BrowserSelection.  Here we just assert the dispatch happens cleanly.
        mock_runner, _ = mock_modules
        result = runner.invoke(
            cli,
            [
                "run",
                "--usecase-id", "u1",
                "--browser", "cdp-external",
                "--cdp-endpoint-url", "wss://x.test/",
            ],
        )
        assert result.exit_code == 0
        mock_runner.run_usecase.assert_called_once()
        _, kwargs = mock_runner.run_usecase.call_args
        assert kwargs["browser"] == "cdp-external"
        assert kwargs["cdp_endpoint_url"] == "wss://x.test/"

    def test_agentcore_passes_through(self, runner, mock_modules):
        # T2.6 unblocked --browser=agentcore.  It goes through to
        # run_usecase; the engine constructs the AgentCoreBrowserProvisioner
        # only when the remote path actually provisions a browser.
        mock_runner, _ = mock_modules
        result = runner.invoke(
            cli, ["run", "--usecase-id", "u1", "--browser", "agentcore"],
        )
        assert result.exit_code == 0
        mock_runner.run_usecase.assert_called_once()
        _, kwargs = mock_runner.run_usecase.call_args
        assert kwargs["browser"] == "agentcore"


class TestExecutionIdFlag:
    """--execution-id validation + pass-through to run_usecase."""

    def test_execution_id_requires_usecase_id(self, runner):
        result = runner.invoke(
            cli, ["run", "--suite-id", "s1", "--execution-id", "exec-1"]
        )
        assert result.exit_code != 0
        # Either of the two UsageErrors is acceptable — the point is the
        # combination is rejected before reaching the runner.
        assert (
            "--execution-id is not supported with --suite-id" in result.output
            or "--execution-id requires --usecase-id" in result.output
        )

    def test_execution_id_alone_is_rejected(self, runner):
        result = runner.invoke(cli, ["run", "--execution-id", "exec-1"])
        assert result.exit_code != 0

    def test_execution_id_passes_through_to_run_usecase(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        result = runner.invoke(
            cli,
            [
                "run",
                "--usecase-id", "u1",
                "--execution-id", "exec-42",
            ],
        )
        assert result.exit_code == 0
        mock_runner.run_usecase.assert_called_once()
        _, kwargs = mock_runner.run_usecase.call_args
        assert kwargs["execution_id"] == "exec-42"

    def test_no_execution_id_passes_none(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        result = runner.invoke(cli, ["run", "--usecase-id", "u1"])
        assert result.exit_code == 0
        _, kwargs = mock_runner.run_usecase.call_args
        assert kwargs["execution_id"] is None
