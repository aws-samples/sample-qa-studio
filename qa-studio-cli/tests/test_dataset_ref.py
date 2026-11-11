"""Parity: the CLI ``dataset_ref`` mirror behaves exactly like the Lambda module.

Both are driven by ``dataset_ref_cases.json``; the CLI keeps its own copy
under ``tests/fixtures/`` so the suite runs standalone, and the copy must
stay byte-identical to ``web-app/lambdas/endpoints/fixtures/`` when the
monorepo is present.  The remaining tests pin the CLI-only fetcher
(``application_dataset_fetcher`` over ``ApplicationsAPI``) and the runner
error mapping (``resolve_usecase_dataset_refs``).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from qa_studio_cli.api.applications import READ_SCOPE
from qa_studio_cli.models.errors import ApiError
from qa_studio_cli.runner.dataset_ref import (
    UNRESOLVED_DATASET_ERROR,
    DatasetNotFoundError,
    application_dataset_fetcher,
    resolve_dataset_refs,
    resolve_usecase_dataset_refs,
)
from qa_studio_cli.runner.repeat_expansion import expand_repeat_steps

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dataset_ref_cases.json"
_CASES = json.loads(_FIXTURE.read_text())["cases"]


def _find_server_fixture() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "web-app" / "lambdas" / "endpoints" / "fixtures" / "dataset_ref_cases.json"
        if candidate.exists():
            return candidate
    return None


_SERVER_FIXTURE = _find_server_fixture()


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


@pytest.mark.skipif(_SERVER_FIXTURE is None, reason="Lambda fixture not present (standalone CLI install)")
def test_fixture_copy_is_identical_to_the_server_fixture():
    assert _FIXTURE.read_text() == _SERVER_FIXTURE.read_text(), (
        "tests/fixtures/dataset_ref_cases.json drifted from "
        "web-app/lambdas/endpoints/fixtures/dataset_ref_cases.json — copy the server fixture over"
    )


def test_module_docstring_names_the_lambda_source():
    import qa_studio_cli.runner.dataset_ref as mod

    assert "web-app/lambdas/endpoints/dataset_ref.py" in (mod.__doc__ or "")
    assert "dataset_ref_cases.json" in (mod.__doc__ or "")


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
    (resolved,) = resolve_dataset_refs(
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


_REF_STEPS = [
    {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "L", "dataset_id": "ds-1"},
    {"id": "c1", "sort": 2, "step_type": "navigation", "instruction": "{{a}}", "parent_step_id": "r1"},
]


class TestApplicationDatasetFetcher:
    """``DatasetFetcher`` over ``ApplicationsAPI.get_dataset`` for one application."""

    def test_reads_the_dataset_of_the_application(self):
        api = MagicMock()
        api.get_dataset.return_value = {"dataset_id": "ds-1", "columns": ["a"], "rows": [["1"]]}
        fetch = application_dataset_fetcher(api, "app-1")
        assert fetch("ds-1") == {"dataset_id": "ds-1", "columns": ["a"], "rows": [["1"]]}
        api.get_dataset.assert_called_once_with("app-1", "ds-1")

    def test_404_is_none(self):
        api = MagicMock()
        api.get_dataset.side_effect = ApiError(404, "Resource not found.")
        assert application_dataset_fetcher(api, "app-1")("ds-missing") is None

    def test_memoizes_per_dataset_id_including_absent(self):
        api = MagicMock()
        api.get_dataset.side_effect = lambda app, ds: (
            {"columns": ["a"], "rows": []} if ds == "ds-1" else (_ for _ in ()).throw(ApiError(404, "nf"))
        )
        fetch = application_dataset_fetcher(api, "app-1")
        fetch("ds-1")
        fetch("ds-1")
        assert fetch("ds-missing") is None
        assert fetch("ds-missing") is None
        assert api.get_dataset.call_count == 2

    @pytest.mark.parametrize("application_id", [None, ""])
    def test_without_application_nothing_is_fetched(self, application_id):
        api = MagicMock()
        assert application_dataset_fetcher(api, application_id)("ds-1") is None
        api.get_dataset.assert_not_called()

    def test_403_raises_runtime_error_with_scope_hint(self):
        api = MagicMock()
        api.get_dataset.side_effect = ApiError(403, "Insufficient permissions.")
        with pytest.raises(RuntimeError) as excinfo:
            application_dataset_fetcher(api, "app-1")("ds-1")
        message = str(excinfo.value)
        assert f"--local-only with application datasets needs the {READ_SCOPE} scope" in message
        assert "ds-1" in message and "app-1" in message
        assert "Insufficient permissions." in message

    def test_other_api_errors_propagate_unchanged(self):
        api = MagicMock()
        api.get_dataset.side_effect = ApiError(500, "boom")
        with pytest.raises(ApiError) as excinfo:
            application_dataset_fetcher(api, "app-1")("ds-1")
        assert excinfo.value.status_code == 500


class TestResolveUsecaseDatasetRefs:
    """Runner wrapper: same resolution, ``RuntimeError`` messages for exit code 2."""

    def test_resolves_through_the_fetcher(self):
        fetch = _RecordingFetcher({"ds-1": {"columns": ["a"], "rows": [["1"], ["2"]]}})
        resolved = resolve_usecase_dataset_refs(_REF_STEPS, "app-1", fetch)
        assert resolved[0]["repeat_rows"] == [["1"], ["2"]]
        assert fetch.calls == ["ds-1"]

    def test_inline_steps_never_call_the_fetcher(self):
        fetch = _RecordingFetcher({})
        steps = [
            {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "L",
             "repeat_columns": ["a"], "repeat_rows": [["1"]]},
            {"id": "c1", "sort": 2, "step_type": "navigation", "instruction": "{{a}}", "parent_step_id": "r1"},
        ]
        assert resolve_usecase_dataset_refs(steps, None, fetch) == steps
        assert fetch.calls == []

    def test_missing_dataset_names_dataset_and_application(self):
        with pytest.raises(RuntimeError, match=r"^dataset ds-1 not found in application app-1$") as excinfo:
            resolve_usecase_dataset_refs(_REF_STEPS, "app-1", _RecordingFetcher({}))
        assert isinstance(excinfo.value.__cause__, DatasetNotFoundError)

    @pytest.mark.parametrize("application_id", [None, ""])
    def test_reference_without_application_is_explicit(self, application_id):
        with pytest.raises(RuntimeError, match=r"^dataset ds-1 not found: the use case has no application$"):
            resolve_usecase_dataset_refs(_REF_STEPS, application_id, _RecordingFetcher({}))
