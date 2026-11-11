"""``qa-studio tests insert-template <usecase-id> --template-id … [--position N] [--secret K=V]``."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from qa_studio_cli.cli import cli
from qa_studio_cli.models.errors import ApiError

TEMPLATE_ID = "3f1c0000-0000-4000-8000-000000000001"
USECASE_ID = "7a7a0000-0000-4000-8000-000000000009"
STEPS = [
    {"id": "s1", "sort": 1, "step_type": "browser", "instruction": "Open login", "browser_action": "navigate"},
    {"id": "s2", "sort": 2, "step_type": "secret", "instruction": "Click into the username field.",
     "secret_key": "shop_username"},
    {"id": "s3", "sort": 3, "step_type": "secret", "instruction": "Click into the password field.",
     "secret_key": "shop_password"},
]


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.get.side_effect = lambda path, params=None: {"steps": STEPS}
    client.post.side_effect = lambda path, json_body=None, params=None: (
        {"message": "Template imported successfully", "steps_created": 3,
         "missingSecrets": ["shop_username", "shop_password"]}
        if path.endswith("/import-template") else {"success": True}
    )
    return client


def _invoke(runner, mock_client, args):
    with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
         patch("qa_studio_cli.api.client.load_config") as mock_config, \
         patch("qa_studio_cli.api.client.get_valid_token", return_value="fake-token"), \
         patch("qa_studio_cli.api.client.ApiClient", return_value=mock_client):
        mock_config.return_value = MagicMock(api_url="https://fake-api.example.com")
        return runner.invoke(cli, ["tests", "insert-template", *args])


def _posts(mock_client):
    return [(c.args[0], c.kwargs.get("json_body")) for c in mock_client.post.call_args_list]


class TestHappyPath:
    def test_append_without_position(self, runner, mock_client):
        result = _invoke(runner, mock_client, [USECASE_ID, "--template-id", TEMPLATE_ID])
        assert result.exit_code == 0, result.output
        assert f"✓ Inserted 3 step(s) from template {TEMPLATE_ID} at position end" in result.output
        assert "⚠ Missing secrets (set in UI or pass --secret): shop_username, shop_password" in result.output
        assert _posts(mock_client) == [
            (f"/usecase/{USECASE_ID}/import-template", {"template_id": TEMPLATE_ID, "insert_position": -1}),
        ]

    def test_position_and_secrets(self, runner, mock_client):
        result = _invoke(runner, mock_client, [
            USECASE_ID, "--template-id", TEMPLATE_ID, "--position", "2",
            "--secret", "shop_username=qa-user", "--secret", "shop_password=hunter2",
        ])
        assert result.exit_code == 0, result.output
        assert "at position 2" in result.output
        assert "Missing secrets" not in result.output
        assert "hunter2" not in result.output and "qa-user" not in result.output
        assert _posts(mock_client) == [
            (f"/usecase/{USECASE_ID}/import-template", {"template_id": TEMPLATE_ID, "insert_position": 2}),
            (f"/usecase/{USECASE_ID}/secrets", {"secrets": [{"key": "shop_username", "value": "qa-user"}]}),
            (f"/usecase/{USECASE_ID}/secrets", {"secrets": [{"key": "shop_password", "value": "hunter2"}]}),
        ]

    def test_partial_secrets_reports_remaining(self, runner, mock_client):
        result = _invoke(runner, mock_client, [
            USECASE_ID, "--template-id", TEMPLATE_ID, "--secret", "shop_username=qa-user",
        ])
        assert result.exit_code == 0, result.output
        assert "⚠ Missing secrets (set in UI or pass --secret): shop_password" in result.output

    def test_json_output(self, runner, mock_client):
        result = _invoke(runner, mock_client, [
            USECASE_ID, "--template-id", TEMPLATE_ID, "--position", "1",
            "--secret", "shop_username=qa-user", "--format", "json",
        ])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == {
            "usecaseId": USECASE_ID, "templateId": TEMPLATE_ID, "position": 1, "stepsCreated": 3,
            "secretsSet": ["shop_username"], "missingSecrets": ["shop_password"],
        }
        assert "qa-user" not in result.output

    def test_no_missing_secrets_in_response(self, runner, mock_client):
        mock_client.post.side_effect = lambda path, json_body=None, params=None: {"steps_created": 1}
        mock_client.get.side_effect = lambda path, params=None: {"steps": STEPS[:1]}
        result = _invoke(runner, mock_client, [USECASE_ID, "--template-id", TEMPLATE_ID])
        assert result.exit_code == 0, result.output
        assert "Missing secrets" not in result.output


class TestUsageErrors:
    @pytest.mark.parametrize("position", ["0", "-1", "abc"])
    def test_invalid_position_is_exit_2(self, runner, mock_client, position):
        result = _invoke(runner, mock_client, [USECASE_ID, "--template-id", TEMPLATE_ID, "--position", position])
        assert result.exit_code == 2
        mock_client.post.assert_not_called()

    def test_missing_template_id_is_exit_2(self, runner, mock_client):
        result = _invoke(runner, mock_client, [USECASE_ID])
        assert result.exit_code == 2

    def test_unknown_secret_key_is_exit_2_before_insert(self, runner, mock_client):
        result = _invoke(runner, mock_client, [
            USECASE_ID, "--template-id", TEMPLATE_ID, "--secret", "nope=x",
        ])
        assert result.exit_code == 2
        assert "nope" in result.output
        assert "shop_username, shop_password" in result.output
        mock_client.post.assert_not_called()

    def test_malformed_secret_is_exit_2(self, runner, mock_client):
        result = _invoke(runner, mock_client, [USECASE_ID, "--template-id", TEMPLATE_ID, "--secret", "novalue"])
        assert result.exit_code == 2
        mock_client.post.assert_not_called()


class TestApiErrors:
    def test_template_not_found(self, runner, mock_client):
        mock_client.get.side_effect = ApiError(404, "Resource not found.")
        result = _invoke(runner, mock_client, [USECASE_ID, "--template-id", TEMPLATE_ID])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
        mock_client.post.assert_not_called()

    def test_out_of_range_position_from_server(self, runner, mock_client):
        mock_client.post.side_effect = ApiError(400, "insert_position must be between 1 and 3 (or -1 to append)")
        result = _invoke(runner, mock_client, [USECASE_ID, "--template-id", TEMPLATE_ID, "--position", "9"])
        assert result.exit_code == 1
        assert "insert_position must be between 1 and 3" in result.output

    def test_forbidden(self, runner, mock_client):
        mock_client.post.side_effect = ApiError(403, "Insufficient permissions.")
        result = _invoke(runner, mock_client, [USECASE_ID, "--template-id", TEMPLATE_ID])
        assert result.exit_code == 1
        assert "Insufficient permissions" in result.output

    def test_failed_secret_set_is_reported_and_exit_1(self, runner, mock_client):
        def post(path, json_body=None, params=None):
            if path.endswith("/secrets"):
                raise ApiError(500, "boom")
            return {"steps_created": 3, "missingSecrets": ["shop_username", "shop_password"]}
        mock_client.post.side_effect = post
        result = _invoke(runner, mock_client, [
            USECASE_ID, "--template-id", TEMPLATE_ID, "--secret", "shop_username=qa-user",
        ])
        assert result.exit_code == 1
        assert "shop_username" in result.output
        assert "qa-user" not in result.output
