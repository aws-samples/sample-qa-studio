import pytest

try:
    import nova_act  # noqa: F401
    HAS_RUNNER = True
except ImportError:
    HAS_RUNNER = False

requires_runner = pytest.mark.skipif(
    not HAS_RUNNER,
    reason="Runner extras not installed (pip install qa-studio[runner])",
)


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


@pytest.fixture
def tmp_kiro_dir(tmp_path):
    """Provide a temporary ~/.kiro/ directory."""
    kiro_dir = tmp_path / ".kiro"
    kiro_dir.mkdir()
    return kiro_dir


@pytest.fixture
def tmp_skills_source(tmp_path):
    """Create a temporary bundled skills directory with the unified qa-studio skill."""
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "qa-studio"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: qa-studio\ndescription: Test skill\n---\n"
    )
    ref_dir = skill_dir / "reference"
    ref_dir.mkdir()
    (ref_dir / "step-types.md").write_text("# Step Types\n")
    return skills_dir


from unittest.mock import MagicMock, patch

from click.testing import CliRunner


@pytest.fixture
def cli_runner():
    """Provide a Click CliRunner for command tests."""
    return CliRunner()


@pytest.fixture
def mock_api_client():
    """Provide a mock ApiClient for command tests."""
    return MagicMock()


@pytest.fixture
def auth_context(mock_api_client):
    """Patch require_auth to inject mock client without real auth."""
    with (
        patch("qa_studio_cli.api.client.config_exists", return_value=True),
        patch("qa_studio_cli.api.client.load_config") as mock_config,
        patch("qa_studio_cli.api.client.get_valid_token", return_value="test-token"),
    ):
        mock_config.return_value = MagicMock(api_url="https://api.qa-studio.example.com")
        yield mock_api_client
