"""Tests for the transform step executor."""

import json

import pytest

from models import ExecutionStep
from transform_step import execute_transform_step


class FakeTemplateParser:
    """Minimal template parser that resolves {{ var }} references."""

    def __init__(self, variables: dict[str, str] | None = None):
        self._vars = variables or {}

    def parse_instruction(self, text: str) -> str:
        import re
        def _replace(m):
            key = m.group(1).strip()
            return self._vars.get(key, m.group(0))
        return re.sub(r"\{\{\s*(\w+)\s*\}\}", _replace, text)


def _make_step(**overrides) -> ExecutionStep:
    defaults = dict(
        pk="EXECUTION#e1", sk="EXECUTION_STEP#s1", step_id="s1", sort=1,
        instruction="", artefact="", logs=[], created_at="2026-01-01",
        secret_key="", step_type="transform", validation_type="",
        validation_operator="", validation_value="", capture_variable="result",
        value_type="", assertion_variable="",
    )
    defaults.update(overrides)
    return ExecutionStep(**defaults)


class TestTransformStepExecutor:
    """Integration tests for execute_transform_step."""

    def test_math_expression(self):
        step = _make_step(
            transform_operation="math",
            transform_args=json.dumps({"expression": "2 + 3 * 4"}),
        )
        _, success, logs, actual = execute_transform_step(step, FakeTemplateParser())
        assert success
        assert actual == "14"

    def test_math_with_variables(self):
        step = _make_step(
            transform_operation="math",
            transform_args=json.dumps({"expression": "{{ price }} * {{ qty }}"}),
        )
        tp = FakeTemplateParser({"price": "10", "qty": "3"})
        _, success, logs, actual = execute_transform_step(step, tp)
        assert success
        assert actual == "30"

    def test_concat(self):
        step = _make_step(
            transform_operation="concat",
            transform_args=json.dumps({"values": ["hello", " ", "{{ name }}"]}),
        )
        tp = FakeTemplateParser({"name": "world"})
        _, success, logs, actual = execute_transform_step(step, tp)
        assert success
        assert actual == "hello world"

    def test_regex_extract(self):
        step = _make_step(
            transform_operation="regex_extract",
            transform_args=json.dumps({
                "value": "Order #12345 placed",
                "pattern": r"#(\d+)",
                "group": 1,
            }),
        )
        _, success, logs, actual = execute_transform_step(step, FakeTemplateParser())
        assert success
        assert actual == "12345"

    def test_floor(self):
        step = _make_step(
            transform_operation="floor",
            transform_args=json.dumps({"value": "{{ price }}"}),
        )
        tp = FakeTemplateParser({"price": "9.99"})
        _, success, logs, actual = execute_transform_step(step, tp)
        assert success
        assert actual == "9"

    def test_format_operation(self):
        step = _make_step(
            transform_operation="format",
            transform_args=json.dumps({"template": "Order #{}", "args": ["{{ id }}"]}),
        )
        tp = FakeTemplateParser({"id": "42"})
        _, success, logs, actual = execute_transform_step(step, tp)
        assert success
        assert actual == "Order #42"


class TestTransformStepFailures:
    """Test failure paths."""

    def test_unknown_operation(self):
        step = _make_step(transform_operation="eval", transform_args="{}")
        _, success, logs, _ = execute_transform_step(step, FakeTemplateParser())
        assert not success
        assert "Unknown transform operation" in logs

    def test_missing_capture_variable(self):
        step = _make_step(
            transform_operation="math",
            transform_args=json.dumps({"expression": "1+1"}),
            capture_variable="",
        )
        _, success, logs, _ = execute_transform_step(step, FakeTemplateParser())
        assert not success
        assert "capture_variable is required" in logs

    def test_invalid_json_args(self):
        step = _make_step(
            transform_operation="math",
            transform_args="{bad json",
        )
        _, success, logs, _ = execute_transform_step(step, FakeTemplateParser())
        assert not success
        assert "Invalid transform_args JSON" in logs

    def test_math_error(self):
        step = _make_step(
            transform_operation="math",
            transform_args=json.dumps({"expression": "1 / 0"}),
        )
        _, success, logs, _ = execute_transform_step(step, FakeTemplateParser())
        assert not success
        assert "failed" in logs.lower()

    def test_missing_args(self):
        step = _make_step(
            transform_operation="math",
            transform_args=None,
        )
        _, success, logs, _ = execute_transform_step(step, FakeTemplateParser())
        assert not success

    def test_pydantic_validation_error(self):
        step = _make_step(
            transform_operation="floor",
            transform_args=json.dumps({}),  # missing required 'value'
        )
        _, success, logs, _ = execute_transform_step(step, FakeTemplateParser())
        assert not success
        assert "failed" in logs.lower()

    def test_result_is_always_none(self):
        """Transform steps never return a NovaAct result object."""
        step = _make_step(
            transform_operation="math",
            transform_args=json.dumps({"expression": "1 + 1"}),
        )
        result, success, _, _ = execute_transform_step(step, FakeTemplateParser())
        assert result is None
        assert success
