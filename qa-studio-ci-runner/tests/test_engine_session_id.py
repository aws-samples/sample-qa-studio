"""Bug condition exploration tests for Nova session ID capture in qa-studio-ci-runner path.

**Validates: Requirements 1.1, 1.2, 2.1, 2.2**

These tests encode the EXPECTED (correct) behavior: after opening a NovaAct context,
_run_steps_with_nova should call nova.get_session_id() and persist the result via
the ExecutionAPI. On UNFIXED code, these tests MUST FAIL — failure confirms the bug
exists.

Property 1 (Fault Condition): Nova Session ID Never Captured in QA Studio CI Runner Path
- _run_steps_with_nova opens a NovaAct context but never calls nova.get_session_id()
- ExecutionAPI has no update_session_id method to persist the session ID
"""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from hypothesis import given, strategies as st, settings

from src.execution.engine import ExecutionEngine
from src.execution.models import StepResult
from src.api.executions import ExecutionAPI


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

session_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=8,
    max_size=64,
).filter(lambda s: len(s.strip()) > 0)

single_step_strategy = st.fixed_dictionaries({
    "sk": st.just("EXECUTION_STEP#step-001"),
    "step_id": st.just("step-001"),
    "sort": st.just(1),
    "instruction": st.just("click the button"),
    "step_type": st.just("navigation"),
})


def _build_nova_mock(session_id: str) -> MagicMock:
    """Build a mock NovaAct context manager that returns a known session ID."""
    nova_instance = MagicMock()
    nova_instance.get_session_id.return_value = session_id
    nova_instance.page = MagicMock()
    nova_instance.go_to_url = MagicMock()

    nova_cm = MagicMock()
    nova_cm.__enter__ = Mock(return_value=nova_instance)
    nova_cm.__exit__ = Mock(return_value=False)
    return nova_cm, nova_instance


def _build_engine() -> tuple:
    """Build an ExecutionEngine with mocked dependencies."""
    mock_client = Mock()
    execution_api = ExecutionAPI(client=mock_client)
    # Mock async methods used during step execution
    execution_api.update_step_status = AsyncMock()
    engine = ExecutionEngine(
        execution_api=execution_api,
        suite_execution_id="suite-exec-001",
    )
    return engine, execution_api


def _build_step_executor_mock(success: bool = True) -> MagicMock:
    """Build a mock StepExecutor that returns a predetermined result."""
    mock_executor = MagicMock()
    mock_executor.execute.return_value = StepResult(
        success=success, act_id="act-001", logs=""
    )
    return mock_executor


# ---------------------------------------------------------------------------
# Property 1: Fault Condition — get_session_id is called and result persisted
# ---------------------------------------------------------------------------


