"""Client-side validation for QA Studio CLI.

Network-assertion body-size cap
-------------------------------
The server-side validators (``web-app/lambdas/endpoints/utils.py``) and the
worker (``web-app/worker/network_matcher.py``) read the cap from the
``NETWORK_ASSERTION_BODY_MAX_BYTES`` environment variable configured via
``configuration.json`` at deploy time.  The CLI runs on developer machines
and cannot see that environment, so it uses a fixed 1 MiB default for
pre-submit validation.

Consequence: a deployment that raises the cap server-side will accept
payloads the CLI rejected locally.  A deployment that lowers the cap
server-side will reject payloads the CLI accepted locally; in that case the
server's ``400`` response is authoritative and surfaces a clear error.
"""

import json
import re
from urllib.parse import urlparse


VALID_BROWSER_ACTIONS = {"reload", "back", "forward", "navigate"}

VALID_TRANSFORM_OPERATIONS = {
    "math", "round", "floor", "ceil", "abs", "min", "max",
    "concat", "upper", "lower", "trim", "replace", "substring", "length",
    "to_number", "to_string", "to_int", "regex_extract", "format",
}


def validate_step(step: dict) -> tuple[bool, list[str]]:
    """Validate a step dict based on its step_type.

    Returns (is_valid, errors).  Only validates step types that have
    dedicated validators; other step types pass through.
    """
    step_type = step.get("step_type", "")
    if step_type == "browser":
        return validate_browser_step(step)
    if step_type == "transform":
        return validate_transform_step(step)
    if step_type == "network_assertion":
        return validate_network_assertion_step(step)
    return True, []


def validate_browser_step(step: dict) -> tuple[bool, list[str]]:
    """Validate a browser step."""
    errors: list[str] = []
    action = step.get("browser_action")
    if not action:
        errors.append("browser_action is required for browser steps")
        return False, errors
    if action not in VALID_BROWSER_ACTIONS:
        errors.append(
            f"Invalid browser_action '{action}'. Must be one of: {', '.join(sorted(VALID_BROWSER_ACTIONS))}"
        )
    args_raw = step.get("browser_args")
    if args_raw:
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except (json.JSONDecodeError, TypeError):
            errors.append("browser_args must be valid JSON")
            return len(errors) == 0, errors
        if action == "navigate" and not args.get("url"):
            errors.append("browser_args.url is required for navigate action")
    elif action == "navigate":
        errors.append("browser_args with url is required for navigate action")
    return len(errors) == 0, errors


def validate_transform_step(step: dict) -> tuple[bool, list[str]]:
    """Validate a transform step."""
    errors: list[str] = []
    operation = step.get("transform_operation")
    if not operation:
        errors.append("transform_operation is required for transform steps")
        return False, errors
    if operation not in VALID_TRANSFORM_OPERATIONS:
        errors.append(
            f"Invalid transform_operation '{operation}'. Must be one of: {', '.join(sorted(VALID_TRANSFORM_OPERATIONS))}"
        )
    if not step.get("capture_variable"):
        errors.append("capture_variable is required for transform steps")
    args_raw = step.get("transform_args")
    if not args_raw:
        errors.append("transform_args is required for transform steps")
    else:
        try:
            json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except (json.JSONDecodeError, TypeError):
            errors.append("transform_args must be valid JSON")
    return len(errors) == 0, errors

# Step-level validation — network_assertion
# ---------------------------------------------------------------------------

_NETWORK_ASSERTION_ALLOWED_METHODS = {
    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS",
}
# Request side accepts all three match types.
_NETWORK_ASSERTION_REQUEST_MATCH_TYPES = {"exact", "subset", "schema"}
# Response side rejects "exact" — response payloads frequently contain
# non-deterministic values (timestamps, generated ids, ordering) and strict
# equality is a known footgun.  Users who need tight response checks express
# them via a schema with ``const`` or via subset.
_NETWORK_ASSERTION_RESPONSE_MATCH_TYPES = {"subset", "schema"}
_NETWORK_ASSERTION_MAX_BODY_BYTES = 1_048_576  # 1 MiB
_NETWORK_ASSERTION_MIN_TIMEOUT = 1
_NETWORK_ASSERTION_MAX_TIMEOUT = 120
_EXTERNAL_REF_PREFIXES = ("http://", "https://", "file://")
_MIN_HTTP_STATUS = 100
_MAX_HTTP_STATUS = 599


