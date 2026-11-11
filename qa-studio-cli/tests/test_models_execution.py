"""Tests for the multi-run result models in ``models/execution.py``."""

import pytest
from pydantic import ValidationError

from qa_studio_cli.models.execution import MultiRunEntry, MultiRunSummary


def _entry(status: str, **kw) -> MultiRunEntry:
    return MultiRunEntry(usecase_id="u-1", usecase_name="Login", status=status, **kw)


class TestMultiRunEntry:
    def test_defaults(self):
        e = _entry("success")
        assert e.execution_id is None
        assert e.duration == 0.0
        assert e.error is None

    def test_rejects_unknown_status(self):
        with pytest.raises(ValidationError):
            _entry("completed")

    def test_dump_uses_camel_case_aliases(self):
        dumped = _entry("failed", execution_id="ex-1", duration=2.5, error="boom").model_dump(by_alias=True)
        assert dumped == {
            "usecaseId": "u-1",
            "usecaseName": "Login",
            "status": "failed",
            "executionId": "ex-1",
            "duration": 2.5,
            "error": "boom",
        }

    def test_populate_by_alias(self):
        e = MultiRunEntry(usecaseId="u-2", usecaseName="X", status="skipped")
        assert e.usecase_id == "u-2"


class TestMultiRunSummary:
    def test_from_results_counts(self):
        s = MultiRunSummary.from_results(
            [_entry("success"), _entry("failed"), _entry("skipped"), _entry("success")]
        )
        assert (s.total, s.passed, s.failed, s.skipped) == (4, 2, 1, 1)
        assert len(s.results) == 4

    def test_from_results_empty(self):
        s = MultiRunSummary.from_results([])
        assert (s.total, s.passed, s.failed, s.skipped) == (0, 0, 0, 0)
        assert s.results == []

    def test_dump_shape(self):
        dumped = MultiRunSummary.from_results([_entry("success")]).model_dump(by_alias=True)
        assert set(dumped) == {"total", "passed", "failed", "skipped", "results"}
        assert dumped["results"][0]["usecaseId"] == "u-1"
