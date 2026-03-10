"""Configuration file I/O with environment variable overlay."""

import json
import os
from pathlib import Path

from qa_studio_cli.models.config import CLIConfig
from qa_studio_cli.models.errors import ConfigError

QA_STUDIO_DIR = Path.home() / ".qa-studio"
CONFIG_FILE = QA_STUDIO_DIR / "config.json"

ENV_VAR_MAP = {
    "api_url": "QA_STUDIO_API_URL",
    "cognito_domain": "QA_STUDIO_COGNITO_DOMAIN",
    "client_id": "QA_STUDIO_CLIENT_ID",
    "oauth_client_id": "OAUTH_CLIENT_ID",
    "oauth_client_secret": "OAUTH_CLIENT_SECRET",
    "oauth_token_endpoint": "OAUTH_TOKEN_ENDPOINT",
}


def save_config(config: CLIConfig) -> None:
    """Save config to ~/.qa-studio/config.json with chmod 600.

    Excludes None-valued optional fields from the JSON output to keep
    the config file clean for users who don't use M2M auth.
    """
    QA_STUDIO_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        config.model_dump_json(indent=2, exclude_none=True)
    )
    os.chmod(CONFIG_FILE, 0o600)


def load_config() -> CLIConfig:
    """Load config: file values overlaid with env vars.

    Raises:
        ConfigError: If file missing and no env vars provide required values.
    """
    file_data = {}
    if CONFIG_FILE.exists():
        file_data = json.loads(CONFIG_FILE.read_text())

    # Overlay env vars
    for field, env_var in ENV_VAR_MAP.items():
        env_value = os.environ.get(env_var)
        if env_value:
            file_data[field] = env_value

    if not file_data:
        raise ConfigError("Configuration not found. Run 'qa-studio configure' first.")

    try:
        return CLIConfig(**file_data)
    except Exception as e:
        raise ConfigError(f"Invalid configuration: {e}")


def config_exists() -> bool:
    """Check if config file exists on disk."""
    return CONFIG_FILE.exists()


def get_config_value(key: str) -> str:
    """Get single config value with env var precedence over file.

    Args:
        key: Config field name (e.g. 'api_url', 'cognito_domain', 'client_id')

    Returns:
        The config value as a string.
    """
    env_var = ENV_VAR_MAP.get(key)
    if env_var:
        env_value = os.environ.get(env_var)
        if env_value:
            return env_value
    config = load_config()
    return getattr(config, key)
