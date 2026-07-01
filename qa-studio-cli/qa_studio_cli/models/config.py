"""CLI configuration model."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CLIConfig(BaseModel):
    """Persisted CLI configuration in ~/.qa-studio/config.json.

    Required:
      - ``api_url`` — used by every execution path.

    Optional:
      - ``cognito_domain`` and ``client_id`` — only needed for the
        interactive user OAuth flow (``qa-studio login``).  The ECS
        worker container uses M2M client-credentials instead and never
        references them.  Leaving them out prevents "configure placeholder
        values" cruft in deployed environments.
      - ``oauth_client_id`` / ``oauth_client_secret`` /
        ``oauth_token_endpoint`` — the M2M auth triple.  Required in
        the worker container; optional for developer-workstation
        users who authenticate interactively.
    """

    api_url: str = Field(..., description="QA Studio API base URL")
    cognito_domain: Optional[str] = Field(
        default=None,
        description="Cognito hosted UI domain (required for interactive login)",
    )
    client_id: Optional[str] = Field(
        default=None,
        min_length=1,
        description=(
            "Cognito app client ID for the user-facing client "
            "(required for interactive login)"
        ),
    )

    # Optional M2M client credentials (for CI/runner auth)
    oauth_client_id: Optional[str] = Field(
        default=None, description="OAuth M2M client ID"
    )
    oauth_client_secret: Optional[str] = Field(
        default=None, description="OAuth M2M client secret"
    )
    oauth_token_endpoint: Optional[str] = Field(
        default=None, description="Cognito token endpoint URL"
    )

    # Optional web-app URL used by ``qa-studio tui`` to open use cases
    # for editing in the browser.  Unset ⇒ Edit action is disabled in
    # the TUI with a hint to re-run ``qa-studio configure``.
    web_url: Optional[str] = Field(
        default=None,
        description="QA Studio web app base URL (optional, TUI-only)",
    )

    @field_validator("api_url")
    @classmethod
    def validate_https_url(cls, v: str) -> str:
        """Validate URL starts with https:// and strip trailing slashes."""
        if not v.startswith("https://"):
            raise ValueError("URL must start with https://")
        return v.rstrip("/")

    @field_validator("cognito_domain")
    @classmethod
    def validate_optional_cognito_domain(cls, v: Optional[str]) -> Optional[str]:
        """Validate optional Cognito domain uses HTTPS."""
        if v is not None and not v.startswith("https://"):
            raise ValueError("URL must start with https://")
        return v.rstrip("/") if v is not None else v

    @field_validator("oauth_token_endpoint")
    @classmethod
    def validate_optional_https_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate optional token endpoint uses HTTPS."""
        if v is not None and not v.startswith("https://"):
            raise ValueError("Token endpoint must start with https://")
        return v

    @field_validator("web_url")
    @classmethod
    def validate_optional_web_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate optional web URL uses HTTPS; strip trailing slash."""
        if v is None:
            return None
        if not v.startswith("https://"):
            raise ValueError("Web URL must start with https://")
        return v.rstrip("/")
