"""Nested repeat shape in export / import JSON (+ ``step_copy`` helpers)."""
import json
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

from authz_test_support import APP_ID, make_event, resource_access_granted  # noqa: E402
from step_copy import (  # noqa: E402
    COPYABLE_STEP_FIELDS,
    StepTreeError,
    copy_step_fields,
    flatten_imported_steps,
    nest_repeat_children,
)


class TestCopyStepFields:
    def test_copies_present_non_empty_fields_only(self):
        step = {
            "pk": "USECASE#u", "sk": "STEP#s", "id": "s", "sort": 3, "created_at": "t",
            "instruction": "Go", "step_type": "browser", "browser_action": "navigate",
            "browser_args": '{"url": "x"}', "secret_key": "", "validation_type": None,
            "enable_advanced_click_types": False, "parent_step_id": "r1",
            "trajectory_s3_key": "k", "cached_steps": "[]",
            "repeat_columns": ["a"], "repeat_rows": [["1"]],
        }
        copied = copy_step_fields(step)
        assert copied == {
            "instruction": "Go", "step_type": "browser", "browser_action": "navigate",
            "browser_args": '{"url": "x"}', "enable_advanced_click_types": False,
            "repeat_columns": ["a"], "repeat_rows": [["1"]],
        }

    def test_field_list_covers_every_authoring_field(self):
        for field in ("browser_action", "transform_args", "network_url_pattern",
                      "repeat_columns", "repeat_rows", "value_format", "value_source"):
            assert field in COPYABLE_STEP_FIELDS


