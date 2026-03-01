"""Unit tests for ExecutionAPI.

**Validates: Requirements 2.2**

Tests for the update_session_id method added to support Nova Act session ID
persistence from the qa-studio-ci-runner path.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch
from src.api.executions import ExecutionAPI
from src.utils.errors import APIError


def _run(coro):
    """Helper to run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestUpdateSessionId:
    """Tests for ExecutionAPI.update_session_id."""

    def _make_api(self) -> tuple:
        """Create an ExecutionAPI with a mocked client."""
        mock_client = MagicMock()
        mock_client.patch.return_value = {"status": "running", "execution_id": "exec-1"}
        api = ExecutionAPI(client=mock_client)
        return api, mock_client

    def test_calls_patch_with_correct_url_and_payload(self):
        """update_session_id calls client.patch with the right URL and body.

        **Validates: Requirements 2.2**
        """
        api, mock_client = self._make_api()

        result = _run(api.update_session_id(
            usecase_id="uc-123",
            execution_id="exec-456",
            session_id="session-abc-789",
        ))

        mock_client.patch.assert_called_once_with(
            "/usecase/uc-123/executions/exec-456/status",
            {"status": "running", "nova_session_id": "session-abc-789"},
        )
        assert result == {"status": "running", "execution_id": "exec-1"}

    def test_propagates_api_errors(self):
        """update_session_id propagates APIError from the client.

        **Validates: Requirements 2.2**
        """
        api, mock_client = self._make_api()
        mock_client.patch.side_effect = APIError(
            "API request failed: 500 - Internal Server Error",
            status_code=500,
            response={"error": "Internal Server Error"},
        )

        with pytest.raises(APIError) as exc_info:
            _run(api.update_session_id(
                usecase_id="uc-123",
                execution_id="exec-456",
                session_id="session-abc-789",
            ))

        assert exc_info.value.status_code == 500


class TestExistingMethodsUnchanged:
    """Preservation: existing methods still work as before.

    **Validates: Requirements 3.3**
    """

    def _make_api(self) -> tuple:
        mock_client = MagicMock()
        mock_client.patch.return_value = {"ok": True}
        mock_client.get.return_value = {"steps": []}
        api = ExecutionAPI(client=mock_client)
        return api, mock_client

    def test_update_status_still_works(self):
        """update_status sends status and optional error_message."""
        api, mock_client = self._make_api()

        _run(api.update_status("uc-1", "exec-1", "failed", error_message="boom"))

        mock_client.patch.assert_called_once_with(
            "/usecase/uc-1/executions/exec-1/status",
            {"status": "failed", "error_message": "boom"},
        )

    def test_update_step_status_still_works(self):
        """update_step_status sends step payload correctly."""
        api, mock_client = self._make_api()

        _run(api.update_step_status(
            "uc-1", "exec-1", "step-1", "success",
            actual_value="val", act_id="act-1",
        ))

        mock_client.patch.assert_called_once_with(
            "/usecase/uc-1/executions/exec-1/steps/step-1/status",
            {"status": "success", "actual_value": "val", "act_id": "act-1"},
        )

    def test_update_suite_status_still_works(self):
        """update_suite_status sends suite payload correctly."""
        api, mock_client = self._make_api()

        _run(api.update_suite_status("suite-1", "se-1", "running"))

        mock_client.patch.assert_called_once_with(
            "/test-suites/suite-1/executions/se-1/status",
            {"status": "running"},
        )
