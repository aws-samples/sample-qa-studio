"""Read access_token from a JSON file, re-reading on each call."""

import json
from pathlib import Path

from qa_studio_cli.models.errors import AuthError


class TokenFileProvider:
    """Read access_token from a JSON file, re-reading on each call.

    This supports externally refreshed tokens — the file is read fresh
    on every get_token() call, never cached.
    """

    def __init__(self, path: str):
        self._path = Path(path).expanduser()
        # Validate on init so we fail fast if the file is bad
        self.get_token()

    def get_token(self) -> str:
        """Read and return access_token from the JSON file.

        Raises:
            AuthError: If file doesn't exist, is invalid JSON, or
                       is missing the access_token field.
        """
        if not self._path.exists():
            raise AuthError(f"Token file not found: {self._path}")
        try:
            data = json.loads(self._path.read_text())
        except (json.JSONDecodeError, ValueError):
            raise AuthError(f"Failed to parse token file: {self._path}")

        token = data.get("access_token")
        if not token or not isinstance(token, str):
            raise AuthError(
                f"Token file missing valid 'access_token' field: {self._path}"
            )
        return token
