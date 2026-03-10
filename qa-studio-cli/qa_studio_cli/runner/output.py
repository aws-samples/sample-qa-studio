"""Format execution summary for console output."""

from datetime import datetime
from typing import Any, Dict, List


class SummaryFormatter:
    """Format execution summary for console output."""

    @staticmethod
    def format_table(
        suite_name: str,
        suite_execution_id: str,
        results: List[Dict[str, Any]],
        start_time: datetime,
        end_time: datetime,
    ) -> str:
        """Format results as plain text summary."""
        total = len(results)
        passed = sum(1 for r in results if r["status"] == "success")
        failed = total - passed
        success_rate = (passed / total * 100) if total > 0 else 0
        duration = (end_time - start_time).total_seconds()

        lines = [
            "QA Studio - CI/CD Runner",
            "",
            f"Suite: {suite_name}",
            f"Suite Execution ID: {suite_execution_id}",
            f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Completed: {end_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Duration: {SummaryFormatter._format_duration(duration)}",
            "",
        ]

        for result in results:
            prefix = "\u2713" if result["status"] == "success" else "\u2717"
            duration_str = SummaryFormatter._format_duration(result["duration"])
            lines.append(f"{prefix} {result['usecase_name']} ({duration_str})")

        lines.append("")
        lines.append(
            f"Total: {total}  |  Passed: {passed}  |  Failed: {failed}  |  Success: {success_rate:.0f}%"
        )
        return "\n".join(lines)

    @staticmethod
    def format_usecase(result: Dict[str, Any]) -> str:
        """Format a single use case execution result as human-readable text."""
        usecase_name = result.get("usecaseName", result.get("usecase_name", "Unknown"))
        status = result.get("status", "unknown")
        duration = result.get("duration", 0)
        steps = result.get("steps", [])
        artifacts = result.get("artifacts", {})

        total = len(steps)
        passed = sum(1 for s in steps if s.get("status") == "success")
        failed = total - passed

        lines = [
            "QA Studio - Local Execution",
            "",
            f"Test: {usecase_name}",
            f"Duration: {SummaryFormatter._format_duration(duration)}",
            "",
        ]

        for i, step in enumerate(steps, 1):
            prefix = "\u2713" if step.get("status") == "success" else "\u2717"
            step_duration = SummaryFormatter._format_duration(step.get("duration", 0))
            step_type = step.get("stepType", step.get("step_type", ""))
            instruction = step.get("instruction", "")
            label = f"[{step_type}] {instruction}" if step_type and instruction else f"Step {i}"
            lines.append(f"  {prefix} {label} ({step_duration})")
            if step.get("status") != "success" and step.get("error"):
                lines.append(f"    Error: {step['error']}")

        lines.append("")
        overall = "\u2713 PASSED" if status == "success" else "\u2717 FAILED"
        lines.append(f"{overall}  |  Steps: {passed}/{total} passed  |  Failed: {failed}")

        if artifacts:
            video = artifacts.get("video")
            logs = artifacts.get("logs")
            if video or logs:
                lines.append("")
                lines.append("Artifacts:")
                if video:
                    lines.append(f"  Video: {video}")
                if logs:
                    lines.append(f"  Logs:  {logs}")

        return "\n".join(lines)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration as human-readable string."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
