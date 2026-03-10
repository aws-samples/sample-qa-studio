"""Tests for client_credentials, token_file_provider, and resolver."""

import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from qa_studio_cli.models.errors import AuthError
from qa_studio_cli.models.config import CLIConfig


# ---------------------------------------------------------------------------
# ClientCredentialsProvider
# ---------------------------------------------------------------------------


class TestClientCredentialsProvider:
    """Tests for the OAuth client-credentials provider."""

    def test_requests_token_on_first_call(self):
        from qa_studio_cli.auth.client_credentials import ClientCredentialsProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-token",
            "expires_in": 3600,
        }

        with patch("qa_studio_cli.auth.client_credentials.requests.post", return_value=mock_response) as mock_post:
            provider = ClientCredentialsProvider("cid", "csecret", "https://auth.example.com/token")
            token = provider.get_token()

        assert token == "new-token"
        mock_post.assert_called_once()

    def test_caches_token_on_second_call(self):
        from qa_studio_cli.auth.client_credentials import ClientCredentialsProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "cached-token",
            "expires_in": 3600,
        }

        with patch("qa_studio_cli.auth.client_credentials.requests.post", return_value=mock_response) as mock_post:
            provider = ClientCredentialsProvider("cid", "csecret", "https://auth.example.com/token")
            token1 = provider.get_token()
            token2 = provider.get_token()

        assert token1 == token2 == "cached-token"
        assert mock_post.call_count == 1  # Only one HTTP call

    def test_refreshes_expired_token(self):
        from qa_studio_cli.auth.client_credentials import ClientCredentialsProvider
        from datetime import timezone

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "fresh-token",
            "expires_in": 3600,
        }

        with patch("qa_studio_cli.auth.client_credentials.requests.post", return_value=mock_response):
            provider = ClientCredentialsProvider("cid", "csecret", "https://auth.example.com/token")
            provider.get_token()
            # Force expiry
            provider._expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            token = provider.get_token()

        assert token == "fresh-token"

    def test_raises_auth_error_on_401(self):
        from qa_studio_cli.auth.client_credentials import ClientCredentialsProvider

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "invalid_client"

        with patch("qa_studio_cli.auth.client_credentials.requests.post", return_value=mock_response):
            provider = ClientCredentialsProvider("bad", "creds", "https://auth.example.com/token")
            with pytest.raises(AuthError, match="401"):
                provider.get_token()

    def test_raises_auth_error_on_network_failure(self):
        from qa_studio_cli.auth.client_credentials import ClientCredentialsProvider
        import requests as req

        with patch("qa_studio_cli.auth.client_credentials.requests.post", side_effect=req.ConnectionError("timeout")):
            provider = ClientCredentialsProvider("cid", "csecret", "https://auth.example.com/token")
            with pytest.raises(AuthError, match="token request failed"):
                provider.get_token()


# ---------------------------------------------------------------------------
# TokenFileProvider
# ---------------------------------------------------------------------------


class TestTokenFileProvider:
    """Tests for the token file provider."""

    def test_reads_valid_token_file(self, tmp_path):
        from qa_studio_cli.auth.token_file_provider import TokenFileProvider

        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"access_token": "file-token"}))

        provider = TokenFileProvider(str(token_file))
        assert provider.get_token() == "file-token"

    def test_raises_on_missing_file(self, tmp_path):
        from qa_studio_cli.auth.token_file_provider import TokenFileProvider

        with pytest.raises(AuthError, match="not found"):
            TokenFileProvider(str(tmp_path / "nonexistent.json"))

    def test_raises_on_invalid_json(self, tmp_path):
        from qa_studio_cli.auth.token_file_provider import TokenFileProvider

        token_file = tmp_path / "token.json"
        token_file.write_text("not json")

        with pytest.raises(AuthError, match="parse"):
            TokenFileProvider(str(token_file))

    def test_raises_on_missing_access_token_field(self, tmp_path):
        from qa_studio_cli.auth.token_file_provider import TokenFileProvider

        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"refresh_token": "only-refresh"}))

        with pytest.raises(AuthError, match="access_token"):
            TokenFileProvider(str(token_file))

    def test_rereads_on_each_call(self, tmp_path):
        from qa_studio_cli.auth.token_file_provider import TokenFileProvider

        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"access_token": "token-v1"}))

        provider = TokenFileProvider(str(token_file))
        assert provider.get_token() == "token-v1"

        # Overwrite with new token
        token_file.write_text(json.dumps({"access_token": "token-v2"}))
        assert provider.get_token() == "token-v2"

    def test_rejects_non_string_access_token(self, tmp_path):
        from qa_studio_cli.auth.token_file_provider import TokenFileProvider

        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"access_token": 12345}))

        with pytest.raises(AuthError, match="access_token"):
            TokenFileProvider(str(token_file))


# ---------------------------------------------------------------------------
# TokenResolver
# ---------------------------------------------------------------------------


