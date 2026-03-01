"""Artifact capture during test execution."""

import logging
import shutil
import threading
from pathlib import Path
from typing import Dict, Optional

from src.utils.log_filters import ThreadLogFilter

logger = logging.getLogger(__name__)


class ArtifactCapture:
    """Capture artifacts during test execution."""
    
    def __init__(self, execution_id: str, temp_dir: Path):
        """
        Initialize artifact capture.
        
        Args:
            execution_id: Execution UUID
            temp_dir: Directory for storing artifacts
        """
        self.execution_id = execution_id
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        self.recording_path = None
        self.log_path = None
        self.step_artifacts = {}
        self._log_handler = None
        self._thread_filter = None
    
    def setup_recording(self) -> Path:
        """
        Setup video recording path.
        
        Returns:
            Path to recording file
        """
        self.recording_path = self.temp_dir / "recording.webm"
        return self.recording_path
    
    def setup_logs(self) -> Path:
        """
        Setup log file path and configure logging.
        
        The file handler is added immediately but the thread filter
        is not bound yet.  Call ``bind_to_current_thread()`` from the
        worker thread so that only logs from that thread are captured.
        
        Returns:
            Path to log file
        """
        self.log_path = self.temp_dir / "logs.txt"
        
        # Create file handler for this execution
        file_handler = logging.FileHandler(self.log_path)
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        
        # Attach a thread filter — thread ID will be set by bind_to_current_thread()
        self._thread_filter = ThreadLogFilter(threading.get_ident())
        file_handler.addFilter(self._thread_filter)

        # Add handler to root logger
        logging.getLogger().addHandler(file_handler)
        self._log_handler = file_handler
        
        return self.log_path

    def bind_to_current_thread(self) -> None:
        """Re-bind the log filter to the calling thread's ID.

        Must be called from the worker thread that actually executes
        the usecase so that only that thread's log records are captured.

        Also ensures nova_act loggers propagate to the root logger so
        their output is captured in the per-usecase log file.
        """
        if self._thread_filter is not None:
            self._thread_filter.thread_id = threading.get_ident()

        # Force nova_act loggers to propagate so their records reach
        # the root logger (and thus our file handler).  Nova Act's own
        # setup_logging sets propagate=False, which we need to override.
        for name in list(logging.Logger.manager.loggerDict):
            if name.startswith('nova_act'):
                nova_logger = logging.getLogger(name)
                nova_logger.propagate = True

    def capture_step_screenshot(
        self,
        nova_page,
        step_id: str,
        step_number: int,
    ) -> Optional[Path]:
        """
        Capture screenshot after step execution using Nova Act's page object.

        Args:
            nova_page: Nova Act page object (nova.page)
            step_id: Step UUID
            step_number: Step number for filename

        Returns:
            Path to screenshot file, or None if capture failed
        """
        try:
            screenshot_path = self.temp_dir / f"step_{step_number}_screenshot.png"
            nova_page.screenshot(path=str(screenshot_path))

            if step_id not in self.step_artifacts:
                self.step_artifacts[step_id] = {}
            self.step_artifacts[step_id]["screenshot"] = screenshot_path

            logger.debug(f"Captured screenshot for step {step_number}")
            return screenshot_path

        except Exception as e:
            logger.warning(f"Failed to capture screenshot for step {step_number}: {e}")
            return None

    def capture_step_trace(
        self,
        step_id: str,
        step_number: int,
        trace_data: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Capture trace data for step.

        Args:
            step_id: Step UUID
            step_number: Step number for filename
            trace_data: Optional trace content to write

        Returns:
            Path to trace file, or None if capture failed
        """
        try:
            trace_path = self.temp_dir / f"step_{step_number}_trace.json"
            if trace_data:
                trace_path.write_text(trace_data)
            else:
                return None

            if step_id not in self.step_artifacts:
                self.step_artifacts[step_id] = {}
            self.step_artifacts[step_id]["trace"] = trace_path

            logger.debug(f"Captured trace for step {step_number}")
            return trace_path

        except Exception as e:
            logger.warning(f"Failed to capture trace for step {step_number}: {e}")
            return None
    
    def get_execution_artifacts(self) -> Dict[str, Path]:
        """
        Get paths to execution-level artifacts.
        
        Returns:
            Dict mapping artifact type to file path
        """
        artifacts = {}
        
        if self.recording_path and self.recording_path.exists():
            artifacts['recording'] = self.recording_path
        
        if self.log_path and self.log_path.exists():
            artifacts['logs'] = self.log_path
        
        return artifacts
    
    def get_step_artifacts(self, step_id: str) -> Dict[str, Path]:
        """
        Get paths to step-level artifacts.
        
        Args:
            step_id: Step UUID
            
        Returns:
            Dict mapping artifact type to file path
        """
        return self.step_artifacts.get(step_id, {})
    
    def close_log_handler(self):
        """Close the log file handler without deleting files."""
        if self._log_handler:
            try:
                self._log_handler.close()
                logging.getLogger().removeHandler(self._log_handler)
            except Exception:
                pass
            self._log_handler = None

    def cleanup(self):
        """Clean up log handler and temporary artifact files."""
        self.close_log_handler()

        if self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
                logger.debug(f"Cleaned up temporary artifacts: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup artifacts: {e}")
