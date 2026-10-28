"""
Tests for extract_user_identity edge cases (auth hardening — Bolt 3a).

Covers:
- Missing teamRoles key → defaults to []
- Malformed JSON in teamRoles → defaults to []
- Missing isAdmin → defaults to False
- Various identity_type fallback paths
"""

import json
import os
import sys
import pytest

# Ensure the endpoints directory is on the path
sys.path.insert(0, os.path.dirname(__file__))

from utils import extract_user_identity


def _make_event(authorizer_context: dict) -> dict:
    """Build an API Gateway event with the given authorizer context."""
    return {
        'requestContext': {
            'authorizer': authorizer_context,
        }
    }


class TestExtractUserIdentityTeamRoles:
    """Edge cases for teamRoles parsing in extract_user_identity."""

    def test_missing_team_roles_key_defaults_to_empty_list(self):
        """If teamRoles key is absent, team_roles defaults to []."""
        event = _make_event({
            'sub': 'user-sub',
            'email': 'user@example.com',
            'identityType': 'user',
            'scope': 'api/usecases.read',
            # No 'teamRoles' key
            'isAdmin': 'false',
        })

        identity = extract_user_identity(event)
        assert identity['team_roles'] == []

    def test_malformed_json_in_team_roles_defaults_to_empty_list(self):
        """If teamRoles contains invalid JSON, team_roles defaults to []."""
        event = _make_event({
            'sub': 'user-sub',
            'email': 'user@example.com',
            'identityType': 'user',
            'scope': 'api/usecases.read',
            'teamRoles': 'not valid json{[',
            'isAdmin': 'false',
        })

        identity = extract_user_identity(event)
        assert identity['team_roles'] == []

    def test_team_roles_with_empty_string_defaults_to_empty_list(self):
        """If teamRoles is an empty string, team_roles defaults to []."""
        event = _make_event({
            'sub': 'user-sub',
            'email': 'user@example.com',
            'identityType': 'user',
            'scope': 'api/usecases.read',
            'teamRoles': '',
            'isAdmin': 'false',
        })

        identity = extract_user_identity(event)
        assert identity['team_roles'] == []

    def test_valid_team_roles_parsed_correctly(self):
        """Valid teamRoles JSON is parsed into list of dicts."""
        team_roles = [
            {'team_id': 'alpha', 'role': 'editor', 'group_name': 'team-alpha-editor'},
            {'team_id': 'beta', 'role': 'viewer', 'group_name': 'team-beta-viewer'},
        ]
        event = _make_event({
            'sub': 'user-sub',
            'email': 'user@example.com',
            'identityType': 'user',
            'scope': 'api/usecases.read',
            'teamRoles': json.dumps(team_roles),
            'isAdmin': 'false',
        })

        identity = extract_user_identity(event)
        assert identity['team_roles'] == team_roles

    def test_team_roles_none_value_defaults_to_empty_list(self):
        """If teamRoles value is None (null), team_roles defaults to []."""
        event = _make_event({
            'sub': 'user-sub',
            'email': 'user@example.com',
            'identityType': 'user',
            'scope': 'api/usecases.read',
            'teamRoles': None,
            'isAdmin': 'false',
        })

        identity = extract_user_identity(event)
        assert identity['team_roles'] == []


