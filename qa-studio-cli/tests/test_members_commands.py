"""Tests for the members command group."""

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


def invoke_members(runner, mock_client, args):
    """Helper to invoke members subcommands with auth mocked out."""
    with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
         patch("qa_studio_cli.api.client.load_config") as mock_config, \
         patch("qa_studio_cli.api.client.get_valid_token", return_value="fake-token"), \
         patch("qa_studio_cli.api.client.ApiClient", return_value=mock_client):
        mock_config.return_value = MagicMock(api_url="https://fake-api.example.com")
        return runner.invoke(cli, args)


class TestMembersAdd:
    """Tests for 'qa-studio members add'."""

    def test_members_add_success(self, runner, mock_client):
        """Adding a member returns success message."""
        mock_client.post.return_value = {
            "user_id": "user-001",
            "email": "alice@example.com",
            "role": "Editor",
            "joined_at": "2025-06-20T10:00:00Z",
        }

        result = invoke_members(runner, mock_client, [
            "members", "add", "--team", "team-1", "--email", "alice@example.com", "--role", "Editor"
        ])

        assert result.exit_code == 0
        assert "Added alice@example.com" in result.output
        assert "Editor" in result.output
        mock_client.post.assert_called_once_with(
            "/teams/team-1/members", json_body={"email": "alice@example.com", "role": "Editor"}
        )

    def test_members_add_invalid_role(self, runner, mock_client):
        """Adding a member with an invalid role fails with usage error."""
        result = invoke_members(runner, mock_client, [
            "members", "add", "--team", "team-1", "--email", "alice@example.com", "--role", "SuperUser"
        ])

        assert result.exit_code != 0
        assert "Invalid value" in result.output or "invalid" in result.output.lower()


class TestMembersRemove:
    """Tests for 'qa-studio members remove'."""

    def test_members_remove_success(self, runner, mock_client):
        """Removing a member with --yes skips confirmation."""
        mock_client.delete.return_value = None

        result = invoke_members(runner, mock_client, [
            "members", "remove", "--team", "team-1", "--user", "user-001", "--yes"
        ])

        assert result.exit_code == 0
        assert "user-001 removed" in result.output
        mock_client.delete.assert_called_once_with("/teams/team-1/members/user-001")


class TestMembersSetRole:
    """Tests for 'qa-studio members set-role'."""

    def test_members_set_role_success(self, runner, mock_client):
        """Updating a member role returns success message."""
        mock_client.patch.return_value = {
            "user_id": "user-001",
            "email": "alice@example.com",
            "role": "Admin",
        }

        result = invoke_members(runner, mock_client, [
            "members", "set-role", "--team", "team-1", "--user", "user-001", "--role", "Admin"
        ])

        assert result.exit_code == 0
        assert "Updated alice@example.com" in result.output
        assert "Admin" in result.output
        mock_client.patch.assert_called_once_with(
            "/teams/team-1/members/user-001", json_body={"role": "Admin"}
        )

    def test_members_set_role_403(self, runner, mock_client):
        """Updating a role without permission shows error."""
        mock_client.patch.side_effect = ApiError(403, "Insufficient permissions.")

        result = invoke_members(runner, mock_client, [
            "members", "set-role", "--team", "team-1", "--user", "user-001", "--role", "Admin"
        ])

        assert result.exit_code == 1
        assert "403" in result.output or "permission" in result.output.lower()


class TestMembersList:
    """Tests for 'qa-studio members list'."""

    def test_members_list_success(self, runner, mock_client):
        """Listing members shows tabular output."""
        mock_client.get.return_value = {
            "members": [
                {"user_id": "user-001", "email": "alice@example.com", "role": "Admin"},
                {"user_id": "user-002", "email": "bob@example.com", "role": "Viewer"},
            ]
        }

        result = invoke_members(runner, mock_client, [
            "members", "list", "--team", "team-1"
        ])

        assert result.exit_code == 0
        assert "alice@example.com" in result.output
        assert "bob@example.com" in result.output
        assert "Admin" in result.output
        assert "Viewer" in result.output
