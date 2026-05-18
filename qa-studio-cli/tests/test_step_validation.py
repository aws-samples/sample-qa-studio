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


# ── validation_type = "date" ────────────────────────────────────────────


from qa_studio_cli.validation import (
    VALID_DATE_OPERATORS,
    VALID_DATE_DURATION_UNITS,
    validate_date_validation_type,
)


def _date_step(operator: str, validation_value: str = "2024-01-02") -> dict:
    return {
        "step_type": "assertion",
        "validation_type": "date",
        "validation_operator": operator,
        "validation_value": validation_value,
        "assertion_variable": "captured",
    }


class TestValidateStepDispatchesToDate:
    def test_dispatches_when_validation_type_is_date(self):
        step = _date_step(operator="banana")
        is_valid, errors = validate_step(step)
        assert is_valid is False
        assert any("date" in e and "banana" in e for e in errors)

    def test_does_not_dispatch_when_validation_type_is_string(self):
        # Existing string assertion; should not be touched by date validator.
        step = {
            "step_type": "assertion",
            "validation_type": "string",
            "validation_operator": "exact",
            "validation_value": "hello",
            "assertion_variable": "captured",
        }
        is_valid, _ = validate_step(step)
        assert is_valid is True

    def test_step_type_validators_take_precedence_over_date(self):
        # A transform step with validation_type=date should still be validated
        # as a transform — the per-step-type validators run first.
        step = {
            "step_type": "transform",
            "validation_type": "date",  # nonsensical here but shouldn't matter
            # ... missing transform_operation
        }
        is_valid, errors = validate_step(step)
        assert is_valid is False
        # Errors should be about transform shape, not date shape.
        assert any("transform_operation" in e for e in errors)


class TestValidateDateOperator:
    @pytest.mark.parametrize("op", sorted(VALID_DATE_OPERATORS - {"equals_within"}))
    def test_each_simple_operator_with_value_is_valid(self, op):
        is_valid, errors = validate_date_validation_type(_date_step(operator=op))
        assert is_valid, f"Expected '{op}' to validate; got: {errors}"

    def test_unknown_operator_rejected(self):
        is_valid, errors = validate_date_validation_type(_date_step(operator="banana"))
        assert is_valid is False
        assert any("banana" in e for e in errors)
        assert any(o in errors[0] for o in VALID_DATE_OPERATORS)

    def test_missing_operator_rejected(self):
        step = _date_step(operator="")
        is_valid, errors = validate_date_validation_type(step)
        assert is_valid is False

    @pytest.mark.parametrize("op", sorted(VALID_DATE_OPERATORS - {"equals_within"}))
    def test_simple_operators_require_non_empty_value(self, op):
        is_valid, errors = validate_date_validation_type(
            _date_step(operator=op, validation_value="")
        )
        assert is_valid is False
        assert any("validation_value is required" in e for e in errors)

    def test_simple_operator_whitespace_only_value_rejected(self):
        is_valid, errors = validate_date_validation_type(
            _date_step(operator="equals", validation_value="   ")
        )
        assert is_valid is False

    def test_simple_operator_does_not_parse_date_at_validation_time(self):
        # validation_value may be a {{ var }} reference; must not be parsed here.
        step = _date_step(operator="equals", validation_value="{{ order_date }}")
        is_valid, errors = validate_date_validation_type(step)
        assert is_valid, f"Variable reference should pass client validation; got: {errors}"


