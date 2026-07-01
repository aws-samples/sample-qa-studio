"""Tests for the CLI network_matcher mirror module."""

import pytest

from qa_studio_cli.runner.network_matcher import (
    MAX_BODY_SIZE,
    MAX_DEPTH,
    match_exact,
    match_schema,
    match_subset,
    validate_body_size,
)


class TestValidateBodySize:
    def test_none_allowed(self):
        assert validate_body_size(None) == (True, "")

    def test_at_limit(self):
        assert validate_body_size("x" * MAX_BODY_SIZE)[0] is True

    def test_over_limit(self):
        ok, err = validate_body_size("x" * (MAX_BODY_SIZE + 1))
        assert ok is False
        assert "exceeds maximum" in err


class TestMatchExact:
    def test_equal(self):
        assert match_exact('{"a": 1}', {"a": 1}) == (True, "")

    def test_mismatch(self):
        ok, err = match_exact('{"a": 1}', {"a": 2})
        assert ok is False
        assert "mismatch" in err

    def test_actual_string_parsed(self):
        assert match_exact('{"a": 1}', '{"a": 1}') == (True, "")

    def test_invalid_expected(self):
        ok, err = match_exact("not json", {"a": 1})
        assert ok is False
        assert "invalid JSON" in err


class TestMatchSubset:
    def test_subset_match(self):
        assert match_subset('{"a": 1}', {"a": 1, "b": 2}) == (True, "")

    def test_nested_match(self):
        ok, err = match_subset(
            '{"user": {"name": "John"}}',
            {"user": {"name": "John", "age": 30}},
        )
        assert ok is True
        assert err == ""

    def test_missing_key(self):
        ok, err = match_subset('{"a": 1, "b": 2}', {"a": 1})
        assert ok is False
        assert "b" in err

    def test_value_mismatch_path(self):
        ok, err = match_subset(
            '{"user": {"name": "John"}}', {"user": {"name": "Jane"}}
        )
        assert ok is False
        assert "user.name" in err

    def test_array_length_mismatch(self):
        ok, err = match_subset('{"tags": ["a"]}', {"tags": ["a", "b"]})
        assert ok is False
        assert "length" in err

    def test_depth_cap(self):
        def nest(depth):
            return "{}" if depth == 0 else '{"x": ' + nest(depth - 1) + "}"

        import json

        over = nest(MAX_DEPTH + 2)
        ok, err = match_subset(over, json.loads(over))
        assert ok is False
        assert "depth" in err


class TestMatchSchema:
    """Minimal schema-matcher coverage on the CLI side.

    The full behavioural matrix lives in
    ``web-app/worker/tests/test_network_matcher.py``; here we only verify
    the CLI mirror implements the same public interface and common paths.
    The parity test in the worker's test file asserts that the two
    implementations return identical ``(bool, str)`` on a shared fixture
    set (including schema cases).
    """

    def test_valid_passes(self):
        schema = '{"type": "object", "required": ["id"]}'
        assert match_schema(schema, {"id": "x"}) == (True, "")

    def test_missing_required_fails(self):
        schema = '{"type": "object", "required": ["id"]}'
        ok, err = match_schema(schema, {})
        assert ok is False

    def test_external_ref_rejected(self):
        schema = '{"$ref": "http://evil/s.json"}'
        ok, err = match_schema(schema, {})
        assert ok is False
        assert "external $ref" in err

    def test_malformed_schema_rejected(self):
        ok, err = match_schema("not json", {})
        assert ok is False

    def test_invalid_schema_rejected(self):
        ok, err = match_schema('{"type": 42}', {})
        assert ok is False
        assert "invalid JSON Schema" in err
