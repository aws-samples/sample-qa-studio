"""
Tests for the resource authorization decision engine (resource_auth.py).

Covers:
- Admin bypass
- Owner-team member permissions (all roles)
- Ceiling rule scenarios (US-3.2)
- Creator-retains-edit (FR-4.1, FR-4.3)
- Unassigned user denial
- Orphaned app denial
- Per-test-case override narrowing
- DynamoDB error → deny (deny-by-default)
- filter_visible_apps correctness
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Ensure the endpoints directory is on the path
sys.path.insert(0, os.path.dirname(__file__))

from resource_auth import (
    authorize_resource,
    effective_permission,
    can_act,
    filter_visible_apps,
    annotate_app_source,
    can_view_testcase,
    has_team_role,
    require_team_role,
    validate_team_role,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(sub='user-sub-123', email='user@example.com', team_roles=None,
                is_admin=False, identity_type='user'):
    """Build an API Gateway event with authorizer context."""
    if team_roles is None:
        team_roles = []

    return {
        'requestContext': {
            'authorizer': {
                'sub': sub,
                'email': email,
                'identityType': identity_type,
                'identity_type': identity_type,
                'teamRoles': json.dumps(team_roles),
                'isAdmin': 'true' if is_admin else 'false',
                'scope': 'api/admin' if is_admin else 'api/usecases.read',
            }
        }
    }


# ---------------------------------------------------------------------------
# effective_permission tests
# ---------------------------------------------------------------------------


class TestEffectivePermission:
    """Unit tests for the ceiling rule computation."""

    def test_viewer_plus_full_shared_equals_view(self):
        """US-3.2 scenario 1: Viewer + Full shared → view."""
        assert effective_permission('viewer', 'full') == 'view'

    def test_executor_plus_view_shared_equals_view(self):
        """US-3.2 scenario 2: Executor + View shared → view."""
        assert effective_permission('executor', 'view') == 'view'

    def test_editor_plus_execute_shared_equals_execute(self):
        """US-3.2 scenario 3: Editor + Execute shared → execute."""
        assert effective_permission('editor', 'execute') == 'execute'

    def test_editor_plus_full_shared_equals_full(self):
        """Editor + Full shared → full (no ceiling reduction)."""
        assert effective_permission('editor', 'full') == 'full'

    def test_team_lead_plus_view_shared_equals_view(self):
        """Team lead + View shared → view (ceiling caps)."""
        assert effective_permission('team_lead', 'view') == 'view'

    def test_unknown_role_defaults_to_view(self):
        """Unknown role → treated as view."""
        assert effective_permission('unknown_role', 'full') == 'view'


# ---------------------------------------------------------------------------
# can_act tests
# ---------------------------------------------------------------------------


class TestCanAct:
    """Unit tests for action permission matrix."""

    def test_full_can_do_everything(self):
        assert can_act('full', 'view') is True
        assert can_act('full', 'execute') is True
        assert can_act('full', 'edit') is True
        assert can_act('full', 'delete') is True

    def test_execute_can_view_and_execute(self):
        assert can_act('execute', 'view') is True
        assert can_act('execute', 'execute') is True
        assert can_act('execute', 'edit') is False
        assert can_act('execute', 'delete') is False

    def test_view_can_only_view(self):
        assert can_act('view', 'view') is True
        assert can_act('view', 'execute') is False
        assert can_act('view', 'edit') is False
        assert can_act('view', 'delete') is False

    def test_unknown_action_denied(self):
        assert can_act('full', 'unknown_action') is False


# ---------------------------------------------------------------------------
# authorize_resource tests
# ---------------------------------------------------------------------------


class TestAuthorizeResourceAdminBypass:
    """Admin bypasses all resource authorization."""

    @patch('resource_auth.get_app_owner')
    def test_admin_bypasses_all(self, mock_get_owner):
        """Admin can access any app with any action without checking ownership."""
        event = _make_event(is_admin=True)
        identity, error = authorize_resource(event, 'app-123', 'delete')

        assert error is None
        assert identity['is_admin'] is True
        # Should NOT have called get_app_owner (short-circuited)
        mock_get_owner.assert_not_called()


class TestAuthorizeResourceOwnerTeam:
    """Direct team membership authorization."""

    @patch('resource_auth.get_app_owner')
    def test_editor_can_edit(self, mock_get_owner):
        """Editor in owner team can edit."""
        mock_get_owner.return_value = 'team-alpha'
        event = _make_event(
            team_roles=[{'team_id': 'team-alpha', 'role': 'editor'}]
        )

        identity, error = authorize_resource(event, 'app-123', 'edit')
        assert error is None

    @patch('resource_auth.get_app_owner')
    def test_viewer_cannot_edit(self, mock_get_owner):
        """Viewer in owner team cannot edit."""
        mock_get_owner.return_value = 'team-alpha'
        event = _make_event(
            team_roles=[{'team_id': 'team-alpha', 'role': 'viewer'}]
        )

        identity, error = authorize_resource(event, 'app-123', 'edit')
        assert error is not None
        assert error['statusCode'] == 403

    @patch('resource_auth.get_app_owner')
    def test_executor_can_execute(self, mock_get_owner):
        """Executor in owner team can execute."""
        mock_get_owner.return_value = 'team-alpha'
        event = _make_event(
            team_roles=[{'team_id': 'team-alpha', 'role': 'executor'}]
        )

        identity, error = authorize_resource(event, 'app-123', 'execute')
        assert error is None

    @patch('resource_auth.get_app_owner')
    def test_executor_cannot_edit(self, mock_get_owner):
        """Executor in owner team cannot edit."""
        mock_get_owner.return_value = 'team-alpha'
        event = _make_event(
            team_roles=[{'team_id': 'team-alpha', 'role': 'executor'}]
        )

        identity, error = authorize_resource(event, 'app-123', 'edit')
        assert error is not None
        assert error['statusCode'] == 403

    @patch('resource_auth.get_app_owner')
    def test_viewer_can_view(self, mock_get_owner):
        """Viewer in owner team can view."""
        mock_get_owner.return_value = 'team-alpha'
        event = _make_event(
            team_roles=[{'team_id': 'team-alpha', 'role': 'viewer'}]
        )

        identity, error = authorize_resource(event, 'app-123', 'view')
        assert error is None


class TestAuthorizeResourceOwnerPassThrough:
    """owner_team_id pass-through avoids the internal get_app_owner read."""

    @patch('resource_auth.get_app_owner')
    def test_supplied_owner_skips_read(self, mock_get_owner):
        """When owner_team_id is passed, get_app_owner must NOT be called."""
        event = _make_event(team_roles=[{'team_id': 'team-alpha', 'role': 'editor'}])

        identity, error = authorize_resource(
            event, 'app-123', 'edit', owner_team_id='team-alpha')

        assert error is None
        mock_get_owner.assert_not_called()

    @patch('resource_auth.get_app_owner')
    def test_supplied_owner_still_enforces(self, mock_get_owner):
        """Passing the owner does not bypass the permission check."""
        event = _make_event(team_roles=[{'team_id': 'team-alpha', 'role': 'viewer'}])

        identity, error = authorize_resource(
            event, 'app-123', 'edit', owner_team_id='team-alpha')

        assert error is not None
        assert error['statusCode'] == 403
        mock_get_owner.assert_not_called()

    @patch('resource_auth.get_app_owner')
    def test_supplied_none_owner_denies_as_orphaned(self, mock_get_owner):
        """Explicit owner_team_id=None is treated as orphaned → deny, no read."""
        event = _make_event(team_roles=[{'team_id': 'team-alpha', 'role': 'editor'}])

        identity, error = authorize_resource(
            event, 'app-123', 'view', owner_team_id=None)

        assert error is not None
        assert error['statusCode'] == 403
        mock_get_owner.assert_not_called()

    @patch('resource_auth.get_app_owner')
    def test_omitted_owner_falls_back_to_read(self, mock_get_owner):
        """When owner_team_id is omitted, get_app_owner IS called (fallback)."""
        mock_get_owner.return_value = 'team-alpha'
        event = _make_event(team_roles=[{'team_id': 'team-alpha', 'role': 'editor'}])

        identity, error = authorize_resource(event, 'app-123', 'edit')

        assert error is None
        mock_get_owner.assert_called_once_with('app-123')


class TestAuthorizeResourceCeilingRule:
    """Ceiling rule for shared access (US-3.2 scenarios)."""

    @patch('resource_auth.list_shared_access')
    @patch('resource_auth.get_app_owner')
    def test_viewer_plus_full_shared_can_only_view(self, mock_get_owner, mock_list_shared):
        """US-3.2 scenario 1: Viewer + Full shared → view only."""
        mock_get_owner.return_value = 'team-owner'
        mock_list_shared.return_value = [
            {'target_team_id': 'team-beta', 'app_id': 'app-123', 'level': 'full'}
        ]
        event = _make_event(
            team_roles=[{'team_id': 'team-beta', 'role': 'viewer'}]
        )

        # Can view
        identity, error = authorize_resource(event, 'app-123', 'view')
        assert error is None

        # Cannot execute
        identity, error = authorize_resource(event, 'app-123', 'execute')
        assert error is not None
        assert error['statusCode'] == 403

    @patch('resource_auth.list_shared_access')
    @patch('resource_auth.get_app_owner')
    def test_executor_plus_view_shared_can_only_view(self, mock_get_owner, mock_list_shared):
        """US-3.2 scenario 2: Executor + View shared → view only."""
        mock_get_owner.return_value = 'team-owner'
        mock_list_shared.return_value = [
            {'target_team_id': 'team-beta', 'app_id': 'app-123', 'level': 'view'}
        ]
        event = _make_event(
            team_roles=[{'team_id': 'team-beta', 'role': 'executor'}]
        )

        # Can view
        identity, error = authorize_resource(event, 'app-123', 'view')
        assert error is None

        # Cannot execute (ceiling caps to view)
        identity, error = authorize_resource(event, 'app-123', 'execute')
        assert error is not None
        assert error['statusCode'] == 403

    @patch('resource_auth.list_shared_access')
    @patch('resource_auth.get_app_owner')
    def test_editor_plus_execute_shared_can_execute_not_edit(self, mock_get_owner, mock_list_shared):
        """US-3.2 scenario 3: Editor + Execute shared → execute only."""
        mock_get_owner.return_value = 'team-owner'
        mock_list_shared.return_value = [
            {'target_team_id': 'team-beta', 'app_id': 'app-123', 'level': 'execute'}
        ]
        event = _make_event(
            team_roles=[{'team_id': 'team-beta', 'role': 'editor'}]
        )

        # Can execute
        identity, error = authorize_resource(event, 'app-123', 'execute')
        assert error is None

        # Cannot edit (ceiling caps to execute)
        identity, error = authorize_resource(event, 'app-123', 'edit')
        assert error is not None
        assert error['statusCode'] == 403

    @patch('resource_auth.get_app_owner')
    def test_admin_exempt_from_ceiling(self, mock_get_owner):
        """US-3.2 scenario 4: Admin bypasses ceiling entirely."""
        event = _make_event(is_admin=True)

        identity, error = authorize_resource(event, 'app-123', 'delete')
        assert error is None
        mock_get_owner.assert_not_called()


class TestAuthorizeResourceCreatorOverride:
    """Creator-retains-edit (FR-4.1, bounded by FR-4.3)."""

    @patch('resource_auth.list_shared_access')
    @patch('resource_auth.get_app_owner')
    def test_creator_with_viewer_role_gets_edit_override(self, mock_get_owner, mock_list_shared):
        """Creator with viewer role can edit own resource via override."""
        mock_get_owner.return_value = 'team-alpha'
        mock_list_shared.return_value = []

        event = _make_event(
            sub='creator-sub',
            team_roles=[{'team_id': 'team-alpha', 'role': 'viewer'}]
        )

        # Pass created_by matching the caller's sub
        identity, error = authorize_resource(event, 'app-123', 'edit', created_by='creator-sub')
        assert error is None

    @patch('resource_auth.list_shared_access')
    @patch('resource_auth.get_app_owner')
    def test_creator_removed_from_team_denied_edit(self, mock_get_owner, mock_list_shared):
        """Creator removed from team loses edit override (FR-4.3)."""
        mock_get_owner.return_value = 'team-alpha'
        mock_list_shared.return_value = []

        # User has NO team membership at all
        event = _make_event(
            sub='creator-sub',
            team_roles=[]
        )

        identity, error = authorize_resource(event, 'app-123', 'edit', created_by='creator-sub')
        # Should be denied (no access path at all — step 6 fires)
        assert error is not None
        assert error['statusCode'] == 403

    @patch('resource_auth.list_shared_access')
    @patch('resource_auth.get_app_owner')
    def test_creator_override_does_not_grant_delete(self, mock_get_owner, mock_list_shared):
        """Creator override only grants edit, NOT delete."""
        mock_get_owner.return_value = 'team-alpha'
        mock_list_shared.return_value = []

        event = _make_event(
            sub='creator-sub',
            team_roles=[{'team_id': 'team-alpha', 'role': 'viewer'}]
        )

        # Even with created_by, delete is not granted
        identity, error = authorize_resource(event, 'app-123', 'delete', created_by='creator-sub')
        assert error is not None
        assert error['statusCode'] == 403

    @patch('resource_auth.get_app_owner')
    def test_non_creator_with_viewer_role_denied_edit(self, mock_get_owner):
        """Non-creator with viewer role cannot edit (no override)."""
        mock_get_owner.return_value = 'team-alpha'

        event = _make_event(
            sub='user-sub-123',
            team_roles=[{'team_id': 'team-alpha', 'role': 'viewer'}]
        )

        # created_by is a different user
        identity, error = authorize_resource(event, 'app-123', 'edit', created_by='other-user')
        assert error is not None
        assert error['statusCode'] == 403


class TestAuthorizeResourceDenyScenarios:
    """Denial scenarios."""

    @patch('resource_auth.list_shared_access')
    @patch('resource_auth.get_app_owner')
    def test_unassigned_user_denied(self, mock_get_owner, mock_list_shared):
        """User with no team memberships is denied."""
        mock_get_owner.return_value = 'team-alpha'
        mock_list_shared.return_value = []
        event = _make_event(team_roles=[])

        identity, error = authorize_resource(event, 'app-123', 'view')
        assert error is not None
        assert error['statusCode'] == 403

    @patch('resource_auth.get_app_owner')
    def test_orphaned_app_denied_for_non_admin(self, mock_get_owner):
        """Orphaned app (no owner) is denied for non-admins (BR-4)."""
        mock_get_owner.return_value = None
        event = _make_event(
            team_roles=[{'team_id': 'team-alpha', 'role': 'editor'}]
        )

        identity, error = authorize_resource(event, 'app-orphan', 'view')
        assert error is not None
        assert error['statusCode'] == 403

    @patch('resource_auth.get_app_owner')
    def test_dynamodb_error_denies_access(self, mock_get_owner):
        """DynamoDB error triggers deny-by-default."""
        mock_get_owner.side_effect = Exception("DynamoDB timeout")
        event = _make_event(
            team_roles=[{'team_id': 'team-alpha', 'role': 'editor'}]
        )

        identity, error = authorize_resource(event, 'app-123', 'view')
        assert error is not None
        assert error['statusCode'] == 500
        assert 'Authorization check failed' in json.loads(error['body'])['message']

    @patch('resource_auth.list_shared_access')
    @patch('resource_auth.get_app_owner')
    def test_user_not_in_shared_target_team_denied(self, mock_get_owner, mock_list_shared):
        """User not in any team that has shared access → deny."""
        mock_get_owner.return_value = 'team-owner'
        mock_list_shared.return_value = [
            {'target_team_id': 'team-other', 'app_id': 'app-123', 'level': 'full'}
        ]
        event = _make_event(
            team_roles=[{'team_id': 'team-unrelated', 'role': 'editor'}]
        )

        identity, error = authorize_resource(event, 'app-123', 'view')
        assert error is not None
        assert error['statusCode'] == 403


# ---------------------------------------------------------------------------
# filter_visible_apps tests
# ---------------------------------------------------------------------------


class TestFilterVisibleApps:
    """Tests for the list filtering function."""

    @patch('resource_auth.list_apps_shared_with_team')
    def test_admin_sees_all_apps(self, mock_shared_with):
        """Admin sees all apps regardless of ownership."""
        identity = {'is_admin': True, 'team_roles': [], 'sub': 'admin-sub'}
        apps = [
            {'id': 'app-1', 'owner_team_id': 'team-a'},
            {'id': 'app-2', 'owner_team_id': 'team-b'},
            {'id': 'app-3', 'owner_team_id': None},  # orphaned
        ]

        result = filter_visible_apps(identity, apps)
        assert len(result) == 3
        assert all(a['source'] == 'owned' for a in result)

    @patch('resource_auth.list_apps_shared_with_team')
    def test_excludes_non_accessible_apps(self, mock_shared_with):
        """Non-admin user cannot see apps from other teams without shared access."""
        mock_shared_with.return_value = []
        identity = {
            'is_admin': False,
            'team_roles': [{'team_id': 'team-a', 'role': 'editor'}],
            'sub': 'user-sub',
        }
        apps = [
            {'id': 'app-1', 'owner_team_id': 'team-a'},
            {'id': 'app-2', 'owner_team_id': 'team-b'},  # not accessible
        ]

        result = filter_visible_apps(identity, apps)
        assert len(result) == 1
        assert result[0]['id'] == 'app-1'
        assert result[0]['source'] == 'owned'

    @patch('resource_auth.list_apps_shared_with_team')
    @patch('resource_auth.list_shared_access')
    @patch('resource_auth.get_team')
    def test_annotates_shared_apps(self, mock_get_team, mock_list_shared, mock_shared_with):
        """Shared apps are annotated with source='shared' and sharedFrom."""
        mock_shared_with.return_value = [
            {'app_id': 'app-2', 'target_team_id': 'team-a', 'owner_team_id': 'team-b', 'level': 'execute'}
        ]
        mock_list_shared.return_value = [
            {'target_team_id': 'team-a', 'app_id': 'app-2', 'level': 'execute'}
        ]
        mock_get_team.return_value = {'name': 'Team B'}

        identity = {
            'is_admin': False,
            'team_roles': [{'team_id': 'team-a', 'role': 'editor'}],
            'sub': 'user-sub',
        }
        apps = [
            {'id': 'app-2', 'owner_team_id': 'team-b'},
        ]

        result = filter_visible_apps(identity, apps)
        assert len(result) == 1
        assert result[0]['source'] == 'shared'
        assert result[0]['sharedFrom'] == 'Team B'

    @patch('resource_auth.list_apps_shared_with_team')
    def test_orphaned_apps_excluded_for_non_admin(self, mock_shared_with):
        """Orphaned apps (null owner) excluded for non-admins."""
        mock_shared_with.return_value = []
        identity = {
            'is_admin': False,
            'team_roles': [{'team_id': 'team-a', 'role': 'editor'}],
            'sub': 'user-sub',
        }
        apps = [
            {'id': 'app-orphan', 'owner_team_id': None},
        ]

        result = filter_visible_apps(identity, apps)
        assert len(result) == 0

    @patch('resource_auth.list_apps_shared_with_team')
    def test_user_with_no_teams_sees_nothing(self, mock_shared_with):
        """User with no team memberships sees zero apps."""
        identity = {
            'is_admin': False,
            'team_roles': [],
            'sub': 'user-sub',
        }
        apps = [
            {'id': 'app-1', 'owner_team_id': 'team-a'},
        ]

        result = filter_visible_apps(identity, apps)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# can_view_testcase tests
# ---------------------------------------------------------------------------


class TestCanViewTestcase:
    """Per-test-case override tests (BR-3)."""

    @patch('resource_auth.get_testcase_override')
    def test_no_override_allows_view(self, mock_override):
        """No override → allow."""
        mock_override.return_value = None
        identity = {'is_admin': False, 'sub': 'user-sub'}

        assert can_view_testcase(identity, 'tc-1', 'editor') is True

    @patch('resource_auth.get_testcase_override')
    def test_admin_bypasses_override(self, mock_override):
        """Admin bypasses per-test-case overrides."""
        mock_override.return_value = {
            'allowed_subs': ['other-sub'],
            'allowed_roles': ['admin'],
        }
        identity = {'is_admin': True, 'sub': 'admin-sub'}

        assert can_view_testcase(identity, 'tc-1', 'viewer') is True
        mock_override.assert_not_called()

    @patch('resource_auth.get_testcase_override')
    def test_sub_not_in_allowed_subs_denied(self, mock_override):
        """Caller not in allowed_subs → denied."""
        mock_override.return_value = {
            'allowed_subs': ['other-sub-1', 'other-sub-2'],
            'allowed_roles': [],
        }
        identity = {'is_admin': False, 'sub': 'user-sub'}

        assert can_view_testcase(identity, 'tc-1', 'editor') is False

    @patch('resource_auth.get_testcase_override')
    def test_role_not_in_allowed_roles_denied(self, mock_override):
        """Caller role not in allowed_roles → denied."""
        mock_override.return_value = {
            'allowed_subs': [],
            'allowed_roles': ['editor', 'team_lead'],
        }
        identity = {'is_admin': False, 'sub': 'user-sub'}

        assert can_view_testcase(identity, 'tc-1', 'viewer') is False

    @patch('resource_auth.get_testcase_override')
    def test_sub_in_allowed_subs_allowed(self, mock_override):
        """Caller in allowed_subs → allowed."""
        mock_override.return_value = {
            'allowed_subs': ['user-sub', 'other-sub'],
            'allowed_roles': [],
        }
        identity = {'is_admin': False, 'sub': 'user-sub'}

        assert can_view_testcase(identity, 'tc-1', 'viewer') is True

    @patch('resource_auth.get_testcase_override')
    def test_dynamodb_error_denies_view(self, mock_override):
        """DynamoDB error on override fetch → deny (deny-by-default)."""
        mock_override.side_effect = Exception("DynamoDB error")
        identity = {'is_admin': False, 'sub': 'user-sub'}

        assert can_view_testcase(identity, 'tc-1', 'editor') is False


# ---------------------------------------------------------------------------
# Team role checks (C-1)
# ---------------------------------------------------------------------------


def _identity(team_roles=None, is_admin=False, scopes=None):
    return {
        'sub': 'caller', 'identity_type': 'user', 'is_admin': is_admin,
        'team_roles': team_roles or [], 'scopes': scopes or [],
    }


class TestHasTeamRole:
    def test_role_at_or_above_minimum(self):
        ident = _identity([{'team_id': 't1', 'role': 'team_lead'}])
        assert has_team_role(ident, 't1', 'team_lead') is True
        assert has_team_role(ident, 't1', 'viewer') is True

    def test_role_below_minimum(self):
        ident = _identity([{'team_id': 't1', 'role': 'editor'}])
        assert has_team_role(ident, 't1', 'team_lead') is False

    def test_other_team_does_not_count(self):
        ident = _identity([{'team_id': 't2', 'role': 'team_lead'}])
        assert has_team_role(ident, 't1', 'viewer') is False

    def test_any_team_when_team_id_none(self):
        ident = _identity([{'team_id': 't1', 'role': 'viewer'}, {'team_id': 't2', 'role': 'team_lead'}])
        assert has_team_role(ident, None, 'team_lead') is True
        assert has_team_role(_identity([{'team_id': 't1', 'role': 'editor'}]), None, 'team_lead') is False

    def test_admin_team_role_is_ignored(self):
        """'admin' is not a team role; a stale context entry must not pass."""
        ident = _identity([{'team_id': 't1', 'role': 'admin'}])
        assert has_team_role(ident, 't1', 'viewer') is False
        assert has_team_role(ident, None, 'team_lead') is False

    def test_unknown_role_is_ignored(self):
        assert has_team_role(_identity([{'team_id': 't1', 'role': 'superuser'}]), 't1', 'viewer') is False


class TestRequireTeamRole:
    def test_admin_flag_passes(self):
        assert require_team_role(_identity(is_admin=True), 't1', 'team_lead') is None

    def test_admin_scope_passes(self):
        assert require_team_role(_identity(scopes=['api/admin']), 't1', 'team_lead') is None

    def test_team_lead_passes(self):
        assert require_team_role(_identity([{'team_id': 't1', 'role': 'team_lead'}]), 't1', 'team_lead') is None

    def test_editor_gets_403_with_message(self):
        resp = require_team_role(_identity([{'team_id': 't1', 'role': 'editor'}]), 't1', 'team_lead', 'nope')
        assert resp['statusCode'] == 403
        assert json.loads(resp['body'])['error'] == 'nope'

    def test_teams_manage_scope_alone_is_not_enough(self):
        resp = require_team_role(_identity(scopes=['api/teams.manage']), 't1', 'team_lead')
        assert resp['statusCode'] == 403


class TestValidateTeamRole:
    @pytest.mark.parametrize('role', ['team_lead', 'editor', 'executor', 'viewer'])
    def test_team_roles_valid(self, role):
        assert validate_team_role(role) is None

    def test_admin_rejected_with_hint(self):
        resp = validate_team_role('admin')
        assert resp['statusCode'] == 400
        assert 'PATCH /users/{id}' in json.loads(resp['body'])['error']

    @pytest.mark.parametrize('role', ['', 'superadmin', 'Admin', 'admins'])
    def test_other_values_rejected(self, role):
        resp = validate_team_role(role)
        assert resp['statusCode'] == 400
        assert 'Invalid role' in json.loads(resp['body'])['error']


class TestRoleToLevelHasNoAdmin:
    def test_admin_team_role_gets_view_only(self):
        """A stale 'admin' team role maps to the lowest level, never 'full'."""
        assert effective_permission('admin', 'full') == 'view'


# ---------------------------------------------------------------------------
# Resolvers and require_resource_access (H-2)
# ---------------------------------------------------------------------------

import resource_auth as ra  # noqa: E402


def _req(path=None, query=None, body=None, team_roles=None, is_admin=False,
         scope='api/usecases.read', identity_type='user'):
    authorizer = {
        'sub': 'caller-sub', 'email': 'c@example.com',
        'identityType': identity_type,
        'teamRoles': json.dumps(team_roles or []),
        'isAdmin': 'true' if is_admin else 'false',
        'scope': scope,
    }
    if identity_type != 'user':
        authorizer.update({'email': '', 'clientId': 'client-1'})
    return {
        'pathParameters': path or {},
        'queryStringParameters': query,
        'body': json.dumps(body) if body is not None else None,
        'requestContext': {'authorizer': authorizer},
    }


_UC_OWNED = {'application_id': 'app-1', 'owner_team_id': 'team-a', 'created_by': None}


class TestUsecaseFromPath:
    @patch('resource_auth.get_usecase_owner', return_value=None)
    def test_not_found(self, _):
        ref = ra.usecase_from_path(_req(path={'id': 'uc-1'}))
        assert ref.error['statusCode'] == 404

    def test_invalid_id_400(self):
        ref = ra.usecase_from_path(_req(path={'id': '../x'}))
        assert ref.error['statusCode'] == 400

    @patch('resource_auth.get_app_owner')
    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    def test_denormalized_owner_skips_app_read(self, _, mock_app_owner):
        ref = ra.usecase_from_path(_req(path={'id': 'uc-1'}))
        assert (ref.app_id, ref.owner_team_id, ref.usecase_id) == ('app-1', 'team-a', 'uc-1')
        mock_app_owner.assert_not_called()

    @patch('resource_auth.get_app_owner', return_value='team-b')
    @patch('resource_auth.get_usecase_owner',
           return_value={'application_id': 'app-1', 'owner_team_id': None, 'created_by': None})
    def test_owner_falls_back_to_app(self, *_):
        assert ra.usecase_from_path(_req(path={'id': 'uc-1'})).owner_team_id == 'team-b'

    @patch('resource_auth.get_app_owner')
    @patch('resource_auth.get_usecase_owner',
           return_value={'application_id': None, 'owner_team_id': 'team-a', 'created_by': None})
    def test_no_application_is_orphan_even_with_stale_owner(self, _, mock_app_owner):
        ref = ra.usecase_from_path(_req(path={'id': 'uc-1'}))
        assert ref.error is None and ref.owner_team_id is None
        mock_app_owner.assert_not_called()

    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    def test_creator_loaded_only_for_edit(self, mock_owner):
        ra.usecase_from_path(_req(path={'id': 'uc-1'}), 'view')
        mock_owner.assert_called_with('uc-1', include_creator=False)
        ra.usecase_from_path(_req(path={'id': 'uc-1'}), 'edit')
        mock_owner.assert_called_with('uc-1', include_creator=True)


class TestExecutionFromPath:
    @patch('resource_auth.get_usecase_owner')
    @patch('resource_auth.get_execution_record', return_value=None)
    def test_execution_not_under_usecase_404(self, mock_exec, mock_owner):
        ref = ra.execution_from_path(_req(path={'id': 'uc-mine', 'executionId': 'ex-foreign'}))
        assert ref.error['statusCode'] == 404
        mock_exec.assert_called_once_with('uc-mine', 'ex-foreign')
        mock_owner.assert_not_called()

    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    @patch('resource_auth.get_execution_record',
           return_value={'status': 'running', 'worker_token_hash': None,
                         'suite_id': 's-1', 'suite_execution_id': 'sx-1'})
    def test_resolves_execution_and_owner(self, *_):
        ref = ra.execution_from_path(_req(path={'id': 'uc-1', 'executionId': 'ex-1'}))
        assert ref.error is None
        assert (ref.execution_id, ref.suite_id, ref.suite_execution_id) == ('ex-1', 's-1', 'sx-1')
        assert ref.owner_team_id == 'team-a'

    @patch('resource_auth.get_usecase_owner', return_value=None)
    @patch('resource_auth.get_execution_record', return_value={'status': 'running'})
    def test_usecase_missing_404(self, *_):
        ref = ra.execution_from_path(_req(path={'id': 'uc-1', 'executionId': 'ex-1'}))
        assert ref.error['statusCode'] == 404

    def test_missing_execution_id_400(self):
        assert ra.execution_from_path(_req(path={'id': 'uc-1'})).error['statusCode'] == 400


class TestSuiteResolvers:
    @patch('resource_auth.get_suite_owner', return_value=None)
    def test_suite_not_found(self, _):
        assert ra.suite_from_path(_req(path={'suite_id': 's-1'})).error['statusCode'] == 404

    @patch('resource_auth.get_suite_owner', return_value={'application_id': None, 'owner_team_id': None})
    def test_orphan_suite(self, _):
        ref = ra.suite_from_path(_req(path={'suite_id': 's-1'}))
        assert ref.error is None and ref.owner_team_id is None and ref.suite_id == 's-1'

    @patch('resource_auth.get_suite_owner')
    @patch('resource_auth.get_suite_execution_record', return_value=None)
    def test_suite_execution_not_under_suite_404(self, mock_sx, mock_suite):
        ref = ra.suite_execution_from_path(_req(path={'suite_id': 's-1', 'execution_id': 'sx-9'}))
        assert ref.error['statusCode'] == 404
        mock_sx.assert_called_once_with('s-1', 'sx-9')
        mock_suite.assert_not_called()

    @patch('resource_auth.get_suite_owner', return_value={'application_id': 'app-1', 'owner_team_id': 'team-a'})
    @patch('resource_auth.get_suite_execution_record', return_value={'status': 'running'})
    def test_suite_execution_resolves(self, *_):
        ref = ra.suite_execution_from_path(_req(path={'suite_id': 's-1', 'execution_id': 'sx-1'}))
        assert (ref.suite_id, ref.suite_execution_id, ref.owner_team_id) == ('s-1', 'sx-1', 'team-a')


class TestAppAndBodyResolvers:
    @patch('resource_auth.get_app_ownership', return_value=None)
    def test_app_not_found(self, _):
        assert ra.app_from_path(_req(path={'id': 'app-1'})).error['statusCode'] == 404

    @patch('resource_auth.get_app_ownership', return_value={'owner_team_id': None})
    def test_orphan_app(self, _):
        ref = ra.app_from_path(_req(path={'id': 'app-1'}))
        assert ref.error is None and ref.app_id == 'app-1' and ref.owner_team_id is None

    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    def test_usecase_from_body(self, mock_owner):
        ref = ra.usecase_from_body('usecaseId')(_req(body={'usecaseId': 'uc-7'}))
        assert ref.usecase_id == 'uc-7' and ref.owner_team_id == 'team-a'

    def test_usecase_from_body_missing_400(self):
        assert ra.usecase_from_body('usecaseId')(_req(body={})).error['statusCode'] == 400

    def test_usecase_from_body_bad_json_400(self):
        event = _req()
        event['body'] = '{not json'
        assert ra.usecase_from_body('usecaseId')(event).error['statusCode'] == 400

    @patch('resource_auth.get_app_ownership', return_value={'owner_team_id': 'team-a'})
    def test_app_from_body(self, _):
        ref = ra.app_from_body('application_id')(_req(body={'application_id': 'app-2'}))
        assert ref.app_id == 'app-2' and ref.owner_team_id == 'team-a'

    def test_app_from_body_required(self):
        assert ra.app_from_body('application_id')(_req(body={})).error['statusCode'] == 400


class TestWizardSessionFromPath:
    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    @patch('resource_auth.get_execution_record', return_value={'status': 'running'})
    def test_usecase_from_path_query_or_body(self, mock_exec, _):
        for event in (
            _req(path={'sessionId': 'ws-1', 'usecaseId': 'uc-1'}),
            _req(path={'sessionId': 'ws-1'}, query={'usecaseId': 'uc-1'}),
            _req(path={'sessionId': 'ws-1'}, body={'usecaseId': 'uc-1'}),
        ):
            ref = ra.wizard_session_from_path(event)
            assert ref.error is None and ref.usecase_id == 'uc-1' and ref.execution_id == 'ws-1'
        mock_exec.assert_called_with('uc-1', 'ws-1')

    def test_usecase_id_required(self):
        ref = ra.wizard_session_from_path(_req(path={'sessionId': 'ws-1'}, body={}))
        assert ref.error['statusCode'] == 400

    @patch('resource_auth.get_execution_record', return_value=None)
    def test_session_not_under_usecase_404(self, _):
        ref = ra.wizard_session_from_path(_req(path={'sessionId': 'ws-1', 'usecaseId': 'uc-2'}))
        assert ref.error['statusCode'] == 404


def _protected(action='view', resolver=None, scopes=('api/usecases.read',), allow_worker=False):
    calls = []

    @ra.require_resource_access(action, resolver or ra.usecase_from_path,
                                scopes=list(scopes), allow_worker=allow_worker)
    def handler(event, context):
        calls.append(event)
        return {'statusCode': 200, 'body': '{}'}
    return handler, calls


class TestRequireResourceAccess:
    @pytest.fixture(autouse=True)
    def _no_override(self):
        with patch('resource_auth.get_testcase_override', return_value=None):
            yield

    def test_scope_checked_before_resolver(self):
        resolver = MagicMock()
        handler, calls = _protected(resolver=resolver, scopes=['api/usecases.write'])
        resp = handler(_req(path={'id': 'uc-1'}, team_roles=[{'team_id': 'team-a', 'role': 'editor'}]), None)
        assert resp['statusCode'] == 403
        resolver.assert_not_called()
        assert calls == []

    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    def test_owner_team_member_allowed(self, _):
        handler, calls = _protected()
        resp = handler(_req(path={'id': 'uc-1'}, team_roles=[{'team_id': 'team-a', 'role': 'viewer'}]), None)
        assert resp['statusCode'] == 200 and len(calls) == 1

    @patch('resource_auth.list_shared_access', return_value=[])
    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    def test_other_team_denied(self, *_):
        handler, calls = _protected()
        resp = handler(_req(path={'id': 'uc-1'}, team_roles=[{'team_id': 'team-b', 'role': 'editor'}]), None)
        assert resp['statusCode'] == 403 and calls == []

    @patch('resource_auth.get_usecase_owner',
           return_value={'application_id': None, 'owner_team_id': None, 'created_by': None})
    def test_orphan_denied_for_non_admin(self, _):
        handler, calls = _protected()
        resp = handler(_req(path={'id': 'uc-1'}, team_roles=[{'team_id': 'team-a', 'role': 'team_lead'}]), None)
        assert resp['statusCode'] == 403 and calls == []

    @patch('resource_auth.get_usecase_owner',
           return_value={'application_id': None, 'owner_team_id': None, 'created_by': None})
    def test_orphan_allowed_for_admin(self, _):
        handler, calls = _protected(action='delete')
        resp = handler(_req(path={'id': 'uc-1'}, is_admin=True, scope='api/admin'), None)
        assert resp['statusCode'] == 200

    @patch('resource_auth.get_usecase_owner', return_value=None)
    def test_resolver_error_returned(self, _):
        handler, calls = _protected()
        resp = handler(_req(path={'id': 'uc-1'}, is_admin=True, scope='api/admin'), None)
        assert resp['statusCode'] == 404 and calls == []

    @patch('resource_auth.get_usecase_owner', side_effect=Exception('ddb down'))
    def test_resolver_exception_fails_closed(self, _):
        handler, calls = _protected()
        resp = handler(_req(path={'id': 'uc-1'}, team_roles=[{'team_id': 'team-a', 'role': 'editor'}]), None)
        assert resp['statusCode'] == 500 and calls == []

    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    def test_action_enforced(self, _):
        handler, calls = _protected(action='execute', scopes=['api/usecases.execute'])
        resp = handler(_req(path={'id': 'uc-1'}, scope='api/usecases.execute',
                            team_roles=[{'team_id': 'team-a', 'role': 'viewer'}]), None)
        assert resp['statusCode'] == 403 and calls == []

    @patch('resource_auth.get_usecase_owner',
           return_value={'application_id': 'app-1', 'owner_team_id': 'team-a', 'created_by': 'caller-sub'})
    def test_creator_retains_edit(self, mock_owner):
        handler, calls = _protected(action='edit', scopes=['api/usecases.write'])
        resp = handler(_req(path={'id': 'uc-1'}, scope='api/usecases.write',
                            team_roles=[{'team_id': 'team-a', 'role': 'viewer'}]), None)
        assert resp['statusCode'] == 200
        mock_owner.assert_called_once_with('uc-1', include_creator=True)

    @patch('resource_auth.list_shared_access', return_value=[])
    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    def test_client_without_team_roles_denied(self, *_):
        handler, calls = _protected()
        resp = handler(_req(path={'id': 'uc-1'}, identity_type='client'), None)
        assert resp['statusCode'] == 403 and calls == []

    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    def test_client_bound_to_owner_team_allowed(self, _):
        handler, calls = _protected()
        resp = handler(_req(path={'id': 'uc-1'}, identity_type='client',
                            team_roles=[{'team_id': 'team-a', 'role': 'executor'}]), None)
        assert resp['statusCode'] == 200

    @patch('resource_auth.list_shared_access', return_value=[])
    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    def test_client_bound_to_other_team_denied(self, *_):
        handler, calls = _protected()
        resp = handler(_req(path={'id': 'uc-1'}, identity_type='client',
                            team_roles=[{'team_id': 'team-b', 'role': 'editor'}]), None)
        assert resp['statusCode'] == 403 and calls == []

    @patch('resource_auth._authorize_worker')
    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    def test_worker_rejected_when_not_allowed(self, _, mock_worker):
        handler, calls = _protected(allow_worker=False)
        resp = handler(_req(path={'id': 'uc-1'}, identity_type='worker'), None)
        assert resp['statusCode'] == 403 and calls == []
        mock_worker.assert_not_called()

    @patch('resource_auth.authorize_resource')
    @patch('resource_auth._authorize_worker', return_value=None)
    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    def test_worker_uses_capability_not_team_check(self, _, mock_worker, mock_authz):
        handler, calls = _protected(allow_worker=True)
        resp = handler(_req(path={'id': 'uc-1'}, identity_type='worker'), None)
        assert resp['statusCode'] == 200
        mock_worker.assert_called_once()
        mock_authz.assert_not_called()


import hashlib  # noqa: E402

_TOKEN = 'tok-123'
_TOKEN_HASH = hashlib.sha256(_TOKEN.encode()).hexdigest()


def _exec_record(status='running', token_hash=_TOKEN_HASH, suite_id=None, suite_execution_id=None):
    return {'status': status, 'worker_token_hash': token_hash,
            'suite_id': suite_id, 'suite_execution_id': suite_execution_id}


def _worker_event(header='uc-1:ex-1:' + _TOKEN, header_name='X-QA-Execution-Token', path=None):
    event = _req(path=path or {'id': 'uc-1', 'executionId': 'ex-1'}, identity_type='worker',
                 scope='api/executions.write api/usecases.read')
    event['headers'] = {header_name: header} if header is not None else {}
    return event


class TestParseExecutionToken:
    def test_valid(self):
        assert ra.parse_execution_token('uc-1:ex-1:abc:def') == ('uc-1', 'ex-1', 'abc:def')

    @pytest.mark.parametrize('raw', [None, '', 'ex-1:tok', 'uc-1:ex-1:', '../x:ex-1:tok', 'uc-1::tok'])
    def test_malformed(self, raw):
        assert ra.parse_execution_token(raw) is None


class TestAuthorizeWorker:
    @patch('resource_auth.get_execution_record', return_value=_exec_record())
    def test_valid_token_for_own_execution(self, mock_exec):
        ref = ra.ResourceRef(usecase_id='uc-1', execution_id='ex-1')
        assert ra._authorize_worker(_worker_event(), ref) is None
        mock_exec.assert_called_once_with('uc-1', 'ex-1')

    @patch('resource_auth.get_execution_record', return_value=_exec_record())
    def test_header_name_case_insensitive(self, _):
        ref = ra.ResourceRef(usecase_id='uc-1', execution_id='ex-1')
        assert ra._authorize_worker(_worker_event(header_name='x-qa-execution-token'), ref) is None

    @patch('resource_auth.get_execution_record', return_value=_exec_record())
    def test_use_case_level_route_of_own_use_case(self, _):
        assert ra._authorize_worker(_worker_event(), ra.ResourceRef(usecase_id='uc-1')) is None

    @patch('resource_auth.get_execution_record', return_value=_exec_record())
    def test_wrong_token(self, _):
        ref = ra.ResourceRef(usecase_id='uc-1', execution_id='ex-1')
        assert ra._authorize_worker(_worker_event(header='uc-1:ex-1:guess'), ref)['statusCode'] == 403

    @patch('resource_auth.get_execution_record', return_value=_exec_record())
    def test_missing_header(self, mock_exec):
        ref = ra.ResourceRef(usecase_id='uc-1', execution_id='ex-1')
        assert ra._authorize_worker(_worker_event(header=None), ref)['statusCode'] == 403
        mock_exec.assert_not_called()

    @patch('resource_auth.get_execution_record', return_value=_exec_record())
    def test_token_for_another_use_case(self, mock_exec):
        ref = ra.ResourceRef(usecase_id='uc-other', execution_id='ex-9')
        assert ra._authorize_worker(_worker_event(), ref)['statusCode'] == 403
        mock_exec.assert_not_called()

    @patch('resource_auth.get_execution_record', return_value=_exec_record())
    def test_token_for_another_execution(self, mock_exec):
        ref = ra.ResourceRef(usecase_id='uc-1', execution_id='ex-2')
        assert ra._authorize_worker(_worker_event(), ref)['statusCode'] == 403
        mock_exec.assert_not_called()

    @pytest.mark.parametrize('status', ['success', 'failed', 'stopped', None])
    def test_finished_execution(self, status):
        ref = ra.ResourceRef(usecase_id='uc-1', execution_id='ex-1')
        with patch('resource_auth.get_execution_record', return_value=_exec_record(status=status)):
            assert ra._authorize_worker(_worker_event(), ref)['statusCode'] == 403

    @patch('resource_auth.get_execution_record', return_value=_exec_record(status='pending'))
    def test_pending_execution_allowed(self, _):
        assert ra._authorize_worker(_worker_event(), ra.ResourceRef(usecase_id='uc-1', execution_id='ex-1')) is None

    @patch('resource_auth.get_execution_record', return_value=_exec_record(token_hash=None))
    def test_execution_without_hash(self, _):
        ref = ra.ResourceRef(usecase_id='uc-1', execution_id='ex-1')
        assert ra._authorize_worker(_worker_event(), ref)['statusCode'] == 403

    @patch('resource_auth.get_execution_record', return_value=None)
    def test_unknown_execution(self, _):
        ref = ra.ResourceRef(usecase_id='uc-1', execution_id='ex-1')
        assert ra._authorize_worker(_worker_event(), ref)['statusCode'] == 403

    def test_non_execution_resource_denied(self):
        assert ra._authorize_worker(_worker_event(), ra.ResourceRef(app_id='app-1'))['statusCode'] == 403

    @patch('resource_auth.get_execution_record',
           return_value=_exec_record(suite_id='s-1', suite_execution_id='sx-1'))
    def test_suite_route_must_match_execution_suite(self, _):
        event = _worker_event(path={'suite_id': 's-1', 'execution_id': 'sx-1'})
        assert ra._authorize_worker(event, ra.ResourceRef(suite_id='s-1', suite_execution_id='sx-1')) is None
        assert ra._authorize_worker(event, ra.ResourceRef(suite_id='s-2', suite_execution_id='sx-1'))['statusCode'] == 403
        assert ra._authorize_worker(event, ra.ResourceRef(suite_id='s-1', suite_execution_id='sx-2'))['statusCode'] == 403

    @patch('resource_auth.get_execution_record', return_value=_exec_record())
    def test_suite_route_for_non_suite_execution(self, _):
        event = _worker_event(path={'suite_id': 's-1', 'execution_id': 'sx-1'})
        assert ra._authorize_worker(event, ra.ResourceRef(suite_id='s-1', suite_execution_id='sx-1'))['statusCode'] == 403


class TestDecoratorWithWorkerCapability:
    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    @patch('resource_auth.get_execution_record', return_value=_exec_record())
    def test_worker_allowed_on_allow_worker_route(self, *_):
        handler, calls = _protected(resolver=ra.execution_from_path, scopes=['api/executions.write'],
                                    allow_worker=True)
        assert handler(_worker_event(), None)['statusCode'] == 200

    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    @patch('resource_auth.get_execution_record', return_value=_exec_record())
    def test_worker_denied_without_allow_worker(self, *_):
        handler, calls = _protected(resolver=ra.execution_from_path, scopes=['api/executions.write'])
        assert handler(_worker_event(), None)['statusCode'] == 403
        assert calls == []

    @patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED))
    @patch('resource_auth.get_execution_record', return_value=_exec_record())
    def test_human_with_forged_header_still_needs_team_access(self, *_):
        handler, calls = _protected(resolver=ra.execution_from_path, allow_worker=True)
        event = _req(path={'id': 'uc-1', 'executionId': 'ex-1'}, team_roles=[{'team_id': 'team-b', 'role': 'editor'}])
        event['headers'] = {'X-QA-Execution-Token': 'uc-1:ex-1:' + _TOKEN}
        with patch('resource_auth.list_shared_access', return_value=[]):
            assert handler(event, None)['statusCode'] == 403


class TestRequireOwnerTeamLead:
    def test_owner_team_lead_allowed(self):
        assert ra.require_owner_team_lead(_identity([{'team_id': 't1', 'role': 'team_lead'}]), 't1') is None

    def test_owner_editor_denied(self):
        assert ra.require_owner_team_lead(_identity([{'team_id': 't1', 'role': 'editor'}]), 't1')['statusCode'] == 403

    def test_other_team_lead_denied(self):
        assert ra.require_owner_team_lead(_identity([{'team_id': 't2', 'role': 'team_lead'}]), 't1')['statusCode'] == 403

    def test_orphan_admin_only(self):
        assert ra.require_owner_team_lead(_identity([{'team_id': 't1', 'role': 'team_lead'}]), None)['statusCode'] == 403
        assert ra.require_owner_team_lead(_identity(is_admin=True), None) is None


class TestRequireOAuthClientManager:
    RECORD = {'created_by': 'owner@example.com', 'team_id': 't1'}

    def _ident(self, identity='someone@example.com', team_roles=None, **kw):
        ident = _identity(team_roles, **kw)
        ident['identity'] = identity
        return ident

    def test_creator_allowed(self):
        assert ra.require_oauth_client_manager(self._ident('owner@example.com'), self.RECORD) is None

    def test_team_lead_of_client_team_allowed(self):
        assert ra.require_oauth_client_manager(
            self._ident(team_roles=[{'team_id': 't1', 'role': 'team_lead'}]), self.RECORD) is None

    def test_admin_allowed(self):
        assert ra.require_oauth_client_manager(self._ident(scopes=['api/admin']), self.RECORD) is None

    def test_editor_of_client_team_denied(self):
        resp = ra.require_oauth_client_manager(
            self._ident(team_roles=[{'team_id': 't1', 'role': 'editor'}]), self.RECORD)
        assert resp['statusCode'] == 403

    def test_team_lead_of_other_team_denied(self):
        resp = ra.require_oauth_client_manager(
            self._ident(team_roles=[{'team_id': 't2', 'role': 'team_lead'}]), self.RECORD)
        assert resp['statusCode'] == 403

    def test_unbound_client_only_creator_or_admin(self):
        record = {'created_by': 'owner@example.com'}
        assert ra.require_oauth_client_manager(
            self._ident(team_roles=[{'team_id': 't1', 'role': 'team_lead'}]), record)['statusCode'] == 403


class TestAuthorizeTargetApp:
    def _event(self, team_roles=None, is_admin=False):
        return _req(team_roles=team_roles, is_admin=is_admin, scope='api/usecases.write')

    @patch('resource_auth.list_shared_access', return_value=[])
    @patch('resource_auth.get_app_ownership', return_value={'owner_team_id': 'team-a'})
    def test_editor_of_owner_team_allowed(self, *_):
        owner, err = ra.authorize_target_app(self._event([{'team_id': 'team-a', 'role': 'editor'}]), 'app-1')
        assert (owner, err) == ('team-a', None)

    @patch('resource_auth.list_shared_access', return_value=[])
    @patch('resource_auth.get_app_ownership', return_value={'owner_team_id': 'team-a'})
    def test_other_team_denied(self, *_):
        owner, err = ra.authorize_target_app(self._event([{'team_id': 'team-b', 'role': 'editor'}]), 'app-1')
        assert owner is None and err['statusCode'] == 403

    @patch('resource_auth.get_app_ownership', return_value=None)
    def test_unknown_app_404(self, _):
        assert ra.authorize_target_app(self._event(is_admin=True), 'app-x')[1]['statusCode'] == 404

    def test_bad_id_400(self):
        assert ra.authorize_target_app(self._event(is_admin=True), '../x')[1]['statusCode'] == 400

    @patch('resource_auth.get_app_ownership', return_value={'owner_team_id': None})
    def test_orphan_app_admin_only(self, _):
        assert ra.authorize_target_app(self._event([{'team_id': 'team-a', 'role': 'editor'}]), 'app-1')[1]['statusCode'] == 403
        assert ra.authorize_target_app(self._event(is_admin=True), 'app-1') == (None, None)


class TestAuthorizeSession:
    """authorize_session: a wizard / recording session named outside the path."""

    def _event(self, team_roles=None, is_admin=False):
        return _req(team_roles=team_roles, is_admin=is_admin, scope='api/usecases.write')

    def _owned(self, execution=True, application_id='app-1'):
        return [
            patch('resource_auth.get_execution_record', return_value={'status': 'running'} if execution else None),
            patch('resource_auth.get_usecase_owner',
                  return_value={'application_id': application_id, 'owner_team_id': 'team-a'}),
            patch('resource_auth.list_shared_access', return_value=[]),
        ]

    def _call(self, event, usecase_id='uc-1', session_id='s-1', **owned):
        patches = self._owned(**owned)
        for p in patches:
            p.start()
        try:
            return ra.authorize_session(event, usecase_id, session_id, 'edit')
        finally:
            for p in patches:
                p.stop()

    def test_owner_editor_allowed(self):
        assert self._call(self._event([{'team_id': 'team-a', 'role': 'editor'}])) is None

    def test_owner_executor_denied(self):
        assert self._call(self._event([{'team_id': 'team-a', 'role': 'executor'}]))['statusCode'] == 403

    def test_other_team_denied(self):
        assert self._call(self._event([{'team_id': 'team-b', 'role': 'editor'}]))['statusCode'] == 403

    def test_session_not_under_usecase_404(self):
        assert self._call(self._event(is_admin=True), execution=False)['statusCode'] == 404

    @pytest.mark.parametrize('usecase_id,session_id', [('../x', 's-1'), ('uc-1', ''), ('', 's-1')])
    def test_bad_ids_400(self, usecase_id, session_id):
        assert self._call(self._event(is_admin=True), usecase_id, session_id)['statusCode'] == 400

    def test_orphan_usecase_admin_only(self):
        editor = self._event([{'team_id': 'team-a', 'role': 'editor'}])
        assert self._call(editor, application_id='')['statusCode'] == 403
        assert self._call(self._event(is_admin=True), application_id='') is None


class TestNewUsecaseOwnerFields:
    @patch('resource_auth.get_app_owner', return_value='team-a')
    def test_owned_app(self, _):
        assert ra.new_usecase_owner_fields('app-1') == {'application_id': 'app-1', 'owner_team_id': 'team-a'}

    @patch('resource_auth.get_app_owner', return_value=None)
    def test_orphan_app_has_no_owner(self, _):
        assert ra.new_usecase_owner_fields('app-1') == {'application_id': 'app-1'}


# ---------------------------------------------------------------------------
# Per-test-case override wiring (decision 12)
# ---------------------------------------------------------------------------


class TestOverrideInDecorator:
    """'view' of a use case resource also honours USECASE#{id}/OVERRIDE (404 when hidden)."""

    def _call(self, override, team_roles=None, action='view', is_admin=False, shares=None,
              identity_type='user', resolver=None, scope='api/usecases.read', path=None, headers=None):
        handler, calls = _protected(action=action, resolver=resolver, scopes=[scope],
                                    allow_worker=identity_type == 'worker')
        event = _req(path=path or {'id': 'uc-1'}, team_roles=team_roles, is_admin=is_admin,
                     scope=scope, identity_type=identity_type)
        if headers:
            event['headers'] = headers
        with patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED)), \
                patch('resource_auth.get_testcase_override', return_value=override) as lookup, \
                patch('resource_auth.list_shared_access', return_value=shares or []):
            resp = handler(event, None)
        return resp, calls, lookup

    def test_hidden_from_caller_404_before_handler(self):
        resp, calls, _ = self._call({'allowed_subs': ['someone-else']},
                                    [{'team_id': 'team-a', 'role': 'editor'}])
        assert resp['statusCode'] == 404 and calls == []

    def test_caller_in_allowed_subs_sees_it(self):
        resp, calls, _ = self._call({'allowed_subs': ['caller-sub']},
                                    [{'team_id': 'team-a', 'role': 'viewer'}])
        assert resp['statusCode'] == 200 and len(calls) == 1

    @pytest.mark.parametrize('role,status', [('viewer', 404), ('editor', 200), ('team_lead', 404)])
    def test_allowed_roles_matched_against_owner_team_role(self, role, status):
        resp, _, _ = self._call({'allowed_roles': ['editor']}, [{'team_id': 'team-a', 'role': role}])
        assert resp['statusCode'] == status

    def test_share_only_caller_hidden_by_role_override(self):
        shares = [{'app_id': 'app-1', 'target_team_id': 'team-b', 'level': 'full'}]
        resp, _, _ = self._call({'allowed_roles': ['editor']}, [{'team_id': 'team-b', 'role': 'editor'}],
                                shares=shares)
        assert resp['statusCode'] == 404

    def test_no_override_unchanged(self):
        resp, _, lookup = self._call(None, [{'team_id': 'team-a', 'role': 'viewer'}])
        assert resp['statusCode'] == 200
        lookup.assert_called_once_with('uc-1')

    def test_admin_bypasses_override(self):
        resp, _, lookup = self._call({'allowed_subs': ['x']}, is_admin=True, scope='api/admin')
        assert resp['statusCode'] == 200
        lookup.assert_not_called()

    def test_edit_is_not_narrowed_by_override(self):
        resp, _, lookup = self._call({'allowed_subs': ['x']}, [{'team_id': 'team-a', 'role': 'editor'}],
                                     action='edit', scope='api/usecases.write')
        assert resp['statusCode'] == 200
        lookup.assert_not_called()

    def test_lookup_error_hides(self):
        handler, calls = _protected()
        with patch('resource_auth.get_usecase_owner', return_value=dict(_UC_OWNED)), \
                patch('resource_auth.get_testcase_override', side_effect=Exception('ddb')):
            resp = handler(_req(path={'id': 'uc-1'}, team_roles=[{'team_id': 'team-a', 'role': 'viewer'}]), None)
        assert resp['statusCode'] == 404 and calls == []

    def test_execution_route_view_hidden(self):
        with patch('resource_auth.get_execution_record', return_value={'status': 'success'}):
            resp, calls, _ = self._call({'allowed_subs': ['x']}, [{'team_id': 'team-a', 'role': 'editor'}],
                                        resolver=ra.execution_from_path,
                                        path={'id': 'uc-1', 'executionId': 'ex-1'})
        assert resp['statusCode'] == 404 and calls == []

    def test_suite_view_not_checked(self):
        with patch('resource_auth.get_suite_owner', return_value=dict(_UC_OWNED)):
            resp, _, lookup = self._call({'allowed_subs': ['x']}, [{'team_id': 'team-a', 'role': 'viewer'}],
                                         resolver=ra.suite_from_path, path={'suite_id': 's-1'})
        assert resp['statusCode'] == 200
        lookup.assert_not_called()

    def test_worker_not_narrowed(self):
        token = 'tok'
        record = {'status': 'running', 'worker_token_hash': __import__('hashlib').sha256(token.encode()).hexdigest(),
                  'suite_id': None, 'suite_execution_id': None}
        with patch('resource_auth.get_execution_record', return_value=record):
            resp, _, lookup = self._call({'allowed_subs': ['x']}, identity_type='worker',
                                         headers={'X-QA-Execution-Token': f'uc-1:ex-1:{token}'})
        assert resp['statusCode'] == 200
        lookup.assert_not_called()


