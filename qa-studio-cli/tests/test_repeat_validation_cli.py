"""CLI pre-submit validation for ``repeat`` steps + parity with the Lambda rules."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from qa_studio_cli.validation import (
    MAX_REPEAT_COLUMNS,
    MAX_REPEAT_ROWS,
    REPEAT_BOTH_SOURCES_ERROR,
    REPEAT_NO_SOURCE_ERROR,
    RESERVED_REPEAT_COLUMN_NAMES,
    validate_repeat_dataset,
    validate_repeat_step,
    validate_step,
)


def _repeat(**overrides) -> dict:
    step = {
        "step_type": "repeat",
        "instruction": "Login as each user",
        "repeat_columns": ["email", "role"],
        "repeat_rows": [["a@x.test", "admin"], ["b@x.test", "viewer"]],
    }
    step.update(overrides)
    return step


class TestValidateRepeatStep:
    def test_valid(self):
        assert validate_step(_repeat()) == (True, [])

    def test_dispatched_from_validate_step(self):
        ok, errors = validate_step(_repeat(repeat_columns=["1bad"], repeat_rows=[["x"]]))
        assert ok is False
        assert any("identifier" in e for e in errors)

    def test_columns_required(self):
        ok, errors = validate_repeat_step(_repeat(repeat_columns=None))
        assert not ok and any("repeat_columns is required" in e for e in errors)

    def test_rows_required(self):
        ok, errors = validate_repeat_step(_repeat(repeat_rows=None))
        assert not ok and any("repeat_rows is required" in e for e in errors)

    @pytest.mark.parametrize("name", sorted(RESERVED_REPEAT_COLUMN_NAMES))
    def test_reserved_names(self, name):
        ok, errors = validate_repeat_step(_repeat(repeat_columns=[name], repeat_rows=[["x"]]))
        assert not ok and any("reserved" in e for e in errors)

    def test_caps(self):
        cols = [f"c{i}" for i in range(MAX_REPEAT_COLUMNS + 1)]
        rows = [["x"] * len(cols)] * (MAX_REPEAT_ROWS + 1)
        ok, errors = validate_repeat_step(_repeat(repeat_columns=cols, repeat_rows=rows))
        assert not ok
        assert any(f"at most {MAX_REPEAT_COLUMNS} columns" in e for e in errors)
        assert any(f"at most {MAX_REPEAT_ROWS} rows" in e for e in errors)

    def test_ragged_rows(self):
        ok, errors = validate_repeat_step(_repeat(repeat_rows=[["only-one"]]))
        assert not ok and any("row 1 has 1 cells but 2 cells are expected" in e for e in errors)

    def test_size_cap(self):
        big = "x" * (200 * 1024)
        ok, errors = validate_repeat_step(_repeat(repeat_columns=["a"], repeat_rows=[[big]]))
        assert not ok and any("200 KB" in e for e in errors)

    def test_repeat_with_parent_rejected(self):
        ok, errors = validate_repeat_step(_repeat(parent_step_id="other"))
        assert not ok and any("nested" in e for e in errors)

    def test_non_repeat_steps_untouched(self):
        assert validate_step({"step_type": "navigation", "instruction": "x"}) == (True, [])


class TestDatasetReference:
    """``dataset_id`` XOR inline rows — strings are the server's (see parity below)."""

    def test_dataset_id_alone_is_valid(self):
        assert validate_repeat_step(_repeat(repeat_columns=None, repeat_rows=None, dataset_id="ds-1")) == (True, [])

    def test_both_sources_rejected(self):
        ok, errors = validate_repeat_step(_repeat(dataset_id="ds-1"))
        assert not ok and errors == [REPEAT_BOTH_SOURCES_ERROR]

    def test_neither_source_rejected(self):
        ok, errors = validate_repeat_step(_repeat(repeat_columns=None, repeat_rows=None))
        assert not ok and errors == [REPEAT_NO_SOURCE_ERROR]

    def test_blank_dataset_id_is_absent(self):
        assert validate_repeat_step(_repeat(dataset_id="")) == (True, [])

    def test_dataset_id_must_be_string(self):
        ok, errors = validate_repeat_step(_repeat(repeat_columns=None, repeat_rows=None, dataset_id=3))
        assert not ok and errors == ["dataset_id must be a string"]

    def test_dataset_id_on_plain_step_rejected_by_validate_step(self):
        ok, errors = validate_step({"step_type": "navigation", "instruction": "x", "dataset_id": "ds-1"})
        assert not ok and errors == ["dataset_id is only allowed on repeat steps"]


