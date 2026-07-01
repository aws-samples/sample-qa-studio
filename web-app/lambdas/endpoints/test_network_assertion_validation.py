"""Tests for ``network_assertion`` validation in ``utils.py``."""

import os

os.environ.setdefault("TABLE_NAME", "test-table")

from utils import (  # noqa: E402
    _validate_network_assertion_fields,
    _validate_network_json_field,
)


def _valid_step(**overrides) -> dict:
    base = {
        "sort": 1,
        "instruction": "Click submit",
        "step_type": "network_assertion",
        "network_url_pattern": "**/api/users",
    }
    base.update(overrides)
    return base


def _run(step: dict) -> list[str]:
    errors: list[str] = []
    _validate_network_assertion_fields(step, 0, errors)
    return errors


class TestNetworkAssertionValidation:
    def test_minimal_valid(self):
        assert _run(_valid_step()) == []

    def test_missing_url_pattern(self):
        errors = _run(_valid_step(network_url_pattern=None))
        assert any("network_url_pattern" in e for e in errors)

    def test_blank_url_pattern(self):
        errors = _run(_valid_step(network_url_pattern="   "))
        assert any("network_url_pattern" in e for e in errors)

    def test_invalid_method(self):
        errors = _run(_valid_step(network_method="TEAPOT"))
        assert any("network_method" in e for e in errors)

    def test_method_case_insensitive(self):
        # Lower-case methods are normalized to upper before the allow-list check.
        assert _run(_valid_step(network_method="post")) == []

    def test_empty_method_ignored(self):
        assert _run(_valid_step(network_method="")) == []

    def test_invalid_match_type(self):
        errors = _run(_valid_step(
            network_request_body='{"x":1}',
            network_body_match_type="fuzzy",
        ))
        assert any("network_body_match_type" in e for e in errors)

    def test_malformed_request_body(self):
        errors = _run(_valid_step(network_request_body="not json"))
        assert any("network_request_body" in e for e in errors)

    def test_body_over_limit(self):
        big = '"' + "a" * 1_048_577 + '"'
        errors = _run(_valid_step(network_request_body=big))
        assert any("exceeds maximum" in e for e in errors)

    def test_body_exactly_at_limit(self):
        # 1 MiB encoded as JSON string literal: 2 quotes + 1_048_574 chars
        at_limit = '"' + "a" * (1_048_576 - 2) + '"'
        assert len(at_limit.encode("utf-8")) == 1_048_576
        assert _run(_valid_step(network_request_body=at_limit)) == []

    def test_mock_response_must_be_object(self):
        errors = _run(_valid_step(network_mock_response='["not", "object"]'))
        assert any("object" in e for e in errors)

    def test_mock_response_malformed(self):
        errors = _run(_valid_step(network_mock_response="not json"))
        assert any("network_mock_response" in e for e in errors)

    def test_mock_response_over_limit(self):
        big = '{"body": "' + "a" * 1_048_577 + '"}'
        errors = _run(_valid_step(network_mock_response=big))
        assert any("exceeds maximum" in e for e in errors)

    def test_timeout_below_minimum(self):
        errors = _run(_valid_step(network_timeout=0))
        assert any("network_timeout" in e for e in errors)

    def test_timeout_above_maximum(self):
        errors = _run(_valid_step(network_timeout=121))
        assert any("network_timeout" in e for e in errors)

    def test_timeout_at_boundary(self):
        assert _run(_valid_step(network_timeout=1)) == []
        assert _run(_valid_step(network_timeout=120)) == []

    def test_timeout_non_numeric(self):
        errors = _run(_valid_step(network_timeout="abc"))
        assert any("integer" in e for e in errors)

    def test_multiple_errors_collected_together(self):
        errors = _run({
            "sort": 1,
            "instruction": "x",
            "step_type": "network_assertion",
            "network_url_pattern": "",
            "network_method": "WAT",
            "network_timeout": 999,
        })
        assert any("network_url_pattern" in e for e in errors)
        assert any("network_method" in e for e in errors)
        assert any("network_timeout" in e for e in errors)


