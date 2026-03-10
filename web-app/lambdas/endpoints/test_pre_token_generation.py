"""Tests for the pre-token generation Lambda trigger (V2)."""

import copy
import json
import sys
import os
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Add the auth directory to the path so we can import the handler
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'auth'))

from pre_token_generation import handler, SCOPE_MAPPINGS


def make_event(groups=None, user_attributes=None, username="testuser"):
    """Build a minimal Cognito pre-token-generation V2 event."""
    event = {
        "userName": username,
        "triggerSource": "TokenGeneration_HostedAuth",
        "request": {
            "groupConfiguration": {
                "groupsToOverride": groups or [],
            },
            "userAttributes": user_attributes or {},
        },
        "response": {},
    }
    return event


class TestScopeMappings:
    """Verify the SCOPE_MAPPINGS constant is well-formed."""

    def test_users_group_exists(self):
        assert "users" in SCOPE_MAPPINGS

    def test_admins_group_exists(self):
        assert "admins" in SCOPE_MAPPINGS

    def test_admins_is_superset_of_users(self):
        assert set(SCOPE_MAPPINGS["users"]).issubset(set(SCOPE_MAPPINGS["admins"]))

    def test_admin_scope_only_in_admins(self):
        assert "api/admin" in SCOPE_MAPPINGS["admins"]
        assert "api/admin" not in SCOPE_MAPPINGS["users"]

    def test_all_scopes_have_api_prefix(self):
        for group, scopes in SCOPE_MAPPINGS.items():
            for scope in scopes:
                assert scope.startswith("api/"), f"{group}: {scope!r} missing 'api/' prefix"


class TestIdTokenScopeInjection:
    """Verify scopes are injected into the ID token."""

    def test_users_group_injects_scopes_into_id_token(self):
        event = make_event(groups=["users"])
        result = handler(event, None)

        id_claims = result["response"]["claimsAndScopeOverrideDetails"]["idTokenGeneration"]["claimsToAddOrOverride"]
        scope_string = id_claims["scope"]
        for s in SCOPE_MAPPINGS["users"]:
            assert s in scope_string

    def test_admins_group_injects_admin_scope_into_id_token(self):
        event = make_event(groups=["admins"])
        result = handler(event, None)

        id_claims = result["response"]["claimsAndScopeOverrideDetails"]["idTokenGeneration"]["claimsToAddOrOverride"]
        assert "api/admin" in id_claims["scope"]

    def test_no_groups_produces_empty_scope_in_id_token(self):
        event = make_event(groups=[])
        result = handler(event, None)

        id_claims = result["response"]["claimsAndScopeOverrideDetails"]["idTokenGeneration"]["claimsToAddOrOverride"]
        assert id_claims["scope"] == ""


class TestAccessTokenScopeInjection:
    """Verify scopes are injected into the access token."""

    def test_users_group_adds_scopes_to_access_token(self):
        event = make_event(groups=["users"])
        result = handler(event, None)

        access_token = result["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]
        # Check scopesToAdd list
        scopes_to_add = access_token["scopesToAdd"]
        for s in SCOPE_MAPPINGS["users"]:
            assert s in scopes_to_add

    def test_admins_group_adds_admin_to_access_token_scopes(self):
        event = make_event(groups=["admins"])
        result = handler(event, None)

        scopes_to_add = result["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["scopesToAdd"]
        assert "api/admin" in scopes_to_add

    def test_no_groups_produces_empty_scopes_to_add(self):
        event = make_event(groups=[])
        result = handler(event, None)

        scopes_to_add = result["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["scopesToAdd"]
        assert scopes_to_add == []

    def test_custom_scopes_claim_added_to_access_token(self):
        event = make_event(groups=["users"])
        result = handler(event, None)

        access_claims = result["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["claimsToAddOrOverride"]
        assert "custom_scopes" in access_claims
        for s in SCOPE_MAPPINGS["users"]:
            assert s in access_claims["custom_scopes"]


class TestGroupFallback:
    """Verify fallback to userAttributes when groupConfiguration is empty."""

    def test_falls_back_to_user_attributes_cognito_groups(self):
        event = make_event(
            groups=[],
            user_attributes={"cognito:groups": "users"},
        )
        result = handler(event, None)

        scopes_to_add = result["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["scopesToAdd"]
        for s in SCOPE_MAPPINGS["users"]:
            assert s in scopes_to_add

    def test_unknown_group_produces_no_scopes(self):
        event = make_event(groups=["unknown-group"])
        result = handler(event, None)

        scopes_to_add = result["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["scopesToAdd"]
        assert scopes_to_add == []


class TestMultipleGroups:
    """Verify scope union when user belongs to multiple groups."""

    def test_users_and_admins_produces_union(self):
        event = make_event(groups=["users", "admins"])
        result = handler(event, None)

        scopes_to_add = result["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["scopesToAdd"]
        # Should have admin scope (from admins) and all user scopes
        assert "api/admin" in scopes_to_add
        for s in SCOPE_MAPPINGS["users"]:
            assert s in scopes_to_add


class TestErrorHandling:
    """Verify the handler doesn't crash on malformed events."""

    def test_missing_request_key_returns_event(self):
        event = {"userName": "test", "response": {}}
        # Should not raise — returns event unchanged on error
        result = handler(event, None)
        assert result is not None

    def test_none_response_field_is_handled(self):
        event = make_event(groups=["users"])
        event["response"] = None
        result = handler(event, None)
        # Should still inject scopes
        scopes_to_add = result["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["scopesToAdd"]
        assert len(scopes_to_add) > 0


class TestPropertyBased:
    """Property-based tests for scope injection consistency."""

    @given(st.lists(st.sampled_from(["users", "admins", "unknown"]), min_size=0, max_size=3))
    @settings(max_examples=20)
    def test_scopes_are_always_subset_of_defined_mappings(self, groups):
        """All injected scopes should come from SCOPE_MAPPINGS."""
        event = make_event(groups=groups)
        result = handler(event, None)

        scopes_to_add = set(result["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["scopesToAdd"])
        all_defined = set()
        for mapping_scopes in SCOPE_MAPPINGS.values():
            all_defined.update(mapping_scopes)

        assert scopes_to_add.issubset(all_defined)

    @given(st.lists(st.sampled_from(["users", "admins", "unknown"]), min_size=0, max_size=3))
    @settings(max_examples=20)
    def test_id_and_access_token_scopes_are_consistent(self, groups):
        """ID token scope string and access token scopesToAdd should contain the same scopes."""
        event = make_event(groups=groups)
        result = handler(event, None)

        id_scope_string = result["response"]["claimsAndScopeOverrideDetails"]["idTokenGeneration"]["claimsToAddOrOverride"]["scope"]
        id_scopes = set(id_scope_string.split()) if id_scope_string else set()

        access_scopes = set(result["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["scopesToAdd"])

        assert id_scopes == access_scopes
