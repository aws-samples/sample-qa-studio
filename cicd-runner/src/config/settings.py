"""Configuration management for the CI/CD runner."""

import os
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ValidationError
from ..utils.errors import ConfigurationError


class Settings(BaseModel):
    """Application settings loaded from environment variables."""
    
    oauth_client_id: str = Field(..., description="OAuth client ID from Cognito")
    oauth_client_secret: str = Field(..., description="OAuth client secret from Cognito")
    oauth_token_endpoint: str = Field(..., description="Cognito token endpoint URL")
    api_endpoint: str = Field(..., description="Platform API base URL")
    log_level: str = Field(default="INFO", description="Logging level")
    
    @field_validator('oauth_token_endpoint', 'api_endpoint')
    @classmethod
    def validate_https_url(cls, v: str, info) -> str:
        """
        Validate that URLs use HTTPS protocol.
        
        Args:
            v: URL value to validate
            info: Field validation info
            
        Returns:
            Validated URL
            
        Raises:
            ValueError: If URL is not HTTPS
        """
        if not v.startswith('https://'):
            raise ValueError(f'{info.field_name} must be an HTTPS URL')
        return v
    
    @classmethod
    def from_env(cls) -> 'Settings':
        """
        Load settings from environment variables.
        
        Environment variables:
            OAUTH_CLIENT_ID: OAuth client ID (required)
            OAUTH_CLIENT_SECRET: OAuth client secret (required)
            OAUTH_TOKEN_ENDPOINT: Cognito token endpoint URL (required)
            API_ENDPOINT: Platform API base URL (required)
            LOG_LEVEL: Logging level (optional, default: INFO)
        
        Returns:
            Validated Settings instance
            
        Raises:
            ConfigurationError: If required variables are missing or validation fails
        """
        try:
            return cls(
                oauth_client_id=os.environ['OAUTH_CLIENT_ID'],
                oauth_client_secret=os.environ['OAUTH_CLIENT_SECRET'],
                oauth_token_endpoint=os.environ['OAUTH_TOKEN_ENDPOINT'],
                api_endpoint=os.environ['API_ENDPOINT'],
                log_level=os.environ.get('LOG_LEVEL', 'INFO')
            )
        except KeyError as e:
            missing_var = e.args[0]
            raise ConfigurationError(f"Missing required environment variable: {missing_var}")
        except ValidationError as e:
            # Extract validation error details
            errors = []
            for error in e.errors():
                field = error['loc'][0]
                msg = error['msg']
                errors.append(f"{field}: {msg}")
            raise ConfigurationError(f"Configuration validation failed: {'; '.join(errors)}")
