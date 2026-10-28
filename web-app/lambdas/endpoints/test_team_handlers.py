"""Tests for team CRUD handlers (list, get, update, delete)."""
import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Ensure the handlers directory is importable
sys.path.insert(0, os.path.dirname(__file__))


def _make_event(method='GET', path='/teams', body=None, path_params=None, authorizer=None):
    """Create a mock API Gateway proxy event."""
    event = {
        'httpMethod': method,
        'resource': path,
        'body': json.dumps(body) if body else None,
        'pathParameters': path_params or {},
        'requestContext': {
            'authorizer': authorizer or {
                'sub': 'admin-sub',
                'email': 'admin@example.com',
                'identityType': 'user',
                'scope': 'api/admin api/applications.read',
                'isAdmin': 'true',
                'teamRoles': '[]',
            }
        },
    }
    return event


def _non_admin_event(team_id='team-1', team_role='team_lead', body=None, path_params=None):
    """Create event for a non-admin team-lead user."""
    event = _make_event(body=body, path_params=path_params)
    event['requestContext']['authorizer'] = {
        'sub': 'user-sub',
        'email': 'user@example.com',
        'identityType': 'user',
        'scope': 'api/applications.read',
        'isAdmin': 'false',
        'teamRoles': json.dumps([{'team_id': team_id, 'role': team_role}]),
    }
    return event


# ======================================================================
# list_teams tests
# ======================================================================

class TestListTeams:
    @patch('permissions_repo.list_team_apps')
    @patch('permissions_repo.list_team_members')
    @patch('permissions_repo.list_teams')
    def test_happy_path(self, mock_list_teams, mock_list_members, mock_list_apps):
        from handlers.list_teams import handle

        mock_list_teams.return_value = [
            {'id': 'team-1', 'name': 'Alpha'},
            {'id': 'team-2', 'name': 'Beta'},
        ]
        mock_list_members.return_value = [{'user_sub': 'u1'}]
        mock_list_apps.return_value = [{'id': 'app-1'}]

        event = _make_event()
        response = handle(event)
        body = json.loads(response['body'])

        assert response['statusCode'] == 200
        assert len(body) == 2
        assert body[0]['memberCount'] == 1
        assert body[0]['applicationCount'] == 1

    @patch('permissions_repo.list_teams')
    def test_team_lead_gets_minimal_list(self, mock_list):
        from handlers.list_teams import handle

        mock_list.return_value = [
            {'id': 'team-1', 'name': 'Alpha'},
            {'id': 'team-2', 'name': 'Beta'},
        ]
        event = _non_admin_event(team_role='team_lead')
        response = handle(event)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body) == 2
        assert body[0] == {'id': 'team-1', 'name': 'Alpha'}
        # Minimal payload — no member/app counts leaked
        assert 'memberCount' not in body[0]

    def test_non_privileged_user_gets_403(self):
        from handlers.list_teams import handle

        event = _non_admin_event(team_role='viewer')
        response = handle(event)

        assert response['statusCode'] == 403


# ======================================================================
# get_team tests
# ======================================================================

class TestGetTeam:
    @patch('permissions_repo.list_team_apps')
    @patch('permissions_repo.list_team_members')
    @patch('permissions_repo.get_team')
    def test_admin_can_get_any_team(self, mock_get, mock_members, mock_apps):
        from handlers.get_team import handle

        mock_get.return_value = {'id': 'team-1', 'name': 'Alpha', 'created_by': 's1', 'created_at': 't1'}
        mock_members.return_value = []
        mock_apps.return_value = []

        event = _make_event(path_params={'id': 'team-1'})
        response = handle(event)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['name'] == 'Alpha'

    @patch('permissions_repo.list_team_apps')
    @patch('permissions_repo.list_team_members')
    @patch('permissions_repo.get_team')
    def test_member_can_get_own_team(self, mock_get, mock_members, mock_apps):
        from handlers.get_team import handle

        mock_get.return_value = {'id': 'team-1', 'name': 'Alpha', 'created_by': 's1', 'created_at': 't1'}
        mock_members.return_value = []
        mock_apps.return_value = []

        event = _non_admin_event(team_id='team-1', team_role='editor', path_params={'id': 'team-1'})
        response = handle(event)

        assert response['statusCode'] == 200

    def test_non_member_gets_403(self):
        from handlers.get_team import handle

        event = _non_admin_event(team_id='team-other', team_role='editor', path_params={'id': 'team-1'})
        response = handle(event)

        assert response['statusCode'] == 403

    @patch('permissions_repo.get_team')
    def test_team_not_found_returns_404(self, mock_get):
        from handlers.get_team import handle

        mock_get.return_value = None
        event = _make_event(path_params={'id': 'nonexistent'})
        response = handle(event)

        assert response['statusCode'] == 404


