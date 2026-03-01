"""Logging configuration for the CI/CD runner."""

import logging
import sys

from .log_filters import NovaActLogFilter


def setup_logging(verbose: bool) -> None:
    """
    Configure logging for the CI/CD runner.
    
    Args:
        verbose: If True, set logging level to DEBUG. Otherwise, set to INFO.
    """
    # Determine logging level based on verbose flag
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Configure log format with timestamp, level, and message
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Configure console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    console_handler.addFilter(NovaActLogFilter())
    
    # Configure root logger — always DEBUG so file handlers get all records
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Remove any existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Add console handler
    root_logger.addHandler(console_handler)
