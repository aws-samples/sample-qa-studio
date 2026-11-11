"""Runner-specific data models for Nova Act execution.

These models are only imported by runner code and should not be imported
at module load time by core CLI modules (lazy import only).
"""

from dataclasses import dataclass
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class StepResult:
    """Result of a single step execution."""

    success: bool
    act_id: str = ""
    logs: str = ""
    actual_value: str = ""


@dataclass
class ReplayResult:
    """Outcome of a trajectory-replay attempt.

    Mirrors ``web-app/worker/models.py::ReplayResult`` so the CLI and
    worker share an identical contract around trajectory replay.
    """

    success: bool
    duration_ms: int
    trajectory_s3_key: str
    error: Optional[str] = None


class TrajectoryReplayError(Exception):
    """Raised when trajectory replay fails.

    Mirrors ``web-app/worker/models.py::TrajectoryReplayError``.  Raised
    for every non-recoverable path in the replay pipeline — download
    failure, malformed trajectory JSON, SDK internal error,
    per-trajectory-step timeout — so the navigation-step logic can
    uniformly catch and fall through to Nova Act.
    """

    def __init__(
        self,
        message: str,
        s3_key: str,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.s3_key = s3_key
        self.cause = cause


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
    browser_action: Optional[str] = None
    browser_args: Optional[str] = None
    transform_operation: Optional[str] = None
    transform_args: Optional[str] = None
    # value_format is consumed by retrieve_value steps when value_type='date'.
    # Empty / missing means auto-detect ISO 8601 / Unix epoch; otherwise it's
    # a strptime format string passed to transform.date_parser.parse_to_utc.
    value_format: Optional[str] = None
    # network_assertion step fields
    network_url_pattern: Optional[str] = None
    network_method: Optional[str] = None
    network_request_body: Optional[str] = None
    network_body_match_type: Optional[str] = None
    network_mock_response: Optional[str] = None
    network_mock_passthrough: bool = False
    network_timeout: Optional[int] = None
    # network_assertion response-side assertion fields
    network_response_body: Optional[str] = None
    network_response_body_match_type: Optional[str] = None
    network_response_status: Optional[int] = None


class StepResultDetail(BaseModel):
    """Detail of a single step result in execution output."""

    model_config = ConfigDict(populate_by_name=True)

    step_id: str = Field(alias="stepId")
    step_type: str = Field(default="", alias="stepType")
    instruction: str = ""
    status: str
    duration: float
    error: Optional[str] = None
    # Set on steps unrolled from a ``repeat`` step (see repeat-step design).
    repeat_row_index: Optional[int] = None
    repeat_row_total: Optional[int] = None
    repeat_label: Optional[str] = None


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


MultiRunStatus = Literal["success", "failed", "skipped"]


class MultiRunEntry(BaseModel):
    """One use case's verdict in a multi-use-case ``qa-studio run``.

    ``skipped`` is only produced by ``--fail-fast`` for use cases that
    were never started.  ``execution_id`` is set on the remote path only.
    """

    model_config = ConfigDict(populate_by_name=True)

    usecase_id: str = Field(alias="usecaseId")
    usecase_name: str = Field(alias="usecaseName")
    status: MultiRunStatus
    execution_id: Optional[str] = Field(default=None, alias="executionId")
    duration: float = 0.0
    error: Optional[str] = None


class MultiRunSummary(BaseModel):
    """Aggregate verdict of a multi-use-case run. Serialized as JSON to stdout."""

    total: int
    passed: int
    failed: int
    skipped: int
    results: List[MultiRunEntry]

    @classmethod
    def from_results(cls, results: List[MultiRunEntry]) -> "MultiRunSummary":
        """Build the summary; counts are always derived, never hand-assembled."""
        return cls(
            total=len(results),
            passed=sum(1 for r in results if r.status == "success"),
            failed=sum(1 for r in results if r.status == "failed"),
            skipped=sum(1 for r in results if r.status == "skipped"),
            results=list(results),
        )
