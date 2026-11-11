import os
import logging
import signal
import threading
from datetime import datetime

TIME_FORMAT='%Y-%m-%dT%H:%M:%SZ'
STRING_SCHEMA = {"type": "string"}
NUMBER_SCHEMA = {"type": "number"}
BOOL_SCHEMA = {"type": "boolean"}

#: Conventional exit code for "killed by SIGTERM" (128 + 15).
SIGTERM_EXIT_CODE = 128 + signal.SIGTERM


def install_sigterm_exit(logger: logging.Logger) -> None:
  """Make SIGTERM raise ``SystemExit(143)`` in the main thread.

  Python's default SIGTERM disposition kills the interpreter without running
  any ``finally`` block, so the MicroVM supervisor's ``/terminate`` SIGTERM
  (and the watchdog's) left the wizard worker's AgentCore browser and live-view
  record behind.  ``SystemExit`` is a ``BaseException`` — the worker's
  ``except Exception`` blocks cannot mistake it for a step failure, and its
  ``finally`` cleanup runs (same reasoning as
  ``qa_studio_cli.runner.termination.sigterm_raises``).

  Signal handlers can only be installed from the main thread; elsewhere this is
  a logged no-op so the default disposition stays in place instead of crashing.
  """
  if threading.current_thread() is not threading.main_thread():
    logger.warning("Not on the main thread; SIGTERM keeps its default disposition")
    return

  def _handler(signum, _frame):
    logger.info("SIGTERM received - exiting with code %s so cleanup runs", SIGTERM_EXIT_CODE)
    raise SystemExit(SIGTERM_EXIT_CODE)

  signal.signal(signal.SIGTERM, _handler)

def get_region(default='us-east-1'):
  """Get the AWS region from environment variables or use a default."""
  return os.getenv('AWS_REGION', default)

def get_time():
  return datetime.now().strftime(TIME_FORMAT)
