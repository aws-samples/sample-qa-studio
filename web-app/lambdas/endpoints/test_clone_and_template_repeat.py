"""Clone remaps ``parent_step_id`` and copies repeat fields; templates reject repeat."""
import json
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("TABLE_NAME", "test-table")

import clone_usecase  # noqa: E402
import create_template_step  # noqa: E402
import update_template_step  # noqa: E402
from authz_test_support import resource_access_granted  # noqa: E402
from repeat_validation import REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR  # noqa: E402
from step_copy import nest_repeat_children  # noqa: E402


def _event(body=None, path=None, scope="api/usecases.write"):
    event = {"requestContext": {"authorizer": {"sub": "u1", "email": "qa@example.com", "scope": scope}}}
    if body is not None:
        event["body"] = json.dumps(body)
    if path is not None:
        event["pathParameters"] = path
    return event


SOURCE_STEPS = [
    {"pk": "USECASE#src", "sk": "STEP#r1", "id": "r1", "sort": 1, "step_type": "repeat",
     "instruction": "Users", "repeat_columns": ["email"], "repeat_rows": [["a"], ["b"]]},
    {"pk": "USECASE#src", "sk": "STEP#c1", "id": "c1", "sort": 2, "step_type": "browser",
     "instruction": "Open", "browser_action": "navigate", "browser_args": '{"url": "x"}',
     "parent_step_id": "r1", "trajectory_s3_key": "k"},
    {"pk": "USECASE#src", "sk": "STEP#c2", "id": "c2", "sort": 3, "step_type": "navigation",
     "instruction": "Type {{email}}", "parent_step_id": "r1"},
    {"pk": "USECASE#src", "sk": "STEP#p1", "id": "p1", "sort": 4, "step_type": "validation",
     "instruction": "Done", "validation_type": "string", "validation_operator": "exact", "validation_value": "ok"},
]


class TestCloneRepeatBlock:
    def _clone(self, steps):
        table = MagicMock()
        table.get_item.side_effect = lambda Key: (
            {"Item": {"name": "Src", "starting_url": "https://e.test/"}} if Key["sk"] == "USECASE#src" else {}
        )
        table.query.return_value = {"Items": list(steps)}
        put_items = []
        table.put_item.side_effect = lambda Item: put_items.append(Item)
        resource = MagicMock()
        resource.Table.return_value = table
        secrets = MagicMock()
        secrets.list_secrets.return_value = {"SecretList": []}
        with patch.object(clone_usecase, "boto3") as boto_mock, resource_access_granted():
            boto_mock.resource.return_value = resource
            boto_mock.client.return_value = secrets
            response = clone_usecase.handler(_event({"name": "Copy"}, {"id": "src"}), None)
        assert response["statusCode"] == 200, response["body"]
        return [i for i in put_items if i["sk"].startswith("STEP#")]

    def test_children_point_at_cloned_repeat(self):
        cloned = sorted(self._clone(SOURCE_STEPS), key=lambda s: s["sort"])
        assert [s["sort"] for s in cloned] == [1, 2, 3, 4]
        repeat, c1, c2, p1 = cloned
        assert repeat["step_type"] == "repeat"
        assert repeat["id"] != "r1"
        assert repeat["repeat_columns"] == ["email"]
        assert repeat["repeat_rows"] == [["a"], ["b"]]
        assert c1["parent_step_id"] == repeat["id"]
        assert c2["parent_step_id"] == repeat["id"]
        assert "parent_step_id" not in p1
        assert c1["browser_action"] == "navigate"
        assert "trajectory_s3_key" not in c1
        assert p1["validation_value"] == "ok"
        assert len({s["id"] for s in cloned}) == 4

    def test_clone_is_structurally_equal_to_source(self):
        cloned = self._clone(SOURCE_STEPS)

        def _export_shape(items):
            from step_copy import copy_step_fields
            return nest_repeat_children([
                {"sort": i["sort"], **copy_step_fields(i), "id": i["id"], "parent_step_id": i.get("parent_step_id")}
                for i in items
            ])

        assert _export_shape(cloned) == _export_shape(SOURCE_STEPS)

    def test_plain_usecase_clone_unchanged(self):
        cloned = self._clone([SOURCE_STEPS[3]])
        assert len(cloned) == 1
        assert "parent_step_id" not in cloned[0]
        assert cloned[0]["instruction"] == "Done"


class TestTemplateStepsRejectRepeat:
    def _create(self, body):
        with patch.object(create_template_step, "boto3") as boto_mock, \
             patch.object(create_template_step, "require_scopes", return_value=({"sub": "u1"}, None)):
            table = boto_mock.resource.return_value.Table.return_value
            response = create_template_step.handler(_event(body, {"id": "t1"}, "api/templates.write"), None)
        return response, table

    def _update(self, body):
        with patch.object(update_template_step, "boto3") as boto_mock, \
             patch.object(update_template_step, "require_scopes", return_value=({"sub": "u1"}, None)):
            table = boto_mock.resource.return_value.Table.return_value
            table.update_item.return_value = {"Attributes": {"id": "s1"}}
            response = update_template_step.handler(
                _event(body, {"id": "t1", "stepId": "s1"}, "api/templates.write"), None,
            )
        return response, table

    def test_create_repeat_rejected(self):
        response, table = self._create({"sort": 1, "instruction": "L", "step_type": "repeat",
                                        "repeat_columns": ["a"], "repeat_rows": [["x"]]})
        assert response["statusCode"] == 400
        assert json.loads(response["body"])["error"] == REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR
        table.put_item.assert_not_called()

    def test_create_with_parent_rejected(self):
        response, table = self._create({"sort": 1, "instruction": "x", "step_type": "navigation", "parent_step_id": "r1"})
        assert response["statusCode"] == 400
        table.put_item.assert_not_called()

    def test_create_plain_step_ok(self):
        response, table = self._create({"sort": 1, "instruction": "x", "step_type": "navigation"})
        assert response["statusCode"] == 201
        item = table.put_item.call_args.kwargs["Item"]
        assert "parent_step_id" not in item and "repeat_columns" not in item

    def test_update_repeat_rejected(self):
        response, table = self._update({"instruction": "L", "step_type": "repeat"})
        assert response["statusCode"] == 400
        assert json.loads(response["body"])["error"] == REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR
        table.update_item.assert_not_called()

    def test_update_with_parent_rejected(self):
        response, table = self._update({"instruction": "x", "step_type": "navigation", "parent_step_id": "r1"})
        assert response["statusCode"] == 400
        table.update_item.assert_not_called()

    def test_update_plain_step_ok(self):
        response, table = self._update({"instruction": "x", "step_type": "navigation"})
        assert response["statusCode"] == 200
        step_update, version_bump = table.update_item.call_args_list
        assert step_update.kwargs["Key"] == {"pk": "TEMPLATE#t1", "sk": "STEP#s1"}
        assert version_bump.kwargs["Key"] == {"pk": "TEMPLATES", "sk": "TEMPLATE#t1"}


class TestTemplateComparisonToleratesChildren:
    """``update_step_from_template`` / ``check_template_updates`` must not crash
    on a usecase step that carries ``parent_step_id`` (templates never do)."""

    def test_check_template_updates_handles_child_step(self):
        import check_template_updates

        source = open(check_template_updates.__file__).read()
        # Static guard: nothing in the comparison indexes repeat-only fields.
        assert "repeat_columns" not in source and "parent_step_id" not in source

    def test_update_step_from_template_handles_child_step(self):
        import update_step_from_template

        source = open(update_step_from_template.__file__).read()
        assert "repeat_columns" not in source and "parent_step_id" not in source