class TestValidateEqualsWithinPayload:
    def _payload(self, **overrides):
        base = {"date": "2024-01-02T15:00:00+00:00", "tolerance": 5, "unit": "minutes"}
        base.update(overrides)
        return json.dumps(base)

    def test_valid_payload_accepted(self):
        is_valid, errors = validate_date_validation_type(
            _date_step(operator="equals_within", validation_value=self._payload())
        )
        assert is_valid, errors

    def test_zero_tolerance_accepted(self):
        is_valid, _ = validate_date_validation_type(
            _date_step(operator="equals_within", validation_value=self._payload(tolerance=0))
        )
        assert is_valid is True

    def test_missing_value_rejected(self):
        is_valid, errors = validate_date_validation_type(
            _date_step(operator="equals_within", validation_value="")
        )
        assert is_valid is False
        assert any("required" in e for e in errors)

    def test_malformed_json_rejected(self):
        is_valid, errors = validate_date_validation_type(
            _date_step(operator="equals_within", validation_value="not-json{{{")
        )
        assert is_valid is False
        assert any("valid JSON" in e for e in errors)

    def test_top_level_array_rejected(self):
        is_valid, errors = validate_date_validation_type(
            _date_step(
                operator="equals_within",
                validation_value=json.dumps(["2024-01-02", 5, "minutes"]),
            )
        )
        assert is_valid is False
        assert any("must be a JSON object" in e for e in errors)

    def test_missing_date_field_rejected(self):
        is_valid, errors = validate_date_validation_type(
            _date_step(
                operator="equals_within",
                validation_value=json.dumps({"tolerance": 5, "unit": "minutes"}),
            )
        )
        assert is_valid is False
        assert any("'date'" in e for e in errors)

    def test_empty_date_field_rejected(self):
        is_valid, errors = validate_date_validation_type(
            _date_step(operator="equals_within", validation_value=self._payload(date=""))
        )
        assert is_valid is False
        assert any("'date'" in e for e in errors)

    def test_missing_tolerance_field_rejected(self):
        is_valid, errors = validate_date_validation_type(
            _date_step(
                operator="equals_within",
                validation_value=json.dumps({"date": "2024-01-02", "unit": "minutes"}),
            )
        )
        assert is_valid is False
        assert any("'tolerance'" in e for e in errors)

    def test_negative_tolerance_rejected(self):
        is_valid, errors = validate_date_validation_type(
            _date_step(operator="equals_within", validation_value=self._payload(tolerance=-1))
        )
        assert is_valid is False
        assert any("non-negative" in e for e in errors)

    def test_non_integer_tolerance_rejected(self):
        is_valid, errors = validate_date_validation_type(
            _date_step(operator="equals_within", validation_value=self._payload(tolerance=1.5))
        )
        assert is_valid is False
        assert any("integer" in e for e in errors)

    def test_bool_tolerance_rejected(self):
        # bool is a subclass of int in Python; we explicitly exclude it.
        is_valid, errors = validate_date_validation_type(
            _date_step(operator="equals_within", validation_value=self._payload(tolerance=True))
        )
        assert is_valid is False
        assert any("integer" in e for e in errors)

    def test_missing_unit_field_rejected(self):
        is_valid, errors = validate_date_validation_type(
            _date_step(
                operator="equals_within",
                validation_value=json.dumps({"date": "2024-01-02", "tolerance": 5}),
            )
        )
        assert is_valid is False
        assert any("'unit'" in e for e in errors)

    def test_unsupported_unit_rejected(self):
        is_valid, errors = validate_date_validation_type(
            _date_step(operator="equals_within", validation_value=self._payload(unit="months"))
        )
        assert is_valid is False
        assert any("'unit'" in e for e in errors)

    @pytest.mark.parametrize("unit", sorted(VALID_DATE_DURATION_UNITS))
    def test_each_supported_unit_accepted(self, unit):
        is_valid, _ = validate_date_validation_type(
            _date_step(operator="equals_within", validation_value=self._payload(unit=unit))
        )
        assert is_valid, f"Unit '{unit}' should be accepted"


# ── Transform op registry includes date ops ─────────────────────────────


class TestDateOpsInTransformRegistry:
    @pytest.mark.parametrize("op", [
        "parse_date", "format_date", "add_duration", "date_diff", "to_epoch",
    ])
    def test_date_ops_accepted_by_transform_validator(self, op):
        step = {
            "step_type": "transform",
            "transform_operation": op,
            "transform_args": json.dumps({"value": "x"}),  # shape varies but JSON-valid
            "capture_variable": "result",
        }
        is_valid, errors = validate_transform_step(step)
        assert is_valid, f"Date op '{op}' should be in transform registry; got: {errors}"
