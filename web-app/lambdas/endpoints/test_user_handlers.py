"""Tests for user management handlers (list, create, update, delete)."""
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
        'resource': '/users',
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


def _non_admin_event(body=None, path_params=None):
    """Create non-admin event."""
    return {
        'httpMethod': 'POST',
        'resource': '/users',
        'body': json.dumps(body) if body else None,
        'pathParameters': path_params or {},
        'requestContext': {
            'authorizer': {
                'sub': 'user-sub',
                'email': 'user@example.com',
                'identityType': 'user',
                'scope': 'api/applications.read',
                'isAdmin': 'false',
                'teamRoles': '[]',
            }
        },
    }


# ======================================================================
# list_users tests
# ======================================================================

class TestListUsers:
    @patch('permissions_repo.get_team')
    @patch('permissions_repo.list_user_teams')
    @patch('boto3.client')
    def test_happy_path(self, mock_boto_client, mock_list_teams, mock_get_team):
        from handlers.list_users import handle

        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.list_users.return_value = {
            'Users': [
                {
                    'Username': 'user-sub-1',
                    'Attributes': [{'Name': 'email', 'Value': 'u1@example.com'}],
                },
            ],
        }
        mock_list_teams.return_value = [{'team_id': 'team-1', 'role': 'editor'}]
        mock_get_team.return_value = {'id': 'team-1', 'name': 'Alpha'}

        os.environ['USER_POOL_ID'] = 'pool-123'
        event = _admin_event()
        response = handle(event)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body) == 1
        assert body[0]['email'] == 'u1@example.com'
        assert body[0]['teams'][0]['name'] == 'Alpha'

    @patch('permissions_repo.get_team')
    @patch('permissions_repo.list_user_teams')
    @patch('boto3.client')
    def test_is_admin_only_from_admins_group(self, mock_boto_client, mock_list_teams, mock_get_team):
        from handlers.list_users import handle

        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.list_users.return_value = {'Users': [
            {'Username': 'legacy-team-admin', 'Attributes': []},
            {'Username': 'studio-admin', 'Attributes': []},
        ]}
        groups = {
            'legacy-team-admin': [{'GroupName': 'team-x-admin'}, {'GroupName': 'team-x-team_lead'}],
            'studio-admin': [{'GroupName': 'admins'}],
        }
        mock_cognito.admin_list_groups_for_user.side_effect = (
            lambda UserPoolId, Username: {'Groups': groups[Username]})
        mock_list_teams.return_value = []
        os.environ['USER_POOL_ID'] = 'pool-123'

        response = handle(_admin_event())

        assert response['statusCode'] == 200
        by_id = {u['userId']: u for u in json.loads(response['body'])}
        assert by_id['legacy-team-admin']['isAdmin'] is False
        assert by_id['studio-admin']['isAdmin'] is True

    def test_non_admin_gets_403(self):
        from handlers.list_users import handle

        event = _non_admin_event()
        response = handle(event)

        assert response['statusCode'] == 403


# ======================================================================
# create_user tests
# ======================================================================

class TestCreateUser:
    @patch('perm_audit.log_permission_change')
    @patch('boto3.client')
    def test_happy_path_no_team(self, mock_boto_client, mock_audit):
        from handlers.create_user import handle

        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.admin_create_user.return_value = {
            'User': {
                'Username': 'new-sub',
                'Attributes': [
                    {'Name': 'sub', 'Value': 'new-sub'},
                    {'Name': 'email', 'Value': 'new@example.com'},
                ],
            },
        }

        os.environ['USER_POOL_ID'] = 'pool-123'
        event = _admin_event(body={'email': 'new@example.com'})
        response = handle(event)

        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert body['email'] == 'new@example.com'
        assert body['teams'] == []

    def test_missing_email_returns_400(self):
        from handlers.create_user import handle

        os.environ['USER_POOL_ID'] = 'pool-123'
        event = _admin_event(body={'email': ''})
        response = handle(event)

        assert response['statusCode'] == 400
        assert 'email' in json.loads(response['body'])['error']

    def test_non_admin_gets_403(self):
        from handlers.create_user import handle

        event = _non_admin_event(body={'email': 'x@y.com'})
        response = handle(event)

        assert response['statusCode'] == 403


