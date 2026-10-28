"""Tests for the role_scopes module — single source of truth for role-to-scope mapping."""

import os
import sys
import pytest
from hypothesis import given, strategies as st

# Add the auth directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from role_scopes import (
    ROLES,
    TEAM_ROLES,
    ROLE_RANK,
    ACCESS_RANK,
    scopes_for_role,
    scopes_for_groups,
    parse_group,
    is_admin_group,
)


class TestRoleConstants:
    """Verify role constants are well-formed."""

    def test_five_roles_defined(self):
        assert len(ROLES) == 5

    def test_roles_ordered_highest_first(self):
        assert ROLES == ['admin', 'team_lead', 'editor', 'executor', 'viewer']

    def test_team_roles_exclude_admin(self):
        assert TEAM_ROLES == ('team_lead', 'editor', 'executor', 'viewer')
        assert 'admin' not in TEAM_ROLES

    def test_role_rank_covers_all_roles(self):
        for role in ROLES:
            assert role in ROLE_RANK

    def test_role_rank_ordering(self):
        assert ROLE_RANK['admin'] > ROLE_RANK['team_lead']
        assert ROLE_RANK['team_lead'] > ROLE_RANK['editor']
        assert ROLE_RANK['editor'] > ROLE_RANK['executor']
        assert ROLE_RANK['executor'] > ROLE_RANK['viewer']


class TestScopesForRole:
    """Unit tests for scopes_for_role."""

    def test_viewer_has_read_scopes(self):
        scopes = scopes_for_role('viewer')
        assert 'api/usecases.read' in scopes
        assert 'api/templates.read' in scopes
        assert 'api/executions.read' in scopes
        assert 'api/suite.read' in scopes
        assert 'api/applications.read' in scopes

    def test_viewer_has_no_write_scopes(self):
        scopes = scopes_for_role('viewer')
        assert 'api/usecases.write' not in scopes
        assert 'api/admin' not in scopes

    def test_executor_inherits_viewer(self):
        viewer_scopes = scopes_for_role('viewer')
        executor_scopes = scopes_for_role('executor')
        assert viewer_scopes.issubset(executor_scopes)
        assert 'api/usecases.execute' in executor_scopes
        assert 'api/executions.write' in executor_scopes

    def test_editor_inherits_executor(self):
        executor_scopes = scopes_for_role('executor')
        editor_scopes = scopes_for_role('editor')
        assert executor_scopes.issubset(editor_scopes)
        assert 'api/usecases.write' in editor_scopes
        assert 'api/templates.write' in editor_scopes

    def test_team_lead_inherits_editor(self):
        editor_scopes = scopes_for_role('editor')
        lead_scopes = scopes_for_role('team_lead')
        assert editor_scopes.issubset(lead_scopes)
        assert 'api/teams.manage' in lead_scopes

    def test_admin_inherits_all(self):
        lead_scopes = scopes_for_role('team_lead')
        admin_scopes = scopes_for_role('admin')
        assert lead_scopes.issubset(admin_scopes)
        assert 'api/admin' in admin_scopes

    def test_unknown_role_returns_empty(self):
        scopes = scopes_for_role('superuser')
        assert len(scopes) == 0

    def test_all_scopes_have_api_prefix(self):
        for role in ROLES:
            for scope in scopes_for_role(role):
                assert scope.startswith('api/'), f"{role}: {scope!r} missing prefix"


class TestParseGroup:
    """Unit tests for parse_group."""

    def test_legacy_users_group(self):
        result = parse_group('users')
        assert result is not None
        assert result['team_id'] is None
        assert result['role'] == 'editor'
        assert result['group_name'] == 'users'

    def test_legacy_admins_group(self):
        result = parse_group('admins')
        assert result is not None
        assert result['team_id'] is None
        assert result['role'] == 'admin'
        assert result['group_name'] == 'admins'

    def test_team_editor_group(self):
        result = parse_group('team-abc123-editor')
        assert result is not None
        assert result['team_id'] == 'abc123'
        assert result['role'] == 'editor'

    def test_team_viewer_group(self):
        result = parse_group('team-my-team-viewer')
        assert result is not None
        assert result['team_id'] == 'my-team'
        assert result['role'] == 'viewer'

    def test_team_admin_group_is_not_recognized(self):
        # Admin is studio-wide only; a team-scoped admin group must not parse.
        assert parse_group('team-platform-admin') is None
        assert parse_group('team-x-admin') is None

    def test_team_team_lead_group(self):
        result = parse_group('team-qa-team_lead')
        assert result is not None
        assert result['team_id'] == 'qa'
        assert result['role'] == 'team_lead'

    def test_invalid_group_returns_none(self):
        assert parse_group('random-group') is None

    def test_empty_string_returns_none(self):
        assert parse_group('') is None

    def test_team_group_invalid_role_returns_none(self):
        assert parse_group('team-abc-superuser') is None

    def test_whitespace_stripped(self):
        result = parse_group('  users  ')
        assert result is not None
        assert result['role'] == 'editor'


