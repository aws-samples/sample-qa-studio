"""OAuth client credentials authentication module."""

import requests
from datetime import datetime, timedelta
from typing import Optional
from ..utils.errors import AuthenticationError


class OAuthClient:
    """OAuth client credentials authentication."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_endpoint: str
    ):
        """
        Initialize OAuth client.

        Args:
            client_id: OAuth client ID from Cognito
            client_secret: OAuth client secret from Cognito
            token_endpoint: Cognito token endpoint URL
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_endpoint = token_endpoint
        self._access_token: Optional[str] = None
        self._expires_at: Optional[datetime] = None

    def get_access_token(self) -> str:
        """
        Get valid access token, using in-memory cache if available.

        Returns:
            Valid access token string

        Raises:
            AuthenticationError: If authentication fails
        """
        if self._access_token and not self._is_token_expired():
            return self._access_token

        return self._request_new_token()

    def _request_new_token(self) -> str:
        """
        Request new access token from Cognito.

        Returns:
            New access token string

        Raises:
            AuthenticationError: If token request fails
        """
        try:
            response = requests.post(
                self.token_endpoint,
                auth=(self.client_id, self.client_secret),
                data={
                    'grant_type': 'client_credentials',
                    'scope': 'api/suite.read api/suite.write api/usecases.read api/usecases.execute api/executions.read api/executions.write'
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )

            # Handle authentication errors
            if response.status_code in (400, 401):
                raise AuthenticationError(
                    f"OAuth authentication failed: {response.status_code} - {response.text}"
                )

            # Handle other HTTP errors
            if response.status_code != 200:
                raise AuthenticationError(
                    f"OAuth token request failed with status {response.status_code}: {response.text}"
                )

            token_data = response.json()

            # Cache in memory
            expires_in = token_data.get('expires_in', 3600)
            self._access_token = token_data['access_token']
            self._expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            return self._access_token

        except requests.exceptions.RequestException as e:
            # Handle network errors
            raise AuthenticationError(
                f"OAuth token request failed due to network error: {str(e)}"
            )

    def _is_token_expired(self) -> bool:
        """
        Check if token is expired or about to expire.

        Returns:
            True if token is expired or expires within 5 minutes
        """
        if not self._expires_at:
            return True

        # Consider expired if less than 5 minutes remaining
        buffer = timedelta(minutes=5)
        return datetime.utcnow() >= (self._expires_at - buffer)
