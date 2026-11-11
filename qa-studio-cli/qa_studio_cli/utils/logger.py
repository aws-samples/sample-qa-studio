"""Logging configuration for the runner."""

import logging
import os
import sys
from pathlib import Path
from typing import Union

from qa_studio_cli.utils.log_filters import (
    NoisyLibraryFilter,
    NovaActLogFilter,
    SecretRedactionFilter,
)

ARTIFACT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# Console lines share the ``[HH:MM:SS]`` prefix of ``runner.progress`` so the
# two interleave cleanly in verbose mode.
CONSOLE_LOG_FORMAT = "[%(asctime)s] %(levelname)s %(message)s"
CONSOLE_DATE_FORMAT = "%H:%M:%S"
# Read lazily by nova_act.util.logging on first use.
NOVA_ACT_LOG_LEVEL_ENV = "NOVA_ACT_LOG_LEVEL"


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


def configure_nova_act_logging(verbose: bool) -> None:
    """Tie Nova Act's self-managed loggers to the ``--verbose`` flag.

    Nova Act gives ``nova_act.trace`` and its module loggers their own
    stderr ``StreamHandler`` with ``propagate=False``, so our root console
    handler (and its ``NovaActLogFilter``) never sees those records.  Two
    knobs are needed:

    - ``NOVA_ACT_LOG_LEVEL``: read lazily by ``make_trace_logger()`` on first
      use, overriding anything set earlier — the only reliable knob for the
      think/act trace.  Left alone when the user exported it themselves.
    - ``setLevel`` on every ``nova_act*`` logger that already exists: module
      loggers fix their level at import time, and ``engine.py`` imports
      ``nova_act`` before ``setup_logging`` runs.
    """
    level = logging.INFO if verbose else logging.WARNING
    os.environ.setdefault(NOVA_ACT_LOG_LEVEL_ENV, str(level))
    for name, existing in list(logging.Logger.manager.loggerDict.items()):
        if not isinstance(existing, logging.Logger):
            continue  # PlaceHolder — created implicitly for dotted parents
        if name == "nova_act" or name.startswith("nova_act."):
            existing.setLevel(level)


def setup_logging(verbose: bool) -> None:
    """Configure console logging for the runner.

    The console handler is WARNING by default and DEBUG with ``--verbose``.
    User-facing progress is printed by ``runner.progress``, not by logging,
    so the quiet default shows only warnings/errors plus the progress lines.
    The root logger stays at DEBUG: the per-execution file handler and
    ``SuiteLogCapture`` attach later and record everything.

    Args:
        verbose: If True, console at DEBUG and Nova Act trace at INFO.
                 Otherwise console at WARNING and Nova Act at WARNING.
    """
    log_level = logging.DEBUG if verbose else logging.WARNING

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(
        logging.Formatter(CONSOLE_LOG_FORMAT, datefmt=CONSOLE_DATE_FORMAT),
    )
    console_handler.addFilter(NovaActLogFilter())
    add_safety_filters(console_handler)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)

    configure_nova_act_logging(verbose)
