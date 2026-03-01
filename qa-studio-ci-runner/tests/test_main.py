"""Tests for suite log lifecycle integration in main.py."""

from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from src.main import run_runner


def _make_settings():
    """Create a mock Settings object with required attributes."""
    settings = MagicMock()
    settings.oauth_client_id = "test-client-id"
    settings.oauth_client_secret = "test-secret"
    settings.oauth_token_endpoint = "https://auth.example.com/token"
    settings.api_endpoint = "https://api.example.com"
    return settings


def _make_execution_response():
    return {
        "suite_execution_id": "suite-exec-123",
        "execution_ids": ["exec-1", "exec-2"],
    }


def _make_results(status="success"):
    return [
        {"status": status, "usecase_name": "Test 1", "duration": 10},
        {"status": status, "usecase_name": "Test 2", "duration": 20},
    ]


class TestRunRunnerSuiteLogCapture:
    """Tests for SuiteLogCapture wiring in run_runner()."""

    _SENTINEL = object()

    def _patch_and_run(self, suite_log_stop_return=_SENTINEL, upload_side_effect=None,
                       engine_side_effect=None):
        """Run run_runner() with all dependencies mocked.

        Returns a dict of mock instances for assertions.
        """
        mocks = {}

        with patch("src.main.Settings") as mock_settings_cls, \
             patch("src.main.validate_aws_session"), \
             patch("src.main.OAuthClient"), \
             patch("src.main.APIClient") as mock_api_client_cls, \
             patch("src.main.TestSuiteAPI") as mock_suite_api_cls, \
             patch("src.main.ExecutionAPI") as mock_exec_api_cls, \
             patch("src.main.ExecutionEngine") as mock_engine_cls, \
             patch("src.main.SummaryFormatter") as mock_formatter, \
             patch("src.main.SuiteLogCapture") as mock_slc_cls, \
             patch("src.main.ArtifactUploader") as mock_uploader_cls:

            # Settings
            mock_settings_cls.from_env.return_value = _make_settings()

            # API client
            api_client_instance = mock_api_client_cls.return_value
            mocks["api_client"] = api_client_instance

            # TestSuiteAPI
            suite_api = mock_suite_api_cls.return_value
            suite_api.get_suite.return_value = {"name": "My Suite"}
            suite_api.execute_suite.return_value = _make_execution_response()

            # ExecutionAPI
            exec_api = mock_exec_api_cls.return_value
            exec_api.update_suite_status = AsyncMock()

            # ExecutionEngine
            engine = mock_engine_cls.return_value
            if engine_side_effect:
                engine.execute_all = AsyncMock(side_effect=engine_side_effect)
            else:
                engine.execute_all = AsyncMock(return_value=_make_results())

            # SummaryFormatter
            mock_formatter.format_table.return_value = "summary"

            # SuiteLogCapture
            slc = mock_slc_cls.return_value
            slc.start.return_value = Path("/tmp/suite_logs.txt")
            if suite_log_stop_return is not self._SENTINEL:
                slc.stop.return_value = suite_log_stop_return
            else:
                slc.stop.return_value = Path("/tmp/suite_logs.txt")
            mocks["suite_log_capture_cls"] = mock_slc_cls
            mocks["suite_log_capture"] = slc

            # ArtifactUploader
            uploader = mock_uploader_cls.return_value
            if upload_side_effect:
                uploader.upload_suite_artifacts = AsyncMock(
                    side_effect=upload_side_effect
                )
            else:
                uploader.upload_suite_artifacts = AsyncMock()
            mocks["artifact_uploader_cls"] = mock_uploader_cls
            mocks["artifact_uploader"] = uploader

            with pytest.raises(SystemExit) as exc_info:
                run_runner(
                    suite_id="suite-123",
                    base_url=None,
                    variables={},
                    region=None,
                    model_id=None,
                    timeout=300,
                )

            mocks["exit_code"] = exc_info.value.code

        return mocks

    def test_run_runner_starts_suite_log_capture(self):
        """Verify SuiteLogCapture is created with suite_execution_id and start() is called."""
        mocks = self._patch_and_run()

        mocks["suite_log_capture_cls"].assert_called_once_with("suite-exec-123")
        mocks["suite_log_capture"].start.assert_called_once()

    def test_run_runner_stops_suite_log_capture_on_success(self):
        """Verify stop() is called when execution succeeds."""
        mocks = self._patch_and_run()

        mocks["suite_log_capture"].stop.assert_called_once()
        assert mocks["exit_code"] == 0

    def test_run_runner_stops_suite_log_capture_on_failure(self):
        """Verify stop() is called even when execution engine raises an error."""
        mocks = self._patch_and_run(
            engine_side_effect=RuntimeError("engine exploded")
        )

        mocks["suite_log_capture"].stop.assert_called_once()
        assert mocks["exit_code"] == 2

    def test_run_runner_uploads_suite_log(self):
        """Verify upload_suite_artifacts is called with correct args after stop()."""
        mocks = self._patch_and_run()

        mocks["artifact_uploader"].upload_suite_artifacts.assert_awaited_once_with(
            suite_id="suite-123",
            suite_execution_id="suite-exec-123",
            artifacts={"logs": Path("/tmp/suite_logs.txt")},
        )

    def test_run_runner_continues_on_upload_failure(self):
        """Verify exit code is based on test results, not upload success."""
        mocks = self._patch_and_run(
            upload_side_effect=RuntimeError("upload failed")
        )

        # Exit code should still be 0 (all tests passed), not 2
        assert mocks["exit_code"] == 0

    def test_run_runner_skips_upload_when_no_log_path(self):
        """Verify upload is skipped when suite_log_capture.stop() returns None."""
        mocks = self._patch_and_run(suite_log_stop_return=None)

        mocks["artifact_uploader"].upload_suite_artifacts.assert_not_awaited()
