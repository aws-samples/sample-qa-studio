"""Tests for browser and transform step validation."""

import json

import pytest

from qa_studio_cli.validation import (
    VALID_BROWSER_ACTIONS,
    VALID_TRANSFORM_OPERATIONS,
    validate_browser_step,
    validate_step,
    validate_transform_step,
)


class TestValidateStep:
    """Top-level dispatch tests."""

    def test_unknown_step_type_passes(self):
        is_valid, errors = validate_step({"step_type": "navigation"})
        assert is_valid

    def test_dispatches_to_browser(self):
        is_valid, errors = validate_step({"step_type": "browser"})
        assert not is_valid
        assert any("browser_action" in e for e in errors)

    def test_dispatches_to_transform(self):
        is_valid, errors = validate_step({"step_type": "transform"})
        assert not is_valid
        assert any("transform_operation" in e for e in errors)


class TestValidateBrowserStep:
    """Tests for browser step validation."""

    def test_valid_reload(self):
        step = {"step_type": "browser", "browser_action": "reload"}
        is_valid, errors = validate_browser_step(step)
        assert is_valid

    def test_valid_back(self):
        step = {"step_type": "browser", "browser_action": "back"}
        is_valid, errors = validate_browser_step(step)
        assert is_valid

    def test_valid_forward(self):
        step = {"step_type": "browser", "browser_action": "forward"}
        is_valid, errors = validate_browser_step(step)
        assert is_valid

    def test_valid_navigate_with_url(self):
        step = {
            "step_type": "browser",
            "browser_action": "navigate",
            "browser_args": json.dumps({"url": "https://example.com"}),
        }
        is_valid, errors = validate_browser_step(step)
        assert is_valid

    def test_missing_browser_action(self):
        step = {"step_type": "browser"}
        is_valid, errors = validate_browser_step(step)
        assert not is_valid
        assert any("browser_action is required" in e for e in errors)

    def test_invalid_browser_action(self):
        step = {"step_type": "browser", "browser_action": "close_tab"}
        is_valid, errors = validate_browser_step(step)
        assert not is_valid
        assert any("Invalid browser_action" in e for e in errors)

    def test_navigate_missing_args(self):
        step = {"step_type": "browser", "browser_action": "navigate"}
        is_valid, errors = validate_browser_step(step)
        assert not is_valid
        assert any("url is required" in e for e in errors)

    def test_navigate_missing_url_in_args(self):
        step = {
            "step_type": "browser",
            "browser_action": "navigate",
            "browser_args": json.dumps({"hard": True}),
        }
        is_valid, errors = validate_browser_step(step)
        assert not is_valid
        assert any("url is required" in e for e in errors)

    def test_malformed_json_args(self):
        step = {
            "step_type": "browser",
            "browser_action": "reload",
            "browser_args": "not json{",
        }
        is_valid, errors = validate_browser_step(step)
        assert not is_valid
        assert any("valid JSON" in e for e in errors)

    def test_reload_with_hard_arg(self):
        step = {
            "step_type": "browser",
            "browser_action": "reload",
            "browser_args": json.dumps({"hard": True}),
        }
        is_valid, errors = validate_browser_step(step)
        assert is_valid


class TestValidateTransformStep:
    """Tests for transform step validation."""

    def test_valid_math(self):
        step = {
            "step_type": "transform",
            "transform_operation": "math",
            "transform_args": json.dumps({"expression": "{{ price }} * 1.2"}),
            "capture_variable": "total",
        }
        is_valid, errors = validate_transform_step(step)
        assert is_valid

    def test_valid_concat(self):
        step = {
            "step_type": "transform",
            "transform_operation": "concat",
            "transform_args": json.dumps({"values": ["hello", " ", "world"]}),
            "capture_variable": "greeting",
        }
        is_valid, errors = validate_transform_step(step)
        assert is_valid

    def test_missing_operation(self):
        step = {
            "step_type": "transform",
            "transform_args": "{}",
            "capture_variable": "x",
        }
        is_valid, errors = validate_transform_step(step)
        assert not is_valid
        assert any("transform_operation is required" in e for e in errors)

    def test_invalid_operation(self):
        step = {
            "step_type": "transform",
            "transform_operation": "eval",
            "transform_args": "{}",
            "capture_variable": "x",
        }
        is_valid, errors = validate_transform_step(step)
        assert not is_valid
        assert any("Invalid transform_operation" in e for e in errors)

    def test_missing_capture_variable(self):
        step = {
            "step_type": "transform",
            "transform_operation": "math",
            "transform_args": json.dumps({"expression": "1 + 1"}),
        }
        is_valid, errors = validate_transform_step(step)
        assert not is_valid
        assert any("capture_variable is required" in e for e in errors)

    def test_missing_transform_args(self):
        step = {
            "step_type": "transform",
            "transform_operation": "math",
            "capture_variable": "x",
        }
        is_valid, errors = validate_transform_step(step)
        assert not is_valid
        assert any("transform_args is required" in e for e in errors)

    def test_malformed_json_args(self):
        step = {
            "step_type": "transform",
            "transform_operation": "math",
            "transform_args": "{bad json",
            "capture_variable": "x",
        }
        is_valid, errors = validate_transform_step(step)
        assert not is_valid
        assert any("valid JSON" in e for e in errors)

    @pytest.mark.parametrize("op", sorted(VALID_TRANSFORM_OPERATIONS))
    def test_all_known_operations_accepted(self, op):
        step = {
            "step_type": "transform",
            "transform_operation": op,
            "transform_args": json.dumps({"value": "1"}),
            "capture_variable": "result",
        }
        is_valid, errors = validate_transform_step(step)
        assert is_valid, f"Operation '{op}' should be valid but got errors: {errors}"
