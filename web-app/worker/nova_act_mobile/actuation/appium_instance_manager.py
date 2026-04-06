"""Manages the lifecycle of an Appium WebDriver session.

Handles driver initialization, capability configuration, implicit waits,
video recording, and cleanup. Used internally by MobileActuator — not
intended for direct use.
"""

import base64
import os
from typing import Any

from appium import webdriver
from appium.webdriver.webdriver import WebDriver
from nova_act.types.errors import ClientNotStarted, StartFailed
from nova_act.util.logging import setup_logging
from selenium.common.exceptions import WebDriverException

from nova_act_mobile.actuation.appium_instance_options import (
    AppiumInstanceOptions,
)
from nova_act_mobile.platform import Platform

_LOGGER = setup_logging(__name__)


class AppiumInstanceManager:
    """RAII Manager for the Appium WebDriver.

    This class manages the lifecycle of an Appium WebDriver session,
    including initialization, configuration, and cleanup.
    """

    def __init__(self, options: AppiumInstanceOptions):
        """Initialize the Appium instance manager.

        Args:
            options: Configuration options for the Appium session.
        """
        self._options = options
        self._driver: WebDriver | None = None
        self._session_logs_directory: str | None = None

    @property
    def started(self) -> bool:
        """Check if the Appium driver is started."""
        return self._driver is not None

    def start(self, session_logs_directory: str | None = None) -> None:
        """Start and initialize the Appium driver.

        Args:
            session_logs_directory: Optional directory for session logs and recordings.

        Raises:
            StartFailed: If the driver fails to start or initialize.
        """
        if self._driver is not None:
            _LOGGER.warning("Appium driver already started")
            return

        if self._options.record_video and session_logs_directory is None:
            raise ValueError(
                "session_logs_directory required when record_video is True"
            )

        self._session_logs_directory = session_logs_directory

        try:
            _LOGGER.info(
                f"Starting Appium session for {self._options.platform} "
                f"device '{self._options.device_name}' "
                f"on server {self._options.appium_server_url}"
            )

            # Build capabilities
            capabilities = self._options.to_capabilities()

            # Add video recording capability if requested
            if self._options.record_video and session_logs_directory:
                # Platform-specific video recording
                if self._options.platform == Platform.ANDROID:
                    capabilities["appium:videoSize"] = "1280x720"
                elif self._options.platform == Platform.IOS:
                    capabilities["appium:videoType"] = "h264"
                    capabilities["appium:videoQuality"] = "medium"

            _LOGGER.debug(f"Appium capabilities: {capabilities}")

            # Create the driver with retry logic for Device Farm timing issues
            import time
            max_retries = 3
            retry_delay = 15  # seconds
            last_error = None

            for attempt in range(1, max_retries + 1):
                try:
                    self._driver = webdriver.Remote(  # type: ignore[attr-defined]
                        command_executor=self._options.appium_server_url,
                        options=self._create_driver_options(capabilities),
                    )
                    last_error = None
                    break
                except WebDriverException as e:
                    last_error = e
                    if attempt < max_retries:
                        _LOGGER.warning(
                            f"Appium session creation failed (attempt {attempt}/{max_retries}): {e}. "
                            f"Retrying in {retry_delay}s..."
                        )
                        time.sleep(retry_delay)
                    else:
                        _LOGGER.error(f"Appium session creation failed after {max_retries} attempts")

            if last_error is not None:
                raise last_error

            # Set implicit wait
            self._driver.implicitly_wait(1)

            _LOGGER.info(
                f"Appium session started successfully. Session ID: {self._driver.session_id}"
            )

        except WebDriverException as e:
            _LOGGER.exception(f"Failed to start Appium driver: {e}")
            self.stop()
            raise StartFailed(f"Failed to start Appium driver: {str(e)}") from e
        except Exception as e:
            _LOGGER.exception(f"Unexpected error starting Appium: {e}")
            self.stop()
            raise StartFailed(f"Failed to start Appium driver: {str(e)}") from e

    def _create_driver_options(self, capabilities: dict[str, Any]) -> Any:  # type: ignore[explicit-any]
        """Create platform-specific driver options.

        Args:
            capabilities: Appium capabilities dictionary.

        Returns:
            Platform-specific options object (UiAutomator2Options or XCUITestOptions).
        """
        if self._options.platform == Platform.ANDROID:
            from appium.options.android import (
                UiAutomator2Options,  # type: ignore[attr-defined]
            )

            options: Any = UiAutomator2Options()  # type: ignore[explicit-any]
        elif self._options.platform == Platform.IOS:
            from appium.options.ios import XCUITestOptions  # type: ignore[attr-defined]

            options = XCUITestOptions()
        else:
            raise ValueError(f"Unsupported platform: {self._options.platform}")

        # Load capabilities into options
        options.load_capabilities(capabilities)
        return options

    def stop(self) -> None:
        """Stop and cleanup the Appium driver."""
        if self._driver is not None:
            try:
                # Handle video recording cleanup
                if self._options.record_video and self._session_logs_directory:
                    self._save_recording()

                # Quit the driver session
                _LOGGER.info("Stopping Appium session")
                self._driver.quit()
            except Exception as e:
                _LOGGER.error(f"Error stopping Appium driver: {e}")
            finally:
                self._driver = None
                self._session_logs_directory = None

    def _save_recording(self) -> None:
        """Save the session recording to the logs directory.

        Uses Appium's start/stop_recording_screen for local Appium servers.
        For Device Farm sessions, this is a no-op — Device Farm does not support
        the stop_recording_screen command. Video artifacts are retrieved via the
        Device Farm list_artifacts API after the session is stopped (handled by
        DeviceFarmActuator).
        """
        if self._driver is None or self._session_logs_directory is None:
            return

        # Device Farm endpoints contain "devicefarm" in the URL — skip Appium
        # recording for those sessions since the command is unsupported.
        server_url = self._options.appium_server_url or ""
        if "devicefarm" in server_url.lower():
            _LOGGER.info(
                "Skipping Appium screen recording on Device Farm — "
                "video will be retrieved from Device Farm artifacts"
            )
            return

        try:
            # Get the video recording from the session (local Appium only)
            video_data = self._driver.stop_recording_screen()

            if video_data:
                video_path = os.path.join(
                    self._session_logs_directory, "session_recording.mp4"
                )
                with open(video_path, "wb") as f:
                    f.write(base64.b64decode(video_data))
                _LOGGER.info(f"Session recording saved to {video_path}")
        except Exception as e:
            _LOGGER.warning(f"Failed to save session recording: {e}")

    @property
    def driver(self) -> WebDriver:
        """Get the active Appium WebDriver instance.

        Returns:
            The active WebDriver instance.

        Raises:
            ClientNotStarted: If the driver has not been started.
        """
        if self._driver is None:
            raise ClientNotStarted("Appium driver not started, call start() first")
        return self._driver

    def get_driver(self) -> WebDriver:
        """Get the active Appium WebDriver instance.

        Returns:
            The active WebDriver instance.

        Raises:
            ClientNotStarted: If the driver has not been started.
        """
        return self.driver
