"""``dataset_id`` on repeat steps across every step write / copy path.

A repeat step references an application dataset (``dataset_id``) *or* carries
inline ``repeat_columns`` / ``repeat_rows``.  ``create_step`` / ``update_step``
check the dataset exists in the use case's application, ``import_usecase``
checks it in the target application, ``clone_usecase`` only when cloning into
another application, ``export_usecase`` keeps the reference, and template
steps reject it (templates have no application).
"""
import json
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

import clone_usecase  # noqa: E402
import create_step  # noqa: E402
import create_template_step  # noqa: E402
import export_usecase  # noqa: E402
import import_usecase  # noqa: E402
import replace_template_definition  # noqa: E402
import update_step  # noqa: E402
import update_template_step  # noqa: E402
from authz_test_support import APP_ID, make_event, resource_access_granted  # noqa: E402
from dataset_models import DATASET_NOT_IN_APPLICATION_ERROR  # noqa: E402
from fake_table import FakeTable  # noqa: E402
from repeat_validation import (  # noqa: E402
    DATASET_NOT_SUPPORTED_IN_TEMPLATES_ERROR,
    REPEAT_BOTH_SOURCES_ERROR,
)

UC = "uc-1"
OTHER_APP = "app-b"


@pytest.fixture(autouse=True)
def _access_granted():
    with resource_access_granted():
        yield


def _usecase(usecase_id=UC, app_id=APP_ID):
    item = {"pk": "USECASES", "sk": f"USECASE#{usecase_id}", "id": usecase_id, "name": "Login",
            "starting_url": "https://e.test/", "executing_region": "us-east-1", "active": True, "tags": []}
    if app_id:
        item["application_id"] = app_id
    return item


def _dataset(dataset_id="ds-1", app_id=APP_ID):
    return {"pk": f"APPLICATION#{app_id}", "sk": f"DATASET#{dataset_id}", "dataset_id": dataset_id,
            "name": "customers", "columns": ["email"], "rows": [["a@x.test"]],
            "created_at": "t", "updated_at": "t", "created_by": "qa"}


def _step(step_id, usecase_id=UC, **fields):
    item = {"pk": f"USECASE#{usecase_id}", "sk": f"STEP#{step_id}", "id": step_id, "sort": 1,
            "step_type": "navigation", "instruction": "x"}
    item.update(fields)
    return item


