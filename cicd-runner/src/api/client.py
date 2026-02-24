"""Base API client with authentication."""

import requests
from typing import Optional, Dict, Any
from ..auth.oauth_client import OAuthClient
from ..utils.errors import APIError


class APIClient:
    """Base API client with authentication."""
    
    def __init__(self, base_url: str, oauth_client: OAuthClient):
        """
        Initialize API client.
        
        Args:
            base_url: Platform API base URL
            oauth_client: OAuth client for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.oauth_client = oauth_client
        self.session = requests.Session()
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Get request headers with authentication.
        
        Returns:
            Headers dict with Authorization and Content-Type
        """
        access_token = self.oauth_client.get_access_token()
        return {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
    
    def get(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make authenticated GET request.
        
        Args:
            path: API path (e.g., "/test-suites/123")
            params: Optional query parameters
            
        Returns:
            Parsed JSON response
            
        Raises:
            APIError: If request fails
        """
        url = f"{self.base_url}{path}"
        response = self.session.get(url, headers=self._get_headers(), params=params)
        return self._handle_response(response)
    
    def post(self, path: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make authenticated POST request.
        
        Args:
            path: API path
            data: Optional JSON body
            
        Returns:
            Parsed JSON response
            
        Raises:
            APIError: If request fails
        """
        url = f"{self.base_url}{path}"
        response = self.session.post(url, headers=self._get_headers(), json=data)
        return self._handle_response(response)
    
    def patch(self, path: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make authenticated PATCH request.
        
        Args:
            path: API path
            data: Optional JSON body
            
        Returns:
            Parsed JSON response
            
        Raises:
            APIError: If request fails
        """
        url = f"{self.base_url}{path}"
        response = self.session.patch(url, headers=self._get_headers(), json=data)
        return self._handle_response(response)
    
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        Handle API response and errors.
        
        Args:
            response: HTTP response object
            
        Returns:
            Parsed JSON response
            
        Raises:
            APIError: If status code >= 400
        """
        if response.status_code >= 400:
            # Try to parse response as JSON, fallback to empty dict
            try:
                response_body = response.json() if response.text else {}
            except Exception:
                response_body = {}
            
            raise APIError(
                f"API request failed: {response.status_code} - {response.text}",
                status_code=response.status_code,
                response=response_body
            )
        
        # Return parsed JSON or empty dict if no content
        return response.json() if response.text else {}