class TestRoleAssignmentValidation:
    """C-1: 'admin' only ever means the global 'admins' group."""

    @patch('permissions_repo.get_team')
    @patch('boto3.client')
    def test_create_user_invalid_role_returns_400(self, mock_boto_client, mock_get_team):
        from handlers.create_user import handle

        mock_get_team.return_value = {'id': 't1', 'name': 'T'}
        response = handle(_admin_event(body={'email': 'x@example.com', 'teamId': 't1', 'role': 'superadmin'}))

        assert response['statusCode'] == 400
        mock_boto_client.return_value.admin_create_user.assert_not_called()

    @patch('perm_audit.log_permission_change')
    @patch('permissions_repo.add_membership')
    @patch('permissions_repo.get_team')
    @patch('boto3.client')
    def test_create_user_admin_goes_to_admins_group_only(self, mock_boto_client, mock_get_team,
                                                         mock_add, mock_audit):
        from handlers.create_user import handle

        mock_get_team.return_value = {'id': 't1', 'name': 'T'}
        cognito = mock_boto_client.return_value
        cognito.admin_create_user.return_value = {
            'User': {'Username': 'new-sub', 'Attributes': [{'Name': 'sub', 'Value': 'new-sub'}]}}
        os.environ['USER_POOL_ID'] = 'pool-123'

        response = handle(_admin_event(body={'email': 'x@example.com', 'teamId': 't1', 'role': 'admin'}))

        assert response['statusCode'] == 201
        groups = [c.kwargs['GroupName'] for c in cognito.admin_add_user_to_group.call_args_list]
        assert groups == ['admins']
        mock_add.assert_not_called()

    def test_update_user_invalid_role_returns_400(self):
        from handlers.update_user import handle

        response = handle(_admin_event(body={'teamId': 't1', 'role': 'superadmin'},
                                       path_params={'userId': 'u1'}))

        assert response['statusCode'] == 400
        assert 'Invalid role' in json.loads(response['body'])['error']

    @patch('cognito_sync.is_last_studio_admin', return_value=False)
    @patch('perm_audit.log_permission_change')
    @patch('permissions_repo.add_membership')
    @patch('permissions_repo.list_user_teams')
    @patch('permissions_repo.get_team')
    @patch('boto3.client')
    def test_update_user_team_role_uses_team_group(self, mock_boto_client, mock_get_team,
                                                   mock_list_teams, mock_add, mock_audit, mock_last):
        from handlers.update_user import handle

        mock_get_team.return_value = {'id': 't1', 'name': 'T'}
        mock_list_teams.return_value = []
        os.environ['USER_POOL_ID'] = 'pool-123'

        response = handle(_admin_event(body={'teamId': 't1', 'role': 'team_lead'},
                                       path_params={'userId': 'u1'}))

        assert response['statusCode'] == 200
        mock_add.assert_called_once_with('t1', 'u1', 'team_lead')
        groups = [c.kwargs['GroupName'] for c in mock_boto_client.return_value.admin_add_user_to_group.call_args_list]
        assert groups == ['team-t1-team_lead']


# ======================================================================
# delete_user tests
# ======================================================================

