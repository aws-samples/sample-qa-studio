"""Use case API operations."""

from typing import Dict, Any, List, Optional
from .client import APIClient


class UseCaseAPI:
    """Use case API operations for fetching definitions and triggering execution."""

    def __init__(self, client: APIClient):
        """
        Initialize use case API.

        Args:
            client: Base API client with authentication
        """
        self.client = client

    def get_usecase(self, usecase_id: str) -> Dict[str, Any]:
        """
        Fetch use case metadata.

        Args:
            usecase_id: Use case UUID

        Returns:
            Use case object with name, starting_url, executing_region, model_id, etc.

        Raises:
            APIError: If request fails
        """
        return self.client.get(f"/usecase/{usecase_id}")

    def get_steps(self, usecase_id: str) -> List[Dict[str, Any]]:
        """
        Fetch use case steps.

        Args:
            usecase_id: Use case UUID

        Returns:
            List of step dicts

        Raises:
            APIError: If request fails
        """
        response = self.client.get(f"/usecase/{usecase_id}/steps")
        return response.get("steps", [])

    def get_variables(self, usecase_id: str) -> Dict[str, str]:
        """
        Fetch use case variables and parse to key-value dict.

        The API returns variables in list format:
            [{"key": "k", "value": "v"}, ...]

        This method parses them into a flat dict:
            {"k": "v", ...}

        Args:
            usecase_id: Use case UUID

        Returns:
            Variables as key-value dict

        Raises:
            APIError: If request fails
        """
        response = self.client.get(f"/usecase/{usecase_id}/variables")
        raw_vars = response.get("variables", [])
        variables: Dict[str, str] = {}
        if isinstance(raw_vars, list):
            for v in raw_vars:
                if isinstance(v, dict) and "key" in v and "value" in v:
                    variables[v["key"]] = v["value"]
        elif isinstance(raw_vars, dict):
            variables = raw_vars
        return variables

    def get_secrets(self, usecase_id: str) -> List[Dict[str, Any]]:
        """
        Fetch use case secrets.

        Args:
            usecase_id: Use case UUID

        Returns:
            List of secret dicts

        Raises:
            APIError: If request fails
        """
        return self.client.get(f"/usecase/{usecase_id}/secrets")

    def execute_usecase(
        self,
        usecase_id: str,
        base_url: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
        region: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute use case (creates execution record).

        Sends POST /usecase/{usecase_id}/execute with trigger_type=ci_runner
        and optional overrides.

        Args:
            usecase_id: Use case UUID
            base_url: Optional base URL override
            variables: Optional variable overrides (key-value pairs)
            region: Optional AWS region override
            model_id: Optional Bedrock model ID override

        Returns:
            Execution response with execution_id, etc.

        Raises:
            APIError: If request fails
        """
        payload: Dict[str, Any] = {
            "trigger_type": "ci_runner",
        }

        if base_url is not None:
            payload["base_url"] = base_url
        if variables is not None:
            payload["variables"] = variables
        if region is not None:
            payload["region"] = region
        if model_id is not None:
            payload["model_id"] = model_id

        return self.client.post(f"/usecase/{usecase_id}/execute", data=payload)
