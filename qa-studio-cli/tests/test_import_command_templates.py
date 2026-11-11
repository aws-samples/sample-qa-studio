"""``qa-studio tests import`` with template placeholder steps.

The CLI validates that every referenced template exists and prompts for the
template's secrets; the expansion itself happens in ``POST /import``.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from qa_studio_cli.cli import cli
from qa_studio_cli.models.errors import ApiError

LOGIN_ID = "3f1c0000-0000-4000-8000-000000000001"
MISSING_ID = "3f1c0000-0000-4000-8000-00000000dead"
LOGIN_STEPS = [
    {"id": "s1", "sort": 1, "step_type": "browser", "instruction": "Open login"},
    {"id": "s2", "sort": 2, "step_type": "secret", "instruction": "user", "secret_key": "shop_username"},
    {"id": "s3", "sort": 3, "step_type": "secret", "instruction": "pw", "secret_key": "shop_password"},
]


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    client = MagicMock()

    def get(path, params=None):
        if path == f"/templates/{LOGIN_ID}":
            return {"id": LOGIN_ID, "name": "Login – Shop"}
        if path == f"/templates/{LOGIN_ID}/steps":
            return {"steps": LOGIN_STEPS}
        raise ApiError(404, "Resource not found.")

    def post(path, json_body=None, params=None):
        if path == "/import":
            return {"success": True, "usecaseId": "uc-new", "message": "ok",
                    "missingSecrets": ["shop_username", "shop_password"],
                    "templatesApplied": [{"templateId": LOGIN_ID, "version": 3, "stepsCreated": 3}]}
        if path.endswith("/secrets"):
            return {"success": True}
        raise AssertionError(path)

    client.get.side_effect = get
    client.post.side_effect = post
    return client


def _write(tmp_path: Path, name="checkout", steps=None, secrets=()):
    steps = steps or [
        {"sort": 1, "step_type": "template", "template_id": LOGIN_ID},
        {"sort": 2, "step_type": "navigation", "instruction": "Click 'Add to cart'."},
    ]
    payload = {
        "exportVersion": "1.0", "exportedAt": "2025-01-01T00:00:00Z",
        "usecase": {"name": name, "starting_url": "https://e.test"},
        "steps": steps, "secrets": list(secrets),
    }
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(payload))
    return path


APP_ID = "app-1"


def _invoke(runner, mock_client, args, input_text=None):
    """`args` is the argv tail after `tests import`; every import belongs to an application."""
    with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
         patch("qa_studio_cli.api.client.load_config") as mock_config, \
         patch("qa_studio_cli.api.client.get_valid_token", return_value="fake-token"), \
         patch("qa_studio_cli.api.client.ApiClient", return_value=mock_client):
        mock_config.return_value = MagicMock(api_url="https://fake-api.example.com")
        return runner.invoke(cli, ["tests", "import", *args, "--application-id", APP_ID], input=input_text)


def _secret_posts(mock_client):
    return [(c.args[0], c.kwargs["json_body"]) for c in mock_client.post.call_args_list if c.args[0].endswith("/secrets")]


class TestDryRun:
    def test_lists_template_and_its_secrets(self, runner, mock_client, tmp_path):
        path = _write(tmp_path)
        result = _invoke(runner, mock_client, [str(path), "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "Login – Shop" in result.output
        assert "shop_username" in result.output and "shop_password" in result.output
        mock_client.post.assert_not_called()

    def test_json(self, runner, mock_client, tmp_path):
        path = _write(tmp_path)
        result = _invoke(runner, mock_client, [str(path), "--dry-run", "--format", "json"])
        assert result.exit_code == 0, result.output
        file_entry = json.loads(result.output)["validation"]["files"][0]
        assert file_entry["templates"] == [{"id": LOGIN_ID, "name": "Login – Shop"}]
        assert file_entry["secretKeys"] == ["shop_username", "shop_password"]
        assert file_entry["secretsCount"] == 2

    def test_unknown_template_is_invalid(self, runner, mock_client, tmp_path):
        path = _write(tmp_path, steps=[{"sort": 1, "step_type": "template", "template_id": MISSING_ID},
                                       {"sort": 2, "step_type": "navigation", "instruction": "x"}])
        result = _invoke(runner, mock_client, [str(path), "--dry-run"])
        assert result.exit_code == 1
        assert f"step 1: template {MISSING_ID} not found" in result.output
        assert "qa-studio templates list" in result.output
        mock_client.post.assert_not_called()


class TestImport:
    def test_unknown_template_blocks_import(self, runner, mock_client, tmp_path):
        path = _write(tmp_path, steps=[{"sort": 1, "step_type": "template", "template_id": MISSING_ID},
                                       {"sort": 2, "step_type": "navigation", "instruction": "x"}])
        result = _invoke(runner, mock_client, [str(path), "-y"])
        assert result.exit_code == 1
        assert "No valid files to import" in result.output
        mock_client.post.assert_not_called()

    def test_template_secrets_via_secret_flag(self, runner, mock_client, tmp_path):
        path = _write(tmp_path)
        result = _invoke(runner, mock_client, [
            str(path), "--non-interactive", "--secret", "shop_username=qa-user", "--secret", "shop_password=hunter2",
        ])
        assert result.exit_code == 0, result.output
        import_body = next(c.kwargs["json_body"] for c in mock_client.post.call_args_list if c.args[0] == "/import")
        # the CLI does not expand: the placeholder is sent as-is
        assert import_body["steps"][0] == {"sort": 1, "step_type": "template", "template_id": LOGIN_ID}
        assert import_body["secrets"] == []
        assert _secret_posts(mock_client) == [
            ("/usecase/uc-new/secrets", {"secrets": [{"key": "shop_username", "value": "qa-user"}]}),
            ("/usecase/uc-new/secrets", {"secrets": [{"key": "shop_password", "value": "hunter2"}]}),
        ]
        assert "hunter2" not in result.output

    def test_non_interactive_fails_on_missing_template_secret(self, runner, mock_client, tmp_path):
        path = _write(tmp_path)
        result = _invoke(runner, mock_client, [str(path), "--non-interactive", "--secret", "shop_username=qa-user"])
        assert result.exit_code == 2
        assert "shop_password" in result.output
        mock_client.post.assert_not_called()

    def test_interactive_prompts_for_template_secrets(self, runner, mock_client, tmp_path):
        path = _write(tmp_path)
        result = _invoke(runner, mock_client, [str(path), "-y"], input_text="qa-user\nhunter2\n")
        assert result.exit_code == 0, result.output
        assert "shop_username" in result.output and "Login – Shop" in result.output
        assert [b["secrets"][0]["key"] for _, b in _secret_posts(mock_client)] == ["shop_username", "shop_password"]

    def test_skip_secrets_reports_template_secrets(self, runner, mock_client, tmp_path):
        path = _write(tmp_path)
        result = _invoke(runner, mock_client, [str(path), "-y", "--skip-secrets"])
        assert result.exit_code == 0, result.output
        assert "shop_username, shop_password" in result.output
        assert _secret_posts(mock_client) == []

    def test_file_secret_and_template_secret_deduped(self, runner, mock_client, tmp_path):
        path = _write(tmp_path, secrets=[{"key": "shop_password", "description": "Shop password"}])
        result = _invoke(runner, mock_client, [
            str(path), "--non-interactive", "--secret", "shop_username=u", "--secret", "shop_password=p",
        ])
        assert result.exit_code == 0, result.output
        assert len(_secret_posts(mock_client)) == 2

    def test_plain_file_makes_no_template_calls(self, runner, mock_client, tmp_path):
        path = _write(tmp_path, steps=[{"sort": 1, "step_type": "navigation", "instruction": "x"}])
        result = _invoke(runner, mock_client, [str(path), "-y"])
        assert result.exit_code == 0, result.output
        mock_client.get.assert_not_called()
