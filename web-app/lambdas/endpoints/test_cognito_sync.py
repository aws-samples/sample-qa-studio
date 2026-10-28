"""
Tests for Cognito group synchronization utilities (cognito_sync.py).

Covers:
- ensure_team_groups (existing Bolt 1 function)
- delete_team_groups (idempotent deletion)
- set_user_role (add-first-then-remove ordering)
- remove_user_from_team_role
- count_studio_admins
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock, call

# Ensure the endpoints directory is on the path
sys.path.insert(0, os.path.dirname(__file__))

from cognito_sync import (
    ensure_team_groups,
    delete_team_groups,
    remove_user_from_team_role,
    set_user_role,
    count_studio_admins,
    is_last_studio_admin,
)


# ---------------------------------------------------------------------------
# ensure_team_groups tests (existing from Bolt 1)
# ---------------------------------------------------------------------------


class TestEnsureTeamGroups:
    """Tests for idempotent group creation."""

    @patch('cognito_sync.boto3.client')
    def test_creates_all_four_team_role_groups(self, mock_boto_client):
        """Creates the 4 team role groups; never a team-scoped admin group (C-1)."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito

        result = ensure_team_groups('team-123', 'us-east-1_pool')

        expected_groups = [
            'team-team-123-team_lead',
            'team-team-123-editor',
            'team-team-123-executor',
            'team-team-123-viewer',
        ]
        assert result == expected_groups
        assert mock_cognito.create_group.call_count == 4
        created = [c.kwargs['GroupName'] for c in mock_cognito.create_group.call_args_list]
        assert 'team-team-123-admin' not in created

    @patch('cognito_sync.boto3.client')
    def test_idempotent_when_groups_exist(self, mock_boto_client):
        """Swallows GroupExistsException — idempotent."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.exceptions.GroupExistsException = type('GroupExistsException', (Exception,), {})
        mock_cognito.create_group.side_effect = mock_cognito.exceptions.GroupExistsException()

        result = ensure_team_groups('team-123', 'us-east-1_pool')

        assert len(result) == 4
        assert mock_cognito.create_group.call_count == 4


# ---------------------------------------------------------------------------
# delete_team_groups tests
# ---------------------------------------------------------------------------


class TestDeleteTeamGroups:
    """Tests for team group deletion."""

    @patch('cognito_sync.boto3.client')
    def test_deletes_team_role_groups_and_legacy_admin_group(self, mock_boto_client):
        """Deletes the 4 team role groups plus the legacy team-{id}-admin group."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito

        result = delete_team_groups('team-456', 'us-east-1_pool')

        expected_groups = [
            'team-team-456-team_lead',
            'team-team-456-editor',
            'team-team-456-executor',
            'team-team-456-viewer',
            'team-team-456-admin',
        ]
        assert result == expected_groups
        assert mock_cognito.delete_group.call_count == 5

        # Verify each call has correct parameters
        for role in ['team_lead', 'editor', 'executor', 'viewer', 'admin']:
            mock_cognito.delete_group.assert_any_call(
                GroupName=f'team-team-456-{role}',
                UserPoolId='us-east-1_pool',
            )

    @patch('cognito_sync.boto3.client')
    def test_idempotent_when_groups_already_deleted(self, mock_boto_client):
        """Swallows ResourceNotFoundException — idempotent."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.exceptions.ResourceNotFoundException = type(
            'ResourceNotFoundException', (Exception,), {}
        )
        mock_cognito.delete_group.side_effect = mock_cognito.exceptions.ResourceNotFoundException()

        result = delete_team_groups('team-gone', 'us-east-1_pool')

        assert len(result) == 5
        assert mock_cognito.delete_group.call_count == 5

    @patch('cognito_sync.boto3.client')
    def test_raises_on_unexpected_error(self, mock_boto_client):
        """Non-ResourceNotFoundException errors are propagated."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.exceptions.ResourceNotFoundException = type(
            'ResourceNotFoundException', (Exception,), {}
        )
        mock_cognito.delete_group.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(RuntimeError, match="Unexpected error"):
            delete_team_groups('team-456', 'us-east-1_pool')


