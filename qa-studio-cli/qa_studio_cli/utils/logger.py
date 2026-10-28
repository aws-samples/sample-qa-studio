"""Logging configuration for the runner."""

import logging
import sys
from pathlib import Path
from typing import Union

from qa_studio_cli.utils.log_filters import (
    NoisyLibraryFilter,
    NovaActLogFilter,
    SecretRedactionFilter,
)

ARTIFACT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def add_safety_filters(handler: logging.Handler) -> logging.Handler:
    """Attach the filters every handler needs before writing logs anywhere.

    - NoisyLibraryFilter: drops botocore/urllib3 DEBUG output, which contains
      SigV4 signing details and the STS session token.
    - SecretRedactionFilter: masks resolved secret values, bearer tokens,
      JWTs, and credential key/value pairs.
    """
    handler.addFilter(NoisyLibraryFilter())
    handler.addFilter(SecretRedactionFilter())
    return handler


def create_artifact_file_handler(log_path: Union[str, Path]) -> logging.FileHandler:
    """Create the DEBUG file handler used for uploaded log artifacts."""
    handler = logging.FileHandler(log_path)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(ARTIFACT_LOG_FORMAT))
    return add_safety_filters(handler)


def setup_logging(verbose: bool) -> None:
    """Configure logging for the runner.

    Args:
        verbose: If True, set logging level to DEBUG. Otherwise, INFO.
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    console_handler.addFilter(NovaActLogFilter())
    add_safety_filters(console_handler)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
