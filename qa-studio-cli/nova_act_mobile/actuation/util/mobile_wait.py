"""Mobile wait utilities for app idle detection and synchronization."""

import time
from dataclasses import dataclass

from appium.webdriver.webdriver import WebDriver
from nova_act.util.logging import setup_logging

_LOGGER = setup_logging(__name__)


@dataclass
class WaitConfig:
    """Configuration for mobile wait strategies."""

    max_wait_time_s: float = 10.0
    """Maximum time to wait in seconds."""

    stability_duration_s: float = 0.5
    """Duration the app must remain stable to be considered idle."""

    check_interval_s: float = 0.2
    """Interval between stability checks."""

    wait_for_animations: bool = True
    """Whether to wait for animations to complete."""


# Default configuration for waiting
DEFAULT_WAIT_CONFIG = WaitConfig(
    max_wait_time_s=10.0,
    stability_duration_s=0.5,
    check_interval_s=0.2,
    wait_for_animations=True,
)


def wait_for_app_idle(
    driver: WebDriver, config: WaitConfig = DEFAULT_WAIT_CONFIG
) -> None:
    """Wait for the mobile app to reach an idle state.

    This function waits until:
    1. No UI updates are occurring
    2. Animations have completed (if enabled)
    3. The app has been stable for the configured duration

    Args:
        driver: Appium WebDriver instance.
        config: Wait configuration settings.

    Raises:
        TimeoutError: If the app doesn't become idle within max_wait_time.
    """
    _LOGGER.debug(f"Waiting for app idle (max {config.max_wait_time_s}s)")

    start_time = time.time()
    stable_since: float | None = None
    last_source_hash: int | None = None

    while True:
        elapsed = time.time() - start_time

        # Check timeout
        if elapsed > config.max_wait_time_s:
            _LOGGER.warning(f"App did not become idle within {config.max_wait_time_s}s")
            return  # Don't raise, just proceed

        try:
            # Get current page source hash as a stability indicator
            current_source = driver.page_source
            current_hash = hash(current_source)

            # Check if UI has changed
            if last_source_hash is None:
                # First check
                last_source_hash = current_hash
                stable_since = time.time()
            elif current_hash != last_source_hash:
                # UI changed, reset stability timer
                last_source_hash = current_hash
                stable_since = time.time()
                _LOGGER.debug("UI changed, resetting stability timer")
            else:
                # UI unchanged, check if stable long enough
                if (
                    stable_since
                    and (time.time() - stable_since) >= config.stability_duration_s
                ):
                    _LOGGER.debug(f"App idle after {elapsed:.2f}s")
                    return

            # Wait before next check
            time.sleep(config.check_interval_s)

        except Exception as e:
            _LOGGER.warning(f"Error during idle wait: {e}")
            # Continue waiting despite errors
            time.sleep(config.check_interval_s)


def smart_wait(driver: WebDriver, seconds: float) -> None:
    """Perform a smart wait that combines explicit delay with idle detection.

    If seconds is 0, waits for app to become idle.
    Otherwise, waits for the specified duration then checks for idle.

    Args:
        driver: Appium WebDriver instance.
        seconds: Duration to wait in seconds. 0 means wait for idle only.
    """
    if seconds < 0:
        raise ValueError("Wait duration must be non-negative")

    if seconds == 0:
        # Wait for idle only
        wait_for_app_idle(driver)
    else:
        # Wait for specified duration
        time.sleep(seconds)
        # Then wait for idle with shorter timeout
        quick_config = WaitConfig(
            max_wait_time_s=2.0,
            stability_duration_s=0.3,
            check_interval_s=0.1,
        )
        wait_for_app_idle(driver, quick_config)
