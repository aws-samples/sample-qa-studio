"""Test suite API operations for the runner."""

from typing import Any, Dict, List, Optional

from qa_studio_cli.api.client import ApiClient


class TestSuiteAPI:
    """Test suite API operations."""

    def __init__(self, client: ApiClient):
        self.client = client

    def get_suite(self, suite_id: str) -> Dict[str, Any]:
        """Fetch test suite definition."""
        return self.client.get(f"/api/test-suites/{suite_id}")

    def execute_suite(
        self,
        suite_id: str,
        base_url: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
        region: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute test suite (CI/CD runner mode).

        Creates a suite execution record and execution records for all
        usecases in the test suite with overrides applied.
        """
        payload: Dict[str, Any] = {"trigger_type": "ci_runner"}
        if base_url is not None:
            payload["base_url"] = base_url
        if variables is not None:
            payload["variables"] = variables
        if region is not None:
            payload["region"] = region
        if model_id is not None:
            payload["model_id"] = model_id
        return self.client.post(f"/api/test-suites/{suite_id}/execute", json_body=payload)

    def list_usecases(self, suite_id: str) -> List[Dict[str, Any]]:
        """List use cases belonging to a test suite."""
        response = self.client.get(f"/api/test-suites/{suite_id}/usecases")
        return response.get("usecases", [])
