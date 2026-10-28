"""Tests for the create_team handler."""

import json
import os
import pytest
from unittest.mock import patch, MagicMock

os.environ["TABLE_NAME"] = "test-table"
os.environ["USER_POOL_ID"] = "us-east-1_test"


def _build_event(body=None, scopes="api/admin"):
    """Build a minimal API Gateway event."""
    return {
        "httpMethod": "POST",
        "resource": "/teams",
        "pathParameters": {},
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {
            "authorizer": {
                "email": "admin@test.com",
                "identityType": "user",
                "sub": "admin-sub-123",
                "scope": scopes,
            }
        },
    }


class TestCreateTeamHandler:
    """Tests for handlers/create_team.py"""

    @patch("handlers.create_team.cognito_sync")
    @patch("handlers.create_team.permissions_repo")
    def test_creates_team_successfully(self, mock_repo, mock_cognito):
        from handlers.create_team import handle

        mock_repo.team_name_exists.return_value = False
        mock_repo.create_team.return_value = {
            'pk': 'TEAM#uuid-001',
            'sk': 'METADATA',
            'id': 'uuid-001',
            'name': 'New Team',
            'created_by': 'admin-sub-123',
            'created_at': '2026-06-23T00:00:00Z',
        }
        mock_cognito.ensure_team_groups.return_value = []

        event = _build_event(body={"name": "New Team"})
        response = handle(event)

        assert response["statusCode"] == 201
        body = json.loads(response["body"])
        assert body["id"] == "uuid-001"
        assert body["name"] == "New Team"
        mock_repo.create_team.assert_called_once_with("New Team", "admin-sub-123")
        mock_cognito.ensure_team_groups.assert_called_once()

    @patch("handlers.create_team.cognito_sync")
    @patch("handlers.create_team.permissions_repo")
    def test_non_admin_gets_403(self, mock_repo, mock_cognito):
        from handlers.create_team import handle

        event = _build_event(
            body={"name": "Team"},
            scopes="api/usecases.read api/usecases.write",
        )
        response = handle(event)

        assert response["statusCode"] == 403
        mock_repo.create_team.assert_not_called()

    @patch("handlers.create_team.cognito_sync")
    @patch("handlers.create_team.permissions_repo")
    def test_duplicate_name_returns_400(self, mock_repo, mock_cognito):
        from handlers.create_team import handle

        mock_repo.team_name_exists.return_value = True

        event = _build_event(body={"name": "Existing Team"})
        response = handle(event)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "already exists" in body["error"]
        mock_repo.create_team.assert_not_called()

    @patch("handlers.create_team.cognito_sync")
    @patch("handlers.create_team.permissions_repo")
    def test_missing_name_returns_400(self, mock_repo, mock_cognito):
        from handlers.create_team import handle

        event = _build_event(body={})
        response = handle(event)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "name is required" in body["error"]
