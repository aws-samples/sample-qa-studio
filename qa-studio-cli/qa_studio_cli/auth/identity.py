"""Resolve a human-readable identity for display in the TUI.

Mirrors :class:`qa_studio_cli.auth.resolver.TokenResolver` so the
string the header shows reflects which auth source the rest of the
app will actually use. Returns ``None`` when no auth source is
configured so the caller can decide whether to render a dash, a
hint, or nothing at all.

Intentionally read-only: this module never triggers a network
request (no token refresh, no client-credentials exchange). It only
inspects environment variables, the on-disk config, and the locally
stored user token. That keeps header rendering cheap and offline.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Dict, Optional

from qa_studio_cli.auth.token_manager import load_token
from qa_studio_cli.config.manager import load_config
from qa_studio_cli.models.config import CLIConfig
from qa_studio_cli.models.errors import AuthError, ConfigError

logger = logging.getLogger(__name__)


# Preference order for JWT claims when deriving a display string from
# a user access token. Cognito access tokens don't carry ``email``
# (that lives in the ID token, which we don't persist); ``username``
# is what the user actually signed in with and equals the email for
# pools configured with email-as-username. ``sub`` is the final
# fallback — opaque, but still better than showing nothing.
_USER_CLAIM_PREFERENCE = ("email", "username", "cognito:username", "sub")


def get_display_identity(config: Optional[CLIConfig] = None) -> Optional[str]:
    """Return a short display identity for the active auth source.

    Resolution priority mirrors :class:`TokenResolver`:

    1. Environment ``OAUTH_CLIENT_ID`` / ``OAUTH_CLIENT_SECRET`` /
       ``OAUTH_TOKEN_ENDPOINT`` — returns the client id.
    2. Config file ``oauth_client_id`` / ``_secret`` / ``_token_endpoint``
       — returns the client id.
    3. Stored user token at ``~/.qa-studio/token.json`` — decodes the
       JWT payload and returns the first populated user-identifier
       claim (see :data:`_USER_CLAIM_PREFERENCE`).

    Args:
        config: Optional pre-loaded :class:`CLIConfig`. When ``None``
            the function loads it itself and treats a missing /
            invalid config as "no M2M credentials" rather than an
            error — the header should never crash because the user
            hasn't run ``qa-studio configure`` yet.

    Returns:
        The display string, or ``None`` when no auth source matched.
    """
    env_identity = _identity_from_env()
    if env_identity is not None:
        return env_identity

    config_identity = _identity_from_config(config)
    if config_identity is not None:
        return config_identity

    return _identity_from_stored_token()


def _identity_from_env() -> Optional[str]:
    """Return the M2M client id from the env triple when complete.

    All three env vars must be set — the resolver only accepts the
    triple as a unit. A partial env set falls through to the next
    source instead of pretending to be a valid identity.
    """
    client_id = os.environ.get("OAUTH_CLIENT_ID")
    secret = os.environ.get("OAUTH_CLIENT_SECRET")
    endpoint = os.environ.get("OAUTH_TOKEN_ENDPOINT")
    if client_id and secret and endpoint:
        return client_id
    return None


def _identity_from_config(config: Optional[CLIConfig]) -> Optional[str]:
    """Return the M2M client id from the config triple when complete."""
    if config is None:
        try:
            config = load_config()
        except ConfigError:
            return None

    if (
        config.oauth_client_id
        and config.oauth_client_secret
        and config.oauth_token_endpoint
    ):
        return config.oauth_client_id
    return None


def _identity_from_stored_token() -> Optional[str]:
    """Decode the stored user access token and return a user claim."""
    try:
        token_data = load_token()
    except AuthError as exc:
        logger.debug("Stored token unreadable: %s", exc)
        return None
    if token_data is None:
        return None

    claims = _decode_jwt_payload(token_data.access_token)
    for key in _USER_CLAIM_PREFERENCE:
        value = claims.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _decode_jwt_payload(access_token: str) -> Dict[str, Any]:
    """Decode the payload of a JWT without verifying its signature.

    We decode a token this CLI previously stored itself; there is no
    external trust boundary. Signature verification would require
    fetching the Cognito JWKs over the network, which is out of
    scope for a purely cosmetic header field.

    Returns an empty dict on any decode failure so callers can treat
    "no claims" and "malformed token" identically.
    """
    parts = access_token.split(".")
    if len(parts) != 3:
        return {}
    payload_b64 = parts[1]

    # ``urlsafe_b64decode`` requires correct padding; JWTs omit it.
    padding = -len(payload_b64) % 4
    try:
        decoded = base64.urlsafe_b64decode(payload_b64 + "=" * padding)
        payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        logger.debug("Failed to decode access token payload: %s", exc)
        return {}

    if not isinstance(payload, dict):
        return {}
    return payload
