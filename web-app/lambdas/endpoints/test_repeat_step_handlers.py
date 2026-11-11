"""Handler tests for repeat-step fields in create_step / update_step / delete_step."""
import json
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("TABLE_NAME", "test-table")

import create_step  # noqa: E402
import delete_step  # noqa: E402
import update_step  # noqa: E402
from authz_test_support import make_event  # noqa: E402


def _event(body=None, path=None):
    return make_event(path=path, body=body, scopes="api/usecases.write")


class _FakeTable:
    def __init__(self, steps):
        self.steps = steps
        self.put_items = []
        self.update_calls = []
        self.delete_keys = []

    def query(self, **kwargs):
        return {"Items": list(self.steps)}

    def put_item(self, Item):  # noqa: N803
        self.put_items.append(Item)

    def update_item(self, **kwargs):
        self.update_calls.append(kwargs)

    def delete_item(self, Key):  # noqa: N803
        self.delete_keys.append(Key)

    def batch_writer(self):
        table = self

        class _Writer:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def delete_item(self_inner, Key):  # noqa: N803
                table.delete_keys.append(Key)

        return _Writer()


def _patch(module, table):
    resource = MagicMock()
    resource.Table.return_value = table
    boto_mock = patch.object(module, "boto3")
    return boto_mock, resource


REPEAT = {
    "pk": "USECASE#uc-1", "sk": "STEP#r1", "id": "r1", "sort": 1,
    "step_type": "repeat", "instruction": "Login as each user",
    "repeat_columns": ["email"], "repeat_rows": [["a@x.test"]],
}
CHILD = {
    "pk": "USECASE#uc-1", "sk": "STEP#c1", "id": "c1", "sort": 2,
    "step_type": "navigation", "instruction": "Type {{email}}", "parent_step_id": "r1",
}
PLAIN = {
    "pk": "USECASE#uc-1", "sk": "STEP#p1", "id": "p1", "sort": 3,
    "step_type": "navigation", "instruction": "Click",
}


class TestCreateStep:
    def _create(self, body, steps):
        table = _FakeTable(steps)
        boto_mock, resource = _patch(create_step, table)
        with boto_mock as b:
            b.resource.return_value = resource
            response = create_step.handler(_event(body, {"id": "uc-1"}), None)
        return response, table

    def test_repeat_step_persists_dataset(self):
        body = {
            "usecaseId": "uc-1", "sort": 1, "instruction": "Login as each user",
            "step_type": "repeat", "repeat_columns": ["email", "role"],
            "repeat_rows": [["a@x.test", "admin"]],
        }
        response, table = self._create(body, [])
        assert response["statusCode"] == 201, response["body"]
        item = table.put_items[0]
        assert item["step_type"] == "repeat"
        assert item["repeat_columns"] == ["email", "role"]
        assert item["repeat_rows"] == [["a@x.test", "admin"]]
        assert "parent_step_id" not in item

    def test_plain_step_has_no_repeat_fields(self):
        body = {"usecaseId": "uc-1", "sort": 1, "instruction": "Click", "step_type": "navigation"}
        response, table = self._create(body, [])
        assert response["statusCode"] == 201
        item = table.put_items[0]
        for field in ("repeat_columns", "repeat_rows", "parent_step_id"):
            assert field not in item

    def test_child_step_persists_parent(self):
        body = {
            "usecaseId": "uc-1", "sort": 2, "instruction": "Type {{email}}",
            "step_type": "navigation", "parent_step_id": "r1",
        }
        response, table = self._create(body, [REPEAT])
        assert response["statusCode"] == 201, response["body"]
        assert table.put_items[0]["parent_step_id"] == "r1"

    def test_invalid_repeat_returns_400_with_joined_errors(self):
        body = {
            "usecaseId": "uc-1", "sort": 1, "instruction": "Login as each user",
            "step_type": "repeat", "repeat_columns": ["UniqueID", "1bad"],
            "repeat_rows": [["a"]],
        }
        response, table = self._create(body, [])
        assert response["statusCode"] == 400
        error = json.loads(response["body"])["error"]
        assert "reserved" in error
        assert "identifier" in error
        assert table.put_items == []

    def test_duplicate_label_returns_400(self):
        body = {
            "usecaseId": "uc-1", "sort": 5, "instruction": "Login as each user",
            "step_type": "repeat", "repeat_columns": ["email"], "repeat_rows": [["x"]],
        }
        response, _ = self._create(body, [REPEAT])
        assert response["statusCode"] == 400
        assert "unique" in json.loads(response["body"])["error"]

    def test_child_with_unknown_parent_returns_400(self):
        body = {
            "usecaseId": "uc-1", "sort": 2, "instruction": "x",
            "step_type": "navigation", "parent_step_id": "nope",
        }
        response, _ = self._create(body, [REPEAT])
        assert response["statusCode"] == 400
        assert "does not exist" in json.loads(response["body"])["error"]

    def test_row_and_column_caps(self):
        body = {
            "usecaseId": "uc-1", "sort": 1, "instruction": "L", "step_type": "repeat",
            "repeat_columns": [f"c{i}" for i in range(21)],
            "repeat_rows": [["x"] * 21 for _ in range(101)],
        }
        response, _ = self._create(body, [])
        assert response["statusCode"] == 400
        error = json.loads(response["body"])["error"]
        assert "at most 20 columns" in error
        assert "at most 100 rows" in error

    def test_sibling_query_skipped_for_plain_steps(self):
        """Plain steps don't pay for a sibling query."""
        table = _FakeTable([])
        table.query = MagicMock(side_effect=AssertionError("should not query"))
        boto_mock, resource = _patch(create_step, table)
        body = {"usecaseId": "uc-1", "sort": 1, "instruction": "Click", "step_type": "navigation"}
        with boto_mock as b:
            b.resource.return_value = resource
            response = create_step.handler(_event(body, {"id": "uc-1"}), None)
        assert response["statusCode"] == 201


