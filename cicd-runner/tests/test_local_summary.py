"""Tests for format_local_summary and --output flag integration."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.execution.models import LocalExecutionResult, LocalStepResult, LocalArtifacts
from src.output.summary import SummaryFormatter


def _make_step(instruction: str, status: str = "success", duration: float = 2.0) -> LocalStepResult:
    return LocalStepResult(
        step_id="step-1",
        instruction=instruction,
        status=status,
        duration=duration,
    )


def _make_result(
    status: str = "success",
    steps: list | None = None,
    video: str | None = None,
    logs: str | None = None,
) -> LocalExecutionResult:
    if steps is None:
        steps = [
            _make_step("Navigate to login page", "success", 2.0),
            _make_step("Enter credentials", "success", 3.0),
            _make_step("Click login button", "failed", 2.0),
            _make_step("Verify dashboard loads", "success", 5.0),
        ]
    return LocalExecutionResult(
        status=status,
        usecase_id="ab49d73a-e3db-450b-a25b-d35a325e711f",
        usecase_name="Login Flow Test",
        duration=45.0,
        steps=steps,
        artifacts=LocalArtifacts(video=video, logs=logs),
    )


class TestFormatLocalSummary:
    """Tests for SummaryFormatter.format_local_summary()."""

    def test_header(self):
        result = _make_result()
        output = SummaryFormatter.format_local_summary(result)
        assert "QA Studio - Local Execution" in output

    def test_usecase_metadata(self):
        result = _make_result()
        output = SummaryFormatter.format_local_summary(result)
        assert "Use Case: Login Flow Test" in output
        assert "Use Case ID: ab49d73a-e3db-450b-a25b-d35a325e711f" in output
        assert "Duration: 45s" in output

    def test_passed_status(self):
        result = _make_result(status="success")
        output = SummaryFormatter.format_local_summary(result)
        assert "Status: ✓ PASSED" in output

    def test_failed_status(self):
        result = _make_result(status="failed")
        output = SummaryFormatter.format_local_summary(result)
        assert "Status: ✗ FAILED" in output

    def test_step_listing(self):
        result = _make_result()
        output = SummaryFormatter.format_local_summary(result)
        assert "✓ 1. Navigate to login page (2s)" in output
        assert "✓ 2. Enter credentials (3s)" in output
        assert "✗ 3. Click login button (2s)" in output
        assert "✓ 4. Verify dashboard loads (5s)" in output

    def test_step_totals(self):
        result = _make_result()
        output = SummaryFormatter.format_local_summary(result)
        assert "Total: 4  |  Passed: 3  |  Failed: 1" in output

    def test_all_passed_totals(self):
        steps = [_make_step("Step A", "success"), _make_step("Step B", "success")]
        result = _make_result(status="success", steps=steps)
        output = SummaryFormatter.format_local_summary(result)
        assert "Total: 2  |  Passed: 2  |  Failed: 0" in output

    def test_artifacts_with_video_and_logs(self):
        result = _make_result(
            video="/tmp/qa-studio-artifacts/abc-123/recording.webm",
            logs="/tmp/qa-studio-artifacts/abc-123/execution.log",
        )
        output = SummaryFormatter.format_local_summary(result)
        assert "Artifacts:" in output
        assert "Video: /tmp/qa-studio-artifacts/abc-123/recording.webm" in output
        assert "Logs:  /tmp/qa-studio-artifacts/abc-123/execution.log" in output

    def test_artifacts_video_only(self):
        result = _make_result(video="/tmp/recording.webm")
        output = SummaryFormatter.format_local_summary(result)
        assert "Video: /tmp/recording.webm" in output
        assert "Logs:" not in output

    def test_artifacts_logs_only(self):
        result = _make_result(logs="/tmp/execution.log")
        output = SummaryFormatter.format_local_summary(result)
        assert "Logs:  /tmp/execution.log" in output
        assert "Video:" not in output

    def test_no_artifacts_section_when_empty(self):
        result = _make_result()
        output = SummaryFormatter.format_local_summary(result)
        assert "Artifacts:" not in output

    def test_empty_steps(self):
        result = _make_result(steps=[])
        output = SummaryFormatter.format_local_summary(result)
        assert "Steps:" in output
        assert "Total: 0  |  Passed: 0  |  Failed: 0" in output

    def test_duration_minutes(self):
        result = _make_result()
        result.duration = 150.0
        output = SummaryFormatter.format_local_summary(result)
        assert "Duration: 2m 30s" in output

    def test_duration_hours(self):
        result = _make_result()
        result.duration = 4500.0
        output = SummaryFormatter.format_local_summary(result)
        assert "Duration: 1h 15m" in output