def validate_network_assertion_step(step: dict) -> tuple[bool, list[str]]:
    """Validate a ``network_assertion`` step.

    Rules mirror the server-side validation:
      - URL pattern required.
      - Method allow-list.
      - Body / mock size caps (1 MiB on the CLI — see module docstring).
      - JSON validity for body fields; when match-type is ``schema``, the
        document must also be a JSON object and must not contain external
        ``$ref`` (SSRF / file-read protection).
      - Match-type allow-list: request-side ∈ {exact, subset, schema};
        response-side ∈ {subset, schema} (``exact`` is rejected on the
        response side per R14).
      - Timeout range [1, 120] seconds.
      - Response status integer in [100, 599].
    """
    errors: list[str] = []

    url_pattern = step.get("network_url_pattern")
    if not url_pattern or not str(url_pattern).strip():
        errors.append("network_url_pattern is required for network_assertion steps")

    method = step.get("network_method")
    if method is not None and method != "":
        if str(method).upper() not in _NETWORK_ASSERTION_ALLOWED_METHODS:
            errors.append(
                "network_method must be one of: "
                f"{', '.join(sorted(_NETWORK_ASSERTION_ALLOWED_METHODS))}"
            )

    # Request-side match type.
    req_match_type = step.get("network_body_match_type")
    if req_match_type is not None and req_match_type != "":
        normalized = str(req_match_type).lower()
        if normalized not in _NETWORK_ASSERTION_REQUEST_MATCH_TYPES:
            errors.append(
                "network_body_match_type must be one of: "
                f"{', '.join(sorted(_NETWORK_ASSERTION_REQUEST_MATCH_TYPES))}"
            )
        req_match_type = normalized
    else:
        req_match_type = None

    body = step.get("network_request_body")
    if body:
        _validate_json_field(
            body, "network_request_body", errors,
            is_schema=(req_match_type == "schema"),
        )

    mock = step.get("network_mock_response")
    if mock:
        _validate_json_field(mock, "network_mock_response", errors, require_object=True)

    timeout = step.get("network_timeout")
    if timeout is not None:
        try:
            timeout_int = int(timeout)
        except (TypeError, ValueError):
            errors.append("network_timeout must be an integer")
        else:
            if timeout_int < _NETWORK_ASSERTION_MIN_TIMEOUT or timeout_int > _NETWORK_ASSERTION_MAX_TIMEOUT:
                errors.append(
                    f"network_timeout must be between {_NETWORK_ASSERTION_MIN_TIMEOUT} "
                    f"and {_NETWORK_ASSERTION_MAX_TIMEOUT} seconds"
                )

    # Response-side match type — no ``exact``.
    resp_match_type = step.get("network_response_body_match_type")
    if resp_match_type is not None and resp_match_type != "":
        normalized = str(resp_match_type).lower()
        if normalized not in _NETWORK_ASSERTION_RESPONSE_MATCH_TYPES:
            errors.append(
                "network_response_body_match_type must be one of: "
                f"{', '.join(sorted(_NETWORK_ASSERTION_RESPONSE_MATCH_TYPES))} "
                '("exact" is not permitted on the response side)'
            )
        resp_match_type = normalized
    else:
        resp_match_type = None

    resp_body = step.get("network_response_body")
    if resp_body:
        _validate_json_field(
            resp_body, "network_response_body", errors,
            is_schema=(resp_match_type == "schema"),
        )

    status = step.get("network_response_status")
    if status is not None:
        try:
            status_int = int(status)
        except (TypeError, ValueError):
            errors.append("network_response_status must be an integer")
        else:
            if status_int < _MIN_HTTP_STATUS or status_int > _MAX_HTTP_STATUS:
                errors.append(
                    f"network_response_status must be between "
                    f"{_MIN_HTTP_STATUS} and {_MAX_HTTP_STATUS}"
                )

    return len(errors) == 0, errors


