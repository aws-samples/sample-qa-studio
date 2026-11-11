"""Fixture-driven tests for ``repeat_expansion.expand_repeat_steps``.

The cases live in ``fixtures/repeat_expansion_cases.json`` and are shared
with the CLI mirror (``qa-studio-cli/tests/test_repeat_expansion_parity.py``).
"""
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

from repeat_expansion import RepeatExpansionError, expand_repeat_steps  # noqa: E402

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "repeat_expansion_cases.json"
_CASES = json.loads(_FIXTURE.read_text())["cases"]


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_fixture_case(case):
    overrides = case.get("overrides")
    if "error" in case:
        with pytest.raises(RepeatExpansionError) as excinfo:
            expand_repeat_steps(case["steps"], overrides)
        assert case["error"] in str(excinfo.value), str(excinfo.value)
    else:
        assert expand_repeat_steps(case["steps"], overrides) == case["expected"]


def test_input_steps_are_not_mutated():
    steps = [
        {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "L",
         "repeat_columns": ["a"], "repeat_rows": [["1"]]},
        {"id": "c1", "sort": 2, "step_type": "navigation", "instruction": "x",
         "parent_step_id": "r1", "cached_steps": "[]"},
    ]
    snapshot = json.dumps(steps, sort_keys=True)
    expand_repeat_steps(steps)
    assert json.dumps(steps, sort_keys=True) == snapshot


def test_row_variable_values_are_strings():
    steps = [
        {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "L",
         "repeat_columns": ["n"], "repeat_rows": [["1"], ["2"], ["3"]]},
        {"id": "c1", "sort": 2, "step_type": "navigation", "instruction": "x", "parent_step_id": "r1"},
    ]
    out = expand_repeat_steps(steps)
    assert [s["repeat_row_index"] for s in out] == [1, 2, 3]
    for step in out:
        assert all(isinstance(v, str) for v in step["row_variables"].values())
        assert step["row_variables"]["RepeatTotal"] == "3"


def test_expanded_steps_drop_cache_and_parent_fields():
    steps = [
        {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "L",
         "repeat_columns": ["a"], "repeat_rows": [["1"]]},
        {"id": "c1", "sort": 2, "step_type": "navigation", "instruction": "x", "parent_step_id": "r1",
         "trajectory_s3_key": "k", "trajectory_last_updated": "t",
         "cached_steps": "[]", "cache_last_updated": "u"},
    ]
    (out,) = expand_repeat_steps(steps)
    for field in ("trajectory_s3_key", "trajectory_last_updated", "cached_steps",
                  "cache_last_updated", "parent_step_id"):
        assert field not in out


def test_none_overrides_equals_empty_overrides():
    steps = [{"id": "a", "sort": 1, "step_type": "navigation", "instruction": "A"}]
    assert expand_repeat_steps(steps, None) == expand_repeat_steps(steps, {})
