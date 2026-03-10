"""OAuth client-credentials flow with in-memory token caching."""

from datetime import datetime, timedelta

import requests

from qa_studio_cli.models.errors import AuthError

# Scopes matching the existing runner's client-credentials request.
M2M_SCOPES = (
    "api/suite.read api/suite.write "
    "api/usecases.read api/usecases.execute "
    "api/executions.read api/executions.write"
)


class ClientCredentialsProvider:
    """OAuth client-credentials flow with in-memory token caching."""

    def __init__(self, client_id: str, client_secret: str, token_endpoint: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_endpoint = token_endpoint
        self._access_token: str | None = None
        self._expires_at: datetime | None = None

    def get_token(self) -> str:
        """Return cached token or request a new one.

        Raises:
            AuthError: If the token request fails.
        """
        if self._access_token and not self._is_expired():
            return self._access_token
        return self._request_token()

    def _request_token(self) -> str:
        """POST to token endpoint with client_credentials grant.

        Raises:
            AuthError: On HTTP errors or network failures.
        """
        try:
            response = requests.post(
                self._token_endpoint,
                auth=(self._client_id, self._client_secret),
                data={
                    "grant_type": "client_credentials",
                    "scope": M2M_SCOPES,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except requests.exceptions.RequestException as e:
            raise AuthError(f"OAuth token request failed: {e}")

        if response.status_code != 200:
            raise AuthError(
                f"OAuth authentication failed: {response.status_code} - {response.text}"
            )

        data = response.json()
        expires_in = data.get("expires_in", 3600)
        self._access_token = data["access_token"]
        from datetime import datetime, timezone
        self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        return self._access_token

    def _is_expired(self) -> bool:
        """True if token is expired or expires within 5 minutes."""
        if not self._expires_at:
            return True
        from datetime import datetime, timezone
        return datetime.now(timezone.utc) >= (self._expires_at - timedelta(minutes=5))
