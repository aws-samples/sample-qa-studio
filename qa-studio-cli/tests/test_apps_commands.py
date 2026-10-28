"""Tests for the apps command group."""

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


def invoke_apps(runner, mock_client, args):
    """Helper to invoke apps subcommands with auth mocked out."""
    with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
         patch("qa_studio_cli.api.client.load_config") as mock_config, \
         patch("qa_studio_cli.api.client.get_valid_token", return_value="fake-token"), \
         patch("qa_studio_cli.api.client.ApiClient", return_value=mock_client):
        mock_config.return_value = MagicMock(api_url="https://fake-api.example.com")
        return runner.invoke(cli, args)


class TestAppsReassign:
    """Tests for 'qa-studio apps reassign'."""

    def test_apps_reassign_success(self, runner, mock_client):
        """Reassigning an application returns success message."""
        mock_client.post.return_value = {}

        result = invoke_apps(runner, mock_client, [
            "apps", "reassign", "--app", "app-xyz", "--to-team", "team-2", "--yes"
        ])

        assert result.exit_code == 0
        assert "app-xyz reassigned to team team-2" in result.output
        mock_client.post.assert_called_once_with(
            "/applications/app-xyz/reassign", json_body={"target_team_id": "team-2"}
        )

    def test_apps_reassign_403_non_admin(self, runner, mock_client):
        """Reassigning without admin permission shows 403 error."""
        mock_client.post.side_effect = ApiError(403, "Insufficient permissions. Only admins can reassign applications.")

        result = invoke_apps(runner, mock_client, [
            "apps", "reassign", "--app", "app-xyz", "--to-team", "team-2", "--yes"
        ])

        assert result.exit_code == 1
        assert "403" in result.output or "permission" in result.output.lower()

    def test_apps_reassign_not_found(self, runner, mock_client):
        """Reassigning a nonexistent application shows 404 error."""
        mock_client.post.side_effect = ApiError(404, "Resource not found.")

        result = invoke_apps(runner, mock_client, [
            "apps", "reassign", "--app", "nonexistent", "--to-team", "team-2", "--yes"
        ])

        assert result.exit_code == 1
        assert "404" in result.output or "not found" in result.output.lower()
