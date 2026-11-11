"""Tests for the import_schema validator.

Critical: any step-type or step-field that ships to the runtime must be
declared in import_schema.py too, or `qa-studio tests import` will
silently drop the field (pydantic v2 default extra='ignore') or reject
the whole file with a 'must be one of:' error.

This test file enforces:
- Every active step type validates (round-trip preserves step_type).
- Step-type-specific fields survive the round-trip (no silent drop).
- The shipped sample test (testcases/sample-app/date_workflow.json) is
  importable end-to-end — a regression guard, since we discovered that
  file was unimportable before this fix.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from qa_studio_cli.models.import_schema import (
    ExportPayload,
    ExportStep,
    VALID_STEP_TYPES,
)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _minimal_payload(steps: list[dict]) -> dict:
    """Build a minimal valid ExportPayload dict around a list of step dicts."""
    return {
        "exportVersion": "1.0",
        "exportedAt": "2024-01-02T15:00:00Z",
        "usecase": {"name": "Test", "starting_url": "https://example.com"},
        "steps": steps,
    }


# ── Step-type allow-list ─────────────────────────────────────────────────


class TestStepTypeAllowList:
    """Every active step type the runtime supports must validate here."""

    def test_all_active_step_types_in_allow_list(self):
        """Lockstep with the runtime: any step type the worker/CLI executes
        must be importable. Drift is the failure mode we're guarding against."""
        expected = {
            "navigation", "url", "browser", "secret", "validation",
            "retrieve_value", "assertion", "download", "transform",
            "network_assertion", "repeat",
        }
        assert set(VALID_STEP_TYPES) == expected

    @pytest.mark.parametrize("step_type", [
        "navigation", "url", "browser", "secret", "validation",
        "retrieve_value", "assertion", "download", "transform",
        "network_assertion",
    ])
    def test_each_step_type_validates(self, step_type):
        step = {"sort": 1, "instruction": "x", "step_type": step_type}
        ExportStep.model_validate(step)

    def test_unknown_step_type_rejected(self):
        with pytest.raises(ValidationError, match="must be one of"):
            ExportStep.model_validate({"sort": 1, "instruction": "x", "step_type": "banana"})


# ── Step-type-specific field round-trip ──────────────────────────────────


class TestFieldRoundTrip:
    """Every per-type field must survive validate -> model_dump.

    Pydantic v2's default extra='ignore' silently drops fields not declared
    on the model. The import flow does payload.model_dump(by_alias=False)
    before POSTing to the cloud, so any field we forget to declare here
    gets stripped before the cloud sees it — a silent data loss bug.
    """

    def test_browser_args_preserved(self):
        step = {
            "sort": 1, "instruction": "go", "step_type": "browser",
            "browser_action": "navigate",
            "browser_args": '{"url": "https://example.com"}',
        }
        dumped = ExportStep.model_validate(step).model_dump(by_alias=False)
        assert dumped["browser_action"] == "navigate"
        assert dumped["browser_args"] == '{"url": "https://example.com"}'

    def test_enable_advanced_click_types_preserved(self):
        step = {
            "sort": 1, "instruction": "click the toggle", "step_type": "navigation",
            "enable_advanced_click_types": True,
        }
        dumped = ExportStep.model_validate(step).model_dump(by_alias=False)
        assert dumped["enable_advanced_click_types"] is True

    def test_transform_args_preserved(self):
        step = {
            "sort": 1, "instruction": "x", "step_type": "transform",
            "transform_operation": "math",
            "transform_args": '{"expression": "1 + 2"}',
            "capture_variable": "result",
        }
        dumped = ExportStep.model_validate(step).model_dump(by_alias=False)
        assert dumped["transform_operation"] == "math"
        assert dumped["transform_args"] == '{"expression": "1 + 2"}'
        assert dumped["capture_variable"] == "result"

    def test_retrieve_value_date_fields_preserved(self):
        step = {
            "sort": 1, "instruction": "get the date", "step_type": "retrieve_value",
            "capture_variable": "order_date",
            "value_type": "date",
            "value_format": "%d/%m/%Y",
            "value_source": "screen",
        }
        dumped = ExportStep.model_validate(step).model_dump(by_alias=False)
        assert dumped["value_type"] == "date"
        assert dumped["value_format"] == "%d/%m/%Y"
        assert dumped["value_source"] == "screen"

    def test_network_assertion_fields_preserved(self):
        step = {
            "sort": 1, "instruction": "click submit", "step_type": "network_assertion",
            "network_url_pattern": "**/api/users",
            "network_method": "POST",
            "network_request_body": '{"name": "John"}',
            "network_body_match_type": "subset",
            "network_mock_response": '{"status": 201}',
            "network_mock_passthrough": False,
            "network_timeout": 15,
            "network_response_status": 201,
            "network_response_body": '{"type": "object"}',
            "network_response_body_match_type": "schema",
        }
        dumped = ExportStep.model_validate(step).model_dump(by_alias=False)
        for key in [
            "network_url_pattern", "network_method", "network_request_body",
            "network_body_match_type", "network_mock_response", "network_timeout",
            "network_response_status", "network_response_body",
            "network_response_body_match_type",
        ]:
            assert dumped[key] == step[key], f"Field '{key}' was dropped or altered"
        assert dumped["network_mock_passthrough"] is False

    def test_assertion_with_date_validation_type_preserved(self):
        step = {
            "sort": 1, "instruction": "compare dates", "step_type": "assertion",
            "assertion_variable": "order_date",
            "validation_type": "date",
            "validation_operator": "after",
            "validation_value": "{{ baseline_date }}",
        }
        dumped = ExportStep.model_validate(step).model_dump(by_alias=False)
        assert dumped["validation_type"] == "date"
        assert dumped["validation_operator"] == "after"


