"""Token persistence, expiry checking, refresh, and lifecycle management."""

import json
import os
import time
from pathlib import Path

import requests

from qa_studio_cli.models.errors import AuthError
from qa_studio_cli.models.token import TokenData
from qa_studio_cli.utils.config import load_config

QA_STUDIO_DIR = Path.home() / ".qa-studio"
TOKEN_FILE = QA_STUDIO_DIR / "token.json"


def save_token(token_data: TokenData) -> None:
    """Save token to ~/.qa-studio/token.json with chmod 600."""
    QA_STUDIO_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token_data.model_dump_json(indent=2))
    os.chmod(TOKEN_FILE, 0o600)


def load_token() -> TokenData | None:
    """
    Load token from file.

    Returns:
        TokenData if file exists and is valid, None if file is missing.

    Raises:
        AuthError: If the token file exists but contains invalid data.
    """
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text())
        return TokenData(**data)
    except (json.JSONDecodeError, Exception) as e:
        raise AuthError(f"Corrupt token file: {e}")


def delete_token() -> None:
    """Delete token file if it exists, succeed silently if not."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


def is_token_expired(token_data: TokenData) -> bool:
    """Check if token is expired with a 30-second buffer."""
    return int(time.time()) >= (token_data.expires_at - 30)


def refresh_access_token(
    refresh_token: str, cognito_domain: str, client_id: str
) -> TokenData:
    """
    Refresh access token via Cognito's /oauth2/token endpoint.

    Args:
        refresh_token: The refresh token to use.
        cognito_domain: Cognito hosted UI domain (https://...).
        client_id: Cognito app client ID.

    Returns:
        New TokenData with updated access_token and expires_at.

    Raises:
        AuthError: If the refresh fails (e.g. invalid_grant).
    """
    token_url = f"{cognito_domain}/oauth2/token"
    response = requests.post(
        token_url,
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status_code != 200:
        raise AuthError(
            f"Token refresh failed: {response.status_code} - {response.text}"
        )

    data = response.json()
    return TokenData(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", refresh_token),
        expires_at=int(time.time()) + data["expires_in"],
        token_type=data.get("token_type", "Bearer"),
    )


def get_valid_token() -> str:
    """
    Single entry point for all token consumers.

    Load token → check expiry → refresh if needed → return access_token.

    Returns:
        A valid (non-expired) access_token string.

    Raises:
        AuthError: If not authenticated or refresh fails.
    """
    token_data = load_token()
    if token_data is None:
        raise AuthError("Not authenticated. Run 'qa-studio login'.")

    if not is_token_expired(token_data):
        return token_data.access_token

    # Token expired — attempt refresh
    config = load_config()
    try:
        new_token = refresh_access_token(
            refresh_token=token_data.refresh_token,
            cognito_domain=config.cognito_domain,
            client_id=config.client_id,
        )
        save_token(new_token)
        return new_token.access_token
    except AuthError:
        raise AuthError(
            "Session expired. Run 'qa-studio login' to re-authenticate."
        )
