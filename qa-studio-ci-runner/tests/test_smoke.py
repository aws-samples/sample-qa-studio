"""Smoke tests to verify core functionality."""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from src.main import determine_exit_code, validate_aws_session
from src.output.summary import SummaryFormatter
from src.utils.errors import ExecutionError, RunnerError, sanitize_error_message


class TestExitCodeLogic:
    """Test exit code determination."""
    
    def test_exit_code_0_all_passed(self):
        """Verify exit code 0 when all tests pass."""
        results = [
            {'status': 'success', 'usecase_name': 'Test 1'},
            {'status': 'success', 'usecase_name': 'Test 2'},
        ]
        assert determine_exit_code(results) == 0
    
    def test_exit_code_1_some_failed(self):
        """Verify exit code 1 when tests fail."""
        results = [
            {'status': 'success', 'usecase_name': 'Test 1'},
            {'status': 'failed', 'usecase_name': 'Test 2'},
        ]
        assert determine_exit_code(results) == 1
    
    def test_exit_code_2_no_results(self):
        """Verify exit code 2 when no results."""
        results = []
        assert determine_exit_code(results) == 2


class TestSummaryFormatter:
    """Test summary output formatting."""
    
    def test_format_duration_seconds(self):
        """Verify duration formatting for seconds."""
        assert SummaryFormatter._format_duration(45) == "45s"
    
    def test_format_duration_minutes(self):
        """Verify duration formatting for minutes."""
        assert SummaryFormatter._format_duration(150) == "2m 30s"
    
    def test_format_duration_hours(self):
        """Verify duration formatting for hours."""
        assert SummaryFormatter._format_duration(4500) == "1h 15m"
    
    def test_format_table_structure(self):
        """Verify table structure is correct."""
        results = [
            {
                'usecase_name': 'Login Test',
                'status': 'success',
                'duration': 45
            },
            {
                'usecase_name': 'Logout Test',
                'status': 'failed',
                'duration': 30
            }
        ]

        start_time = datetime(2024, 2, 16, 12, 0, 0)
        end_time = datetime(2024, 2, 16, 12, 5, 30)

        table = SummaryFormatter.format_table(
            suite_name='Test Suite',
            suite_execution_id='test-123',
            results=results,
            start_time=start_time,
            end_time=end_time
        )

        # Verify key elements are present
        assert 'QA Studio - CI/CD Runner' in table
        assert 'Suite: Test Suite' in table
        assert 'Suite Execution ID: test-123' in table
        assert '✓ Login Test (45s)' in table
        assert '✗ Logout Test (30s)' in table
        assert 'Total: 2' in table
        assert 'Passed: 1' in table
        assert 'Failed: 1' in table
        assert 'Success: 50%' in table
        # Verify no box-drawing characters
        assert '╔' not in table
        assert '║' not in table


class TestErrorHandling:
    """Test error handling utilities."""
    
    def test_execution_error_creation(self):
        """Test ExecutionError can be created."""
        error = ExecutionError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
    
    def test_sanitize_error_message_urls(self):
        """Test URL sanitization."""
        message = "Failed to connect to https://example.com?token=secret123"
        sanitized = sanitize_error_message(message)
        assert "secret123" not in sanitized
        assert "https://example.com?[REDACTED]" in sanitized
    
    def test_sanitize_error_message_emails(self):
        """Test email sanitization."""
        message = "Error from user@example.com"
        sanitized = sanitize_error_message(message)
        assert "user@example.com" not in sanitized
        assert "[EMAIL_REDACTED]" in sanitized
    
    def test_sanitize_error_message_tokens(self):
        """Test token path sanitization."""
        message = "Failed at /token/abc123/endpoint"
        sanitized = sanitize_error_message(message)
        assert "abc123" not in sanitized
        assert "/token/[REDACTED]" in sanitized


class TestValidateAwsSession:
    """Test AWS session validation."""

    @patch('src.main.boto3')
    def test_valid_session_passes(self, mock_boto3):
        """Verify no error when STS returns a valid identity."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            'Account': '123456789012',
            'Arn': 'arn:aws:iam::123456789012:user/test',
            'UserId': 'AIDEXAMPLE'
        }
        mock_boto3.client.return_value = mock_sts
        validate_aws_session()  # should not raise

    @patch('src.main.boto3')
    def test_missing_credentials_raises_runner_error(self, mock_boto3):
        """Verify clear RunnerError when AWS credentials are missing."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.side_effect = Exception("Unable to locate credentials")
        mock_boto3.client.return_value = mock_sts
        with pytest.raises(RunnerError, match="No valid AWS session found"):
            validate_aws_session()

    @patch('src.main.boto3')
    def test_expired_credentials_raises_runner_error(self, mock_boto3):
        """Verify clear RunnerError when AWS credentials are expired."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.side_effect = Exception("ExpiredToken")
        mock_boto3.client.return_value = mock_sts
        with pytest.raises(RunnerError, match="No valid AWS session found"):
            validate_aws_session()

