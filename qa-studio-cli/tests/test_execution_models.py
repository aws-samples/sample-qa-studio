"""Tests for runner-specific execution models."""

from qa_studio_cli.models.execution import (
    StepResult,
    UseCaseMetadata,
    UseCaseStep,
    StepResultDetail,
    ArtifactPaths,
    LocalExecutionResult,
    RemoteExecutionResult,
)


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_defaults(self):
        r = StepResult(success=True)
        assert r.success is True
        assert r.act_id == ""
        assert r.logs == ""
        assert r.actual_value == ""

    def test_with_values(self):
        r = StepResult(success=False, act_id="act-1", logs="error", actual_value="42")
        assert r.success is False
        assert r.act_id == "act-1"
        assert r.logs == "error"
        assert r.actual_value == "42"


class TestUseCaseMetadata:
    """Tests for UseCaseMetadata pydantic model."""

    def test_required_fields(self):
        m = UseCaseMetadata(
            id="uc-1", name="Login", starting_url="https://app.com",
            executing_region="us-east-1",
        )
        assert m.id == "uc-1"
        assert m.model_id is None

    def test_optional_model_id(self):
        m = UseCaseMetadata(
            id="uc-1", name="Login", starting_url="https://app.com",
            executing_region="us-east-1", model_id="nova-act-v2.0",
        )
        assert m.model_id == "nova-act-v2.0"


class TestUseCaseStep:
    """Tests for UseCaseStep pydantic model."""

    def test_required_fields(self):
        s = UseCaseStep(
            step_id="s1", step_type="action", instruction="Click button", sort=1,
        )
        assert s.expected_value is None
        assert s.capture_variable is None

    def test_optional_fields(self):
        s = UseCaseStep(
            step_id="s1", step_type="retrieve_value", instruction="Get text",
            sort=2, expected_value="Hello", capture_variable="greeting",
            operator="equals",
        )
        assert s.expected_value == "Hello"
        assert s.capture_variable == "greeting"


class TestStepResultDetail:
    """Tests for StepResultDetail with alias serialization."""

    def test_alias_serialization(self):
        d = StepResultDetail(step_id="s1", status="success", duration=1.5)
        dumped = d.model_dump(by_alias=True)
        assert dumped["stepId"] == "s1"
        assert dumped["stepType"] == ""
        assert "step_id" not in dumped

    def test_populate_by_name(self):
        d = StepResultDetail(step_id="s1", step_type="action", status="failed", duration=2.0, error="timeout")
        assert d.step_id == "s1"
        assert d.error == "timeout"


class TestArtifactPaths:
    """Tests for ArtifactPaths."""

    def test_defaults_none(self):
        a = ArtifactPaths()
        assert a.video is None
        assert a.logs is None

    def test_with_paths(self):
        a = ArtifactPaths(video="/tmp/v.webm", logs="/tmp/l.txt")
        assert a.video == "/tmp/v.webm"


class TestLocalExecutionResult:
    """Tests for LocalExecutionResult with alias serialization."""

    def test_alias_serialization(self):
        r = LocalExecutionResult(
            status="success",
            usecase_id="uc-1",
            usecase_name="Login",
            duration=10.0,
            steps=[],
            artifacts=ArtifactPaths(),
        )
        dumped = r.model_dump(by_alias=True)
        assert dumped["usecaseId"] == "uc-1"
        assert dumped["usecaseName"] == "Login"
        assert "usecase_id" not in dumped


class TestRemoteExecutionResult:
    """Tests for RemoteExecutionResult with alias serialization."""

    def test_alias_serialization(self):
        r = RemoteExecutionResult(
            status="failed",
            usecase_id="uc-2",
            usecase_name="Checkout",
            execution_id="exec-1",
            duration=5.0,
            steps=[],
        )
        dumped = r.model_dump(by_alias=True)
        assert dumped["usecaseId"] == "uc-2"
        assert dumped["executionId"] == "exec-1"
        assert "usecase_id" not in dumped
