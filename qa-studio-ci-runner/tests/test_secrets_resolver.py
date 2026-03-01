"""Tests for secrets resolution in the CI runner.

Covers:
1. ExecutionAPI.get_secret_value calls the correct API endpoint
2. Engine passes secrets_resolver to StepExecutor
3. StepExecutor uses the resolver for secret steps
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
from src.api.executions import ExecutionAPI
from src.api.client import APIClient
from src.execution.engine import ExecutionEngine
from src.execution.models import StepResult


class TestExecutionAPIGetSecretValue(unittest.TestCase):
    """Tests for ExecutionAPI.get_secret_value."""

    def _build_api(self):
        mock_client = Mock(spec=APIClient)
        return ExecutionAPI(client=mock_client), mock_client

    def test_returns_value_on_success(self):
        """Calls GET /usecase/{id}/secrets/{key}/value and returns the value."""
        api, mock_client = self._build_api()
        mock_client.get.return_value = {"key": "db_password", "value": "s3cret"}

        result = api.get_secret_value("uc-123", "db_password")

        self.assertEqual(result, "s3cret")
        mock_client.get.assert_called_once_with(
            "/usecase/uc-123/secrets/db_password/value"
        )

    def test_returns_none_on_api_error(self):
        """Returns None when the API call raises an exception."""
        api, mock_client = self._build_api()
        mock_client.get.side_effect = Exception("404 Not Found")

        result = api.get_secret_value("uc-123", "nonexistent")

        self.assertIsNone(result)

    def test_returns_none_when_value_missing(self):
        """Returns None when response has no 'value' key."""
        api, mock_client = self._build_api()
        mock_client.get.return_value = {"key": "db_password"}

        result = api.get_secret_value("uc-123", "db_password")

        self.assertIsNone(result)


class TestEngineSecretsResolverWiring(unittest.TestCase):
    """Tests that the engine passes secrets_resolver to StepExecutor."""

    def _build_engine(self):
        mock_client = Mock()
        execution_api = ExecutionAPI(client=mock_client)
        engine = ExecutionEngine(
            execution_api=execution_api,
            suite_execution_id="suite-exec-001",
        )
        return engine, execution_api

    def _build_nova_mock(self):
        nova_instance = MagicMock()
        nova_instance.get_session_id.return_value = "session-123"
        nova_instance.page = MagicMock()
        nova_cm = MagicMock()
        nova_cm.__enter__ = Mock(return_value=nova_instance)
        nova_cm.__exit__ = Mock(return_value=False)
        return nova_cm, nova_instance

    def test_step_executor_receives_secrets_resolver(self):
        """StepExecutor is instantiated with secrets_resolver=execution_api.get_secret_value."""
        engine, execution_api = self._build_engine()
        execution_api.update_session_id = MagicMock()
        nova_cm, _ = self._build_nova_mock()

        mock_step_executor = MagicMock()
        mock_step_executor.execute.return_value = StepResult(success=True)

        step = {
            "sk": "EXECUTION_STEP#step-1",
            "sort": 1,
            "instruction": "Click login",
            "step_type": "navigation",
        }

        artifact_capture = MagicMock()
        artifact_capture.capture_step_screenshot.return_value = None
        artifact_uploader = MagicMock()

        with patch("src.execution.engine.NovaAct", return_value=nova_cm):
            with patch(
                "src.execution.engine.StepExecutor",
                return_value=mock_step_executor,
            ) as mock_se_cls:
                with patch("src.execution.engine.WorkflowManager"):
                    with patch("src.execution.engine.Workflow") as mock_wf:
                        mock_wf_instance = MagicMock()
                        mock_wf.return_value.__enter__ = Mock(return_value=mock_wf_instance)
                        mock_wf.return_value.__exit__ = Mock(return_value=False)

                        engine._execute_with_nova_act(
                            execution_details={
                                "starting_url": "https://example.com",
                                "steps": [step],
                                "variables": {},
                                "headers": {},
                            },
                            usecase_id="uc-001",
                            execution_id="exec-001",
                            artifact_capture=artifact_capture,
                            artifact_uploader=artifact_uploader,
                        )

                # Verify StepExecutor was called with secrets_resolver
                mock_se_cls.assert_called_once()
                call_kwargs = mock_se_cls.call_args
                self.assertIn("secrets_resolver", call_kwargs.kwargs)
                self.assertEqual(
                    call_kwargs.kwargs["secrets_resolver"],
                    execution_api.get_secret_value,
                )


if __name__ == "__main__":
    unittest.main()
