"""``PUT /templates/{id}`` — atomic replace of metadata, steps (matched by ``id``) and variables.

One ``transact_write_items`` with exactly one version bump.  Matched steps
keep their ``id`` (so linked use-case steps keep a valid
``template_step_id``) and ``created_at``; steps without ``id`` are created;
existing steps absent from the file are deleted.
"""
import json
import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

import replace_template_definition  # noqa: E402
from fake_table import FakeTable  # noqa: E402
from repeat_validation import REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR  # noqa: E402
from template_expansion import NESTED_TEMPLATE_ERROR  # noqa: E402

TEMPLATE = {"pk": "TEMPLATES", "sk": "TEMPLATE#t1", "id": "t1", "name": "Login", "description": "old",
            "category": "auth", "tags": ["shop"], "version": Decimal(3), "created_at": "t0", "updated_at": "t0"}
EXISTING = [
    {"pk": "TEMPLATE#t1", "sk": "STEP#ts1", "id": "ts1", "sort": Decimal(1), "created_at": "c1",
     "step_type": "browser", "instruction": "Open login", "browser_action": "navigate", "browser_args": '{"url": "x"}'},
    {"pk": "TEMPLATE#t1", "sk": "STEP#ts2", "id": "ts2", "sort": Decimal(2), "created_at": "c2",
     "step_type": "secret", "instruction": "Click into the password field.", "secret_key": "password"},
    {"pk": "TEMPLATE#t1", "sk": "STEP#ts3", "id": "ts3", "sort": Decimal(3), "created_at": "c3",
     "step_type": "navigation", "instruction": "Submit"},
]
VARIABLES = {"pk": "TEMPLATE#t1", "sk": "VARIABLES", "variables": [{"key": "base", "value": "x"}], "created_at": "t0"}


def _body(steps, variables=None, **template):
    return {
        "templateVersion": "1.0",
        "template": {"name": "Login v2", "description": "new", "category": "auth", "tags": ["shop", "new"], **template},
        "steps": steps,
        "variables": variables if variables is not None else [{"key": "base", "value": "y"}],
    }


