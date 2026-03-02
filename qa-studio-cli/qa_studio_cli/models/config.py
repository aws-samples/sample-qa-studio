"""CLI configuration model."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CLIConfig(BaseModel):
    """Persisted CLI configuration in ~/.qa-studio/config.json."""

    api_url: str = Field(..., description="QA Studio API base URL")
    cognito_domain: str = Field(..., description="Cognito hosted UI domain")
    client_id: str = Field(
        ..., min_length=1, description="Cognito app client ID (public)"
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

    @field_validator("api_url", "cognito_domain")
    @classmethod
    def validate_https_url(cls, v: str) -> str:
        """Validate URL starts with https:// and strip trailing slashes."""
        if not v.startswith("https://"):
            raise ValueError("URL must start with https://")
        return v.rstrip("/")

    @field_validator("oauth_token_endpoint")
    @classmethod
    def validate_optional_https_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate optional token endpoint uses HTTPS."""
        if v is not None and not v.startswith("https://"):
            raise ValueError("Token endpoint must start with https://")
        return v
