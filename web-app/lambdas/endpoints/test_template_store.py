"""Template metadata access and version tracking (``template_store``).

Templates live at ``pk=TEMPLATES, sk=TEMPLATE#{id}``.  ``check_template_updates``
used to read ``pk=TEMPLATE#{id}, sk=METADATA`` (never existed) and the
``version`` was only bumped on metadata edits — so "update from template"
hints never appeared.  Every step create / update / delete / reorder now
bumps the template-level version through one helper.
"""
import json
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

import check_template_updates  # noqa: E402
import create_template_step  # noqa: E402
import delete_template_step  # noqa: E402
import reorder_template_steps  # noqa: E402
import update_template  # noqa: E402
import update_template_step  # noqa: E402
from authz_test_support import make_event, resource_access_granted  # noqa: E402
from fake_table import FakeTable  # noqa: E402
from template_store import (  # noqa: E402
    bump_template_version,
    bump_template_version_transact_item,
    get_template_metadata,
)


@pytest.fixture(autouse=True)
def _access_granted():
    """Handler-logic tests: ownership is covered by the *_access tests."""
    with resource_access_granted():
        yield


TEMPLATE = {"pk": "TEMPLATES", "sk": "TEMPLATE#t1", "id": "t1", "name": "Login", "version": 3, "updated_at": "t0"}
STEP = {"pk": "TEMPLATE#t1", "sk": "STEP#ts1", "id": "ts1", "sort": 1, "instruction": "x", "step_type": "navigation"}


def _event(body=None, path=None, scope="api/templates.write"):
    return make_event(path=path or {}, body=body, scopes=scope)