# ── Regression guard: the shipped sample test must validate ──────────────


class TestSampleTestImportable:
    """Real-world regression: testcases/sample-app/date_workflow.json was
    unimportable before this fix because it uses 'transform' step types."""

    SAMPLE_PATH = REPO_ROOT / "testcases" / "sample-app" / "date_workflow.json"

    def test_sample_date_workflow_validates(self):
        if not self.SAMPLE_PATH.is_file():
            pytest.skip(f"Sample file not found at {self.SAMPLE_PATH}")
        data = json.loads(self.SAMPLE_PATH.read_text())
        # Will raise ValidationError if any step is rejected.
        ExportPayload.model_validate(data)

    def test_sample_date_workflow_round_trip_preserves_transform_args(self):
        if not self.SAMPLE_PATH.is_file():
            pytest.skip(f"Sample file not found at {self.SAMPLE_PATH}")
        data = json.loads(self.SAMPLE_PATH.read_text())
        payload = ExportPayload.model_validate(data)
        dumped = payload.model_dump(by_alias=False)
        # Find the transform steps in the dump and confirm transform_args
        # is preserved verbatim.
        original_transforms = [s for s in data["steps"] if s.get("step_type") == "transform"]
        dumped_transforms = [s for s in dumped["steps"] if s.get("step_type") == "transform"]
        assert len(dumped_transforms) == len(original_transforms)
        for orig, dumped_step in zip(original_transforms, dumped_transforms):
            assert dumped_step["transform_args"] == orig["transform_args"]
            assert dumped_step["transform_operation"] == orig["transform_operation"]


# ── Top-level payload validation (existing behavior, regression guard) ───


class TestExportPayload:
    def test_minimum_valid_payload(self):
        ExportPayload.model_validate(_minimal_payload([
            {"sort": 1, "instruction": "click", "step_type": "navigation"},
        ]))

    def test_export_version_must_be_1_0(self):
        with pytest.raises(ValidationError, match='exportVersion must be "1.0"'):
            ExportPayload.model_validate(
                _minimal_payload([{"sort": 1, "instruction": "x", "step_type": "navigation"}])
                | {"exportVersion": "2.0"}
            )

    def test_steps_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            ExportPayload.model_validate(_minimal_payload([]))


class TestUsecasePlatform:
    """``test_platform`` must round-trip (the lambda reads it) and electron
    must be a first-class value with no mobile baggage."""

    def _payload(self, usecase_extra):
        return {
            "exportVersion": "1.0",
            "exportedAt": "2026-01-01T00:00:00Z",
            "usecase": {"name": "Harness", **usecase_extra},
            "steps": [{"instruction": "x", "step_type": "validation", "sort": 1}],
        }

    def test_default_platform_is_web(self):
        payload = ExportPayload.model_validate(self._payload({}))
        assert payload.usecase.test_platform == "web"

    @pytest.mark.parametrize("platform", ["web", "mobile", "electron"])
    def test_known_platforms_round_trip(self, platform):
        extra = {"test_platform": platform}
        if platform == "mobile":
            extra.update({"platform": "ANDROID", "app_package": "com.x", "app_activity": ".Main"})
        payload = ExportPayload.model_validate(self._payload(extra))
        assert payload.usecase.test_platform == platform
        assert payload.usecase.model_dump()["test_platform"] == platform

    def test_unknown_platform_rejected(self):
        with pytest.raises(ValidationError, match="test_platform must be one of"):
            ExportPayload.model_validate(self._payload({"test_platform": "tauri"}))

    def test_electron_needs_no_starting_url(self):
        payload = ExportPayload.model_validate(self._payload({"test_platform": "electron"}))
        assert payload.usecase.starting_url == ""

    def test_electron_rejects_mobile_fields(self):
        with pytest.raises(ValidationError, match="not allowed for electron"):
            ExportPayload.model_validate(self._payload({
                "test_platform": "electron", "platform": "ANDROID",
            }))

    def test_electron_allows_bundle_id(self):
        payload = ExportPayload.model_validate(self._payload({
            "test_platform": "electron", "bundle_id": "com.productharness.desktop",
        }))
        assert payload.usecase.model_dump()["bundle_id"] == "com.productharness.desktop"

    def test_mobile_fields_preserved_for_mobile(self):
        payload = ExportPayload.model_validate(self._payload({
            "test_platform": "mobile", "platform": "IOS", "bundle_id": "com.x.app",
        }))
        dumped = payload.usecase.model_dump()
        assert dumped["platform"] == "IOS"
        assert dumped["bundle_id"] == "com.x.app"