class TestNetworkJsonFieldHelper:
    def test_non_string_rejected(self):
        errors: list[str] = []
        _validate_network_json_field(42, "f", errors)
        assert any("must be a JSON string" in e for e in errors)

    def test_non_object_with_require_object(self):
        errors: list[str] = []
        _validate_network_json_field('["x"]', "f", errors, require_object=True)
        assert any("must be a JSON object" in e for e in errors)

    def test_object_with_require_object(self):
        errors: list[str] = []
        _validate_network_json_field('{"x": 1}', "f", errors, require_object=True)
        assert errors == []


class TestConfigurableBodyCap:
    """Validation cap is sourced from ``NETWORK_ASSERTION_BODY_MAX_BYTES``.

    The value is read at module load time.  These tests verify the helper
    directly and verify that re-importing with an overridden env picks up
    the new cap.
    """

    def test_default_is_1_mib(self):
        from utils import _NETWORK_ASSERTION_MAX_BODY_BYTES

        assert _NETWORK_ASSERTION_MAX_BODY_BYTES == 1_048_576

    def test_read_helper_applies_env_override(self, monkeypatch):
        from utils import _read_network_assertion_max_body_bytes

        monkeypatch.setenv("NETWORK_ASSERTION_BODY_MAX_BYTES", "500")
        assert _read_network_assertion_max_body_bytes() == 500

    def test_read_helper_falls_back_on_non_integer(self, monkeypatch):
        from utils import _read_network_assertion_max_body_bytes

        monkeypatch.setenv("NETWORK_ASSERTION_BODY_MAX_BYTES", "not-a-number")
        assert _read_network_assertion_max_body_bytes() == 1_048_576

    def test_read_helper_falls_back_on_zero(self, monkeypatch):
        from utils import _read_network_assertion_max_body_bytes

        monkeypatch.setenv("NETWORK_ASSERTION_BODY_MAX_BYTES", "0")
        assert _read_network_assertion_max_body_bytes() == 1_048_576

    def test_module_cap_responds_to_env_on_reimport(self, monkeypatch):
        """A 501-byte body is rejected when the module cap is 500."""
        import importlib

        import utils

        monkeypatch.setenv("NETWORK_ASSERTION_BODY_MAX_BYTES", "500")
        try:
            reloaded = importlib.reload(utils)
            assert reloaded._NETWORK_ASSERTION_MAX_BODY_BYTES == 500

            errors: list[str] = []
            # 501 bytes of raw JSON string (quotes + 499 chars).
            oversized = '"' + ("a" * 499) + '"'
            reloaded._validate_network_json_field(
                oversized, "step.network_request_body", errors,
            )
            assert any("exceeds maximum size" in e for e in errors)
        finally:
            # Restore the default cap for later tests.
            monkeypatch.delenv("NETWORK_ASSERTION_BODY_MAX_BYTES", raising=False)
            importlib.reload(utils)


