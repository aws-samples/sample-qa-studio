"""Token data model for persisted authentication tokens."""

from pydantic import BaseModel, Field


class TokenData(BaseModel):
    """Persisted token data in ~/.qa-studio/token.json."""

    access_token: str = Field(
        ..., min_length=1, description="JWT access token from Cognito"
    )
    refresh_token: str = Field(
        ..., min_length=1, description="Refresh token for obtaining new access tokens"
    )
    expires_at: int = Field(
        ..., gt=0, description="Unix timestamp when access_token expires"
    )
    token_type: str = Field(
        default="Bearer", description="Token type, always Bearer"
    )
