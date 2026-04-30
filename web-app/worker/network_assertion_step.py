"""Worker step executor for `network_assertion` steps.

A network_assertion step couples a Nova Act UI action with HTTP request
observation, optional mocking, and optional response-side assertion.
Typical flow:

1. Optionally register a Playwright route handler that mocks the response
   (static fulfill or passthrough-with-overrides).
2. Start waiting for a response matching the URL pattern.
3. Execute the Nova Act instruction (e.g. "Click the Submit button").
4. Await the response.
5. Optionally assert the request method and request body (exact / subset /
   schema).
6. Capture the response body (size-checked against the configured cap).
7. Optionally assert the response status and response body (subset / schema;
   ``exact`` is not permitted on the response side).
8. Always clean up the route handler in a ``finally`` block so stale
   interception does not leak into subsequent steps.

Caching: this step type is intentionally not cached.  Network interception
setup and assertion always run fresh — the whole point is to observe the
live HTTP traffic, which a cache hit would mask.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any, Optional, Tuple

from models import ExecutionStep
from network_matcher import (
    MAX_BODY_SIZE,
    match_exact,
    match_schema,
    match_subset,
    validate_body_size,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15
MAX_TIMEOUT_SECONDS = 120
_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_REQUEST_MATCH_TYPES = {"exact", "subset", "schema"}
# Response side explicitly rejects "exact" — see R14 in the spec.
_RESPONSE_MATCH_TYPES = {"subset", "schema"}
_LOG_BODY_MAX_CHARS = 500
_MIN_HTTP_STATUS = 100
_MAX_HTTP_STATUS = 599


def execute_network_assertion_step(
    nova,
    step: ExecutionStep,
) -> Tuple[Any, bool, str, str]:
    """Execute a network_assertion step.

    Returns: ``(result, success, logs, actual_value)`` — matches the shape
    of other assertion-style steps.  ``actual_value`` is a short match
    summary string (never the raw captured body) safe to persist in
    DynamoDB and display in the UI.
    """

    # --- 1. Validate + parse configuration -------------------------------
    url_pattern = step.network_url_pattern
    if not url_pattern:
        return _error("network_url_pattern is required for network_assertion steps")

    method_expected = (step.network_method or "").upper() or None
    if method_expected is not None and method_expected not in _ALLOWED_METHODS:
        return _error(f"invalid network_method: {method_expected!r}")

    # Request-side match type — default to "exact" for backwards compat
    # with steps authored before schema mode existed.
    req_match_type = (step.network_body_match_type or "exact").lower()
    if step.network_request_body and req_match_type not in _REQUEST_MATCH_TYPES:
        return _error(f"invalid network_body_match_type: {req_match_type!r}")

    ok, err = validate_body_size(step.network_request_body)
    if not ok:
        return _error(f"network_request_body: {err}")

    ok, err = validate_body_size(step.network_mock_response)
    if not ok:
        return _error(f"network_mock_response: {err}")

    # Response-side match type defaults to "subset" when only the response
    # body is set without an explicit match type.
    resp_match_type = (step.network_response_body_match_type or "").lower() or None
    if step.network_response_body and resp_match_type is None:
        resp_match_type = "subset"
    if resp_match_type is not None and resp_match_type not in _RESPONSE_MATCH_TYPES:
        return _error(
            f"invalid network_response_body_match_type: {resp_match_type!r} "
            '("exact" is not permitted on the response side)'
        )

    ok, err = validate_body_size(step.network_response_body)
    if not ok:
        return _error(f"network_response_body: {err}")

    status_expected: Optional[int] = None
    if step.network_response_status is not None:
        try:
            status_expected = int(step.network_response_status)
        except (TypeError, ValueError):
            return _error("network_response_status must be an integer")
        if status_expected < _MIN_HTTP_STATUS or status_expected > _MAX_HTTP_STATUS:
            return _error(
                f"network_response_status must be between "
                f"{_MIN_HTTP_STATUS} and {_MAX_HTTP_STATUS}"
            )

    mock_cfg: Optional[dict] = None
    if step.network_mock_response:
        try:
            mock_cfg = json.loads(step.network_mock_response)
        except (json.JSONDecodeError, TypeError) as exc:
            return _error(f"network_mock_response is not valid JSON: {exc}")
        if not isinstance(mock_cfg, dict):
            return _error("network_mock_response must be a JSON object")

    timeout_s = _resolve_timeout(step.network_timeout)
    timeout_ms = timeout_s * 1000

    passthrough = bool(step.network_mock_passthrough)
    mode = _describe_mode(
        has_mock=mock_cfg is not None,
        has_request_body=bool(step.network_request_body),
        has_method=method_expected is not None,
        has_response_body=bool(step.network_response_body),
        has_status=status_expected is not None,
    )
    logger.info(
        "network_assertion step %s: pattern=%s mode=%s timeout=%ss",
        step.sort, url_pattern, mode, timeout_s,
    )

    page = getattr(nova, "page", None)
    if page is None:
        return _error("nova.page is not available; cannot set up network interception")

    # --- 2. Execute with guaranteed cleanup ------------------------------
    route_registered = False
    try:
        if mock_cfg is not None:
            handler = _build_route_handler(mock_cfg, passthrough)
            page.route(url_pattern, handler)
            route_registered = True

        # expect_response is a context manager that starts listening BEFORE
        # the action and resolves with the response once the action triggers
        # the matching request.
        with page.expect_response(url_pattern, timeout=timeout_ms) as response_info:
            try:
                act_result = nova.act(step.instruction)
            except Exception as exc:  # noqa: BLE001
                logger.error("network_assertion step %s: Nova Act failed: %s", step.sort, exc)
                return _error(f"Nova Act action failed: {exc}", act_exc=exc)

        response = response_info.value
        request = response.request

        summary_parts: list[str] = []

        # --- 3. Request-side: method assertion --------------------------
        if method_expected is not None:
            actual_method = (request.method or "").upper()
            if actual_method != method_expected:
                msg = f"method mismatch: expected {method_expected}, got {actual_method}"
                return _failed(act_result, msg, f"method={actual_method}:fail")
            summary_parts.append(f"method={method_expected}")

        # --- 4. Request-side: body assertion ----------------------------
        if step.network_request_body:
            captured_body = _capture_request_body(request)
            logger.info(
                "network_assertion step %s: captured %s %s body=%s",
                step.sort, request.method, request.url,
                _truncate_for_log(captured_body),
            )
            ok, diff = _match_request_body(
                req_match_type, step.network_request_body, captured_body,
            )
            if not ok:
                return _failed(
                    act_result, f"request body mismatch ({req_match_type}): {diff}",
                    f"body_match={req_match_type}:fail",
                )
            summary_parts.append(f"body_match={req_match_type}:pass")
        else:
            logger.info(
                "network_assertion step %s: captured %s %s",
                step.sort, request.method, request.url,
            )

        # --- 5. Response capture (always, for size check) ---------------
        # Size-check always runs when a response was captured — an oversized
        # response reports eagerly rather than silently passing until a
        # later change adds a body assertion (see requirements R14).
        captured_response_body = _capture_response_body(response)
        if captured_response_body is not None:
            body_bytes = len(captured_response_body.encode("utf-8"))
            if body_bytes > MAX_BODY_SIZE:
                return _failed(
                    act_result,
                    f"captured response body size {body_bytes} exceeds maximum {MAX_BODY_SIZE} bytes",
                    "resp_body=cap:fail",
                )

        # --- 6. Response-side: status assertion -------------------------
        if status_expected is not None:
            actual_status = getattr(response, "status", None)
            try:
                actual_status_int = int(actual_status) if actual_status is not None else None
            except (TypeError, ValueError):
                actual_status_int = None
            if actual_status_int != status_expected:
                msg = (
                    f"response status mismatch: expected {status_expected}, "
                    f"got {actual_status!r}"
                )
                return _failed(
                    act_result, msg, f"resp_status={actual_status_int or actual_status}:fail",
                )
            summary_parts.append(f"resp_status={status_expected}")

        # --- 7. Response-side: body assertion ---------------------------
        if step.network_response_body:
            logger.info(
                "network_assertion step %s: captured response status=%s body=%s",
                step.sort,
                getattr(response, "status", "?"),
                _truncate_for_log(captured_response_body),
            )
            ok, diff = _match_response_body(
                resp_match_type, step.network_response_body, captured_response_body,
            )
            if not ok:
                return _failed(
                    act_result, f"response body mismatch ({resp_match_type}): {diff}",
                    f"resp_body={resp_match_type}:fail",
                )
            summary_parts.append(f"resp_body={resp_match_type}:pass")

        # --- 8. Success --------------------------------------------------
        summary = " ".join(summary_parts) if summary_parts else "captured"
        logger.info("network_assertion step %s passed (%s)", step.sort, summary)
        return act_result, True, "", summary

    except Exception as exc:  # noqa: BLE001 — includes Playwright TimeoutError
        err_name = type(exc).__name__
        if "Timeout" in err_name:
            msg = f"no request matched '{url_pattern}' within {timeout_s}s"
        else:
            msg = f"{err_name}: {exc}"
        logger.error("network_assertion step %s failed: %s", step.sort, msg)
        return None, False, msg, f"error:{err_name}"

    finally:
        if route_registered:
            try:
                page.unroute(url_pattern)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "network_assertion step %s: failed to unroute %s: %s",
                    step.sort, url_pattern, exc,
                )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_timeout(value: Optional[int]) -> int:
    if value is None:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    if ivalue <= 0:
        return DEFAULT_TIMEOUT_SECONDS
    return min(ivalue, MAX_TIMEOUT_SECONDS)


def _describe_mode(
    *,
    has_mock: bool,
    has_request_body: bool,
    has_method: bool,
    has_response_body: bool,
    has_status: bool,
) -> str:
    """Short human-readable mode string for the step-start log line."""
    has_request_assertion = has_request_body or has_method
    has_response_assertion = has_response_body or has_status
    parts = []
    if has_mock:
        parts.append("mock")
    if has_request_assertion:
        parts.append("assert-req")
    if has_response_assertion:
        parts.append("assert-resp")
    return "+".join(parts) if parts else "observe-only"


def _build_route_handler(mock_cfg: dict, passthrough: bool):
    """Build a Playwright route handler closure."""

    def _serialize_body(body: Any) -> str:
        if body is None:
            return ""
        if isinstance(body, (bytes, bytearray)):
            return body.decode("utf-8", errors="replace")
        if isinstance(body, str):
            return body
        return json.dumps(body)

    status = mock_cfg.get("status", 200)
    mock_body = mock_cfg.get("body")
    mock_headers = mock_cfg.get("headers") or {}

    if passthrough:
        def handler(route):
            real = route.fetch()
            merged_headers = {**(real.headers or {}), **mock_headers}
            if "body" in mock_cfg:
                merged_body = _serialize_body(mock_body)
            else:
                merged_body = real.body()
            merged_status = mock_cfg.get("status", real.status)
            route.fulfill(
                status=merged_status,
                body=merged_body,
                headers=merged_headers,
            )
    else:
        def handler(route):
            route.fulfill(
                status=status,
                body=_serialize_body(mock_body),
                headers=mock_headers,
            )

    return handler


def _capture_request_body(request) -> Optional[str]:
    """Extract the request body as a string, tolerating missing data."""
    try:
        data = request.post_data
    except Exception:  # noqa: BLE001
        return None
    if data is None:
        return None
    if isinstance(data, (bytes, bytearray)):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _capture_response_body(response) -> Optional[str]:
    """Extract the response body as a UTF-8 string, tolerating missing data.

    Playwright's ``Response.body()`` returns bytes.  For matching (subset /
    schema), we parse as JSON downstream, so a best-effort UTF-8 decode is
    sufficient here.
    """
    try:
        data = response.body()
    except Exception:  # noqa: BLE001
        return None
    if data is None:
        return None
    if isinstance(data, (bytes, bytearray)):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _match_request_body(
    match_type: str, expected_json: str, actual_body: Optional[str],
) -> Tuple[bool, str]:
    if actual_body is None:
        return False, "captured request had no body"
    return _dispatch_matcher(match_type, expected_json, actual_body)


def _match_response_body(
    match_type: str, expected_json: str, actual_body: Optional[str],
) -> Tuple[bool, str]:
    if actual_body is None:
        return False, "captured response had no body"
    return _dispatch_matcher(match_type, expected_json, actual_body)


def _dispatch_matcher(
    match_type: str, expected_json: str, actual_body: str,
) -> Tuple[bool, str]:
    if match_type == "schema":
        return match_schema(expected_json, actual_body)
    if match_type == "subset":
        return match_subset(expected_json, actual_body)
    return match_exact(expected_json, actual_body)


def _truncate_for_log(body: Optional[str]) -> str:
    """Return a log-safe representation of a request / response body.

    Full bodies are never logged; they can contain secrets.
    """
    if not body:
        return "<empty>"
    if len(body) <= _LOG_BODY_MAX_CHARS:
        return body
    return body[:_LOG_BODY_MAX_CHARS] + f"...<truncated {len(body) - _LOG_BODY_MAX_CHARS} chars>"


def _error(message: str, act_exc: Optional[Exception] = None) -> Tuple[Any, bool, str, str]:
    """Build a failure tuple with a minimal result object for downstream safety."""
    result = SimpleNamespace()
    result.metadata = SimpleNamespace()
    result.metadata.act_id = (
        act_exc.metadata.act_id
        if act_exc is not None and hasattr(act_exc, "metadata") and hasattr(act_exc.metadata, "act_id")
        else "error"
    )
    return result, False, message, "error:validation" if act_exc is None else "error:nova_act"


def _failed(act_result: Any, message: str, summary: str) -> Tuple[Any, bool, str, str]:
    return act_result, False, message, summary


# Size cap constant re-exported for the dispatcher's convenience
__all__ = ["execute_network_assertion_step", "MAX_BODY_SIZE"]
