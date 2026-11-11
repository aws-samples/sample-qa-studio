"""Application dataset routes (``/applications/{id}/datasets[/{datasetId}]``) on the application router.

Covers every route against ``FakeTable``: list summaries, create (201), get,
full-replace update, delete (204 / 409 with referencing use cases), name
uniqueness (case-insensitive, rename-aware), verbatim ``repeat_validation``
errors as ``{errors: [...]}`` and scope / access enforcement through
``app_from_path``.
"""
import json
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

import repeat_validation  # noqa: E402
from authz_test_support import APP_ID, make_event, owned_resources  # noqa: E402
from fake_table import FakeTable  # noqa: E402
from handlers import (  # noqa: E402
    create_application_dataset,
    delete_application_dataset,
    get_application_dataset,
    list_application_datasets,
    update_application_dataset,
)

READ = "api/applications.read"
WRITE = "api/applications.write"

VALID_BODY = {"name": "customers", "description": "Test customers",
              "columns": ["first_name", "email"], "rows": [["Ada", "ada@x.test"], ["Alan", "alan@x.test"]]}


def _dataset(dataset_id="ds-1", name="customers", app_id=APP_ID, **extra):
    item = {
        "pk": f"APPLICATION#{app_id}", "sk": f"DATASET#{dataset_id}", "dataset_id": dataset_id,
        "name": name, "description": "d", "columns": ["a"], "rows": [["1"], ["2"]],
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z", "created_by": "qa@example.com",
    }
    item.update(extra)
    return item


@pytest.fixture(autouse=True)
def _app_owned():
    """APP_ID belongs to TEAM_A (editor_a may edit, viewer_a may view, editor_b sees 403/404)."""
    with owned_resources():
        yield


