"""Tests for qa-studio tests create command."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from qa_studio_cli.cli import cli
from qa_studio_cli.models.errors import ApiError


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    return MagicMock()


def invoke_create(runner, mock_client, extra_args=None):
    """Helper to invoke create command with auth mocked out."""
    args = [
        "tests", "create", "--from-journey",
        "--title", "Test Login",
        "--url", "https://example.com",
        "--journey", "Navigate to login page, enter credentials, click Sign In, verify dashboard",
        "--region", "us-east-1",
    ]
    if extra_args:
        args.extend(extra_args)

    with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
         patch("qa_studio_cli.api.client.load_config") as mock_config, \
         patch("qa_studio_cli.api.client.get_valid_token", return_value="fake-token"), \
         patch("qa_studio_cli.api.client.ApiClient", return_value=mock_client):
        mock_config.return_value = MagicMock(api_url="https://fake-api.example.com")
        return runner.invoke(cli, args)


class TestTestsCreate:
    """Tests for 'qa-studio tests create' command."""

    def test_create_without_export(self, runner, mock_client):
        """Test creating a test without --export-to."""
        mock_client.post.side_effect = [
            {"success": True, "message": "Generated", "usecaseData": json.dumps({"name": "Test Login", "steps": []})},
            {"success": True, "message": "Imported", "usecase_id": "test-123"},
        ]

        result = invoke_create(runner, mock_client)

        if result.exit_code != 0:
            print(f"Output: {result.output}")
            print(f"Exception: {result.exception}")
        assert result.exit_code == 0
        assert "Test created: Test Login" in result.output
        assert "Test JSON exported to:" not in result.output

    def test_create_with_export(self, runner, mock_client):
        """Test creating a test with --export-to exports JSON."""
        mock_client.post.side_effect = [
            {"success": True, "message": "Generated", "usecaseData": json.dumps({"title": "Test Login", "steps": []})},
            {"success": True, "message": "Imported", "usecase_id": "test-123"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = invoke_create(runner, mock_client, ["--export-to", tmpdir])

            assert result.exit_code == 0
            expected_file = os.path.join(tmpdir, "Test_Login.json")
            assert os.path.exists(expected_file)
            with open(expected_file, 'r') as f:
                data = json.load(f)
            assert isinstance(data, dict)
            assert "Test JSON exported to:" in result.output

    def test_create_export_creates_nested_directory(self, runner, mock_client):
        """Test that --export-to creates nested directories."""
        mock_client.post.side_effect = [
            {"success": True, "message": "Generated", "usecaseData": json.dumps({"name": "Test Login", "steps": []})},
            {"success": True, "message": "Imported", "usecase_id": "test-123"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = os.path.join(tmpdir, "nested", "export")
            result = invoke_create(runner, mock_client, ["--export-to", export_dir])

            assert result.exit_code == 0
            assert os.path.exists(export_dir)
            assert os.path.exists(os.path.join(export_dir, "Test_Login.json"))

    def test_create_generation_failure(self, runner, mock_client):
        """Test handling of generation failure."""
        mock_client.post.return_value = {"success": False, "message": "Bedrock error"}

        result = invoke_create(runner, mock_client)

        assert result.exit_code == 1
        assert "Generation failed" in result.output

    def test_create_api_error(self, runner, mock_client):
        """Test handling of API error."""
        mock_client.post.side_effect = ApiError(400, "Bad request")

        result = invoke_create(runner, mock_client)

        assert result.exit_code == 1

    def test_create_sends_correct_payload(self, runner, mock_client):
        """Test that the correct payload is sent to the API."""
        mock_client.post.side_effect = [
            {"success": True, "message": "Generated", "usecaseData": json.dumps({"steps": []})},
            {"success": True, "message": "Imported", "usecase_id": "test-123"},
        ]

        invoke_create(runner, mock_client)

        # Verify generate-usecase call
        gen_call = mock_client.post.call_args_list[0]
        assert gen_call[0][0] == "/api/generate-usecase"
        body = gen_call[1]["json_body"]
        assert body["title"] == "Test Login"
        assert body["startingUrl"] == "https://example.com"
        assert "Navigate to login page" in body["userJourney"]
        assert body["region"] == "us-east-1"
