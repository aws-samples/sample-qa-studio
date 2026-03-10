"""Artifact capture during test execution."""

import logging
import shutil
import threading
from pathlib import Path
from typing import Dict, Optional

from qa_studio_cli.utils.log_filters import ThreadLogFilter

logger = logging.getLogger(__name__)


class ArtifactCapture:
    """Capture artifacts during test execution."""

    def __init__(self, execution_id: str, temp_dir: Path):
        self.execution_id = execution_id
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        self.recording_path = None
        self.log_path = None
        self.step_artifacts: Dict[str, Dict[str, Path]] = {}
        self._log_handler = None
        self._thread_filter = None

    def setup_recording(self) -> Path:
        """Setup video recording path."""
        self.recording_path = self.temp_dir / "recording.webm"
        return self.recording_path

    def setup_logs(self) -> Path:
        """Setup log file path and configure logging."""
        self.log_path = self.temp_dir / "logs.txt"

        file_handler = logging.FileHandler(self.log_path)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))

        self._thread_filter = ThreadLogFilter(threading.get_ident())
        file_handler.addFilter(self._thread_filter)
        logging.getLogger().addHandler(file_handler)
        self._log_handler = file_handler
        return self.log_path

    def bind_to_current_thread(self) -> None:
        """Re-bind the log filter to the calling thread's ID."""
        if self._thread_filter is not None:
            self._thread_filter.thread_id = threading.get_ident()

        for name in list(logging.Logger.manager.loggerDict):
            if name.startswith("nova_act"):
                nova_logger = logging.getLogger(name)
                nova_logger.propagate = True

    def capture_step_screenshot(
        self,
        nova_page,
        step_id: str,
        step_number: int,
    ) -> Optional[Path]:
        """Capture screenshot after step execution."""
        try:
            screenshot_path = self.temp_dir / f"step_{step_number}_screenshot.png"
            nova_page.screenshot(path=str(screenshot_path))

            if step_id not in self.step_artifacts:
                self.step_artifacts[step_id] = {}
            self.step_artifacts[step_id]["screenshot"] = screenshot_path

            logger.debug("Captured screenshot for step %d", step_number)
            return screenshot_path
        except Exception as e:
            logger.warning("Failed to capture screenshot for step %d: %s", step_number, e)
            return None

    def capture_step_trace(
        self,
        step_id: str,
        step_number: int,
        trace_data: Optional[str] = None,
    ) -> Optional[Path]:
        """Capture trace data for step."""
        try:
            trace_path = self.temp_dir / f"step_{step_number}_trace.json"
            if trace_data:
                trace_path.write_text(trace_data)
            else:
                return None

            if step_id not in self.step_artifacts:
                self.step_artifacts[step_id] = {}
            self.step_artifacts[step_id]["trace"] = trace_path

            logger.debug("Captured trace for step %d", step_number)
            return trace_path
        except Exception as e:
            logger.warning("Failed to capture trace for step %d: %s", step_number, e)
            return None

    def get_execution_artifacts(self) -> Dict[str, Path]:
        """Get paths to execution-level artifacts."""
        artifacts = {}
        if self.recording_path and self.recording_path.exists():
            artifacts["recording"] = self.recording_path
        if self.log_path and self.log_path.exists():
            artifacts["logs"] = self.log_path
        return artifacts

    def get_step_artifacts(self, step_id: str) -> Dict[str, Path]:
        """Get paths to step-level artifacts."""
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
                logger.debug("Cleaned up temporary artifacts: %s", self.temp_dir)
            except Exception as e:
                logger.warning("Failed to cleanup artifacts: %s", e)
