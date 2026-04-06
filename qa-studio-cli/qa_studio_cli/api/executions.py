"""Execution API operations with async wrappers."""

import asyncio
import logging
from typing import Any, Dict, Optional

from qa_studio_cli.api.client import ApiClient

logger = logging.getLogger(__name__)


class ExecutionAPI:
    """Execution API operations with async support."""

    def __init__(self, client: ApiClient):
        self.client = client

    async def get_execution(
        self, usecase_id: str, execution_id: str
    ) -> Dict[str, Any]:
        """Fetch execution details including steps and variables.

        Makes multiple API calls to compose the full execution object:
        1. GET /api/usecase/{id}/executions/{executionId}
        2. GET /api/usecase/{id}/executions/{executionId}/steps
        3. GET /api/usecase/{id}/executions/{executionId}/variables
        """
        execution = await asyncio.to_thread(
            self.client.get,
            f"/api/usecase/{usecase_id}/executions/{execution_id}",
        )

        try:
            steps_response = await asyncio.to_thread(
                self.client.get,
                f"/api/usecase/{usecase_id}/executions/{execution_id}/steps",
            )
            execution["steps"] = steps_response.get("steps", [])
        except Exception as e:
            logger.warning("Failed to fetch steps: %s", e)
            execution["steps"] = []

        try:
            vars_response = await asyncio.to_thread(
                self.client.get,
                f"/api/usecase/{usecase_id}/executions/{execution_id}/variables",
            )
            exec_vars = vars_response.get("execution_variables", {})
            if isinstance(exec_vars, dict) and exec_vars:
                execution["variables"] = exec_vars
            else:
                raw_vars = vars_response.get("variables", [])
                variables = {}
                if isinstance(raw_vars, list):
                    for v in raw_vars:
                        if isinstance(v, dict) and "key" in v and "value" in v:
                            variables[v["key"]] = v["value"]
                elif isinstance(raw_vars, dict):
                    variables = raw_vars
                execution["variables"] = variables
        except Exception as e:
            logger.warning("Failed to fetch variables: %s", e)
            execution["variables"] = {}

        return execution

    async def update_status(
        self,
        usecase_id: str,
        execution_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update execution status."""
        payload = {"status": status}
        if error_message is not None:
            payload["error_message"] = error_message
        return await asyncio.to_thread(
            self.client.patch,
            f"/api/usecase/{usecase_id}/executions/{execution_id}/status",
            payload,
        )

    async def update_suite_status(
        self,
        suite_id: str,
        suite_execution_id: str,
        status: str,
    ) -> Dict[str, Any]:
        """Update suite execution status."""
        return await asyncio.to_thread(
            self.client.patch,
            f"/api/test-suites/{suite_id}/executions/{suite_execution_id}/status",
            {"status": status},
        )

    async def update_step_status(
        self,
        usecase_id: str,
        execution_id: str,
        step_id: str,
        status: str,
        error_message: Optional[str] = None,
        actual_value: Optional[str] = None,
        act_id: Optional[str] = None,
        logs: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update individual step status via API."""
        payload: Dict[str, Any] = {"status": status}
        if error_message is not None:
            payload["error_message"] = error_message
        if actual_value is not None:
            payload["actual_value"] = actual_value
        if act_id is not None:
            payload["act_id"] = act_id
        if logs is not None:
            payload["logs"] = logs
        return await asyncio.to_thread(
            self.client.patch,
            f"/api/usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/status",
            payload,
        )

    async def update_session_id(
        self,
        usecase_id: str,
        execution_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """Persist Nova Act session ID to the execution record."""
        return await asyncio.to_thread(
            self.client.patch,
            f"/api/usecase/{usecase_id}/executions/{execution_id}/status",
            {"status": "running", "nova_session_id": session_id},
        )

    def get_secret_value(self, usecase_id: str, secret_key: str) -> Optional[str]:
        """Fetch the decrypted value of a usecase secret via API."""
        try:
            response = self.client.get(
                f"/api/usecase/{usecase_id}/secrets/{secret_key}/value"
            )
            return response.get("value")
        except Exception:
            return None

    async def request_recording_download(
        self,
        usecase_id: str,
        execution_id: str,
        session_arn: str,
        nova_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Request async Device Farm recording download via the Studio API."""
        payload: Dict[str, Any] = {"session_arn": session_arn}
        if nova_session_id:
            payload["nova_session_id"] = nova_session_id
        return await asyncio.to_thread(
            self.client.post,
            f"/api/usecase/{usecase_id}/executions/{execution_id}/download-recording",
            json_body=payload,
        )

