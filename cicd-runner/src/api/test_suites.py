"""Test suite API operations."""

from typing import Dict, Any, Optional
from .client import APIClient


class TestSuiteAPI:
    """Test suite API operations."""
    
    def __init__(self, client: APIClient):
        """
        Initialize test suite API.
        
        Args:
            client: Base API client
        """
        self.client = client
    
    def get_suite(self, suite_id: str) -> Dict[str, Any]:
        """
        Fetch test suite definition.
        
        Args:
            suite_id: Test suite UUID
            
        Returns:
            Test suite object with name, usecases, etc.
            
        Raises:
            APIError: If request fails
        """
        return self.client.get(f"/test-suites/{suite_id}")
    
    def execute_suite(
        self,
        suite_id: str,
        base_url: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
        region: Optional[str] = None,
        model_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute test suite (CI/CD runner mode).
        
        Creates a suite execution record and execution records for all usecases
        in the test suite with overrides applied. Does not spawn ECS tasks.
        
        Args:
            suite_id: Test suite UUID
            base_url: Optional base URL override for all usecases
            variables: Optional variable overrides (key-value pairs)
            region: Optional AWS region override for all executions
            model_id: Optional Bedrock model ID override for all executions
            
        Returns:
            Execution response with suite_execution_id and execution_ids
            
        Raises:
            APIError: If request fails
        """
        payload = {
            'trigger_type': 'ci_runner'
        }
        
        if base_url is not None:
            payload['base_url'] = base_url
        if variables is not None:
            payload['variables'] = variables
        if region is not None:
            payload['region'] = region
        if model_id is not None:
            payload['model_id'] = model_id
        
        return self.client.post(f"/test-suites/{suite_id}/execute", data=payload)
