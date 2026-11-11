"""``POST /import`` expands ``step_type: "template"`` placeholders server-side.

A placeholder is exactly ``{sort, step_type: "template", template_id}``; it
is replaced by the template's steps (with template linkage) at that slot.
Every referenced template is loaded *before* anything is written.
"""
import json
import os
from decimal import Decimal
from unittest.mock import patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

import import_usecase  # noqa: E402
from authz_test_support import APP_ID, resource_access_granted  # noqa: E402
from fake_table import FakeTable  # noqa: E402


@pytest.fixture(autouse=True)
def _access_granted():
    """Handler-logic tests: ownership is covered by the *_access tests."""
    with resource_access_granted():
        yield


LOGIN_ID = "3f1c0000-0000-4000-8000-000000000001"
SETUP_ID = "3f1c0000-0000-4000-8000-000000000002"
MISSING_ID = "3f1c0000-0000-4000-8000-00000000dead"

LOGIN = {"pk": "TEMPLATES", "sk": f"TEMPLATE#{LOGIN_ID}", "id": LOGIN_ID, "name": "Login", "version": Decimal(4)}
LOGIN_STEPS = [
    {"pk": f"TEMPLATE#{LOGIN_ID}", "sk": "STEP#ls1", "id": "ls1", "sort": Decimal(1), "step_type": "browser",
     "instruction": "Open login", "browser_action": "navigate", "browser_args": '{"url": "https://e.test"}'},
    {"pk": f"TEMPLATE#{LOGIN_ID}", "sk": "STEP#ls2", "id": "ls2", "sort": Decimal(2), "step_type": "secret",
     "instruction": "Click into the username field.", "secret_key": "shop_username"},
    {"pk": f"TEMPLATE#{LOGIN_ID}", "sk": "STEP#ls3", "id": "ls3", "sort": Decimal(3), "step_type": "secret",
     "instruction": "Click into the password field.", "secret_key": "shop_password"},
]
LOGIN_VARS = {"pk": f"TEMPLATE#{LOGIN_ID}", "sk": "VARIABLES",
              "variables": [{"key": "base", "value": "https://e.test"}, {"key": "lang", "value": "en"}]}
SETUP = {"pk": "TEMPLATES", "sk": f"TEMPLATE#{SETUP_ID}", "id": SETUP_ID, "name": "Setup", "version": Decimal(1)}
SETUP_STEPS = [
    {"pk": f"TEMPLATE#{SETUP_ID}", "sk": "STEP#ss1", "id": "ss1", "sort": Decimal(1), "step_type": "navigation",
     "instruction": "Dismiss the cookie banner."},
]

SCOPES = "api/usecases.write api/templates.read"


def _payload(steps, **extra):
    body = {
        "exportVersion": "1.0", "exportedAt": "2025-01-01T00:00:00Z",
        "application_id": APP_ID,  # target app, required by the app_from_body resolver
        "usecase": {"name": "Checkout", "starting_url": "https://e.test"},
        "steps": steps,
    }
    body.update(extra)
    return body


def _placeholder(sort, template_id=LOGIN_ID, **extra):
    step = {"sort": sort, "step_type": "template", "template_id": template_id}
    step.update(extra)
    return step


def _step(sort, instruction="Click 'Add to cart'.", step_type="navigation", **extra):
    return {"sort": sort, "instruction": instruction, "step_type": step_type, **extra}


