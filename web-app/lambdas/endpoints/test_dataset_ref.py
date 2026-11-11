"""Tests for ``dataset_ref`` — resolving ``dataset_id`` on repeat steps.

The fixture cases live in ``fixtures/dataset_ref_cases.json`` and are shared
with the CLI mirror (task 09); the remaining tests pin the server-only
fetcher factory (``application_dataset_fetcher``).
"""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

from dataset_ref import (  # noqa: E402
    UNRESOLVED_DATASET_ERROR,
    DatasetNotFoundError,
    application_dataset_fetcher,
    resolve_dataset_refs,
)
from repeat_expansion import expand_repeat_steps  # noqa: E402
from variable_merge import client_item_reader  # noqa: E402

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dataset_ref_cases.json"
_CASES = json.loads(_FIXTURE.read_text())["cases"]


class _RecordingFetcher:
    """``datasets.get`` that remembers every id it was asked for."""

    def __init__(self, datasets):
        self.datasets = datasets
        self.calls = []

    def __call__(self, dataset_id):
        self.calls.append(dataset_id)
        return self.datasets.get(dataset_id)


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_fixture_case(case):
    fetch = _RecordingFetcher(case["datasets"])
    if "error" in case:
        with pytest.raises(DatasetNotFoundError) as excinfo:
            resolve_dataset_refs(case["steps"], fetch)
        assert excinfo.value.dataset_id == case["error"]["dataset_id"]
        assert case["error"]["dataset_id"] in str(excinfo.value)
    else:
        resolved = resolve_dataset_refs(case["steps"], fetch)
        assert resolved == case["expected"]
        if "expanded" in case:
            assert expand_repeat_steps(resolved, case.get("overrides")) == case["expanded"]
    assert fetch.calls == case["fetched"]


def test_fixture_cases_are_self_describing():
    """Every case names its inputs and exactly one outcome (task 09 relies on this shape)."""
    for case in _CASES:
        assert set(case) >= {"name", "steps", "datasets", "fetched"}, case["name"]
        assert ("expected" in case) != ("error" in case), case["name"]
        if "expanded" in case:
            assert "overrides" in case and "expected" in case, case["name"]


def test_input_steps_are_not_mutated():
    steps = [
        {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "L", "dataset_id": "ds-1"},
        {"id": "c1", "sort": 2, "step_type": "navigation", "instruction": "x", "parent_step_id": "r1"},
    ]
    snapshot = json.dumps(steps, sort_keys=True)
    resolved = resolve_dataset_refs(steps, {"ds-1": {"columns": ["a"], "rows": [["1"]]}}.get)
    assert json.dumps(steps, sort_keys=True) == snapshot
    assert all(new is not old for new, old in zip(resolved, steps))


def test_resolved_rows_are_copies_of_the_dataset():
    dataset = {"columns": ["a"], "rows": [["1"]]}
    (resolved, ) = resolve_dataset_refs(
        [{"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "L", "dataset_id": "ds-1"}],
        {"ds-1": dataset}.get,
    )
    resolved["repeat_rows"][0].append("mutated")
    resolved["repeat_columns"].append("mutated")
    assert dataset == {"columns": ["a"], "rows": [["1"]]}


def test_error_carries_dataset_id_and_message():
    error = DatasetNotFoundError("ds-9")
    assert error.dataset_id == "ds-9"
    assert str(error) == f"{UNRESOLVED_DATASET_ERROR}: ds-9"
    assert isinstance(error, ValueError)


class TestApplicationDatasetFetcher:
    def _client(self, items):
        """Low-level client stub: ``items`` is ``{(pk, sk): typed item}``."""
        client = MagicMock()

        def get_item(TableName, Key):
            item = items.get((Key["pk"]["S"], Key["sk"]["S"]))
            return {"Item": item} if item is not None else {}

        client.get_item.side_effect = get_item
        return client

    def test_reads_the_dataset_record_of_the_application(self):
        client = self._client({
            ("APPLICATION#app-1", "DATASET#ds-1"): {
                "dataset_id": {"S": "ds-1"},
                "columns": {"L": [{"S": "email"}]},
                "rows": {"L": [{"L": [{"S": "a@x.test"}]}]},
            },
        })
        fetch = application_dataset_fetcher(client_item_reader(client, "tbl"), "app-1")
        dataset = fetch("ds-1")
        assert dataset["columns"] == ["email"]
        assert dataset["rows"] == [["a@x.test"]]
        client.get_item.assert_called_once_with(
            TableName="tbl", Key={"pk": {"S": "APPLICATION#app-1"}, "sk": {"S": "DATASET#ds-1"}},
        )

    def test_missing_record_is_none(self):
        fetch = application_dataset_fetcher(client_item_reader(self._client({}), "tbl"), "app-1")
        assert fetch("ds-missing") is None

    def test_memoizes_per_dataset_id(self):
        client = self._client({
            ("APPLICATION#app-1", "DATASET#ds-1"): {"columns": {"L": [{"S": "a"}]}, "rows": {"L": []}},
        })
        fetch = application_dataset_fetcher(client_item_reader(client, "tbl"), "app-1")
        fetch("ds-1")
        fetch("ds-1")
        fetch("ds-missing")
        fetch("ds-missing")
        assert client.get_item.call_count == 2

    @pytest.mark.parametrize("application_id", [None, ""])
    def test_without_application_nothing_is_read_and_nothing_resolves(self, application_id):
        client = self._client({})
        fetch = application_dataset_fetcher(client_item_reader(client, "tbl"), application_id)
        assert fetch("ds-1") is None
        client.get_item.assert_not_called()

    def test_resolution_through_the_fetcher_end_to_end(self):
        client = self._client({
            ("APPLICATION#app-1", "DATASET#ds-1"): {
                "columns": {"L": [{"S": "n"}]},
                "rows": {"L": [{"L": [{"S": "1"}]}, {"L": [{"S": "2"}]}]},
            },
        })
        fetch = application_dataset_fetcher(client_item_reader(client, "tbl"), "app-1")
        steps = [
            {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "L", "dataset_id": "ds-1"},
            {"id": "c1", "sort": 2, "step_type": "navigation", "instruction": "{{n}}", "parent_step_id": "r1"},
        ]
        expanded = expand_repeat_steps(resolve_dataset_refs(steps, fetch))
        assert [s["row_variables"]["n"] for s in expanded] == ["1", "2"]
