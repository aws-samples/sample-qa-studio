"""Tests for the Lambda authorizer — specifically group-to-scope resolution."""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Add the auth directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from authorizer import (
    GROUP_SCOPE_MAPPINGS,
    resolve_scopes_from_groups,
    handler,
    generate_policy,
)


class TestGroupScopeMappings:
    """Verify GROUP_SCOPE_MAPPINGS is well-formed and in sync with pre_token_generation."""

    def test_users_group_exists(self):
        assert "users" in GROUP_SCOPE_MAPPINGS

    def test_admins_group_exists(self):
        assert "admins" in GROUP_SCOPE_MAPPINGS

    def test_admins_is_superset_of_users(self):
        assert set(GROUP_SCOPE_MAPPINGS["users"]).issubset(
            set(GROUP_SCOPE_MAPPINGS["admins"])
        )

    def test_admin_scope_only_in_admins(self):
        assert "api/admin" in GROUP_SCOPE_MAPPINGS["admins"]
        assert "api/admin" not in GROUP_SCOPE_MAPPINGS["users"]

    def test_suite_scopes_present_for_users(self):
        assert "api/suite.read" in GROUP_SCOPE_MAPPINGS["users"]
        assert "api/suite.write" in GROUP_SCOPE_MAPPINGS["users"]

    def test_all_scopes_have_api_prefix(self):
        for group, scopes in GROUP_SCOPE_MAPPINGS.items():
            for scope in scopes:
                assert scope.startswith("api/"), f"{group}: {scope!r} missing prefix"


class TestResolveScopesFromGroups:
    """Unit tests for resolve_scopes_from_groups."""

    def test_users_group_returns_user_scopes(self):
        scopes = resolve_scopes_from_groups(["users"])
        assert "api/usecases.read" in scopes
        assert "api/usecases.write" in scopes
        assert "api/admin" not in scopes

    def test_admins_group_returns_admin_scope(self):
        scopes = resolve_scopes_from_groups(["admins"])
        assert "api/admin" in scopes

    def test_both_groups_returns_union(self):
        scopes = resolve_scopes_from_groups(["users", "admins"])
        assert "api/admin" in scopes
        assert "api/usecases.read" in scopes

    def test_unknown_group_returns_empty(self):
        scopes = resolve_scopes_from_groups(["unknown-group"])
        assert len(scopes) == 0

    def test_empty_groups_returns_empty(self):
        scopes = resolve_scopes_from_groups([])
        assert len(scopes) == 0

    def test_whitespace_group_name_is_stripped(self):
        scopes = resolve_scopes_from_groups(["  users  "])
        assert "api/usecases.read" in scopes


def _make_access_token_claims(
    email=None, username=None, client_id=None, sub="sub-123",
    scope="openid profile email", groups=None
):
    """Build a dict mimicking decoded Cognito access token claims."""
    claims = {
        "token_use": "access",
        "sub": sub,
        "scope": scope,
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_test",
        "exp": 9999999999,
        "iat": 1000000000,
    }
    if email:
        claims["email"] = email
    if username:
        claims["username"] = username
    if client_id:
        claims["client_id"] = client_id
    if groups is not None:
        claims["cognito:groups"] = groups
    return claims