def _run(module, table, event, secrets=None):
    with patch.object(module, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        if secrets is not None:
            boto_mock.client.return_value = secrets
        return module.handler(event, None)


def _body(response):
    return json.loads(response["body"])


# ---------------------------------------------------------------------------
# create_step
# ---------------------------------------------------------------------------


class TestCreateStep:
    def _create(self, table, body):
        event = make_event(path={"id": UC}, body={"usecaseId": UC, "sort": 1, **body}, scopes="api/usecases.write")
        return _run(create_step, table, event)

    def test_repeat_with_dataset_id_persists_reference_only(self):
        table = FakeTable([_usecase(), _dataset()])
        response = self._create(table, {"instruction": "Users", "step_type": "repeat", "dataset_id": "ds-1"})
        assert response["statusCode"] == 201, response["body"]
        item = table.put_calls[0]
        assert item["dataset_id"] == "ds-1"
        assert "repeat_columns" not in item and "repeat_rows" not in item

    def test_missing_dataset_is_400(self):
        table = FakeTable([_usecase()])
        response = self._create(table, {"instruction": "Users", "step_type": "repeat", "dataset_id": "ds-1"})
        assert response["statusCode"] == 400
        assert _body(response)["error"] == DATASET_NOT_IN_APPLICATION_ERROR
        assert table.put_calls == []

    def test_dataset_of_other_application_is_400(self):
        table = FakeTable([_usecase(), _dataset(app_id=OTHER_APP)])
        response = self._create(table, {"instruction": "Users", "step_type": "repeat", "dataset_id": "ds-1"})
        assert response["statusCode"] == 400
        assert _body(response)["error"] == DATASET_NOT_IN_APPLICATION_ERROR

    def test_usecase_without_application_is_400(self):
        table = FakeTable([_usecase(app_id=None), _dataset()])
        response = self._create(table, {"instruction": "Users", "step_type": "repeat", "dataset_id": "ds-1"})
        assert response["statusCode"] == 400
        assert _body(response)["error"] == DATASET_NOT_IN_APPLICATION_ERROR

    def test_both_sources_is_400_before_any_lookup(self):
        table = FakeTable([_usecase(), _dataset()])
        response = self._create(table, {"instruction": "Users", "step_type": "repeat", "dataset_id": "ds-1",
                                        "repeat_columns": ["a"], "repeat_rows": [["1"]]})
        assert response["statusCode"] == 400
        assert _body(response)["error"] == REPEAT_BOTH_SOURCES_ERROR

    def test_dataset_id_on_plain_step_is_400(self):
        table = FakeTable([_usecase(), _dataset()])
        response = self._create(table, {"instruction": "Click", "step_type": "navigation", "dataset_id": "ds-1"})
        assert response["statusCode"] == 400
        assert "only allowed on repeat steps" in _body(response)["error"]

    def test_inline_repeat_does_not_read_the_dataset(self):
        class NoDatasetReads(FakeTable):
            def get_item(self, Key, **kw):  # noqa: N803
                raise AssertionError(f"unexpected get_item {Key}")

        response = self._create(NoDatasetReads([_usecase()]), {
            "instruction": "Users", "step_type": "repeat", "repeat_columns": ["a"], "repeat_rows": [["1"]],
        })
        assert response["statusCode"] == 201, response["body"]


# ---------------------------------------------------------------------------
# update_step
# ---------------------------------------------------------------------------


INLINE_REPEAT = _step("r1", step_type="repeat", instruction="Users", repeat_columns=["email"],
                      repeat_rows=[["a@x.test"]])
DATASET_REPEAT = _step("r2", step_type="repeat", instruction="Customers", dataset_id="ds-1")


class TestUpdateStep:
    def _update(self, table, step_id, body):
        event = make_event(path={"id": UC, "stepId": step_id}, body=body, scopes="api/usecases.write")
        return _run(update_step, table, event)

    def test_switch_inline_to_dataset_removes_inline_rows(self):
        table = FakeTable([_usecase(), _dataset(), INLINE_REPEAT])
        response = self._update(table, "r1", {"instruction": "Users", "step_type": "repeat", "dataset_id": "ds-1"})
        assert response["statusCode"] == 200, response["body"]
        stored = table.get(f"USECASE#{UC}", "STEP#r1")
        assert stored["dataset_id"] == "ds-1"
        assert "repeat_columns" not in stored and "repeat_rows" not in stored
        expression = table.update_calls[0]["UpdateExpression"]
        assert "REMOVE repeat_columns, repeat_rows" in expression

    def test_switch_dataset_to_inline_removes_dataset_id(self):
        table = FakeTable([_usecase(), _dataset(), DATASET_REPEAT])
        response = self._update(table, "r2", {"instruction": "Customers", "step_type": "repeat",
                                              "repeat_columns": ["a"], "repeat_rows": [["1"]]})
        assert response["statusCode"] == 200, response["body"]
        stored = table.get(f"USECASE#{UC}", "STEP#r2")
        assert "dataset_id" not in stored
        assert stored["repeat_columns"] == ["a"]
        assert "REMOVE dataset_id" in table.update_calls[0]["UpdateExpression"]

    def test_body_with_both_sources_is_400(self):
        table = FakeTable([_usecase(), _dataset(), INLINE_REPEAT])
        response = self._update(table, "r1", {"instruction": "Users", "step_type": "repeat", "dataset_id": "ds-1",
                                              "repeat_columns": ["a"], "repeat_rows": [["1"]]})
        assert response["statusCode"] == 400
        assert _body(response)["error"] == REPEAT_BOTH_SOURCES_ERROR
        assert table.update_calls == []

    def test_missing_dataset_is_400(self):
        table = FakeTable([_usecase(), INLINE_REPEAT])
        response = self._update(table, "r1", {"instruction": "Users", "step_type": "repeat", "dataset_id": "ds-9"})
        assert response["statusCode"] == 400
        assert _body(response)["error"] == DATASET_NOT_IN_APPLICATION_ERROR
        assert table.update_calls == []

    def test_label_change_on_dataset_repeat_keeps_reference_without_lookup(self):
        class NoDatasetReads(FakeTable):
            def get_item(self, Key, **kw):  # noqa: N803
                raise AssertionError(f"unexpected get_item {Key}")

        table = NoDatasetReads([_usecase(), DATASET_REPEAT])
        response = self._update(table, "r2", {"instruction": "Renamed", "step_type": "repeat"})
        assert response["statusCode"] == 200, response["body"]
        stored = table.get(f"USECASE#{UC}", "STEP#r2")
        assert stored["dataset_id"] == "ds-1" and stored["instruction"] == "Renamed"

    def test_leaving_repeat_removes_dataset_id_too(self):
        table = FakeTable([_usecase(), DATASET_REPEAT])
        response = self._update(table, "r2", {"instruction": "Plain", "step_type": "navigation"})
        assert response["statusCode"] == 200, response["body"]
        stored = table.get(f"USECASE#{UC}", "STEP#r2")
        assert "dataset_id" not in stored
        assert "REMOVE repeat_columns, repeat_rows, dataset_id" in table.update_calls[0]["UpdateExpression"]


# ---------------------------------------------------------------------------
# import_usecase
# ---------------------------------------------------------------------------


def _import_payload(steps, app_id=APP_ID):
    return {
        "exportVersion": "1.0", "exportedAt": "2026-01-01T00:00:00Z", "application_id": app_id,
        "usecase": {"name": "Login", "starting_url": "https://e.test/", "tags": []},
        "steps": steps,
    }


DATASET_REPEAT_EXPORT = {
    "sort": 1, "step_type": "repeat", "instruction": "Customers", "dataset_id": "ds-1",
    "steps": [{"sort": 1, "step_type": "navigation", "instruction": "Type {{email}}"}],
}


class TestImport:
    def _import(self, table, steps):
        event = make_event(body=_import_payload(steps), scopes="api/usecases.write")
        return _run(import_usecase, table, event)

    def test_existing_dataset_imports_with_reference(self):
        table = FakeTable([_dataset()])
        response = self._import(table, [DATASET_REPEAT_EXPORT])
        assert response["statusCode"] == 200, response["body"]
        steps = sorted([i for i in table.put_calls if i["sk"].startswith("STEP#")], key=lambda s: s["sort"])
        assert steps[0]["dataset_id"] == "ds-1"
        assert "repeat_columns" not in steps[0]
        assert steps[1]["parent_step_id"] == steps[0]["id"]

    def test_missing_dataset_is_400_with_ids_and_no_writes(self):
        table = FakeTable()
        second = {**DATASET_REPEAT_EXPORT, "sort": 2, "instruction": "Orders", "dataset_id": "ds-2"}
        response = self._import(table, [DATASET_REPEAT_EXPORT, second])
        assert response["statusCode"] == 400
        payload = _body(response)
        assert payload["success"] is False
        assert payload["error"] == DATASET_NOT_IN_APPLICATION_ERROR
        assert payload["datasetIds"] == ["ds-1", "ds-2"]
        assert "ds-1" in payload["message"] and "ds-2" in payload["message"]
        assert table.put_calls == []

    def test_dataset_in_other_application_is_400(self):
        table = FakeTable([_dataset(app_id=OTHER_APP)])
        response = self._import(table, [DATASET_REPEAT_EXPORT])
        assert response["statusCode"] == 400
        assert _body(response)["datasetIds"] == ["ds-1"]

    def test_both_sources_is_400(self):
        table = FakeTable([_dataset()])
        step = {**DATASET_REPEAT_EXPORT, "repeat_columns": ["a"], "repeat_rows": [["1"]]}
        response = self._import(table, [step])
        assert response["statusCode"] == 400
        assert REPEAT_BOTH_SOURCES_ERROR in _body(response)["message"]

    def test_inline_file_reads_nothing(self):
        class WriteOnly(FakeTable):
            def get_item(self, Key, **kw):  # noqa: N803
                raise AssertionError("read")

            def query(self, *a, **kw):
                raise AssertionError("read")

        step = {"sort": 1, "step_type": "repeat", "instruction": "Users", "repeat_columns": ["a"],
                "repeat_rows": [["1"]], "steps": []}
        response = self._import(WriteOnly(), [step])
        assert response["statusCode"] == 200, response["body"]


# ---------------------------------------------------------------------------
# clone_usecase
# ---------------------------------------------------------------------------


class TestClone:
    def _clone(self, table, body):
        secrets = MagicMock()
        secrets.list_secrets.return_value = {"SecretList": []}
        event = make_event(path={"id": UC}, body=body, scopes="api/usecases.write")
        return _run(clone_usecase, table, event, secrets=secrets)

    def _cloned_steps(self, table):
        return [i for i in table.put_calls if i["sk"].startswith("STEP#")]

    def test_same_application_keeps_reference_without_lookup(self):
        class NoDatasetReads(FakeTable):
            def get_item(self, Key, **kw):  # noqa: N803
                if Key["sk"].startswith("DATASET#"):
                    raise AssertionError(f"unexpected dataset lookup {Key}")
                return super().get_item(Key, **kw)

        table = NoDatasetReads([_usecase(), DATASET_REPEAT])
        response = self._clone(table, {"name": "Copy"})
        assert response["statusCode"] == 200, response["body"]
        (step,) = self._cloned_steps(table)
        assert step["dataset_id"] == "ds-1"

    def test_cross_application_with_dataset_present_is_ok(self):
        table = FakeTable([_usecase(), DATASET_REPEAT, _dataset(app_id=OTHER_APP)])
        response = self._clone(table, {"name": "Copy", "application_id": OTHER_APP})
        assert response["statusCode"] == 200, response["body"]
        (step,) = self._cloned_steps(table)
        assert step["dataset_id"] == "ds-1"

    def test_cross_application_with_missing_dataset_is_400_and_writes_nothing(self):
        table = FakeTable([_usecase(), DATASET_REPEAT, _dataset(app_id=APP_ID)])
        response = self._clone(table, {"name": "Copy", "application_id": OTHER_APP})
        assert response["statusCode"] == 400
        payload = _body(response)
        assert payload["success"] is False
        assert payload["error"] == DATASET_NOT_IN_APPLICATION_ERROR
        assert payload["datasetIds"] == ["ds-1"]
        assert table.put_calls == []

    def test_cross_application_without_dataset_steps_needs_no_lookup(self):
        table = FakeTable([_usecase(), INLINE_REPEAT])
        response = self._clone(table, {"name": "Copy", "application_id": OTHER_APP})
        assert response["statusCode"] == 200, response["body"]


# ---------------------------------------------------------------------------
# export_usecase
# ---------------------------------------------------------------------------


class TestExport:
    def test_export_keeps_dataset_id_and_has_no_inline_rows(self):
        child = _step("c1", step_type="navigation", instruction="Type {{email}}", parent_step_id="r2", sort=2)
        table = FakeTable([_usecase(), DATASET_REPEAT, child])
        secrets = MagicMock()
        secrets.list_secrets.return_value = {"SecretList": []}
        event = make_event(path={"id": UC}, scopes="api/usecases.read")
        response = _run(export_usecase, table, event, secrets=secrets)
        assert response["statusCode"] == 200, response["body"]
        (repeat,) = _body(response)["steps"]
        assert repeat["dataset_id"] == "ds-1"
        assert "repeat_columns" not in repeat and "repeat_rows" not in repeat
        assert repeat["steps"][0]["instruction"] == "Type {{email}}"


# ---------------------------------------------------------------------------
# template steps reject dataset_id
# ---------------------------------------------------------------------------


def _template_event(body, path, scope="api/templates.write"):
    return {"requestContext": {"authorizer": {"sub": "u1", "email": "qa@example.com", "scope": scope}},
            "body": json.dumps(body), "pathParameters": path}


class TestTemplateSteps:
    def test_create_template_step_rejects_dataset_id(self):
        body = {"sort": 1, "instruction": "x", "step_type": "navigation", "dataset_id": "ds-1"}
        with patch.object(create_template_step, "boto3") as boto_mock:
            table = boto_mock.resource.return_value.Table.return_value
            response = create_template_step.handler(_template_event(body, {"id": "t1"}), None)
        assert response["statusCode"] == 400
        assert _body(response)["error"] == DATASET_NOT_SUPPORTED_IN_TEMPLATES_ERROR
        table.put_item.assert_not_called()

    def test_update_template_step_rejects_dataset_id(self):
        body = {"instruction": "x", "step_type": "navigation", "dataset_id": "ds-1"}
        with patch.object(update_template_step, "boto3") as boto_mock:
            table = boto_mock.resource.return_value.Table.return_value
            response = update_template_step.handler(_template_event(body, {"id": "t1", "stepId": "s1"}), None)
        assert response["statusCode"] == 400
        assert _body(response)["error"] == DATASET_NOT_SUPPORTED_IN_TEMPLATES_ERROR
        table.update_item.assert_not_called()

    def test_put_template_definition_rejects_dataset_id(self):
        template = {"pk": "TEMPLATES", "sk": "TEMPLATE#t1", "id": "t1", "name": "Login", "version": 1}
        body = {"templateVersion": "1.0", "template": {"name": "Login"},
                "steps": [{"sort": 1, "step_type": "navigation", "instruction": "x", "dataset_id": "ds-1"}]}
        client = MagicMock()
        with patch.object(replace_template_definition, "boto3") as boto_mock:
            boto_mock.resource.return_value.Table.return_value = FakeTable([template])
            boto_mock.client.return_value = client
            response = replace_template_definition.handler(_template_event(body, {"id": "t1"}), None)
        assert response["statusCode"] == 400
        assert _body(response)["error"] == DATASET_NOT_SUPPORTED_IN_TEMPLATES_ERROR
        client.transact_write_items.assert_not_called()
