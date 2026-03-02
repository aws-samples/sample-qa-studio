"""Use case API operations for the runner."""

from typing import Any, Dict, List, Optional

from qa_studio_cli.api.client import ApiClient


class UseCaseAPI:
    """Use case API operations for single use case execution."""

    def __init__(self, client: ApiClient):
        self.client = client

    def get_usecase(self, usecase_id: str) -> Dict[str, Any]:
        """Fetch use case metadata."""
        return self.client.get(f"/api/usecase/{usecase_id}")

    def get_steps(self, usecase_id: str) -> List[Dict[str, Any]]:
        """Fetch use case steps."""
        response = self.client.get(f"/api/usecase/{usecase_id}/steps")
        return response.get("steps", [])

    def get_variables(self, usecase_id: str) -> Dict[str, str]:
        """Fetch use case variables as a key-value dict.

        Handles both list format (list of {key, value} dicts) and
        dict format from the API.
        """
        response = self.client.get(f"/api/usecase/{usecase_id}/variables")
        raw_vars = response.get("variables", [])
        if isinstance(raw_vars, dict):
            return raw_vars
        if isinstance(raw_vars, list):
            variables = {}
            for v in raw_vars:
                if isinstance(v, dict) and "key" in v and "value" in v:
                    variables[v["key"]] = v["value"]
            return variables
        return {}

    def get_secrets(self, usecase_id: str) -> List[Dict[str, Any]]:
        """Fetch use case secrets."""
        response = self.client.get(f"/api/usecase/{usecase_id}/secrets")
        return response.get("secrets", [])

    def create_execution(
        self,
        usecase_id: str,
        trigger_type: str = "ci_runner",
        base_url: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
        region: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an execution record for a use case."""
        payload: Dict[str, Any] = {"trigger_type": trigger_type}
        if base_url is not None:
            payload["base_url"] = base_url
        if variables is not None:
            payload["variables"] = variables
        if region is not None:
            payload["region"] = region
        if model_id is not None:
            payload["model_id"] = model_id
        return self.client.post(f"/api/usecase/{usecase_id}/execute", json_body=payload)
