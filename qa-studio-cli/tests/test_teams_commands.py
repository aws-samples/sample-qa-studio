"""Tests for the teams command group."""

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


def invoke_teams(runner, mock_client, args):
    """Helper to invoke teams subcommands with auth mocked out."""
    with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
         patch("qa_studio_cli.api.client.load_config") as mock_config, \
         patch("qa_studio_cli.api.client.get_valid_token", return_value="fake-token"), \
         patch("qa_studio_cli.api.client.ApiClient", return_value=mock_client):
        mock_config.return_value = MagicMock(api_url="https://fake-api.example.com")
        return runner.invoke(cli, args)


class TestTeamsCreate:
    """Tests for 'qa-studio teams create'."""

    def test_teams_create_success(self, runner, mock_client):
        """Creating a team returns success message with team ID."""
        mock_client.post.return_value = {
            "id": "team-abc-123",
            "name": "QA Platform",
            "description": "Platform QA team",
            "member_count": 0,
            "application_count": 0,
        }

        result = invoke_teams(runner, mock_client, [
            "teams", "create", "--name", "QA Platform", "--description", "Platform QA team"
        ])

        assert result.exit_code == 0
        assert "Team created: QA Platform" in result.output
        assert "team-abc-123" in result.output
        mock_client.post.assert_called_once_with(
            "/teams", json_body={"name": "QA Platform", "description": "Platform QA team"}
        )

    def test_teams_create_missing_name(self, runner, mock_client):
        """Creating a team without --name fails with usage error."""
        result = invoke_teams(runner, mock_client, ["teams", "create"])

        assert result.exit_code != 0
        assert "Missing option" in result.output or "required" in result.output.lower()


class TestTeamsDelete:
    """Tests for 'qa-studio teams delete'."""

    def test_teams_delete_success(self, runner, mock_client):
        """Deleting a team with --yes skips confirmation."""
        mock_client.delete.return_value = None

        result = invoke_teams(runner, mock_client, [
            "teams", "delete", "--id", "team-abc-123", "--yes"
        ])

        assert result.exit_code == 0
        assert "Team team-abc-123 deleted" in result.output
        mock_client.delete.assert_called_once_with("/teams/team-abc-123")

    def test_teams_delete_not_found(self, runner, mock_client):
        """Deleting a nonexistent team reports the error."""
        mock_client.delete.side_effect = ApiError(404, "Resource not found.")

        result = invoke_teams(runner, mock_client, [
            "teams", "delete", "--id", "nonexistent", "--yes"
        ])

        assert result.exit_code == 1
        assert "404" in result.output or "not found" in result.output.lower()


class TestTeamsList:
    """Tests for 'qa-studio teams list'."""

    def test_teams_list_success(self, runner, mock_client):
        """Listing teams shows tabular output."""
        mock_client.get.return_value = {
            "teams": [
                {"id": "team-1", "name": "Alpha", "member_count": 3, "application_count": 5},
                {"id": "team-2", "name": "Beta", "member_count": 2, "application_count": 1},
            ]
        }

        result = invoke_teams(runner, mock_client, ["teams", "list"])

        assert result.exit_code == 0
        assert "Alpha" in result.output
        assert "Beta" in result.output
        assert "team-1" in result.output
        assert "team-2" in result.output

    def test_teams_list_empty(self, runner, mock_client):
        """Listing teams when none exist shows informative message."""
        mock_client.get.return_value = {"teams": []}

        result = invoke_teams(runner, mock_client, ["teams", "list"])

        assert result.exit_code == 0
        assert "No teams found" in result.output
