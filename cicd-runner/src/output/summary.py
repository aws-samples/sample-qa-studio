"""Format execution summary for console output."""

from typing import List, Dict, Any
from datetime import datetime


class SummaryFormatter:
    """Format execution summary for console output."""
    
    @staticmethod
    def format_table(
        suite_name: str,
        suite_execution_id: str,
        results: List[Dict[str, Any]],
        start_time: datetime,
        end_time: datetime
    ) -> str:
        """
        Format results as plain text summary.

        Args:
            suite_name: Test suite name
            suite_execution_id: Suite execution UUID
            results: List of execution results
            start_time: Suite execution start time
            end_time: Suite execution end time

        Returns:
            Formatted plain text summary string
        """
        total = len(results)
        passed = sum(1 for r in results if r['status'] == 'success')
        failed = total - passed
        success_rate = (passed / total * 100) if total > 0 else 0
        duration = (end_time - start_time).total_seconds()

        lines = []
        lines.append("Nova Act QA Studio - CI/CD Runner")
        lines.append("")
        lines.append(f"Suite: {suite_name}")
        lines.append(f"Suite Execution ID: {suite_execution_id}")
        lines.append(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Completed: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Duration: {SummaryFormatter._format_duration(duration)}")
        lines.append("")

        for result in results:
            prefix = "✓" if result['status'] == 'success' else "✗"
            duration_str = SummaryFormatter._format_duration(result['duration'])
            lines.append(f"{prefix} {result['usecase_name']} ({duration_str})")

        lines.append("")
        lines.append(f"Total: {total}  |  Passed: {passed}  |  Failed: {failed}  |  Success: {success_rate:.0f}%")

        return "\n".join(lines)
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """
        Format duration as human-readable string.
        
        Args:
            seconds: Duration in seconds
        
        Returns:
            Formatted duration (e.g., "45s", "2m 30s", "1h 15m")
        """
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
