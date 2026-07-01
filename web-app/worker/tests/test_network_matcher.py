"""Tests for the JSON matcher used by network_assertion steps."""

import sys
from pathlib import Path

import pytest

_WORKER_DIR = Path(__file__).resolve().parent.parent
if str(_WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKER_DIR))

from network_matcher import (  # noqa: E402
    MAX_BODY_SIZE,
    MAX_DEPTH,
    match_exact,
    match_schema,
    match_subset,
    validate_body_size,
)


class TestValidateBodySize:
    def test_none_is_allowed(self):
        ok, err = validate_body_size(None)
        assert ok is True
        assert err == ""

    def test_under_limit(self):
        ok, err = validate_body_size("x" * (MAX_BODY_SIZE - 1))
        assert ok is True
        assert err == ""

    def test_at_limit_is_allowed(self):
        ok, err = validate_body_size("x" * MAX_BODY_SIZE)
        assert ok is True
        assert err == ""

    def test_over_limit(self):
        ok, err = validate_body_size("x" * (MAX_BODY_SIZE + 1))
        assert ok is False
        assert "exceeds maximum" in err

    def test_multibyte_chars_are_counted_as_bytes(self):
        # '€' is 3 UTF-8 bytes — MAX_BODY_SIZE / 3 chars is under limit but
        # MAX_BODY_SIZE / 3 + 1 char pushes over.
        at_limit_chars = MAX_BODY_SIZE // 3
        ok, _ = validate_body_size("€" * at_limit_chars)
        assert ok is True

        ok, err = validate_body_size("€" * (at_limit_chars + 1))
        assert ok is False
        assert "exceeds maximum" in err


class TestMatchExact:
    def test_equal_dicts(self):
        ok, err = match_exact('{"name": "John", "age": 30}', {"name": "John", "age": 30})
        assert ok is True
        assert err == ""

    def test_differing_value(self):
        ok, err = match_exact('{"name": "John"}', {"name": "Jane"})
        assert ok is False
        assert "mismatch" in err

    def test_extra_key_in_actual_fails_exact(self):
        ok, err = match_exact('{"name": "John"}', {"name": "John", "age": 30})
        assert ok is False

    def test_actual_string_is_parsed_as_json(self):
        ok, err = match_exact('{"x": 1}', '{"x": 1}')
        assert ok is True
        assert err == ""

    def test_invalid_expected_json(self):
        ok, err = match_exact("not json", {"x": 1})
        assert ok is False
        assert "invalid JSON" in err

    def test_invalid_actual_json_string(self):
        ok, err = match_exact('{"x": 1}', "not json")
        assert ok is False
        assert "invalid JSON" in err

    def test_oversize_expected_rejected(self):
        oversize = '"' + ("a" * (MAX_BODY_SIZE + 10)) + '"'
        ok, err = match_exact(oversize, "a")
        assert ok is False
        assert "exceeds maximum" in err


class TestMatchSubset:
    def test_exact_equal(self):
        ok, err = match_subset('{"a": 1}', {"a": 1})
        assert ok is True
        assert err == ""

    def test_extra_keys_in_actual_ignored(self):
        ok, err = match_subset('{"a": 1}', {"a": 1, "b": 2, "c": 3})
        assert ok is True
        assert err == ""

    def test_nested_subset_match(self):
        ok, err = match_subset(
            '{"user": {"name": "John"}}',
            {"user": {"name": "John", "age": 30, "id": "abc"}, "ts": 1},
        )
        assert ok is True
        assert err == ""

    def test_missing_key_fails(self):
        ok, err = match_subset('{"a": 1, "b": 2}', {"a": 1})
        assert ok is False
        assert "b" in err
        assert "missing" in err

    def test_value_mismatch_reports_path(self):
        ok, err = match_subset(
            '{"user": {"name": "John"}}',
            {"user": {"name": "Jane"}},
        )
        assert ok is False
        assert "user.name" in err

    def test_type_mismatch(self):
        ok, err = match_subset('{"user": {"name": "John"}}', {"user": "string"})
        assert ok is False
        assert "user" in err
        assert "expected object" in err

    def test_array_equal(self):
        ok, err = match_subset('{"tags": ["a", "b"]}', {"tags": ["a", "b"]})
        assert ok is True

    def test_array_length_mismatch(self):
        ok, err = match_subset('{"tags": ["a", "b"]}', {"tags": ["a", "b", "c"]})
        assert ok is False
        assert "length mismatch" in err

    def test_null_values(self):
        ok, err = match_subset('{"a": null}', {"a": None})
        assert ok is True
        assert err == ""

    def test_null_vs_missing(self):
        # explicit null in template should require an explicit null in actual
        ok, err = match_subset('{"a": null}', {})
        assert ok is False
        assert "a" in err

    def test_nested_array_of_objects_subset(self):
        ok, err = match_subset(
            '{"items": [{"id": 1}, {"id": 2}]}',
            {"items": [{"id": 1, "name": "x"}, {"id": 2, "name": "y"}], "total": 2},
        )
        assert ok is True

    def test_deeply_nested_at_limit(self):
        # Build a template exactly MAX_DEPTH levels deep.  The outer dict is
        # depth 0, so we need MAX_DEPTH nested dicts beneath it.
        def nest(depth):
            return "{}" if depth == 0 else '{"x": ' + nest(depth - 1) + "}"

        template = nest(MAX_DEPTH)
        import json

        actual = json.loads(template)
        ok, err = match_subset(template, actual)
        assert ok is True, f"Should allow {MAX_DEPTH} levels but got: {err}"

    def test_deeply_nested_over_limit_rejected(self):
        def nest(depth):
            return "{}" if depth == 0 else '{"x": ' + nest(depth - 1) + "}"

        import json

        template = nest(MAX_DEPTH + 2)
        actual = json.loads(template)
        ok, err = match_subset(template, actual)
        assert ok is False
        assert "depth" in err

    def test_oversize_expected_rejected(self):
        oversize = '"' + ("a" * (MAX_BODY_SIZE + 10)) + '"'
        ok, err = match_subset(oversize, "a")
        assert ok is False
        assert "exceeds maximum" in err


