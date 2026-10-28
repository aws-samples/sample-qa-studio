"""Tests for permissions_repo module using moto for DynamoDB mocking."""

import os
import sys
import json
import pytest
import boto3
from unittest.mock import MagicMock, patch
from moto import mock_aws

os.environ["TABLE_NAME"] = "test-table"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"


@pytest.fixture
def dynamodb_table():
    """Create a mock DynamoDB table with GSI1 and GSI2."""
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='test-table',
            KeySchema=[
                {'AttributeName': 'pk', 'KeyType': 'HASH'},
                {'AttributeName': 'sk', 'KeyType': 'RANGE'},
            ],
            AttributeDefinitions=[
                {'AttributeName': 'pk', 'AttributeType': 'S'},
                {'AttributeName': 'sk', 'AttributeType': 'S'},
                {'AttributeName': 'gsi1pk', 'AttributeType': 'S'},
                {'AttributeName': 'gsi1sk', 'AttributeType': 'S'},
                {'AttributeName': 'gsi2pk', 'AttributeType': 'S'},
                {'AttributeName': 'gsi2sk', 'AttributeType': 'S'},
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'user-teams-index',
                    'KeySchema': [
                        {'AttributeName': 'gsi1pk', 'KeyType': 'HASH'},
                        {'AttributeName': 'gsi1sk', 'KeyType': 'RANGE'},
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                },
                {
                    'IndexName': 'team-apps-index',
                    'KeySchema': [
                        {'AttributeName': 'gsi2pk', 'KeyType': 'HASH'},
                        {'AttributeName': 'gsi2sk', 'KeyType': 'RANGE'},
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                },
            ],
            BillingMode='PAY_PER_REQUEST',
        )
        table.meta.client.get_waiter('table_exists').wait(TableName='test-table')
        yield table


class TestCreateTeam:
    """Tests for create_team."""

    def test_creates_team_successfully(self, dynamodb_table):
        from permissions_repo import create_team

        result = create_team('Platform Team', 'user-sub-123')

        assert result['name'] == 'Platform Team'
        assert result['created_by'] == 'user-sub-123'
        assert 'id' in result
        assert result['pk'] == f"TEAM#{result['id']}"
        assert result['sk'] == 'METADATA'

    def test_creates_index_record(self, dynamodb_table):
        from permissions_repo import create_team

        result = create_team('QA Team', 'user-sub-456')
        team_id = result['id']

        # Verify index record exists
        response = dynamodb_table.get_item(
            Key={'pk': 'TEAMS', 'sk': f'TEAM#{team_id}'}
        )
        item = response.get('Item')
        assert item is not None
        assert item['name'] == 'QA Team'


class TestTeamNameExists:
    """Tests for team_name_exists."""

    def test_returns_false_when_no_teams(self, dynamodb_table):
        from permissions_repo import team_name_exists

        assert team_name_exists('Nonexistent') is False

    def test_returns_true_when_name_exists(self, dynamodb_table):
        from permissions_repo import create_team, team_name_exists

        create_team('Existing Team', 'user-sub-123')
        assert team_name_exists('Existing Team') is True

    def test_case_insensitive_match(self, dynamodb_table):
        from permissions_repo import create_team, team_name_exists

        create_team('My Team', 'user-sub-123')
        assert team_name_exists('my team') is True
        assert team_name_exists('MY TEAM') is True


class TestAddMembership:
    """Tests for add_membership."""

    def test_adds_membership(self, dynamodb_table):
        from permissions_repo import create_team, add_membership

        team = create_team('Team A', 'admin-sub')
        membership = add_membership(team['id'], 'user-sub-789', 'editor')

        assert membership['team_id'] == team['id']
        assert membership['user_sub'] == 'user-sub-789'
        assert membership['role'] == 'editor'
        assert 'added_at' in membership

    def test_membership_stored_with_gsi_keys(self, dynamodb_table):
        from permissions_repo import create_team, add_membership

        team = create_team('Team B', 'admin-sub')
        add_membership(team['id'], 'user-sub-111', 'viewer')

        response = dynamodb_table.get_item(
            Key={'pk': f"TEAM#{team['id']}", 'sk': 'MEMBER#user-sub-111'}
        )
        item = response.get('Item')
        assert item is not None
        assert item['gsi1pk'] == 'USER#user-sub-111'
        assert item['gsi1sk'] == f"TEAM#{team['id']}"


