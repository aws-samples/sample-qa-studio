"""Generic polling utilities for waiting on conditions."""

import time
from typing import Callable


def poll_until(
    condition_fn: Callable[[], bool],
    timeout_seconds: int,
    poll_interval_seconds: int,
    error_message: str,
) -> None:
    """
    Poll until condition function returns True or timeout.

    Args:
        condition_fn: Callable that returns True when condition is met
        timeout_seconds: Maximum time to wait in seconds
        poll_interval_seconds: Time between polls in seconds
        error_message: Error message to raise on timeout

    Raises:
        RuntimeError: If condition not met within timeout
    """
    max_attempts = timeout_seconds // poll_interval_seconds
    for _attempt in range(max_attempts):
        if condition_fn():
            return
        time.sleep(poll_interval_seconds)
    raise RuntimeError(error_message)