class TestNestRepeatChildren:
    def test_children_nested_and_ids_stripped(self):
        flat = [
            {"id": "p1", "sort": 3, "step_type": "navigation", "instruction": "after"},
            {"id": "c1", "sort": 2, "step_type": "navigation", "instruction": "child", "parent_step_id": "r1"},
            {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "L", "repeat_columns": ["a"], "repeat_rows": [["1"]]},
        ]
        assert nest_repeat_children(flat) == [
            {"sort": 1, "step_type": "repeat", "instruction": "L", "repeat_columns": ["a"], "repeat_rows": [["1"]],
             "steps": [{"sort": 2, "step_type": "navigation", "instruction": "child"}]},
            {"sort": 3, "step_type": "navigation", "instruction": "after"},
        ]

    def test_orphan_child_stays_top_level(self):
        flat = [{"id": "c1", "sort": 1, "step_type": "navigation", "instruction": "x", "parent_step_id": "ghost"}]
        assert nest_repeat_children(flat) == [{"sort": 1, "step_type": "navigation", "instruction": "x"}]

    def test_empty_repeat_has_empty_steps(self):
        flat = [{"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "L"}]
        assert nest_repeat_children(flat)[0]["steps"] == []


class TestFlattenImportedSteps:
    def test_nested_shape(self):
        steps = [
            {"step_type": "repeat", "instruction": "L", "steps": [
                {"step_type": "navigation", "instruction": "c1", "sort": 99},
                {"step_type": "validation", "instruction": "c2"},
            ]},
            {"step_type": "navigation", "instruction": "after"},
        ]
        flat = flatten_imported_steps(steps)
        assert [(s["instruction"], p) for s, p in flat] == [("L", None), ("c1", 0), ("c2", 0), ("after", None)]
        assert "steps" not in flat[0][0]

    def test_flat_shape_with_ids(self):
        steps = [
            {"id": "old-r", "step_type": "repeat", "instruction": "L"},
            {"id": "old-c", "step_type": "navigation", "instruction": "c", "parent_step_id": "old-r"},
        ]
        flat = flatten_imported_steps(steps)
        assert [p for _, p in flat] == [None, 0]

    def test_steps_under_non_repeat_rejected(self):
        with pytest.raises(StepTreeError, match="only repeat"):
            flatten_imported_steps([{"step_type": "navigation", "instruction": "x", "steps": [{}]}])

    def test_nested_repeat_rejected(self):
        with pytest.raises(StepTreeError, match="one level"):
            flatten_imported_steps([{"step_type": "repeat", "instruction": "L", "steps": [
                {"step_type": "repeat", "instruction": "inner"},
            ]}])

    def test_flat_unknown_parent_rejected(self):
        with pytest.raises(StepTreeError, match="does not exist"):
            flatten_imported_steps([{"step_type": "navigation", "instruction": "c", "parent_step_id": "ghost"}])

    def test_flat_parent_not_repeat_rejected(self):
        with pytest.raises(StepTreeError, match="not a repeat"):
            flatten_imported_steps([
                {"id": "n", "step_type": "navigation", "instruction": "n"},
                {"id": "c", "step_type": "navigation", "instruction": "c", "parent_step_id": "n"},
            ])


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _usecase_item():
    return {
        "pk": "USECASES", "sk": "USECASE#uc-1", "name": "Login", "description": "",
        "starting_url": "https://e.test/", "executing_region": "us-east-1", "active": True, "tags": [],
    }


def _export(step_items):
    import export_usecase

    table_mock = MagicMock()
    table_mock.get_item.side_effect = lambda Key: {"Item": _usecase_item()} if Key["sk"] == "USECASE#uc-1" else {}
    table_mock.query.return_value = {"Items": step_items}
    dynamodb_mock = MagicMock()
    dynamodb_mock.Table.return_value = table_mock
    secrets_mock = MagicMock()
    secrets_mock.list_secrets.return_value = {"SecretList": []}
    event = make_event("editor_a", path={"id": "uc-1"}, scopes="api/usecases.read")
    with patch("export_usecase.boto3") as boto_mock, resource_access_granted():
        boto_mock.resource.return_value = dynamodb_mock
        boto_mock.client.return_value = secrets_mock
        response = export_usecase.handler(event, None)
    assert response["statusCode"] == 200, response["body"]
    return json.loads(response["body"])


def _import(body):
    import import_usecase

    captured = []

    class _FakeTable:
        """Write-only on purpose: ``import_usecase`` has no ``dynamodb:GetItem``
        in its IAM policy, so any read here must fail the test."""

        def put_item(self, **kwargs):
            captured.append(kwargs["Item"])

    def _fake_resource(_service):
        m = MagicMock()
        m.Table.return_value = _FakeTable()
        return m

    # Top-level application_id is required by the app_from_body resolver; the
    # owner lookups it (and new_usecase_owner_fields) make are patched, so the
    # table stays write-only.
    event = make_event("editor_a", body={**body, "application_id": APP_ID}, scopes="api/usecases.write")
    with patch("import_usecase.boto3") as boto_mock, resource_access_granted():
        boto_mock.resource.side_effect = _fake_resource
        response = import_usecase.handler(event, None)
    return response, captured


STEP_ITEMS = [
    {"pk": "USECASE#uc-1", "sk": "STEP#r1", "id": "r1", "sort": 1, "step_type": "repeat",
     "instruction": "Login as each user", "repeat_columns": ["email", "role"],
     "repeat_rows": [["a@x.test", "admin"], ["b@x.test", "viewer"]]},
    {"pk": "USECASE#uc-1", "sk": "STEP#c1", "id": "c1", "sort": 2, "step_type": "browser",
     "instruction": "Open login", "browser_action": "navigate", "browser_args": '{"url": "https://e.test/login"}',
     "parent_step_id": "r1"},
    {"pk": "USECASE#uc-1", "sk": "STEP#c2", "id": "c2", "sort": 3, "step_type": "assertion",
     "instruction": "Role matches", "assertion_variable": "role", "validation_type": "string",
     "validation_operator": "exact", "validation_value": "admin", "parent_step_id": "r1"},
    {"pk": "USECASE#uc-1", "sk": "STEP#p1", "id": "p1", "sort": 4, "step_type": "navigation",
     "instruction": "Log out"},
]


class TestExportNestedShape:
    def test_children_nested_under_repeat(self):
        body = _export(STEP_ITEMS)
        assert body["exportVersion"] == "1.0"
        steps = body["steps"]
        assert [s["step_type"] for s in steps] == ["repeat", "navigation"]
        repeat = steps[0]
        assert repeat["repeat_columns"] == ["email", "role"]
        assert repeat["repeat_rows"] == [["a@x.test", "admin"], ["b@x.test", "viewer"]]
        assert [c["instruction"] for c in repeat["steps"]] == ["Open login", "Role matches"]
        assert repeat["steps"][0]["browser_action"] == "navigate"
        for step in steps + repeat["steps"]:
            assert "id" not in step and "parent_step_id" not in step

    def test_export_without_repeat_has_no_steps_key(self):
        body = _export([STEP_ITEMS[3]])
        assert body["steps"] == [{"sort": 4, "instruction": "Log out", "step_type": "navigation"}]


class TestImportNestedShape:
    def _body(self, steps):
        return {
            "exportVersion": "1.0", "exportedAt": "2026-01-01T00:00:00Z",
            "usecase": {"name": "Login", "starting_url": "https://e.test/", "tags": []},
            "steps": steps,
        }

    def test_import_flattens_and_remaps_parent(self):
        response, captured = _import(self._body(_export(STEP_ITEMS)["steps"]))
        assert response["statusCode"] == 200, response["body"]
        steps = sorted([i for i in captured if i["sk"].startswith("STEP#")], key=lambda s: s["sort"])
        assert [s["step_type"] for s in steps] == ["repeat", "browser", "assertion", "navigation"]
        assert [s["sort"] for s in steps] == [1, 2, 3, 4]
        repeat = steps[0]
        assert repeat["repeat_columns"] == ["email", "role"]
        assert repeat["repeat_rows"] == [["a@x.test", "admin"], ["b@x.test", "viewer"]]
        assert "parent_step_id" not in repeat
        assert steps[1]["parent_step_id"] == repeat["id"]
        assert steps[2]["parent_step_id"] == repeat["id"]
        assert "parent_step_id" not in steps[3]
        assert steps[1]["browser_action"] == "navigate"
        assert steps[2]["assertion_variable"] == "role"

    def test_round_trip_is_stable(self):
        exported = _export(STEP_ITEMS)
        _, captured = _import(self._body(exported["steps"]))
        reimported_items = [i for i in captured if i["sk"].startswith("STEP#")]
        assert _export(reimported_items)["steps"] == exported["steps"]

    def test_invalid_repeat_dataset_is_400_before_any_write(self):
        steps = [{"step_type": "repeat", "instruction": "L", "repeat_columns": ["1bad"],
                  "repeat_rows": [["x"]], "steps": [{"step_type": "navigation", "instruction": "c"}]}]
        response, captured = _import(self._body(steps))
        assert response["statusCode"] == 400
        assert "identifier" in json.loads(response["body"])["message"]
        assert captured == []

    def test_nested_repeat_is_400(self):
        steps = [{"step_type": "repeat", "instruction": "L", "repeat_columns": ["a"], "repeat_rows": [["x"]],
                  "steps": [{"step_type": "repeat", "instruction": "inner", "repeat_columns": ["b"], "repeat_rows": [["y"]]}]}]
        response, captured = _import(self._body(steps))
        assert response["statusCode"] == 400
        assert captured == []

    def test_steps_under_plain_step_is_400(self):
        steps = [{"step_type": "navigation", "instruction": "x", "steps": [{"step_type": "navigation", "instruction": "y"}]}]
        response, _ = _import(self._body(steps))
        assert response["statusCode"] == 400

    def test_duplicate_repeat_labels_is_400(self):
        child = [{"step_type": "navigation", "instruction": "c"}]
        steps = [
            {"step_type": "repeat", "instruction": "Same", "repeat_columns": ["a"], "repeat_rows": [["x"]], "steps": child},
            {"step_type": "repeat", "instruction": "Same", "repeat_columns": ["a"], "repeat_rows": [["x"]], "steps": child},
        ]
        response, _ = _import(self._body(steps))
        assert response["statusCode"] == 400
        assert "unique" in json.loads(response["body"])["message"]

    def test_plain_export_imports_unchanged(self):
        steps = [
            {"sort": 1, "step_type": "navigation", "instruction": "a"},
            {"sort": 2, "step_type": "validation", "instruction": "b", "validation_type": "string",
             "validation_operator": "exact", "validation_value": "ok"},
        ]
        response, captured = _import(self._body(steps))
        assert response["statusCode"] == 200
        items = sorted([i for i in captured if i["sk"].startswith("STEP#")], key=lambda s: s["sort"])
        assert [i["instruction"] for i in items] == ["a", "b"]
        assert items[1]["validation_value"] == "ok"
        for item in items:
            assert "parent_step_id" not in item and "repeat_columns" not in item
