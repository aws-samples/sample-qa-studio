"""USAGE records are removed when a use case, or its last step linked to a template, is deleted.

Stale records are tolerated downstream; this keeps "Used by N tests" honest.
"""
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

import delete_step  # noqa: E402
import delete_usecase  # noqa: E402
from authz_test_support import make_event, resource_access_granted  # noqa: E402
from fake_table import FakeTable  # noqa: E402
from template_usage import usage_item  # noqa: E402


@pytest.fixture(autouse=True)
def _access_granted():
    """Handler-logic tests: ownership is covered by the *_access tests."""
    with resource_access_granted():
        yield


USECASE = {"pk": "USECASES", "sk": "USECASE#uc-1", "id": "uc-1", "name": "Checkout"}


def _linked(step_id, template_id, sort):
    return {"pk": "USECASE#uc-1", "sk": f"STEP#{step_id}", "id": step_id, "sort": sort, "instruction": "x",
            "step_type": "navigation", "template_id": template_id, "template_step_id": f"ts-{step_id}",
            "template_version": 1}


PLAIN = {"pk": "USECASE#uc-1", "sk": "STEP#p1", "id": "p1", "sort": 9, "instruction": "plain", "step_type": "navigation"}


def _event(path):
    return make_event(path=path, scopes="api/usecases.write")


def _run(module, table, path):
    with patch.object(module, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        return module.handler(_event(path), None)


def _usage_deletes(table):
    return sorted((k["pk"], k["sk"]) for k in table.delete_calls if k["sk"].startswith("USAGE#"))


class TestDeleteUsecase:
    def test_removes_usage_of_every_linked_template(self):
        table = FakeTable([USECASE, _linked("s1", "t1", 1), _linked("s2", "t1", 2), _linked("s3", "t2", 3), PLAIN,
                           usage_item("t1", "uc-1", "now"), usage_item("t2", "uc-1", "now"),
                           usage_item("t1", "uc-other", "now")])
        response = _run(delete_usecase, table, {"id": "uc-1"})
        assert response["statusCode"] == 204, response["body"]
        assert _usage_deletes(table) == [("TEMPLATE#t1", "USAGE#uc-1"), ("TEMPLATE#t2", "USAGE#uc-1")]
        assert table.get("TEMPLATE#t1", "USAGE#uc-other") is not None
        assert table.by_prefix("USECASE#uc-1", "STEP#") == []

    def test_no_linked_steps_no_usage_calls(self):
        table = FakeTable([USECASE, PLAIN])
        response = _run(delete_usecase, table, {"id": "uc-1"})
        assert response["statusCode"] == 204
        assert _usage_deletes(table) == []


class TestDeleteStep:
    def test_other_linked_step_remains_keeps_usage(self):
        table = FakeTable([_linked("s1", "t1", 1), _linked("s2", "t1", 2), usage_item("t1", "uc-1", "now")])
        response = _run(delete_step, table, {"id": "uc-1", "stepId": "s1"})
        assert response["statusCode"] == 204, response["body"]
        assert table.get("USECASE#uc-1", "STEP#s1") is None
        assert table.get("TEMPLATE#t1", "USAGE#uc-1") is not None

    def test_last_linked_step_removes_usage(self):
        table = FakeTable([_linked("s1", "t1", 1), _linked("s3", "t2", 3), PLAIN,
                           usage_item("t1", "uc-1", "now"), usage_item("t2", "uc-1", "now")])
        response = _run(delete_step, table, {"id": "uc-1", "stepId": "s1"})
        assert response["statusCode"] == 204, response["body"]
        assert table.get("TEMPLATE#t1", "USAGE#uc-1") is None
        assert table.get("TEMPLATE#t2", "USAGE#uc-1") is not None

    def test_unlinked_step_does_nothing_extra(self):
        table = FakeTable([_linked("s1", "t1", 1), PLAIN, usage_item("t1", "uc-1", "now")])
        _run(delete_step, table, {"id": "uc-1", "stepId": "p1"})
        assert table.delete_calls == [{"pk": "USECASE#uc-1", "sk": "STEP#p1"}]
        assert table.get("TEMPLATE#t1", "USAGE#uc-1") is not None
