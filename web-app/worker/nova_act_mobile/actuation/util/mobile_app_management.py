"""Mobile app management utilities for launching, terminating, and managing apps."""

from appium.webdriver.webdriver import WebDriver
from nova_act.util.logging import setup_logging

_LOGGER = setup_logging(__name__)


def launch_app(driver: WebDriver, app_identifier: str | None = None) -> None:
    """Launch or relaunch the app.

    Args:
        driver: Appium WebDriver instance.
        app_identifier: Optional app identifier (bundle ID for iOS, package for Android).
                       If None, launches the app configured in capabilities.

    Raises:
        ValueError: If app cannot be launched.
    """
    try:
        if app_identifier:
            _LOGGER.info(f"Launching app: {app_identifier}")
            # Activate a specific app by its identifier
            driver.activate_app(app_identifier)
        else:
            _LOGGER.info("Launching default app")
            # Launch the app configured in session
            driver.launch_app()  # type: ignore[attr-defined]
    except Exception as e:
        _LOGGER.error(f"Failed to launch app: {e}")
        raise ValueError(f"Could not launch app: {e}") from e


def terminate_app(driver: WebDriver, app_identifier: str) -> bool:
    """Terminate a running app.

    Args:
        driver: Appium WebDriver instance.
        app_identifier: App identifier (bundle ID for iOS, package for Android).

    Returns:
        True if app was terminated, False if app was not running.

    Raises:
        ValueError: If app cannot be terminated.
    """
    try:
        _LOGGER.info(f"Terminating app: {app_identifier}")
        result = driver.terminate_app(app_identifier)
        return bool(result)
    except Exception as e:
        _LOGGER.error(f"Failed to terminate app: {e}")
        raise ValueError(f"Could not terminate app: {e}") from e


def background_app(driver: WebDriver, seconds: int = -1) -> None:
    """Send the app to the background for a specified duration.

    Args:
        driver: Appium WebDriver instance.
        seconds: Duration in seconds to keep app in background.
                -1 means keep in background indefinitely until brought back.

    Raises:
        ValueError: If app cannot be backgrounded.
    """
    try:
        _LOGGER.info(f"Sending app to background for {seconds} seconds")
        driver.background_app(seconds)
    except Exception as e:
        _LOGGER.error(f"Failed to background app: {e}")
        raise ValueError(f"Could not background app: {e}") from e


def is_app_installed(driver: WebDriver, app_identifier: str) -> bool:
    """Check if an app is installed on the device.

    Args:
        driver: Appium WebDriver instance.
        app_identifier: App identifier (bundle ID for iOS, package for Android).

    Returns:
        True if app is installed, False otherwise.
    """
    try:
        result = driver.is_app_installed(app_identifier)
        _LOGGER.debug(f"App {app_identifier} installed: {result}")
        return bool(result)
    except Exception as e:
        raise RuntimeError(
            f"Failed to check if app is installed ({app_identifier}): {e}"
        ) from e


def get_app_state(driver: WebDriver, app_identifier: str) -> str:
    """Get the current state of an app.

    Args:
        driver: Appium WebDriver instance.
        app_identifier: App identifier (bundle ID for iOS, package for Android).

    Returns:
        App state as a string. Possible values:
        - "not_installed" (0): App is not installed
        - "not_running" (1): App is installed but not running
        - "running_in_background_suspended" (2): App is running in background (suspended)
        - "running_in_background" (3): App is running in background
        - "running_in_foreground" (4): App is running in foreground
    """
    try:
        state_code = driver.query_app_state(app_identifier)
        state_map = {
            0: "not_installed",
            1: "not_running",
            2: "running_in_background_suspended",
            3: "running_in_background",
            4: "running_in_foreground",
        }
        state = state_map.get(state_code, f"unknown({state_code})")
        _LOGGER.debug(f"App {app_identifier} state: {state}")
        return state
    except Exception as e:
        raise RuntimeError(f"Failed to get app state ({app_identifier}): {e}") from e


def install_app(driver: WebDriver, app_path: str) -> None:
    """Install an app on the device.

    Args:
        driver: Appium WebDriver instance.
        app_path: Path to the .app (iOS) or .apk (Android) file.

    Raises:
        ValueError: If app cannot be installed.
    """
    try:
        _LOGGER.info(f"Installing app from: {app_path}")
        driver.install_app(app_path)
    except Exception as e:
        _LOGGER.error(f"Failed to install app: {e}")
        raise ValueError(f"Could not install app: {e}") from e


def remove_app(driver: WebDriver, app_identifier: str) -> bool:
    """Remove/uninstall an app from the device.

    Args:
        driver: Appium WebDriver instance.
        app_identifier: App identifier (bundle ID for iOS, package for Android).

    Returns:
        True if app was removed, False otherwise.

    Raises:
        ValueError: If app cannot be removed.
    """
    try:
        _LOGGER.info(f"Removing app: {app_identifier}")
        result = driver.remove_app(app_identifier)
        return bool(result)
    except Exception as e:
        _LOGGER.error(f"Failed to remove app: {e}")
        raise ValueError(f"Could not remove app: {e}") from e


def open_deep_link(
    driver: WebDriver, url: str, app_identifier: str | None = None
) -> None:
    """Open a deep link or universal link.

    Args:
        driver: Appium WebDriver instance.
        url: Deep link URL to open (e.g., "myapp://screen/detail?id=123").
        app_identifier: Optional app identifier. If provided, ensures the app
                       is running before opening the link.

    Raises:
        ValueError: If deep link cannot be opened.
    """
    try:
        _LOGGER.info(f"Opening deep link: {url}")

        # If app identifier provided, ensure app is running
        if app_identifier:
            state = get_app_state(driver, app_identifier)
            if state not in ("running_in_foreground", "running_in_background"):
                launch_app(driver, app_identifier)

        # Open the deep link using platform-specific method
        platform = driver.capabilities.get("platformName", "").lower()

        if "ios" in platform:
            # For iOS, use mobile: deepLink command
            driver.execute_script(
                "mobile: deepLink", {"url": url, "package": app_identifier or ""}
            )
        else:
            # For Android, we can use adb shell am start or driver.get()
            # Using execute_script with mobile: deepLink if available
            try:
                driver.execute_script(
                    "mobile: deepLink", {"url": url, "package": app_identifier or ""}
                )
            except Exception:
                # Fallback: try using get() which works for some deep links
                driver.get(url)

    except Exception as e:
        _LOGGER.error(f"Failed to open deep link: {e}")
        raise ValueError(f"Could not open deep link: {e}") from e