class TestUpdateStep:
    def _update(self, step_id, body, steps):
        table = _FakeTable(steps)
        boto_mock, resource = _patch(update_step, table)
        with boto_mock as b:
            b.resource.return_value = resource
            response = update_step.handler(
                _event(body, {"id": "uc-1", "stepId": step_id}), None,
            )
        return response, table

    def test_update_repeat_dataset(self):
        body = {
            "instruction": "Login as each user", "step_type": "repeat",
            "repeat_columns": ["email", "role"], "repeat_rows": [["a", "b"], ["c", "d"]],
        }
        response, table = self._update("r1", body, [REPEAT, CHILD])
        assert response["statusCode"] == 200, response["body"]
        values = table.update_calls[0]["ExpressionAttributeValues"]
        assert values[":repeat_columns"] == ["email", "role"]
        assert values[":repeat_rows"] == [["a", "b"], ["c", "d"]]

    def test_changing_columns_revalidates_stored_rows(self):
        body = {
            "instruction": "Login as each user", "step_type": "repeat",
            "repeat_columns": ["email", "role"],
        }
        response, table = self._update("r1", body, [REPEAT])
        assert response["statusCode"] == 400
        assert "2 cells are expected" in json.loads(response["body"])["error"]
        assert table.update_calls == []

    def test_changing_type_away_from_repeat_with_children_is_400(self):
        body = {"instruction": "Login as each user", "step_type": "navigation"}
        response, table = self._update("r1", body, [REPEAT, CHILD])
        assert response["statusCode"] == 400
        assert "children" in json.loads(response["body"])["error"]
        assert table.update_calls == []

    def test_changing_type_away_from_repeat_without_children_is_ok(self):
        body = {"instruction": "Login", "step_type": "navigation"}
        response, table = self._update("r1", body, [REPEAT, PLAIN])
        assert response["statusCode"] == 200
        assert len(table.update_calls) == 1

    def test_child_update_keeps_parent(self):
        body = {"instruction": "Type {{email}} slowly", "step_type": "navigation", "parent_step_id": "r1"}
        response, table = self._update("c1", body, [REPEAT, CHILD])
        assert response["statusCode"] == 200
        assert table.update_calls[0]["ExpressionAttributeValues"][":parent_step_id"] == "r1"

    def test_child_cannot_become_repeat(self):
        body = {
            "instruction": "inner", "step_type": "repeat", "parent_step_id": "r1",
            "repeat_columns": ["a"], "repeat_rows": [["x"]],
        }
        response, table = self._update("c1", body, [REPEAT, CHILD])
        assert response["statusCode"] == 400
        assert table.update_calls == []

    def test_leaving_repeat_removes_dataset_attributes(self):
        body = {"instruction": "Login", "step_type": "navigation"}
        response, table = self._update("r1", body, [REPEAT, PLAIN])
        assert response["statusCode"] == 200
        assert "REMOVE repeat_columns, repeat_rows" in table.update_calls[0]["UpdateExpression"]


class TestDeleteStep:
    def _delete(self, step_id, steps):
        table = _FakeTable(steps)
        boto_mock, resource = _patch(delete_step, table)
        with boto_mock as b:
            b.resource.return_value = resource
            response = delete_step.handler(_event(None, {"id": "uc-1", "stepId": step_id}), None)
        return response, table

    def test_delete_repeat_cascades_to_children(self):
        child2 = {**CHILD, "sk": "STEP#c2", "id": "c2", "sort": 3}
        response, table = self._delete("r1", [REPEAT, CHILD, child2, PLAIN])
        assert response["statusCode"] == 204
        deleted = sorted(k["sk"] for k in table.delete_keys)
        assert deleted == ["STEP#c1", "STEP#c2", "STEP#r1"]

    def test_delete_plain_step_only_deletes_itself(self):
        response, table = self._delete("p1", [REPEAT, CHILD, PLAIN])
        assert response["statusCode"] == 204
        assert [k["sk"] for k in table.delete_keys] == ["STEP#p1"]

    def test_delete_child_does_not_touch_parent(self):
        response, table = self._delete("c1", [REPEAT, CHILD, PLAIN])
        assert response["statusCode"] == 204
        assert [k["sk"] for k in table.delete_keys] == ["STEP#c1"]


import pytest as _pytest  # noqa: E402
from authz_test_support import resource_access_granted as _resource_access_granted  # noqa: E402


@_pytest.fixture(autouse=True)
def _access_granted():
    """Handler-logic tests: ownership is covered by the *_access tests."""
    with _resource_access_granted():
        yield
