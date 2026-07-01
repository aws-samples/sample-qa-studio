"""Tests for the CLI TemplateParser.

Mirrors the behavioural contract of ``web-app/worker/template_parser.py``
(R-PARITY-2 in .kiro/specs/cli-unified-runner/requirements.md).
"""

import re

import pytest

from qa_studio_cli.runner.template_parser import TemplateParser


class TestBuiltins:
    def test_unique_id_is_five_alphanumeric_chars(self):
        parser = TemplateParser()
        result = parser.parse_instruction("id={{UniqueID}}")
        match = re.match(r"^id=([A-Za-z0-9]{5})$", result)
        assert match is not None, f"unexpected format: {result!r}"

    def test_unique_id_is_stable_within_parser(self):
        parser = TemplateParser()
        first = parser.parse_instruction("{{UniqueID}}")
        second = parser.parse_instruction("{{UniqueID}}")
        assert first == second

    def test_time_is_iso_shape(self):
        parser = TemplateParser()
        result = parser.parse_instruction("at={{Time}}")
        # %Y-%m-%dT%H:%M:%SZ
        assert re.match(r"^at=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", result)

    def test_execution_id_resolves(self):
        parser = TemplateParser(execution_id="exec-123")
        assert parser.parse_instruction("e={{ExecutionID}}") == "e=exec-123"

    def test_created_at_resolves(self):
        parser = TemplateParser(created_at="2026-01-02T00:00:00Z")
        assert parser.parse_instruction("c={{CreatedAt}}") == "c=2026-01-02T00:00:00Z"


class TestUserAndRuntime:
    def test_user_variable_resolves(self):
        parser = TemplateParser(variables={"foo": "bar"})
        assert parser.parse_instruction("{{foo}}") == "bar"

    def test_runtime_variable_overrides_user_variable(self):
        parser = TemplateParser(
            variables={"foo": "user"},
            runtime_variables={"foo": "runtime"},
        )
        assert parser.parse_instruction("{{foo}}") == "runtime"

    def test_add_runtime_variable_updates_state(self):
        parser = TemplateParser(variables={"foo": "user"})
        assert parser.parse_instruction("{{foo}}") == "user"
        parser.add_runtime_variable("foo", "runtime")
        assert parser.parse_instruction("{{foo}}") == "runtime"

    def test_unknown_placeholder_left_intact(self):
        parser = TemplateParser()
        assert parser.parse_instruction("{{absent}}") == "{{absent}}"

    def test_multiple_placeholders_resolve(self):
        parser = TemplateParser(variables={"a": "1", "b": "2"})
        assert parser.parse_instruction("{{a}}-{{b}}-{{a}}") == "1-2-1"

    def test_empty_string_returns_empty(self):
        parser = TemplateParser(variables={"x": "y"})
        assert parser.parse_instruction("") == ""

    def test_none_returns_none(self):
        parser = TemplateParser()
        assert parser.parse_instruction(None) is None


class TestBuiltinProtection:
    @pytest.mark.parametrize("name", ["UniqueID", "Time", "ExecutionID", "CreatedAt"])
    def test_cannot_override_builtin(self, name):
        parser = TemplateParser()
        with pytest.raises(ValueError, match="built-in"):
            parser.add_runtime_variable(name, "hijack")

    def test_builtin_wins_over_user_variable_collision(self):
        # Constructor allows a user variable named 'UniqueID' to sneak in,
        # but the merged-variable order ensures the built-in wins.
        parser = TemplateParser(variables={"UniqueID": "hijack"})
        result = parser.parse_instruction("{{UniqueID}}")
        assert result != "hijack"

    def test_rejects_empty_name(self):
        parser = TemplateParser()
        with pytest.raises(ValueError, match="Invalid variable name"):
            parser.add_runtime_variable("", "value")

    def test_rejects_non_string_name(self):
        parser = TemplateParser()
        with pytest.raises(ValueError, match="Invalid variable name"):
            parser.add_runtime_variable(None, "value")  # type: ignore[arg-type]


class TestStateAccessors:
    def test_get_runtime_variables_dict_is_defensive_copy(self):
        parser = TemplateParser(runtime_variables={"a": "1"})
        snapshot = parser.get_runtime_variables_dict()
        snapshot["a"] = "mutated"
        assert parser.parse_instruction("{{a}}") == "1"

    def test_get_all_variables_includes_builtins(self):
        parser = TemplateParser(variables={"foo": "bar"})
        all_vars = parser.get_all_variables()
        assert "UniqueID" in all_vars
        assert "Time" in all_vars
        assert "foo" in all_vars
        assert all_vars["foo"] == "bar"
