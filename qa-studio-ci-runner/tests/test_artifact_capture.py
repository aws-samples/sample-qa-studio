"""Unit tests for ArtifactCapture class."""

import pytest
import logging
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from src.execution.artifacts import ArtifactCapture


class TestArtifactCapture:
    """Test ArtifactCapture functionality."""
    
    def test_init_creates_temp_directory(self, tmp_path):
        """Test that initialization creates temporary directory."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        assert capture.execution_id == execution_id
        assert capture.temp_dir == artifact_dir
        assert capture.temp_dir.exists()
        assert capture.recording_path is None
        assert capture.log_path is None
        assert capture.step_artifacts == {}
    
    def test_init_with_existing_directory(self, tmp_path):
        """Test initialization with existing directory doesn't fail."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        
        # Create directory first
        artifact_dir.mkdir(parents=True)
        
        # Should not raise exception
        capture = ArtifactCapture(execution_id, artifact_dir)
        assert capture.temp_dir.exists()
    
    def test_setup_recording_creates_correct_path(self, tmp_path):
        """Test setup_recording() creates correct path."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        recording_path = capture.setup_recording()
        
        assert recording_path == artifact_dir / "recording.webm"
        assert capture.recording_path == recording_path
        assert recording_path.suffix == ".webm"
    
    def test_setup_logs_creates_file_handler(self, tmp_path):
        """Test setup_logs() creates file handler and log file path."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        # Get initial handler count
        root_logger = logging.getLogger()
        initial_handler_count = len(root_logger.handlers)
        
        log_path = capture.setup_logs()
        
        assert log_path == artifact_dir / "logs.txt"
        assert capture.log_path == log_path
        assert log_path.suffix == ".txt"
        
        # Verify handler was added
        assert len(root_logger.handlers) > initial_handler_count
        
        # Clean up handler
        for handler in root_logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                if str(log_path) in str(handler.baseFilename):
                    handler.close()
                    root_logger.removeHandler(handler)
    
    def test_capture_step_screenshot_success(self, tmp_path):
        """Test successful screenshot capture."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        # Mock Nova Act page object (synchronous)
        nova_page = Mock()
        nova_page.screenshot = Mock()
        
        step_id = 'step-456'
        step_number = 1
        
        # Capture screenshot
        screenshot_path = capture.capture_step_screenshot(
            nova_page, step_id, step_number
        )
        
        # Verify
        assert screenshot_path == artifact_dir / "step_1_screenshot.png"
        assert screenshot_path.suffix == ".png"
        nova_page.screenshot.assert_called_once_with(path=str(screenshot_path))
        
        # Verify stored in step_artifacts
        assert step_id in capture.step_artifacts
        assert capture.step_artifacts[step_id]['screenshot'] == screenshot_path
    
    def test_capture_step_screenshot_failure_returns_none(self, tmp_path):
        """Test screenshot capture failure returns None."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        # Mock page that raises exception
        nova_page = Mock()
        nova_page.screenshot = Mock(side_effect=Exception("Screenshot failed"))
        
        step_id = 'step-456'
        step_number = 1
        
        # Capture screenshot - should not raise exception
        screenshot_path = capture.capture_step_screenshot(
            nova_page, step_id, step_number
        )
        
        # Verify returns None on failure
        assert screenshot_path is None
        
        # Verify step_artifacts not updated
        assert step_id not in capture.step_artifacts
    
    def test_capture_step_trace_success(self, tmp_path):
        """Test successful trace capture."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        step_id = 'step-456'
        step_number = 1
        
        # Capture trace with data
        trace_path = capture.capture_step_trace(
            step_id, step_number, trace_data='{"trace": "data"}'
        )
        
        # Verify
        assert trace_path == artifact_dir / "step_1_trace.json"
        assert trace_path.suffix == ".json"
        assert trace_path.read_text() == '{"trace": "data"}'
        
        # Verify stored in step_artifacts
        assert step_id in capture.step_artifacts
        assert capture.step_artifacts[step_id]['trace'] == trace_path
    
    def test_capture_step_trace_no_data_returns_none(self, tmp_path):
        """Test trace capture without data returns None."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        step_id = 'step-456'
        step_number = 1
        
        # Capture trace without data
        trace_path = capture.capture_step_trace(step_id, step_number)
        
        # Verify returns None
        assert trace_path is None
        assert step_id not in capture.step_artifacts
    
    def test_capture_multiple_artifacts_for_same_step(self, tmp_path):
        """Test capturing both screenshot and trace for same step."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        # Mock page
        nova_page = Mock()
        nova_page.screenshot = Mock()
        
        step_id = 'step-456'
        step_number = 1
        
        # Capture both artifacts
        screenshot_path = capture.capture_step_screenshot(
            nova_page, step_id, step_number
        )
        trace_path = capture.capture_step_trace(
            step_id, step_number, trace_data='{"trace": "data"}'
        )
        
        # Verify both stored in step_artifacts
        assert step_id in capture.step_artifacts
        assert capture.step_artifacts[step_id]['screenshot'] == screenshot_path
        assert capture.step_artifacts[step_id]['trace'] == trace_path
    
    def test_get_execution_artifacts_returns_only_existing_files(self, tmp_path):
        """Test get_execution_artifacts() returns only existing files."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        # Setup recording path but don't create file
        capture.setup_recording()
        
        # Should return empty dict since recording file doesn't exist
        artifacts = capture.get_execution_artifacts()
        assert artifacts == {}
        
        # Create recording file
        capture.recording_path.touch()
        
        # Should return only recording
        artifacts = capture.get_execution_artifacts()
        assert 'recording' in artifacts
        assert artifacts['recording'] == capture.recording_path
        assert 'logs' not in artifacts
        
        # Setup logs (this creates the log file via FileHandler)
        log_path = capture.setup_logs()
        
        # Should return both now
        artifacts = capture.get_execution_artifacts()
        assert 'recording' in artifacts
        assert 'logs' in artifacts
        assert artifacts['recording'] == capture.recording_path
        assert artifacts['logs'] == log_path
        
        # Clean up handler
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                if str(log_path) in str(handler.baseFilename):
                    handler.close()
                    root_logger.removeHandler(handler)
    
    def test_get_execution_artifacts_without_setup(self, tmp_path):
        """Test get_execution_artifacts() when setup methods not called."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        # Should return empty dict
        artifacts = capture.get_execution_artifacts()
        assert artifacts == {}
    
    def test_get_step_artifacts_returns_correct_artifacts(self, tmp_path):
        """Test get_step_artifacts() returns correct artifacts for step."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        # Manually add step artifacts
        step_id_1 = 'step-456'
        step_id_2 = 'step-789'
        
        capture.step_artifacts[step_id_1] = {
            'screenshot': Path('/tmp/screenshot1.png'),
            'trace': Path('/tmp/trace1.json')
        }
        capture.step_artifacts[step_id_2] = {
            'screenshot': Path('/tmp/screenshot2.png')
        }
        
        # Get artifacts for step 1
        artifacts_1 = capture.get_step_artifacts(step_id_1)
        assert len(artifacts_1) == 2
        assert 'screenshot' in artifacts_1
        assert 'trace' in artifacts_1
        
        # Get artifacts for step 2
        artifacts_2 = capture.get_step_artifacts(step_id_2)
        assert len(artifacts_2) == 1
        assert 'screenshot' in artifacts_2
        assert 'trace' not in artifacts_2
    
    def test_get_step_artifacts_for_nonexistent_step(self, tmp_path):
        """Test get_step_artifacts() for step that doesn't exist."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        # Should return empty dict
        artifacts = capture.get_step_artifacts('nonexistent-step')
        assert artifacts == {}
    
    def test_cleanup_removes_temporary_directory(self, tmp_path):
        """Test cleanup() removes temporary directory."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        # Create some files
        capture.setup_recording()
        capture.recording_path.touch()
        
        # Verify directory exists
        assert capture.temp_dir.exists()
        
        # Cleanup
        capture.cleanup()
        
        # Verify directory removed
        assert not capture.temp_dir.exists()
    
    def test_cleanup_handles_nonexistent_directory(self, tmp_path):
        """Test cleanup() handles already removed directory."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        # Remove directory manually
        capture.temp_dir.rmdir()
        
        # Cleanup should not raise exception
        capture.cleanup()
    
    def test_cleanup_handles_permission_error(self, tmp_path):
        """Test cleanup() handles permission errors gracefully."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        # Mock shutil.rmtree to raise exception
        with patch('shutil.rmtree', side_effect=PermissionError("Permission denied")):
            # Should not raise exception
            capture.cleanup()

    def test_close_log_handler_without_cleanup(self, tmp_path):
        """Test close_log_handler() closes handler but keeps files."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        # Setup logs (creates file handler)
        capture.setup_logs()
        assert capture._log_handler is not None
        assert capture.log_path.exists()
        
        # Close handler only
        capture.close_log_handler()
        
        # Handler should be removed
        assert capture._log_handler is None
        # Files should still exist
        assert capture.temp_dir.exists()
        assert capture.log_path.exists()
    
    def test_close_log_handler_idempotent(self, tmp_path):
        """Test close_log_handler() can be called multiple times safely."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        # Call without setup — should not raise
        capture.close_log_handler()
        capture.close_log_handler()
    
    def test_cleanup_calls_close_log_handler(self, tmp_path):
        """Test cleanup() closes log handler before deleting files."""
        execution_id = 'test-exec-123'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)
        
        capture.setup_logs()
        assert capture._log_handler is not None
        
        capture.cleanup()
        
        assert capture._log_handler is None
        assert not capture.temp_dir.exists()


