"""Tests for the configure command — pre-populating defaults from existing config."""

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from qa_studio_cli.cli import cli


class TestConfigureCommand:
    """Unit tests for the configure command."""

    def test_fresh_configure_uses_generic_defaults(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("qa_studio_cli.cli.config_exists", return_value=False), \
             patch("qa_studio_cli.cli.CONFIG_FILE", config_file), \
             patch("qa_studio_cli.cli.save_config") as mock_save:
            runner = CliRunner()
            result = runner.invoke(
                cli, ["configure"],
                input="https://my-api.com\nhttps://my-auth.com\nmy-client-id\n\n\n\n",
            )

        assert result.exit_code == 0
        assert "Configuration saved" in result.output
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        assert saved.api_url == "https://my-api.com"
        assert saved.cognito_domain == "https://my-auth.com"
        assert saved.client_id == "my-client-id"
        assert saved.oauth_client_id is None

    def test_reconfigure_prepopulates_existing_values(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "api_url": "https://existing-api.com",
            "cognito_domain": "https://existing-auth.com",
            "client_id": "existing-client",
        }))

        with patch("qa_studio_cli.cli.config_exists", return_value=True), \
             patch("qa_studio_cli.cli.load_config") as mock_load, \
             patch("qa_studio_cli.cli.CONFIG_FILE", config_file), \
             patch("qa_studio_cli.cli.save_config") as mock_save:
            from qa_studio_cli.models.config import CLIConfig
            mock_load.return_value = CLIConfig(
                api_url="https://existing-api.com",
                cognito_domain="https://existing-auth.com",
                client_id="existing-client",
            )
            # Press enter 6 times to accept all defaults (3 core + 3 M2M)
            runner = CliRunner()
            result = runner.invoke(cli, ["configure"], input="\n\n\n\n\n\n")

        assert result.exit_code == 0
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        assert saved.api_url == "https://existing-api.com"
        assert saved.cognito_domain == "https://existing-auth.com"
        assert saved.client_id == "existing-client"

    def test_reconfigure_allows_overriding_single_field(self, tmp_path):
        with patch("qa_studio_cli.cli.config_exists", return_value=True), \
             patch("qa_studio_cli.cli.load_config") as mock_load, \
             patch("qa_studio_cli.cli.save_config") as mock_save:
            from qa_studio_cli.models.config import CLIConfig
            mock_load.return_value = CLIConfig(
                api_url="https://old-api.com",
                cognito_domain="https://old-auth.com",
                client_id="old-client",
            )
            # Override only the API URL, accept the rest (3 core + 3 M2M)
            runner = CliRunner()
            result = runner.invoke(
                cli, ["configure"],
                input="https://new-api.com\n\n\n\n\n\n",
            )

        assert result.exit_code == 0
        saved = mock_save.call_args[0][0]
        assert saved.api_url == "https://new-api.com"
        assert saved.cognito_domain == "https://old-auth.com"
        assert saved.client_id == "old-client"

    def test_configure_handles_corrupt_config_gracefully(self):
        with patch("qa_studio_cli.cli.config_exists", return_value=True), \
             patch("qa_studio_cli.cli.load_config", side_effect=Exception("corrupt")), \
             patch("qa_studio_cli.cli.save_config") as mock_save:
            runner = CliRunner()
            result = runner.invoke(
                cli, ["configure"],
                input="https://api.com\nhttps://auth.com\nclient-123\n\n\n\n",
            )

        assert result.exit_code == 0
        assert "Configuration saved" in result.output
        saved = mock_save.call_args[0][0]
        assert saved.client_id == "client-123"