class TestTokenResolver:
    """Tests for the token resolution chain."""

    def test_priority_1_token_file(self, tmp_path):
        from qa_studio_cli.auth.resolver import TokenResolver

        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"access_token": "file-token"}))

        resolver = TokenResolver(token_file=str(token_file))
        assert resolver.get_token() == "file-token"

    def test_priority_2_env_vars(self):
        from qa_studio_cli.auth.resolver import TokenResolver

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "env-token", "expires_in": 3600}

        env = {
            "OAUTH_CLIENT_ID": "env-cid",
            "OAUTH_CLIENT_SECRET": "env-secret",
            "OAUTH_TOKEN_ENDPOINT": "https://auth.example.com/token",
        }
        with patch.dict(os.environ, env, clear=False), \
             patch("qa_studio_cli.auth.client_credentials.requests.post", return_value=mock_response):
            resolver = TokenResolver()
            assert resolver.get_token() == "env-token"

    def test_priority_3_config_m2m(self):
        from qa_studio_cli.auth.resolver import TokenResolver

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "config-token", "expires_in": 3600}

        config = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="pub-client",
            oauth_client_id="m2m-cid",
            oauth_client_secret="m2m-secret",
            oauth_token_endpoint="https://auth.example.com/oauth2/token",
        )
        # Ensure no env vars interfere
        env_clear = {"OAUTH_CLIENT_ID": "", "OAUTH_CLIENT_SECRET": "", "OAUTH_TOKEN_ENDPOINT": ""}
        with patch.dict(os.environ, env_clear, clear=False), \
             patch("qa_studio_cli.auth.client_credentials.requests.post", return_value=mock_response):
            resolver = TokenResolver(config=config)
            assert resolver.get_token() == "config-token"

    def test_priority_4_stored_user_token(self):
        from qa_studio_cli.auth.resolver import TokenResolver

        env_clear = {"OAUTH_CLIENT_ID": "", "OAUTH_CLIENT_SECRET": "", "OAUTH_TOKEN_ENDPOINT": ""}
        with patch.dict(os.environ, env_clear, clear=False), \
             patch("qa_studio_cli.auth.token_manager.get_valid_token", return_value="user-token"):
            resolver = TokenResolver()
            assert resolver.get_token() == "user-token"

    def test_raises_when_all_sources_exhausted(self):
        from qa_studio_cli.auth.resolver import TokenResolver

        env_clear = {"OAUTH_CLIENT_ID": "", "OAUTH_CLIENT_SECRET": "", "OAUTH_TOKEN_ENDPOINT": ""}
        with patch.dict(os.environ, env_clear, clear=False), \
             patch("qa_studio_cli.auth.token_manager.get_valid_token", side_effect=AuthError("no token")):
            resolver = TokenResolver()
            with pytest.raises(AuthError, match="No authentication source"):
                resolver.get_token()

    def test_token_file_takes_priority_over_env_vars(self, tmp_path):
        from qa_studio_cli.auth.resolver import TokenResolver

        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"access_token": "file-wins"}))

        env = {
            "OAUTH_CLIENT_ID": "env-cid",
            "OAUTH_CLIENT_SECRET": "env-secret",
            "OAUTH_TOKEN_ENDPOINT": "https://auth.example.com/token",
        }
        with patch.dict(os.environ, env, clear=False):
            resolver = TokenResolver(token_file=str(token_file))
            assert resolver.get_token() == "file-wins"

    def test_env_vars_take_priority_over_config_m2m(self):
        from qa_studio_cli.auth.resolver import TokenResolver

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "env-wins", "expires_in": 3600}

        config = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="pub-client",
            oauth_client_id="config-cid",
            oauth_client_secret="config-secret",
            oauth_token_endpoint="https://auth.example.com/oauth2/token",
        )
        env = {
            "OAUTH_CLIENT_ID": "env-cid",
            "OAUTH_CLIENT_SECRET": "env-secret",
            "OAUTH_TOKEN_ENDPOINT": "https://auth.example.com/token",
        }
        with patch.dict(os.environ, env, clear=False), \
             patch("qa_studio_cli.auth.client_credentials.requests.post", return_value=mock_response):
            resolver = TokenResolver(config=config)
            # Should use env vars, not config
            assert resolver.get_token() == "env-wins"

    def test_incomplete_env_vars_fall_through_to_config(self):
        from qa_studio_cli.auth.resolver import TokenResolver

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "config-wins", "expires_in": 3600}

        config = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="pub-client",
            oauth_client_id="m2m-cid",
            oauth_client_secret="m2m-secret",
            oauth_token_endpoint="https://auth.example.com/oauth2/token",
        )
        # Only partial env vars — should fall through
        env = {"OAUTH_CLIENT_ID": "env-cid", "OAUTH_CLIENT_SECRET": "", "OAUTH_TOKEN_ENDPOINT": ""}
        with patch.dict(os.environ, env, clear=False), \
             patch("qa_studio_cli.auth.client_credentials.requests.post", return_value=mock_response):
            resolver = TokenResolver(config=config)
            assert resolver.get_token() == "config-wins"
