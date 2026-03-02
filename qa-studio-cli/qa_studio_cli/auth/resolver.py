"""Token resolution chain for the runner command.

Tries multiple auth sources in priority order:
1. Token file (--token-file flag)
2. Environment variables (OAUTH_CLIENT_ID/SECRET/TOKEN_ENDPOINT)
3. Config file M2M credentials (~/.qa-studio/config.json)
4. Stored user token (~/.qa-studio/token.json) with auto-refresh
"""

import logging
import os
from typing import Optional

from qa_studio_cli.models.config import CLIConfig
from qa_studio_cli.models.errors import AuthError

logger = logging.getLogger(__name__)


class TokenResolver:
    """Resolve access token from multiple sources in priority order."""

    def __init__(
        self,
        token_file: Optional[str] = None,
        config: Optional[CLIConfig] = None,
    ):
        self._token_file = token_file
        self._config = config
        self._provider = None  # Lazily initialized on first get_token()

    def get_token(self) -> str:
        """Return a valid access token. Tries sources in priority order.

        Raises:
            AuthError: If all sources are exhausted.
        """
        # If we already resolved a provider, reuse it
        if self._provider is not None:
            return self._provider.get_token()

        # 1. Token file
        if self._token_file:
            logger.debug("Using token file: %s", self._token_file)
            from qa_studio_cli.auth.token_file_provider import TokenFileProvider
            self._provider = TokenFileProvider(self._token_file)
            return self._provider.get_token()

        # 2. Environment variables for client-credentials
        env_client_id = os.environ.get("OAUTH_CLIENT_ID")
        env_client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
        env_token_endpoint = os.environ.get("OAUTH_TOKEN_ENDPOINT")
        if env_client_id and env_client_secret and env_token_endpoint:
            logger.debug("Using client credentials from environment variables")
            from qa_studio_cli.auth.client_credentials import ClientCredentialsProvider
            self._provider = ClientCredentialsProvider(
                client_id=env_client_id,
                client_secret=env_client_secret,
                token_endpoint=env_token_endpoint,
            )
            return self._provider.get_token()

        # 3. Config file M2M credentials
        if (
            self._config
            and self._config.oauth_client_id
            and self._config.oauth_client_secret
            and self._config.oauth_token_endpoint
        ):
            logger.debug("Using client credentials from config file")
            from qa_studio_cli.auth.client_credentials import ClientCredentialsProvider
            self._provider = ClientCredentialsProvider(
                client_id=self._config.oauth_client_id,
                client_secret=self._config.oauth_client_secret,
                token_endpoint=self._config.oauth_token_endpoint,
            )
            return self._provider.get_token()

        # 4. Stored user token (from `qa-studio login`)
        try:
            from qa_studio_cli.auth.token_manager import get_valid_token
            token = get_valid_token()
            logger.debug("Using stored user token from token.json")
            # Wrap in a simple lambda-like provider for caching
            self._provider = _StaticTokenProvider(token)
            return token
        except AuthError:
            pass

        raise AuthError(
            "No authentication source available. Options:\n"
            "  • Run 'qa-studio login' for interactive auth\n"
            "  • Set OAUTH_CLIENT_ID/OAUTH_CLIENT_SECRET/OAUTH_TOKEN_ENDPOINT env vars\n"
            "  • Add oauth_client_id/oauth_client_secret/oauth_token_endpoint to ~/.qa-studio/config.json\n"
            "  • Use --token-file with a JSON file containing access_token"
        )


class _StaticTokenProvider:
    """Wraps a pre-resolved token string as a provider."""

    def __init__(self, token: str):
        self._token = token

    def get_token(self) -> str:
        return self._token