def _run(module, table, event, client=None):
    with patch.object(module, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        if client is not None:
            boto_mock.client.return_value = client
        return module.handler(event, None)


class TestGetTemplateMetadata:
    def test_reads_templates_partition(self):
        table = FakeTable([TEMPLATE])
        assert get_template_metadata(table, "t1") == TEMPLATE

    def test_missing_is_none(self):
        assert get_template_metadata(FakeTable([TEMPLATE]), "nope") is None


class TestBumpTemplateVersion:
    def test_increments_and_returns_new_version(self):
        table = FakeTable([TEMPLATE])
        assert bump_template_version(table, "t1") == 4
        assert bump_template_version(table, "t1") == 5
        stored = table.get("TEMPLATES", "TEMPLATE#t1")
        assert stored["version"] == 5
        assert stored["updated_at"] != "t0"

    def test_missing_template_is_not_created(self):
        table = FakeTable([TEMPLATE])
        assert bump_template_version(table, "ghost") is None
        assert table.get("TEMPLATES", "TEMPLATE#ghost") is None

    def test_version_attribute_is_aliased(self):
        table = FakeTable([TEMPLATE])
        bump_template_version(table, "t1")
        call = table.update_calls[0]
        assert "#version" in call["ExpressionAttributeNames"]
        assert "version" not in call["UpdateExpression"].replace("#version", "")

    def test_transact_item_matches_helper(self):
        item = bump_template_version_transact_item("tbl", "t1")["Update"]
        assert item["TableName"] == "tbl"
        assert item["Key"] == {"pk": {"S": "TEMPLATES"}, "sk": {"S": "TEMPLATE#t1"}}
        assert item["ConditionExpression"] == "attribute_exists(pk)"
        assert item["ExpressionAttributeNames"]["#version"] == "version"
        assert item["ExpressionAttributeValues"][":one"] == {"N": "1"}
        assert "ADD #version :one" in item["UpdateExpression"]


class TestStepWritesBumpVersion:
    def test_create_step(self):
        table = FakeTable([TEMPLATE])
        response = _run(create_template_step, table,
                        _event({"sort": 1, "instruction": "x", "step_type": "navigation"}, {"id": "t1"}))
        assert response["statusCode"] == 201, response["body"]
        assert table.get("TEMPLATES", "TEMPLATE#t1")["version"] == 4

    def test_update_step(self):
        table = FakeTable([TEMPLATE, STEP])
        response = _run(update_template_step, table,
                        _event({"sort": 1, "instruction": "y", "step_type": "navigation"}, {"id": "t1", "stepId": "ts1"}))
        assert response["statusCode"] == 200, response["body"]
        assert table.get("TEMPLATES", "TEMPLATE#t1")["version"] == 4

    def test_delete_step(self):
        table = FakeTable([TEMPLATE, STEP])
        response = _run(delete_template_step, table, _event(None, {"id": "t1", "stepId": "ts1"}))
        assert response["statusCode"] == 200, response["body"]
        assert table.get("TEMPLATE#t1", "STEP#ts1") is None
        assert table.get("TEMPLATES", "TEMPLATE#t1")["version"] == 4

    def test_reorder_bumps_once_in_the_same_transaction(self):
        client = MagicMock()
        response = _run(reorder_template_steps, FakeTable(), _event(
            {"step_orders": [{"step_id": "a", "sort": 2}, {"step_id": "b", "sort": 1}]}, {"id": "t1"},
        ), client=client)
        assert response["statusCode"] == 200, response["body"]
        items = client.transact_write_items.call_args.kwargs["TransactItems"]
        bumps = [i for i in items if i["Update"]["Key"]["pk"] == {"S": "TEMPLATES"}]
        assert len(bumps) == 1
        assert bumps[0] == bump_template_version_transact_item("test-table", "t1")
        assert len(items) == 3

    def test_metadata_update_still_bumps(self):
        table = FakeTable([TEMPLATE])
        response = _run(update_template, table,
                        _event({"name": "n", "description": "d", "category": "c", "tags": []}, {"id": "t1"}))
        assert response["statusCode"] == 200, response["body"]
        assert table.get("TEMPLATES", "TEMPLATE#t1")["version"] == 4


class TestCheckTemplateUpdates:
    LINKED = {"pk": "USECASE#uc-1", "sk": "STEP#s1", "id": "s1", "sort": 1, "instruction": "x",
              "step_type": "navigation", "template_id": "t1", "template_step_id": "ts1", "template_version": 3}

    def _check(self, table):
        response = _run(check_template_updates, table,
                        _event(None, {"id": "uc-1"}, "api/usecases.read api/templates.read"))
        assert response["statusCode"] == 200, response["body"]
        return json.loads(response["body"])["updates"]

    def test_finds_template_and_reports_no_update(self):
        updates = self._check(FakeTable([TEMPLATE, self.LINKED, {"pk": "USECASES", "sk": "USECASE#uc-1"}]))
        assert updates == [{
            "step_id": "s1", "current_version": 3, "latest_version": 3, "has_update": False,
            "template_id": "t1", "template_step_id": "ts1",
        }]

    def test_has_update_after_step_edit(self):
        table = FakeTable([TEMPLATE, STEP, self.LINKED, {"pk": "USECASES", "sk": "USECASE#uc-1"}])
        _run(update_template_step, table,
             _event({"sort": 1, "instruction": "changed", "step_type": "navigation"}, {"id": "t1", "stepId": "ts1"}))
        updates = self._check(table)
        assert updates[0]["has_update"] is True
        assert updates[0]["latest_version"] == 4

    def test_unlinked_steps_and_missing_templates_skipped(self):
        plain = {"pk": "USECASE#uc-1", "sk": "STEP#s2", "id": "s2", "sort": 2, "instruction": "x", "step_type": "navigation"}
        orphan = {**self.LINKED, "sk": "STEP#s3", "id": "s3", "template_id": "gone"}
        assert self._check(FakeTable([TEMPLATE, plain, orphan, {"pk": "USECASES", "sk": "USECASE#uc-1"}])) == []

    def test_no_wrong_metadata_key(self):
        source = open(check_template_updates.__file__).read()
        assert "'METADATA'" not in source
        assert "get_template_metadata" in source
