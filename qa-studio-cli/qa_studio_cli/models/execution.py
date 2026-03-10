"""Runner-specific data models for Nova Act execution.

These models are only imported by runner code and should not be imported
at module load time by core CLI modules (lazy import only).
"""

from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class StepResult:
    """Result of a single step execution."""

    success: bool
    act_id: str = ""
    logs: str = ""
    actual_value: str = ""


class UseCaseMetadata(BaseModel):
    """Use case definition fetched from the platform API."""

    id: str
    name: str
    starting_url: str
    executing_region: str
    model_id: Optional[str] = None


class UseCaseStep(BaseModel):
    """A single step within a use case."""

    step_id: str
    step_type: str
    instruction: str
    sort: int
    expected_value: Optional[str] = None
    capture_variable: Optional[str] = None
    operator: Optional[str] = None


class StepResultDetail(BaseModel):
    """Detail of a single step result in execution output."""

    model_config = ConfigDict(populate_by_name=True)

    step_id: str = Field(alias="stepId")
    step_type: str = Field(default="", alias="stepType")
    instruction: str = ""
    status: str
    duration: float
    error: Optional[str] = None


class ArtifactPaths(BaseModel):
    """Local artifact file paths."""

    video: Optional[str] = None
    logs: Optional[str] = None


class LocalExecutionResult(BaseModel):
    """Result of a local-only use case execution. Serialized as JSON to stdout."""

    model_config = ConfigDict(populate_by_name=True)

    status: str
    usecase_id: str = Field(alias="usecaseId")
    usecase_name: str = Field(alias="usecaseName")
    duration: float
    steps: list[StepResultDetail]
    artifacts: ArtifactPaths


class RemoteExecutionResult(BaseModel):
    """Result of a remote use case execution. Serialized as JSON to stdout."""

    model_config = ConfigDict(populate_by_name=True)

    status: str
    usecase_id: str = Field(alias="usecaseId")
    usecase_name: str = Field(alias="usecaseName")
    execution_id: str = Field(alias="executionId")
    duration: float
    steps: list[StepResultDetail]
