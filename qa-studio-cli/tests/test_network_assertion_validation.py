"""Tests for network_assertion step validation in the CLI."""

import pytest

from qa_studio_cli.validation import (
    validate_network_assertion_step,
    validate_step,
)


def _valid_step(**overrides) -> dict:
    base = {
        "step_type": "network_assertion",
        "instruction": "Click submit",
        "network_url_pattern": "**/api/users",
    }
    base.update(overrides)
    return base


class TestValidateStepDispatcher:
    def test_dispatches_to_network_assertion_validator(self):
        ok, errors = validate_step(_valid_step())
        assert ok is True
        assert errors == []

    def test_unknown_step_type_passes_through(self):
        ok, errors = validate_step({"step_type": "navigation", "instruction": "x"})
        assert ok is True
        assert errors == []

    def test_empty_step_type_passes_through(self):
        # Default step_type is the empty string in some contexts — that
        # should not trip the network_assertion validator.
        ok, errors = validate_step({})
        assert ok is True
        assert errors == []


class TestNetworkAssertionValidation:
    def test_minimal_valid(self):
        ok, errors = validate_network_assertion_step(_valid_step())
        assert ok is True
        assert errors == []

    def test_missing_url_pattern(self):
        ok, errors = validate_network_assertion_step(_valid_step(network_url_pattern=None))
        assert ok is False
        assert any("network_url_pattern" in e for e in errors)

    def test_empty_url_pattern(self):
        ok, errors = validate_network_assertion_step(_valid_step(network_url_pattern="   "))
        assert ok is False
        assert any("network_url_pattern" in e for e in errors)

    @pytest.mark.parametrize(
        "method",
        ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    def test_allowed_methods(self, method):
        ok, errors = validate_network_assertion_step(_valid_step(network_method=method))
        assert ok is True, errors

    def test_invalid_method(self):
        ok, errors = validate_network_assertion_step(_valid_step(network_method="WHATEVER"))
        assert ok is False
        assert any("network_method" in e for e in errors)

    def test_empty_method_ignored(self):
        # Empty string = "no method check", should pass.
        ok, errors = validate_network_assertion_step(_valid_step(network_method=""))
        assert ok is True
        assert errors == []

    @pytest.mark.parametrize("match_type", ["exact", "subset"])
    def test_allowed_match_types(self, match_type):
        ok, errors = validate_network_assertion_step(
            _valid_step(
                network_request_body='{"x": 1}',
                network_body_match_type=match_type,
            )
        )
        assert ok is True, errors

    def test_invalid_match_type(self):
        ok, errors = validate_network_assertion_step(
            _valid_step(
                network_request_body='{"x": 1}',
                network_body_match_type="fuzzy",
            )
        )
        assert ok is False
        assert any("network_body_match_type" in e for e in errors)

    def test_malformed_request_body_json(self):
        ok, errors = validate_network_assertion_step(
            _valid_step(network_request_body="not json")
        )
        assert ok is False
        assert any("network_request_body" in e for e in errors)
        assert any("valid JSON" in e for e in errors)

    def test_request_body_at_size_limit(self):
        # A JSON string ("a" * 1_048_574) surrounded by two quotes = exactly 1 MiB
        at_limit = '"' + "a" * (1_048_576 - 2) + '"'
        assert len(at_limit) == 1_048_576
        ok, errors = validate_network_assertion_step(_valid_step(network_request_body=at_limit))
        assert ok is True, errors

    def test_request_body_over_size_limit(self):
        oversize = '"' + "a" * 1_048_577 + '"'
        ok, errors = validate_network_assertion_step(_valid_step(network_request_body=oversize))
        assert ok is False
        assert any("exceeds maximum" in e for e in errors)

    def test_mock_response_must_be_json(self):
        ok, errors = validate_network_assertion_step(
            _valid_step(network_mock_response="not json")
        )
        assert ok is False
        assert any("network_mock_response" in e for e in errors)

    def test_mock_response_must_be_object(self):
        ok, errors = validate_network_assertion_step(
            _valid_step(network_mock_response='["not", "an", "object"]')
        )
        assert ok is False
        assert any("network_mock_response" in e for e in errors)
        assert any("object" in e for e in errors)

    def test_mock_response_over_size_limit(self):
        oversize = '{"body": "' + "a" * 1_048_577 + '"}'
        ok, errors = validate_network_assertion_step(
            _valid_step(network_mock_response=oversize)
        )
        assert ok is False
        assert any("exceeds maximum" in e for e in errors)

    @pytest.mark.parametrize("bad", [0, -1, 121, 9999])
    def test_timeout_out_of_range(self, bad):
        ok, errors = validate_network_assertion_step(_valid_step(network_timeout=bad))
        assert ok is False
        assert any("network_timeout" in e for e in errors)

    @pytest.mark.parametrize("ok_val", [1, 15, 120])
    def test_timeout_in_range(self, ok_val):
        ok, errors = validate_network_assertion_step(_valid_step(network_timeout=ok_val))
        assert ok is True, errors

    def test_timeout_non_integer(self):
        ok, errors = validate_network_assertion_step(_valid_step(network_timeout="abc"))
        assert ok is False
        assert any("integer" in e for e in errors)

    def test_multiple_errors_reported_together(self):
        ok, errors = validate_network_assertion_step({
            "step_type": "network_assertion",
            "network_url_pattern": "",
            "network_method": "BAD",
            "network_timeout": 9999,
        })
        assert ok is False
        # all three issues should be flagged
        assert any("network_url_pattern" in e for e in errors)
        assert any("network_method" in e for e in errors)
        assert any("network_timeout" in e for e in errors)


class TestSchemaModeValidation:
    """``network_body_match_type == 'schema'`` puts the body under extra
    checks: parse-as-JSON-object + external ``$ref`` rejection.  The CLI
    does not itself structurally validate the schema (Draft 2020-12 validity
    is checked by the runner which has the ``jsonschema`` dep via
    ``[runner]`` extras).
    """

    def test_schema_accepted_on_request_side(self):
        ok, errors = validate_network_assertion_step(_valid_step(
            network_body_match_type="schema",
            network_request_body='{"type": "object"}',
        ))
        assert ok is True, errors

    def test_schema_request_external_ref_http_rejected(self):
        ok, errors = validate_network_assertion_step(_valid_step(
            network_body_match_type="schema",
            network_request_body='{"$ref": "http://evil/schema.json"}',
        ))
        assert ok is False
        assert any("external $ref not allowed" in e for e in errors)

    def test_schema_request_external_ref_https_rejected(self):
        ok, errors = validate_network_assertion_step(_valid_step(
            network_body_match_type="schema",
            network_request_body='{"$ref": "https://evil"}',
        ))
        assert ok is False
        assert any("external $ref" in e for e in errors)

    def test_schema_request_external_ref_file_rejected(self):
        ok, errors = validate_network_assertion_step(_valid_step(
            network_body_match_type="schema",
            network_request_body='{"$ref": "file:///etc/passwd"}',
        ))
        assert ok is False
        assert any("external $ref" in e for e in errors)

    def test_schema_request_local_pointer_ref_allowed(self):
        ok, errors = validate_network_assertion_step(_valid_step(
            network_body_match_type="schema",
            network_request_body='{"$defs": {"X": {"type": "string"}}, "$ref": "#/$defs/X"}',
        ))
        assert ok is True, errors

    def test_schema_request_bare_ref_rejected(self):
        ok, errors = validate_network_assertion_step(_valid_step(
            network_body_match_type="schema",
            network_request_body='{"$ref": "SomeBareName"}',
        ))
        assert ok is False
        assert any("local-pointer $ref" in e for e in errors)

    def test_schema_request_nested_external_ref_rejected(self):
        ok, errors = validate_network_assertion_step(_valid_step(
            network_body_match_type="schema",
            network_request_body='{"type": "object", "properties": {"x": {"$ref": "http://evil"}}}',
        ))
        assert ok is False
        assert any("external $ref" in e for e in errors)

    def test_schema_non_object_document_rejected(self):
        ok, errors = validate_network_assertion_step(_valid_step(
            network_body_match_type="schema",
            network_request_body='"just a string"',
        ))
        assert ok is False
        assert any("schema document" in e for e in errors)


class TestResponseSideValidation:
    """Response-side fields have their own rules:
    - Match type ∈ {subset, schema} only — ``exact`` is rejected.
    - Body follows size + JSON + schema rules.
    - Status is an integer in [100, 599].
    """

    def test_minimal_without_response_fields(self):
        ok, errors = validate_network_assertion_step(_valid_step())
        assert ok is True
        assert errors == []

    def test_response_match_type_exact_rejected(self):
        ok, errors = validate_network_assertion_step(_valid_step(
            network_response_body_match_type="exact",
            network_response_body='{"id": "x"}',
        ))
        assert ok is False
        assert any("network_response_body_match_type" in e for e in errors)
        assert any("not permitted on the response side" in e for e in errors)

    @pytest.mark.parametrize("match_type", ["subset", "schema"])
    def test_response_match_type_allowed(self, match_type):
        body = '{"id": "x"}' if match_type == "subset" else '{"type": "object"}'
        ok, errors = validate_network_assertion_step(_valid_step(
            network_response_body_match_type=match_type,
            network_response_body=body,
        ))
        assert ok is True, errors

    def test_response_match_type_garbage_rejected(self):
        ok, errors = validate_network_assertion_step(_valid_step(
            network_response_body_match_type="gibberish",
        ))
        assert ok is False
        assert any("network_response_body_match_type" in e for e in errors)

    def test_response_body_malformed_json_rejected(self):
        ok, errors = validate_network_assertion_step(_valid_step(
            network_response_body_match_type="subset",
            network_response_body="not json",
        ))
        assert ok is False
        assert any("network_response_body is not valid JSON" in e for e in errors)

    def test_response_body_schema_external_ref_rejected(self):
        ok, errors = validate_network_assertion_step(_valid_step(
            network_response_body_match_type="schema",
            network_response_body='{"$ref": "http://evil"}',
        ))
        assert ok is False
        assert any("external $ref" in e for e in errors)

    def test_response_body_oversize_rejected(self):
        oversize = '"' + ("a" * 1_048_576) + '"'
        ok, errors = validate_network_assertion_step(_valid_step(
            network_response_body_match_type="subset",
            network_response_body=oversize,
        ))
        assert ok is False
        assert any("exceeds maximum" in e for e in errors)

    @pytest.mark.parametrize("status", [100, 200, 201, 404, 500, 599])
    def test_response_status_in_range_accepted(self, status):
        ok, errors = validate_network_assertion_step(_valid_step(network_response_status=status))
        assert ok is True, errors

    @pytest.mark.parametrize("status", [0, 99, 600, 999, -1])
    def test_response_status_out_of_range_rejected(self, status):
        ok, errors = validate_network_assertion_step(_valid_step(network_response_status=status))
        assert ok is False
        assert any("network_response_status must be between" in e for e in errors)

    def test_response_status_non_integer_rejected(self):
        ok, errors = validate_network_assertion_step(_valid_step(network_response_status="not-an-int"))
        assert ok is False
        assert any("network_response_status must be an integer" in e for e in errors)