class TestListUserTeams:
    """Tests for list_user_teams."""

    def test_returns_empty_for_unassigned_user(self, dynamodb_table):
        from permissions_repo import list_user_teams

        result = list_user_teams('orphan-sub')
        assert result == []

    def test_returns_all_user_memberships(self, dynamodb_table):
        from permissions_repo import create_team, add_membership, list_user_teams

        team_a = create_team('Team A', 'admin-sub')
        team_b = create_team('Team B', 'admin-sub')
        add_membership(team_a['id'], 'multi-sub', 'editor')
        add_membership(team_b['id'], 'multi-sub', 'viewer')

        result = list_user_teams('multi-sub')
        assert len(result) == 2
        team_ids = [m['team_id'] for m in result]
        assert team_a['id'] in team_ids
        assert team_b['id'] in team_ids

    def test_does_not_return_other_users_memberships(self, dynamodb_table):
        from permissions_repo import create_team, add_membership, list_user_teams

        team = create_team('Shared Team', 'admin-sub')
        add_membership(team['id'], 'user-a', 'editor')
        add_membership(team['id'], 'user-b', 'viewer')

        result = list_user_teams('user-a')
        assert len(result) == 1
        assert result[0]['user_sub'] == 'user-a'


# ===========================================================================
# Team Operations — get_team, list_teams, update_team, delete_team
# ===========================================================================


class TestGetTeam:
    """Tests for get_team."""

    def test_returns_team_when_exists(self, dynamodb_table):
        from permissions_repo import create_team, get_team

        created = create_team('My Team', 'user-sub-1')
        result = get_team(created['id'])

        assert result is not None
        assert result['name'] == 'My Team'
        assert result['created_by'] == 'user-sub-1'
        assert result['id'] == created['id']

    def test_returns_none_when_not_found(self, dynamodb_table):
        from permissions_repo import get_team

        result = get_team('nonexistent-id')
        assert result is None


class TestListTeams:
    """Tests for list_teams."""

    def test_returns_empty_list_when_no_teams(self, dynamodb_table):
        from permissions_repo import list_teams

        result = list_teams()
        assert result == []

    def test_returns_all_teams(self, dynamodb_table):
        from permissions_repo import create_team, list_teams

        create_team('Team Alpha', 'user-1')
        create_team('Team Beta', 'user-2')
        create_team('Team Gamma', 'user-3')

        result = list_teams()
        assert len(result) == 3
        names = [t['name'] for t in result]
        assert 'Team Alpha' in names
        assert 'Team Beta' in names
        assert 'Team Gamma' in names


class TestUpdateTeam:
    """Tests for update_team."""

    def test_updates_name(self, dynamodb_table):
        from permissions_repo import create_team, update_team, get_team

        team = create_team('Original Name', 'user-1')
        result = update_team(team['id'], {'name': 'Updated Name'})

        assert result is not None
        assert result['name'] == 'Updated Name'

        # Verify via get_team
        fetched = get_team(team['id'])
        assert fetched['name'] == 'Updated Name'

    def test_returns_none_for_nonexistent_team(self, dynamodb_table):
        from permissions_repo import update_team

        result = update_team('nonexistent-id', {'name': 'New Name'})
        assert result is None

    def test_updates_multiple_fields(self, dynamodb_table):
        from permissions_repo import create_team, update_team

        team = create_team('Team X', 'user-1')
        result = update_team(team['id'], {'name': 'Team Y', 'description': 'A great team'})

        assert result['name'] == 'Team Y'
        assert result['description'] == 'A great team'

    def test_noop_with_empty_fields(self, dynamodb_table):
        from permissions_repo import create_team, update_team

        team = create_team('Unchanged', 'user-1')
        result = update_team(team['id'], {})

        assert result is not None
        assert result['name'] == 'Unchanged'