class TestSetupLogsThreadFilter:
    """Tests for ThreadLogFilter integration in ArtifactCapture.setup_logs()."""

    def test_setup_logs_attaches_thread_filter(self, tmp_path):
        """Verify ThreadLogFilter is added to the file handler."""
        from src.utils.log_filters import ThreadLogFilter

        execution_id = 'test-exec-filter'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)

        capture.setup_logs()

        try:
            handler = capture._log_handler
            assert handler is not None
            thread_filters = [f for f in handler.filters if isinstance(f, ThreadLogFilter)]
            assert len(thread_filters) == 1
        finally:
            capture.close_log_handler()

    def test_setup_logs_thread_filter_uses_current_thread(self, tmp_path):
        """Verify the ThreadLogFilter initially uses the calling thread's ID."""
        import threading
        from src.utils.log_filters import ThreadLogFilter

        execution_id = 'test-exec-thread'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)

        expected_thread_id = threading.get_ident()
        capture.setup_logs()

        try:
            handler = capture._log_handler
            thread_filters = [f for f in handler.filters if isinstance(f, ThreadLogFilter)]
            assert len(thread_filters) == 1
            assert thread_filters[0].thread_id == expected_thread_id
        finally:
            capture.close_log_handler()

    def test_bind_to_current_thread_updates_filter(self, tmp_path):
        """Verify bind_to_current_thread rebinds the filter to a different thread."""
        import threading
        from src.utils.log_filters import ThreadLogFilter

        execution_id = 'test-exec-rebind'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)

        capture.setup_logs()

        try:
            # Initially bound to main thread
            main_thread_id = threading.get_ident()
            assert capture._thread_filter.thread_id == main_thread_id

            # Rebind from a worker thread
            worker_thread_id = None

            def worker():
                nonlocal worker_thread_id
                worker_thread_id = threading.get_ident()
                capture.bind_to_current_thread()

            t = threading.Thread(target=worker)
            t.start()
            t.join()

            assert worker_thread_id is not None
            assert capture._thread_filter.thread_id == worker_thread_id
            assert capture._thread_filter.thread_id != main_thread_id
        finally:
            capture.close_log_handler()

    def test_bind_to_current_thread_isolates_logs(self, tmp_path):
        """Verify that after bind_to_current_thread, only worker thread logs are captured."""
        import threading

        execution_id = 'test-exec-isolate'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)

        capture.setup_logs()

        try:
            test_logger = logging.getLogger('test.isolation')

            def worker():
                capture.bind_to_current_thread()
                test_logger.warning('WORKER_LOG')

            t = threading.Thread(target=worker)
            t.start()
            t.join()

            # Log from main thread — should NOT be captured
            test_logger.warning('MAIN_THREAD_LOG')

            capture._log_handler.flush()

            log_content = capture.log_path.read_text()
            assert 'WORKER_LOG' in log_content
            assert 'MAIN_THREAD_LOG' not in log_content
        finally:
            capture.close_log_handler()

    def test_bind_to_current_thread_enables_nova_act_propagation(self, tmp_path):
        """Verify bind_to_current_thread sets propagate=True on nova_act loggers."""
        import threading

        execution_id = 'test-exec-nova'
        artifact_dir = tmp_path / execution_id
        capture = ArtifactCapture(execution_id, artifact_dir)

        capture.setup_logs()

        try:
            # Simulate nova_act logger with propagate=False (as the SDK sets it)
            nova_logger = logging.getLogger('nova_act.test_propagation')
            nova_logger.propagate = False

            def worker():
                capture.bind_to_current_thread()

            t = threading.Thread(target=worker)
            t.start()
            t.join()

            assert nova_logger.propagate is True
        finally:
            capture.close_log_handler()
            # Clean up the test logger
            del logging.Logger.manager.loggerDict['nova_act.test_propagation']
