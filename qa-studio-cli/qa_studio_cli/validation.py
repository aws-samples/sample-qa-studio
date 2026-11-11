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
    "parse_date", "format_date", "add_duration", "date_diff", "to_epoch",
}

# Operators allowed when ``validation_type == "date"``. Mirrors
# ``transform.date_compare.DATE_OPERATORS``; the cross-package consistency
# test in ``test_transform_registry_consistency.py`` verifies the runtime
# helper stays in sync. This client-side set is intentionally hardcoded for
# pre-submit validation without requiring the runner package.
VALID_DATE_OPERATORS = {"before", "after", "equals", "not_equals", "equals_within"}

# Duration units accepted by ``equals_within`` and the ``add_duration`` /
# ``date_diff`` transform ops. Months / years deliberately excluded — see
# the ``transform-dates`` spec, R1.
VALID_DATE_DURATION_UNITS = {"seconds", "minutes", "hours", "days", "weeks"}


def validate_step(step: dict) -> tuple[bool, list[str]]:
    """Validate a step dict based on its step_type.

    Returns (is_valid, errors).  Only validates step types that have
    dedicated validators; other step types pass through. Steps that
    declare ``validation_type == "date"`` (typically assertion or
    validation steps) get an additional date-shape check on top of any
    step-type validation.
    """
    step_type = step.get("step_type", "")
    if step_type == "repeat":
        return validate_repeat_step(step)
    errors = list(_validate_typed_step(step, step_type)[1])
    errors.extend(repeat_only_field_errors(step))
    return len(errors) == 0, errors


def _validate_typed_step(step: dict, step_type: str) -> tuple[bool, list[str]]:
    """The per-type validator of a non-repeat step (pass-through for types without one)."""
    if step_type == "browser":
        return validate_browser_step(step)
    if step_type == "transform":
        return validate_transform_step(step)
    if step_type == "network_assertion":
        return validate_network_assertion_step(step)
    if step.get("validation_type") == "date":
        return validate_date_validation_type(step)
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


def validate_date_validation_type(step: dict) -> tuple[bool, list[str]]:
    """Validate a step with ``validation_type == "date"``.

    Pre-submit checks only. Date string parsing happens at runtime via
    ``transform.date_compare`` because ``{{ var }}`` references in
    ``validation_value`` cannot be resolved client-side.

    Rules:
      - ``validation_operator`` must be in :data:`VALID_DATE_OPERATORS`.
      - For ``equals_within``: ``validation_value`` must parse as a JSON
        object with the shape ``{date: str, tolerance: int >= 0,
        unit: <duration-unit>}``.
      - For other operators: ``validation_value`` must be a non-empty
        string. The string itself is not parsed here because it may be a
        ``{{ var }}`` reference that only resolves at runtime.
    """
    errors: list[str] = []

    operator = step.get("validation_operator", "")
    if operator not in VALID_DATE_OPERATORS:
        errors.append(
            f"Invalid validation_operator '{operator}' for validation_type='date'. "
            f"Must be one of: {', '.join(sorted(VALID_DATE_OPERATORS))}"
        )
        # Bail early — the rest of the validation depends on the operator.
        return False, errors

    validation_value = step.get("validation_value", "")

    if operator == "equals_within":
        errors.extend(_validate_equals_within_payload(validation_value))
    else:
        if not validation_value or not str(validation_value).strip():
            errors.append(
                f"validation_value is required for date '{operator}' operator "
                "(must be a date string or {{ variable }} reference)"
            )

    return len(errors) == 0, errors