class TestDeleteTeam:
    """Tests for delete_team (full implementation)."""

    def test_deletes_team_metadata_and_index(self, dynamodb_table):
        from permissions_repo import create_team, delete_team, get_team, list_teams

        team = create_team('Doomed Team', 'user-1')
        result = delete_team(team['id'])

        assert result['deleted_members_count'] == 0
        assert result['orphaned_apps_count'] == 0

        # Verify team is gone
        assert get_team(team['id']) is None
        assert len(list_teams()) == 0

    def test_deletes_all_memberships(self, dynamodb_table):
        from permissions_repo import (
            create_team, add_membership, delete_team, list_team_members
        )

        team = create_team('Team with Members', 'admin-sub')
        add_membership(team['id'], 'user-a', 'editor')
        add_membership(team['id'], 'user-b', 'viewer')
        add_membership(team['id'], 'user-c', 'admin')

        result = delete_team(team['id'])
        assert result['deleted_members_count'] == 3

        # Verify memberships are gone
        members = list_team_members(team['id'])
        assert len(members) == 0

    def test_orphans_owned_apps(self, dynamodb_table):
        from permissions_repo import (
            create_team, delete_team, set_app_owner, get_app_owner
        )

        team = create_team('App Owner Team', 'admin-sub')

        # Create an app record and assign ownership
        dynamodb_table.put_item(Item={
            'pk': 'APPLICATION#app-1',
            'sk': 'METADATA',
            'id': 'app-1',
            'name': 'Test App',
        })
        set_app_owner('app-1', team['id'])

        result = delete_team(team['id'])
        assert result['orphaned_apps_count'] == 1

        # Verify app is orphaned
        owner = get_app_owner('app-1')
        assert owner is None


# ===========================================================================
# Membership Operations — remove_membership, set_member_role, list_team_members
# ===========================================================================


class TestRemoveMembership:
    """Tests for remove_membership."""

    def test_removes_membership(self, dynamodb_table):
        from permissions_repo import (
            create_team, add_membership, remove_membership, list_team_members
        )

        team = create_team('Team R', 'admin-sub')
        add_membership(team['id'], 'user-to-remove', 'editor')

        remove_membership('user-to-remove', team['id'])

        members = list_team_members(team['id'])
        assert len(members) == 0

    def test_idempotent_remove(self, dynamodb_table):
        from permissions_repo import create_team, remove_membership

        team = create_team('Team R2', 'admin-sub')
        # Remove non-existent membership — should not raise
        remove_membership('nonexistent-user', team['id'])


class TestSetMemberRole:
    """Tests for set_member_role."""

    def test_changes_role(self, dynamodb_table):
        from permissions_repo import create_team, add_membership, set_member_role

        team = create_team('Team Role', 'admin-sub')
        add_membership(team['id'], 'user-1', 'editor')

        result = set_member_role('user-1', team['id'], 'viewer')
        assert result['role'] == 'viewer'

    def test_noop_same_role(self, dynamodb_table):
        from permissions_repo import create_team, add_membership, set_member_role

        team = create_team('Team Noop', 'admin-sub')
        membership = add_membership(team['id'], 'user-1', 'editor')

        result = set_member_role('user-1', team['id'], 'editor')
        assert result['role'] == 'editor'

    def test_legacy_admin_membership_can_be_demoted(self, dynamodb_table):
        """Team 'admin' memberships are legacy (C-1); demoting one has no counter/guard."""
        from permissions_repo import create_team, add_membership, set_member_role

        team = create_team('Team Legacy', 'admin-sub')
        add_membership(team['id'], 'legacy-admin', 'admin')

        result = set_member_role('legacy-admin', team['id'], 'team_lead')
        assert result['role'] == 'team_lead'

    def test_raises_key_error_for_missing_membership(self, dynamodb_table):
        from permissions_repo import create_team, set_member_role

        team = create_team('Team Missing', 'admin-sub')

        with pytest.raises(KeyError):
            set_member_role('ghost-user', team['id'], 'editor')


class TestListTeamMembers:
    """Tests for list_team_members."""

    def test_returns_all_members(self, dynamodb_table):
        from permissions_repo import create_team, add_membership, list_team_members

        team = create_team('Team List', 'admin-sub')
        add_membership(team['id'], 'user-a', 'admin')
        add_membership(team['id'], 'user-b', 'editor')
        add_membership(team['id'], 'user-c', 'viewer')

        result = list_team_members(team['id'])
        assert len(result) == 3
        subs = [m['user_sub'] for m in result]
        assert 'user-a' in subs
        assert 'user-b' in subs
        assert 'user-c' in subs

    def test_returns_empty_for_no_members(self, dynamodb_table):
        from permissions_repo import create_team, list_team_members

        team = create_team('Empty Team', 'admin-sub')
        result = list_team_members(team['id'])
        assert result == []


