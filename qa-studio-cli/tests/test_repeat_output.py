"""Row-aware human output and ``StepResultDetail`` repeat fields."""

from __future__ import annotations

import json

from qa_studio_cli.models.execution import StepResultDetail, LocalExecutionResult, ArtifactPaths
from qa_studio_cli.runner.output import SummaryFormatter


def _step(instruction, **extra):
    base = {"stepId": "s1", "stepType": "navigation", "instruction": instruction,
            "status": "success", "duration": 1.0}
    base.update(extra)
    return base


class TestStepResultDetailRepeatFields:
    def test_optional_and_absent_by_default(self):
        detail = StepResultDetail(step_id="s1", status="success", duration=0)
        dumped = detail.model_dump(by_alias=True)
        assert dumped["repeat_row_index"] is None
        assert dumped["repeat_row_total"] is None
        assert dumped["repeat_label"] is None

    def test_populated(self):
        detail = StepResultDetail(
            step_id="s1", status="success", duration=0,
            repeat_row_index=2, repeat_row_total=3, repeat_label="Users",
        )
        dumped = json.loads(LocalExecutionResult(
            status="success", usecase_id="u", usecase_name="n", duration=0,
            steps=[detail], artifacts=ArtifactPaths(),
        ).model_dump_json(by_alias=True))
        assert dumped["steps"][0]["repeat_row_index"] == 2
        assert dumped["steps"][0]["repeat_row_total"] == 3
        assert dumped["steps"][0]["repeat_label"] == "Users"


class TestHumanOutputRowPrefix:
    def test_expanded_step_gets_row_prefix(self):
        out = SummaryFormatter.format_usecase({
            "usecaseName": "Login", "status": "success", "duration": 3,
            "steps": [
                _step("Type alice into the email field", repeat_row_index=2, repeat_row_total=3),
            ],
        })
        assert "  \u2713 [row 2/3] [navigation] Type alice into the email field (1s)" in out

    def test_plain_step_unchanged(self):
        out = SummaryFormatter.format_usecase({
            "usecaseName": "Login", "status": "success", "duration": 3,
            "steps": [_step("Click login")],
        })
        assert "  \u2713 [navigation] Click login (1s)" in out
        assert "[row" not in out

    def test_snapshot_without_repeat_is_unchanged(self):
        result = {
            "usecaseName": "Login", "status": "failed", "duration": 65,
            "steps": [
                _step("Click login"),
                _step("Check title", stepType="validation", status="failed", error="nope"),
            ],
            "artifacts": {"video": "/tmp/v.webm", "logs": "/tmp/l.txt"},
        }
        assert SummaryFormatter.format_usecase(result) == "\n".join([
            "QA Studio - Local Execution",
            "",
            "Test: Login",
            "Duration: 1m 5s",
            "",
            "  \u2713 [navigation] Click login (1s)",
            "  \u2717 [validation] Check title (1s)",
            "    Error: nope",
            "",
            "\u2717 FAILED  |  Steps: 1/2 passed  |  Failed: 1",
            "",
            "Artifacts:",
            "  Video: /tmp/v.webm",
            "  Logs:  /tmp/l.txt",
        ])
