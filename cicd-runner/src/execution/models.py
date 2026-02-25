"""Data models for Nova Act execution."""

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field


@dataclass
class StepResult:
    """Result of a single step execution."""
    success: bool
    act_id: str = ""
    logs: str = ""
    actual_value: str = ""


class LocalStepResult(BaseModel):
    """Result of a single step in local-only execution."""
    step_id: str = Field(serialization_alias="stepId")
    instruction: str
    status: str  # "success" or "failed"
    duration: float
    screenshot: Optional[str] = None  # local file path

    model_config = {"populate_by_name": True}


class LocalArtifacts(BaseModel):
    """Local artifact paths."""
    video: Optional[str] = None
    logs: Optional[str] = None


class LocalExecutionResult(BaseModel):
    """Complete result of a local-only execution, serialized to stdout as JSON."""
    status: str  # "success" or "failed"
    usecase_id: str = Field(serialization_alias="usecaseId")
    usecase_name: str = Field(serialization_alias="usecaseName")
    duration: float
    steps: list[LocalStepResult]
    artifacts: LocalArtifacts

    model_config = {"populate_by_name": True}
