"""Tests for API response models and ApiError."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from qa_studio_cli.models.api import (
    GenerateUsecaseResponse,
    ImportUsecaseResponse,
    SuiteExecutionResponse,
    SuiteModel,
    UsecaseModel,
)
from qa_studio_cli.models.errors import ApiError


# ---------------------------------------------------------------------------
# Unit tests for ApiError (sub-task 1.6)
# ---------------------------------------------------------------------------


class TestApiError:
    """Unit tests for ApiError exception."""

    def test_str_includes_status_code_and_message(self):
        err = ApiError(status_code=500, message="Internal server error")
        assert str(err) == "[500] Internal server error"

    def test_str_includes_error_code_when_present(self):
        err = ApiError(status_code=422, message="Validation failed", error_code="INVALID_INPUT")
        assert str(err) == "[422] Validation failed (INVALID_INPUT)"

    def test_str_without_error_code(self):
        err = ApiError(status_code=404, message="Not found")
        assert "()" not in str(err)

    def test_attributes(self):
        err = ApiError(status_code=403, message="Forbidden", error_code="NO_SCOPE")
        assert err.status_code == 403
        assert err.message == "Forbidden"
        assert err.error_code == "NO_SCOPE"

    def test_is_exception(self):
        err = ApiError(status_code=500, message="fail")
        assert isinstance(err, Exception)

    def test_error_code_defaults_to_none(self):
        err = ApiError(status_code=400, message="bad")
        assert err.error_code is None


# ---------------------------------------------------------------------------
# Unit tests for UsecaseModel (sub-task 1.6)
# ---------------------------------------------------------------------------


class TestUsecaseModel:
    """Unit tests for UsecaseModel Pydantic model."""

    def test_accepts_camel_case_json(self):
        data = {
            "id": "uc-123",
            "name": "Login Test",
            "description": "Tests login flow",
            "startingUrl": "https://example.com",
            "active": True,
            "tags": ["smoke"],
            "createdAt": "2024-01-01T00:00:00Z",
            "executingRegion": "us-east-1",
            "modelId": "anthropic.claude-v2",
        }
        model = UsecaseModel(**data)
        assert model.id == "uc-123"
        assert model.name == "Login Test"
        assert model.starting_url == "https://example.com"
        assert model.executing_region == "us-east-1"
        assert model.model_id == "anthropic.claude-v2"
        assert model.active is True
        assert model.tags == ["smoke"]

    def test_accepts_snake_case_json_populate_by_name(self):
        data = {
            "id": "uc-456",
            "name": "Signup Test",
            "starting_url": "https://example.com/signup",
            "executing_region": "eu-west-1",
            "model_id": "anthropic.claude-v3",
        }
        model = UsecaseModel(**data)
        assert model.id == "uc-456"
        assert model.starting_url == "https://example.com/signup"
        assert model.executing_region == "eu-west-1"

    def test_defaults(self):
        model = UsecaseModel(id="uc-1", name="Minimal")
        assert model.description == ""
        assert model.starting_url == ""
        assert model.active is False
        assert model.tags == []
        assert model.created_at == ""
        assert model.executing_region == ""
        assert model.model_id == ""

    def test_missing_required_id_raises(self):
        with pytest.raises(ValidationError):
            UsecaseModel(name="No ID")

    def test_missing_required_name_raises(self):
        with pytest.raises(ValidationError):
            UsecaseModel(id="uc-1")


# ---------------------------------------------------------------------------
# Unit tests for SuiteModel (sub-task 1.6)
# ---------------------------------------------------------------------------


class TestSuiteModel:
    """Unit tests for SuiteModel Pydantic model."""

    def test_accepts_camel_case_json(self):
        data = {
            "id": "suite-001",
            "name": "Regression Suite",
            "description": "Full regression",
            "tags": ["regression", "nightly"],
            "createdAt": "2024-06-01T12:00:00Z",
            "createdBy": "user@example.com",
            "totalUsecases": 15,
        }
        model = SuiteModel(**data)
        assert model.id == "suite-001"
        assert model.name == "Regression Suite"
        assert model.created_at == "2024-06-01T12:00:00Z"
        assert model.created_by == "user@example.com"
        assert model.total_usecases == 15

    def test_accepts_snake_case_json_populate_by_name(self):
        data = {
            "id": "suite-002",
            "name": "Smoke Suite",
            "created_at": "2024-06-01",
            "created_by": "admin",
            "total_usecases": 3,
        }
        model = SuiteModel(**data)
        assert model.created_by == "admin"
        assert model.total_usecases == 3

    def test_defaults(self):
        model = SuiteModel(id="s-1", name="Minimal")
        assert model.description == ""
        assert model.tags == []
        assert model.created_at == ""
        assert model.created_by == ""
        assert model.total_usecases == 0

    def test_missing_required_id_raises(self):
        with pytest.raises(ValidationError):
            SuiteModel(name="No ID")


# ---------------------------------------------------------------------------
# Unit tests for response models (sub-task 1.6)
# ---------------------------------------------------------------------------


class TestResponseModels:
    """Unit tests for API response models."""

    def test_suite_execution_response_camel_case(self):
        data = {
            "suiteExecutionId": "se-001",
            "suiteId": "suite-001",
            "status": "running",
            "createdAt": "2024-06-01T12:00:00Z",
            "executionIds": [{"id": "exec-1"}, {"id": "exec-2"}],
        }
        model = SuiteExecutionResponse(**data)
        assert model.suite_execution_id == "se-001"
        assert model.suite_id == "suite-001"
        assert model.status == "running"
        assert len(model.execution_ids) == 2

    def test_generate_usecase_response_camel_case(self):
        data = {
            "success": True,
            "usecaseData": '{"steps": []}',
            "message": "Generated successfully",
        }
        model = GenerateUsecaseResponse(**data)
        assert model.success is True
        assert model.usecase_data == '{"steps": []}'
        assert model.message == "Generated successfully"

    def test_import_usecase_response_camel_case(self):
        data = {
            "success": True,
            "usecaseId": "uc-new-001",
            "message": "Imported",
        }
        model = ImportUsecaseResponse(**data)
        assert model.success is True
        assert model.usecase_id == "uc-new-001"


# ---------------------------------------------------------------------------
# Property test: ApiError string representation (Property 4, sub-task 1.3)
# ---------------------------------------------------------------------------


# Feature: wp4-api-commands, Property 4: ApiError string representation
# **Validates: Requirements 13.2**
class TestApiErrorStringProperty:
    """Property test: ApiError string representation always contains status code and message."""

    @given(
        status_code=st.integers(),
        message=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=100)
    def test_str_contains_status_code_and_message(self, status_code: int, message: str):
        err = ApiError(status_code=status_code, message=message)
        result = str(err)
        assert str(status_code) in result
        assert message in result

    @given(
        status_code=st.integers(),
        message=st.text(min_size=1, max_size=200),
        error_code=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=100)
    def test_str_contains_error_code_when_present(self, status_code: int, message: str, error_code: str):
        err = ApiError(status_code=status_code, message=message, error_code=error_code)
        result = str(err)
        assert str(status_code) in result
        assert message in result
        assert error_code in result


# ---------------------------------------------------------------------------
# Property test: camelCase to snake_case model round-trip (Property 5, sub-task 1.4)
# ---------------------------------------------------------------------------

# Feature: wp4-api-commands, Property 5: camelCase to snake_case model round-trip
# **Validates: Requirements 2.1, 2.2, 2.3**
class TestModelRoundTripProperty:
    """Property test: serializing to camelCase and parsing back produces equal instances."""

    @given(
        id=st.uuids().map(str),
        name=st.text(min_size=1, max_size=100),
        description=st.text(max_size=200),
        starting_url=st.text(max_size=200),
        active=st.booleans(),
        tags=st.lists(st.text(min_size=1, max_size=30), max_size=5),
        created_at=st.text(max_size=30),
        executing_region=st.text(max_size=30),
        model_id=st.text(max_size=50),
    )
    @settings(max_examples=100)
    def test_usecase_model_round_trip(
        self, id, name, description, starting_url, active, tags, created_at, executing_region, model_id
    ):
        original = UsecaseModel(
            id=id,
            name=name,
            description=description,
            starting_url=starting_url,
            active=active,
            tags=tags,
            created_at=created_at,
            executing_region=executing_region,
            model_id=model_id,
        )
        camel_dict = original.model_dump(by_alias=True)
        restored = UsecaseModel(**camel_dict)
        assert restored == original

    @given(
        id=st.uuids().map(str),
        name=st.text(min_size=1, max_size=100),
        description=st.text(max_size=200),
        tags=st.lists(st.text(min_size=1, max_size=30), max_size=5),
        created_at=st.text(max_size=30),
        created_by=st.text(max_size=50),
        total_usecases=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=100)
    def test_suite_model_round_trip(
        self, id, name, description, tags, created_at, created_by, total_usecases
    ):
        original = SuiteModel(
            id=id,
            name=name,
            description=description,
            tags=tags,
            created_at=created_at,
            created_by=created_by,
            total_usecases=total_usecases,
        )
        camel_dict = original.model_dump(by_alias=True)
        restored = SuiteModel(**camel_dict)
        assert restored == original


# ---------------------------------------------------------------------------
# Property test: Invalid API responses raise validation errors (Property 6, sub-task 1.5)
# ---------------------------------------------------------------------------

# Feature: wp4-api-commands, Property 6: Invalid API responses raise validation errors
# **Validates: Requirements 2.4**
class TestInvalidResponseProperty:
    """Property test: missing required 'id' field raises ValidationError."""

    @given(
        data=st.fixed_dictionaries(
            {
                "name": st.text(min_size=1, max_size=100),
                "description": st.text(max_size=200),
            }
        )
    )
    @settings(max_examples=100)
    def test_usecase_model_missing_id_raises(self, data: dict):
        assert "id" not in data
        with pytest.raises(ValidationError):
            UsecaseModel(**data)

    @given(
        data=st.fixed_dictionaries(
            {
                "name": st.text(min_size=1, max_size=100),
                "description": st.text(max_size=200),
            }
        )
    )
    @settings(max_examples=100)
    def test_suite_model_missing_id_raises(self, data: dict):
        assert "id" not in data
        with pytest.raises(ValidationError):
            SuiteModel(**data)
