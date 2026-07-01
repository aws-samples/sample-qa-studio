"""Shared utilities for mobile actuation."""

from typing import Literal

from appium.webdriver.webdriver import WebDriver

PlatformName = Literal["android", "ios"]


def get_platform(driver: WebDriver) -> PlatformName:
    """Derive the platform from the Appium driver's capabilities.

    Returns ``"android"`` or ``"ios"`` — a simple string that keeps the
    low-level utils independent of the higher-level ``Platform`` enum.
    """
    raw = str(driver.capabilities.get("platformName", "")).lower()
    if "ios" in raw:
        return "ios"
    return "android"