class TestExtractUserIdentityIsAdmin:
    """Edge cases for isAdmin parsing in extract_user_identity."""

    def test_missing_is_admin_defaults_to_false(self):
        """If isAdmin key is absent, is_admin defaults to False."""
        event = _make_event({
            'sub': 'user-sub',
            'email': 'user@example.com',
            'identityType': 'user',
            'scope': 'api/usecases.read',
            'teamRoles': '[]',
            # No 'isAdmin' key
        })

        identity = extract_user_identity(event)
        assert identity['is_admin'] is False

    def test_is_admin_true_string_returns_true(self):
        """isAdmin = 'true' returns True."""
        event = _make_event({
            'sub': 'admin-sub',
            'email': 'admin@example.com',
            'identityType': 'user',
            'scope': 'api/admin',
            'teamRoles': '[]',
            'isAdmin': 'true',
        })

        identity = extract_user_identity(event)
        assert identity['is_admin'] is True

    def test_is_admin_false_string_returns_false(self):
        """isAdmin = 'false' returns False."""
        event = _make_event({
            'sub': 'user-sub',
            'email': 'user@example.com',
            'identityType': 'user',
            'scope': 'api/usecases.read',
            'teamRoles': '[]',
            'isAdmin': 'false',
        })

        identity = extract_user_identity(event)
        assert identity['is_admin'] is False

    def test_is_admin_non_string_defaults_to_false(self):
        """isAdmin with non-'true' value returns False."""
        event = _make_event({
            'sub': 'user-sub',
            'email': 'user@example.com',
            'identityType': 'user',
            'scope': 'api/usecases.read',
            'teamRoles': '[]',
            'isAdmin': 'yes',  # Not exactly 'true'
        })

        identity = extract_user_identity(event)
        assert identity['is_admin'] is False


class TestExtractUserIdentityFallback:
    """Tests for identity type detection fallback paths."""

    def test_client_identity_type_returns_client(self):
        """Explicit identityType='client' returns client identity."""
        event = _make_event({
            'sub': 'client-sub',
            'clientId': 'my-client-id',
            'identityType': 'client',
            'scope': 'api/executions.write',
        })

        identity = extract_user_identity(event)
        assert identity['identity_type'] == 'client'
        assert identity['client_id'] == 'my-client-id'

    def test_fallback_client_detection_no_email_no_username(self):
        """If no email/username but client_id present → client type (fallback)."""
        event = _make_event({
            'sub': 'client-sub',
            'client_id': 'my-client-id',
            'scope': 'api/executions.write',
            # No identityType, no email, no username
        })

        identity = extract_user_identity(event)
        assert identity['identity_type'] == 'client'

    def test_unknown_identity_type_when_no_info(self):
        """If no email, no username, no client_id → unknown."""
        event = _make_event({
            'sub': 'some-sub',
            'scope': '',
        })

        identity = extract_user_identity(event)
        assert identity['identity_type'] == 'unknown'


class TestM2MIdentityTeamBinding:
    """Client and worker identities (H-2 M2M binding)."""

    def test_client_carries_team_binding_and_is_never_admin(self):
        identity = extract_user_identity(_make_event({
            'clientId': 'ci-client', 'identityType': 'client', 'scope': 'api/usecases.read',
            'teamRoles': json.dumps([{'team_id': 'team-a', 'role': 'editor'}]),
            'isAdmin': 'true',
        }))
        assert identity['identity_type'] == 'client'
        assert identity['team_roles'] == [{'team_id': 'team-a', 'role': 'editor'}]
        assert identity['is_admin'] is False

    def test_unbound_client_has_no_team_roles(self):
        identity = extract_user_identity(_make_event({'clientId': 'c', 'identityType': 'client', 'scope': ''}))
        assert identity['team_roles'] == [] and identity['is_admin'] is False

    def test_fallback_client_carries_team_binding(self):
        identity = extract_user_identity(_make_event({
            'client_id': 'c', 'scope': 'api/usecases.read',
            'teamRoles': json.dumps([{'team_id': 'team-a', 'role': 'viewer'}]),
        }))
        assert identity['identity_type'] == 'client'
        assert identity['team_roles'] == [{'team_id': 'team-a', 'role': 'viewer'}]
        assert identity['is_admin'] is False

    def test_worker_identity_ignores_team_roles(self):
        identity = extract_user_identity(_make_event({
            'clientId': 'worker-client', 'identityType': 'worker', 'scope': 'api/executions.write',
            'teamRoles': json.dumps([{'team_id': 'team-a', 'role': 'editor'}]), 'isAdmin': 'true',
        }))
        assert identity['identity_type'] == 'worker'
        assert identity['client_id'] == 'worker-client'
        assert identity['team_roles'] == [] and identity['is_admin'] is False