class TestHandlerGroupScopeResolution:
    """Integration tests: handler resolves scopes from cognito:groups for user tokens."""

    @patch("authorizer.decode_and_verify_token")
    def test_user_token_with_groups_gets_api_scopes(self, mock_decode):
        mock_decode.return_value = _make_access_token_claims(
            email="user@example.com",
            groups=["users"],
        )
        event = {
            "authorizationToken": "Bearer fake-token",
            "methodArn": "arn:aws:execute-api:us-east-1:123:api/stage/GET/resource",
        }
        os.environ["USER_POOL_ID"] = "us-east-1_test"

        result = handler(event, None)

        context = result["context"]
        assert context["identityType"] == "user"
        assert "api/usecases.read" in context["scope"]
        assert "api/usecases.write" in context["scope"]

    @patch("authorizer.decode_and_verify_token")
    def test_user_token_with_admins_group_gets_admin_scope(self, mock_decode):
        mock_decode.return_value = _make_access_token_claims(
            email="admin@example.com",
            groups=["admins"],
        )
        event = {
            "authorizationToken": "Bearer fake-token",
            "methodArn": "arn:aws:execute-api:us-east-1:123:api/stage/GET/resource",
        }
        os.environ["USER_POOL_ID"] = "us-east-1_test"

        result = handler(event, None)
        assert "api/admin" in result["context"]["scope"]

    @patch("authorizer.decode_and_verify_token")
    def test_user_token_without_groups_keeps_original_scope(self, mock_decode):
        mock_decode.return_value = _make_access_token_claims(
            email="user@example.com",
            groups=[],
        )
        event = {
            "authorizationToken": "Bearer fake-token",
            "methodArn": "arn:aws:execute-api:us-east-1:123:api/stage/GET/resource",
        }
        os.environ["USER_POOL_ID"] = "us-east-1_test"

        result = handler(event, None)
        # Should still have the original OIDC scopes
        assert "openid" in result["context"]["scope"]
        # Should NOT have API scopes
        assert "api/usecases.read" not in result["context"]["scope"]

    @patch("authorizer.decode_and_verify_token")
    def test_m2m_token_does_not_resolve_groups(self, mock_decode):
        """M2M tokens already have scopes in the scope claim — don't override."""
        mock_decode.return_value = _make_access_token_claims(
            client_id="m2m-client-id",
            scope="api/usecases.read api/executions.write",
        )
        event = {
            "authorizationToken": "Bearer fake-token",
            "methodArn": "arn:aws:execute-api:us-east-1:123:api/stage/GET/resource",
        }
        os.environ["USER_POOL_ID"] = "us-east-1_test"

        result = handler(event, None)
        # M2M token scopes should be passed through as-is
        assert "api/usecases.read" in result["context"]["scope"]
        assert "api/executions.write" in result["context"]["scope"]
        # Should NOT have group-derived scopes (no groups on M2M tokens)
        assert "api/admin" not in result["context"]["scope"]

    @patch("authorizer.decode_and_verify_token")
    def test_merged_scopes_include_both_original_and_group_derived(self, mock_decode):
        """If the access token already has some scopes, group scopes are merged."""
        mock_decode.return_value = _make_access_token_claims(
            email="user@example.com",
            scope="openid profile email",
            groups=["users"],
        )
        event = {
            "authorizationToken": "Bearer fake-token",
            "methodArn": "arn:aws:execute-api:us-east-1:123:api/stage/GET/resource",
        }
        os.environ["USER_POOL_ID"] = "us-east-1_test"

        result = handler(event, None)
        scope_str = result["context"]["scope"]
        # Original OIDC scopes preserved
        assert "openid" in scope_str
        assert "profile" in scope_str
        # Group-derived API scopes added
        assert "api/usecases.read" in scope_str


class TestGeneratePolicy:
    """Tests for the generate_policy helper."""

    def test_allow_policy_structure(self):
        policy = generate_policy("user@test.com", "Allow", "arn:aws:execute-api:us-east-1:123:api/stage/GET/resource")
        assert policy["principalId"] == "user@test.com"
        stmt = policy["policyDocument"]["Statement"][0]
        assert stmt["Effect"] == "Allow"

    def test_context_is_included(self):
        policy = generate_policy("user@test.com", "Allow", "arn:aws:execute-api:us-east-1:123:api/stage/GET/resource", context={"scope": "api/usecases.read"})
        assert policy["context"]["scope"] == "api/usecases.read"

    def test_wildcard_resource(self):
        policy = generate_policy("user@test.com", "Allow", "arn:aws:execute-api:us-east-1:123:api/stage/GET/resource")
        resource = policy["policyDocument"]["Statement"][0]["Resource"]
        assert resource.endswith("/*/*")
