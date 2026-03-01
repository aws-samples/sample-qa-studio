import pytest


@pytest.fixture
def tmp_qa_studio_dir(tmp_path):
    """Provide a temporary directory for ~/.qa-studio/ during tests."""
    qa_studio_dir = tmp_path / ".qa-studio"
    qa_studio_dir.mkdir()
    return qa_studio_dir


@pytest.fixture
def mock_token_data():
    """Return a sample TokenData dict."""
    return {
        "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test-access-token",
        "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test-refresh-token",
        "expires_at": 1999999999,
        "token_type": "Bearer",
    }


@pytest.fixture
def mock_config_data():
    """Return a sample CLIConfig dict."""
    return {
        "api_url": "https://api.qa-studio.example.com",
        "cognito_domain": "https://auth.qa-studio.example.com",
        "client_id": "test-client-id-abc123",
    }