# ---------------------------------------------------------------------------
# remove_user_from_team_role tests
# ---------------------------------------------------------------------------


class TestRemoveUserFromTeamRole:
    """Tests for removing a user from a team role group."""

    @patch('cognito_sync.boto3.client')
    def test_removes_user_from_group(self, mock_boto_client):
        """Successfully removes user from the team role group."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito

        remove_user_from_team_role('user-sub-1', 'team-alpha', 'editor', 'us-east-1_pool')

        mock_cognito.admin_remove_user_from_group.assert_called_once_with(
            UserPoolId='us-east-1_pool',
            Username='user-sub-1',
            GroupName='team-team-alpha-editor',
        )

    @patch('cognito_sync.boto3.client')
    def test_raises_on_error(self, mock_boto_client):
        """Propagates errors from Cognito API."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.admin_remove_user_from_group.side_effect = RuntimeError("API error")

        with pytest.raises(RuntimeError, match="API error"):
            remove_user_from_team_role('user-sub-1', 'team-alpha', 'editor', 'us-east-1_pool')


# ---------------------------------------------------------------------------
# set_user_role tests
# ---------------------------------------------------------------------------


class TestSetUserRole:
    """Tests for role change (add-first-then-remove ordering)."""

    @patch('cognito_sync.boto3.client')
    def test_adds_new_group_before_removing_old(self, mock_boto_client):
        """Verifies add-first ordering to prevent access gap (BL-6)."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito

        # Track call order
        call_order = []
        mock_cognito.admin_add_user_to_group.side_effect = (
            lambda **kwargs: call_order.append(('add', kwargs['GroupName']))
        )
        mock_cognito.admin_remove_user_from_group.side_effect = (
            lambda **kwargs: call_order.append(('remove', kwargs['GroupName']))
        )

        set_user_role('user-sub-1', 'team-alpha', 'viewer', 'editor', 'us-east-1_pool')

        # Verify order: ADD first, REMOVE second
        assert len(call_order) == 2
        assert call_order[0] == ('add', 'team-team-alpha-editor')
        assert call_order[1] == ('remove', 'team-team-alpha-viewer')

    @patch('cognito_sync.boto3.client')
    def test_raises_if_add_fails(self, mock_boto_client):
        """If adding new group fails, exception propagates (user keeps old role)."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.admin_add_user_to_group.side_effect = RuntimeError("Add failed")

        with pytest.raises(RuntimeError, match="Add failed"):
            set_user_role('user-sub-1', 'team-alpha', 'viewer', 'editor', 'us-east-1_pool')

        # Remove should NOT have been called
        mock_cognito.admin_remove_user_from_group.assert_not_called()

    @patch('cognito_sync.boto3.client')
    def test_remove_failure_does_not_raise(self, mock_boto_client):
        """If remove fails after add, warning logged but no exception (BL-6)."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.admin_remove_user_from_group.side_effect = RuntimeError("Remove failed")

        # Should NOT raise — user has both groups briefly
        set_user_role('user-sub-1', 'team-alpha', 'viewer', 'editor', 'us-east-1_pool')

        # Add was called
        mock_cognito.admin_add_user_to_group.assert_called_once()
        # Remove was attempted
        mock_cognito.admin_remove_user_from_group.assert_called_once()

    @patch('cognito_sync.boto3.client')
    def test_correct_group_names_for_role_change(self, mock_boto_client):
        """Group names are correctly formed for any role transition."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito

        set_user_role('user-sub-1', 'my-team', 'executor', 'team_lead', 'us-east-1_pool')

        mock_cognito.admin_add_user_to_group.assert_called_once_with(
            UserPoolId='us-east-1_pool',
            Username='user-sub-1',
            GroupName='team-my-team-team_lead',
        )
        mock_cognito.admin_remove_user_from_group.assert_called_once_with(
            UserPoolId='us-east-1_pool',
            Username='user-sub-1',
            GroupName='team-my-team-executor',
        )


