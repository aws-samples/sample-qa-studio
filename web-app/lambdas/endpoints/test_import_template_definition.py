"""``POST /templates/import`` — create a whole template (metadata, steps, variables) from a template file."""
import json
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

import import_template_definition  # noqa: E402
from fake_table import FakeTable  # noqa: E402
from repeat_validation import REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR  # noqa: E402
from template_expansion import NESTED_TEMPLATE_ERROR  # noqa: E402

STEPS = [
    {"sort": 1, "step_type": "browser", "instruction": "Open login",
     "browser_action": "navigate", "browser_args": '{"url": "https://e.test"}'},
    {"sort": 2, "step_type": "secret", "instruction": "Click into the username field.", "secret_key": "shop_username"},
    {"sort": 3, "step_type": "network_assertion", "instruction": "Wait for the session call.",
     "network_url_pattern": "*/session", "network_mock_passthrough": False, "network_timeout": 0},
]


def _body(**overrides):
    body = {
        "templateVersion": "1.0",
        "template": {"name": "Login – Shop", "description": "Logs in", "category": "auth", "tags": ["shop"]},
        "steps": STEPS,
        "variables": [{"key": "base", "value": "https://e.test"}],
    }
    body.update(overrides)
    return body


def _run(table, body, scope="api/templates.write", raw_body=None):
    event = {"body": raw_body if raw_body is not None else json.dumps(body),
             "requestContext": {"authorizer": {"sub": "u1", "email": "qa@example.com", "scope": scope}}}
    with patch.object(import_template_definition, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        return import_template_definition.handler(event, None)


class TestHappyPath:
    def test_creates_metadata_steps_and_variables(self):
        table = FakeTable()
        response = _run(table, _body())
        assert response["statusCode"] == 201, response["body"]
        body = json.loads(response["body"])
        assert body["name"] == "Login – Shop"
        assert body["stepsCreated"] == 3
        template_id = body["id"]

        metadata = table.get("TEMPLATES", f"TEMPLATE#{template_id}")
        assert metadata["id"] == template_id
        assert metadata["name"] == "Login – Shop"
        assert metadata["description"] == "Logs in"
        assert metadata["category"] == "auth"
        assert metadata["tags"] == ["shop"]
        assert metadata["version"] == 1
        assert metadata["created_by"] == "qa@example.com"
        assert metadata["created_at"] == metadata["updated_at"]

        steps = sorted(table.by_prefix(f"TEMPLATE#{template_id}", "STEP#"), key=lambda s: s["sort"])
        assert [s["sort"] for s in steps] == [1, 2, 3]
        assert [s["instruction"] for s in steps] == [STEPS[0]["instruction"], STEPS[1]["instruction"], STEPS[2]["instruction"]]
        assert steps[0]["browser_action"] == "navigate"
        assert steps[1]["secret_key"] == "shop_username"
        assert steps[2]["network_mock_passthrough"] is False
        assert steps[2]["network_timeout"] == 0
        for step in steps:
            assert step["sk"] == f"STEP#{step['id']}"
            assert step["created_at"]

        variables = table.get(f"TEMPLATE#{template_id}", "VARIABLES")
        assert variables["variables"] == [{"key": "base", "value": "https://e.test"}]

    def test_sort_is_renumbered_from_file_order(self):
        table = FakeTable()
        steps = [{"sort": 10, "step_type": "navigation", "instruction": "b"},
                 {"sort": 20, "step_type": "navigation", "instruction": "c"}]
        response = _run(table, _body(steps=steps))
        template_id = json.loads(response["body"])["id"]
        written = sorted(table.by_prefix(f"TEMPLATE#{template_id}", "STEP#"), key=lambda s: s["sort"])
        assert [(s["sort"], s["instruction"]) for s in written] == [(1, "b"), (2, "c")]

    def test_defaults_and_no_variables_record(self):
        table = FakeTable()
        response = _run(table, {"templateVersion": "1.0", "template": {"name": "Minimal"}, "steps": STEPS[:1]})
        assert response["statusCode"] == 201, response["body"]
        template_id = json.loads(response["body"])["id"]
        metadata = table.get("TEMPLATES", f"TEMPLATE#{template_id}")
        assert (metadata["description"], metadata["category"], metadata["tags"]) == ("", "", [])
        assert table.get(f"TEMPLATE#{template_id}", "VARIABLES") is None

    def test_uses_batch_writer(self):
        assert "batch_writer" in open(import_template_definition.__file__).read()

    def test_step_ids_in_file_are_ignored(self):
        """``id`` belongs to ``PUT /templates/{id}``; a new template gets fresh step ids."""
        table = FakeTable()
        steps = [{**STEPS[0], "id": "ts-from-file"}, {**STEPS[1], "id": "ts-other"}]
        response = _run(table, _body(steps=steps))
        assert response["statusCode"] == 201, response["body"]
        template_id = json.loads(response["body"])["id"]
        written = table.by_prefix(f"TEMPLATE#{template_id}", "STEP#")
        assert len(written) == 2
        assert all(s["id"] not in ("ts-from-file", "ts-other") for s in written)
        assert all(s["sk"] == f"STEP#{s['id']}" for s in written)

    def test_duplicate_step_ids_are_400(self):
        table = FakeTable()
        steps = [{**STEPS[0], "id": "dup"}, {**STEPS[1], "id": "dup"}]
        response = _run(table, _body(steps=steps))
        assert response["statusCode"] == 400
        assert "duplicate step id dup" in json.loads(response["body"])["message"]
        assert table.put_calls == []


class TestValidation:
    def test_nested_template_step_rejected(self):
        table = FakeTable()
        steps = STEPS[:1] + [{"sort": 2, "step_type": "template", "template_id": "3f1c0000-0000-4000-8000-000000000001"}]
        response = _run(table, _body(steps=steps))
        assert response["statusCode"] == 400
        assert json.loads(response["body"])["error"] == NESTED_TEMPLATE_ERROR
        assert table.put_calls == []

    def test_repeat_step_rejected(self):
        table = FakeTable()
        steps = [{"sort": 1, "step_type": "repeat", "instruction": "Loop", "repeat_columns": ["a"], "repeat_rows": [["1"]]}]
        response = _run(table, _body(steps=steps))
        assert response["statusCode"] == 400
        assert json.loads(response["body"])["error"] == REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR
        assert table.put_calls == []

    @pytest.mark.parametrize("body,fragment", [
        (_body(templateVersion="2.0"), "templateVersion"),
        (_body(template={"name": ""}), "name"),
        (_body(template={}), "name"),
        (_body(steps=[]), "steps"),
        (_body(steps=[{"sort": 1, "step_type": "navigation", "instruction": ""}]), "instruction"),
        (_body(steps=[{"sort": 1, "instruction": "x"}]), "step_type"),
        (_body(variables=[{"key": "", "value": "x"}]), "key"),
    ], ids=["version", "empty-name", "missing-name", "no-steps", "empty-instruction", "missing-step_type",
            "variable-key"])
    def test_schema_errors_are_400(self, body, fragment):
        table = FakeTable()
        response = _run(table, body)
        assert response["statusCode"] == 400, response["body"]
        assert fragment in json.loads(response["body"])["message"]
        assert table.put_calls == []

    def test_invalid_json(self):
        response = _run(FakeTable(), None, raw_body="{not json")
        assert response["statusCode"] == 400

    def test_missing_scope_is_403(self):
        table = FakeTable()
        response = _run(table, _body(), scope="api/templates.read")
        assert response["statusCode"] == 403
        assert table.put_calls == []
