"""Tests for browser and transform schema fields on ExecutionStep."""

import pytest
from models import ExecutionStep


def _make_step(**overrides) -> ExecutionStep:
    """Create an ExecutionStep with sensible defaults, applying overrides."""
    defaults = dict(
        pk="EXECUTION#exec-1",
        sk="EXECUTION_STEP#step-1",
        step_id="step-1",
        sort=1,
        instruction="Click the button",
        artefact="",
        logs=[],
        created_at="2026-04-28T12:00:00Z",
        secret_key="",
        step_type="navigation",
        validation_type="",
        validation_operator="",
        validation_value="",
        capture_variable="",
        value_type="",
        assertion_variable="",
    )
    defaults.update(overrides)
    return ExecutionStep(**defaults)


class TestExecutionStepNewFields:
    """Verify the four new optional fields on ExecutionStep."""

    def test_defaults_are_none(self):
        step = _make_step()
        assert step.browser_action is None
        assert step.browser_args is None
        assert step.transform_operation is None
        assert step.transform_args is None

    def test_existing_construction_unchanged(self):
        """Existing code that doesn't pass the new fields still works."""
        step = _make_step(step_type="url")
        assert step.step_type == "url"
        assert step.browser_action is None

    def test_browser_step_fields(self):
        step = _make_step(
            step_type="browser",
            browser_action="reload",
            browser_args='{"hard": true}',
        )
        assert step.step_type == "browser"
        assert step.browser_action == "reload"
        assert step.browser_args == '{"hard": true}'
        assert step.transform_operation is None

    def test_transform_step_fields(self):
        step = _make_step(
            step_type="transform",
            transform_operation="math",
            transform_args='{"expression": "{{ price }} * 1.2"}',
            capture_variable="expected_total",
        )
        assert step.step_type == "transform"
        assert step.transform_operation == "math"
        assert step.transform_args == '{"expression": "{{ price }} * 1.2"}'
        assert step.capture_variable == "expected_total"
        assert step.browser_action is None


class TestDynamoDBItemParsing:
    """Simulate DynamoDB item parsing with the new fields."""

    def _parse_item(self, item: dict) -> ExecutionStep:
        """Mirror the DynamoDB client's parsing pattern."""
        return ExecutionStep(
            pk=item.get('pk', ''),
            sk=item.get('sk', ''),
            step_id=item.get('step_id', ''),
            sort=item.get('sort', 0),
            instruction=item.get('instruction', ''),
            artefact=item.get('artefact', ''),
            logs=item.get('logs', []),
            created_at=item.get('created_at', ''),
            secret_key=item.get('secret_key', ''),
            step_type=item.get('step_type', ''),
            validation_type=item.get('validation_type', ''),
            validation_operator=item.get('validation_operator', ''),
            validation_value=item.get('validation_value', ''),
            capture_variable=item.get('capture_variable', ''),
            value_type=item.get('value_type', ''),
            assertion_variable=item.get('assertion_variable', ''),
            enable_advanced_click_types=item.get('enable_advanced_click_types', False),
            value_source=item.get('value_source', ''),
            cached_steps=item.get('cached_steps', None),
            cache_last_updated=item.get('cache_last_updated', None),
            trajectory_s3_key=item.get('trajectory_s3_key', None),
            trajectory_last_updated=item.get('trajectory_last_updated', None),
            browser_action=item.get('browser_action', None),
            browser_args=item.get('browser_args', None),
            transform_operation=item.get('transform_operation', None),
            transform_args=item.get('transform_args', None),
        )

    def test_legacy_item_without_new_fields(self):
        """Items written before this feature have no new fields — defaults to None."""
        item = {
            'pk': 'EXECUTION#e1', 'sk': 'EXECUTION_STEP#s1',
            'step_id': 's1', 'sort': 1, 'instruction': 'Click',
            'created_at': '2026-01-01', 'step_type': 'navigation',
        }
        step = self._parse_item(item)
        assert step.browser_action is None
        assert step.transform_operation is None

    def test_browser_item_round_trip(self):
        item = {
            'pk': 'EXECUTION#e1', 'sk': 'EXECUTION_STEP#s2',
            'step_id': 's2', 'sort': 2, 'instruction': '',
            'created_at': '2026-01-01', 'step_type': 'browser',
            'browser_action': 'back',
            'browser_args': '{}',
        }
        step = self._parse_item(item)
        assert step.step_type == "browser"
        assert step.browser_action == "back"
        assert step.browser_args == "{}"

    def test_transform_item_round_trip(self):
        item = {
            'pk': 'EXECUTION#e1', 'sk': 'EXECUTION_STEP#s3',
            'step_id': 's3', 'sort': 3, 'instruction': '',
            'created_at': '2026-01-01', 'step_type': 'transform',
            'transform_operation': 'floor',
            'transform_args': '{"value": "{{ price }}"}',
            'capture_variable': 'floored_price',
        }
        step = self._parse_item(item)
        assert step.step_type == "transform"
        assert step.transform_operation == "floor"
        assert step.capture_variable == "floored_price"
