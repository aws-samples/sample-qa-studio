"""Suite-level log capture for the entire runner execution."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SuiteLogCapture:
    """Capture all logs for the entire suite execution into a single file."""

    def __init__(self, suite_execution_id: str):
        self.suite_execution_id = suite_execution_id
        self.log_dir = Path.home() / ".ci_runner" / suite_execution_id
        self.log_path = self.log_dir / "suite_logs.txt"
        self._handler: logging.FileHandler | None = None

    def start(self) -> Path | None:
        """Create log directory and attach file handler to root logger."""
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("Cannot create suite log directory: %s", e)
            return None

        handler = logging.FileHandler(self.log_path)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        logging.getLogger().addHandler(handler)
        self._handler = handler
        return self.log_path

    def stop(self) -> Path | None:
        """Flush and close the suite log handler. Returns path if log exists."""
        if self._handler:
            try:
                self._handler.flush()
                self._handler.close()
                logging.getLogger().removeHandler(self._handler)
            except Exception:
                pass
            self._handler = None
        return self.log_path if self.log_path.exists() else None
