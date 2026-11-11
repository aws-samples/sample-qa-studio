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
        assert kw["usecase_ids"] == ["uc-123"]
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

    def test_default_timeout_is_no_limit(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        runner.invoke(cli, ["run", "--usecase-id", "u1"])
        assert mock_runner.run_usecase.call_args[1]["timeout"] is None

    @pytest.mark.parametrize("value", ["0", "-5"])
    def test_non_positive_timeout_rejected(self, runner, mock_modules, value):
        mock_runner, _ = mock_modules
        result = runner.invoke(cli, ["run", "--usecase-id", "u1", "--timeout", value])
        assert result.exit_code == 2
        assert "Invalid value for '--timeout'" in result.output
        mock_runner.run_usecase.assert_not_called()

    def test_suite_timeout_passed_through(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        runner.invoke(cli, ["run", "--suite-id", "s1", "--timeout", "600"])
        assert mock_runner.run_runner.call_args[1]["timeout"] == 600

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


class TestElectronAppFlags:
    """--app-path is shared with mobile; --app-arg / --app-user-data-dir are
    electron-only and meaningless without an app to launch."""

    def test_app_arg_requires_app_path(self, runner):
        result = runner.invoke(cli, ["run", "--usecase-id", "u1", "--app-arg", "x"])
        assert result.exit_code != 0
        assert "--app-arg" in result.output and "--app-path" in result.output

    def test_app_user_data_dir_requires_app_path(self, runner, tmp_path):
        result = runner.invoke(
            cli, ["run", "--usecase-id", "u1", "--app-user-data-dir", str(tmp_path)],
        )
        assert result.exit_code != 0
        assert "--app-user-data-dir" in result.output and "--app-path" in result.output

    def test_app_flags_pass_through_to_run_usecase(self, runner, mock_modules, tmp_path):
        mock_runner, _ = mock_modules
        result = runner.invoke(
            cli,
            [
                "run", "--usecase-id", "u1",
                "--app-path", "/Apps/Harness.app",
                "--app-arg", "/src/app", "--app-arg", "--flag",
                "--app-user-data-dir", str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        _, kwargs = mock_runner.run_usecase.call_args
        assert kwargs["app_path"] == "/Apps/Harness.app"
        assert kwargs["app_args"] == ["/src/app", "--flag"]
        assert kwargs["app_user_data_dir"] == str(tmp_path)

    def test_app_flags_pass_through_to_run_runner(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        result = runner.invoke(
            cli,
            ["run", "--suite-id", "s1", "--app-path", "/Apps/Harness.app", "--app-arg", "a"],
        )
        assert result.exit_code == 0, result.output
        _, kwargs = mock_runner.run_runner.call_args
        assert kwargs["app_path"] == "/Apps/Harness.app"
        assert kwargs["app_args"] == ["a"]
        assert kwargs["app_user_data_dir"] is None

    def test_defaults_when_absent(self, runner, mock_modules):
        mock_runner, _ = mock_modules
        result = runner.invoke(cli, ["run", "--usecase-id", "u1"])
        assert result.exit_code == 0
        _, kwargs = mock_runner.run_usecase.call_args
        assert kwargs["app_path"] is None
        assert kwargs["app_args"] == []
        assert kwargs["app_user_data_dir"] is None


class TestRunCommandMultipleUsecaseIds:
    """``--usecase-id`` accepts a whitespace-separated list; ``--fail-fast``."""

    def _ids(self, mock_modules):
        return mock_modules[0].run_usecase.call_args[1]["usecase_ids"]

    def test_single_unquoted_id(self, runner, mock_modules):
        runner.invoke(cli, ["run", "--usecase-id", "a"])
        assert self._ids(mock_modules) == ["a"]

    def test_whitespace_separated_ids_are_split(self, runner, mock_modules):
        runner.invoke(cli, ["run", "--usecase-id", " a b\tc\n d  "])
        assert self._ids(mock_modules) == ["a", "b", "c", "d"]

    def test_blank_value_rejected(self, runner):
        result = runner.invoke(cli, ["run", "--usecase-id", "   "])
        assert result.exit_code != 0
        assert "--usecase-id must contain at least one ID" in result.output

    def test_duplicate_ids_rejected(self, runner):
        result = runner.invoke(cli, ["run", "--usecase-id", "a b a"])
        assert result.exit_code != 0
        assert "duplicate" in result.output.lower()
        assert "a" in result.output

    def test_execution_id_with_many_ids_rejected(self, runner):
        result = runner.invoke(
            cli, ["run", "--usecase-id", "a b", "--execution-id", "ex-1"]
        )
        assert result.exit_code != 0
        assert "--execution-id requires exactly one --usecase-id" in result.output

    def test_execution_id_with_single_id_accepted(self, runner, mock_modules):
        result = runner.invoke(
            cli, ["run", "--usecase-id", "a", "--execution-id", "ex-1"]
        )
        assert result.exit_code == 0
        assert mock_modules[0].run_usecase.call_args[1]["execution_id"] == "ex-1"

    def test_fail_fast_default_false(self, runner, mock_modules):
        runner.invoke(cli, ["run", "--usecase-id", "a b"])
        assert mock_modules[0].run_usecase.call_args[1]["fail_fast"] is False

    def test_fail_fast_flag_forwarded(self, runner, mock_modules):
        runner.invoke(cli, ["run", "--usecase-id", "a b", "--fail-fast"])
        assert mock_modules[0].run_usecase.call_args[1]["fail_fast"] is True

    def test_fail_fast_with_suite_rejected(self, runner):
        result = runner.invoke(cli, ["run", "--suite-id", "s1", "--fail-fast"])
        assert result.exit_code != 0
        assert "--fail-fast is only supported with --usecase-id" in result.output

    def test_help_text_mentions_multiple_ids(self, runner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "One or more use case IDs" in result.output
        assert "--fail-fast" in result.output
