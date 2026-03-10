"""Tests for the config manager with M2M field support."""

import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from qa_studio_cli.config.manager import (
    save_config,
    load_config,
    config_exists,
    CONFIG_FILE,
    QA_STUDIO_DIR,
)
from qa_studio_cli.models.config import CLIConfig
from qa_studio_cli.models.errors import ConfigError


class TestSaveConfig:
    """Tests for save_config with M2M fields."""

    def test_saves_core_fields(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("qa_studio_cli.config.manager.CONFIG_FILE", config_file), \
             patch("qa_studio_cli.config.manager.QA_STUDIO_DIR", tmp_path):
            config = CLIConfig(
                api_url="https://api.example.com",
                cognito_domain="https://auth.example.com",
                client_id="test-client",
            )
            save_config(config)

        data = json.loads(config_file.read_text())
        assert data["api_url"] == "https://api.example.com"
        assert data["cognito_domain"] == "https://auth.example.com"
        assert data["client_id"] == "test-client"

    def test_excludes_none_m2m_fields(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("qa_studio_cli.config.manager.CONFIG_FILE", config_file), \
             patch("qa_studio_cli.config.manager.QA_STUDIO_DIR", tmp_path):
            config = CLIConfig(
                api_url="https://api.example.com",
                cognito_domain="https://auth.example.com",
                client_id="test-client",
            )
            save_config(config)

        data = json.loads(config_file.read_text())
        assert "oauth_client_id" not in data
        assert "oauth_client_secret" not in data
        assert "oauth_token_endpoint" not in data

    def test_includes_m2m_fields_when_set(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("qa_studio_cli.config.manager.CONFIG_FILE", config_file), \
             patch("qa_studio_cli.config.manager.QA_STUDIO_DIR", tmp_path):
            config = CLIConfig(
                api_url="https://api.example.com",
                cognito_domain="https://auth.example.com",
                client_id="test-client",
                oauth_client_id="m2m-id",
                oauth_client_secret="m2m-secret",
                oauth_token_endpoint="https://auth.example.com/oauth2/token",
            )
            save_config(config)

        data = json.loads(config_file.read_text())
        assert data["oauth_client_id"] == "m2m-id"
        assert data["oauth_client_secret"] == "m2m-secret"
        assert data["oauth_token_endpoint"] == "https://auth.example.com/oauth2/token"

    def test_file_permissions_0600(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("qa_studio_cli.config.manager.CONFIG_FILE", config_file), \
             patch("qa_studio_cli.config.manager.QA_STUDIO_DIR", tmp_path):
            config = CLIConfig(
                api_url="https://api.example.com",
                cognito_domain="https://auth.example.com",
                client_id="test-client",
            )
            save_config(config)

        mode = stat.S_IMODE(os.stat(config_file).st_mode)
        assert mode == 0o600


class TestLoadConfig:
    """Tests for load_config with M2M env var overlay."""

    def test_loads_core_fields_from_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "api_url": "https://api.example.com",
            "cognito_domain": "https://auth.example.com",
            "client_id": "test-client",
        }))
        with patch("qa_studio_cli.config.manager.CONFIG_FILE", config_file):
            config = load_config()
        assert config.api_url == "https://api.example.com"
        assert config.oauth_client_id is None

    def test_loads_m2m_fields_from_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "api_url": "https://api.example.com",
            "cognito_domain": "https://auth.example.com",
            "client_id": "test-client",
            "oauth_client_id": "m2m-id",
            "oauth_client_secret": "m2m-secret",
            "oauth_token_endpoint": "https://auth.example.com/oauth2/token",
        }))
        with patch("qa_studio_cli.config.manager.CONFIG_FILE", config_file):
            config = load_config()
        assert config.oauth_client_id == "m2m-id"
        assert config.oauth_client_secret == "m2m-secret"
        assert config.oauth_token_endpoint == "https://auth.example.com/oauth2/token"

    def test_env_vars_override_m2m_fields(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "api_url": "https://api.example.com",
            "cognito_domain": "https://auth.example.com",
            "client_id": "test-client",
            "oauth_client_id": "file-id",
        }))
        env = {
            "OAUTH_CLIENT_ID": "env-id",
            "OAUTH_CLIENT_SECRET": "env-secret",
            "OAUTH_TOKEN_ENDPOINT": "https://env-auth.example.com/token",
        }
        with patch("qa_studio_cli.config.manager.CONFIG_FILE", config_file), \
             patch.dict(os.environ, env, clear=False):
            config = load_config()
        assert config.oauth_client_id == "env-id"
        assert config.oauth_client_secret == "env-secret"
        assert config.oauth_token_endpoint == "https://env-auth.example.com/token"

    def test_env_vars_override_core_fields(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "api_url": "https://file-api.example.com",
            "cognito_domain": "https://file-auth.example.com",
            "client_id": "file-client",
        }))
        env = {"QA_STUDIO_API_URL": "https://env-api.example.com"}
        with patch("qa_studio_cli.config.manager.CONFIG_FILE", config_file), \
             patch.dict(os.environ, env, clear=False):
            config = load_config()
        assert config.api_url == "https://env-api.example.com"
        assert config.cognito_domain == "https://file-auth.example.com"

    def test_raises_config_error_when_no_file_and_no_env(self, tmp_path):
        config_file = tmp_path / "nonexistent.json"
        with patch("qa_studio_cli.config.manager.CONFIG_FILE", config_file):
            with pytest.raises(ConfigError, match="Configuration not found"):
                load_config()

    def test_round_trip_with_m2m(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("qa_studio_cli.config.manager.CONFIG_FILE", config_file), \
             patch("qa_studio_cli.config.manager.QA_STUDIO_DIR", tmp_path):
            original = CLIConfig(
                api_url="https://api.example.com",
                cognito_domain="https://auth.example.com",
                client_id="test-client",
                oauth_client_id="m2m-id",
                oauth_client_secret="m2m-secret",
                oauth_token_endpoint="https://auth.example.com/oauth2/token",
            )
            save_config(original)
            loaded = load_config()
        assert loaded == original

    def test_round_trip_without_m2m(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("qa_studio_cli.config.manager.CONFIG_FILE", config_file), \
             patch("qa_studio_cli.config.manager.QA_STUDIO_DIR", tmp_path):
            original = CLIConfig(
                api_url="https://api.example.com",
                cognito_domain="https://auth.example.com",
                client_id="test-client",
            )
            save_config(original)
            loaded = load_config()
        assert loaded == original


class TestConfigureCommandM2M:
    """Tests for the configure command with M2M field prompts."""

    def test_configure_with_m2m_fields(self):
        from click.testing import CliRunner
        from qa_studio_cli.cli import cli

        with patch("qa_studio_cli.cli.config_exists", return_value=False), \
             patch("qa_studio_cli.cli.save_config") as mock_save:
            runner = CliRunner()
            # Core fields + M2M fields
            input_text = (
                "https://api.example.com\n"
                "https://auth.example.com\n"
                "my-client\n"
                "m2m-client-id\n"
                "m2m-secret\n"
                "https://auth.example.com/oauth2/token\n"
            )
            result = runner.invoke(cli, ["configure"], input=input_text)

        assert result.exit_code == 0
        assert "Configuration saved" in result.output
        saved = mock_save.call_args[0][0]
        assert saved.oauth_client_id == "m2m-client-id"
        assert saved.oauth_client_secret == "m2m-secret"
        assert saved.oauth_token_endpoint == "https://auth.example.com/oauth2/token"

    def test_configure_skip_m2m_fields(self):
        from click.testing import CliRunner
        from qa_studio_cli.cli import cli

        with patch("qa_studio_cli.cli.config_exists", return_value=False), \
             patch("qa_studio_cli.cli.save_config") as mock_save:
            runner = CliRunner()
            # Core fields + empty M2M fields (press Enter to skip)
            input_text = (
                "https://api.example.com\n"
                "https://auth.example.com\n"
                "my-client\n"
                "\n"
                "\n"
                "\n"
            )
            result = runner.invoke(cli, ["configure"], input=input_text)

        assert result.exit_code == 0
        saved = mock_save.call_args[0][0]
        assert saved.oauth_client_id is None
        assert saved.oauth_client_secret is None
        assert saved.oauth_token_endpoint is None

    def test_reconfigure_prepopulates_m2m_fields(self):
        from click.testing import CliRunner
        from qa_studio_cli.cli import cli

        with patch("qa_studio_cli.cli.config_exists", return_value=True), \
             patch("qa_studio_cli.cli.load_config") as mock_load, \
             patch("qa_studio_cli.cli.save_config") as mock_save:
            mock_load.return_value = CLIConfig(
                api_url="https://existing-api.com",
                cognito_domain="https://existing-auth.com",
                client_id="existing-client",
                oauth_client_id="existing-m2m-id",
                oauth_client_secret="existing-m2m-secret",
                oauth_token_endpoint="https://existing-auth.com/oauth2/token",
            )
            runner = CliRunner()
            # Press Enter 6 times to accept all defaults
            result = runner.invoke(cli, ["configure"], input="\n\n\n\n\n\n")

        assert result.exit_code == 0
        saved = mock_save.call_args[0][0]
        assert saved.api_url == "https://existing-api.com"
        assert saved.oauth_client_id == "existing-m2m-id"
        assert saved.oauth_client_secret == "existing-m2m-secret"
