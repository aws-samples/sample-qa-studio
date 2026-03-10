"""Tests for the OAuth authorization code grant with PKCE module."""

import base64
import hashlib
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from qa_studio_cli.auth.oauth import (
    API_SCOPES,
    CALLBACK_PORT,
    CALLBACK_PATH,
    generate_pkce_pair,
    exchange_code_for_tokens,
    start_oauth_flow,
)
from qa_studio_cli.models.errors import AuthError


class TestApiScopes:
    """Verify the API_SCOPES constant matches the CDK auth stack."""

    def test_api_scopes_is_non_empty(self):
        assert len(API_SCOPES) > 0

    def test_all_scopes_have_api_prefix(self):
        for scope in API_SCOPES:
            assert scope.startswith("api/"), f"Scope {scope!r} missing 'api/' prefix"

    def test_usecases_read_scope_present(self):
        assert "api/usecases.read" in API_SCOPES

    def test_usecases_write_scope_present(self):
        assert "api/usecases.write" in API_SCOPES

    def test_suite_read_scope_present(self):
        assert "api/suite.read" in API_SCOPES

    def test_suite_write_scope_present(self):
        assert "api/suite.write" in API_SCOPES

    def test_no_admin_scope_in_default_list(self):
        """Admin scope should NOT be requested by default — it's granted via group membership."""
        assert "api/admin" not in API_SCOPES


class TestGeneratePkcePair:
    """Tests for PKCE code_verifier / code_challenge generation."""

    def test_returns_tuple_of_two_strings(self):
        verifier, challenge = generate_pkce_pair()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)

    def test_verifier_and_challenge_differ(self):
        verifier, challenge = generate_pkce_pair()
        assert verifier != challenge

    def test_challenge_is_s256_of_verifier(self):
        verifier, challenge = generate_pkce_pair()
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        assert challenge == expected

    @given(st.integers(min_value=1, max_value=5))
    @settings(max_examples=5)
    def test_each_call_produces_unique_pair(self, _n):
        """Property: successive calls never produce the same verifier."""
        v1, _ = generate_pkce_pair()
        v2, _ = generate_pkce_pair()
        assert v1 != v2


class TestExchangeCodeForTokens:
    """Tests for the authorization code → token exchange."""

    @patch("qa_studio_cli.auth.oauth.requests.post")
    def test_successful_exchange(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "access_token": "at-123",
                "refresh_token": "rt-456",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )
        token = exchange_code_for_tokens(
            code="auth-code",
            code_verifier="verifier",
            cognito_domain="https://auth.example.com",
            client_id="client-1",
        )
        assert token.access_token == "at-123"
        assert token.refresh_token == "rt-456"
        assert token.token_type == "Bearer"

    @patch("qa_studio_cli.auth.oauth.requests.post")
    def test_failed_exchange_raises_auth_error(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=400,
            text="invalid_grant",
        )
        with pytest.raises(AuthError, match="Token exchange failed"):
            exchange_code_for_tokens(
                code="bad-code",
                code_verifier="verifier",
                cognito_domain="https://auth.example.com",
                client_id="client-1",
            )


class TestStartOauthFlowScopeParameter:
    """Verify that start_oauth_flow builds the authorize URL with API scopes."""

    @patch("qa_studio_cli.auth.oauth.webbrowser.open")
    @patch("qa_studio_cli.auth.oauth.HTTPServer")
    def test_authorize_url_includes_api_scopes(self, mock_server_cls, mock_browser):
        """The authorize URL must request API scopes, not just openid/profile/email."""
        # Make the server thread return immediately with no code (will timeout)
        mock_server = MagicMock()
        mock_server_cls.return_value = mock_server

        # Capture the URL passed to webbrowser.open
        captured_url = {}

        def capture_url(url):
            captured_url["url"] = url

        mock_browser.side_effect = capture_url

        # The flow will timeout because no callback arrives, but we can still
        # inspect the authorize URL that was opened.
        with pytest.raises(AuthError, match="timed out"):
            start_oauth_flow(
                cognito_domain="https://auth.example.com",
                client_id="test-client",
            )

        url = captured_url.get("url", "")
        # Verify API scopes are in the URL
        assert "api%2Fusecases.read" in url or "api/usecases.read" in url
        assert "api%2Fusecases.write" in url or "api/usecases.write" in url
        assert "api%2Fsuite.read" in url or "api/suite.read" in url
        # Verify standard OIDC scopes are still present
        assert "openid" in url
        assert "profile" in url
        assert "email" in url

    @patch("qa_studio_cli.auth.oauth.webbrowser.open")
    @patch("qa_studio_cli.auth.oauth.HTTPServer")
    def test_authorize_url_does_not_include_admin_scope(self, mock_server_cls, mock_browser):
        mock_server = MagicMock()
        mock_server_cls.return_value = mock_server

        captured_url = {}
        mock_browser.side_effect = lambda url: captured_url.update({"url": url})

        with pytest.raises(AuthError, match="timed out"):
            start_oauth_flow(
                cognito_domain="https://auth.example.com",
                client_id="test-client",
            )

        url = captured_url.get("url", "")
        assert "api%2Fadmin" not in url and "api/admin" not in url

    @patch("qa_studio_cli.auth.oauth.HTTPServer")
    def test_port_in_use_raises_auth_error(self, mock_server_cls):
        mock_server_cls.side_effect = OSError("Address already in use")
        with pytest.raises(AuthError, match="Port 19847"):
            start_oauth_flow(
                cognito_domain="https://auth.example.com",
                client_id="test-client",
            )