def _validate_json_field(
    raw: str,
    field_name: str,
    errors: list[str],
    *,
    require_object: bool = False,
    is_schema: bool = False,
) -> None:
    """Shared JSON + size validator used by network_assertion fields.

    When ``is_schema=True`` the parsed document is additionally checked:
    must be a JSON object, and must not contain ``$ref`` entries targeting
    external URIs (SSRF + file-read protection).  Structural Draft 2020-12
    validity is not performed here — that lives in the runner which has the
    ``jsonschema`` dependency via the ``[runner]`` extras.
    """
    if not isinstance(raw, str):
        errors.append(f"{field_name} must be a JSON string")
        return
    size = len(raw.encode("utf-8"))
    if size > _NETWORK_ASSERTION_MAX_BODY_BYTES:
        errors.append(
            f"{field_name} exceeds maximum size "
            f"({size} > {_NETWORK_ASSERTION_MAX_BODY_BYTES} bytes)"
        )
        return
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError) as exc:
        errors.append(f"{field_name} is not valid JSON: {exc}")
        return
    if require_object and not isinstance(parsed, dict):
        errors.append(f"{field_name} must be a JSON object")
        return
    if is_schema:
        if not isinstance(parsed, dict):
            errors.append(f"{field_name} must be a JSON object (schema document)")
            return
        try:
            _reject_external_refs(parsed, field_name)
        except ValueError as exc:
            errors.append(str(exc))


def _reject_external_refs(node, context: str, path: str = "") -> None:
    """Reject ``$ref`` entries pointing at external URIs.

    Walks nested dicts and lists.  Raises ``ValueError`` on the first
    offender.  Only local-pointer refs (values beginning with ``#``) are
    accepted; anything else (URLs, file paths, bare identifiers) is
    rejected.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            key_path = f"{path}.{key}" if path else key
            if key == "$ref" and isinstance(value, str):
                if value.startswith(_EXTERNAL_REF_PREFIXES):
                    raise ValueError(
                        f"{context}: external $ref not allowed at {key_path}: {value}"
                    )
                if not value.startswith("#"):
                    raise ValueError(
                        f"{context}: only local-pointer $ref is allowed at {key_path}: {value}"
                    )
            else:
                _reject_external_refs(value, context, key_path)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _reject_external_refs(item, context, f"{path}[{i}]")


def validate_journey_description(journey: str) -> tuple[bool, list[str]]:
    """
    Validate user journey description against API requirements.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    if not journey or not journey.strip():
        errors.append("User journey description is required")
        return False, errors
    
    journey = journey.strip()
    
    # Length validation
    if len(journey) < 50:
        errors.append(f"User journey must be at least 50 characters (currently {len(journey)})")
    
    if len(journey) > 2000:
        errors.append(f"User journey must be 2000 characters or less (currently {len(journey)})")
    
    # Word count validation
    words = journey.split()
    if len(words) < 10:
        errors.append(f"User journey should contain at least 10 words (currently {len(words)})")
    
    return len(errors) == 0, errors


def validate_url(url: str) -> tuple[bool, list[str]]:
    """
    Validate starting URL.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    if not url or not url.strip():
        errors.append("Starting URL is required")
        return False, errors
    
    url = url.strip()
    
    try:
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            errors.append("Invalid URL format. Must include protocol (http:// or https://)")
    except Exception:
        errors.append("Invalid URL format")
    
    return len(errors) == 0, errors


def validate_title(title: str) -> tuple[bool, list[str]]:
    """
    Validate test title.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    if not title or not title.strip():
        errors.append("Title is required")
        return False, errors
    
    title = title.strip()
    
    if len(title) < 3:
        errors.append(f"Title must be at least 3 characters (currently {len(title)})")
    
    if len(title) > 100:
        errors.append(f"Title must be 100 characters or less (currently {len(title)})")
    
    return len(errors) == 0, errors


VALID_REGIONS = ['us-east-1', 'us-west-2', 'ap-southeast-2', 'eu-central-1']


def validate_region(region: str) -> tuple[bool, list[str]]:
    """
    Validate AWS region.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    if not region or not region.strip():
        errors.append("Region is required")
        return False, errors
    
    if region not in VALID_REGIONS:
        errors.append(f"Invalid region. Must be one of: {', '.join(VALID_REGIONS)}")
    
    return len(errors) == 0, errors