class TestNovaSessionIdCapture:
    """Property 1: Fault Condition — Nova Session ID Never Captured in QA Studio CI Runner Path.

    **Validates: Requirements 1.1, 1.2, 2.1, 2.2**

    These tests assert the EXPECTED behavior. They MUST FAIL on unfixed code,
    confirming the bug exists.
    """

    @given(session_id=session_id_strategy, step=single_step_strategy)
    @settings(max_examples=20, deadline=10000)
    def test_get_session_id_called_after_nova_context_opens(
        self, session_id: str, step: dict
    ):
        """After opening the NovaAct context, nova.get_session_id() MUST be called.

        **Validates: Requirements 1.1, 2.1**

        On unfixed code this FAILS because _run_steps_with_nova never calls
        get_session_id().
        """
        engine, execution_api = _build_engine()
        nova_cm, nova_instance = _build_nova_mock(session_id)
        mock_step_executor = _build_step_executor_mock(success=True)

        artifact_capture = MagicMock()
        artifact_capture.capture_step_screenshot.return_value = None
        artifact_uploader = MagicMock()

        with patch("src.execution.engine.NovaAct", return_value=nova_cm):
            with patch(
                "src.execution.engine.StepExecutor",
                return_value=mock_step_executor,
            ):
                engine._run_steps_with_nova(
                    nova_kwargs={"starting_page": "https://example.com"},
                    steps=[step],
                    variables={},
                    headers={},
                    starting_url="https://example.com",
                    usecase_id="uc-001",
                    execution_id="exec-001",
                    artifact_capture=artifact_capture,
                    artifact_uploader=artifact_uploader,
                    logs_dir="/tmp/logs",
                )

        # ASSERT: get_session_id was called at least once
        nova_instance.get_session_id.assert_called()

    @given(session_id=session_id_strategy, step=single_step_strategy)
    @settings(max_examples=20, deadline=10000)
    def test_session_id_persisted_via_api(self, session_id: str, step: dict):
        """The captured session ID MUST be persisted via an API call.

        **Validates: Requirements 1.2, 2.2**

        On unfixed code this FAILS because:
        1. get_session_id() is never called
        2. ExecutionAPI has no update_session_id method
        """
        engine, execution_api = _build_engine()
        nova_cm, nova_instance = _build_nova_mock(session_id)
        mock_step_executor = _build_step_executor_mock(success=True)

        # Add a mock update_session_id to track if it gets called
        execution_api.update_session_id = AsyncMock()

        artifact_capture = MagicMock()
        artifact_capture.capture_step_screenshot.return_value = None
        artifact_uploader = MagicMock()

        with patch("src.execution.engine.NovaAct", return_value=nova_cm):
            with patch(
                "src.execution.engine.StepExecutor",
                return_value=mock_step_executor,
            ):
                engine._run_steps_with_nova(
                    nova_kwargs={"starting_page": "https://example.com"},
                    steps=[step],
                    variables={},
                    headers={},
                    starting_url="https://example.com",
                    usecase_id="uc-001",
                    execution_id="exec-001",
                    artifact_capture=artifact_capture,
                    artifact_uploader=artifact_uploader,
                    logs_dir="/tmp/logs",
                )

        # ASSERT: update_session_id was called with the session ID
        execution_api.update_session_id.assert_called()
        call_kwargs = execution_api.update_session_id.call_args
        # The session_id argument should match what get_session_id returned
        assert session_id in str(call_kwargs), (
            f"Expected session ID '{session_id}' to be passed to update_session_id, "
            f"but got call args: {call_kwargs}"
        )


class TestExecutionAPIHasSessionIdMethod:
    """Verify ExecutionAPI exposes an update_session_id method.

    **Validates: Requirements 1.2, 2.2**

    On unfixed code this FAILS because the method does not exist.
    """

    def test_execution_api_has_update_session_id_method(self):
        """ExecutionAPI MUST have an update_session_id method."""
        mock_client = Mock()
        api = ExecutionAPI(client=mock_client)
        assert hasattr(api, "update_session_id"), (
            "ExecutionAPI is missing update_session_id method — "
            "session ID cannot be persisted from the qa-studio-ci-runner path"
        )


# ---------------------------------------------------------------------------
# Property 2: Preservation — Existing Step Execution and Status Update
# Behavior Unchanged
# ---------------------------------------------------------------------------

# Strategies for preservation tests

step_success_strategy = st.booleans()

step_list_strategy = st.lists(
    st.fixed_dictionaries({
        "sk": st.integers(min_value=1, max_value=99).map(
            lambda i: f"EXECUTION_STEP#step-{i:03d}"
        ),
        "step_id": st.integers(min_value=1, max_value=99).map(
            lambda i: f"step-{i:03d}"
        ),
        "sort": st.integers(min_value=1, max_value=99),
        "instruction": st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
            min_size=3,
            max_size=50,
        ),
        "step_type": st.sampled_from(["navigation", "validation", "url"]),
    }),
    min_size=1,
    max_size=5,
)


def _build_step_results(steps: list, failure_index: int | None) -> list:
    """Build a list of StepResult objects with an optional failure at failure_index."""
    results = []
    for i in range(len(steps)):
        if failure_index is not None and i == failure_index:
            results.append(StepResult(success=False, act_id=f"act-{i}", logs=f"step {i} failed"))
        else:
            results.append(StepResult(success=True, act_id=f"act-{i}", logs=""))
    return results