class TestCanViewTestcaseBatch:
    def _ident(self, team_roles=None, is_admin=False, sub='caller-sub'):
        return {'sub': sub, 'is_admin': is_admin, 'team_roles': team_roles or [], 'scopes': []}

    def test_admin_sees_all_without_lookup(self):
        with patch('resource_auth.batch_get_testcase_overrides') as batch:
            assert ra.can_view_testcase_batch(self._ident(is_admin=True), {'a': 't', 'b': None}) == {'a', 'b'}
        batch.assert_not_called()

    def test_empty_input(self):
        with patch('resource_auth.batch_get_testcase_overrides') as batch:
            assert ra.can_view_testcase_batch(self._ident(), {}) == set()
        batch.assert_not_called()

    def test_filters_by_override_with_one_batch_call(self):
        overrides = {
            'hidden-sub': {'allowed_subs': ['other']},
            'mine': {'allowed_subs': ['caller-sub']},
            'editors': {'allowed_roles': ['editor']},
            'viewers': {'allowed_roles': ['viewer']},
        }
        ident = self._ident([{'team_id': 'team-a', 'role': 'viewer'}, {'team_id': 'team-b', 'role': 'editor'}])
        owners = {'open': 'team-a', 'hidden-sub': 'team-a', 'mine': 'team-a',
                  'editors': 'team-b', 'viewers': 'team-b'}
        with patch('resource_auth.batch_get_testcase_overrides', return_value=overrides) as batch:
            visible = ra.can_view_testcase_batch(ident, owners)
        assert visible == {'open', 'mine', 'editors'}
        batch.assert_called_once()
        assert sorted(batch.call_args.args[0]) == sorted(owners)

    def test_share_only_caller_has_no_owner_role(self):
        ident = self._ident([{'team_id': 'team-b', 'role': 'editor'}])
        with patch('resource_auth.batch_get_testcase_overrides',
                   return_value={'tc': {'allowed_roles': ['editor']}}):
            assert ra.can_view_testcase_batch(ident, {'tc': 'team-a'}) == set()

    def test_lookup_error_hides_everything(self):
        with patch('resource_auth.batch_get_testcase_overrides', side_effect=RuntimeError('x')):
            assert ra.can_view_testcase_batch(self._ident([{'team_id': 't', 'role': 'editor'}]), {'a': 't'}) == set()

    def test_single_and_batch_agree(self):
        """can_view_testcase and can_view_testcase_batch share one rule (_override_allows)."""
        cases = [None, {'allowed_subs': ['caller-sub']}, {'allowed_subs': ['x']},
                 {'allowed_roles': ['editor']}, {'allowed_roles': ['viewer']},
                 {'allowed_subs': ['caller-sub'], 'allowed_roles': ['viewer']}]
        ident = self._ident([{'team_id': 'team-a', 'role': 'editor'}])
        for override in cases:
            with patch('resource_auth.get_testcase_override', return_value=override):
                single = ra.can_view_testcase(ident, 'tc', 'editor')
            with patch('resource_auth.batch_get_testcase_overrides',
                       return_value={'tc': override} if override else {}):
                batch = 'tc' in ra.can_view_testcase_batch(ident, {'tc': 'team-a'})
            assert single == batch, override