class TestDeleteUser:
    @patch('cognito_sync.is_last_studio_admin', return_value=False)
    @patch('perm_audit.log_permission_change')
    @patch('boto3.client')
    @patch('permissions_repo.remove_membership')
    @patch('permissions_repo.list_user_teams')
    def test_happy_path(self, mock_list_teams, mock_remove, mock_boto_client, mock_audit, mock_last):
        from handlers.delete_user import handle

        mock_list_teams.return_value = [{'team_id': 'team-1', 'role': 'editor'}]
        os.environ['USER_POOL_ID'] = 'pool-123'
        event = _admin_event(path_params={'userId': 'user-to-delete'})
        response = handle(event)

        assert response['statusCode'] == 204
        mock_last.assert_called_once_with('user-to-delete', 'pool-123')
        mock_remove.assert_called_once_with('user-to-delete', 'team-1')

    @patch('boto3.client')
    @patch('permissions_repo.list_user_teams')
    @patch('cognito_sync.is_last_studio_admin', return_value=True)
    def test_last_admin_guard(self, mock_last, mock_list_teams, mock_boto_client):
        from handlers.delete_user import handle

        os.environ['USER_POOL_ID'] = 'pool-123'
        event = _admin_event(path_params={'userId': 'last-admin'})
        response = handle(event)

        assert response['statusCode'] == 409
        mock_boto_client.return_value.admin_delete_user.assert_not_called()
        mock_list_teams.assert_not_called()

    @patch('boto3.client')
    @patch('cognito_sync.is_last_studio_admin', side_effect=RuntimeError('cognito down'))
    def test_guard_failure_fails_closed(self, mock_last, mock_boto_client):
        from handlers.delete_user import handle

        os.environ['USER_POOL_ID'] = 'pool-123'
        response = handle(_admin_event(path_params={'userId': 'u1'}))

        assert response['statusCode'] == 500
        mock_boto_client.return_value.admin_delete_user.assert_not_called()

    def test_non_admin_gets_403(self):
        from handlers.delete_user import handle

        event = _non_admin_event(path_params={'userId': 'u1'})
        response = handle(event)

        assert response['statusCode'] == 403


# ======================================================================
# Last-admin guard on the global 'admins' group (N-9)
# ======================================================================

class TestUpdateUserLastAdminGuard:
    @patch('permissions_repo.add_membership')
    @patch('permissions_repo.list_user_teams')
    @patch('permissions_repo.get_team')
    @patch('boto3.client')
    def test_demoting_sole_admin_returns_409(self, mock_boto_client, mock_get_team,
                                            mock_list_teams, mock_add):
        from handlers.update_user import handle

        mock_get_team.return_value = {'id': 't1', 'name': 'T'}
        cognito = mock_boto_client.return_value
        cognito.admin_list_groups_for_user.return_value = {'Groups': [{'GroupName': 'admins'}]}
        cognito.list_users_in_group.return_value = {'Users': [{'Username': 'sole-admin'}]}
        os.environ['USER_POOL_ID'] = 'pool-123'

        response = handle(_admin_event(body={'teamId': 't1', 'role': 'editor'},
                                       path_params={'userId': 'sole-admin'}))

        assert response['statusCode'] == 409
        cognito.list_users_in_group.assert_called_once_with(UserPoolId='pool-123', GroupName='admins')
        cognito.admin_remove_user_from_group.assert_not_called()
        mock_add.assert_not_called()

    @patch('perm_audit.log_permission_change')
    @patch('permissions_repo.add_membership')
    @patch('permissions_repo.list_user_teams')
    @patch('permissions_repo.get_team')
    @patch('boto3.client')
    def test_demoting_one_of_two_admins_succeeds(self, mock_boto_client, mock_get_team,
                                                 mock_list_teams, mock_add, mock_audit):
        from handlers.update_user import handle

        mock_get_team.return_value = {'id': 't1', 'name': 'T'}
        mock_list_teams.return_value = []
        cognito = mock_boto_client.return_value
        cognito.admin_list_groups_for_user.return_value = {'Groups': [{'GroupName': 'admins'}]}
        cognito.list_users_in_group.return_value = {'Users': [{'Username': 'a1'}, {'Username': 'a2'}]}
        os.environ['USER_POOL_ID'] = 'pool-123'

        response = handle(_admin_event(body={'teamId': 't1', 'role': 'editor'},
                                       path_params={'userId': 'a1'}))

        assert response['statusCode'] == 200
        cognito.admin_remove_user_from_group.assert_any_call(
            UserPoolId='pool-123', Username='a1', GroupName='admins')
        mock_add.assert_called_once_with('t1', 'a1', 'editor')

    @patch('perm_audit.log_permission_change')
    @patch('permissions_repo.add_membership')
    @patch('permissions_repo.list_user_teams')
    @patch('permissions_repo.get_team')
    @patch('boto3.client')
    def test_non_admin_user_is_not_counted(self, mock_boto_client, mock_get_team,
                                           mock_list_teams, mock_add, mock_audit):
        from handlers.update_user import handle

        mock_get_team.return_value = {'id': 't1', 'name': 'T'}
        mock_list_teams.return_value = []
        cognito = mock_boto_client.return_value
        cognito.admin_list_groups_for_user.return_value = {'Groups': [{'GroupName': 'team-t1-viewer'}]}
        os.environ['USER_POOL_ID'] = 'pool-123'

        response = handle(_admin_event(body={'teamId': 't1', 'role': 'editor'},
                                       path_params={'userId': 'u1'}))

        assert response['statusCode'] == 200
        cognito.list_users_in_group.assert_not_called()

    @patch('permissions_repo.add_membership')
    @patch('permissions_repo.get_team')
    @patch('cognito_sync.is_last_studio_admin', side_effect=RuntimeError('cognito down'))
    def test_guard_failure_fails_closed(self, mock_last, mock_get_team, mock_add):
        from handlers.update_user import handle

        mock_get_team.return_value = {'id': 't1', 'name': 'T'}
        os.environ['USER_POOL_ID'] = 'pool-123'

        response = handle(_admin_event(body={'teamId': 't1', 'role': 'editor'},
                                       path_params={'userId': 'u1'}))

        assert response['statusCode'] == 500
        mock_add.assert_not_called()

    @patch('cognito_sync.is_last_studio_admin')
    @patch('perm_audit.log_permission_change')
    @patch('permissions_repo.list_user_teams', return_value=[])
    @patch('boto3.client')
    def test_promotion_to_admin_skips_guard(self, mock_boto_client, mock_list_teams,
                                            mock_audit, mock_last):
        from handlers.update_user import handle

        os.environ['USER_POOL_ID'] = 'pool-123'
        response = handle(_admin_event(body={'role': 'admin'}, path_params={'userId': 'u1'}))

        assert response['statusCode'] == 200
        mock_last.assert_not_called()