def _validate_equals_within_payload(validation_value) -> list[str]:
    """Shape-check the JSON payload for the ``equals_within`` operator.

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []

    if not validation_value:
        return ["validation_value is required for equals_within operator"]

    try:
        payload = (
            json.loads(validation_value)
            if isinstance(validation_value, str)
            else validation_value
        )
    except (json.JSONDecodeError, TypeError):
        return [
            'equals_within validation_value must be valid JSON with shape '
            '{"date": str, "tolerance": int, "unit": str}'
        ]

    if not isinstance(payload, dict):
        return ["equals_within validation_value must be a JSON object"]

    date_value = payload.get("date")
    if not isinstance(date_value, str) or not date_value.strip():
        errors.append("equals_within payload requires non-empty 'date' string field")

    tolerance = payload.get("tolerance")
    # bool is a subclass of int — exclude it explicitly.
    if tolerance is None or isinstance(tolerance, bool) or not isinstance(tolerance, int):
        errors.append("equals_within payload 'tolerance' must be an integer")
    elif tolerance < 0:
        errors.append("equals_within payload 'tolerance' must be non-negative")

    unit = payload.get("unit")
    if unit not in VALID_DATE_DURATION_UNITS:
        errors.append(
            "equals_within payload 'unit' must be one of: "
            f"{', '.join(sorted(VALID_DATE_DURATION_UNITS))}"
        )

    return errors

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


# ---------------------------------------------------------------------------
# Step-level validation — repeat
# ---------------------------------------------------------------------------
#
# Mirrors ``web-app/lambdas/endpoints/repeat_validation.py`` (R-PARITY).  The
# server caps are constants there as well (not env-configured), so the CLI
# hardcodes the same 100 rows / 20 columns / 200 KB.  Error strings are
# compared verbatim in ``tests/test_repeat_validation_cli.py``; change both
# sides together.  Sibling-dependent rules (label uniqueness, parent lookup)
# need the usecase's other steps and stay server-side.

MAX_REPEAT_COLUMNS = 20
MAX_REPEAT_ROWS = 100
MAX_REPEAT_DATASET_BYTES = 200 * 1024
RESERVED_REPEAT_COLUMN_NAMES = frozenset({
    "UniqueID", "Time", "ExecutionID", "CreatedAt", "RepeatIndex", "RepeatTotal",
})
_REPEAT_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Dataset-source rule — verbatim copies of ``repeat_validation.REPEAT_*_ERROR``.
REPEAT_NO_SOURCE_ERROR = "repeat step must have either dataset_id or repeat_columns/repeat_rows"
REPEAT_BOTH_SOURCES_ERROR = "repeat step cannot have both dataset_id and inline rows"


def _validate_repeat_columns(columns) -> list[str]:
    errors: list[str] = []
    if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
        return ["repeat_columns must be a list of strings"]
    if len(columns) < 1:
        errors.append("repeat_columns must contain at least 1 column")
    if len(columns) > MAX_REPEAT_COLUMNS:
        errors.append(f"repeat_columns must contain at most {MAX_REPEAT_COLUMNS} columns")
    for column in columns:
        if not _REPEAT_IDENTIFIER_RE.match(column):
            errors.append(
                f'repeat column "{column}" is not a valid identifier '
                f"(letters, digits and underscores, not starting with a digit)"
            )
        elif column in RESERVED_REPEAT_COLUMN_NAMES:
            errors.append(f'repeat column "{column}" is a reserved name')
    if len(set(columns)) != len(columns):
        errors.append("repeat_columns must be unique")
    return errors


def _validate_repeat_rows(rows, column_count: int) -> list[str]:
    errors: list[str] = []
    if not isinstance(rows, list):
        return ["repeat_rows must be a list of rows"]
    if len(rows) < 1:
        errors.append("repeat_rows must contain at least 1 row")
    if len(rows) > MAX_REPEAT_ROWS:
        errors.append(f"repeat_rows must contain at most {MAX_REPEAT_ROWS} rows")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            errors.append(f"repeat_rows row {index} must be a list of cells")
            continue
        if len(row) != column_count:
            errors.append(
                f"repeat_rows row {index} has {len(row)} cells but {column_count} cells are expected"
            )
        if not all(isinstance(cell, str) for cell in row):
            errors.append(f"repeat_rows row {index} must contain only string cells")
    return errors


def _validate_repeat_dataset_size(columns, rows) -> list[str]:
    try:
        size = len(json.dumps(columns)) + len(json.dumps(rows))
    except (TypeError, ValueError):
        return ["repeat dataset is not JSON serializable"]
    if size > MAX_REPEAT_DATASET_BYTES:
        return [
            f"repeat dataset is too large ({size} bytes; the limit is "
            f"{MAX_REPEAT_DATASET_BYTES} bytes / 200 KB)"
        ]
    return []


def validate_repeat_dataset(columns, rows) -> list[str]:
    """Validate a ``{columns, rows}`` pair (stored dataset or ``--dataset-file``)."""
    errors = _validate_repeat_columns(columns)
    if isinstance(columns, list):
        errors.extend(_validate_repeat_rows(rows, len(columns)))
    elif rows is not None and not isinstance(rows, list):
        errors.append("repeat_rows must be a list of rows")
    if not errors:
        errors.extend(_validate_repeat_dataset_size(columns, rows))
    return errors


def validate_repeat_step(step: dict) -> tuple[bool, list[str]]:
    """Validate a ``repeat`` step: no nesting, then exactly one dataset source.

    Mirrors ``repeat_validation.validate_repeat_fields`` for a repeat without
    siblings (same checks, same order, same strings).
    """
    errors: list[str] = []
    if step.get("parent_step_id"):
        errors.append("a repeat step may not have a parent_step_id (nested repeats are not supported)")
    errors.extend(validate_repeat_source(step))
    return len(errors) == 0, errors


def has_dataset_reference(step: dict) -> bool:
    """True when ``step`` names an application dataset (non-empty ``dataset_id``)."""
    dataset_id = step.get("dataset_id")
    return dataset_id is not None and dataset_id != ""


def validate_repeat_source(step: dict) -> list[str]:
    """``dataset_id`` (an application dataset) XOR inline ``repeat_columns`` / ``repeat_rows``.

    Whether the referenced dataset exists is checked by the server (and by the
    local-only runner when it resolves the reference), not here.
    """
    errors: list[str] = []
    columns = step.get("repeat_columns")
    rows = step.get("repeat_rows")
    has_inline = columns is not None or rows is not None
    if has_dataset_reference(step):
        if not isinstance(step.get("dataset_id"), str):
            errors.append("dataset_id must be a string")
        if has_inline:
            errors.append(REPEAT_BOTH_SOURCES_ERROR)
        return errors
    if not has_inline:
        return [REPEAT_NO_SOURCE_ERROR]
    if columns is None:
        errors.append("repeat_columns is required for repeat steps")
    if rows is None:
        errors.append("repeat_rows is required for repeat steps")
    if columns is not None and rows is not None:
        errors.extend(validate_repeat_dataset(columns, rows))
    return errors


def repeat_only_field_errors(step: dict) -> list[str]:
    """Errors for repeat-only fields on a non-repeat step (``dataset_id`` counts only when non-empty)."""
    present = [f for f in ("repeat_columns", "repeat_rows") if step.get(f) is not None]
    if has_dataset_reference(step):
        present.append("dataset_id")
    return [f"{field} is only allowed on repeat steps" for field in present]


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
