"""Execution API operations with async wrappers."""

import asyncio
from typing import Dict, Any, Optional
from .client import APIClient


class ExecutionAPI:
    """Execution API operations with async support."""
    
    def __init__(self, client: APIClient):
        """
        Initialize execution API.
        
        Args:
            client: Base API client with authentication
        """
        self.client = client
    
    async def get_execution(
        self,
        usecase_id: str,
        execution_id: str
    ) -> Dict[str, Any]:
        """
        Fetch execution details including steps and variables.
        
        Makes multiple API calls to compose the full execution object:
        1. GET /usecase/{id}/executions/{executionId} - execution record
        2. GET /usecase/{id}/executions/{executionId}/steps - execution steps
        3. GET /usecase/{id}/executions/{executionId}/variables - variables
        
        Args:
            usecase_id: Usecase UUID
            execution_id: Execution UUID
        
        Returns:
            Execution details with steps, variables, starting_url, etc.
        
        Raises:
            APIError: If request fails
        """
        # Fetch execution record
        execution = await asyncio.to_thread(
            self.client.get,
            f"/usecase/{usecase_id}/executions/{execution_id}"
        )
        
        # Fetch execution steps
        try:
            steps_response = await asyncio.to_thread(
                self.client.get,
                f"/usecase/{usecase_id}/executions/{execution_id}/steps"
            )
            execution['steps'] = steps_response.get('steps', [])
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to fetch steps: {e}")
            execution['steps'] = []
        
        # Fetch execution variables
        try:
            vars_response = await asyncio.to_thread(
                self.client.get,
                f"/usecase/{usecase_id}/executions/{execution_id}/variables"
            )
            # Prefer merged execution_variables (includes CLI overrides)
            # Fall back to usecase-level variables
            exec_vars = vars_response.get('execution_variables', {})
            if isinstance(exec_vars, dict) and exec_vars:
                execution['variables'] = exec_vars
            else:
                raw_vars = vars_response.get('variables', [])
                variables = {}
                if isinstance(raw_vars, list):
                    for v in raw_vars:
                        if isinstance(v, dict) and 'key' in v and 'value' in v:
                            variables[v['key']] = v['value']
                elif isinstance(raw_vars, dict):
                    variables = raw_vars
                execution['variables'] = variables
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to fetch variables: {e}")
            execution['variables'] = {}
        
        return execution
    
    async def update_status(
        self,
        usecase_id: str,
        execution_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update execution status.
        
        Args:
            usecase_id: Usecase UUID
            execution_id: Execution UUID
            status: New status (pending, running, completed, failed)
            error_message: Optional error message for failed executions
        
        Returns:
            API response
        
        Raises:
            APIError: If request fails
        """
        payload = {'status': status}
        if error_message is not None:
            payload['error_message'] = error_message
        
        return await asyncio.to_thread(
            self.client.patch,
            f"/usecase/{usecase_id}/executions/{execution_id}/status",
            payload
        )
    
    async def update_suite_status(
        self,
        suite_id: str,
        suite_execution_id: str,
        status: str
    ) -> Dict[str, Any]:
        """
        Update suite execution status.
        
        Args:
            suite_id: Suite UUID
            suite_execution_id: Suite execution UUID
            status: New status (pending, running, completed, failed)
        
        Returns:
            API response
        
        Raises:
            APIError: If request fails
        """
        return await asyncio.to_thread(
            self.client.patch,
            f"/test-suites/{suite_id}/executions/{suite_execution_id}/status",
            {'status': status}
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
        """
        Update individual step status via API.

        Args:
            usecase_id: Usecase UUID
            execution_id: Execution UUID
            step_id: Step UUID
            status: New status (completed, failed)
            error_message: Optional error message for failed steps
            actual_value: Optional actual value for validation/retrieve_value steps
            act_id: Optional Nova Act action ID for trace linking
            logs: Optional step execution logs

        Returns:
            API response

        Raises:
            APIError: If request fails
        """
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
            f"/usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/status",
            payload,
        )
    async def update_session_id(
        self,
        usecase_id: str,
        execution_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Persist Nova Act session ID to the execution record.

        Sends a PATCH with status "running" (idempotent — execution is already
        running at this point) plus the nova_session_id field.

        Args:
            usecase_id: Usecase UUID
            execution_id: Execution UUID
            session_id: Nova Act session ID string

        Returns:
            API response

        Raises:
            APIError: If request fails
        """
        return await asyncio.to_thread(
            self.client.patch,
            f"/usecase/{usecase_id}/executions/{execution_id}/status",
            {"status": "running", "nova_session_id": session_id},
        )


