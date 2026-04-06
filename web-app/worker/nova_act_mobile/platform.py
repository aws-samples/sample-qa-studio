"""Platform enum for mobile automation.

Single source of truth for platform identity across CLI, Appium,
and Device Farm contexts.
"""

from enum import StrEnum
from typing import Literal

from mypy_boto3_devicefarm.literals import DevicePlatformType, UploadTypeType

AutomationNameType = Literal["XCUITest", "UIAutomator2"]


class Platform(StrEnum):
    """Mobile platform identifier.

    Values are Appium-compatible ("Android", "iOS") since StrEnum
    serializes to the string value directly for platformName capability.
    """

    ANDROID = "Android"
    IOS = "iOS"

    @property
    def device_farm_upload_type(self) -> UploadTypeType:
        """Device Farm upload type for app binaries."""
        mapping: dict[Platform, UploadTypeType] = {
            Platform.ANDROID: "ANDROID_APP",
            Platform.IOS: "IOS_APP",
        }
        return mapping[self]

    @property
    def device_farm_platform(self) -> DevicePlatformType:
        """Device Farm device platform filter value ('ANDROID' / 'IOS')."""
        mapping: dict[Platform, DevicePlatformType] = {
            Platform.ANDROID: "ANDROID",
            Platform.IOS: "IOS",
        }
        return mapping[self]

    @property
    def appium_automation_name(self) -> AutomationNameType:
        """Default Appium automation framework for this platform."""
        return "XCUITest" if self == Platform.IOS else "UIAutomator2"

    @property
    def app_file_extension(self) -> str:
        """Expected app binary file extension."""
        return ".ipa" if self == Platform.IOS else ".apk"