class TestAdminCounterRemoved:
    """The ADMIN_COUNT/GLOBAL counter is gone; the guard uses the 'admins' group."""

    def test_counter_helpers_removed(self):
        import permissions_repo
        for name in ('count_admins', '_increment_admin_count',
                     '_decrement_admin_count', 'initialize_admin_count'):
            assert not hasattr(permissions_repo, name)

    def test_set_member_role_does_not_write_counter(self, dynamodb_table):
        from permissions_repo import create_team, add_membership, set_member_role

        team = create_team('Team Counter', 'admin-sub')
        add_membership(team['id'], 'u1', 'editor')
        set_member_role('u1', team['id'], 'viewer')

        assert 'Item' not in dynamodb_table.get_item(Key={'pk': 'ADMIN_COUNT', 'sk': 'GLOBAL'})


# ===========================================================================
# App Ownership — set_app_owner, get_app_owner, list_team_apps
# ===========================================================================


class TestSetAppOwner:
    """Tests for set_app_owner."""

    def test_sets_owner_and_gsi2_keys(self, dynamodb_table):
        from permissions_repo import set_app_owner

        # Create an application record
        dynamodb_table.put_item(Item={
            'pk': 'APPLICATION#app-100',
            'sk': 'METADATA',
            'id': 'app-100',
            'name': 'My App',
        })

        result = set_app_owner('app-100', 'team-xyz')
        assert result['owner_team_id'] == 'team-xyz'
        assert result['gsi2pk'] == 'OWNERTEAM#team-xyz'
        assert result['gsi2sk'] == 'APP#app-100'


class TestGetAppOwner:
    """Tests for get_app_owner."""

    def test_returns_owner_team_id(self, dynamodb_table):
        from permissions_repo import set_app_owner, get_app_owner

        dynamodb_table.put_item(Item={
            'pk': 'APPLICATION#app-200',
            'sk': 'METADATA',
            'id': 'app-200',
            'name': 'Owned App',
        })
        set_app_owner('app-200', 'team-owner')

        result = get_app_owner('app-200')
        assert result == 'team-owner'

    def test_returns_none_when_app_not_found(self, dynamodb_table):
        from permissions_repo import get_app_owner

        result = get_app_owner('nonexistent-app')
        assert result is None

    def test_returns_none_when_no_owner_set(self, dynamodb_table):
        from permissions_repo import get_app_owner

        dynamodb_table.put_item(Item={
            'pk': 'APPLICATION#app-no-owner',
            'sk': 'METADATA',
            'id': 'app-no-owner',
            'name': 'Unowned App',
        })

        result = get_app_owner('app-no-owner')
        assert result is None


class TestListTeamApps:
    """Tests for list_team_apps via GSI2."""

    def test_returns_apps_owned_by_team(self, dynamodb_table):
        from permissions_repo import set_app_owner, list_team_apps

        # Create multiple apps and assign them to the same team
        for app_id in ['app-a', 'app-b', 'app-c']:
            dynamodb_table.put_item(Item={
                'pk': f'APPLICATION#{app_id}',
                'sk': 'METADATA',
                'id': app_id,
                'name': f'App {app_id}',
            })
            set_app_owner(app_id, 'team-multi')

        result = list_team_apps('team-multi')
        assert len(result) == 3

    def test_returns_empty_for_team_with_no_apps(self, dynamodb_table):
        from permissions_repo import list_team_apps

        result = list_team_apps('team-no-apps')
        assert result == []

    def test_does_not_return_other_teams_apps(self, dynamodb_table):
        from permissions_repo import set_app_owner, list_team_apps

        dynamodb_table.put_item(Item={
            'pk': 'APPLICATION#app-x',
            'sk': 'METADATA',
            'id': 'app-x',
            'name': 'App X',
        })
        dynamodb_table.put_item(Item={
            'pk': 'APPLICATION#app-y',
            'sk': 'METADATA',
            'id': 'app-y',
            'name': 'App Y',
        })
        set_app_owner('app-x', 'team-one')
        set_app_owner('app-y', 'team-two')

        result = list_team_apps('team-one')
        assert len(result) == 1
        assert result[0]['gsi2sk'] == 'APP#app-x'


