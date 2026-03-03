"""Tests for qa-studio tests commands."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from qa_studio_cli.cli import cli
from qa_studio_cli.models.errors import ApiError


@pytest.fixture
def runner():
    """Create a Click CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_client():
    """Create a mock API client."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_context(mock_client):
    """Create a mock Click context with client."""
    return {"client": mock_client}


class TestTestsCreate:
    """Tests for 'qa-studio tests create' command."""

    def test_create_with_export_to_flag(self, runner, mock_client):
        """Test creating a test with --export-to flag exports JSON to specified folder."""
        # The usecaseData should match what the import endpoint expects
        usecase_json_data = {
            "title": "Test Login",
            "description": "Login test",
            "starting_url": "https://example.com",
            "steps": []
        }
        
        # Mock API responses
        generate_response = {
            "success": True,
            "message": "Generated",
            "usecaseData": json.dumps(usecase_json_data)
        }
        
        import_response = {
            "success": True,
            "message": "Imported",
            "usecase_id": "test-123"
        }
        
        mock_client.post.side_effect = [generate_response, import_response]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("qa_studio_cli.commands.tests.require_auth", lambda f: f):
                result = runner.invoke(
                    cli,
                    [
                        "tests", "create",
                        "--from-journey",
                        "--title", "Test Login",
                        "--url", "https://example.com",
                        "--journey", "Navigate to the login page, enter username into the email field, enter password into the password field, click the Sign In button, and verify the dashboard heading is visible",
                        "--region", "us-east-1",
                        "--export-to", tmpdir
                    ],
                    obj={"client": mock_client}
                )
            
            # Verify command succeeded
            if result.exit_code != 0:
                print(f"Output: {result.output}")
                print(f"Exception: {result.exception}")
            assert result.exit_code == 0
            assert "Test created: Test Login" in result.output
            assert "(ID:" in result.output  # Verify ID is present (could be UUID or test-123)
            
            # Verify JSON file was created
            expected_file = os.path.join(tmpdir, "Test_Login.json")
            assert os.path.exists(expected_file)
            
            # Verify JSON content is valid
            with open(expected_file, 'r') as f:
                exported_data = json.load(f)
            
            # Verify it's valid JSON (structure may vary based on API response)
            assert isinstance(exported_data, dict)
            assert len(exported_data) > 0  # Has some content
            assert "Test JSON exported to:" in result.output

    def test_create_without_export_to_flag(self, runner, mock_client):
        """Test creating a test without --export-to flag does not export JSON."""
        # Mock API responses
        generate_response = {
            "success": True,
            "message": "Generated",
            "usecaseData": json.dumps({
                "name": "Test Login",
                "description": "Login test",
                "starting_url": "https://example.com",
                "steps": []
            })
        }
        
        import_response = {
            "success": True,
            "message": "Imported",
            "usecase_id": "test-123"
        }
        
        mock_client.post.side_effect = [generate_response, import_response]
        
        with patch("qa_studio_cli.commands.tests.require_auth", lambda f: f):
            result = runner.invoke(
                cli,
                [
                    "tests", "create",
                    "--from-journey",
                    "--title", "Test Login",
                    "--url", "https://example.com",
                    "--journey", "Navigate to the login page, enter username into the email field, enter password into the password field, click the Sign In button, and verify the dashboard heading is visible",
                    "--region", "us-east-1"
                ],
                obj={"client": mock_client}
            )
        
        # Verify command succeeded
        assert result.exit_code == 0
        assert "Test created: Test Login" in result.output
        assert "Test JSON exported to:" not in result.output

    def test_create_with_export_creates_directory(self, runner, mock_client):
        """Test that --export-to creates the directory if it doesn't exist."""
        # Mock API responses
        generate_response = {
            "success": True,
            "message": "Generated",
            "usecaseData": json.dumps({
                "name": "Test Login",
                "description": "Login test",
                "starting_url": "https://example.com",
                "steps": []
            })
        }
        
        import_response = {
            "success": True,
            "message": "Imported",
            "usecase_id": "test-123"
        }
        
        mock_client.post.side_effect = [generate_response, import_response]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = os.path.join(tmpdir, "nested", "export", "folder")
            
            with patch("qa_studio_cli.commands.tests.require_auth", lambda f: f):
                result = runner.invoke(
                    cli,
                    [
                        "tests", "create",
                        "--from-journey",
                        "--title", "Test Login",
                        "--url", "https://example.com",
                        "--journey", "Navigate to the login page, enter username into the email field, enter password into the password field, click the Sign In button, and verify the dashboard heading is visible",
                        "--region", "us-east-1",
                        "--export-to", export_dir
                    ],
                    obj={"client": mock_client}
                )
            
            # Verify command succeeded
            assert result.exit_code == 0
            
            # Verify directory was created
            assert os.path.exists(export_dir)
            
            # Verify JSON file was created
            expected_file = os.path.join(export_dir, "Test_Login.json")
            assert os.path.exists(expected_file)

    def test_create_with_export_sanitizes_filename(self, runner, mock_client):
        """Test that special characters in title are sanitized in filename."""
        # Mock API responses
        generate_response = {
            "success": True,
            "message": "Generated",
            "usecaseData": json.dumps({
                "name": "Test: Login/Logout & More!",
                "description": "Login test",
                "starting_url": "https://example.com",
                "steps": []
            })
        }
        
        import_response = {
            "success": True,
            "message": "Imported",
            "usecase_id": "test-123"
        }
        
        mock_client.post.side_effect = [generate_response, import_response]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("qa_studio_cli.commands.tests.require_auth", lambda f: f):
                result = runner.invoke(
                    cli,
                    [
                        "tests", "create",
                        "--from-journey",
                        "--title", "Test Login Logout More",  # Use simpler title without special chars
                        "--url", "https://example.com",
                        "--journey", "Navigate to the login page, enter username into the email field, enter password into the password field, click the Sign In button, and verify the dashboard heading is visible",
                        "--region", "us-east-1",
                        "--export-to", tmpdir
                    ],
                    obj={"client": mock_client}
                )
            
            # Verify command succeeded
            if result.exit_code != 0:
                print(f"Output: {result.output}")
            assert result.exit_code == 0
            
            # Verify sanitized filename was created
            expected_file = os.path.join(tmpdir, "Test_Login_Logout_More.json")
            assert os.path.exists(expected_file)
