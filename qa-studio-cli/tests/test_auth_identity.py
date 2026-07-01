"""Tests for :mod:`qa_studio_cli.auth.identity`.

Covers the resolution priority chain (env → config → stored token),
the JWT payload decoder's tolerance of malformed inputs, and the
user-claim preference order (email → username → cognito:username →
sub).

The identity resolver mirrors :class:`TokenResolver` so any
reordering there should be reflected here — these tests pin the
contract so a silent drift fails CI.
"""

from __future__ import annotations

import base64
import json
import os
from unittest.mock import patch

import pytest

from qa_studio_cli.auth.identity import (
    _decode_jwt_payload,
    get_display_identity,
)
from qa_studio_cli.models.config import CLIConfig
from qa_studio_cli.models.errors import AuthError, ConfigError
from qa_studio_cli.models.token import TokenData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jwt(payload: dict) -> str:
    """Build a fake JWT with an unsigned payload.

    The resolver never verifies the signature (we trust tokens we
    stored ourselves), so a placeholder header/signature is enough to
    exercise the decoder.
    """
    header_b64 = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload_bytes = json.dumps(payload).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
    return f"{header_b64}.{payload_b64}.signature"


def _token_data(payload: dict) -> TokenData:
    return TokenData(
        access_token=_make_jwt(payload),
        refresh_token="refresh",
        expires_at=2_000_000_000,
    )


def _m2m_config(**overrides) -> CLIConfig:
    base = {
        "api_url": "https://api.example.com",
        "cognito_domain": "https://auth.example.com",
        "client_id": "pub-client",
        "oauth_client_id": "cfg-cid",
        "oauth_client_secret": "cfg-secret",
        "oauth_token_endpoint": "https://auth.example.com/oauth2/token",
    }
    base.update(overrides)
    return CLIConfig(**base)


def _no_m2m_config() -> CLIConfig:
    return CLIConfig(api_url="https://api.example.com")


def _env_clear() -> dict:
    # Clearing OAUTH_* vars on every test so a developer env doesn't
    # leak into the assertions. ``clear=False`` on ``patch.dict`` +
    # empty strings replicates how the resolver treats "unset".
    return {
        "OAUTH_CLIENT_ID": "",
        "OAUTH_CLIENT_SECRET": "",
        "OAUTH_TOKEN_ENDPOINT": "",
    }


# ---------------------------------------------------------------------------
# _decode_jwt_payload
# ---------------------------------------------------------------------------


class TestDecodeJwtPayload:
    def test_decodes_standard_payload(self):
        token = _make_jwt({"sub": "123", "username": "alice"})
        assert _decode_jwt_payload(token) == {"sub": "123", "username": "alice"}

    def test_decodes_payload_missing_padding(self):
        """JWTs omit base64 padding — decoder must add it back."""
        # Craft a payload whose encoded length is not a multiple of 4.
        payload_bytes = b'{"u":"x"}'  # 9 bytes → 12 chars base64 → padded to 12
        # To actually exercise the "needs padding" branch we use a
        # 10-byte payload — 10/3 * 4 = 13.3, encoded to 14 chars with
        # 2 trailing '=' that JWTs strip.
        payload_bytes = b'{"u":"xy"}'
        header_b64 = base64.urlsafe_b64encode(b'{"a":1}').rstrip(b"=").decode()
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
        token = f"{header_b64}.{payload_b64}.sig"
        assert _decode_jwt_payload(token) == {"u": "xy"}

    def test_returns_empty_dict_for_wrong_part_count(self):
        assert _decode_jwt_payload("only.two") == {}
        assert _decode_jwt_payload("no-dots-at-all") == {}
        assert _decode_jwt_payload("a.b.c.d") == {}

    def test_returns_empty_dict_for_non_base64_payload(self):
        assert _decode_jwt_payload("a.!!!not-base64!!!.c") == {}

    def test_returns_empty_dict_for_non_json_payload(self):
        payload_b64 = base64.urlsafe_b64encode(b"not json").rstrip(b"=").decode()
        token = f"a.{payload_b64}.c"
        assert _decode_jwt_payload(token) == {}

    def test_returns_empty_dict_for_non_dict_payload(self):
        """A JWT payload must be a JSON object — arrays get rejected."""
        payload_b64 = base64.urlsafe_b64encode(b"[1,2,3]").rstrip(b"=").decode()
        token = f"a.{payload_b64}.c"
        assert _decode_jwt_payload(token) == {}


# ---------------------------------------------------------------------------
# Priority chain
# ---------------------------------------------------------------------------


class TestIdentityFromEnv:
    def test_env_triple_returns_client_id(self):
        env = {
            "OAUTH_CLIENT_ID": "env-cid",
            "OAUTH_CLIENT_SECRET": "env-secret",
            "OAUTH_TOKEN_ENDPOINT": "https://auth.example.com/token",
        }
        with patch.dict(os.environ, env, clear=False):
            assert get_display_identity(_no_m2m_config()) == "env-cid"

    def test_partial_env_falls_through(self):
        """Only some of the triple set → treat as not configured."""
        env = {
            "OAUTH_CLIENT_ID": "env-cid",
            "OAUTH_CLIENT_SECRET": "",
            "OAUTH_TOKEN_ENDPOINT": "",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "qa_studio_cli.auth.identity.load_token", return_value=None
        ):
            assert get_display_identity(_no_m2m_config()) is None