# ===========================================================================
# Shared Access — grant, revoke, list outgoing, list incoming
# ===========================================================================


class TestGrantSharedAccess:
    """Tests for grant_shared_access."""

    def test_creates_grant_record(self, dynamodb_table):
        from permissions_repo import grant_shared_access

        result = grant_shared_access('team-owner', 'team-target', 'app-1', 'view', 'actor-sub')

        assert result['owner_team_id'] == 'team-owner'
        assert result['target_team_id'] == 'team-target'
        assert result['app_id'] == 'app-1'
        assert result['level'] == 'view'
        assert result['granted_by'] == 'actor-sub'
        assert 'grant_id' in result
        assert 'granted_at' in result
        assert result['gsi2pk'] == 'SHAREDWITH#team-target'

    def test_rejects_self_share(self, dynamodb_table):
        from permissions_repo import grant_shared_access

        with pytest.raises(ValueError, match="Cannot share an application with its own team"):
            grant_shared_access('team-same', 'team-same', 'app-1', 'full', 'actor')

    def test_overwrites_existing_grant(self, dynamodb_table):
        from permissions_repo import grant_shared_access, list_shared_access

        grant_shared_access('team-o', 'team-t', 'app-1', 'view', 'actor')
        grant_shared_access('team-o', 'team-t', 'app-1', 'full', 'actor')

        # Should only be one grant (overwritten)
        grants = list_shared_access('team-o')
        assert len(grants) == 1
        assert grants[0]['level'] == 'full'


class TestRevokeSharedAccess:
    """Tests for revoke_shared_access."""

    def test_removes_grant(self, dynamodb_table):
        from permissions_repo import (
            grant_shared_access, revoke_shared_access, list_shared_access
        )

        grant_shared_access('team-o', 'team-t', 'app-1', 'execute', 'actor')
        revoke_shared_access('team-o', 'team-t', 'app-1')

        grants = list_shared_access('team-o')
        assert len(grants) == 0

    def test_idempotent_revoke(self, dynamodb_table):
        from permissions_repo import revoke_shared_access

        # Should not raise even if item doesn't exist
        revoke_shared_access('team-o', 'team-t', 'app-nonexistent')


class TestListSharedAccess:
    """Tests for list_shared_access (outgoing)."""

    def test_returns_all_outgoing_grants(self, dynamodb_table):
        from permissions_repo import grant_shared_access, list_shared_access

        grant_shared_access('team-o', 'team-a', 'app-1', 'view', 'actor')
        grant_shared_access('team-o', 'team-b', 'app-2', 'execute', 'actor')
        grant_shared_access('team-o', 'team-c', 'app-1', 'full', 'actor')

        result = list_shared_access('team-o')
        assert len(result) == 3

    def test_returns_empty_when_no_shares(self, dynamodb_table):
        from permissions_repo import list_shared_access

        result = list_shared_access('team-no-shares')
        assert result == []


class TestListAppsSharedWithTeam:
    """Tests for list_apps_shared_with_team (incoming via GSI2)."""

    def test_returns_grants_targeting_team(self, dynamodb_table):
        from permissions_repo import grant_shared_access, list_apps_shared_with_team

        grant_shared_access('team-o1', 'team-target', 'app-1', 'view', 'actor')
        grant_shared_access('team-o2', 'team-target', 'app-2', 'execute', 'actor')

        result = list_apps_shared_with_team('team-target')
        assert len(result) == 2
        app_ids = [r['app_id'] for r in result]
        assert 'app-1' in app_ids
        assert 'app-2' in app_ids

    def test_does_not_return_grants_for_other_teams(self, dynamodb_table):
        from permissions_repo import grant_shared_access, list_apps_shared_with_team

        grant_shared_access('team-o', 'team-a', 'app-1', 'view', 'actor')
        grant_shared_access('team-o', 'team-b', 'app-2', 'view', 'actor')

        result = list_apps_shared_with_team('team-a')
        assert len(result) == 1
        assert result[0]['app_id'] == 'app-1'

    def test_returns_empty_when_nothing_shared(self, dynamodb_table):
        from permissions_repo import list_apps_shared_with_team

        result = list_apps_shared_with_team('team-lonely')
        assert result == []


