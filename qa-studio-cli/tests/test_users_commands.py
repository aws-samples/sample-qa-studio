"""Tests for the users command group."""

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


def invoke_users(runner, mock_client, args):
    """Helper to invoke users subcommands with auth mocked out."""
    with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
         patch("qa_studio_cli.api.client.load_config") as mock_config, \
         patch("qa_studio_cli.api.client.get_valid_token", return_value="fake-token"), \
         patch("qa_studio_cli.api.client.ApiClient", return_value=mock_client):
        mock_config.return_value = MagicMock(api_url="https://fake-api.example.com")
        return runner.invoke(cli, args)


class TestUsersList:
    """Tests for 'qa-studio users list'."""

    def test_users_list_success(self, runner, mock_client):
        """Listing users shows tabular output with team info."""
        mock_client.get.return_value = {
            "users": [
                {
                    "user_id": "user-001",
                    "email": "alice@example.com",
                    "teams": [{"team_id": "team-1", "name": "Alpha", "role": "Admin"}],
                },
                {
                    "user_id": "user-002",
                    "email": "bob@example.com",
                    "teams": [],
                },
            ]
        }

        result = invoke_users(runner, mock_client, ["users", "list"])

        assert result.exit_code == 0
        assert "alice@example.com" in result.output
        assert "bob@example.com" in result.output
        assert "Alpha" in result.output


class TestUsersAssign:
    """Tests for 'qa-studio users assign'."""

    def test_users_assign_success(self, runner, mock_client):
        """Assigning a user to a team returns success message."""
        mock_client.patch.return_value = {}

        result = invoke_users(runner, mock_client, [
            "users", "assign", "--user", "user-001", "--team", "team-2", "--role", "Editor"
        ])

        assert result.exit_code == 0
        assert "user-001 assigned to team team-2" in result.output
        assert "Editor" in result.output
        mock_client.patch.assert_called_once_with(
            "/users/user-001", json_body={"team_id": "team-2", "role": "Editor"}
        )

    def test_users_assign_not_found(self, runner, mock_client):
        """Assigning a nonexistent user shows 404 error."""
        mock_client.patch.side_effect = ApiError(404, "Resource not found.")

        result = invoke_users(runner, mock_client, [
            "users", "assign", "--user", "nonexistent", "--team", "team-2", "--role", "Viewer"
        ])

        assert result.exit_code == 1
        assert "404" in result.output or "not found" in result.output.lower()

    def test_users_assign_403(self, runner, mock_client):
        """Assigning without admin permission shows 403 error."""
        mock_client.patch.side_effect = ApiError(403, "Insufficient permissions.")

        result = invoke_users(runner, mock_client, [
            "users", "assign", "--user", "user-001", "--team", "team-2", "--role", "Editor"
        ])

        assert result.exit_code == 1
        assert "403" in result.output or "permission" in result.output.lower()
