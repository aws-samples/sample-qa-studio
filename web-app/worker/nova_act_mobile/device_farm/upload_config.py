"""Device Farm app upload configuration."""

from dataclasses import dataclass


@dataclass
class DeviceFarmUploadConfig:
    """Configuration for uploading an app to Device Farm.

    Attributes:
        app_name: Display name for Device Farm upload filename and session naming
        app_path: Path to .apk/.ipa file
        app_arn: Pre-existing Device Farm upload ARN (skips upload entirely)
        force_upload: Force re-upload even if a matching upload already exists
    """

    app_name: str
    app_path: str | None = None
    app_arn: str | None = None
    force_upload: bool = False
