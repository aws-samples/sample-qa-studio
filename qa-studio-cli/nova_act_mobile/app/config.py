"""Mobile app identity configuration.

Encapsulates the platform and app identifiers needed to target a mobile app.
Infrastructure-agnostic — used by both local Appium and Device Farm flows.
"""

from dataclasses import dataclass

from nova_act_mobile.platform import Platform


@dataclass
class MobileAppConfig:
    """Identifies which mobile app to launch and interact with on a device.

    Holds the platform-specific identifiers (package/activity for Android,
    bundle ID for iOS) that actuators use to start the correct app, whether
    through Device Farm or a local Appium session. Use the factory methods
    `for_android()` and `for_ios()` for construction.

    Attributes:
        platform: Platform identifier (Android or iOS)
        app_package: Android package name (None for iOS)
        app_activity: Android main activity (None for iOS)
        bundle_id: iOS bundle ID (None for Android)
    """

    platform: Platform
    app_package: str | None = None
    app_activity: str | None = None
    bundle_id: str | None = None

    @property
    def app_identifier(self) -> str:
        """Primary app identifier for the current platform."""
        if self.platform == Platform.ANDROID:
            if not self.app_package:
                raise ValueError("app_package is required for Android")
            return self.app_package
        elif self.platform == Platform.IOS:
            if not self.bundle_id:
                raise ValueError("bundle_id is required for iOS")
            return self.bundle_id
        raise ValueError(f"Unsupported platform: {self.platform}")

    @classmethod
    def for_android(cls, app_package: str, app_activity: str) -> "MobileAppConfig":
        """Create configuration for an Android app.

        Args:
            app_package: Android package name (e.g., com.example.app)
            app_activity: Android main activity (e.g., .MainActivity)
        """
        return cls(
            platform=Platform.ANDROID,
            app_package=app_package,
            app_activity=app_activity,
        )

    @classmethod
    def for_ios(cls, bundle_id: str) -> "MobileAppConfig":
        """Create configuration for an iOS app.

        Args:
            bundle_id: iOS bundle ID (e.g., com.apple.mobilesafari)
        """
        return cls(
            platform=Platform.IOS,
            bundle_id=bundle_id,
        )
