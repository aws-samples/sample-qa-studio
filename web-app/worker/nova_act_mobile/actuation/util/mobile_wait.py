"""Mobile wait utilities using screenshot-based stability detection.

Mirrors the browser SDK's approach: takes consecutive screenshots and compares
them visually using pixel difference. This avoids the expensive
``driver.page_source`` call (especially slow on iOS/XCUITest) and uses a fuzzy
threshold so minor rendering jitter doesn't reset the stability timer.

Reuses ``compare_images`` from the Nova Act SDK's browser utilities so the
comparison algorithm stays in sync with the browser actuator.
"""

import time

from appium.webdriver.webdriver import WebDriver
from nova_act.tools.browser.default.util.image_helpers import compare_images
from nova_act.util.logging import setup_logging
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException

_LOGGER = setup_logging(__name__)


def _is_session_error(exc: BaseException) -> bool:
    """Check if an exception indicates the WDA/Appium session is dead.

    This is a known transient condition on Device Farm when the console
    viewer is opened — it takes over the WDA session, temporarily
    invalidating the existing one. The session recovers on its own.
    """
    if isinstance(exc, InvalidSessionIdException):
        return True
    # The error sometimes surfaces wrapped in other exception types
    if isinstance(exc, WebDriverException):
        msg = str(exc).lower()
        if "session does not exist" in msg or "invalid session id" in msg:
            return True
    # Check chained causes (e.g. ValueError wrapping WebDriverException)
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return _is_session_error(cause)
    return False


# Matches the browser SDK's WAIT_FOR_PAGE_TO_SETTLE_CONFIG
_MAX_TIMEOUT_S = 3.0
_NUMBER_OF_CHECKS = 3
_PERCENT_DIFFERENCE_THRESHOLD = 25.0
_POLLING_INTERVAL_S = 0.5


def _take_screenshot_data_url(driver: WebDriver) -> str:
    """Capture a screenshot and return it as a data URL."""
    screenshot_base64 = driver.get_screenshot_as_base64()
    return f"data:image/png;base64,{screenshot_base64}"


def wait_for_app_idle(driver: WebDriver) -> None:
    """Wait for the mobile app to reach a visually stable state.

    Takes consecutive screenshots and compares them. The app is considered
    idle once the configured number of consecutive comparisons fall below
    the pixel-difference threshold, or when the timeout is reached.

    This replaces the previous ``page_source`` hashing approach which was
    prohibitively slow on iOS (XCUITest ``page_source`` takes 1-3 s per call).

    Args:
        driver: Appium WebDriver instance.
    """
    _LOGGER.debug(f"Waiting for app idle (max {_MAX_TIMEOUT_S}s)")

    start_time = time.time()
    consecutive_stable = 0
    previous_screenshot: str | None = None

    while True:
        elapsed = time.time() - start_time

        if elapsed >= _MAX_TIMEOUT_S:
            _LOGGER.debug(
                f"Timeout reached ({_MAX_TIMEOUT_S}s) after "
                f"{consecutive_stable} stable check(s)"
            )
            return

        try:
            screenshot = _take_screenshot_data_url(driver)
        except Exception as e:
            if _is_session_error(e):
                _LOGGER.debug(
                    "Session unavailable during idle wait (likely Device Farm "
                    "console viewer), skipping stability check"
                )
                return
            _LOGGER.warning(f"Screenshot failed during idle wait: {e}")
            time.sleep(_POLLING_INTERVAL_S)
            continue

        if previous_screenshot is None:
            previous_screenshot = screenshot
            time.sleep(_POLLING_INTERVAL_S)
            continue

        try:
            pct_diff = compare_images(previous_screenshot, screenshot)
        except Exception as e:
            _LOGGER.warning(f"Screenshot comparison failed: {e}")
            previous_screenshot = screenshot
            time.sleep(_POLLING_INTERVAL_S)
            continue

        _LOGGER.debug(
            f"Stability check: {pct_diff:.1f}% diff "
            f"(threshold {_PERCENT_DIFFERENCE_THRESHOLD}%), "
            f"streak {consecutive_stable}/{_NUMBER_OF_CHECKS}"
        )

        if pct_diff >= _PERCENT_DIFFERENCE_THRESHOLD:
            consecutive_stable = 0
        else:
            consecutive_stable += 1
            if consecutive_stable >= _NUMBER_OF_CHECKS:
                _LOGGER.debug(f"App idle after {elapsed:.2f}s")
                return

        previous_screenshot = screenshot
        time.sleep(_POLLING_INTERVAL_S)
