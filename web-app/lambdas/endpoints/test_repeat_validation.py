"""Tests for ``repeat_validation.py`` — the rules shared by create/update/import."""
import json
import os

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

from repeat_validation import (  # noqa: E402
    DATASET_NOT_SUPPORTED_IN_TEMPLATES_ERROR,
    MAX_REPEAT_COLUMNS,
    MAX_REPEAT_DATASET_BYTES,
    MAX_REPEAT_ROWS,
    REPEAT_BOTH_SOURCES_ERROR,
    REPEAT_NO_SOURCE_ERROR,
    RESERVED_COLUMN_NAMES,
    needs_sibling_validation,
    template_step_dataset_error,
    template_step_repeat_error,
    validate_repeat_fields,
)


def _repeat(**overrides) -> dict:
    step = {
        "id": "r1",
        "step_type": "repeat",
        "instruction": "Login as each user",
        "repeat_columns": ["email", "role"],
        "repeat_rows": [["a@x.test", "admin"], ["b@x.test", "viewer"]],
    }
    step.update(overrides)
    return step


def _child(**overrides) -> dict:
    step = {
        "id": "c1",
        "step_type": "navigation",
        "instruction": "Type {{email}}",
        "parent_step_id": "r1",
    }
    step.update(overrides)
    return step


class TestRepeatColumns:
    def test_valid_repeat_has_no_errors(self):
        assert validate_repeat_fields(_repeat(), []) == []

    def test_columns_required(self):
        errors = validate_repeat_fields(_repeat(repeat_columns=None), [])
        assert any("repeat_columns" in e for e in errors)

    def test_columns_must_be_list_of_strings(self):
        errors = validate_repeat_fields(_repeat(repeat_columns=["email", 3], repeat_rows=[["a", "b"]]), [])
        assert any("repeat_columns" in e for e in errors)

    def test_empty_columns_rejected(self):
        errors = validate_repeat_fields(_repeat(repeat_columns=[], repeat_rows=[[]]), [])
        assert any("at least 1" in e for e in errors)

    def test_too_many_columns_rejected(self):
        cols = [f"c{i}" for i in range(MAX_REPEAT_COLUMNS + 1)]
        errors = validate_repeat_fields(_repeat(repeat_columns=cols, repeat_rows=[["x"] * len(cols)]), [])
        assert any(f"at most {MAX_REPEAT_COLUMNS}" in e for e in errors)

    @pytest.mark.parametrize("bad", ["1abc", "has space", "dash-ed", "", "ümlaut"])
    def test_identifier_regex(self, bad):
        errors = validate_repeat_fields(_repeat(repeat_columns=["ok", bad], repeat_rows=[["a", "b"]]), [])
        assert any("identifier" in e for e in errors), errors

    def test_duplicate_columns_rejected(self):
        errors = validate_repeat_fields(_repeat(repeat_columns=["email", "email"]), [])
        assert any("unique" in e for e in errors)

    @pytest.mark.parametrize("name", sorted(RESERVED_COLUMN_NAMES))
    def test_reserved_names_rejected(self, name):
        errors = validate_repeat_fields(_repeat(repeat_columns=[name], repeat_rows=[["x"]]), [])
        assert any("reserved" in e for e in errors)