# ======================================================================
# update_team tests
# ======================================================================

class TestUpdateTeam:
    @patch('permissions_repo.update_team')
    @patch('permissions_repo.get_team')
    @patch('permissions_repo.team_name_exists')
    def test_happy_path(self, mock_exists, mock_get, mock_update):
        from handlers.update_team import handle

        mock_exists.return_value = False
        mock_get.return_value = {'id': 'team-1', 'name': 'Old'}
        mock_update.return_value = {
            'id': 'team-1', 'name': 'New', 'description': '',
            'created_by': 's', 'created_at': 't',
        }

        event = _make_event(body={'name': 'New'}, path_params={'id': 'team-1'})
        response = handle(event)

        assert response['statusCode'] == 200
        assert json.loads(response['body'])['name'] == 'New'

    def test_non_admin_gets_403(self):
        from handlers.update_team import handle

        event = _non_admin_event(body={'name': 'X'}, path_params={'id': 'team-1'})
        response = handle(event)

        assert response['statusCode'] == 403

    def test_empty_body_returns_400(self):
        from handlers.update_team import handle

        event = _make_event(body={}, path_params={'id': 'team-1'})
        response = handle(event)

        assert response['statusCode'] == 400

    @patch('permissions_repo.get_team')
    @patch('permissions_repo.team_name_exists')
    def test_duplicate_name_returns_400(self, mock_exists, mock_get):
        from handlers.update_team import handle

        mock_exists.return_value = True
        mock_get.return_value = {'id': 'team-1', 'name': 'OtherTeam'}

        event = _make_event(body={'name': 'Duplicate'}, path_params={'id': 'team-1'})
        response = handle(event)

        assert response['statusCode'] == 400


# ======================================================================
# delete_team tests
# ======================================================================

class TestDeleteTeam:
    @patch('handlers.delete_team.log_permission_change')
    @patch('cognito_sync.delete_team_groups')
    @patch('permissions_repo.delete_team')
    @patch('permissions_repo.list_team_members')
    @patch('permissions_repo.get_team')
    def test_happy_path_small_team(self, mock_get, mock_members, mock_delete,
                                    mock_cognito, mock_audit):
        from handlers.delete_team import handle

        mock_get.return_value = {'id': 'team-1', 'name': 'Alpha'}
        mock_members.return_value = [{'user_sub': f'u{i}'} for i in range(3)]
        mock_delete.return_value = {'deleted_members_count': 3, 'orphaned_apps_count': 1}

        event = _make_event(path_params={'id': 'team-1'})
        os.environ['USER_POOL_ID'] = 'pool-123'
        response = handle(event)

        assert response['statusCode'] == 204
        assert response['body'] == ''
        details = mock_audit.call_args.kwargs['details']
        assert details['deleted_members_count'] == 3
        assert details['orphaned_apps_count'] == 1

    @patch('permissions_repo.list_team_members')
    @patch('permissions_repo.get_team')
    def test_bulk_confirm_required_for_large_team(self, mock_get, mock_members):
        from handlers.delete_team import handle

        mock_get.return_value = {'id': 'team-1', 'name': 'Big'}
        mock_members.return_value = [{'user_sub': f'u{i}'} for i in range(10)]

        event = _make_event(path_params={'id': 'team-1'})
        response = handle(event)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'confirm' in body['error']

    @patch('perm_audit.log_permission_change')
    @patch('cognito_sync.delete_team_groups')
    @patch('permissions_repo.delete_team')
    @patch('permissions_repo.list_team_members')
    @patch('permissions_repo.get_team')
    def test_bulk_confirm_provided_succeeds(self, mock_get, mock_members, mock_delete,
                                              mock_cognito, mock_audit):
        from handlers.delete_team import handle

        mock_get.return_value = {'id': 'team-1', 'name': 'Big'}
        mock_members.return_value = [{'user_sub': f'u{i}'} for i in range(10)]
        mock_delete.return_value = {'deleted_members_count': 10, 'orphaned_apps_count': 0}

        event = _make_event(body={'confirm': True}, path_params={'id': 'team-1'})
        os.environ['USER_POOL_ID'] = 'pool-123'
        response = handle(event)

        assert response['statusCode'] == 204

    @patch('permissions_repo.get_team')
    def test_team_not_found(self, mock_get):
        from handlers.delete_team import handle

        mock_get.return_value = None
        event = _make_event(path_params={'id': 'nonexistent'})
        response = handle(event)

        assert response['statusCode'] == 404
