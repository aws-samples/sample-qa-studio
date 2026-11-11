"""``DELETE /templates/{id}`` — unlink use-case steps first, then wipe the template; ``204``.

Order matters: a Lambda that dies after the unlink leaves the template in
place, so a retry redoes the idempotent unlink.  The reverse order would
orphan linked steps with no way to find them again.
"""
import json
import os
from unittest.mock import patch

os.environ.setdefault("TABLE_NAME", "test-table")

import delete_template  # noqa: E402
from fake_table import FakeTable  # noqa: E402
from template_usage import LINKAGE_FIELDS, usage_item  # noqa: E402

TEMPLATE = {"pk": "TEMPLATES", "sk": "TEMPLATE#t1", "id": "t1", "name": "Login", "version": 3}
TEMPLATE_STEP = {"pk": "TEMPLATE#t1", "sk": "STEP#ts1", "id": "ts1", "sort": 1, "instruction": "x", "step_type": "navigation"}
TEMPLATE_VARS = {"pk": "TEMPLATE#t1", "sk": "VARIABLES", "variables": [{"key": "a", "value": "1"}]}
OTHER_TEMPLATE = {"pk": "TEMPLATES", "sk": "TEMPLATE#t2", "id": "t2", "name": "Other", "version": 1}
OTHER_STEP = {"pk": "TEMPLATE#t2", "sk": "STEP#ts9", "id": "ts9", "sort": 1, "instruction": "o", "step_type": "navigation"}


def _linked(usecase_id, step_id, template_id="t1", sort=1):
    return {"pk": f"USECASE#{usecase_id}", "sk": f"STEP#{step_id}", "id": step_id, "sort": sort, "instruction": "x",
            "step_type": "navigation", "template_id": template_id, "template_step_id": "ts1", "template_version": 3}


def _plain(usecase_id, step_id, sort=5):
    return {"pk": f"USECASE#{usecase_id}", "sk": f"STEP#{step_id}", "id": step_id, "sort": sort, "instruction": "p",
            "step_type": "navigation"}


def _run(table, template_id="t1", scope="api/templates.write"):
    event = {"requestContext": {"authorizer": {"sub": "u1", "email": "qa@example.com", "scope": scope}},
             "pathParameters": {"id": template_id}}
    with patch.object(delete_template, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        return delete_template.handler(event, None)


def _full_table():
    return FakeTable([
        TEMPLATE, TEMPLATE_STEP, TEMPLATE_VARS, OTHER_TEMPLATE, OTHER_STEP,
        usage_item("t1", "uc-1", "now"), usage_item("t1", "uc-2", "now"), usage_item("t2", "uc-1", "now"),
        {"pk": "USECASES", "sk": "USECASE#uc-1", "id": "uc-1"}, {"pk": "USECASES", "sk": "USECASE#uc-2", "id": "uc-2"},
        _linked("uc-1", "a1"), _linked("uc-1", "a2", sort=2), _linked("uc-1", "a3", template_id="t2", sort=3),
        _plain("uc-1", "a4"),
        _linked("uc-2", "b1"),
    ])


class TestDelete:
    def test_returns_204_without_body(self):
        response = _run(_full_table())
        assert response["statusCode"] == 204
        assert response["body"] in ("", "null")

    def test_unlinks_steps_of_every_usage(self):
        table = _full_table()
        _run(table)
        for usecase_id, step_id in (("uc-1", "a1"), ("uc-1", "a2"), ("uc-2", "b1")):
            step = table.get(f"USECASE#{usecase_id}", f"STEP#{step_id}")
            assert step is not None and step["instruction"] == "x"
            for field in LINKAGE_FIELDS:
                assert field not in step, (step_id, field)

    def test_other_templates_steps_and_plain_steps_untouched(self):
        table = _full_table()
        _run(table)
        assert table.get("USECASE#uc-1", "STEP#a3")["template_id"] == "t2"
        assert table.get("USECASE#uc-1", "STEP#a4") == _plain("uc-1", "a4")
        assert table.get("TEMPLATE#t2", "STEP#ts9") == OTHER_STEP
        assert table.get("TEMPLATE#t2", "USAGE#uc-1") is not None
        assert table.get("TEMPLATES", "TEMPLATE#t2") == OTHER_TEMPLATE

    def test_partition_and_metadata_gone(self):
        table = _full_table()
        _run(table)
        assert table.by_prefix("TEMPLATE#t1", "") == []
        assert table.get("TEMPLATES", "TEMPLATE#t1") is None

    def test_stale_usage_is_skipped(self):
        table = FakeTable([TEMPLATE, TEMPLATE_STEP, usage_item("t1", "uc-gone", "now"), usage_item("t1", "uc-1", "now"),
                           _linked("uc-1", "a1")])
        response = _run(table)
        assert response["statusCode"] == 204
        assert "template_id" not in table.get("USECASE#uc-1", "STEP#a1")
        assert table.by_prefix("TEMPLATE#t1", "") == []

    def test_unlink_before_delete(self):
        """A failure during unlink leaves the template deletable on retry."""
        class FailsUnlink(FakeTable):
            def update_item(self, *a, **k):
                raise RuntimeError("dynamo down")

        table = FailsUnlink([TEMPLATE, TEMPLATE_STEP, usage_item("t1", "uc-1", "now"), _linked("uc-1", "a1")])
        response = _run(table)
        assert response["statusCode"] == 500
        assert table.get("TEMPLATES", "TEMPLATE#t1") == TEMPLATE
        assert table.get("TEMPLATE#t1", "STEP#ts1") == TEMPLATE_STEP
        assert table.delete_calls == []

    def test_template_without_usages(self):
        table = FakeTable([TEMPLATE, TEMPLATE_STEP, TEMPLATE_VARS])
        assert _run(table)["statusCode"] == 204
        assert table.by_prefix("TEMPLATE#t1", "") == [] and table.get("TEMPLATES", "TEMPLATE#t1") is None
        assert table.update_calls == []


class TestErrors:
    def test_unknown_template_is_404_and_writes_nothing(self):
        table = _full_table()
        response = _run(table, "ghost")
        assert response["statusCode"] == 404
        assert table.delete_calls == [] and table.update_calls == []

    def test_missing_scope_is_403(self):
        table = _full_table()
        assert _run(table, scope="api/templates.read")["statusCode"] == 403
        assert table.delete_calls == []

    def test_path_label_is_template(self):
        response = _run(_full_table(), "bad id!")
        assert response["statusCode"] == 400
        assert "template ID" in json.loads(response["body"])["error"]