# ---------------------------------------------------------------------------
# count_studio_admins tests
# ---------------------------------------------------------------------------


class TestCountStudioAdmins:
    """Tests for counting members of the global 'admins' group."""

    @patch('cognito_sync.boto3.client')
    def test_counts_single_page(self, mock_boto_client):
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.list_users_in_group.return_value = {'Users': [{'Username': 'a'}, {'Username': 'b'}]}

        assert count_studio_admins('us-east-1_pool') == 2
        mock_cognito.list_users_in_group.assert_called_once_with(
            UserPoolId='us-east-1_pool', GroupName='admins',
        )

    @patch('cognito_sync.boto3.client')
    def test_paginates(self, mock_boto_client):
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.list_users_in_group.side_effect = [
            {'Users': [{'Username': 'a'}], 'NextToken': 't1'},
            {'Users': [{'Username': 'b'}, {'Username': 'c'}]},
        ]

        assert count_studio_admins('us-east-1_pool') == 3
        assert mock_cognito.list_users_in_group.call_args_list[1] == call(
            UserPoolId='us-east-1_pool', GroupName='admins', NextToken='t1',
        )

    @patch('cognito_sync.boto3.client')
    def test_empty_group(self, mock_boto_client):
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.list_users_in_group.return_value = {'Users': []}

        assert count_studio_admins('us-east-1_pool') == 0

    @patch('cognito_sync.boto3.client')
    def test_propagates_errors(self, mock_boto_client):
        """Errors propagate so the last-admin guard fails closed."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.list_users_in_group.side_effect = RuntimeError('boom')

        with pytest.raises(RuntimeError):
            count_studio_admins('us-east-1_pool')


class TestIsLastStudioAdmin:
    @patch('cognito_sync.boto3.client')
    def test_sole_admin_is_last(self, mock_boto_client):
        cognito = mock_boto_client.return_value
        cognito.admin_list_groups_for_user.return_value = {'Groups': [{'GroupName': 'admins'}]}
        cognito.list_users_in_group.return_value = {'Users': [{'Username': 'u1'}]}

        assert is_last_studio_admin('u1', 'pool') is True

    @patch('cognito_sync.boto3.client')
    def test_one_of_many_admins_is_not_last(self, mock_boto_client):
        cognito = mock_boto_client.return_value
        cognito.admin_list_groups_for_user.return_value = {'Groups': [{'GroupName': 'admins'}]}
        cognito.list_users_in_group.return_value = {'Users': [{'Username': 'u1'}, {'Username': 'u2'}]}

        assert is_last_studio_admin('u1', 'pool') is False

    @patch('cognito_sync.boto3.client')
    def test_team_admin_group_is_not_studio_admin(self, mock_boto_client):
        cognito = mock_boto_client.return_value
        cognito.admin_list_groups_for_user.return_value = {'Groups': [{'GroupName': 'team-x-admin'}]}

        assert is_last_studio_admin('u1', 'pool') is False
        cognito.list_users_in_group.assert_not_called()

    @patch('cognito_sync.boto3.client')
    def test_paginates_user_groups(self, mock_boto_client):
        cognito = mock_boto_client.return_value
        cognito.admin_list_groups_for_user.side_effect = [
            {'Groups': [{'GroupName': 'team-x-viewer'}], 'NextToken': 'n1'},
            {'Groups': [{'GroupName': 'admins'}]},
        ]
        cognito.list_users_in_group.return_value = {'Users': [{'Username': 'u1'}]}

        assert is_last_studio_admin('u1', 'pool') is True
        assert cognito.admin_list_groups_for_user.call_args_list[1] == call(
            UserPoolId='pool', Username='u1', NextToken='n1')
