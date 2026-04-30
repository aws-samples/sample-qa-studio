"""Schema tests for network_assertion fields in the usecase export schema."""

import os

os.environ.setdefault("TABLE_NAME", "test-table")
os.environ.setdefault("BUCKET_NAME", "test-bucket")
os.environ.setdefault("BEDROCK_MODEL_ID", "test-model")

from generate_usecase import USECASE_EXPORT_SCHEMA  # noqa: E402


STEP_PROPS = USECASE_EXPORT_SCHEMA["properties"]["steps"]["items"]["properties"]

NETWORK_FIELDS = (
    "network_url_pattern",
    "network_method",
    "network_request_body",
    "network_body_match_type",
    "network_mock_response",
    "network_mock_passthrough",
    "network_timeout",
    "network_response_body",
    "network_response_body_match_type",
    "network_response_status",
)


class TestNetworkFieldsInSchema:
    """Every new field must appear in the schema with the right shape."""

    def test_all_fields_are_present(self):
        for field in NETWORK_FIELDS:
            assert field in STEP_PROPS, f"{field} missing from schema properties"

    def test_url_pattern_is_string(self):
        assert STEP_PROPS["network_url_pattern"]["type"] == "string"

    def test_method_enum_covers_all_verbs_and_empty(self):
        enum = STEP_PROPS["network_method"]["enum"]
        for verb in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", ""):
            assert verb in enum, f"HTTP verb {verb!r} missing from enum"

    def test_request_match_type_enum_includes_schema(self):
        """Request side accepts exact, subset, schema, and empty string."""
        enum = STEP_PROPS["network_body_match_type"]["enum"]
        assert set(enum) == {"exact", "subset", "schema", ""}

    def test_response_match_type_enum_excludes_exact(self):
        """Response side only accepts subset and schema — ``exact`` is
        deliberately absent per R14."""
        enum = STEP_PROPS["network_response_body_match_type"]["enum"]
        assert set(enum) == {"subset", "schema", ""}
        assert "exact" not in enum

    def test_response_body_is_string(self):
        assert STEP_PROPS["network_response_body"]["type"] == "string"

    def test_response_status_is_integer(self):
        assert STEP_PROPS["network_response_status"]["type"] == "integer"

    def test_passthrough_is_boolean(self):
        assert STEP_PROPS["network_mock_passthrough"]["type"] == "boolean"

    def test_timeout_is_integer(self):
        assert STEP_PROPS["network_timeout"]["type"] == "integer"

    def test_network_fields_not_required(self):
        """The new fields are optional — they must NOT appear in `required`
        so existing step types can continue to omit them."""
        required = USECASE_EXPORT_SCHEMA["properties"]["steps"]["items"]["required"]
        for field in NETWORK_FIELDS:
            assert field not in required, f"{field} should not be required"


class TestStepTypeEnumIncludesNetworkAssertion:
    def test_network_assertion_in_enum(self):
        enum = STEP_PROPS["step_type"]["enum"]
        assert "network_assertion" in enum


def test_sample_testcase_passes_server_validation():
    """The checked-in sample JSON must pass ``validate_generated_json``."""
    import json
    from pathlib import Path

    from utils import validate_generated_json

    sample_path = (
        Path(__file__).resolve().parents[3]
        / "testcases" / "operators" / "network_assertion_basic.json"
    )
    raw = sample_path.read_text()
    data = json.loads(raw)

    # validate_generated_json expects the shape the LLM produces: usecase +
    # steps at the top level (without the export wrapper).  Ensure every
    # required usecase field is present so we only exercise the step-level
    # validation we care about in this spec.
    inner = {
        "exportVersion": data["exportVersion"],
        "exportedAt": data["exportedAt"],
        "usecase": {
            **data["usecase"],
            # sample has starting_url empty on purpose — fill for validator
            "starting_url": data["usecase"].get("starting_url") or "https://example.test/",
        },
        "steps": data["steps"],
    }
    ok, errors, validated = validate_generated_json(json.dumps(inner))
    assert ok, f"sample failed server validation: {errors}"
    assert validated is not None
