"""Tests for runner output formatter (SummaryFormatter)."""

from datetime import datetime

import click

from qa_studio_cli.runner.output import SummaryFormatter


class TestFormatTable:
    """Tests for SummaryFormatter.format_table."""

    def test_all_passed(self):
        results = [
            {"usecase_name": "Login", "status": "success", "duration": 10.5},
            {"usecase_name": "Checkout", "status": "success", "duration": 25.0},
        ]
        output = SummaryFormatter.format_table(
            suite_name="Smoke Tests",
            suite_execution_id="exec-123",
            results=results,
            start_time=datetime(2025, 1, 1, 12, 0, 0),
            end_time=datetime(2025, 1, 1, 12, 1, 0),
        )
        assert "Smoke Tests" in output
        assert "exec-123" in output
        assert "Passed: 2" in output
        assert "Failed: 0" in output
        assert "100%" in output
        assert "✓ Login" in output
        assert "✓ Checkout" in output

    def test_mixed_results(self):
        results = [
            {"usecase_name": "Login", "status": "success", "duration": 10.0},
            {"usecase_name": "Payment", "status": "failed", "duration": 5.0},
        ]
        output = SummaryFormatter.format_table(
            suite_name="Suite",
            suite_execution_id="e1",
            results=results,
            start_time=datetime(2025, 1, 1, 12, 0, 0),
            end_time=datetime(2025, 1, 1, 12, 0, 30),
        )
        assert "Passed: 1" in output
        assert "Failed: 1" in output
        assert "50%" in output
        assert "✓ Login" in output
        assert "✗ Payment" in output

    def test_empty_results(self):
        output = SummaryFormatter.format_table(
            suite_name="Empty",
            suite_execution_id="e0",
            results=[],
            start_time=datetime(2025, 1, 1, 12, 0, 0),
            end_time=datetime(2025, 1, 1, 12, 0, 0),
        )
        assert "Total: 0" in output


class TestFormatUsecase:
    """Tests for SummaryFormatter.format_usecase."""

    def test_success_with_steps(self):
        result = {
            "usecase_name": "Login Flow",
            "status": "success",
            "duration": 15.0,
            "steps": [
                {"step_type": "action", "instruction": "Click login", "status": "success", "duration": 5.0},
                {"step_type": "validation", "instruction": "Check dashboard", "status": "success", "duration": 3.0},
            ],
            "artifacts": {"video": "/tmp/video.webm", "logs": "/tmp/logs.txt"},
        }
        output = SummaryFormatter.format_usecase(result)
        assert "Login Flow" in output
        assert "✓ PASSED" in output
        assert "2/2 passed" in output
        assert "/tmp/video.webm" in output
        assert "/tmp/logs.txt" in output

    def test_failed_with_error(self):
        result = {
            "usecase_name": "Checkout",
            "status": "failed",
            "duration": 8.0,
            "steps": [
                {"step_type": "action", "instruction": "Add to cart", "status": "success", "duration": 3.0},
                {"step_type": "action", "instruction": "Pay", "status": "failed", "duration": 2.0, "error": "Timeout"},
            ],
            "artifacts": {},
        }
        output = SummaryFormatter.format_usecase(result)
        assert "✗ FAILED" in output
        assert "1/2 passed" in output
        assert "Timeout" in output

    def test_no_steps(self):
        result = {
            "usecase_name": "Empty",
            "status": "success",
            "duration": 0,
            "steps": [],
            "artifacts": {},
        }
        output = SummaryFormatter.format_usecase(result)
        assert "0/0 passed" in output


class TestFormatDuration:
    """Tests for SummaryFormatter._format_duration."""

    def test_seconds(self):
        assert SummaryFormatter._format_duration(45.3) == "45s"

    def test_minutes(self):
        assert SummaryFormatter._format_duration(125) == "2m 5s"

    def test_hours(self):
        assert SummaryFormatter._format_duration(3725) == "1h 2m"

    def test_zero(self):
        assert SummaryFormatter._format_duration(0) == "0s"


class TestFormatMultiSummary:
    """Tests for SummaryFormatter.format_multi_summary (multi-usecase runs)."""

    @staticmethod
    def _summary(*statuses):
        from qa_studio_cli.models.execution import MultiRunEntry, MultiRunSummary

        entries = [
            MultiRunEntry(usecase_id=f"u-{i}", usecase_name=f"Case {i}", status=s)
            for i, s in enumerate(statuses)
        ]
        return MultiRunSummary.from_results(entries)

    def test_all_passed(self):
        output = click.unstyle(
            SummaryFormatter.format_multi_summary(self._summary("success", "success"))
        )
        assert output == (
            "QA Studio - Run Summary\n"
            "\n"
            "Passed: 2/2\n"
            "\n"
            "\u2713 Case 0\n"
            "\u2713 Case 1"
        )

    def test_mixed_with_skipped_keeps_input_order(self):
        output = click.unstyle(SummaryFormatter.format_multi_summary(
            self._summary("success", "failed", "skipped")
        ))
        lines = output.splitlines()
        assert "Passed: 1/3" in lines
        assert lines[-3:] == ["\u2713 Case 0", "\u2717 Case 1", "\u25cb Case 2 (skipped)"]

    def test_marks_are_coloured(self):
        output = SummaryFormatter.format_multi_summary(
            self._summary("success", "failed", "skipped")
        )
        assert click.style("\u2713", fg="green") + " Case 0" in output
        assert click.style("\u2717", fg="red") + " Case 1" in output
        assert click.style("\u25cb", fg="yellow") + " Case 2" in output

    def test_empty(self):
        output = SummaryFormatter.format_multi_summary(self._summary())
        assert "Passed: 0/0" in output
        assert output.endswith("Passed: 0/0")
