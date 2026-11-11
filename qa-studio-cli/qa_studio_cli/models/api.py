"""Pydantic models for QA Studio API responses."""

from typing import Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class UsecaseModel(BaseModel):
    """A test/usecase as returned by the API."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    name: str
    description: str = ""
    starting_url: str = ""
    active: bool = False
    tags: list[str] = []
    created_at: str = ""
    executing_region: str = ""
    model_id: str = ""


class StepModel(BaseModel):
    """A step within a test/usecase as returned by the API."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str = ""
    sort: int = 0
    instruction: str = ""
    step_type: str = "navigation"


class SuiteModel(BaseModel):
    """A test suite as returned by the API."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    name: str
    description: str = ""
    tags: list[str] = []
    created_at: str = ""
    created_by: str = ""
    total_usecases: int = 0


class SuiteUsecaseModel(BaseModel):
    """A usecase mapping within a test suite as returned by the API."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    usecase_id: str = ""
    usecase_name: str = ""
    added_by: str = ""
    added_at: str = ""


class SuiteExecutionResponse(BaseModel):
    """Response from suite execution endpoint."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    suite_execution_id: str
    suite_id: str
    status: str
    created_at: str
    execution_ids: list[dict] = []


class AddUsecasesResponse(BaseModel):
    """Response from POST /test-suites/{suite_id}/usecases.

    The backend returns snake_case keys (``added``, ``total_usecases``);
    ``populate_by_name`` accepts those alongside the camelCase aliases.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    added: int = 0
    total_usecases: int = 0


class GenerateUsecaseResponse(BaseModel):
    """Response from generate-usecase endpoint."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    success: bool
    usecase_data: str = ""
    message: str = ""


class ImportUsecaseResponse(BaseModel):
    """Response from import endpoint."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    success: bool
    usecase_id: str = ""
    message: str = ""


class ExecuteUsecaseResponse(BaseModel):
    """Response from execute usecase endpoint."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    status: str
    usecase_id: str
    execution_id: str = ""
    task_arn: str = ""
    task_id: str = ""
    cloud_watch_logs_url: str = ""


class TemplateModel(BaseModel):
    """A template (``GET /templates`` item / ``GET /templates/{id}``)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    name: str
    description: str = ""
    category: str = ""
    tags: list[str] = []
    version: int = 1
    created_by: str = ""
    created_at: str = ""


class TemplateStepModel(BaseModel):
    """A template step (``GET /templates/{id}/steps`` item)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str = ""
    sort: int = 0
    step_type: str = "navigation"
    instruction: str = ""
    secret_key: Optional[str] = None
    browser_action: Optional[str] = None
    validation_type: Optional[str] = None
    validation_operator: Optional[str] = None
    validation_value: Optional[str] = None
    capture_variable: Optional[str] = None


class ImportTemplateResponse(BaseModel):
    """Response from ``POST /templates/import``."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    name: str = ""
    steps_created: int = 0


class ReplaceTemplateResponse(BaseModel):
    """Response from ``PUT /templates/{id}``."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    name: str = ""
    version: int = 0
    steps_created: int = 0
    steps_updated: int = 0
    steps_deleted: int = 0


class TemplateUsageModel(BaseModel):
    """One entry of ``GET /templates/{id}/usages`` — a test with steps linked to the template."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    usecase_id: str
    name: str = ""


class InsertTemplateResponse(BaseModel):
    """Response from ``POST /usecase/{id}/import-template``.

    The backend sends ``steps_created`` (snake_case) and ``missingSecrets``
    (camelCase); ``populate_by_name`` accepts both spellings.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    message: str = ""
    steps_created: int = 0
    missing_secrets: list[str] = []
