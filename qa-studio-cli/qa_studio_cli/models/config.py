"""CLI configuration model."""

from pydantic import BaseModel, Field, field_validator


class CLIConfig(BaseModel):
    """Persisted CLI configuration in ~/.qa-studio/config.json."""

    api_url: str = Field(..., description="QA Studio API base URL")
    cognito_domain: str = Field(..., description="Cognito hosted UI domain")
    client_id: str = Field(
        ..., min_length=1, description="Cognito app client ID (public)"
    )

    @field_validator("api_url", "cognito_domain")
    @classmethod
    def validate_https_url(cls, v: str) -> str:
        """Validate URL starts with https:// and strip trailing slashes."""
        if not v.startswith("https://"):
            raise ValueError("URL must start with https://")
        return v.rstrip("/")
