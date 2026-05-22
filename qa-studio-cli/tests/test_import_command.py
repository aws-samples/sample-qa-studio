"""Tests for the qa-studio tests import command.

Covers the new --non-interactive and --secret KEY=VALUE flags as well as the
existing --yes / -y flag (which had no test coverage before this change).

The import command interacts with the cloud via two API calls:
    POST /import                        — uploads the validated JSON payload.
    POST /usecase/{id}/secrets          — sets a secret value (one call per
                                          (file, key) pair when secret values
                                          are supplied).

Both are routed through ApiClient.post; the mock_post helper below distinguishes
them by path so each test can assert the expected calls were made.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from qa_studio_cli.cli import cli
from qa_studio_cli.commands.tests import _parse_cli_secrets


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    """Mock ApiClient. Tests configure .post.side_effect per case."""
    return MagicMock()


def _write_test_json(tmp_path: Path, *, with_secrets: bool = True) -> Path:
    """Write a minimal valid test JSON to tmp_path/login.json and return the path.

    When with_secrets=True the JSON declares two secrets (admin_email,
    admin_password) so the secret-collection path is exercised. When False
    the secrets array is empty and no secret prompting / hard-error path
    fires.
    """
    secrets = (
        [
            {"key": "admin_email", "description": "Admin email"},
            {"key": "admin_password", "description": "Admin password"},
        ]
        if with_secrets
        else []
    )
    payload = {
        "exportVersion": "1.0",
        "exportedAt": "2024-01-02T15:00:00Z",
        "usecase": {
            "name": "Login",
            "description": "Login flow.",
            "starting_url": "https://example.com",
            "active": True,
            "executing_region": "us-east-1",
            "tags": [],
        },
        "steps": [
            {"sort": 1, "step_type": "navigation", "instruction": "Click Sign In"},
        ],
        "variables": [],
        "secrets": secrets,
    }
    file_path = tmp_path / "login.json"
    file_path.write_text(json.dumps(payload))
    return file_path


def _make_mock_post(usecase_id: str = "uc-fake-id"):
    """Return a side_effect function that routes by URL path.

    POST /import returns a successful import response.
    POST /usecase/{id}/secrets returns a generic success.
    Anything else raises so unexpected calls surface in test output.
    """
    def post(path, json_body=None, **kwargs):
        if path == "/import":
            return {
                "success": True,
                "message": "Imported",
                "usecase_id": usecase_id,
                "missingSecrets": [],
            }
        if "/secrets" in path:
            return {"success": True}
        raise AssertionError(f"Unexpected client.post path: {path!r}")

    return post


def _invoke_import(runner, mock_client, args):
    """Invoke `qa-studio tests import` with auth + ApiClient mocked out.

    `args` is the argv tail that follows `tests import`, e.g.
    `[str(json_path), "--non-interactive"]`.
    """
    with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
         patch("qa_studio_cli.api.client.load_config") as mock_config, \
         patch("qa_studio_cli.api.client.get_valid_token", return_value="fake-token"), \
         patch("qa_studio_cli.api.client.ApiClient", return_value=mock_client):
        mock_config.return_value = MagicMock(api_url="https://fake-api.example.com")
        return runner.invoke(cli, ["tests", "import", *args])


# ---------------------------------------------------------------------------
# Direct unit tests for _parse_cli_secrets
# ---------------------------------------------------------------------------


class TestParseCliSecrets:
    """Direct tests for the --secret KEY=VALUE parser."""

    def test_parses_single_pair(self):
        assert _parse_cli_secrets(("admin_pwd=hunter2",)) == {"admin_pwd": "hunter2"}

    def test_parses_multiple_pairs(self):
        result = _parse_cli_secrets(("a=1", "b=two", "c=three=four"))
        # Note: c keeps the equals sign in the value (only first '=' splits).
        assert result == {"a": "1", "b": "two", "c": "three=four"}

    def test_empty_input(self):
        assert _parse_cli_secrets(()) == {}

    def test_rejects_missing_equals(self):
        with pytest.raises(click.BadParameter, match="KEY=VALUE form"):
            _parse_cli_secrets(("no_equals_sign",))

    def test_rejects_empty_key(self):
        with pytest.raises(click.BadParameter, match="empty key"):
            _parse_cli_secrets(("=value",))

    def test_rejects_empty_value(self):
        with pytest.raises(click.BadParameter, match="value for 'k' is empty"):
            _parse_cli_secrets(("k=",))

    def test_rejects_duplicate_key(self):
        with pytest.raises(click.BadParameter, match="supplied more than once"):
            _parse_cli_secrets(("k=one", "k=two"))


# ---------------------------------------------------------------------------
# Integration tests for the import command — confirmation flow
# ---------------------------------------------------------------------------


class TestImportConfirmation:
    """Tests for the import confirmation prompt and -y / --non-interactive bypasses."""

    def test_yes_skips_confirmation(self, runner, mock_client, tmp_path):
        """-y bypasses the 'Import N tests?' prompt."""
        json_path = _write_test_json(tmp_path, with_secrets=False)
        mock_client.post.side_effect = _make_mock_post()

        result = _invoke_import(runner, mock_client, [str(json_path), "-y"])

        assert result.exit_code == 0, result.output
        assert "Import 1 test(s)?" not in result.output
        assert "✓ Imported" in result.output

    def test_no_yes_prompts_and_aborts_on_no(self, runner, mock_client, tmp_path):
        """Without -y, the confirmation prompt fires and 'n' aborts the run."""
        json_path = _write_test_json(tmp_path, with_secrets=False)
        mock_client.post.side_effect = _make_mock_post()

        result = _invoke_import(runner, mock_client, [str(json_path)], )
        # Note: above call doesn't pass input; runner.invoke(input=...) is the right way.
        # Re-invoke with explicit "n\n" input.
        with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
             patch("qa_studio_cli.api.client.load_config") as mock_config, \
             patch("qa_studio_cli.api.client.get_valid_token", return_value="fake-token"), \
             patch("qa_studio_cli.api.client.ApiClient", return_value=mock_client):
            mock_config.return_value = MagicMock(api_url="https://fake-api.example.com")
            result = runner.invoke(cli, ["tests", "import", str(json_path)], input="n\n")

        assert result.exit_code == 0, result.output
        assert "Import 1 test(s)?" in result.output
        assert "Aborted." in result.output
        # Crucially, /import was never called
        assert all(call.args[0] != "/import" for call in mock_client.post.call_args_list)

    def test_non_interactive_implies_yes(self, runner, mock_client, tmp_path):
        """--non-interactive bypasses the confirmation without -y."""
        json_path = _write_test_json(tmp_path, with_secrets=False)
        mock_client.post.side_effect = _make_mock_post()

        result = _invoke_import(runner, mock_client, [str(json_path), "--non-interactive"])

        assert result.exit_code == 0, result.output
        assert "Import 1 test(s)?" not in result.output


# ---------------------------------------------------------------------------
# Integration tests — secret-supply flow
# ---------------------------------------------------------------------------


class TestImportSecrets:
    """Tests for the new --secret KEY=VALUE flag and the missing-secrets fail-loud path."""

    def test_non_interactive_missing_secrets_exits_2(self, runner, mock_client, tmp_path):
        """Test JSON declares secrets, --non-interactive set, no values supplied → exit 2."""
        json_path = _write_test_json(tmp_path, with_secrets=True)
        mock_client.post.side_effect = _make_mock_post()

        result = _invoke_import(runner, mock_client, [str(json_path), "--non-interactive"])

        assert result.exit_code == 2, result.output
        assert "missing secret values for" in result.output
        assert "admin_email" in result.output
        assert "admin_password" in result.output
        # /import was never called — we failed before phase 2
        assert mock_client.post.call_count == 0

    def test_non_interactive_supplies_secrets_via_flag(self, runner, mock_client, tmp_path):
        """--non-interactive --secret K=V supplies the value and proceeds."""
        json_path = _write_test_json(tmp_path, with_secrets=True)
        mock_client.post.side_effect = _make_mock_post(usecase_id="uc-123")

        result = _invoke_import(
            runner, mock_client,
            [
                str(json_path),
                "--non-interactive",
                "--secret", "admin_email=admin@dev.local",
                "--secret", "admin_password=devpass123",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "✓ Imported" in result.output

        # Verify both secrets were set via POST /usecase/{id}/secrets
        secret_calls = [
            call for call in mock_client.post.call_args_list
            if "/secrets" in call.args[0]
        ]
        assert len(secret_calls) == 2
        bodies = [call.kwargs["json_body"] for call in secret_calls]
        keys_set = {b["secrets"][0]["key"] for b in bodies}
        values_set = {b["secrets"][0]["value"] for b in bodies}
        assert keys_set == {"admin_email", "admin_password"}
        assert values_set == {"admin@dev.local", "devpass123"}

    def test_non_interactive_skip_secrets_runs_without_setting(self, runner, mock_client, tmp_path):
        """--non-interactive --skip-secrets runs without prompting or setting values."""
        json_path = _write_test_json(tmp_path, with_secrets=True)
        mock_client.post.side_effect = _make_mock_post()

        result = _invoke_import(
            runner, mock_client,
            [str(json_path), "--non-interactive", "--skip-secrets"],
        )

        assert result.exit_code == 0, result.output
        assert "✓ Imported" in result.output
        # /import was called, but no /secrets calls
        secret_calls = [
            call for call in mock_client.post.call_args_list
            if "/secrets" in call.args[0]
        ]
        assert secret_calls == []

    def test_unknown_secret_key_exits_2(self, runner, mock_client, tmp_path):
        """--secret referencing a key no test declares → exit 2 with available-keys list."""
        json_path = _write_test_json(tmp_path, with_secrets=True)

        result = _invoke_import(
            runner, mock_client,
            [str(json_path), "--non-interactive", "--secret", "bogus_key=value"],
        )

        assert result.exit_code == 2, result.output
        assert "unknown key" in result.output
        assert "bogus_key" in result.output
        # The error message should list the available keys for recovery
        assert "admin_email" in result.output
        assert "admin_password" in result.output
        # /import was never called
        assert mock_client.post.call_count == 0

    def test_secret_malformed_argument_rejected(self, runner, mock_client, tmp_path):
        """--secret without an '=' is rejected by the parser (Click BadParameter, exit 2)."""
        json_path = _write_test_json(tmp_path, with_secrets=False)

        result = _invoke_import(
            runner, mock_client,
            [str(json_path), "--non-interactive", "--secret", "no_equals_sign"],
        )

        assert result.exit_code == 2, result.output
        assert "KEY=VALUE form" in result.output
        assert mock_client.post.call_count == 0

    def test_secret_empty_value_rejected(self, runner, mock_client, tmp_path):
        """--secret KEY= (empty value) is rejected with a recovery hint."""
        json_path = _write_test_json(tmp_path, with_secrets=True)

        result = _invoke_import(
            runner, mock_client,
            [str(json_path), "--non-interactive", "--secret", "admin_email="],
        )

        assert result.exit_code == 2, result.output
        assert "is empty" in result.output
        assert "--skip-secrets" in result.output

    def test_secret_duplicate_key_rejected(self, runner, mock_client, tmp_path):
        """The same --secret KEY supplied twice is rejected."""
        json_path = _write_test_json(tmp_path, with_secrets=True)

        result = _invoke_import(
            runner, mock_client,
            [
                str(json_path),
                "--non-interactive",
                "--secret", "admin_email=one",
                "--secret", "admin_email=two",
            ],
        )

        assert result.exit_code == 2, result.output
        assert "supplied more than once" in result.output

    def test_partial_secret_supply_in_interactive_mode_only_prompts_unsupplied(
        self, runner, mock_client, tmp_path,
    ):
        """In interactive mode, --secret K=V suppresses the prompt for K only.

        For a test declaring two secrets, supplying one via --secret should
        prompt only for the other. The test simulates the interactive prompt
        by feeding stdin.
        """
        json_path = _write_test_json(tmp_path, with_secrets=True)
        mock_client.post.side_effect = _make_mock_post()

        # Input: 'y\n' for the import confirmation, then 'pwd-from-stdin\n' for
        # the single remaining secret prompt (admin_password).
        with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
             patch("qa_studio_cli.api.client.load_config") as mock_config, \
             patch("qa_studio_cli.api.client.get_valid_token", return_value="fake-token"), \
             patch("qa_studio_cli.api.client.ApiClient", return_value=mock_client):
            mock_config.return_value = MagicMock(api_url="https://fake-api.example.com")
            result = runner.invoke(
                cli,
                [
                    "tests", "import", str(json_path),
                    "--secret", "admin_email=admin@dev.local",
                ],
                input="y\npwd-from-stdin\n",
            )

        assert result.exit_code == 0, result.output

        # The prompt for admin_email should NOT appear (already supplied).
        # The prompt for admin_password SHOULD appear.
        assert "admin_password" in result.output
        # Both secrets ended up being set via the API
        secret_calls = [
            call for call in mock_client.post.call_args_list
            if "/secrets" in call.args[0]
        ]
        keys_set = {call.kwargs["json_body"]["secrets"][0]["key"] for call in secret_calls}
        values_set = {call.kwargs["json_body"]["secrets"][0]["value"] for call in secret_calls}
        assert keys_set == {"admin_email", "admin_password"}
        assert "admin@dev.local" in values_set
        assert "pwd-from-stdin" in values_set