def _run(module, table, caller="editor_a", scopes=WRITE, dataset_id=None, body=None):
    path = {"id": APP_ID}
    if dataset_id is not None:
        path["datasetId"] = dataset_id
    event = make_event(caller=caller, path=path, body=body, scopes=scopes)
    with patch.object(module, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        return module.handle(event)


def _body(response):
    return json.loads(response["body"])


# ---------------------------------------------------------------------------
# GET /applications/{id}/datasets
# ---------------------------------------------------------------------------


class TestList:
    def test_returns_summaries_sorted_by_name(self):
        table = FakeTable([
            _dataset("ds-1", "orders"), _dataset("ds-2", "customers"),
            _dataset("ds-9", "elsewhere", app_id="app-b"),
            {"pk": f"APPLICATION#{APP_ID}", "sk": "METADATA", "name": "App"},
            {"pk": f"APPLICATION#{APP_ID}", "sk": "USECASE#uc-1"},
        ])
        response = _run(list_application_datasets, table, caller="viewer_a", scopes=READ)
        assert response["statusCode"] == 200
        datasets = _body(response)["datasets"]
        assert [d["name"] for d in datasets] == ["customers", "orders"]
        assert datasets[0] == {
            "dataset_id": "ds-2", "name": "customers", "description": "d",
            "column_count": 1, "row_count": 2, "updated_at": "2026-01-02T00:00:00Z",
        }
        assert "rows" not in datasets[0]

    def test_empty(self):
        response = _run(list_application_datasets, FakeTable(), caller="viewer_a", scopes=READ)
        assert response["statusCode"] == 200
        assert _body(response) == {"datasets": []}

    def test_requires_read_scope(self):
        response = _run(list_application_datasets, FakeTable(), caller="viewer_a", scopes=WRITE)
        assert response["statusCode"] == 403

    def test_other_team_cannot_view(self):
        response = _run(list_application_datasets, FakeTable(), caller="viewer_b", scopes=READ)
        assert response["statusCode"] in (403, 404)


# ---------------------------------------------------------------------------
# POST /applications/{id}/datasets
# ---------------------------------------------------------------------------


class TestCreate:
    @patch("handlers.create_application_dataset.generate_uuid7", return_value="ds-new")
    @patch("handlers.create_application_dataset.get_current_timestamp", return_value="2026-05-01T00:00:00Z")
    def test_creates_record_and_returns_201(self, _ts, _uuid):
        table = FakeTable()
        response = _run(create_application_dataset, table, body=VALID_BODY)
        assert response["statusCode"] == 201, response["body"]
        dataset = _body(response)["dataset"]
        assert dataset == {
            "dataset_id": "ds-new", "name": "customers", "description": "Test customers",
            "columns": ["first_name", "email"], "rows": [["Ada", "ada@x.test"], ["Alan", "alan@x.test"]],
            "created_at": "2026-05-01T00:00:00Z", "updated_at": "2026-05-01T00:00:00Z",
            "created_by": "editor_a@example.com",
        }
        item = table.get(f"APPLICATION#{APP_ID}", "DATASET#ds-new")
        assert item is not None
        assert item["columns"] == ["first_name", "email"]
        assert item["created_by"] == "editor_a@example.com"

    def test_description_optional_and_name_stripped(self):
        table = FakeTable()
        body = {k: v for k, v in VALID_BODY.items() if k != "description"}
        response = _run(create_application_dataset, table, body={**body, "name": "  customers "})
        assert response["statusCode"] == 201, response["body"]
        dataset = _body(response)["dataset"]
        assert dataset["name"] == "customers"
        assert dataset["description"] == ""

    def test_repeat_validation_errors_verbatim(self):
        table = FakeTable()
        body = {**VALID_BODY, "columns": ["UniqueID", "1bad"], "rows": [["a"]]}
        response = _run(create_application_dataset, table, body=body)
        assert response["statusCode"] == 400
        payload = _body(response)
        assert payload["errors"] == repeat_validation.validate_dataset(body["columns"], body["rows"])
        assert payload["error"] == "; ".join(payload["errors"])
        assert table.put_calls == []

    @pytest.mark.parametrize("name,fragment", [
        ("", "name is required"),
        ("1customers", 'dataset name "1customers" is invalid'),
        ("x" * 65, "is invalid"),
    ])
    def test_name_rules(self, name, fragment):
        response = _run(create_application_dataset, FakeTable(), body={**VALID_BODY, "name": name})
        assert response["statusCode"] == 400
        assert any(fragment in e for e in _body(response)["errors"])

    def test_too_large_dataset_rejected(self):
        rows = [["x" * 2100] for _ in range(100)]  # > 200 KB serialized
        response = _run(create_application_dataset, FakeTable(), body={**VALID_BODY, "columns": ["c"], "rows": rows})
        assert response["statusCode"] == 400
        assert any("too large" in e for e in _body(response)["errors"])

    def test_duplicate_name_case_insensitive_409(self):
        table = FakeTable([_dataset("ds-1", "Customers")])
        response = _run(create_application_dataset, table, body=VALID_BODY)
        assert response["statusCode"] == 409
        assert _body(response)["error"] == 'a dataset named "customers" already exists in this application'
        assert len(table.by_prefix(f"APPLICATION#{APP_ID}", "DATASET#")) == 1

    def test_same_name_in_other_application_is_fine(self):
        table = FakeTable([_dataset("ds-1", "customers", app_id="app-b")])
        response = _run(create_application_dataset, table, body=VALID_BODY)
        assert response["statusCode"] == 201

    def test_invalid_json(self):
        response = _run(create_application_dataset, FakeTable(), body="{not json")
        assert response["statusCode"] == 400
        assert _body(response)["error"] == "Invalid JSON in request body"

    def test_non_object_body(self):
        response = _run(create_application_dataset, FakeTable(), body=[1, 2])
        assert response["statusCode"] == 400
        assert "request body must be a JSON object" in _body(response)["errors"]

    def test_requires_write_scope(self):
        response = _run(create_application_dataset, FakeTable(), scopes=READ, body=VALID_BODY)
        assert response["statusCode"] == 403

    def test_viewer_cannot_create(self):
        response = _run(create_application_dataset, FakeTable(), caller="viewer_a", body=VALID_BODY)
        assert response["statusCode"] == 403

    def test_other_team_cannot_create(self):
        response = _run(create_application_dataset, FakeTable(), caller="editor_b", body=VALID_BODY)
        assert response["statusCode"] in (403, 404)

    def test_unknown_application_404(self):
        event = make_event(caller="admin", path={"id": "nonexistent-app"}, body=VALID_BODY, scopes=WRITE)
        with patch.object(create_application_dataset, "boto3") as boto_mock:
            boto_mock.resource.return_value.Table.return_value = FakeTable()
            response = create_application_dataset.handle(event)
        assert response["statusCode"] == 404


# ---------------------------------------------------------------------------
# GET /applications/{id}/datasets/{datasetId}
# ---------------------------------------------------------------------------


class TestGet:
    def test_returns_full_dataset(self):
        table = FakeTable([_dataset()])
        response = _run(get_application_dataset, table, caller="viewer_a", scopes=READ, dataset_id="ds-1")
        assert response["statusCode"] == 200
        dataset = _body(response)["dataset"]
        assert dataset["dataset_id"] == "ds-1"
        assert dataset["columns"] == ["a"]
        assert dataset["rows"] == [["1"], ["2"]]
        assert "pk" not in dataset and "sk" not in dataset

    def test_404_when_missing(self):
        response = _run(get_application_dataset, FakeTable(), caller="viewer_a", scopes=READ, dataset_id="ds-1")
        assert response["statusCode"] == 404
        assert _body(response)["error"] == "Dataset not found"

    def test_404_when_dataset_belongs_to_other_application(self):
        table = FakeTable([_dataset(app_id="app-b")])
        response = _run(get_application_dataset, table, caller="viewer_a", scopes=READ, dataset_id="ds-1")
        assert response["statusCode"] == 404

    def test_invalid_dataset_id_400(self):
        response = _run(get_application_dataset, FakeTable(), caller="viewer_a", scopes=READ, dataset_id="../x")
        assert response["statusCode"] == 400

    def test_requires_read_scope(self):
        response = _run(get_application_dataset, FakeTable([_dataset()]), caller="viewer_a", scopes=WRITE,
                        dataset_id="ds-1")
        assert response["statusCode"] == 403


# ---------------------------------------------------------------------------
# PUT /applications/{id}/datasets/{datasetId}
# ---------------------------------------------------------------------------


class TestUpdate:
    @patch("handlers.update_application_dataset.get_current_timestamp", return_value="2026-06-01T00:00:00Z")
    def test_full_replace_keeps_identity_and_created_fields(self, _ts):
        table = FakeTable([_dataset()])
        response = _run(update_application_dataset, table, dataset_id="ds-1", body=VALID_BODY)
        assert response["statusCode"] == 200, response["body"]
        dataset = _body(response)["dataset"]
        assert dataset == {
            "dataset_id": "ds-1", "name": "customers", "description": "Test customers",
            "columns": ["first_name", "email"], "rows": [["Ada", "ada@x.test"], ["Alan", "alan@x.test"]],
            "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-06-01T00:00:00Z",
            "created_by": "qa@example.com",
        }
        item = table.get(f"APPLICATION#{APP_ID}", "DATASET#ds-1")
        assert item["rows"] == [["Ada", "ada@x.test"], ["Alan", "alan@x.test"]]
        assert item["created_at"] == "2026-01-01T00:00:00Z"

    def test_rename_to_other_datasets_name_409(self):
        table = FakeTable([_dataset("ds-1", "customers"), _dataset("ds-2", "Orders")])
        response = _run(update_application_dataset, table, dataset_id="ds-1", body={**VALID_BODY, "name": "orders"})
        assert response["statusCode"] == 409
        assert table.get(f"APPLICATION#{APP_ID}", "DATASET#ds-1")["name"] == "customers"

    def test_keeping_own_name_is_not_a_conflict(self):
        table = FakeTable([_dataset("ds-1", "Customers"), _dataset("ds-2", "orders")])
        response = _run(update_application_dataset, table, dataset_id="ds-1", body=VALID_BODY)
        assert response["statusCode"] == 200, response["body"]

    def test_404_when_missing(self):
        response = _run(update_application_dataset, FakeTable(), dataset_id="ds-1", body=VALID_BODY)
        assert response["statusCode"] == 404

    def test_validation_errors_verbatim(self):
        table = FakeTable([_dataset()])
        body = {**VALID_BODY, "columns": ["a"], "rows": [["1", "2"]]}
        response = _run(update_application_dataset, table, dataset_id="ds-1", body=body)
        assert response["statusCode"] == 400
        assert _body(response)["errors"] == repeat_validation.validate_dataset(["a"], [["1", "2"]])
        assert table.get(f"APPLICATION#{APP_ID}", "DATASET#ds-1")["rows"] == [["1"], ["2"]]

    def test_invalid_json(self):
        response = _run(update_application_dataset, FakeTable([_dataset()]), dataset_id="ds-1", body="{")
        assert response["statusCode"] == 400

    def test_requires_write_scope(self):
        response = _run(update_application_dataset, FakeTable([_dataset()]), scopes=READ, dataset_id="ds-1",
                        body=VALID_BODY)
        assert response["statusCode"] == 403

    def test_viewer_cannot_update(self):
        response = _run(update_application_dataset, FakeTable([_dataset()]), caller="viewer_a", dataset_id="ds-1",
                        body=VALID_BODY)
        assert response["statusCode"] == 403


# ---------------------------------------------------------------------------
# DELETE /applications/{id}/datasets/{datasetId}
# ---------------------------------------------------------------------------


def _step(usecase_id, step_id, **extra):
    item = {"pk": f"USECASE#{usecase_id}", "sk": f"STEP#{step_id}", "id": step_id, "sort": 1,
            "step_type": "repeat", "instruction": "x"}
    item.update(extra)
    return item


class TestDelete:
    def test_deletes_unreferenced_dataset_204(self):
        table = FakeTable([
            _dataset(), _dataset("ds-2", "orders"),
            {"pk": f"APPLICATION#{APP_ID}", "sk": "USECASE#uc-1"},
            _step("uc-1", "s1", repeat_columns=["a"], repeat_rows=[["1"]]),
        ])
        response = _run(delete_application_dataset, table, dataset_id="ds-1")
        assert response["statusCode"] == 204
        assert response["body"] == ""
        assert table.get(f"APPLICATION#{APP_ID}", "DATASET#ds-1") is None
        assert table.get(f"APPLICATION#{APP_ID}", "DATASET#ds-2") is not None

    def test_referenced_dataset_409_with_usecase_names(self):
        table = FakeTable([
            _dataset(),
            {"pk": f"APPLICATION#{APP_ID}", "sk": "USECASE#uc-1"},
            {"pk": f"APPLICATION#{APP_ID}", "sk": "USECASE#uc-2"},
            {"pk": "USECASES", "sk": "USECASE#uc-1", "id": "uc-1", "name": "Login"},
            {"pk": "USECASES", "sk": "USECASE#uc-2", "id": "uc-2", "name": "Checkout"},
            _step("uc-1", "s1", dataset_id="ds-1"),
            _step("uc-2", "s2", dataset_id="ds-1"),
            _step("uc-2", "s3", dataset_id="ds-1"),
        ])
        response = _run(delete_application_dataset, table, dataset_id="ds-1")
        assert response["statusCode"] == 409
        payload = _body(response)
        assert payload["usecases"] == [{"usecase_id": "uc-2", "name": "Checkout"},
                                       {"usecase_id": "uc-1", "name": "Login"}]
        assert "referenced" in payload["error"]
        assert table.get(f"APPLICATION#{APP_ID}", "DATASET#ds-1") is not None

    def test_404_when_missing(self):
        response = _run(delete_application_dataset, FakeTable(), dataset_id="ds-1")
        assert response["statusCode"] == 404

    def test_requires_write_scope(self):
        response = _run(delete_application_dataset, FakeTable([_dataset()]), scopes=READ, dataset_id="ds-1")
        assert response["statusCode"] == 403

    def test_viewer_cannot_delete(self):
        table = FakeTable([_dataset()])
        response = _run(delete_application_dataset, table, caller="viewer_a", dataset_id="ds-1")
        assert response["statusCode"] == 403
        assert table.get(f"APPLICATION#{APP_ID}", "DATASET#ds-1") is not None
