"""Tests verifying network_assertion fields propagate through Lambda endpoints.

The emphasis is on the *propagation* — each endpoint's copy block must
include the new network_* fields.  A static check across all 13 target
files guards against future drift where someone adds a field and forgets
an endpoint.  A focused behavioural test covers the two highest-traffic
endpoints (create_step, import_usecase).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("TABLE_NAME", "test-table")

_ENDPOINTS_DIR = Path(__file__).resolve().parent

NETWORK_FIELDS = (
    "network_url_pattern",
    "network_method",
    "network_request_body",
    "network_body_match_type",
    "network_mock_response",
    "network_mock_passthrough",
    "network_timeout",
    "network_response_body",
    "network_response_body_match_type",
    "network_response_status",
)

# Endpoints that must propagate network_* fields onto the persisted step record.
PROPAGATION_ENDPOINTS = [
    "create_step.py",
    "update_step.py",
    "execute_usecase.py",
    "execute_test_suite.py",
    "export_usecase.py",
    "import_usecase.py",
    "clone_usecase.py",
    "apply_template.py",
    "import_template.py",
    "create_template_step.py",
    "update_template_step.py",
    "update_step_from_template.py",
    "add_wizard_step.py",
    "accept_wizard_step.py",
]


class TestStaticFieldPropagation:
    """Every propagation endpoint must mention every network_* field."""

    def test_every_endpoint_mentions_every_field(self):
        missing = []
        for endpoint in PROPAGATION_ENDPOINTS:
            path = _ENDPOINTS_DIR / endpoint
            source = path.read_text()
            for field in NETWORK_FIELDS:
                if field not in source:
                    missing.append(f"{endpoint} missing {field}")
        assert not missing, (
            "These endpoints do not propagate network_assertion fields:\n"
            + "\n".join(missing)
        )


class TestCreateStepPropagation:
    """POST /steps — the record persisted to DynamoDB must include all
    network_* fields when the client sent them."""

    def _event(self, body: dict) -> dict:
        return {
            "body": json.dumps(body),
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "user-1",
                        "cognito:groups": '["api/usecases.write"]',
                    }
                }
            },
        }

    def test_network_fields_persisted(self):
        import create_step

        captured_items = []

        class _FakeTable:
            def put_item(self, **kwargs):
                captured_items.append(kwargs["Item"])

        class _FakeDynamo:
            def Table(self, _name):
                return _FakeTable()

        body = {
            "usecaseId": "uc-1",
            "sort": 1,
            "instruction": "Click submit",
            "step_type": "network_assertion",
            "network_url_pattern": "**/api/users",
            "network_method": "POST",
            "network_request_body": '{"name": "John"}',
            "network_body_match_type": "subset",
            "network_mock_response": '{"status": 201}',
            "network_mock_passthrough": True,
            "network_timeout": 30,
        }

        with patch("create_step.boto3") as boto_mock, \
             patch("create_step.require_scopes", return_value=({"sub": "u1"}, None)):
            boto_mock.resource.return_value = _FakeDynamo()
            response = create_step.handler(self._event(body), None)

        assert response["statusCode"] == 201
        assert len(captured_items) == 1
        item = captured_items[0]
        assert item["step_type"] == "network_assertion"
        assert item["network_url_pattern"] == "**/api/users"
        assert item["network_method"] == "POST"
        assert item["network_request_body"] == '{"name": "John"}'
        assert item["network_body_match_type"] == "subset"
        assert item["network_mock_response"] == '{"status": 201}'
        assert item["network_mock_passthrough"] is True
        assert item["network_timeout"] == 30

    def test_non_network_step_unaffected(self):
        """A regular navigation step must not gain network_* attributes."""
        import create_step

        captured_items = []

        class _FakeTable:
            def put_item(self, **kwargs):
                captured_items.append(kwargs["Item"])

        class _FakeDynamo:
            def Table(self, _name):
                return _FakeTable()

        body = {
            "usecaseId": "uc-1",
            "sort": 1,
            "instruction": "Click login",
            "step_type": "navigation",
        }

        with patch("create_step.boto3") as boto_mock, \
             patch("create_step.require_scopes", return_value=({"sub": "u1"}, None)):
            boto_mock.resource.return_value = _FakeDynamo()
            response = create_step.handler(self._event(body), None)

        assert response["statusCode"] == 201
        item = captured_items[0]
        for field in NETWORK_FIELDS:
            assert field not in item, f"{field} should not be set on non-network step"


class TestImportUsecasePropagation:
    """Importing a use case with a network_assertion step must preserve all fields."""

    def test_round_trip_fields_preserved(self):
        import import_usecase

        captured_items = []

        class _FakeTable:
            def put_item(self, **kwargs):
                captured_items.append(kwargs["Item"])

        imported_steps = [
            {
                "sort": 1,
                "instruction": "Click submit",
                "step_type": "network_assertion",
                "network_url_pattern": "**/api/users",
                "network_method": "POST",
                "network_request_body": '{"name":"John"}',
                "network_body_match_type": "subset",
                "network_mock_response": '{"status":201}',
                "network_mock_passthrough": True,
                "network_timeout": 20,
            }
        ]

        usecase_body = {
            "exportVersion": "1.0",
            "usecase": {
                "name": "Create user",
                "description": "Test create flow",
                "starting_url": "https://example.test/",
                "tags": [],
            },
            "steps": imported_steps,
        }

        event = {
            "body": json.dumps(usecase_body),
            "requestContext": {
                "authorizer": {"claims": {"cognito:groups": '["api/usecases.write"]'}}
            },
        }

        def _fake_resource(_service):
            m = MagicMock()
            m.Table.return_value = _FakeTable()
            return m

        with patch("import_usecase.boto3") as boto_mock, \
             patch("import_usecase.require_scopes", return_value=({"sub": "u1"}, None)):
            boto_mock.resource.side_effect = _fake_resource
            response = import_usecase.handler(event, None)

        # Accept 200/201 — we only care that the persisted step has the fields.
        assert response["statusCode"] in (200, 201)
        step_items = [
            i for i in captured_items if i.get("sk", "").startswith("STEP#")
        ]
        assert step_items, "no STEP# item was persisted"
        item = step_items[0]
        assert item["step_type"] == "network_assertion"
        assert item["network_url_pattern"] == "**/api/users"
        assert item["network_method"] == "POST"
        assert item["network_body_match_type"] == "subset"
        assert item["network_mock_passthrough"] is True
        assert item["network_timeout"] == 20


class TestExportImportRoundTrip:
    """End-to-end: a use case in DynamoDB is exported via export_usecase,
    then the exported JSON is fed to import_usecase, and we assert every
    network_* field survives the round-trip exactly.

    This is the strongest guarantee of propagation correctness — each
    endpoint individually is covered by TestStaticFieldPropagation, but
    only a full round-trip catches subtle serialization / type coercion
    bugs at the boundaries.
    """

    def _dynamodb_step_item(self) -> dict:
        """A realistic DynamoDB row for a network_assertion step populated
        with every field under test."""
        return {
            "pk": "USECASE#uc-1",
            "sk": "STEP#step-1",
            "id": "step-1",
            "sort": 1,
            "instruction": "Click submit",
            "step_type": "network_assertion",
            "network_url_pattern": "**/api/users",
            "network_method": "POST",
            "network_request_body": '{"name": "John"}',
            "network_body_match_type": "subset",
            "network_mock_response": '{"status": 201}',
            "network_mock_passthrough": True,
            "network_timeout": 30,
            "network_response_body": '{"type":"object","required":["id"]}',
            "network_response_body_match_type": "schema",
            "network_response_status": 201,
        }

    def _dynamodb_usecase_item(self) -> dict:
        return {
            "pk": "USECASES",
            "sk": "USECASE#uc-1",
            "name": "Create user",
            "description": "Test create flow",
            "starting_url": "https://example.test/",
            "executing_region": "us-east-1",
            "active": True,
            "tags": [],
        }

    def _export(self, step_item: dict, usecase_item: dict) -> dict:
        """Run export_usecase.handler against a mocked DynamoDB and return
        the parsed JSON body."""
        import export_usecase

        table_mock = MagicMock()

        def _get_item(Key):  # noqa: N803 — AWS kwarg name
            if Key == {"pk": "USECASES", "sk": "USECASE#uc-1"}:
                return {"Item": usecase_item}
            # variables + hooks + anything else → empty response
            return {}

        table_mock.get_item.side_effect = _get_item
        table_mock.query.return_value = {"Items": [step_item]}

        dynamodb_mock = MagicMock()
        dynamodb_mock.Table.return_value = table_mock

        # secretsmanager call should return no secrets.
        secrets_mock = MagicMock()
        secrets_mock.list_secrets.return_value = {"SecretList": []}

        def _client(service):
            if service == "secretsmanager":
                return secrets_mock
            return MagicMock()

        event = {
            "pathParameters": {"id": "uc-1"},
            "requestContext": {
                "authorizer": {
                    "claims": {"cognito:groups": '["api/usecases.read"]', "sub": "u1"}
                }
            },
        }

        with patch("export_usecase.boto3") as boto_mock, \
             patch("export_usecase.require_scopes", return_value=({"sub": "u1"}, None)):
            boto_mock.resource.return_value = dynamodb_mock
            boto_mock.client.side_effect = _client
            response = export_usecase.handler(event, None)

        assert response["statusCode"] == 200
        return json.loads(response["body"])

    def _import(self, export_body: dict) -> dict:
        """Run import_usecase.handler against a mocked DynamoDB and return
        the first persisted STEP# item."""
        import import_usecase

        captured_items: list[dict] = []

        class _FakeTable:
            def put_item(self, **kwargs):
                captured_items.append(kwargs["Item"])

        def _fake_resource(_service):
            m = MagicMock()
            m.Table.return_value = _FakeTable()
            return m

        event = {
            "body": json.dumps(export_body),
            "requestContext": {
                "authorizer": {
                    "claims": {"cognito:groups": '["api/usecases.write"]'}
                }
            },
        }

        with patch("import_usecase.boto3") as boto_mock, \
             patch("import_usecase.require_scopes", return_value=({"sub": "u1"}, None)):
            boto_mock.resource.side_effect = _fake_resource
            response = import_usecase.handler(event, None)

        assert response["statusCode"] in (200, 201), response.get("body")
        step_items = [
            i for i in captured_items if i.get("sk", "").startswith("STEP#")
        ]
        assert step_items, "no STEP# item was persisted after import"
        return step_items[0]

    def test_round_trip_preserves_all_network_fields(self):
        source = self._dynamodb_step_item()
        usecase = self._dynamodb_usecase_item()

        export_body = self._export(source, usecase)

        # The export JSON should contain our step with every network_* field.
        exported_steps = export_body.get("steps", [])
        assert len(exported_steps) == 1
        exported_step = exported_steps[0]
        for field in NETWORK_FIELDS:
            assert field in exported_step, (
                f"export dropped {field}; got keys: {sorted(exported_step.keys())}"
            )

        # Feed the export back through import.
        imported_item = self._import(export_body)

        # Every network_* field should survive unchanged.
        for field in NETWORK_FIELDS:
            assert imported_item.get(field) == source[field], (
                f"field {field} diverged in round-trip: "
                f"source={source[field]!r}, imported={imported_item.get(field)!r}"
            )

    def test_round_trip_minimal_step_has_no_network_fields(self):
        """A non-network step should not acquire network_* fields through
        the round-trip."""
        source = {
            "pk": "USECASE#uc-1",
            "sk": "STEP#step-1",
            "id": "step-1",
            "sort": 1,
            "instruction": "Navigate to login",
            "step_type": "navigation",
        }
        usecase = self._dynamodb_usecase_item()

        export_body = self._export(source, usecase)
        imported_item = self._import(export_body)

        for field in NETWORK_FIELDS:
            assert field not in imported_item, (
                f"{field} leaked into a non-network step through the round-trip"
            )
