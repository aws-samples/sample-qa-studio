"""Pydantic models for QA Studio export JSON validation (client-side)."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


VALID_STEP_TYPES = [
    "navigation",
    "validation",
    "secret",
    "retrieve_value",
    "assertion",
    "url",
    "download",
]


class ExportStep(BaseModel):
    """A single step in the export JSON."""

    sort: int = Field(..., gt=0)
    instruction: str = Field(..., min_length=1)
    step_type: str
    secret_key: Optional[str] = None
    capture_variable: Optional[str] = None
    validation_type: Optional[str] = None
    validation_operator: Optional[str] = None
    validation_value: Optional[str] = None
    assertion_variable: Optional[str] = None
    value_step: Optional[str] = None
    value_type: Optional[str] = None

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
