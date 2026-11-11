"""``dataset_models`` — the ``APPLICATION#{id} / DATASET#{id}`` record, its request models and read helpers."""
import os

import pytest
from pydantic import ValidationError

os.environ.setdefault("TABLE_NAME", "test-table")

import repeat_validation  # noqa: E402
from dataset_models import (  # noqa: E402
    DATASET_SK_PREFIX,
    ApplicationDataset,
    ApplicationDatasetCreate,
    ApplicationDatasetUpdate,
    dataset_name_errors,
    dataset_sk,
    find_name_conflict,
    get_dataset,
    list_datasets,
    validate_dataset_request,
)
from fake_table import FakeTable  # noqa: E402

APP = "app-1"
VALID_BODY = {"name": "customers", "description": "", "columns": ["first", "last"],
              "rows": [["Ada", "Lovelace"], ["Alan", "Turing"]]}


def _item(dataset_id="ds-1", name="customers", app_id=APP, **extra):
    item = {
        "pk": f"APPLICATION#{app_id}", "sk": f"DATASET#{dataset_id}", "dataset_id": dataset_id,
        "name": name, "description": "d", "columns": ["a"], "rows": [["1"], ["2"]],
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z", "created_by": "qa@example.com",
    }
    item.update(extra)
    return item


class TestNameRules:
    @pytest.mark.parametrize("name", ["customers", "_private", "Customers 2026", "a-b_c", "x" * 64])
    def test_valid_names(self, name):
        assert dataset_name_errors(name) == []

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_blank_name_is_required(self, name):
        assert dataset_name_errors(name) == ["name is required"]

    @pytest.mark.parametrize("name", ["1abc", "-abc", "a.b", "a/b", "x" * 65, "ünï"])
    def test_invalid_names_report_pattern(self, name):
        errors = dataset_name_errors(name)
        assert len(errors) == 1
        assert errors[0].startswith(f'dataset name "{name}" is invalid')

    def test_surrounding_whitespace_is_stripped_before_the_pattern_check(self):
        assert dataset_name_errors("  abc ") == []

    def test_non_string_name(self):
        assert dataset_name_errors(42) == ["name must be a string"]


class TestValidateDatasetRequest:
    def test_valid_body_has_no_errors(self):
        assert validate_dataset_request(VALID_BODY) == []

    def test_repeat_validation_errors_are_returned_verbatim(self):
        body = {**VALID_BODY, "columns": ["UniqueID", "1bad"], "rows": [["a"]]}
        expected = repeat_validation.validate_dataset(body["columns"], body["rows"])
        assert expected  # the rule set itself produces errors for this input
        assert validate_dataset_request(body) == expected

    def test_name_errors_come_first(self):
        body = {**VALID_BODY, "name": "1bad", "columns": "nope", "rows": []}
        errors = validate_dataset_request(body)
        assert errors[0].startswith('dataset name "1bad" is invalid')
        assert "repeat_columns must be a list of strings" in errors

    def test_missing_columns_and_rows(self):
        errors = validate_dataset_request({"name": "ok"})
        assert "repeat_columns must be a list of strings" in errors

    def test_non_dict_body(self):
        assert validate_dataset_request([]) == ["request body must be a JSON object"]


class TestRequestModels:
    def test_create_strips_name_and_defaults_description(self):
        model = ApplicationDatasetCreate(**{**VALID_BODY, "name": "  customers "})
        assert model.name == "customers"
        assert model.description == ""

    def test_update_is_the_same_shape(self):
        model = ApplicationDatasetUpdate(**VALID_BODY)
        assert model.columns == ["first", "last"]
        assert model.rows == [["Ada", "Lovelace"], ["Alan", "Turing"]]

    def test_rows_must_be_lists_of_strings(self):
        with pytest.raises(ValidationError):
            ApplicationDatasetCreate(**{**VALID_BODY, "rows": [[1, 2]]})

    def test_description_is_optional_but_typed(self):
        with pytest.raises(ValidationError):
            ApplicationDatasetCreate(**{**VALID_BODY, "description": 3})


class TestRecordModel:
    def test_from_item_drops_keys_and_round_trips(self):
        dataset = ApplicationDataset.from_item(_item())
        assert dataset.dataset_id == "ds-1"
        assert dataset.columns == ["a"]
        item = dataset.to_item(APP)
        assert item["pk"] == f"APPLICATION#{APP}"
        assert item["sk"] == "DATASET#ds-1"
        assert item == _item()

    def test_summary_has_counts_not_rows(self):
        summary = ApplicationDataset.from_item(_item()).summary()
        assert summary == {
            "dataset_id": "ds-1", "name": "customers", "description": "d",
            "column_count": 1, "row_count": 2, "updated_at": "2026-01-02T00:00:00Z",
        }

    def test_from_item_tolerates_missing_optional_attributes(self):
        item = _item()
        del item["description"]
        del item["created_by"]
        dataset = ApplicationDataset.from_item(item)
        assert dataset.description == ""
        assert dataset.created_by == ""


class TestReadHelpers:
    def test_dataset_sk(self):
        assert DATASET_SK_PREFIX == "DATASET#"
        assert dataset_sk("ds-1") == "DATASET#ds-1"

    def test_get_dataset_scoped_to_application(self):
        table = FakeTable([_item(), _item(app_id="other")])
        assert get_dataset(table, APP, "ds-1")["name"] == "customers"
        assert get_dataset(table, APP, "missing") is None
        assert get_dataset(table, "third", "ds-1") is None

    def test_list_datasets_only_dataset_records_of_the_application(self):
        table = FakeTable([
            _item("ds-1", "b"), _item("ds-2", "a"), _item("ds-9", "z", app_id="other"),
            {"pk": f"APPLICATION#{APP}", "sk": "METADATA", "name": "App"},
            {"pk": f"APPLICATION#{APP}", "sk": "USECASE#uc-1"},
        ])
        names = [d["name"] for d in list_datasets(table, APP)]
        assert names == ["a", "b"]  # sorted by name

    def test_find_name_conflict_is_case_insensitive_and_can_exclude_self(self):
        datasets = [_item("ds-1", "Customers"), _item("ds-2", "orders")]
        assert find_name_conflict(datasets, "customers")["dataset_id"] == "ds-1"
        assert find_name_conflict(datasets, "CUSTOMERS", exclude_dataset_id="ds-1") is None
        assert find_name_conflict(datasets, "orders", exclude_dataset_id="ds-1")["dataset_id"] == "ds-2"
        assert find_name_conflict(datasets, "new") is None
