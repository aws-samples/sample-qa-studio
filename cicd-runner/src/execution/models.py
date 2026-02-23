"""Data models for Nova Act execution."""

from dataclasses import dataclass, field


@dataclass
class StepResult:
    """Result of a single step execution."""
    success: bool
    act_id: str = ""
    logs: str = ""
    actual_value: str = ""
