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
            "network_assertion",
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