# ===========================================================================
# Test Case Overrides — put, get
# ===========================================================================


class TestPutTestcaseOverride:
    """Tests for put_testcase_override."""

    def test_creates_override(self, dynamodb_table):
        from permissions_repo import put_testcase_override

        override = {
            'allowed_subs': ['user-a', 'user-b'],
            'allowed_roles': ['admin'],
            'created_by': 'admin-sub',
        }
        result = put_testcase_override('tc-123', override)

        assert result['testcase_id'] == 'tc-123'
        assert result['allowed_subs'] == ['user-a', 'user-b']
        assert result['allowed_roles'] == ['admin']
        assert result['created_by'] == 'admin-sub'
        assert 'created_at' in result

    def test_overwrites_existing_override(self, dynamodb_table):
        from permissions_repo import put_testcase_override, get_testcase_override

        put_testcase_override('tc-456', {
            'allowed_subs': ['user-a'],
            'allowed_roles': ['editor'],
        })
        put_testcase_override('tc-456', {
            'allowed_subs': ['user-b', 'user-c'],
            'allowed_roles': ['admin', 'editor'],
        })

        result = get_testcase_override('tc-456')
        assert result['allowed_subs'] == ['user-b', 'user-c']
        assert result['allowed_roles'] == ['admin', 'editor']


class TestGetTestcaseOverride:
    """Tests for get_testcase_override."""

    def test_returns_override_when_exists(self, dynamodb_table):
        from permissions_repo import put_testcase_override, get_testcase_override

        put_testcase_override('tc-789', {
            'allowed_subs': ['user-x'],
            'allowed_roles': [],
            'created_by': 'creator-sub',
        })

        result = get_testcase_override('tc-789')
        assert result is not None
        assert result['allowed_subs'] == ['user-x']

    def test_returns_none_when_not_found(self, dynamodb_table):
        from permissions_repo import get_testcase_override

        result = get_testcase_override('nonexistent-tc')
        assert result is None


# ---------------------------------------------------------------------------
# Owner readers (H-2 resolvers)
# ---------------------------------------------------------------------------


class TestOwnerReaders:
    def test_usecase_owner(self, dynamodb_table):
        from permissions_repo import get_usecase_owner
        dynamodb_table.put_item(Item={'pk': 'USECASES', 'sk': 'USECASE#uc-1', 'application_id': 'app-1',
                                      'owner_team_id': 'team-a', 'name': 'secret-ish', 'starting_url': 'x'})
        dynamodb_table.put_item(Item={'pk': 'USECASE#uc-1', 'sk': 'CREATED_BY', 'sub': 'creator', 'email': 'e'})
        assert get_usecase_owner('uc-1') == {'application_id': 'app-1', 'owner_team_id': 'team-a', 'created_by': None}
        assert get_usecase_owner('uc-1', include_creator=True)['created_by'] == 'creator'

    def test_usecase_owner_missing_and_orphan(self, dynamodb_table):
        from permissions_repo import get_usecase_owner
        assert get_usecase_owner('nope') is None
        dynamodb_table.put_item(Item={'pk': 'USECASES', 'sk': 'USECASE#uc-2', 'application_id': ''})
        assert get_usecase_owner('uc-2', include_creator=True) == {
            'application_id': None, 'owner_team_id': None, 'created_by': None}

    def test_suite_owner(self, dynamodb_table):
        from permissions_repo import get_suite_owner
        assert get_suite_owner('s-1') is None
        dynamodb_table.put_item(Item={'pk': 'TEST_SUITES', 'sk': 'SUITE#s-1', 'application_id': 'app-1'})
        assert get_suite_owner('s-1') == {'application_id': 'app-1', 'owner_team_id': None}

    def test_execution_record_keyed_by_usecase(self, dynamodb_table):
        from permissions_repo import get_execution_record
        dynamodb_table.put_item(Item={'pk': 'USECASE_EXECUTION#uc-1', 'sk': 'EXECUTION#ex-1',
                                      'status': 'running', 'worker_token_hash': 'h', 'suite_id': 's-1',
                                      'starting_url': 'x'})
        assert get_execution_record('uc-1', 'ex-1') == {
            'status': 'running', 'worker_token_hash': 'h', 'suite_id': 's-1', 'suite_execution_id': None}
        assert get_execution_record('uc-other', 'ex-1') is None

    def test_suite_execution_record(self, dynamodb_table):
        from permissions_repo import get_suite_execution_record
        dynamodb_table.put_item(Item={'pk': 'SUITE_EXECUTION#s-1', 'sk': 'EXECUTION#sx-1', 'status': 'pending'})
        assert get_suite_execution_record('s-1', 'sx-1') == {'status': 'pending'}
        assert get_suite_execution_record('s-2', 'sx-1') is None

    def test_app_ownership(self, dynamodb_table):
        from permissions_repo import get_app_ownership
        assert get_app_ownership('nope') is None
        dynamodb_table.put_item(Item={'pk': 'APPLICATION#a-1', 'sk': 'METADATA', 'name': 'A'})
        assert get_app_ownership('a-1') == {'owner_team_id': None}