class TestIdentityFromConfig:
    def test_config_triple_returns_client_id(self):
        with patch.dict(os.environ, _env_clear(), clear=False):
            assert get_display_identity(_m2m_config()) == "cfg-cid"

    def test_config_missing_secret_falls_through(self):
        config = _m2m_config(oauth_client_secret=None)
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_token", return_value=None
        ):
            assert get_display_identity(config) is None

    def test_missing_config_loads_from_disk(self):
        """When no config is passed, the resolver reads from disk."""
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_config", return_value=_m2m_config()
        ):
            assert get_display_identity() == "cfg-cid"

    def test_config_load_error_falls_through(self):
        """A missing config file must not crash the header."""
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_config",
            side_effect=ConfigError("no config"),
        ), patch("qa_studio_cli.auth.identity.load_token", return_value=None):
            assert get_display_identity() is None


class TestIdentityFromStoredToken:
    def test_prefers_email_claim(self):
        token = _token_data({"email": "alice@example.com", "username": "alice"})
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_token", return_value=token
        ):
            assert get_display_identity(_no_m2m_config()) == "alice@example.com"

    def test_falls_back_to_username_when_no_email(self):
        token = _token_data({"username": "alice", "sub": "abc-123"})
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_token", return_value=token
        ):
            assert get_display_identity(_no_m2m_config()) == "alice"

    def test_falls_back_to_cognito_username(self):
        token = _token_data({"cognito:username": "alice", "sub": "abc-123"})
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_token", return_value=token
        ):
            assert get_display_identity(_no_m2m_config()) == "alice"

    def test_falls_back_to_sub_when_nothing_else_present(self):
        token = _token_data({"sub": "abc-123"})
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_token", return_value=token
        ):
            assert get_display_identity(_no_m2m_config()) == "abc-123"

    def test_no_token_returns_none(self):
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_token", return_value=None
        ):
            assert get_display_identity(_no_m2m_config()) is None

    def test_corrupt_token_returns_none(self):
        """``load_token`` raising :class:`AuthError` must not bubble."""
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_token",
            side_effect=AuthError("corrupt"),
        ):
            assert get_display_identity(_no_m2m_config()) is None

    def test_malformed_jwt_returns_none(self):
        token = TokenData(
            access_token="not-a-jwt",
            refresh_token="refresh",
            expires_at=2_000_000_000,
        )
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_token", return_value=token
        ):
            assert get_display_identity(_no_m2m_config()) is None

    def test_ignores_non_string_claim_values(self):
        """Cognito should never set e.g. ``email`` to a non-string,
        but the decoder must skip unexpected types rather than crash."""
        token = _token_data({"email": 42, "username": "alice"})
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_token", return_value=token
        ):
            assert get_display_identity(_no_m2m_config()) == "alice"

    def test_ignores_empty_string_claim_values(self):
        token = _token_data({"email": "", "username": "alice"})
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_token", return_value=token
        ):
            assert get_display_identity(_no_m2m_config()) == "alice"


# ---------------------------------------------------------------------------
# Priority ordering between sources
# ---------------------------------------------------------------------------


class TestPriorityOrdering:
    def test_env_wins_over_config(self):
        env = {
            "OAUTH_CLIENT_ID": "env-cid",
            "OAUTH_CLIENT_SECRET": "env-secret",
            "OAUTH_TOKEN_ENDPOINT": "https://auth.example.com/token",
        }
        with patch.dict(os.environ, env, clear=False):
            assert get_display_identity(_m2m_config()) == "env-cid"

    def test_env_wins_over_stored_token(self):
        env = {
            "OAUTH_CLIENT_ID": "env-cid",
            "OAUTH_CLIENT_SECRET": "env-secret",
            "OAUTH_TOKEN_ENDPOINT": "https://auth.example.com/token",
        }
        token = _token_data({"email": "alice@example.com"})
        with patch.dict(os.environ, env, clear=False), patch(
            "qa_studio_cli.auth.identity.load_token", return_value=token
        ):
            assert get_display_identity(_no_m2m_config()) == "env-cid"

    def test_config_wins_over_stored_token(self):
        token = _token_data({"email": "alice@example.com"})
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_token", return_value=token
        ):
            assert get_display_identity(_m2m_config()) == "cfg-cid"


# ---------------------------------------------------------------------------
# Exhaustion
# ---------------------------------------------------------------------------


class TestNoIdentityAvailable:
    def test_returns_none_when_nothing_configured(self):
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_token", return_value=None
        ):
            assert get_display_identity(_no_m2m_config()) is None


# ---------------------------------------------------------------------------
# Smoke — module surface
# ---------------------------------------------------------------------------


class TestModuleSurface:
    def test_get_display_identity_is_callable_with_no_args(self):
        """The TUI calls this with zero args on every AppHeader mount.
        It must never raise on a plain import/call, even on a machine
        with no config and no stored token."""
        with patch.dict(os.environ, _env_clear(), clear=False), patch(
            "qa_studio_cli.auth.identity.load_config",
            side_effect=ConfigError("no config"),
        ), patch("qa_studio_cli.auth.identity.load_token", return_value=None):
            # Any return value is fine; the test pins that the call
            # itself does not raise.
            result = get_display_identity()
            assert result is None or isinstance(result, str)