class TestRepeatRows:
    def test_rows_required(self):
        errors = validate_repeat_fields(_repeat(repeat_rows=None), [])
        assert any("repeat_rows" in e for e in errors)

    def test_empty_rows_rejected(self):
        errors = validate_repeat_fields(_repeat(repeat_rows=[]), [])
        assert any("at least 1 row" in e for e in errors)

    def test_too_many_rows_rejected(self):
        rows = [["a", "b"]] * (MAX_REPEAT_ROWS + 1)
        errors = validate_repeat_fields(_repeat(repeat_rows=rows), [])
        assert any(f"at most {MAX_REPEAT_ROWS} rows" in e for e in errors)

    def test_row_length_must_match_columns(self):
        errors = validate_repeat_fields(_repeat(repeat_rows=[["a", "b"], ["only-one"]]), [])
        assert any("row 2" in e and "2 cells" in e for e in errors)

    def test_cells_must_be_strings(self):
        errors = validate_repeat_fields(_repeat(repeat_rows=[["a", 1]]), [])
        assert any("string" in e for e in errors)

    def test_row_must_be_list(self):
        errors = validate_repeat_fields(_repeat(repeat_rows=["not-a-list"]), [])
        assert any("row 1" in e for e in errors)

    def test_dataset_size_cap(self):
        big_cell = "x" * (MAX_REPEAT_DATASET_BYTES // 2 + 10)
        errors = validate_repeat_fields(
            _repeat(repeat_columns=["a", "b"], repeat_rows=[[big_cell, big_cell]]), [],
        )
        assert any("200 KB" in e or str(MAX_REPEAT_DATASET_BYTES) in e for e in errors)

    def test_dataset_size_just_under_cap_passes(self):
        cols = ["a"]
        cell_len = MAX_REPEAT_DATASET_BYTES - len(json.dumps(cols)) - len(json.dumps([[""]])) - 1
        rows = [["x" * cell_len]]
        assert len(json.dumps(cols)) + len(json.dumps(rows)) <= MAX_REPEAT_DATASET_BYTES
        assert validate_repeat_fields(_repeat(repeat_columns=cols, repeat_rows=rows), []) == []


class TestRepeatLabel:
    def test_label_unique_among_repeats(self):
        other = _repeat(id="r2", instruction="Login as each user")
        errors = validate_repeat_fields(_repeat(), [other])
        assert any("label" in e and "unique" in e for e in errors)

    def test_same_label_on_self_is_fine_when_updating(self):
        existing = _repeat()
        assert validate_repeat_fields(_repeat(), [existing]) == []

    def test_same_label_on_non_repeat_is_fine(self):
        other = {"id": "n1", "step_type": "navigation", "instruction": "Login as each user"}
        assert validate_repeat_fields(_repeat(), [other]) == []

    def test_repeat_cannot_have_parent(self):
        errors = validate_repeat_fields(_repeat(parent_step_id="r0"), [_repeat(id="r0", instruction="outer")])
        assert any("nested" in e or "parent_step_id" in e for e in errors)


class TestParentStepId:
    def test_valid_child(self):
        assert validate_repeat_fields(_child(), [_repeat()]) == []

    def test_parent_must_exist(self):
        errors = validate_repeat_fields(_child(parent_step_id="missing"), [_repeat()])
        assert any("does not exist" in e for e in errors)

    def test_parent_must_be_repeat(self):
        parent = {"id": "n1", "step_type": "navigation", "instruction": "x"}
        errors = validate_repeat_fields(_child(parent_step_id="n1"), [parent])
        assert any("not a repeat" in e for e in errors)

    def test_parent_may_not_itself_be_nested(self):
        parent = _repeat(parent_step_id="r0")
        errors = validate_repeat_fields(_child(), [parent, _repeat(id="r0", instruction="outer")])
        assert any("one level" in e for e in errors)

    def test_parent_step_id_must_be_string(self):
        errors = validate_repeat_fields(_child(parent_step_id=5), [_repeat()])
        assert any("parent_step_id" in e for e in errors)

    def test_non_repeat_without_parent_ignores_repeat_fields(self):
        step = {"id": "n1", "step_type": "navigation", "instruction": "x"}
        assert validate_repeat_fields(step, []) == []

    def test_non_repeat_with_repeat_columns_rejected(self):
        step = {"id": "n1", "step_type": "navigation", "instruction": "x", "repeat_columns": ["a"]}
        errors = validate_repeat_fields(step, [])
        assert any("only allowed" in e for e in errors)


class TestDatasetReference:
    """A repeat step carries ``dataset_id`` *or* inline rows — never both, never neither."""

    def test_dataset_id_alone_is_valid(self):
        step = _repeat(repeat_columns=None, repeat_rows=None, dataset_id="ds-1")
        assert validate_repeat_fields(step, []) == []

    def test_dataset_id_with_inline_rows_rejected(self):
        errors = validate_repeat_fields(_repeat(dataset_id="ds-1"), [])
        assert errors == [REPEAT_BOTH_SOURCES_ERROR]

    def test_dataset_id_with_only_columns_rejected_as_both(self):
        errors = validate_repeat_fields(_repeat(repeat_rows=None, dataset_id="ds-1"), [])
        assert errors == [REPEAT_BOTH_SOURCES_ERROR]

    def test_neither_source_rejected(self):
        errors = validate_repeat_fields(_repeat(repeat_columns=None, repeat_rows=None), [])
        assert errors == [REPEAT_NO_SOURCE_ERROR]

    @pytest.mark.parametrize("empty", ["", None])
    def test_blank_dataset_id_counts_as_absent(self, empty):
        assert validate_repeat_fields(_repeat(dataset_id=empty), []) == []
        errors = validate_repeat_fields(_repeat(repeat_columns=None, repeat_rows=None, dataset_id=empty), [])
        assert errors == [REPEAT_NO_SOURCE_ERROR]

    def test_dataset_id_must_be_a_string(self):
        errors = validate_repeat_fields(_repeat(repeat_columns=None, repeat_rows=None, dataset_id=7), [])
        assert errors == ["dataset_id must be a string"]

    def test_partial_inline_rows_keep_the_required_errors(self):
        assert validate_repeat_fields(_repeat(repeat_rows=None), []) == ["repeat_rows is required for repeat steps"]
        assert validate_repeat_fields(_repeat(repeat_columns=None), []) == ["repeat_columns is required for repeat steps"]

    def test_dataset_id_only_allowed_on_repeat_steps(self):
        step = {"id": "n1", "step_type": "navigation", "instruction": "x", "dataset_id": "ds-1"}
        assert validate_repeat_fields(step, []) == ["dataset_id is only allowed on repeat steps"]

    def test_exact_error_strings_are_the_cli_contract(self):
        assert REPEAT_NO_SOURCE_ERROR == "repeat step must have either dataset_id or repeat_columns/repeat_rows"
        assert REPEAT_BOTH_SOURCES_ERROR == "repeat step cannot have both dataset_id and inline rows"

    def test_label_uniqueness_still_checked_for_dataset_repeats(self):
        step = _repeat(repeat_columns=None, repeat_rows=None, dataset_id="ds-1")
        errors = validate_repeat_fields(step, [_repeat(id="r2")])
        assert any("unique" in e for e in errors)

    def test_needs_sibling_validation_for_dataset_id(self):
        assert needs_sibling_validation({"step_type": "navigation", "dataset_id": "ds-1"})
        assert not needs_sibling_validation({"step_type": "navigation"})


class TestTemplateGuards:
    def test_template_step_dataset_error(self):
        assert template_step_dataset_error({"step_type": "navigation", "dataset_id": "ds-1"}) == (
            DATASET_NOT_SUPPORTED_IN_TEMPLATES_ERROR
        )
        assert template_step_dataset_error({"step_type": "navigation"}) is None
        assert template_step_dataset_error({"step_type": "navigation", "dataset_id": ""}) is None

    def test_template_step_repeat_error_unchanged(self):
        assert template_step_repeat_error({"step_type": "repeat"}) is not None
        assert template_step_repeat_error({"step_type": "navigation"}) is None