class TestEngineStepExecutionPreservation:
    """Property 2: Preservation — Engine step execution behavior unchanged.

    **Validates: Requirements 3.1, 3.2**

    For any list of steps (1–5 steps, mix of success/failure), the engine:
    - Calls update_step_status for each step up to and including the first failure
    - Returns {"success": False} on failure or {"success": True} when all pass
    - Stops executing after the first failure

    These tests MUST PASS on unfixed code.
    """

    @given(steps=step_list_strategy)
    @settings(max_examples=30, deadline=10000)
    def test_all_steps_succeed_returns_success(self, steps: list):
        """When all steps succeed, result is {"success": True} and
        update_step_status is called for every step.

        **Validates: Requirements 3.2**
        """
        engine, execution_api = _build_engine()
        nova_cm, nova_instance = _build_nova_mock("session-ignored")

        # Build a step executor that always succeeds
        mock_step_executor = MagicMock()
        mock_step_executor.execute.return_value = StepResult(
            success=True, act_id="act-ok", logs=""
        )

        artifact_capture = MagicMock()
        artifact_capture.capture_step_screenshot.return_value = None
        artifact_uploader = MagicMock()

        with patch("src.execution.engine.NovaAct", return_value=nova_cm):
            with patch(
                "src.execution.engine.StepExecutor",
                return_value=mock_step_executor,
            ):
                result = engine._run_steps_with_nova(
                    nova_kwargs={"starting_page": "https://example.com"},
                    steps=steps,
                    variables={},
                    headers={},
                    starting_url="https://example.com",
                    usecase_id="uc-001",
                    execution_id="exec-001",
                    artifact_capture=artifact_capture,
                    artifact_uploader=artifact_uploader,
                    logs_dir="/tmp/logs",
                )

        assert result["success"] is True
        assert "error" not in result

        # update_step_status called once per step
        assert execution_api.update_step_status.call_count == len(steps)

        # All calls should have status="success"
        for call in execution_api.update_step_status.call_args_list:
            assert call.kwargs.get("status") == "success" or \
                   (len(call.args) >= 4 and call.args[3] == "success") or \
                   call[1].get("status") == "success"

    @given(
        steps=step_list_strategy,
        data=st.data(),
    )
    @settings(max_examples=30, deadline=10000)
    def test_first_failure_stops_execution(self, steps: list, data):
        """When a step fails, execution stops at that step and result is
        {"success": False}. update_step_status is called for each step
        up to and including the failing one.

        **Validates: Requirements 3.2**
        """
        failure_index = data.draw(
            st.integers(min_value=0, max_value=len(steps) - 1)
        )

        engine, execution_api = _build_engine()
        nova_cm, nova_instance = _build_nova_mock("session-ignored")

        step_results = _build_step_results(steps, failure_index)
        call_counter = {"i": 0}

        def execute_side_effect(resolved_step, variables, runtime_variables):
            idx = call_counter["i"]
            call_counter["i"] += 1
            return step_results[idx]

        mock_step_executor = MagicMock()
        mock_step_executor.execute.side_effect = execute_side_effect

        artifact_capture = MagicMock()
        artifact_capture.capture_step_screenshot.return_value = None
        artifact_uploader = MagicMock()

        with patch("src.execution.engine.NovaAct", return_value=nova_cm):
            with patch(
                "src.execution.engine.StepExecutor",
                return_value=mock_step_executor,
            ):
                result = engine._run_steps_with_nova(
                    nova_kwargs={"starting_page": "https://example.com"},
                    steps=steps,
                    variables={},
                    headers={},
                    starting_url="https://example.com",
                    usecase_id="uc-001",
                    execution_id="exec-001",
                    artifact_capture=artifact_capture,
                    artifact_uploader=artifact_uploader,
                    logs_dir="/tmp/logs",
                )

        assert result["success"] is False
        assert "error" in result

        # Steps executed: 0..failure_index (inclusive)
        expected_calls = failure_index + 1
        assert execution_api.update_step_status.call_count == expected_calls

    @given(steps=step_list_strategy)
    @settings(max_examples=20, deadline=10000)
    def test_step_executor_receives_resolved_instructions(self, steps: list):
        """StepExecutor.execute is called once per step (until failure)
        with the step data including resolved instruction.

        **Validates: Requirements 3.2**
        """
        engine, execution_api = _build_engine()
        nova_cm, nova_instance = _build_nova_mock("session-ignored")

        mock_step_executor = MagicMock()
        mock_step_executor.execute.return_value = StepResult(
            success=True, act_id="act-ok", logs=""
        )

        artifact_capture = MagicMock()
        artifact_capture.capture_step_screenshot.return_value = None
        artifact_uploader = MagicMock()

        with patch("src.execution.engine.NovaAct", return_value=nova_cm):
            with patch(
                "src.execution.engine.StepExecutor",
                return_value=mock_step_executor,
            ):
                engine._run_steps_with_nova(
                    nova_kwargs={"starting_page": "https://example.com"},
                    steps=steps,
                    variables={},
                    headers={},
                    starting_url="https://example.com",
                    usecase_id="uc-001",
                    execution_id="exec-001",
                    artifact_capture=artifact_capture,
                    artifact_uploader=artifact_uploader,
                    logs_dir="/tmp/logs",
                )

        assert mock_step_executor.execute.call_count == len(steps)


