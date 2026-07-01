"""Tests for network_assertion step schema fields on ExecutionStep
and their round-trip through the DynamoDB client loader.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Worker code is a flat module; tests are a subpackage.  Add the worker
# directory to sys.path so we can import `models` and `dynamodb_client`
# without installing the worker as a package.
_WORKER_DIR = Path(__file__).resolve().parent.parent
if str(_WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKER_DIR))

from models import ExecutionStep  # noqa: E402


def _base_step_kwargs(**overrides):
    """Build the mandatory positional args for ExecutionStep."""
    defaults = dict(
        pk="EXECUTION#e1",
        sk="EXECUTION_STEP#s1",
        step_id="s1",
        sort=1,
        instruction="Click submit",
        artefact="",
        logs=[],
        created_at="2026-01-01T00:00:00Z",
        secret_key="",
        step_type="network_assertion",
        validation_type="",
        validation_operator="",
        validation_value="",
        capture_variable="",
        value_type="",
        assertion_variable="",
    )
    defaults.update(overrides)
    return defaults


class TestExecutionStepNetworkAssertionFields:
    """The new optional fields should have sensible defaults and round-trip."""

    def test_defaults_are_none_or_false(self):
        step = ExecutionStep(**_base_step_kwargs())

        assert step.network_url_pattern is None
        assert step.network_method is None
        assert step.network_request_body is None
        assert step.network_body_match_type is None
        assert step.network_mock_response is None
        assert step.network_mock_passthrough is False
        assert step.network_timeout is None
        # Response-side fields — all optional, default None.
        assert step.network_response_body is None
        assert step.network_response_body_match_type is None
        assert step.network_response_status is None

    def test_all_fields_populated(self):
        step = ExecutionStep(
            **_base_step_kwargs(
                network_url_pattern="**/api/users",
                network_method="POST",
                network_request_body='{"name": "John"}',
                network_body_match_type="subset",
                network_mock_response='{"status": 201, "body": {"id": "abc"}}',
                network_mock_passthrough=True,
                network_timeout=30,
                network_response_body='{"type": "object", "required": ["id"]}',
                network_response_body_match_type="schema",
                network_response_status=201,
            )
        )

        assert step.network_url_pattern == "**/api/users"
        assert step.network_method == "POST"
        assert step.network_request_body == '{"name": "John"}'
        assert step.network_body_match_type == "subset"
        assert step.network_mock_response == '{"status": 201, "body": {"id": "abc"}}'
        assert step.network_mock_passthrough is True
        assert step.network_timeout == 30
        assert step.network_response_body == '{"type": "object", "required": ["id"]}'
        assert step.network_response_body_match_type == "schema"
        assert step.network_response_status == 201

    def test_existing_step_construction_without_new_fields_still_works(self):
        # A pre-existing step type (e.g., 'navigation') should be constructible
        # without mentioning any of the new fields.
        step = ExecutionStep(**_base_step_kwargs(step_type="navigation"))
        assert step.step_type == "navigation"
        assert step.network_url_pattern is None


class TestDynamoDBLoaderNetworkAssertionFields:
    """`get_execution_steps` should load the new fields with defaults."""

    @pytest.fixture
    def client(self):
        from dynamodb_client import DynamoDBClient

        with patch("dynamodb_client.boto3") as boto3_mock:
            boto3_mock.resource.return_value.Table.return_value = MagicMock()
            client = DynamoDBClient("table", "us-east-1")
        return client

    @staticmethod
    def _item(**overrides):
        base = {
            "pk": "EXECUTION#e1",
            "sk": "EXECUTION_STEP#s1",
            "step_id": "s1",
            "sort": 1,
            "instruction": "Click submit",
            "artefact": "",
            "logs": [],
            "created_at": "2026-01-01T00:00:00Z",
            "secret_key": "",
            "step_type": "network_assertion",
            "validation_type": "",
            "validation_operator": "",
            "validation_value": "",
            "capture_variable": "",
            "value_type": "",
            "assertion_variable": "",
        }
        base.update(overrides)
        return base

    def test_loads_network_fields_when_present(self, client):
        item = self._item(
            network_url_pattern="**/api/users",
            network_method="POST",
            network_request_body='{"name": "John"}',
            network_body_match_type="subset",
            network_mock_response='{"status": 201}',
            network_mock_passthrough=True,
            network_timeout=30,
        )
        client.table.query.return_value = {"Items": [item]}

        steps = client.get_execution_steps("u1", "e1")

        assert len(steps) == 1
        step = steps[0]
        assert step.network_url_pattern == "**/api/users"
        assert step.network_method == "POST"
        assert step.network_request_body == '{"name": "John"}'
        assert step.network_body_match_type == "subset"
        assert step.network_mock_response == '{"status": 201}'
        assert step.network_mock_passthrough is True
        assert step.network_timeout == 30

    def test_loads_defaults_when_fields_absent(self, client):
        item = self._item(step_type="navigation")  # pre-existing step shape
        client.table.query.return_value = {"Items": [item]}

        steps = client.get_execution_steps("u1", "e1")

        assert len(steps) == 1
        step = steps[0]
        assert step.network_url_pattern is None
        assert step.network_method is None
        assert step.network_request_body is None
        assert step.network_body_match_type is None
        assert step.network_mock_response is None
        assert step.network_mock_passthrough is False
        assert step.network_timeout is None

    def test_network_timeout_as_decimal_is_coerced_to_int(self, client):
        # DynamoDB numeric attributes come back as `decimal.Decimal` via boto3.
        from decimal import Decimal

        item = self._item(network_timeout=Decimal("45"))
        client.table.query.return_value = {"Items": [item]}

        steps = client.get_execution_steps("u1", "e1")

        assert steps[0].network_timeout == 45
        assert isinstance(steps[0].network_timeout, int)

    def test_network_response_status_as_decimal_is_coerced_to_int(self, client):
        # DynamoDB returns integer attributes as Decimal — cover the same
        # coercion path for network_response_status.
        from decimal import Decimal

        item = self._item(network_response_status=Decimal("201"))
        client.table.query.return_value = {"Items": [item]}

        steps = client.get_execution_steps("u1", "e1")

        assert steps[0].network_response_status == 201
        assert isinstance(steps[0].network_response_status, int)