def _run(table, body, template_id="t1", scope="api/templates.write", raw_body=None):
    event = {"body": raw_body if raw_body is not None else json.dumps(body),
             "pathParameters": {"id": template_id},
             "requestContext": {"authorizer": {"sub": "u1", "email": "qa@example.com", "scope": scope}}}
    client = MagicMock()
    with patch.object(replace_template_definition, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        boto_mock.client.return_value = client
        response = replace_template_definition.handler(event, None)
    return response, client


def _items(client):
    return client.transact_write_items.call_args.kwargs["TransactItems"]


def _by_kind(items):
    out = {"Put": [], "Delete": [], "Update": []}
    for item in items:
        (kind, payload), = item.items()
        out[kind].append(payload)
    return out


def _s(value):
    return {"S": value}


class TestReplace:
    MIXED = [
        # ts2 moves to the front, keeps its id; secret_key removed from the file → disappears
        {"id": "ts2", "sort": 1, "step_type": "navigation", "instruction": "Click into the password field."},
        {"id": "ts1", "sort": 2, "step_type": "browser", "instruction": "Open login (edited)", "browser_action": "navigate"},
        {"sort": 3, "step_type": "navigation", "instruction": "Brand new"},
        # ts3 is absent → deleted
    ]

    def test_transaction_items(self):
        table = FakeTable([TEMPLATE, *EXISTING, VARIABLES])
        response, client = _run(table, _body(self.MIXED))
        assert response["statusCode"] == 200, response["body"]
        items = _by_kind(_items(client))
        assert len(_items(client)) == 3 + 1 + 1 + 1  # 3 step puts, 1 delete, 1 metadata update, 1 variables put
        for payload in _items(client)[0].values():
            assert payload["TableName"] == "test-table"

        puts = {p["Item"]["sk"]["S"]: p["Item"] for p in items["Put"]}
        ts2 = puts["STEP#ts2"]
        assert ts2["id"] == _s("ts2") and ts2["sort"] == {"N": "1"} and ts2["created_at"] == _s("c2")
        assert ts2["step_type"] == _s("navigation") and "secret_key" not in ts2
        ts1 = puts["STEP#ts1"]
        assert ts1["sort"] == {"N": "2"} and ts1["instruction"] == _s("Open login (edited)")
        assert ts1["browser_action"] == _s("navigate") and "browser_args" not in ts1 and ts1["created_at"] == _s("c1")
        new = [p for sk, p in puts.items() if sk.startswith("STEP#") and sk not in ("STEP#ts1", "STEP#ts2")]
        assert len(new) == 1 and new[0]["sort"] == {"N": "3"} and new[0]["created_at"]["S"] not in ("c1", "c2", "c3")
        assert new[0]["sk"] == _s(f"STEP#{new[0]['id']['S']}")
        assert puts["VARIABLES"]["variables"] == {"L": [{"M": {"key": _s("base"), "value": _s("y")}}]}

        assert items["Delete"] == [{"TableName": "test-table", "Key": {"pk": _s("TEMPLATE#t1"), "sk": _s("STEP#ts3")}}]

    def test_single_metadata_update_with_version_bump(self):
        table = FakeTable([TEMPLATE, *EXISTING])
        _, client = _run(table, _body(self.MIXED))
        updates = _by_kind(_items(client))["Update"]
        assert len(updates) == 1
        update = updates[0]
        assert update["Key"] == {"pk": _s("TEMPLATES"), "sk": _s("TEMPLATE#t1")}
        assert update["ConditionExpression"] == "attribute_exists(pk)"
        assert update["UpdateExpression"].count("ADD") == 1 and "#version :one" in update["UpdateExpression"]
        assert update["ExpressionAttributeNames"] == {"#name": "name", "#desc": "description", "#version": "version"}
        values = update["ExpressionAttributeValues"]
        assert values[":name"] == _s("Login v2") and values[":desc"] == _s("new")
        assert values[":category"] == _s("auth") and values[":tags"] == {"L": [_s("shop"), _s("new")]}
        assert values[":one"] == {"N": "1"} and values[":updated_at"]["S"]
        # the version is bumped exactly once across the whole transaction
        assert sum("#version" in (i.get("Update") or {}).get("UpdateExpression", "") for i in _items(client)) == 1

    def test_response_counts_and_version(self):
        table = FakeTable([TEMPLATE, *EXISTING])
        response, _ = _run(table, _body(self.MIXED))
        assert json.loads(response["body"]) == {
            "id": "t1", "name": "Login v2", "version": 4, "stepsCreated": 1, "stepsUpdated": 2, "stepsDeleted": 1,
        }

    def test_empty_variables_deletes_record(self):
        table = FakeTable([TEMPLATE, *EXISTING, VARIABLES])
        _, client = _run(table, _body([{"id": "ts1", "sort": 1, "step_type": "navigation", "instruction": "x"}], variables=[]))
        items = _by_kind(_items(client))
        assert {"TableName": "test-table", "Key": {"pk": _s("TEMPLATE#t1"), "sk": _s("VARIABLES")}} in items["Delete"]
        assert not [p for p in items["Put"] if p["Item"]["sk"] == _s("VARIABLES")]

    def test_sort_is_renumbered_from_file_order(self):
        table = FakeTable([TEMPLATE, *EXISTING])
        steps = [{"id": "ts3", "sort": 50, "step_type": "navigation", "instruction": "c"},
                 {"id": "ts1", "sort": 10, "step_type": "navigation", "instruction": "a"},
                 {"id": "ts2", "sort": 20, "step_type": "navigation", "instruction": "b"}]
        _, client = _run(table, _body(steps))
        puts = {p["Item"]["sk"]["S"]: p["Item"]["sort"]["N"] for p in _by_kind(_items(client))["Put"] if p["Item"]["sk"]["S"].startswith("STEP#")}
        assert puts == {"STEP#ts1": "1", "STEP#ts2": "2", "STEP#ts3": "3"}

    def test_all_new_steps_delete_all_existing(self):
        table = FakeTable([TEMPLATE, *EXISTING])
        response, client = _run(table, _body([{"sort": 1, "step_type": "navigation", "instruction": "fresh"}]))
        items = _by_kind(_items(client))
        assert sorted(d["Key"]["sk"]["S"] for d in items["Delete"]) == ["STEP#ts1", "STEP#ts2", "STEP#ts3"]
        body = json.loads(response["body"])
        assert (body["stepsCreated"], body["stepsUpdated"], body["stepsDeleted"]) == (1, 0, 3)


class TestErrors:
    def test_unknown_step_id_is_400_and_writes_nothing(self):
        table = FakeTable([TEMPLATE, *EXISTING])
        steps = [{"id": "ts1", "sort": 1, "step_type": "navigation", "instruction": "a"},
                 {"sort": 2, "step_type": "navigation", "instruction": "b"},
                 {"id": "ghost", "sort": 3, "step_type": "navigation", "instruction": "c"}]
        response, client = _run(table, _body(steps))
        assert response["statusCode"] == 400
        assert json.loads(response["body"])["error"] == "steps[2]: id ghost does not belong to template t1"
        client.transact_write_items.assert_not_called()

    def test_duplicate_step_id_is_400(self):
        table = FakeTable([TEMPLATE, *EXISTING])
        steps = [{"id": "ts1", "sort": 1, "step_type": "navigation", "instruction": "a"},
                 {"id": "ts1", "sort": 2, "step_type": "navigation", "instruction": "b"}]
        response, client = _run(table, _body(steps))
        assert response["statusCode"] == 400
        assert "duplicate step id ts1" in json.loads(response["body"])["message"]
        client.transact_write_items.assert_not_called()

    def test_missing_template_is_404(self):
        response, client = _run(FakeTable([TEMPLATE]), _body([{"sort": 1, "step_type": "navigation", "instruction": "a"}]), "ghost")
        assert response["statusCode"] == 404
        client.transact_write_items.assert_not_called()

    def test_placeholder_is_400(self):
        steps = [{"sort": 1, "step_type": "template", "template_id": "3f1c0000-0000-4000-8000-000000000001"}]
        response, client = _run(FakeTable([TEMPLATE]), _body(steps))
        assert response["statusCode"] == 400
        assert json.loads(response["body"])["error"] == NESTED_TEMPLATE_ERROR
        client.transact_write_items.assert_not_called()

    def test_repeat_is_400(self):
        steps = [{"sort": 1, "step_type": "repeat", "instruction": "Loop", "repeat_columns": ["a"], "repeat_rows": [["1"]]}]
        response, client = _run(FakeTable([TEMPLATE]), _body(steps))
        assert response["statusCode"] == 400
        assert json.loads(response["body"])["error"] == REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR

    def test_too_many_steps_is_400(self):
        steps = [{"sort": i, "step_type": "navigation", "instruction": f"s{i}"} for i in range(1, 100)]
        response, client = _run(FakeTable([TEMPLATE]), _body(steps))
        assert response["statusCode"] == 400
        assert json.loads(response["body"])["error"] == "template too large for an atomic update (max 98 steps)"
        client.transact_write_items.assert_not_called()

    def test_ninety_eight_steps_fit(self):
        steps = [{"sort": i, "step_type": "navigation", "instruction": f"s{i}"} for i in range(1, 99)]
        response, client = _run(FakeTable([TEMPLATE]), _body(steps))
        assert response["statusCode"] == 200, response["body"]
        assert len(_items(client)) == 100

    @pytest.mark.parametrize("body,fragment", [
        ({"templateVersion": "2.0", "template": {"name": "x"}, "steps": [{"sort": 1, "step_type": "navigation", "instruction": "a"}]}, "templateVersion"),
        ({"templateVersion": "1.0", "template": {"name": ""}, "steps": [{"sort": 1, "step_type": "navigation", "instruction": "a"}]}, "name"),
        ({"templateVersion": "1.0", "template": {"name": "x"}, "steps": []}, "steps"),
    ], ids=["version", "empty-name", "no-steps"])
    def test_schema_errors_are_400(self, body, fragment):
        response, client = _run(FakeTable([TEMPLATE]), body)
        assert response["statusCode"] == 400
        assert fragment in json.loads(response["body"])["message"]
        client.transact_write_items.assert_not_called()

    def test_invalid_json(self):
        response, _ = _run(FakeTable([TEMPLATE]), None, raw_body="{nope")
        assert response["statusCode"] == 400

    def test_missing_scope_is_403(self):
        response, client = _run(FakeTable([TEMPLATE]), _body([{"sort": 1, "step_type": "navigation", "instruction": "a"}]),
                                scope="api/templates.read")
        assert response["statusCode"] == 403
        client.transact_write_items.assert_not_called()