def _run(table, body, scope=SCOPES):
    event = {"body": json.dumps(body),
             "requestContext": {"authorizer": {"sub": "u1", "email": "qa@example.com", "scope": scope}}}
    with patch.object(import_usecase, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        return import_usecase.handler(event, None)


def _table():
    return FakeTable([LOGIN, *LOGIN_STEPS, LOGIN_VARS, SETUP, *SETUP_STEPS])


def _steps_of(table, usecase_id):
    return sorted(table.by_prefix(f"USECASE#{usecase_id}", "STEP#"), key=lambda s: int(s["sort"]))


class TestExpansion:
    def test_placeholder_at_slot_one_expands_in_file_order(self):
        table = _table()
        response = _run(table, _payload([_placeholder(1), _step(2), _step(3, "Return the badge.", "validation")]))
        assert response["statusCode"] == 200, response["body"]
        body = json.loads(response["body"])
        steps = _steps_of(table, body["usecaseId"])
        assert [s["sort"] for s in steps] == [1, 2, 3, 4, 5]
        assert [s["instruction"] for s in steps] == [
            "Open login", "Click into the username field.", "Click into the password field.",
            "Click 'Add to cart'.", "Return the badge.",
        ]
        for linked in steps[:3]:
            assert linked["template_id"] == LOGIN_ID
            assert linked["template_version"] == 4
            assert linked["template_step_id"].startswith("ls")
        for own in steps[3:]:
            assert "template_id" not in own
        assert steps[0]["browser_action"] == "navigate"
        assert body["templatesApplied"] == [{"templateId": LOGIN_ID, "version": 4, "stepsCreated": 3}]

    def test_placeholder_in_middle_and_end(self):
        table = _table()
        response = _run(table, _payload([_step(1, "Start"), _placeholder(2, SETUP_ID), _step(3, "Middle"),
                                         _placeholder(4)]))
        body = json.loads(response["body"])
        steps = _steps_of(table, body["usecaseId"])
        assert [s["instruction"] for s in steps] == [
            "Start", "Dismiss the cookie banner.", "Middle",
            "Open login", "Click into the username field.", "Click into the password field.",
        ]
        assert body["templatesApplied"] == [
            {"templateId": SETUP_ID, "version": 1, "stepsCreated": 1},
            {"templateId": LOGIN_ID, "version": 4, "stepsCreated": 3},
        ]

    def test_same_template_twice_gets_independent_step_ids(self):
        table = _table()
        response = _run(table, _payload([_placeholder(1, SETUP_ID), _step(2), _placeholder(3, SETUP_ID)]))
        body = json.loads(response["body"])
        steps = _steps_of(table, body["usecaseId"])
        linked = [s for s in steps if s.get("template_id") == SETUP_ID]
        assert len(linked) == 2
        assert linked[0]["id"] != linked[1]["id"]
        assert [s["sort"] for s in linked] == [1, 3]
        assert len(body["templatesApplied"]) == 2
        # one USAGE record per distinct template, not per placeholder
        usages = table.by_prefix(f"TEMPLATE#{SETUP_ID}", "USAGE#")
        assert len(usages) == 1
        assert usages[0] == {"pk": f"TEMPLATE#{SETUP_ID}", "sk": f"USAGE#{body['usecaseId']}",
                             "template_id": SETUP_ID, "usecase_id": body["usecaseId"],
                             "created_at": usages[0]["created_at"]}

    def test_usage_record_per_template(self):
        table = _table()
        response = _run(table, _payload([_placeholder(1, SETUP_ID), _placeholder(2)]))
        usecase_id = json.loads(response["body"])["usecaseId"]
        assert [u["sk"] for u in table.by_prefix(f"TEMPLATE#{SETUP_ID}", "USAGE#")] == [f"USAGE#{usecase_id}"]
        assert [u["sk"] for u in table.by_prefix(f"TEMPLATE#{LOGIN_ID}", "USAGE#")] == [f"USAGE#{usecase_id}"]

    def test_no_placeholders_no_usage_record(self):
        table = _table()
        _run(table, _payload([_step(1)]))
        assert not [i for i in table.put_calls if i["sk"].startswith("USAGE#")]

    def test_placeholder_before_repeat_keeps_parent_links(self):
        table = _table()
        repeat = _step(2, "For each user", "repeat", repeat_columns=["email"], repeat_rows=[["a"], ["b"]],
                       steps=[_step(1, "Type {{email}}")])
        response = _run(table, _payload([_placeholder(1, SETUP_ID), repeat, _step(3, "Done")]))
        assert response["statusCode"] == 200, response["body"]
        steps = _steps_of(table, json.loads(response["body"])["usecaseId"])
        assert [s["instruction"] for s in steps] == ["Dismiss the cookie banner.", "For each user", "Type {{email}}", "Done"]
        assert steps[2]["parent_step_id"] == steps[1]["id"]


class TestSecretsAndVariables:
    def test_template_secret_keys_join_missing_secrets_deduped(self):
        table = _table()
        response = _run(table, _payload(
            [_placeholder(1), _step(2, "Click into the password field.", "secret", secret_key="shop_password")],
            secrets=[{"key": "shop_password", "description": "Shop password"}],
        ))
        body = json.loads(response["body"])
        assert body["missingSecrets"] == ["shop_password", "shop_username"]
        records = sorted(table.by_prefix(f"USECASE#{body['usecaseId']}", "SECRET#"), key=lambda r: r["key"])
        assert [(r["key"], r["description"]) for r in records] == [("shop_password", "Shop password"), ("shop_username", "")]

    def test_variables_merge_file_wins(self):
        table = _table()
        response = _run(table, _payload([_placeholder(1)], variables=[{"key": "base", "value": "https://prod"}]))
        body = json.loads(response["body"])
        record = table.get(f"USECASE#{body['usecaseId']}", "USECASE_VARIABLES")
        assert record["variables"] == [{"key": "base", "value": "https://prod"}, {"key": "lang", "value": "en"}]

    def test_template_variables_without_file_variables(self):
        table = _table()
        response = _run(table, _payload([_placeholder(1)]))
        body = json.loads(response["body"])
        assert table.get(f"USECASE#{body['usecaseId']}", "USECASE_VARIABLES")["variables"] == LOGIN_VARS["variables"]


class TestValidation:
    def test_missing_template_is_400_and_writes_nothing(self):
        table = _table()
        response = _run(table, _payload([_placeholder(1, MISSING_ID), _placeholder(2), _step(3)]))
        assert response["statusCode"] == 400, response["body"]
        body = json.loads(response["body"])
        assert body["error"] == "Template not found"
        assert body["templateIds"] == [MISSING_ID]
        assert table.put_calls == []

    def test_placeholders_require_templates_read_scope(self):
        table = _table()
        response = _run(table, _payload([_placeholder(1)]), scope="api/usecases.write")
        assert response["statusCode"] == 403
        assert "api/templates.read" in json.loads(response["body"])["message"]
        assert table.put_calls == []

    def test_no_placeholders_needs_only_usecases_write(self):
        table = _table()
        response = _run(table, _payload([_step(1)]), scope="api/usecases.write")
        assert response["statusCode"] == 200, response["body"]
        assert "templatesApplied" not in json.loads(response["body"])

    @pytest.mark.parametrize("placeholder", [
        _placeholder(1, instruction="Log in"),
        _placeholder(1, secret_key="x"),
        {"sort": 1, "step_type": "template"},
        _placeholder(1, "not-a-uuid"),
        _placeholder(1, ""),
    ], ids=["extra-instruction", "extra-secret_key", "missing-template_id", "bad-uuid", "empty-id"])
    def test_malformed_placeholder_is_400(self, placeholder):
        table = _table()
        response = _run(table, _payload([placeholder, _step(2)]))
        assert response["statusCode"] == 400, response["body"]
        assert "template" in json.loads(response["body"])["message"]
        assert table.put_calls == []

    def test_placeholder_inside_repeat_is_400(self):
        table = _table()
        repeat = _step(1, "Loop", "repeat", repeat_columns=["a"], repeat_rows=[["1"]], steps=[_placeholder(1)])
        response = _run(table, _payload([repeat]))
        assert response["statusCode"] == 400, response["body"]
        assert table.put_calls == []

    def test_files_without_placeholders_do_not_read_the_table(self):
        """``import_usecase`` stays write-only for plain files (no template → no read)."""
        class WriteOnly(FakeTable):
            def get_item(self, *a, **k):
                raise AssertionError("unexpected read")

            def query(self, *a, **k):
                raise AssertionError("unexpected read")

        response = _run(WriteOnly(), _payload([_step(1)]))
        assert response["statusCode"] == 200, response["body"]