class TestSchemaModeValidation:
    """``network_body_match_type == 'schema'`` puts the body under extra checks.

    The Lambda layer doesn't run full Draft 2020-12 validation (that would
    require a new dependency).  It does:
      - allow 'schema' in the match-type enum;
      - require the schema document parses as a JSON object;
      - reject external ``$ref`` to http/https/file URIs and bare identifiers.
    """

    def test_schema_accepted_in_request_match_type(self):
        errors = _run(_valid_step(
            network_body_match_type='schema',
            network_request_body='{"type": "object"}',
        ))
        assert errors == []

    def test_schema_request_body_external_ref_rejected(self):
        errors = _run(_valid_step(
            network_body_match_type='schema',
            network_request_body='{"$ref": "http://evil/schema.json"}',
        ))
        assert any('external $ref not allowed' in e for e in errors)

    def test_schema_request_body_file_ref_rejected(self):
        errors = _run(_valid_step(
            network_body_match_type='schema',
            network_request_body='{"$ref": "file:///etc/passwd"}',
        ))
        assert any('external $ref not allowed' in e for e in errors)

    def test_schema_request_body_local_pointer_ref_allowed(self):
        errors = _run(_valid_step(
            network_body_match_type='schema',
            network_request_body='{"$defs": {"X": {"type": "string"}}, "$ref": "#/$defs/X"}',
        ))
        assert errors == []

    def test_schema_request_body_bare_ref_rejected(self):
        errors = _run(_valid_step(
            network_body_match_type='schema',
            network_request_body='{"$ref": "SomeBareName"}',
        ))
        assert any('local-pointer $ref is allowed' in e for e in errors)

    def test_schema_request_body_nested_external_ref_rejected(self):
        errors = _run(_valid_step(
            network_body_match_type='schema',
            network_request_body='{"type": "object", "properties": {"x": {"$ref": "https://evil/s.json"}}}',
        ))
        assert any('external $ref' in e for e in errors)

    def test_schema_request_body_non_object_rejected(self):
        errors = _run(_valid_step(
            network_body_match_type='schema',
            network_request_body='"just a string"',
        ))
        assert any('schema document' in e for e in errors)


class TestResponseSideValidation:
    """Response-side fields have their own validation rules.

    - Match type is {subset, schema} only — no ``exact``.
    - Body follows the same size/JSON/schema rules as request side.
    - Status must be an integer in [100, 599].
    """

    def test_minimal_without_response_fields(self):
        """Response fields are entirely optional; absence is not an error."""
        assert _run(_valid_step()) == []

    def test_response_match_type_exact_rejected(self):
        errors = _run(_valid_step(
            network_response_body_match_type='exact',
            network_response_body='{"id": "x"}',
        ))
        assert any('exact' in e.lower() for e in errors)
        assert any('not permitted on the response side' in e for e in errors)

    def test_response_match_type_subset_accepted(self):
        errors = _run(_valid_step(
            network_response_body_match_type='subset',
            network_response_body='{"id": "x"}',
        ))
        assert errors == []

    def test_response_match_type_schema_accepted(self):
        errors = _run(_valid_step(
            network_response_body_match_type='schema',
            network_response_body='{"type": "object"}',
        ))
        assert errors == []

    def test_response_match_type_garbage_rejected(self):
        errors = _run(_valid_step(
            network_response_body_match_type='gibberish',
        ))
        assert any('network_response_body_match_type' in e for e in errors)

    def test_response_body_malformed_json_rejected(self):
        errors = _run(_valid_step(
            network_response_body_match_type='subset',
            network_response_body='not json',
        ))
        assert any('network_response_body is not valid JSON' in e for e in errors)

    def test_response_body_schema_external_ref_rejected(self):
        errors = _run(_valid_step(
            network_response_body_match_type='schema',
            network_response_body='{"$ref": "http://evil"}',
        ))
        assert any('external $ref' in e for e in errors)

    def test_response_body_oversize_rejected(self):
        oversize = '"' + ('a' * 1_048_576) + '"'
        errors = _run(_valid_step(
            network_response_body_match_type='subset',
            network_response_body=oversize,
        ))
        assert any('exceeds maximum size' in e for e in errors)

    def test_response_status_200_accepted(self):
        errors = _run(_valid_step(network_response_status=200))
        assert errors == []

    def test_response_status_100_boundary_accepted(self):
        errors = _run(_valid_step(network_response_status=100))
        assert errors == []

    def test_response_status_599_boundary_accepted(self):
        errors = _run(_valid_step(network_response_status=599))
        assert errors == []

    def test_response_status_99_rejected(self):
        errors = _run(_valid_step(network_response_status=99))
        assert any('network_response_status must be between' in e for e in errors)

    def test_response_status_600_rejected(self):
        errors = _run(_valid_step(network_response_status=600))
        assert any('network_response_status must be between' in e for e in errors)

    def test_response_status_non_integer_rejected(self):
        errors = _run(_valid_step(network_response_status='not-an-int'))
        assert any('network_response_status must be an integer' in e for e in errors)