class TestSessionIdFailureResilience:
    """Preservation: Session ID failure resilience.

    **Validates: Requirements 3.4**

    On unfixed code, there is no session ID capture code at all, so these
    tests pass trivially. After the fix, they verify that a failing
    nova.get_session_id() does not interrupt step execution.
    """

    @given(step=single_step_strategy)
    @settings(max_examples=10, deadline=10000)
    def test_step_execution_completes_when_get_session_id_raises(self, step: dict):
        """When nova.get_session_id() raises an exception, step execution
        still completes and returns results.

        **Validates: Requirements 3.4**

        On unfixed code: get_session_id is never called, so the exception
        is never triggered — steps execute normally. This test passes trivially.
        After the fix: the try/except around get_session_id ensures steps
        still execute.
        """
        engine, execution_api = _build_engine()

        nova_instance = MagicMock()
        nova_instance.get_session_id.side_effect = RuntimeError("session ID unavailable")
        nova_instance.page = MagicMock()
        nova_instance.go_to_url = MagicMock()

        nova_cm = MagicMock()
        nova_cm.__enter__ = Mock(return_value=nova_instance)
        nova_cm.__exit__ = Mock(return_value=False)

        mock_step_executor = _build_step_executor_mock(success=True)

        artifact_capture = MagicMock()
        artifact_capture.capture_step_screenshot.return_value = None
        artifact_uploader = MagicMock()

        with patch("src.execution.engine.NovaAct", return_value=nova_cm):
            with patch(
                "src.execution.engine.StepExecutor",
                return_value=mock_step_executor,
            ):
                result = engine._run_steps_with_nova(
                    nova_kwargs={"starting_page": "https://example.com"},
                    steps=[step],
                    variables={},
                    headers={},
                    starting_url="https://example.com",
                    usecase_id="uc-001",
                    execution_id="exec-001",
                    artifact_capture=artifact_capture,
                    artifact_uploader=artifact_uploader,
                    logs_dir="/tmp/logs",
                )

        # Steps must still execute and succeed
        assert result["success"] is True
        mock_step_executor.execute.assert_called_once()
        execution_api.update_step_status.assert_called_once()

    @given(step=single_step_strategy)
    @settings(max_examples=10, deadline=10000)
    def test_step_execution_completes_when_get_session_id_returns_none(self, step: dict):
        """When nova.get_session_id() returns None, step execution still
        completes normally.

        **Validates: Requirements 3.4**
        """
        engine, execution_api = _build_engine()

        nova_instance = MagicMock()
        nova_instance.get_session_id.return_value = None
        nova_instance.page = MagicMock()
        nova_instance.go_to_url = MagicMock()

        nova_cm = MagicMock()
        nova_cm.__enter__ = Mock(return_value=nova_instance)
        nova_cm.__exit__ = Mock(return_value=False)

        mock_step_executor = _build_step_executor_mock(success=True)

        artifact_capture = MagicMock()
        artifact_capture.capture_step_screenshot.return_value = None
        artifact_uploader = MagicMock()

        with patch("src.execution.engine.NovaAct", return_value=nova_cm):
            with patch(
                "src.execution.engine.StepExecutor",
                return_value=mock_step_executor,
            ):
                result = engine._run_steps_with_nova(
                    nova_kwargs={"starting_page": "https://example.com"},
                    steps=[step],
                    variables={},
                    headers={},
                    starting_url="https://example.com",
                    usecase_id="uc-001",
                    execution_id="exec-001",
                    artifact_capture=artifact_capture,
                    artifact_uploader=artifact_uploader,
                    logs_dir="/tmp/logs",
                )

        assert result["success"] is True
        mock_step_executor.execute.assert_called_once()
