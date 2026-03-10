"""Pydantic models for QA Studio API responses."""

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

