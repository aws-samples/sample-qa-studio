"""JSON body matcher for network_assertion steps.

**Deprecated.**  This module is scheduled for removal as part of the
CLI-unified-runner refactor (see ``.kiro/specs/cli-unified-runner/``).
The canonical implementation now lives at
``qa-studio-cli/qa_studio_cli/runner/network_matcher.py``.

Until the worker is migrated (refactor phase 4, R-WORKER-5), any change
here MUST also be applied to the CLI copy.

Three matching modes:

- ``match_exact`` — strict JSON equality between the expected body and the
  captured body.
- ``match_subset`` — every key/value pair in the expected template must be
  present (and equal) in the captured body.  Extra keys in the captured body
  are ignored.  Recurses into nested dicts and lists; lists must have equal
  length.
- ``match_schema`` — validates the captured body against a JSON Schema
  Draft 2020-12 document using the ``jsonschema`` library.  External
  ``$ref`` targets (http://, https://, file://) are rejected to prevent
  SSRF and file-system reads from the worker.

Security guards:

- ``MAX_BODY_SIZE`` — raw JSON strings larger than this are rejected before
  parsing to avoid memory blow-ups on pathological input.  Default 1 MiB;
  overridable via the ``NETWORK_ASSERTION_BODY_MAX_BYTES`` environment
  variable (set at container / Lambda deploy time from
  ``configuration.json`` -> ``networkAssertionBodyMaxBytes``).
- ``MAX_DEPTH`` (20) — recursive matchers refuse to descend deeper than this
  to avoid stack overflow and CPU exhaustion on deeply nested input.
- External ``$ref`` rejection — the schema document itself is walked before
  validation and any ``$ref`` targeting an external URI raises a validation
  error.  Only local-pointer refs (e.g. ``#/$defs/Foo``) are accepted.

Return convention: every public matcher returns ``(bool, str)`` where the
string is empty on success and a short human-readable diff description on
failure.  Callers log the string and set the step to failed.
"""

from __future__ import annotations

import json
import os
from typing import Any, Tuple


def _read_max_body_size() -> int:
    """Read the configurable body-size cap from the environment.

    Defaults to 1 MiB (1_048_576 bytes).  An invalid value (non-integer or
    non-positive) falls back to the default rather than failing at import
    time — the matcher should never refuse to load because of a malformed
    env var.
    """
    raw = os.getenv("NETWORK_ASSERTION_BODY_MAX_BYTES", "1048576")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 1_048_576
    return value if value > 0 else 1_048_576


MAX_BODY_SIZE = _read_max_body_size()
MAX_DEPTH = 20


def validate_body_size(body: str) -> Tuple[bool, str]:
    """Reject raw JSON bodies larger than MAX_BODY_SIZE.

    Size is measured in bytes of the UTF-8 encoded string so that multi-byte
    characters can't sneak past a naive ``len()`` check.
    """
    if body is None:
        return True, ""
    size = len(body.encode("utf-8"))
    if size > MAX_BODY_SIZE:
        return False, f"body size {size} exceeds maximum {MAX_BODY_SIZE} bytes"
    return True, ""


def _parse_json(raw: str, label: str) -> Tuple[bool, Any, str]:
    """Parse a JSON string with a size guard.  Returns (ok, value, error)."""
    ok, err = validate_body_size(raw)
    if not ok:
        return False, None, f"{label}: {err}"
    try:
        return True, json.loads(raw), ""
    except (json.JSONDecodeError, TypeError) as exc:
        return False, None, f"{label}: invalid JSON ({exc})"


def match_exact(expected_json: str, actual: Any) -> Tuple[bool, str]:
    """Parse ``expected_json`` and assert full equality with ``actual``.

    ``actual`` is expected to already be a parsed JSON value (dict/list/etc.).
    If ``actual`` is a string, it is parsed as JSON first.
    """
    ok, expected, err = _parse_json(expected_json, "expected body")
    if not ok:
        return False, err

    if isinstance(actual, (str, bytes)):
        raw = actual.decode("utf-8") if isinstance(actual, bytes) else actual
        ok_actual, actual_value, err_actual = _parse_json(raw, "captured body")
        if not ok_actual:
            return False, err_actual
    else:
        actual_value = actual

    if expected == actual_value:
        return True, ""
    return False, f"body mismatch: expected {expected!r}, got {actual_value!r}"


def match_subset(template_json: str, actual: Any) -> Tuple[bool, str]:
    """Partial match: every key/value in the template must be in ``actual``.

    Recurses into nested dicts and lists.  Lists must have equal length and
    match element-by-element.  Extra keys in ``actual`` are ignored.
    """
    ok, template, err = _parse_json(template_json, "expected body")
    if not ok:
        return False, err

    if isinstance(actual, (str, bytes)):
        raw = actual.decode("utf-8") if isinstance(actual, bytes) else actual
        ok_actual, actual_value, err_actual = _parse_json(raw, "captured body")
        if not ok_actual:
            return False, err_actual
    else:
        actual_value = actual

    try:
        ok_match, err_match = _subset(template, actual_value, depth=0, path="")
    except RecursionError:
        return False, "nesting exceeds maximum depth"
    return ok_match, err_match


