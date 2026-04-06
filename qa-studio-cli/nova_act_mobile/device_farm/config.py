"""Configuration constants for Device Farm"""

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


class DeviceFarmConfig:
    """Centralized configuration for Device Farm operations.

    Note: AWS Device Farm is only available in us-west-2 region.
    The region is hardcoded in DeviceFarmClient and cannot be changed.
    """

    # Default app — AWS Device Farm Android Reference App (Apache 2.0)
    # Source: https://github.com/aws-samples/aws-device-farm-sample-app-for-android
    DEFAULT_APP_NAME = "aws-device-farm-sample-app-for-android.apk"
    DEFAULT_APP_PATH = str(
        _PACKAGE_ROOT / "app" / "samples" / "aws-device-farm-sample" / "app-debug.apk"
    )
    DEFAULT_APP_PACKAGE = "com.amazonaws.devicefarm.android.referenceapp"
    DEFAULT_APP_ACTIVITY = (
        "com.amazonaws.devicefarm.android.referenceapp.Activities.MainActivity"
    )

    # Polling Configuration
    POLL_INTERVAL_SECONDS = 2
    """How often to check upload/session status (seconds)"""

    UPLOAD_POLL_ATTEMPTS = 30
    """Maximum number of polling attempts for uploads"""

    RUN_POLL_INTERVAL_SECONDS = 30
    """How often to check test run status (seconds)"""

    # Timeout Configuration
    MAX_WAIT_SECONDS = 300
    """Maximum wait time for session setup (5 minutes - under Device Farm's inactivity timeout)"""

    RUN_TIMEOUT_SECONDS = 1800
    """Maximum test run duration (30 minutes)"""
