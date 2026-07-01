"""Pydantic models for QA Studio export JSON validation (client-side).

Used by ``qa-studio tests import`` to validate JSON test files before
sending them to the cloud-side ``/import`` endpoint. The model must
enumerate every step type and every per-type field that we want
preserved through the round-trip — pydantic v2's default
``extra='ignore'`` would otherwise silently drop any field not
declared here.

Mirrors the runtime ``ExecutionStep`` field set on the worker side
(``web-app/worker/models.py``). When new step types or new step fields
ship to the runtime, this model must be updated in lockstep or
``qa-studio tests import`` will reject (or worse, silently strip) the
new shape.
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


# Active step types plus the deprecated 'url' (kept for back-compat
# imports of older test files). 'url' steps still execute correctly on
# the runtime; new tests should use 'browser' with browser_action='navigate'.
VALID_STEP_TYPES = [
    "navigation",
    "url",  # deprecated but still valid for back-compat imports
    "browser",
    "secret",
    "validation",
    "retrieve_value",
    "assertion",
    "download",
    "transform",
    "network_assertion",
]


class ExportStep(BaseModel):
    """A single step in the export JSON.

    Optional fields are step-type-specific. The validator only enforces
    ``sort``, ``instruction``, and ``step_type``; per-type field
    requirements are checked at runtime by the worker / CLI runner.
    """

    sort: int = Field(..., gt=0)
    instruction: str = Field(..., min_length=1)
    step_type: str

    # Common across multiple step types
    capture_variable: Optional[str] = None
    assertion_variable: Optional[str] = None

    # Validation / assertion fields
    validation_type: Optional[str] = None
    validation_operator: Optional[str] = None
    validation_value: Optional[str] = None

    # Secret step
    secret_key: Optional[str] = None

    # Retrieve_value step
    value_type: Optional[str] = None
    value_source: Optional[str] = None
    value_format: Optional[str] = None  # used when value_type='date'

    # Browser step
    browser_action: Optional[str] = None
    browser_args: Optional[str] = None  # JSON-encoded

    # Transform step
    transform_operation: Optional[str] = None
    transform_args: Optional[str] = None  # JSON-encoded

    # Network assertion step — request side
    network_url_pattern: Optional[str] = None
    network_method: Optional[str] = None
    network_request_body: Optional[str] = None
    network_body_match_type: Optional[str] = None
    network_mock_response: Optional[str] = None
    network_mock_passthrough: Optional[bool] = None
    network_timeout: Optional[int] = None

    # Network assertion step — response side
    network_response_body: Optional[str] = None
    network_response_body_match_type: Optional[str] = None
    network_response_status: Optional[int] = None

    # Legacy field, kept for back-compat with very old export files.
    value_step: Optional[str] = None

    @field_validator("step_type")
    @classmethod
    def validate_step_type(cls, v: str) -> str:
        if v not in VALID_STEP_TYPES:
            raise ValueError(
                f"must be one of: {', '.join(VALID_STEP_TYPES)}"
            )
        return v


class ExportSecret(BaseModel):
    """A secret entry in the export JSON."""

    key: str = Field(..., min_length=1)
    description: str = ""


class ExportHooks(BaseModel):
    """Hook scripts in the export JSON."""

    beforeScript: str = ""
    afterScript: str = ""


class ExportUsecase(BaseModel):
    """Usecase metadata in the export JSON."""

    name: str = Field(..., min_length=1)
    starting_url: str = ""
    tags: list[str] = []
    description: str = ""
    active: bool = False
    executing_region: str = ""


class ExportPayload(BaseModel):
    """Top-level export JSON schema (exportVersion 1.0)."""

    exportVersion: str = Field(...)
    exportedAt: str = Field(..., min_length=1)
    usecase: ExportUsecase
    steps: list[ExportStep] = Field(..., min_length=1)
    variables: list[dict] = []
    secrets: list[ExportSecret] = []
    hooks: Optional[ExportHooks] = None

    @field_validator("exportVersion")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != "1.0":
            raise ValueError('exportVersion must be "1.0"')
        return v