def _subset(template: Any, actual: Any, depth: int, path: str) -> Tuple[bool, str]:
    if depth > MAX_DEPTH:
        raise RecursionError("nesting exceeds maximum depth")

    # Dict: every key in template must exist in actual with matching value
    if isinstance(template, dict):
        if not isinstance(actual, dict):
            return False, _diff(path, f"expected object, got {_type_name(actual)}")
        for key, tmpl_value in template.items():
            key_path = f"{path}.{key}" if path else key
            if key not in actual:
                return False, _diff(key_path, "key missing in captured body")
            ok, err = _subset(tmpl_value, actual[key], depth + 1, key_path)
            if not ok:
                return False, err
        return True, ""

    # List: length + element-wise recursion
    if isinstance(template, list):
        if not isinstance(actual, list):
            return False, _diff(path, f"expected array, got {_type_name(actual)}")
        if len(template) != len(actual):
            return False, _diff(
                path,
                f"array length mismatch: expected {len(template)}, got {len(actual)}",
            )
        for i, (t_item, a_item) in enumerate(zip(template, actual)):
            item_path = f"{path}[{i}]"
            ok, err = _subset(t_item, a_item, depth + 1, item_path)
            if not ok:
                return False, err
        return True, ""

    # Primitive: direct equality
    if template == actual:
        return True, ""
    return False, _diff(path, f"expected {template!r}, got {actual!r}")


def _diff(path: str, message: str) -> str:
    return f"{path or '<root>'}: {message}"


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


# ---------------------------------------------------------------------------
# JSON Schema matcher (Draft 2020-12)
# ---------------------------------------------------------------------------

_EXTERNAL_REF_PREFIXES = ("http://", "https://", "file://")


def _reject_external_refs(node: Any, path: str = "") -> None:
    """Walk a parsed JSON-Schema document and reject external ``$ref`` targets.

    Only local-pointer refs (values starting with ``#``) are allowed.
    Anything else — URLs, file paths, bare identifiers — raises ``ValueError``.

    Raises ``ValueError`` on the first offending ``$ref`` so the failure
    message is precise.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            key_path = f"{path}.{key}" if path else key
            if key == "$ref" and isinstance(value, str):
                if value.startswith(_EXTERNAL_REF_PREFIXES):
                    raise ValueError(
                        f"external $ref not allowed at {key_path}: {value}"
                    )
                # Local pointer refs are fine; other non-URL strings (e.g.
                # plain identifiers) are also rejected for safety.
                if not value.startswith("#"):
                    raise ValueError(
                        f"only local-pointer $ref is allowed at {key_path}: {value}"
                    )
            else:
                _reject_external_refs(value, key_path)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _reject_external_refs(item, f"{path}[{i}]")


def match_schema(schema_json: str, actual: Any) -> Tuple[bool, str]:
    """Validate ``actual`` against the JSON Schema in ``schema_json``.

    Returns ``(True, "")`` on success, ``(False, <concise message>)`` on any
    failure: oversize schema, malformed JSON, invalid schema, external
    ``$ref``, or validation mismatch.

    ``actual`` may be a parsed value (dict/list/...) or a JSON string that
    will be parsed first.  Non-parseable captured bodies become the step's
    failure message rather than raising.
    """
    # Import lazily so the module still loads for callers that don't use
    # schema mode (e.g. the CLI base install in option-B packaging).
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError, ValidationError
    except ImportError as exc:  # pragma: no cover — environmental guard
        return False, f"jsonschema library not available: {exc}"

    ok, schema, err = _parse_json(schema_json, "schema")
    if not ok:
        return False, err
    if not isinstance(schema, dict):
        return False, "schema: must be a JSON object"

    try:
        _reject_external_refs(schema)
    except ValueError as exc:
        return False, str(exc)

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return False, f"invalid JSON Schema: {exc.message}"

    if isinstance(actual, (str, bytes)):
        raw = actual.decode("utf-8") if isinstance(actual, bytes) else actual
        ok_actual, actual_value, err_actual = _parse_json(raw, "captured body")
        if not ok_actual:
            return False, err_actual
    else:
        actual_value = actual

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(actual_value), key=lambda e: list(e.absolute_path))
    if not errors:
        return True, ""

    # Render a single-line message for the first error.  Including the path
    # in JSONPath-ish form makes the failure immediately actionable.
    first = errors[0]
    path = "/".join(str(p) for p in first.absolute_path) or "<root>"
    return False, f"schema mismatch at {path}: {first.message}"
