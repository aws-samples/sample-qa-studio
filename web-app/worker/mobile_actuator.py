"""
Mobile actuator module for Device Farm integration.

Provides functions to create and clean up mobile Device Farm sessions
for use with Nova Act's DeviceFarmActuator.
"""

import os
import logging
import tempfile
import boto3

from models import MobileAppConfig

# nova_act_mobile is vendored in the worker directory (copied from nova-act-samples repo)
try:
    from nova_act_mobile.actuation.device_farm_actuator import DeviceFarmActuator
    from nova_act_mobile.app import MobileAppConfig as NovaActMobileAppConfig
    from nova_act_mobile.device_farm import DeviceFarmUploadConfig
    from nova_act_mobile.actuation.mobile_actuator import MobileActuator
    from nova_act_mobile.platform import Platform
except ImportError:
    DeviceFarmActuator = None
    NovaActMobileAppConfig = None
    DeviceFarmUploadConfig = None
    MobileActuator = None
    Platform = None

logger = logging.getLogger(__name__)

DEVICE_FARM_REGION = os.getenv('DEVICE_FARM_REGION', 'us-west-2')


def create_mobile_session(execution):
    """
    Create a DeviceFarmActuator from an Execution object.

    Args:
        execution: An Execution dataclass instance with mobile config fields.

    Returns:
        Tuple of (actuator, session_metadata_dict).
        The actuator is passed to NovaAct; NovaAct calls actuator.start()
        when entering the context manager.
        session_metadata_dict contains metadata the worker can store on the
        execution record.
    """
    if DeviceFarmActuator is None:
        raise ImportError(
            "nova_act_mobile is not installed. "
            "Ensure the worker Docker image includes nova-act-mobile."
        )

    # Build MobileAppConfig from execution fields or env vars
    platform_str = execution.platform or os.getenv('MOBILE_PLATFORM')
    app_package = getattr(execution, 'app_identifier', None) or os.getenv('APP_PACKAGE')
    app_activity = os.getenv('APP_ACTIVITY')
    bundle_id = os.getenv('BUNDLE_ID')
    app_binary_s3_path = execution.app_binary_s3_path or os.getenv('APP_BINARY_S3_PATH')
    app_arn = execution.app_arn or os.getenv('APP_ARN')
    device_farm_project_arn = execution.device_farm_project_arn or os.getenv('DEVICE_FARM_PROJECT_ARN')
    device_arn = execution.device_arn or os.getenv('DEVICE_ARN')

    if not platform_str:
        raise ValueError("Mobile platform is required (ANDROID or IOS)")

    # Parse platform-specific identifiers from app_identifier if needed
    # app_identifier is stored as "package/activity" for Android or bundle_id for iOS
    if platform_str.upper() == 'ANDROID':
        if execution.app_identifier and '/' in execution.app_identifier:
            parts = execution.app_identifier.split('/', 1)
            app_package = parts[0]
            app_activity = parts[1]
        app_package = app_package or os.getenv('APP_PACKAGE')
        app_activity = app_activity or os.getenv('APP_ACTIVITY')
    elif platform_str.upper() == 'IOS':
        bundle_id = execution.app_identifier or bundle_id

    logger.info(f"Creating mobile session: platform={platform_str}, "
                f"app_binary_s3_path={app_binary_s3_path}, app_arn={app_arn}")

    # Download app binary from S3 if needed
    local_binary_path = None
    if app_binary_s3_path:
        local_binary_path = _download_binary_from_s3(app_binary_s3_path)

    # Build nova_act_mobile MobileAppConfig
    if platform_str.upper() == 'ANDROID':
        if not app_package or not app_activity:
            raise ValueError("app_package and app_activity are required for Android")
        nova_app_config = NovaActMobileAppConfig.for_android(
            app_package=app_package,
            app_activity=app_activity,
        )
    elif platform_str.upper() == 'IOS':
        if not bundle_id:
            raise ValueError("bundle_id is required for iOS")
        nova_app_config = NovaActMobileAppConfig.for_ios(
            bundle_id=bundle_id,
        )
    else:
        raise ValueError(f"Unsupported platform: {platform_str}")

    # Build DeviceFarmUploadConfig if we have a local binary
    upload_config = None
    if local_binary_path:
        filename = os.path.basename(local_binary_path)
        upload_config = DeviceFarmUploadConfig(
            app_name=filename,
            app_path=local_binary_path,
        )

    # Create the DeviceFarmActuator
    actuator = DeviceFarmActuator(
        app_config=nova_app_config,
        upload_config=upload_config,
        project_arn=device_farm_project_arn if device_farm_project_arn else None,
        device_arn=device_arn if device_arn else None,
    )

    # Build session metadata for the worker to store on the execution record
    session_metadata = {
        'platform': platform_str.upper(),
        'device_farm_region': DEVICE_FARM_REGION,
        'app_identifier': nova_app_config.app_identifier,
    }

    logger.info(f"DeviceFarmActuator created. Region: {DEVICE_FARM_REGION}")
    return actuator, session_metadata


def cleanup_mobile_session(actuator):
    """
    Best-effort cleanup of a Device Farm session.

    Calls actuator.stop() to terminate the Remote Access Session.
    Wrapped in try/except so it doesn't mask the original error.

    Args:
        actuator: A DeviceFarmActuator instance.
    """
    if actuator is None:
        return
    try:
        actuator.stop()
        logger.info("Device Farm session cleaned up successfully")
    except Exception as e:
        logger.warning(f"Failed to clean up Device Farm session: {e}")




def _download_binary_from_s3(s3_path):
    """
    Download an app binary from S3 to a local temp file.

    Args:
        s3_path: S3 key of the app binary (e.g. "usecase123/app_binary/my-app.apk")

    Returns:
        Local file path to the downloaded binary.
    """
    s3_bucket = os.getenv('S3_BUCKET')
    if not s3_bucket:
        raise ValueError("S3_BUCKET environment variable is required to download app binary")

    filename = os.path.basename(s3_path)
    suffix = os.path.splitext(filename)[1]  # .apk or .ipa
    tmp_dir = tempfile.mkdtemp(prefix='mobile_binary_')
    local_path = os.path.join(tmp_dir, filename)

    logger.info(f"Downloading app binary from s3://{s3_bucket}/{s3_path} to {local_path}")

    s3_client = boto3.client('s3', region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
    s3_client.download_file(s3_bucket, s3_path, local_path)

    logger.info(f"App binary downloaded: {local_path} ({os.path.getsize(local_path)} bytes)")
    return local_path
