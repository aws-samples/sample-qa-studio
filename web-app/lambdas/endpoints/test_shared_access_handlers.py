"""Tests for shared access handlers (grant, revoke, list)."""
import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))


def _admin_event(body=None, path_params=None):
    """Create admin event."""
    return {
        'httpMethod': 'POST',
        'resource': '/teams/{id}/shared-access',
        'body': json.dumps(body) if body else None,
        'pathParameters': path_params or {},
        'requestContext': {
            'authorizer': {
                'sub': 'admin-sub',
                'email': 'admin@example.com',
                'identityType': 'user',
                'scope': 'api/admin',
                'isAdmin': 'true',
                'teamRoles': '[]',
            }
        },
    }


def _team_lead_event(team_id='team-1', body=None, path_params=None):
    """Create team-lead event."""
    return {
        'httpMethod': 'POST',
        'resource': '/teams/{id}/shared-access',
        'body': json.dumps(body) if body else None,
        'pathParameters': path_params or {},
        'requestContext': {
            'authorizer': {
                'sub': 'lead-sub',
                'email': 'lead@example.com',
                'identityType': 'user',
                'scope': 'api/applications.read',
                'isAdmin': 'false',
                'teamRoles': json.dumps([{'team_id': team_id, 'role': 'team_lead'}]),
            }
        },
    }


# ======================================================================
# grant_shared_access tests
# ======================================================================

class TestGrantSharedAccess:
    @patch('perm_audit.log_permission_change')
    @patch('permissions_repo.grant_shared_access')
    @patch('permissions_repo.get_app_owner')
    @patch('permissions_repo.get_team')
    def test_admin_happy_path(self, mock_get_team, mock_get_owner, mock_grant, mock_audit):
        from handlers.grant_shared_access import handle

        # get_team is called twice: once for owner, once for target
        mock_get_team.side_effect = [
            {'id': 'team-1', 'name': 'Owner'},
            {'id': 'team-2', 'name': 'Target'},
        ]
        mock_get_owner.return_value = 'team-1'
        mock_grant.return_value = {
            'grant_id': 'g1', 'owner_team_id': 'team-1',
            'target_team_id': 'team-2', 'app_id': 'app-1',
            'level': 'view', 'granted_at': 'now',
        }

        event = _admin_event(
            body={'targetTeamId': 'team-2', 'appId': 'app-1', 'level': 'view'},
            path_params={'id': 'team-1'},
        )
        response = handle(event)

        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert body['grantId'] == 'g1'
        assert body['targetTeamName'] == 'Target'

    @patch('permissions_repo.get_app_owner')
    @patch('permissions_repo.get_team')
    def test_owner_equals_target_returns_400(self, mock_get_team, mock_get_owner):
        from handlers.grant_shared_access import handle

        mock_get_team.side_effect = [
            {'id': 'team-1', 'name': 'Owner'},
            {'id': 'team-1', 'name': 'Owner'},
        ]
        mock_get_owner.return_value = 'team-1'

        from permissions_repo import grant_shared_access as _original
        with patch('permissions_repo.grant_shared_access', side_effect=ValueError("Cannot share an application with its own team")):
            event = _admin_event(
                body={'targetTeamId': 'team-1', 'appId': 'app-1', 'level': 'view'},
                path_params={'id': 'team-1'},
            )
            response = handle(event)

        assert response['statusCode'] == 400

    @patch('permissions_repo.get_team')
    def test_missing_fields_returns_400(self, mock_get_team):
        from handlers.grant_shared_access import handle

        mock_get_team.return_value = {'id': 'team-1', 'name': 'T'}
        event = _admin_event(body={'targetTeamId': '', 'appId': '', 'level': ''}, path_params={'id': 'team-1'})
        response = handle(event)

        assert response['statusCode'] == 400

    def test_invalid_level_returns_400(self):
        from handlers.grant_shared_access import handle

        with patch('permissions_repo.get_team', return_value={'id': 'team-1', 'name': 'T'}):
            event = _admin_event(
                body={'targetTeamId': 'team-2', 'appId': 'a1', 'level': 'superadmin'},
                path_params={'id': 'team-1'},
            )
            response = handle(event)

        assert response['statusCode'] == 400


# ======================================================================
# revoke_shared_access tests
# ======================================================================

class TestRevokeSharedAccess:
    @patch('perm_audit.log_permission_change')
    @patch('permissions_repo.revoke_shared_access')
    @patch('permissions_repo.list_shared_access')
    def test_happy_path(self, mock_list, mock_revoke, mock_audit):
        from handlers.revoke_shared_access import handle

        mock_list.return_value = [
            {'grant_id': 'g1', 'target_team_id': 'team-2', 'app_id': 'app-1'},
        ]

        event = _admin_event(path_params={'id': 'team-1', 'grantId': 'g1'})
        response = handle(event)

        assert response['statusCode'] == 204
        mock_revoke.assert_called_once()

    @patch('permissions_repo.list_shared_access')
    def test_grant_not_found_returns_404(self, mock_list):
        from handlers.revoke_shared_access import handle

        mock_list.return_value = []

        event = _admin_event(path_params={'id': 'team-1', 'grantId': 'nonexistent'})
        response = handle(event)

        assert response['statusCode'] == 404


# ======================================================================
# list_shared_access tests
# ======================================================================

class TestListSharedAccess:
    @patch('permissions_repo.get_team')
    @patch('permissions_repo.list_shared_access')
    def test_happy_path(self, mock_list, mock_get_team):
        from handlers.list_shared_access import handle

        # get_team called for: owner team check + each target team for enrichment
        mock_get_team.side_effect = [
            {'id': 'team-1', 'name': 'Owner'},  # team existence check
            {'id': 'team-2', 'name': 'Target'},  # enrichment
        ]
        mock_list.return_value = [
            {'grant_id': 'g1', 'target_team_id': 'team-2', 'app_id': 'app-1',
             'level': 'view', 'granted_at': 'now'},
        ]

        event = _admin_event(path_params={'id': 'team-1'})
        response = handle(event)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body) == 1
        assert body[0]['targetTeamName'] == 'Target'