# ── Repeat steps (nested shape) ───────────────────────────────────────────


class TestRepeatStepSchema:
    def _repeat(self, **overrides):
        step = {
            "sort": 1, "instruction": "Login as each user", "step_type": "repeat",
            "repeat_columns": ["email", "role"],
            "repeat_rows": [["a@x.test", "admin"]],
            "steps": [
                {"sort": 2, "instruction": "Type {{email}}", "step_type": "navigation"},
            ],
        }
        step.update(overrides)
        return step

    def test_repeat_is_an_allowed_step_type(self):
        assert "repeat" in VALID_STEP_TYPES

    def test_nested_shape_round_trips(self):
        payload = ExportPayload.model_validate(_minimal_payload([self._repeat()]))
        dumped = payload.model_dump(exclude_none=True)
        repeat = dumped["steps"][0]
        assert repeat["repeat_columns"] == ["email", "role"]
        assert repeat["repeat_rows"] == [["a@x.test", "admin"]]
        assert repeat["steps"][0]["instruction"] == "Type {{email}}"

    def test_plain_step_dump_has_no_steps_key(self):
        payload = ExportPayload.model_validate(_minimal_payload([
            {"sort": 1, "instruction": "x", "step_type": "navigation"},
        ]))
        dumped = payload.model_dump(exclude_none=True, exclude_defaults=True)
        assert "steps" not in dumped["steps"][0]
        assert "parent_step_id" not in dumped["steps"][0]

    def test_steps_only_allowed_on_repeat(self):
        with pytest.raises(ValidationError, match="only repeat"):
            ExportStep.model_validate({
                "sort": 1, "instruction": "x", "step_type": "navigation",
                "steps": [{"sort": 2, "instruction": "y", "step_type": "navigation"}],
            })

    def test_repeat_inside_repeat_rejected(self):
        with pytest.raises(ValidationError, match="one level"):
            ExportStep.model_validate(self._repeat(steps=[self._repeat(sort=2, instruction="inner", steps=[])]))

    def test_repeat_requires_columns_and_rows(self):
        with pytest.raises(ValidationError, match="repeat_columns"):
            ExportStep.model_validate(self._repeat(repeat_columns=None))

    def test_repeat_dataset_rules_applied(self):
        with pytest.raises(ValidationError, match="reserved"):
            ExportStep.model_validate(self._repeat(repeat_columns=["UniqueID"], repeat_rows=[["x"]]))

    def test_dataset_fields_only_on_repeat(self):
        with pytest.raises(ValidationError, match="only allowed on repeat"):
            ExportStep.model_validate({
                "sort": 1, "instruction": "x", "step_type": "navigation", "repeat_columns": ["a"],
            })

    def test_dataset_id_only_on_repeat(self):
        with pytest.raises(ValidationError, match="dataset_id is only allowed on repeat"):
            ExportStep.model_validate({
                "sort": 1, "instruction": "x", "step_type": "navigation", "dataset_id": "ds-1",
            })

    def test_repeat_with_dataset_id_round_trips_without_inline_rows(self):
        step = self._repeat(repeat_columns=None, repeat_rows=None, dataset_id="ds-1")
        payload = ExportPayload.model_validate(_minimal_payload([step]))
        dumped = payload.model_dump(exclude_none=True)
        repeat = dumped["steps"][0]
        assert repeat["dataset_id"] == "ds-1"
        assert "repeat_columns" not in repeat and "repeat_rows" not in repeat
        assert repeat["steps"][0]["instruction"] == "Type {{email}}"

    def test_repeat_with_both_sources_rejected(self):
        with pytest.raises(ValidationError, match="cannot have both dataset_id and inline rows"):
            ExportStep.model_validate(self._repeat(dataset_id="ds-1"))

    def test_repeat_with_neither_source_rejected(self):
        with pytest.raises(ValidationError, match="either dataset_id or repeat_columns/repeat_rows"):
            ExportStep.model_validate(self._repeat(repeat_columns=None, repeat_rows=None))

    def test_flat_parent_step_id_preserved(self):
        step = ExportStep.model_validate({
            "id": "c", "sort": 2, "instruction": "x", "step_type": "navigation", "parent_step_id": "r",
        })
        assert step.parent_step_id == "r"