class TestValidateRepeatDataset:
    def test_valid(self):
        assert validate_repeat_dataset(["a"], [["1"]]) == []

    def test_errors(self):
        errors = validate_repeat_dataset(["a", "a"], [["1"]])
        assert any("unique" in e for e in errors)


# ---------------------------------------------------------------------------
# Parity with web-app/lambdas/endpoints/repeat_validation.py
# ---------------------------------------------------------------------------

def _load_lambda_module():
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "web-app" / "lambdas" / "endpoints" / "repeat_validation.py"
        if candidate.exists():
            spec = importlib.util.spec_from_file_location("_lambda_repeat_validation", candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    return None


_LAMBDA = _load_lambda_module()

_PARITY_CASES = [
    (["email", "role"], [["a", "b"]]),
    ([], [[]]),
    (["1bad", "ok"], [["a", "b"]]),
    (["UniqueID"], [["a"]]),
    (["RepeatIndex"], [["a"]]),
    (["dup", "dup"], [["a", "b"]]),
    (["a"], []),
    (["a"], [["x", "y"]]),
    (["a"], [["x"], "junk"]),
    (["a"], [[1]]),
    ([f"c{i}" for i in range(21)], [["x"] * 21]),
    (["a"], [["x"]] * 101),
    (["a"], [["x" * (200 * 1024)]]),
    ("not-a-list", [["x"]]),
    (["a"], "not-a-list"),
]


@pytest.mark.skipif(_LAMBDA is None, reason="Lambda source not present (standalone CLI install)")
@pytest.mark.parametrize("columns,rows", _PARITY_CASES, ids=[str(i) for i in range(len(_PARITY_CASES))])
def test_dataset_errors_match_lambda(columns, rows):
    assert validate_repeat_dataset(columns, rows) == _LAMBDA.validate_dataset(columns, rows)


@pytest.mark.skipif(_LAMBDA is None, reason="Lambda source not present (standalone CLI install)")
def test_constants_match_lambda():
    assert MAX_REPEAT_COLUMNS == _LAMBDA.MAX_REPEAT_COLUMNS
    assert MAX_REPEAT_ROWS == _LAMBDA.MAX_REPEAT_ROWS
    assert RESERVED_REPEAT_COLUMN_NAMES == _LAMBDA.RESERVED_COLUMN_NAMES


_SOURCE_PARITY_CASES = [
    {"dataset_id": "ds-1"},                                                   # reference only
    {"dataset_id": "ds-1", "repeat_columns": ["a"], "repeat_rows": [["x"]]},  # both
    {"dataset_id": "ds-1", "repeat_columns": ["a"]},                          # reference + partial inline
    {},                                                                        # neither
    {"dataset_id": ""},                                                        # blank reference = neither
    {"dataset_id": 3},                                                         # wrong type
    {"repeat_columns": ["a"]},                                                 # rows missing
    {"repeat_rows": [["x"]]},                                                  # columns missing
    {"repeat_columns": ["a"], "repeat_rows": [["x"]], "parent_step_id": "r0"},  # nested
    {"repeat_columns": ["a"], "repeat_rows": [["x"]]},                         # valid inline
]


@pytest.mark.skipif(_LAMBDA is None, reason="Lambda source not present (standalone CLI install)")
@pytest.mark.parametrize("fields", _SOURCE_PARITY_CASES, ids=[str(i) for i in range(len(_SOURCE_PARITY_CASES))])
def test_repeat_step_errors_match_lambda(fields):
    step = {"step_type": "repeat", "instruction": "Loop", **fields}
    _, cli_errors = validate_repeat_step(step)
    assert cli_errors == _LAMBDA.validate_repeat_fields(step, [])


@pytest.mark.skipif(_LAMBDA is None, reason="Lambda source not present (standalone CLI install)")
def test_source_error_strings_match_lambda():
    assert REPEAT_NO_SOURCE_ERROR == _LAMBDA.REPEAT_NO_SOURCE_ERROR
    assert REPEAT_BOTH_SOURCES_ERROR == _LAMBDA.REPEAT_BOTH_SOURCES_ERROR


@pytest.mark.skipif(_LAMBDA is None, reason="Lambda source not present (standalone CLI install)")
def test_dataset_id_on_plain_step_matches_lambda():
    step = {"step_type": "navigation", "instruction": "x", "dataset_id": "ds-1"}
    assert validate_step(step)[1] == _LAMBDA.validate_repeat_fields(step, [])
