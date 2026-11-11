"""Tests for ApiClient and require_auth decorator."""

import logging
from unittest.mock import MagicMock, patch

import click
import pytest
import requests
from click.testing import CliRunner
from hypothesis import given, settings
from hypothesis import strategies as st

from qa_studio_cli.api.client import (
    ApiClient, require_auth,
    RETRY_ATTEMPTS, RETRY_JITTER_MAX_S, RETRY_WAIT_MAX_S, RETRY_WAIT_MIN_S,
)
from qa_studio_cli.models.errors import ApiError, AuthError, ConfigError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int = 200, json_data: dict | None = None, text: str = ""):
    """Create a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = text
    return resp


def _make_client(token: str = "tok", base_url: str = "https://api.example.com") -> ApiClient:
    """Create an ApiClient with a static token provider."""
    return ApiClient(base_url=base_url, token_provider=lambda: token)


@pytest.fixture(autouse=True)
def recorded_sleeps(monkeypatch):
    """Never sleep in these tests: the retry schedule waits up to ~1 min per call.

    The waits tenacity would have slept are recorded so tests can assert on
    the schedule (see ``TestRetryBehavior``).
    """
    sleeps: list[float] = []
    monkeypatch.setattr(ApiClient._request_with_retry.retry, "sleep", sleeps.append)
    return sleeps


# ---------------------------------------------------------------------------
# Property: Bearer header on every request (Design Property 8)
# ---------------------------------------------------------------------------

# Feature: merge-cli-tools, Property 8: API client sends Bearer authorization header
class TestBearerHeaderProperty:
    """For any token and path, every request includes Bearer auth header."""

    @given(
        token=st.text(min_size=1, max_size=200),
        path=st.from_regex(r"/[a-z0-9\-/]{0,50}", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_get_includes_bearer_header(self, token, path):
        client = _make_client(token)
        with patch.object(client._session, "request", return_value=_mock_response(200, {"ok": True})):
            client.get(path)
            _, kwargs = client._session.request.call_args
            assert kwargs["headers"]["Authorization"] == f"Bearer {token}"
            assert kwargs["headers"]["Content-Type"] == "application/json"

    @given(
        token=st.text(min_size=1, max_size=200),
        path=st.from_regex(r"/[a-z0-9\-/]{0,50}", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_post_includes_bearer_header(self, token, path):
        client = _make_client(token)
        with patch.object(client._session, "request", return_value=_mock_response(200, {"ok": True})):
            client.post(path, json_body={"key": "value"})
            _, kwargs = client._session.request.call_args
            assert kwargs["headers"]["Authorization"] == f"Bearer {token}"

    @given(
        token=st.text(min_size=1, max_size=200),
        path=st.from_regex(r"/[a-z0-9\-/]{0,50}", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_patch_includes_bearer_header(self, token, path):
        client = _make_client(token)
        with patch.object(client._session, "request", return_value=_mock_response(200, {"ok": True})):
            client.patch(path, json_body={"key": "value"})
            _, kwargs = client._session.request.call_args
            assert kwargs["headers"]["Authorization"] == f"Bearer {token}"

    @given(
        token=st.text(min_size=1, max_size=200),
        path=st.from_regex(r"/[a-z0-9\-/]{0,50}", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_delete_includes_bearer_header(self, token, path):
        client = _make_client(token)
        with patch.object(client._session, "request", return_value=_mock_response(204)):
            client.delete(path)
            _, kwargs = client._session.request.call_args
            assert kwargs["headers"]["Authorization"] == f"Bearer {token}"


# ---------------------------------------------------------------------------
# Property: 2xx responses return parsed JSON (Design Property 9)
# ---------------------------------------------------------------------------

# Feature: merge-cli-tools, Property 9: API client supports all required HTTP methods
class TestSuccessResponseProperty:
    """For any valid JSON body and 2xx status (excl 204), ApiClient returns parsed JSON."""

    @given(
        json_body=st.dictionaries(
            keys=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
            values=st.one_of(st.text(max_size=50), st.integers(), st.booleans()),
            max_size=5,
        ),
        status_code=st.sampled_from([200, 201, 202]),
    )
    @settings(max_examples=100)
    def test_2xx_returns_parsed_json(self, json_body, status_code):
        client = _make_client()
        with patch.object(client._session, "request", return_value=_mock_response(status_code, json_body)):
            result = client.get("/test")
            assert result == json_body


# ---------------------------------------------------------------------------
# Property: Non-2xx raises ApiError
# ---------------------------------------------------------------------------

class TestNon2xxErrorProperty:
    """For non-2xx codes (excl 401/403/404), _handle_error raises ApiError."""

    @given(
        status_code=st.integers(min_value=400, max_value=599).filter(lambda x: x not in (401, 403, 404)),
        message=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=100)
    def test_handle_error_raises_api_error(self, status_code, message):
        client = _make_client()
        resp = _mock_response(status_code, {"message": message}, text=message)
        with pytest.raises(ApiError) as exc_info:
            client._handle_error(resp)
        assert exc_info.value.status_code == status_code
        assert exc_info.value.message == message


# ---------------------------------------------------------------------------
# Unit tests: token_provider called on each request
# ---------------------------------------------------------------------------

class TestTokenProviderCalledPerRequest:
    """Verify token_provider is called on every request (supports refresh)."""

    def test_token_provider_called_on_get(self):
        provider = MagicMock(return_value="fresh-token")
        client = ApiClient(base_url="https://api.example.com", token_provider=provider)
        with patch.object(client._session, "request", return_value=_mock_response(200, {})):
            client.get("/test")
            client.get("/test2")
        assert provider.call_count == 2

    def test_token_provider_called_on_post(self):
        provider = MagicMock(return_value="fresh-token")
        client = ApiClient(base_url="https://api.example.com", token_provider=provider)
        with patch.object(client._session, "request", return_value=_mock_response(200, {})):
            client.post("/test")
        provider.assert_called_once()

    def test_token_provider_called_on_patch(self):
        provider = MagicMock(return_value="fresh-token")
        client = ApiClient(base_url="https://api.example.com", token_provider=provider)
        with patch.object(client._session, "request", return_value=_mock_response(200, {})):
            client.patch("/test")
        provider.assert_called_once()

    def test_token_provider_called_on_delete(self):
        provider = MagicMock(return_value="fresh-token")
        client = ApiClient(base_url="https://api.example.com", token_provider=provider)
        with patch.object(client._session, "request", return_value=_mock_response(204)):
            client.delete("/test")
        provider.assert_called_once()


# ---------------------------------------------------------------------------
# Unit tests: session reuse
# ---------------------------------------------------------------------------

class TestSessionReuse:
    """Verify requests.Session is reused across calls."""

    def test_same_session_used_for_multiple_requests(self):
        client = _make_client()
        with patch.object(client._session, "request", return_value=_mock_response(200, {})) as mock_req:
            client.get("/a")
            client.post("/b")
            client.patch("/c")
            assert mock_req.call_count == 3


# ---------------------------------------------------------------------------
# Unit tests: HTTP methods
# ---------------------------------------------------------------------------

class TestApiClientGet:
    def test_sends_get_with_correct_url_and_headers(self):
        client = _make_client("my-token")
        with patch.object(client._session, "request", return_value=_mock_response(200, {"data": "ok"})) as mock_req:
            result = client.get("/usecases", params={"limit": 10})
            mock_req.assert_called_once_with(
                "GET",
                "https://api.example.com/usecases",
                headers={"Authorization": "Bearer my-token", "Content-Type": "application/json"},
                params={"limit": 10},
            )
            assert result == {"data": "ok"}


class TestApiClientPost:
    def test_sends_post_with_json_body(self):
        client = _make_client("my-token")
        with patch.object(client._session, "request", return_value=_mock_response(201, {"id": "new-1"})) as mock_req:
            result = client.post("/usecases", json_body={"name": "Test"})
            mock_req.assert_called_once_with(
                "POST",
                "https://api.example.com/usecases",
                headers={"Authorization": "Bearer my-token", "Content-Type": "application/json"},
                json={"name": "Test"},
                params=None,
            )
            assert result == {"id": "new-1"}


class TestApiClientPatch:
    def test_sends_patch_with_json_body(self):
        client = _make_client("my-token")
        with patch.object(client._session, "request", return_value=_mock_response(200, {"updated": True})) as mock_req:
            result = client.patch("/usecase/abc/status", json_body={"status": "running"})
            mock_req.assert_called_once_with(
                "PATCH",
                "https://api.example.com/usecase/abc/status",
                headers={"Authorization": "Bearer my-token", "Content-Type": "application/json"},
                json={"status": "running"},
            )
            assert result == {"updated": True}


class TestApiClientPut:
    def test_sends_put_with_json_body(self):
        client = _make_client("my-token")
        with patch.object(client._session, "request", return_value=_mock_response(200, {"version": 4})) as mock_req:
            result = client.put("/templates/t1", json_body={"templateVersion": "1.0"})
            mock_req.assert_called_once_with(
                "PUT",
                "https://api.example.com/templates/t1",
                headers={"Authorization": "Bearer my-token", "Content-Type": "application/json"},
                json={"templateVersion": "1.0"},
            )
            assert result == {"version": 4}


class TestApiClientDelete:
    def test_returns_none_for_204(self):
        client = _make_client("my-token")
        with patch.object(client._session, "request", return_value=_mock_response(204)):
            result = client.delete("/usecase/abc-123")
            assert result is None

    def test_returns_json_for_200(self):
        client = _make_client("my-token")
        with patch.object(client._session, "request", return_value=_mock_response(200, {"deleted": True})):
            result = client.delete("/usecase/abc-123")
            assert result == {"deleted": True}


# ---------------------------------------------------------------------------
# Unit tests: error handling
# ---------------------------------------------------------------------------

class TestHandleError:
    def test_401_raises_session_expired(self):
        client = _make_client()
        resp = _mock_response(401)
        with pytest.raises(ApiError) as exc_info:
            client._handle_error(resp)
        assert exc_info.value.status_code == 401
        assert "session expired" in exc_info.value.message.lower()

    def test_403_raises_insufficient_permissions(self):
        client = _make_client()
        resp = _mock_response(403)
        with pytest.raises(ApiError) as exc_info:
            client._handle_error(resp)
        assert exc_info.value.status_code == 403
        assert "insufficient permissions" in exc_info.value.message.lower()

    def test_403_includes_detail_from_body(self):
        client = _make_client()
        resp = _mock_response(403, {"message": "Missing scope api/tests.read"})
        with pytest.raises(ApiError) as exc_info:
            client._handle_error(resp)
        assert "Missing scope" in exc_info.value.message

    def test_404_raises_resource_not_found(self):
        client = _make_client()
        resp = _mock_response(404)
        with pytest.raises(ApiError) as exc_info:
            client._handle_error(resp)
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message.lower()

    def test_500_includes_status_code_and_body_message(self):
        client = _make_client()
        resp = _mock_response(500, {"message": "Internal server error"}, text="Internal server error")
        with pytest.raises(ApiError) as exc_info:
            client._handle_error(resp)
        assert exc_info.value.status_code == 500
        assert exc_info.value.message == "Internal server error"


class TestConnectionErrors:
    def test_handles_connection_error(self):
        client = _make_client()
        with patch.object(client._session, "request", side_effect=requests.ConnectionError("refused")):
            with pytest.raises(ApiError) as exc_info:
                client.get("/test")
            assert exc_info.value.status_code == 0
            assert "connection error" in exc_info.value.message.lower()

    def test_handles_timeout(self):
        client = _make_client()
        with patch.object(client._session, "request", side_effect=requests.Timeout("timed out")):
            with pytest.raises(ApiError) as exc_info:
                client.get("/test")
            assert exc_info.value.status_code == 0
            assert "timed out" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# Unit tests: require_auth decorator
# ---------------------------------------------------------------------------

class TestRequireAuth:
    def test_creates_api_client_when_config_and_token_exist(self):
        @click.command()
        @require_auth
        @click.pass_context
        def dummy_cmd(ctx):
            client = ctx.obj["client"]
            click.echo(f"base_url={client.base_url}")

        runner = CliRunner()
        with (
            patch("qa_studio_cli.api.client.config_exists", return_value=True),
            patch("qa_studio_cli.api.client.load_config") as mock_config,
            patch("qa_studio_cli.api.client.get_valid_token", return_value="valid-token"),
        ):
            mock_config.return_value = MagicMock(api_url="https://api.example.com")
            result = runner.invoke(dummy_cmd, catch_exceptions=False)
        assert result.exit_code == 0
        assert "base_url=https://api.example.com" in result.output

    def test_exits_when_config_missing(self):
        @click.command()
        @require_auth
        @click.pass_context
        def dummy_cmd(ctx):
            click.echo("should not reach here")

        runner = CliRunner()
        with patch("qa_studio_cli.api.client.config_exists", return_value=False):
            result = runner.invoke(dummy_cmd)
        assert result.exit_code == 1
        assert "Configuration not found" in result.output

    def test_exits_when_token_missing(self):
        @click.command()
        @require_auth
        @click.pass_context
        def dummy_cmd(ctx):
            click.echo("should not reach here")

        runner = CliRunner()
        with (
            patch("qa_studio_cli.api.client.config_exists", return_value=True),
            patch("qa_studio_cli.api.client.load_config") as mock_config,
            patch("qa_studio_cli.api.client.get_valid_token", side_effect=AuthError("Not authenticated. Run 'qa-studio login'.")),
        ):
            mock_config.return_value = MagicMock(api_url="https://api.example.com")
            result = runner.invoke(dummy_cmd)
        assert result.exit_code == 1
        assert "Not authenticated" in result.output

    def test_exits_on_config_error(self):
        @click.command()
        @require_auth
        @click.pass_context
        def dummy_cmd(ctx):
            click.echo("should not reach here")

        runner = CliRunner()
        with (
            patch("qa_studio_cli.api.client.config_exists", return_value=True),
            patch("qa_studio_cli.api.client.load_config", side_effect=ConfigError("Invalid configuration")),
        ):
            result = runner.invoke(dummy_cmd)
        assert result.exit_code == 1
        assert "Configuration error" in result.output

    def test_base_url_trailing_slash_stripped(self):
        @click.command()
        @require_auth
        @click.pass_context
        def dummy_cmd(ctx):
            client = ctx.obj["client"]
            click.echo(f"base_url={client.base_url}")

        runner = CliRunner()
        with (
            patch("qa_studio_cli.api.client.config_exists", return_value=True),
            patch("qa_studio_cli.api.client.load_config") as mock_config,
            patch("qa_studio_cli.api.client.get_valid_token", return_value="tok"),
        ):
            mock_config.return_value = MagicMock(api_url="https://api.example.com/")
            result = runner.invoke(dummy_cmd, catch_exceptions=False)
        assert result.exit_code == 0
        assert "base_url=https://api.example.com" in result.output

    def test_client_uses_token_provider_not_static_token(self):
        """Verify require_auth passes get_valid_token as token_provider."""
        captured_client = {}

        @click.command()
        @require_auth
        @click.pass_context
        def dummy_cmd(ctx):
            captured_client["client"] = ctx.obj["client"]

        runner = CliRunner()
        with (
            patch("qa_studio_cli.api.client.config_exists", return_value=True),
            patch("qa_studio_cli.api.client.load_config") as mock_config,
            patch("qa_studio_cli.api.client.get_valid_token", return_value="tok"),
        ):
            mock_config.return_value = MagicMock(api_url="https://api.example.com")
            runner.invoke(dummy_cmd, catch_exceptions=False)

        client = captured_client["client"]
        assert client._token_provider is not None
        assert callable(client._token_provider)



class TestBuildApiClient:
    """Tests for :func:`qa_studio_cli.api.client.build_api_client`."""

    def test_uses_provided_config(self):
        from qa_studio_cli.api.client import build_api_client
        from qa_studio_cli.models.config import CLIConfig

        config = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="cid",
        )
        client = build_api_client(config=config)
        assert client.base_url == "https://api.example.com"
        assert callable(client._token_provider)

    def test_loads_config_when_none_provided(self):
        from unittest.mock import patch

        from qa_studio_cli.api.client import build_api_client
        from qa_studio_cli.models.config import CLIConfig

        cfg = CLIConfig(
            api_url="https://loaded.example.com",
            cognito_domain="https://auth.example.com",
            client_id="cid",
        )
        with patch("qa_studio_cli.api.client.load_config", return_value=cfg):
            client = build_api_client()
        assert client.base_url == "https://loaded.example.com"

    def test_passes_token_file_through_to_resolver(self):
        """--token-file path should be handed to TokenResolver so the
        file provider wins over env / config / stored-user sources."""
        from unittest.mock import patch

        from qa_studio_cli.api.client import build_api_client
        from qa_studio_cli.models.config import CLIConfig

        cfg = CLIConfig(
            api_url="https://api.example.com",
            cognito_domain="https://auth.example.com",
            client_id="cid",
        )
        with patch("qa_studio_cli.auth.resolver.TokenResolver") as mock_cls:
            build_api_client(token_file="/tmp/token.json", config=cfg)
        mock_cls.assert_called_once_with(token_file="/tmp/token.json", config=cfg)


# ---------------------------------------------------------------------------
# Retry behavior tests
# ---------------------------------------------------------------------------

class TestRetryBehavior:
    """Verify retry logic for transient errors.

    The retry schedule has to outlast an API throttling burst: a suite fan-out
    starts ~20 MicroVMs within seconds and every runner's first call is
    ``GET /usecase/{id}`` against a Lambda with a small reserved concurrency,
    so API Gateway answers 500/429 for several seconds.  The module-level
    ``recorded_sleeps`` fixture patches the waits out and records them so the
    schedule can be asserted without sleeping.
    """

    @pytest.fixture(autouse=True)
    def _sleeps(self, recorded_sleeps):
        self.sleeps = recorded_sleeps

    def test_429_triggers_retry_then_succeeds(self):
        client = _make_client()
        throttled = _mock_response(429, {"message": "Too many requests"}, text="Too many requests")
        success = _mock_response(200, {"ok": True})
        with patch.object(client._session, "request", side_effect=[throttled, success]):
            result = client.get("/test")
            assert result == {"ok": True}
            assert client._session.request.call_count == 2

    def test_500_triggers_retry_then_succeeds(self):
        client = _make_client()
        error = _mock_response(500, {"message": "Internal server error"}, text="error")
        success = _mock_response(200, {"data": 1})
        with patch.object(client._session, "request", side_effect=[error, success]):
            result = client.get("/test")
            assert result == {"data": 1}
            assert client._session.request.call_count == 2

    def test_502_503_504_trigger_retry(self):
        client = _make_client()
        for code in (502, 503, 504):
            error = _mock_response(code, {"message": "gateway error"}, text="err")
            success = _mock_response(200, {"ok": True})
            with patch.object(client._session, "request", side_effect=[error, success]):
                result = client.get("/test")
                assert result == {"ok": True}

    def test_400_does_not_retry(self):
        client = _make_client()
        bad_request = _mock_response(400, {"message": "Bad request"}, text="Bad request")
        with patch.object(client._session, "request", return_value=bad_request):
            with pytest.raises(ApiError) as exc_info:
                client.get("/test")
            assert exc_info.value.status_code == 400
            assert client._session.request.call_count == 1

    def test_401_does_not_retry(self):
        client = _make_client()
        unauthorized = _mock_response(401, {"message": "Unauthorized"}, text="Unauthorized")
        with patch.object(client._session, "request", return_value=unauthorized):
            with pytest.raises(ApiError) as exc_info:
                client.get("/test")
            assert exc_info.value.status_code == 401
            assert client._session.request.call_count == 1

    def test_403_does_not_retry(self):
        client = _make_client()
        forbidden = _mock_response(403, {"message": "Forbidden"}, text="Forbidden")
        with patch.object(client._session, "request", return_value=forbidden):
            with pytest.raises(ApiError) as exc_info:
                client.get("/test")
            assert exc_info.value.status_code == 403
            assert client._session.request.call_count == 1

    def test_connection_error_triggers_retry(self):
        client = _make_client()
        success = _mock_response(200, {"ok": True})
        with patch.object(client._session, "request", side_effect=[requests.ConnectionError("reset"), success]):
            result = client.get("/test")
            assert result == {"ok": True}
            assert client._session.request.call_count == 2

    def test_timeout_error_triggers_retry(self):
        client = _make_client()
        success = _mock_response(200, {"ok": True})
        with patch.object(client._session, "request", side_effect=[requests.Timeout("timed out"), success]):
            result = client.get("/test")
            assert result == {"ok": True}
            assert client._session.request.call_count == 2

    def test_max_retries_exhausted_raises_api_error(self):
        client = _make_client()
        error = _mock_response(500, {"message": "Internal server error"}, text="error")
        with patch.object(client._session, "request", return_value=error):
            with pytest.raises(ApiError) as exc_info:
                client.get("/test")
            assert exc_info.value.status_code == 500
            assert client._session.request.call_count == RETRY_ATTEMPTS
        assert len(self.sleeps) == RETRY_ATTEMPTS - 1

    def test_schedule_outlasts_a_throttling_burst(self):
        """Total wait before giving up must cover a fan-out burst (tens of seconds),
        not the ~3 s the old 3-attempt schedule allowed."""
        assert RETRY_ATTEMPTS >= 6
        client = _make_client()
        error = _mock_response(500, {"message": "Internal server error"}, text="error")
        with patch.object(client._session, "request", return_value=error):
            with pytest.raises(ApiError):
                client.get("/test")
        assert sum(self.sleeps) >= 30

    def test_waits_grow_exponentially_with_jitter_and_are_capped(self):
        client = _make_client()
        error = _mock_response(429, {"message": "Too many requests"}, text="throttled")
        with patch.object(client._session, "request", return_value=error):
            with pytest.raises(ApiError):
                client.get("/test")
        base = [RETRY_WAIT_MIN_S * 2 ** n for n in range(len(self.sleeps))]
        for actual, expected in zip(self.sleeps, base):
            capped = min(expected, RETRY_WAIT_MAX_S)
            assert capped <= actual <= capped + RETRY_JITTER_MAX_S, (self.sleeps, base)
        assert self.sleeps[-1] <= RETRY_WAIT_MAX_S + RETRY_JITTER_MAX_S

    def test_recovers_late_in_the_schedule(self):
        client = _make_client()
        error = _mock_response(500, {"message": "Internal server error"}, text="error")
        success = _mock_response(200, {"ok": True})
        with patch.object(client._session, "request", side_effect=[error] * (RETRY_ATTEMPTS - 1) + [success]):
            assert client.get("/test") == {"ok": True}
            assert client._session.request.call_count == RETRY_ATTEMPTS

    def test_each_retry_is_logged_with_attempt_and_wait(self, caplog):
        client = _make_client()
        error = _mock_response(500, {"message": "Internal server error"}, text="error")
        success = _mock_response(200, {"ok": True})
        with caplog.at_level(logging.WARNING, logger="qa_studio_cli.api.client"), \
                patch.object(client._session, "request", side_effect=[error, error, success]):
            client.get("/test")
        retry_lines = [r.getMessage() for r in caplog.records if "retry" in r.getMessage().lower() and "/" in r.getMessage()]
        assert any(f"1/{RETRY_ATTEMPTS}" in line for line in retry_lines), caplog.text
        assert any(f"2/{RETRY_ATTEMPTS}" in line for line in retry_lines), caplog.text


# ---------------------------------------------------------------------------
# Worker execution capability header (H-2)
# ---------------------------------------------------------------------------


class TestExecutionTokenHeader:
    def test_header_sent_when_env_var_set(self, monkeypatch):
        monkeypatch.setenv("QA_STUDIO_EXECUTION_TOKEN", "uc-1:ex-1:secret-token")
        client = _make_client()
        with patch.object(client._session, "request", return_value=_mock_response(200, {})):
            client.get("/usecase/uc-1")
            headers = client._session.request.call_args.kwargs["headers"]
        assert headers["X-QA-Execution-Token"] == "uc-1:ex-1:secret-token"
        assert headers["Authorization"] == "Bearer tok"

    def test_header_absent_without_env_var(self, monkeypatch):
        monkeypatch.delenv("QA_STUDIO_EXECUTION_TOKEN", raising=False)
        client = _make_client()
        with patch.object(client._session, "request", return_value=_mock_response(200, {})):
            client.post("/usecase/uc-1/execute")
            headers = client._session.request.call_args.kwargs["headers"]
        assert "X-QA-Execution-Token" not in headers

    def test_empty_env_var_not_sent(self, monkeypatch):
        monkeypatch.setenv("QA_STUDIO_EXECUTION_TOKEN", "")
        client = _make_client()
        with patch.object(client._session, "request", return_value=_mock_response(200, {})):
            client.patch("/x", {})
            headers = client._session.request.call_args.kwargs["headers"]
        assert "X-QA-Execution-Token" not in headers

    def test_token_never_logged(self, monkeypatch, caplog):
        monkeypatch.setenv("QA_STUDIO_EXECUTION_TOKEN", "uc-1:ex-1:very-secret-value")
        client = _make_client()
        with caplog.at_level("DEBUG"), \
                patch.object(client._session, "request", return_value=_mock_response(200, {})):
            client.get("/usecase/uc-1")
        assert "very-secret-value" not in caplog.text
