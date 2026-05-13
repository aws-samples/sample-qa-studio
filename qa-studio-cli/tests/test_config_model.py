"""Tests for the extended CLIConfig model with M2M fields."""

import pytest
from pydantic import ValidationError

from qa_studio_cli.models.config import CLIConfig


class TestCLIConfigM2MFields:
    """Tests for optional M2M OAuth fields on CLIConfig."""

    def test_core_fields_only(self):
        config = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="my-client",
        )
        assert config.oauth_client_id is None
        assert config.oauth_client_secret is None
        assert config.oauth_token_endpoint is None

    def test_with_m2m_fields(self):
        config = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="my-client",
            oauth_client_id="m2m-client",
            oauth_client_secret="m2m-secret",
            oauth_token_endpoint="https://auth.example.com/oauth2/token",
        )
        assert config.oauth_client_id == "m2m-client"
        assert config.oauth_client_secret == "m2m-secret"
        assert config.oauth_token_endpoint == "https://auth.example.com/oauth2/token"

    def test_partial_m2m_fields(self):
        """Only some M2M fields set — valid, resolver handles completeness check."""
        config = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="my-client",
            oauth_client_id="m2m-client",
        )
        assert config.oauth_client_id == "m2m-client"
        assert config.oauth_client_secret is None

    def test_oauth_token_endpoint_rejects_http(self):
        with pytest.raises(ValidationError, match="https://"):
            CLIConfig(
                api_url="https://api.example.com",
                cognito_domain="https://auth.example.com",
                client_id="my-client",
                oauth_token_endpoint="http://insecure.com/token",
            )

    def test_oauth_token_endpoint_accepts_none(self):
        config = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="my-client",
            oauth_token_endpoint=None,
        )
        assert config.oauth_token_endpoint is None

    def test_round_trip_serialization_with_m2m(self):
        original = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="my-client",
            oauth_client_id="m2m-id",
            oauth_client_secret="m2m-secret",
            oauth_token_endpoint="https://auth.example.com/oauth2/token",
        )
        json_str = original.model_dump_json()
        restored = CLIConfig.model_validate_json(json_str)
        assert restored == original

    def test_round_trip_serialization_without_m2m(self):
        original = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="my-client",
        )
        json_str = original.model_dump_json()
        restored = CLIConfig.model_validate_json(json_str)
        assert restored == original

    def test_api_url_rejects_http(self):
        with pytest.raises(ValidationError):
            CLIConfig(
                api_url="http://insecure.com",
                cognito_domain="https://auth.example.com",
                client_id="my-client",
            )

    def test_cognito_domain_rejects_http(self):
        with pytest.raises(ValidationError):
            CLIConfig(
                api_url="https://api.example.com",
                cognito_domain="http://insecure.com",
                client_id="my-client",
            )

    def test_trailing_slashes_stripped(self):
        config = CLIConfig(
            api_url="https://api.example.com///",
            cognito_domain="https://auth.example.com/",
            client_id="my-client",
        )
        assert config.api_url == "https://api.example.com"
        assert config.cognito_domain == "https://auth.example.com"

    def test_empty_client_id_rejected(self):
        with pytest.raises(ValidationError):
            CLIConfig(
                api_url="https://api.example.com",
                cognito_domain="https://auth.example.com",
                client_id="",
            )


class TestCLIConfigWebUrl:
    """Tests for the optional web_url field used by the TUI."""

    def test_web_url_defaults_to_none(self):
        config = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="my-client",
        )
        assert config.web_url is None

    def test_web_url_accepts_https(self):
        config = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="my-client",
            web_url="https://app.example.com",
        )
        assert config.web_url == "https://app.example.com"

    def test_web_url_strips_trailing_slash(self):
        config = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="my-client",
            web_url="https://app.example.com/",
        )
        assert config.web_url == "https://app.example.com"

    def test_web_url_rejects_http(self):
        with pytest.raises(ValidationError, match="https://"):
            CLIConfig(
                api_url="https://api.example.com",
                cognito_domain="https://auth.example.com",
                client_id="my-client",
                web_url="http://insecure.example.com",
            )

    def test_web_url_none_roundtrips(self):
        config = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="my-client",
            web_url=None,
        )
        assert config.web_url is None
