"""Configuration options for an Appium session.

Encapsulates platform, device, app, and behavior settings needed to start
an Appium WebDriver. Validates platform-specific requirements and converts
to an Appium capabilities dictionary via to_capabilities().
"""

from typing import Any, Literal

from pydantic import BaseModel, model_validator

from nova_act_mobile.platform import Platform

_DEFAULT_APPIUM_SERVER_URL = "http://127.0.0.1:4723"
_DEFAULT_NEW_COMMAND_TIMEOUT = 60


class AppiumInstanceOptions(BaseModel):
    """Configuration options for Appium mobile automation.

    This class encapsulates all configuration needed to start and manage
    an Appium WebDriver session for mobile automation.
    """

    # Platform Configuration
    platform: Platform
    """Target mobile platform."""

    # Device Configuration
    device_name: str
    """Name of the device to automate (e.g., 'iPhone 15 Pro', 'Pixel 8')."""

    platform_version: str | None = None
    """OS version of the target device (e.g., '17.0', '14').

    When None, the capability is omitted — useful for Device Farm sessions
    where the server pre-configures platformVersion as a reserved capability.
    """

    udid: str | None = None
    """Unique device identifier. Required for real devices, optional for simulators."""

    # App Configuration
    app_path: str | None = None
    """Absolute path to the .app (iOS) or .apk (Android) file."""

    bundle_id: str | None = None
    """iOS bundle identifier (e.g., 'com.apple.mobilesafari'). Alternative to app_path."""

    app_package: str | None = None
    """Android app package name (e.g., 'com.android.chrome'). Used with app_activity."""

    app_activity: str | None = None
    """Android app activity to launch (e.g., 'com.google.android.apps.chrome.Main')."""

    # Automation Framework
    automation_name: Literal["XCUITest", "UIAutomator2", "Espresso"] | None = None
    """Automation framework to use. Defaults to XCUITest for iOS, UIAutomator2 for Android."""

    # Server Configuration
    appium_server_url: str = _DEFAULT_APPIUM_SERVER_URL
    """URL of the Appium server."""

    # Timeout Configuration
    new_command_timeout: int = _DEFAULT_NEW_COMMAND_TIMEOUT
    """Timeout in seconds before Appium shuts down the session due to inactivity."""

    # Behavior Options
    auto_launch: bool = True
    """Whether to automatically launch the app when the session starts."""

    auto_accept_alerts: bool = False
    """Automatically accept system alerts (iOS only)."""

    auto_dismiss_alerts: bool = False
    """Automatically dismiss system alerts (iOS only)."""

    no_reset: bool = False
    """Don't reset app state before session."""

    full_reset: bool = False
    """Perform a complete reset (delete and reinstall app)."""

    # Advanced Options
    additional_capabilities: dict[str, str | int | bool] | None = None
    """Additional Appium capabilities to pass to the driver."""

    # Recording
    record_video: bool = False
    """Whether to record video of the session."""

    @model_validator(mode="after")
    def set_defaults_and_validate(self):
        """Set default automation framework and validate app configuration."""
        if self.automation_name is None:
            self.automation_name = self.platform.appium_automation_name

        if self.platform == Platform.ANDROID:
            if not self.app_path and not (self.app_package and self.app_activity):
                raise ValueError(
                    "For Android, either app_path or (app_package + app_activity) must be provided"
                )
        elif self.platform == Platform.IOS:
            if not self.app_path and not self.bundle_id:
                raise ValueError(
                    "For iOS, either app_path or bundle_id must be provided"
                )

        return self

    def to_capabilities(self) -> dict[str, Any]:
        """Convert options to Appium capabilities dictionary.

        Returns:
            Dictionary of Appium capabilities suitable for driver initialization.
        """
        caps: dict[str, Any] = {
            "platformName": self.platform,
            "appium:deviceName": self.device_name,
            "appium:automationName": self.automation_name,
            "appium:newCommandTimeout": self.new_command_timeout,
        }

        # Omit platformVersion when None — Device Farm pre-configures this
        # as a reserved capability and rejects mismatched values.
        if self.platform_version:
            caps["appium:platformVersion"] = self.platform_version

        if self.udid:
            caps["appium:udid"] = self.udid

        if self.app_path:
            caps["appium:app"] = self.app_path

        if self.platform == Platform.ANDROID:
            if self.app_package:
                caps["appium:appPackage"] = self.app_package
            if self.app_activity:
                caps["appium:appActivity"] = self.app_activity
            caps["appium:uiautomator2ServerInstallTimeout"] = 60000
        elif self.platform == Platform.IOS:
            if self.bundle_id:
                caps["appium:bundleId"] = self.bundle_id
            if self.auto_accept_alerts:
                caps["appium:autoAcceptAlerts"] = True
            if self.auto_dismiss_alerts:
                caps["appium:autoDismissAlerts"] = True

        if not self.auto_launch:
            caps["appium:autoLaunch"] = False
        if self.no_reset:
            caps["appium:noReset"] = True
        if self.full_reset:
            caps["appium:fullReset"] = True

        if self.additional_capabilities:
            caps.update(self.additional_capabilities)

        return caps