class TestBatchGetTestcaseOverrides:
    """batch_get_testcase_overrides: BatchGetItem on USECASE#{id}/OVERRIDE (BR-3 lists)."""

    def test_returns_only_existing_overrides(self, dynamodb_table):
        from permissions_repo import put_testcase_override, batch_get_testcase_overrides
        put_testcase_override('tc-1', {'allowed_subs': ['s1']})
        put_testcase_override('tc-3', {'allowed_roles': ['editor']})
        result = batch_get_testcase_overrides(['tc-1', 'tc-2', 'tc-3', 'tc-1'])
        assert set(result) == {'tc-1', 'tc-3'}
        assert result['tc-1']['allowed_subs'] == ['s1']
        assert result['tc-3']['allowed_roles'] == ['editor']

    def test_more_than_100_ids_are_chunked(self, dynamodb_table):
        from permissions_repo import put_testcase_override, batch_get_testcase_overrides
        ids = [f'tc-{i}' for i in range(250)]
        for tc in ids[::50]:
            put_testcase_override(tc, {'allowed_subs': ['s']})
        result = batch_get_testcase_overrides(ids)
        assert set(result) == set(ids[::50])

    def test_chunk_size_never_exceeds_100(self):
        from permissions_repo import batch_get_testcase_overrides
        fake = MagicMock()
        fake.batch_get_item.return_value = {'Responses': {'test-table': []}}
        with patch('permissions_repo.boto3.resource', return_value=fake):
            batch_get_testcase_overrides([f'tc-{i}' for i in range(201)])
        sizes = [len(c.kwargs['RequestItems']['test-table']['Keys']) for c in fake.batch_get_item.call_args_list]
        assert sizes == [100, 100, 1]

    def test_empty_input_makes_no_call(self):
        from permissions_repo import batch_get_testcase_overrides
        with patch('permissions_repo.boto3.resource') as resource:
            assert batch_get_testcase_overrides([]) == {}
        resource.assert_not_called()

    def test_unprocessed_keys_retried(self):
        from permissions_repo import batch_get_testcase_overrides
        fake = MagicMock()
        unprocessed = {'test-table': {'Keys': [{'pk': 'USECASE#tc-2', 'sk': 'OVERRIDE'}]}}
        fake.batch_get_item.side_effect = [
            {'Responses': {'test-table': [{'pk': 'USECASE#tc-1', 'sk': 'OVERRIDE'}]}, 'UnprocessedKeys': unprocessed},
            {'Responses': {'test-table': [{'pk': 'USECASE#tc-2', 'sk': 'OVERRIDE'}]}, 'UnprocessedKeys': {}},
        ]
        with patch('permissions_repo.boto3.resource', return_value=fake):
            result = batch_get_testcase_overrides(['tc-1', 'tc-2'])
        assert set(result) == {'tc-1', 'tc-2'}
        assert fake.batch_get_item.call_args_list[1].kwargs['RequestItems'] == unprocessed

    def test_still_unprocessed_after_retries_raises(self):
        from permissions_repo import batch_get_testcase_overrides
        fake = MagicMock()
        unprocessed = {'test-table': {'Keys': [{'pk': 'USECASE#tc-1', 'sk': 'OVERRIDE'}]}}
        fake.batch_get_item.return_value = {'Responses': {}, 'UnprocessedKeys': unprocessed}
        with patch('permissions_repo.boto3.resource', return_value=fake):
            with pytest.raises(RuntimeError):
                batch_get_testcase_overrides(['tc-1'])
