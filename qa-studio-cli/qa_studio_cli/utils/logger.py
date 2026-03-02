"""Logging configuration for the runner."""

import logging
import sys

from qa_studio_cli.utils.log_filters import NovaActLogFilter


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

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
