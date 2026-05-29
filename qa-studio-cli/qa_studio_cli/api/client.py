"""Authenticated HTTP client and require_auth decorator for QA Studio API."""

import functools
import logging
from typing import Callable, Optional

import click
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from qa_studio_cli.auth.token_manager import get_valid_token
from qa_studio_cli.models.errors import ApiError, AuthError, ConfigError
from qa_studio_cli.config.manager import config_exists, load_config
from qa_studio_cli.models.config import CLIConfig

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class _RetryableError(Exception):
    """Internal: triggers tenacity retry, never surfaces to callers."""
    def __init__(self, api_error: ApiError):
        self.api_error = api_error


def build_api_client(
    *,
    token_file: Optional[str] = None,
    config: Optional[CLIConfig] = None,
) -> "ApiClient":
    """Construct an ``ApiClient`` using the full token-resolution chain.

    Used by the runner and the TUI; the interactive Click commands go
    through :func:`require_auth` instead, which is bound to the Click
    context and uses the stored-user-token path directly.

    Args:
        token_file: Optional path to a pre-generated token JSON file
            (``--token-file`` in the runner).
        config: Optional pre-loaded :class:`CLIConfig`; loads from
            ``~/.qa-studio/config.json`` when ``None``.

    Returns:
        An authenticated :class:`ApiClient` pointed at the configured
        API URL.
    """
    # Imported here (not at module top) because ``auth.resolver``
    # imports providers that only make sense when called, and we want
    # the import cost to land with the function call, not at module
    # import time.
    from qa_studio_cli.auth.resolver import TokenResolver

    cfg = config or load_config()
    resolver = TokenResolver(token_file=token_file, config=cfg)
    return ApiClient(base_url=cfg.api_url, token_provider=resolver.get_token)


class ApiClient:
    """Unified HTTP client for QA Studio API.

    Uses ``requests.Session`` for connection pooling and calls
    ``token_provider()`` on every request so tokens can be refreshed
    transparently (client-credentials, token-file, stored user token).
    """

    def __init__(self, base_url: str, token_provider: Callable[[], str]):
        """
        Args:
            base_url: API base URL without /api suffix.
            token_provider: Callable returning a valid access token string.
                            Called on every request to support token refresh.
        """
        self.base_url = base_url.rstrip("/")
        self._token_provider = token_provider
        self._session = requests.Session()

    def get(self, path: str, params: dict | None = None) -> dict:
        """Send authenticated GET request. Returns parsed JSON."""
        response = self._request("GET", path, params=params)
        return response.json()

    def post(self, path: str, json_body: dict | None = None, params: dict | None = None) -> dict:
        """Send authenticated POST request. Returns parsed JSON."""
        response = self._request("POST", path, json=json_body, params=params)
        return response.json()

    def patch(self, path: str, json_body: dict | None = None) -> dict:
        """Send authenticated PATCH request. Returns parsed JSON."""
        response = self._request("PATCH", path, json=json_body)
        return response.json()

    def delete(self, path: str) -> dict | None:
        """Send authenticated DELETE request. Returns parsed JSON or None for 204."""
        response = self._request("DELETE", path)
        if response.status_code == 204:
            return None
        return response.json()

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Send request with auth headers, retry on transient failures."""
        try:
            return self._request_with_retry(method, path, **kwargs)
        except _RetryableError as e:
            raise e.api_error

    @retry(
        retry=retry_if_exception_type(_RetryableError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    def _request_with_retry(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        token = self._token_provider()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        logger.info("→ %s %s", method, url)
        try:
            response = self._session.request(method, url, headers=headers, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            logger.warning("Transient error, will retry: %s", e)
            raise _RetryableError(ApiError(0, f"Connection error: {e}"))

        logger.debug("← %s %s", response.status_code, response.text[:500])

        if not response.ok:
            if response.status_code in RETRYABLE_STATUS_CODES:
                logger.warning("Retryable %s from %s %s", response.status_code, method, url)
                try:
                    body = response.json()
                except Exception:
                    body = {}
                raise _RetryableError(ApiError(response.status_code, body.get("message", response.text), response_data=body))
            self._handle_error(response)

        return response

    def _handle_error(self, response: requests.Response) -> None:
        """Map HTTP status codes to ApiError with actionable messages."""
        status = response.status_code

        try:
            body = response.json()
        except Exception:
            body = {}

        error_code = body.get("code")

        if status == 401:
            raise ApiError(401, "Session expired. Run 'qa-studio login' to re-authenticate.", response_data=body)
        if status == 403:
            detail = body.get("message", "")
            msg = "Insufficient permissions."
            if detail:
                msg += f" {detail}"
            logger.debug("403 response body: %s", body)
            raise ApiError(403, msg, error_code=error_code, response_data=body)
        if status == 404:
            raise ApiError(404, "Resource not found.", response_data=body)

        message = body.get("message", response.text)
        raise ApiError(status, message, error_code=error_code, response_data=body)


def require_auth(fn):
    """Decorator: load config, get token, create ApiClient, pass via ctx.obj."""

    @functools.wraps(fn)
    @click.pass_context
    def wrapper(ctx, *args, **kwargs):
        if not config_exists():
            click.echo("Configuration not found. Run 'qa-studio configure' first.", err=True)
            raise SystemExit(1)
        try:
            config = load_config()
        except ConfigError as e:
            click.echo(f"Configuration error: {e.message}", err=True)
            raise SystemExit(1)

        try:
            # Validate token is available before creating client
            get_valid_token()
        except AuthError as e:
            click.echo(f"{e.message}", err=True)
            raise SystemExit(1)

        ctx.ensure_object(dict)
        ctx.obj["client"] = ApiClient(
            base_url=config.api_url,
            token_provider=get_valid_token,
        )
        return ctx.invoke(fn, *args, **kwargs)

    return wrapper