def _legacy_delete_event(username):
    event = _admin_event(path_params={'username': username})
    event['httpMethod'] = 'DELETE'
    return event


class TestLegacyDeleteUserLastAdminGuard:
    """DELETE /users/{username} is routed to the top-level delete_user.py."""

    @patch('boto3.client')
    def test_deleting_sole_admin_returns_409(self, mock_boto_client):
        from delete_user import handler

        cognito = mock_boto_client.return_value
        cognito.admin_list_groups_for_user.return_value = {'Groups': [{'GroupName': 'admins'}]}
        cognito.list_users_in_group.return_value = {'Users': [{'Username': 'sole'}]}
        os.environ['USER_POOL_ID'] = 'pool-123'

        response = handler(_legacy_delete_event('sole'), None)

        assert response['statusCode'] == 409
        cognito.admin_delete_user.assert_not_called()

    @patch('boto3.client')
    def test_deleting_non_admin_returns_204(self, mock_boto_client):
        from delete_user import handler

        cognito = mock_boto_client.return_value
        cognito.admin_list_groups_for_user.return_value = {'Groups': []}
        os.environ['USER_POOL_ID'] = 'pool-123'

        response = handler(_legacy_delete_event('user%40example.com'), None)

        assert response['statusCode'] == 204
        cognito.admin_delete_user.assert_called_once_with(UserPoolId='pool-123', Username='user@example.com')

    @patch('boto3.client')
    @patch('cognito_sync.is_last_studio_admin', side_effect=RuntimeError('cognito down'))
    def test_guard_failure_fails_closed(self, mock_last, mock_boto_client):
        from delete_user import handler

        os.environ['USER_POOL_ID'] = 'pool-123'
        response = handler(_legacy_delete_event('u1'), None)

        assert response['statusCode'] == 500
        mock_boto_client.return_value.admin_delete_user.assert_not_called()