class TestConsistencyWithCLI:
    """The CLI matcher must return identical (bool, str) tuples for a
    shared fixture set.  This protects against the two implementations
    silently drifting apart.
    """

    # Path fix-up so we can import the CLI module from worker tests.
    _CLI_SRC = Path(__file__).resolve().parents[3] / "qa-studio-cli"

    @pytest.fixture(autouse=True)
    def _add_cli_to_path(self):
        path = str(self._CLI_SRC)
        added = path not in sys.path
        if added:
            sys.path.insert(0, path)
        yield
        if added:
            sys.path.remove(path)

    @pytest.mark.parametrize(
        "matcher,expected_json,actual",
        [
            ("exact", '{"a": 1}', {"a": 1}),
            ("exact", '{"a": 1}', {"a": 2}),
            ("subset", '{"a": 1}', {"a": 1, "b": 2}),
            ("subset", '{"user": {"name": "John"}}', {"user": {"name": "Jane"}}),
            ("subset", '{"tags": ["a", "b"]}', {"tags": ["a", "b"]}),
            ("subset", '{"tags": ["a"]}', {"tags": ["a", "b"]}),
            # Schema-mode fixtures — identical outcomes required in both impls.
            ("schema", '{"type": "object", "required": ["id"]}', {"id": "x"}),
            ("schema", '{"type": "object", "required": ["id"]}', {"name": "x"}),
            (
                "schema",
                '{"type": "array", "items": {"type": "string"}}',
                ["a", "b"],
            ),
            (
                "schema",
                '{"type": "array", "items": {"type": "string"}}',
                ["a", 2],
            ),
            ("schema", '{"$ref": "http://evil/s.json"}', {}),
            ("schema", 'not valid json', {}),
        ],
    )
    def test_parity(self, matcher, expected_json, actual):
        import network_matcher as worker_matcher
        from qa_studio_cli.runner import network_matcher as cli_matcher

        fn_name = f"match_{matcher}"
        worker_result = getattr(worker_matcher, fn_name)(expected_json, actual)
        cli_result = getattr(cli_matcher, fn_name)(expected_json, actual)
        assert worker_result == cli_result, (
            f"divergence for {matcher}({expected_json!r}, {actual!r}): "
            f"worker={worker_result}, cli={cli_result}"
        )


class TestConfigurableBodyCap:
    """The body-size cap is configurable via ``NETWORK_ASSERTION_BODY_MAX_BYTES``.

    The value is read at module-load time, so we verify both the re-import
    behaviour (env set before first import produces the overridden cap) and
    the internal helper's handling of malformed values.
    """

    def test_default_is_1_mib(self):
        assert MAX_BODY_SIZE == 1_048_576

    def test_read_helper_applies_env_override(self, monkeypatch):
        from network_matcher import _read_max_body_size

        monkeypatch.setenv("NETWORK_ASSERTION_BODY_MAX_BYTES", "500")
        assert _read_max_body_size() == 500

    def test_read_helper_falls_back_on_non_integer(self, monkeypatch):
        from network_matcher import _read_max_body_size

        monkeypatch.setenv("NETWORK_ASSERTION_BODY_MAX_BYTES", "not-a-number")
        assert _read_max_body_size() == 1_048_576

    def test_read_helper_falls_back_on_zero(self, monkeypatch):
        from network_matcher import _read_max_body_size

        monkeypatch.setenv("NETWORK_ASSERTION_BODY_MAX_BYTES", "0")
        assert _read_max_body_size() == 1_048_576

    def test_read_helper_falls_back_on_negative(self, monkeypatch):
        from network_matcher import _read_max_body_size

        monkeypatch.setenv("NETWORK_ASSERTION_BODY_MAX_BYTES", "-1")
        assert _read_max_body_size() == 1_048_576

    def test_module_cap_responds_to_env_on_reimport(self, monkeypatch):
        """Smallest body 501 is rejected when the cap is lowered to 500."""
        import importlib

        import network_matcher as nm

        monkeypatch.setenv("NETWORK_ASSERTION_BODY_MAX_BYTES", "500")
        try:
            reloaded = importlib.reload(nm)
            assert reloaded.MAX_BODY_SIZE == 500
            ok, err = reloaded.validate_body_size("x" * 501)
            assert ok is False
            assert "exceeds maximum" in err
            ok, _ = reloaded.validate_body_size("x" * 500)
            assert ok is True
        finally:
            # Reload once more with the original env so later tests see the
            # default 1 MiB cap.
            monkeypatch.delenv("NETWORK_ASSERTION_BODY_MAX_BYTES", raising=False)
            importlib.reload(nm)