class TestIsAdminGroup:
    """Unit tests for is_admin_group."""

    def test_admins_is_admin(self):
        assert is_admin_group('admins') is True

    def test_team_admin_is_not_admin(self):
        assert is_admin_group('team-platform-admin') is False

    def test_team_lead_is_not_admin(self):
        assert is_admin_group('team-abc-team_lead') is False

    def test_admins_with_whitespace_is_admin(self):
        assert is_admin_group('  admins  ') is True

    def test_users_is_not_admin(self):
        assert is_admin_group('users') is False

    def test_team_editor_is_not_admin(self):
        assert is_admin_group('team-abc-editor') is False

    def test_unknown_group_is_not_admin(self):
        assert is_admin_group('unknown') is False


class TestScopesForGroups:
    """Unit tests for scopes_for_groups (the main entry point for resolving scopes)."""

    def test_single_legacy_users_group(self):
        scopes = scopes_for_groups(['users'])
        assert 'api/usecases.read' in scopes
        assert 'api/usecases.write' in scopes
        assert 'api/admin' not in scopes

    def test_single_legacy_admins_group(self):
        scopes = scopes_for_groups(['admins'])
        assert 'api/admin' in scopes
        assert 'api/usecases.read' in scopes

    def test_team_admin_group_grants_no_scopes(self):
        assert scopes_for_groups(['team-x-admin']) == set()

    def test_team_admin_group_adds_nothing_to_other_groups(self):
        assert scopes_for_groups(['team-x-admin', 'team-x-viewer']) == scopes_for_role('viewer')

    def test_team_editor_group(self):
        scopes = scopes_for_groups(['team-abc-editor'])
        assert 'api/usecases.write' in scopes
        assert 'api/admin' not in scopes

    def test_mixed_groups_returns_union(self):
        scopes = scopes_for_groups(['team-abc-viewer', 'team-xyz-editor'])
        # Should have editor scopes (superset of viewer)
        assert 'api/usecases.write' in scopes
        assert 'api/usecases.read' in scopes

    def test_empty_groups_returns_empty(self):
        scopes = scopes_for_groups([])
        assert len(scopes) == 0

    def test_unknown_groups_returns_empty(self):
        scopes = scopes_for_groups(['unknown-group', 'another-unknown'])
        assert len(scopes) == 0

    def test_admin_group_grants_all_scopes(self):
        admin_scopes = scopes_for_groups(['admins'])
        editor_scopes = scopes_for_groups(['users'])
        assert editor_scopes.issubset(admin_scopes)

    def test_multiple_team_memberships(self):
        scopes = scopes_for_groups([
            'team-alpha-viewer',
            'team-beta-executor',
            'team-gamma-team_lead',
        ])
        # Should have team_lead scopes (highest role)
        assert 'api/teams.manage' in scopes
        assert 'api/usecases.execute' in scopes
        assert 'api/usecases.read' in scopes


_team_ids = st.from_regex(r'[a-zA-Z0-9_-]{1,20}', fullmatch=True)
_role_suffixes = st.one_of(st.sampled_from(ROLES), st.from_regex(r'[a-z_]{1,12}', fullmatch=True))


class TestTeamGroupsNeverGrantAdmin:
    """Property: no team group, whatever its suffix, grants api/admin or admin status."""

    @given(team_id=_team_ids, role=_role_suffixes)
    def test_team_group_never_grants_admin(self, team_id, role):
        group = f'team-{team_id}-{role}'
        assert 'api/admin' not in scopes_for_groups([group])
        assert is_admin_group(group) is False
        parsed = parse_group(group)
        assert parsed is None or parsed['role'] in TEAM_ROLES