class TestMatchSchema:
    """``match_schema`` validates actual against a JSON Schema Draft 2020-12
    document and rejects external ``$ref`` targets up-front.
    """

    def test_valid_object_passes(self):
        schema = '{"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}'
        ok, err = match_schema(schema, {"id": "abc-123"})
        assert ok is True
        assert err == ""

    def test_missing_required_fails(self):
        schema = '{"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}'
        ok, err = match_schema(schema, {"name": "x"})
        assert ok is False
        assert "required" in err.lower() or "'id'" in err

    def test_type_mismatch_fails(self):
        schema = '{"type": "object", "properties": {"age": {"type": "integer"}}}'
        ok, err = match_schema(schema, {"age": "thirty"})
        assert ok is False
        assert "age" in err

    def test_array_items_schema(self):
        schema = '{"type": "array", "items": {"type": "string"}}'
        ok, err = match_schema(schema, ["a", "b", "c"])
        assert ok is True

    def test_array_items_schema_fails_on_mixed_types(self):
        schema = '{"type": "array", "items": {"type": "string"}}'
        ok, err = match_schema(schema, ["a", 2, "c"])
        assert ok is False
        # Path should indicate which item failed (index 1)
        assert "1" in err

    def test_suites_list_motivating_case(self):
        """The user-journey case: every item in an array has required keys."""
        schema = json_dumps({
            "type": "object",
            "required": ["suites"],
            "properties": {
                "suites": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "name", "created_by"],
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "created_by": {"type": "string"},
                        },
                    },
                },
            },
        })
        actual = {
            "suites": [
                {"id": "a", "name": "First", "created_by": "x@y", "extra": True},
                {"id": "b", "name": "Second", "created_by": "x@y"},
            ],
        }
        ok, err = match_schema(schema, actual)
        assert ok is True, f"unexpected error: {err}"

    def test_actual_string_parsed_as_json(self):
        schema = '{"type": "object", "required": ["x"]}'
        ok, err = match_schema(schema, '{"x": 1}')
        assert ok is True

    def test_actual_non_parseable_string_fails(self):
        schema = '{"type": "object"}'
        ok, err = match_schema(schema, "not json")
        assert ok is False
        assert "captured body" in err

    def test_malformed_schema_rejected(self):
        ok, err = match_schema("not valid json", {})
        assert ok is False
        assert "invalid JSON" in err or "schema" in err

    def test_schema_must_be_object(self):
        ok, err = match_schema('"just a string"', {})
        assert ok is False
        assert "JSON object" in err

    def test_invalid_schema_rejected(self):
        # "type" must be a string, not a number
        ok, err = match_schema('{"type": 42}', {})
        assert ok is False
        assert "invalid JSON Schema" in err

    def test_external_ref_http_rejected(self):
        schema = '{"type": "object", "properties": {"x": {"$ref": "http://evil/schema.json"}}}'
        ok, err = match_schema(schema, {"x": 1})
        assert ok is False
        assert "external $ref" in err
        assert "http://evil" in err

    def test_external_ref_https_rejected(self):
        schema = '{"$ref": "https://evil/s.json"}'
        ok, err = match_schema(schema, {})
        assert ok is False
        assert "external $ref" in err

    def test_external_ref_file_rejected(self):
        schema = '{"$ref": "file:///etc/passwd"}'
        ok, err = match_schema(schema, {})
        assert ok is False
        assert "external $ref" in err

    def test_local_pointer_ref_allowed(self):
        """Schemas using $defs + local $ref should validate normally."""
        schema = json_dumps({
            "$defs": {"User": {"type": "object", "required": ["id"]}},
            "type": "object",
            "properties": {"user": {"$ref": "#/$defs/User"}},
        })
        ok, err = match_schema(schema, {"user": {"id": "x"}})
        assert ok is True, err
        ok, err = match_schema(schema, {"user": {"name": "no id"}})
        assert ok is False

    def test_bare_ref_identifier_rejected(self):
        schema = '{"$ref": "SomeBareName"}'
        ok, err = match_schema(schema, {})
        assert ok is False
        assert "local-pointer" in err

    def test_oversize_schema_rejected(self):
        oversize = '"' + ("a" * (MAX_BODY_SIZE + 10)) + '"'
        ok, err = match_schema(oversize, {})
        assert ok is False
        assert "exceeds maximum" in err


def json_dumps(obj):
    import json
    return json.dumps(obj)
