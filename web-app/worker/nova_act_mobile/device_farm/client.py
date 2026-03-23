"""
AWS Device Farm Client Wrapper

Provides a clean interface for Device Farm operations needed for Nova Act mobile actuation on AWS Device Farm.
Handles session creation, app upload, and endpoint extraction with proper
error handling and logging.

Error Handling Strategy:
- RuntimeError: AWS operation failed (upload, session creation, polling timeout)
- All errors include actionable troubleshooting information
"""

import time
from dataclasses import dataclass
from datetime import datetime

import boto3
import requests
from mypy_boto3_devicefarm.client import DeviceFarmClient as DeviceFarmServiceClient
from mypy_boto3_devicefarm.literals import DevicePlatformType, UploadTypeType
from mypy_boto3_devicefarm.type_defs import (
    CreateProjectResultTypeDef,
    CreateRemoteAccessSessionResultTypeDef,
    CreateUploadResultTypeDef,
    DeviceTypeDef,
    GetDeviceResultTypeDef,
    GetRemoteAccessSessionResultTypeDef,
    GetUploadResultTypeDef,
    ListDevicesResultTypeDef,
    ListProjectsResultTypeDef,
    ListUploadsResultTypeDef,
    UploadTypeDef,
)

from nova_act_mobile.device_farm.config import (
    DeviceFarmConfig as Config,
)
from nova_act_mobile.platform import Platform
from nova_act_mobile.polling import poll_until
import logging

logger = logging.getLogger(__name__)


def _os_version_key(device: DeviceTypeDef) -> tuple:
    """Sort key that parses an OS version string into a comparable tuple of ints."""
    try:
        return tuple(int(x) for x in str(device.get("os", "0")).split("."))
    except ValueError:
        return (0,)


def _iphone_model_key(device: DeviceTypeDef) -> int:
    """Sort key that extracts the iPhone model number from the device name.

    Device Farm names look like "Apple iPhone 16 Pro Max" or "Apple iPhone 14".
    Returns the numeric model (e.g. 16) so higher models sort first.
    Falls back to 0 for non-iPhone or unparseable names.
    """
    import re

    name = device.get("name", "")
    match = re.search(r"iPhone\s+(\d+)", name)
    return int(match.group(1)) if match else 0


@dataclass
class DeviceFarmSessionResult:
    """Result of a Device Farm session setup.

    Carries the endpoint URL and device metadata discovered during setup,
    avoiding the need to mutate config objects as a side effect.
    """

    endpoint_url: str
    session_arn: str
    device_name: str
    platform_version: str


class DeviceFarmClient:
    """
    Client for AWS Device Farm operations with atomic execution support.

    Note: AWS Device Farm is only available in us-west-2 region.
    """

    def __init__(self):
        """Initialize Device Farm client in us-west-2 (only supported region)."""
        self.client: DeviceFarmServiceClient = boto3.client(
            "devicefarm", region_name="us-west-2"
        )
        self.region = "us-west-2"

    def _poll_upload_status(self, upload_arn: str) -> str:
        """
        Poll upload status until completion.

        Args:
            upload_arn: Upload ARN to poll

        Returns:
            Upload ARN on success

        Raises:
            RuntimeError: If upload fails or times out
        """

        def check_upload_complete():
            response: GetUploadResultTypeDef = self.client.get_upload(arn=upload_arn)
            upload = response["upload"]
            status = upload.get("status", "")

            logger.debug(f"Upload status: {status}")

            if status == "SUCCEEDED":
                logger.debug("Upload completed successfully")
                return True
            elif status == "FAILED":
                # Parse error details from metadata
                import json

                error_msg = upload.get("message", "")
                metadata = upload.get("metadata", "")

                # metadata is a JSON string according to AWS API
                if metadata:
                    try:
                        if isinstance(metadata, str):
                            metadata_dict = json.loads(metadata)
                        else:
                            # Already a dict (shouldn't happen per API spec, but just in case)
                            metadata_dict = metadata

                        error_code = metadata_dict.get("errorCode", "UNKNOWN")
                        error_message = metadata_dict.get(
                            "errorMessage", "No error message"
                        )
                        error_url = metadata_dict.get("errorMessageUrl", "")

                        error_details = f"Upload failed [{error_code}]: {error_message}"
                        if error_url:
                            error_details += f"\nSee: {error_url}"
                    except (json.JSONDecodeError, AttributeError, TypeError) as e:
                        # Fallback if metadata parsing fails
                        logger.warning(f"Failed to parse metadata: {e}")
                        error_details = f"Upload failed: {error_msg or 'Unknown error'}"
                        error_details += f"\nRaw metadata: {metadata}"
                else:
                    error_details = f"Upload failed: {error_msg or 'Unknown error'}"

                logger.error(error_details)
                raise RuntimeError(error_details)
            return False

        timeout = Config.UPLOAD_POLL_ATTEMPTS * Config.POLL_INTERVAL_SECONDS
        poll_until(
            check_upload_complete,
            timeout,
            Config.POLL_INTERVAL_SECONDS,
            f"Upload timed out after {timeout} seconds",
        )
        return upload_arn

    def upload_app(
        self,
        project_arn: str,
        app_path: str,
        upload_name: str,
        upload_type: UploadTypeType,
    ) -> str:
        """
        Upload mobile app to Device Farm and wait for completion.

        Args:
            project_arn: Device Farm project ARN
            app_path: Local path to app file (.apk for Android, .ipa for iOS)
            upload_name: Upload name (e.g., "app.apk" or "app.ipa")
            upload_type: Upload type ("ANDROID_APP" for .apk, "IOS_APP" for .ipa)

        Returns:
            Upload ARN (can be used as app ARN)

        Raises:
            RuntimeError: If upload fails or times out
        """
        logger.info(f"Uploading app: {app_path} (this may take a while)")

        # Create upload
        response: CreateUploadResultTypeDef = self.client.create_upload(
            projectArn=project_arn, name=upload_name, type=upload_type
        )

        upload = response["upload"]
        upload_arn = upload.get("arn") or ""
        upload_url = upload.get("url") or ""
        if not upload_arn or not upload_url:
            raise RuntimeError("Device Farm create_upload response missing arn or url")
        logger.debug(f"Upload initiated: {upload_arn}")

        # Upload file to presigned URL
        with open(app_path, "rb") as f:
            upload_response = requests.put(upload_url, data=f)
            upload_response.raise_for_status()

        logger.debug("File uploaded to presigned URL")

        # Poll upload status
        return self._poll_upload_status(upload_arn)

    def find_existing_upload(
        self, project_arn: str, upload_name: str, upload_type: UploadTypeType
    ) -> str | None:
        """
        Find an existing successful upload by filename and type.

        Searches Device Farm uploads for a previously uploaded app with the same
        filename, returning the most recently created match. This avoids redundant
        uploads when the same app file is used across multiple test runs.

        Args:
            project_arn: Device Farm project ARN
            upload_name: Upload filename to match
            upload_type: Upload type ("ANDROID_APP" or "IOS_APP")

        Returns:
            Upload ARN if a matching successful upload exists, None otherwise
        """
        logger.debug(f"Checking for existing upload: {upload_name}")

        # Collect all uploads across pages
        all_uploads: list[UploadTypeDef] = []
        next_token: str | None = None

        while True:
            kwargs: dict = {"arn": project_arn, "type": upload_type}
            if next_token:
                kwargs["nextToken"] = next_token

            response: ListUploadsResultTypeDef = self.client.list_uploads(**kwargs)
            all_uploads.extend(response["uploads"])

            next_token = response.get("nextToken")
            if not next_token:
                break

        # Get the most recent upload
        matches = [
            u
            for u in all_uploads
            if u.get("name") == upload_name and u.get("status") == "SUCCEEDED"
        ]
        if matches:
            best = max(matches, key=lambda u: u.get("created") or datetime.min)
            arn = best.get("arn")
            if arn:
                logger.debug(f"Found existing upload: {arn}")
                return str(arn)

        logger.debug("No existing upload found")
        return None

    def create_session(
        self,
        project_arn: str,
        device_arn: str,
        session_name: str,
        app_arn: str | None = None,
    ) -> str:
        """
        Create a Remote Access session.

        Args:
            project_arn: Device Farm project ARN
            device_arn: Device ARN to use
            session_name: Name for the session
            app_arn: Optional app ARN — if provided, Device Farm pre-installs the app
                     before the session reaches RUNNING state

        Returns:
            Session ARN
        """
        logger.debug(f"Creating session: {session_name}")
        kwargs: dict = {
            "projectArn": project_arn,
            "deviceArn": device_arn,
            "name": session_name,
        }
        if app_arn:
            kwargs["appArn"] = app_arn
            logger.debug(f"App will be pre-installed via appArn: {app_arn}")

        response: CreateRemoteAccessSessionResultTypeDef = (
            self.client.create_remote_access_session(**kwargs)
        )

        session_arn = response["remoteAccessSession"].get("arn") or ""
        if not session_arn:
            raise RuntimeError(
                "Device Farm create_remote_access_session response missing arn"
            )
        logger.debug(f"Session created: {session_arn}")
        return str(session_arn)

    def wait_for_session_running(
        self, session_arn: str, timeout: int = Config.MAX_WAIT_SECONDS
    ) -> None:
        """
        Poll session status until RUNNING.

        Args:
            session_arn: Session ARN to poll
            timeout: Maximum wait time in seconds (default: Config.MAX_WAIT_SECONDS)

        Raises:
            RuntimeError: If session fails to reach RUNNING state
        """
        logger.debug("Polling session status...")

        def check_session_running():
            response: GetRemoteAccessSessionResultTypeDef = (
                self.client.get_remote_access_session(arn=session_arn)
            )
            session = response["remoteAccessSession"]
            status = session.get("status", "")
            logger.debug(f"Session status: {status}")

            if status == "RUNNING":
                return True
            if status in ("COMPLETED", "STOPPING"):
                message = session.get("message", "")
                raise RuntimeError(
                    f"Session entered terminal state {status}"
                    + (f": {message}" if message else "")
                )
            return False

        poll_until(
            check_session_running,
            timeout,
            Config.POLL_INTERVAL_SECONDS,
            f"Session failed to reach RUNNING state after {timeout} seconds",
        )

    def get_session_endpoint(self, session_arn: str) -> str:
        """
        Extract Appium endpoint from session.

        Args:
            session_arn: Session ARN

        Returns:
            Appium endpoint URL (HTTPS)
        """
        response: GetRemoteAccessSessionResultTypeDef = (
            self.client.get_remote_access_session(arn=session_arn)
        )
        session = response["remoteAccessSession"]
        endpoints = session.get("endpoints") or {}
        endpoint = endpoints.get("remoteDriverEndpoint") or ""
        if not endpoint:
            raise RuntimeError(
                "Device Farm session response missing remoteDriverEndpoint"
            )
        logger.debug(f"Endpoint: {endpoint[:80]}...")
        return str(endpoint)

    def create_project(self, name: str) -> str:
        """
        Create a Device Farm project.

        Args:
            name: Project name

        Returns:
            Project ARN
        """
        response: CreateProjectResultTypeDef = self.client.create_project(name=name)
        arn = response["project"].get("arn") or ""
        if not arn:
            raise RuntimeError("Device Farm create_project response missing arn")
        return str(arn)

    def list_projects(self) -> list:
        """
        List all Device Farm projects.

        Returns:
            List of project dictionaries
        """
        response: ListProjectsResultTypeDef = self.client.list_projects()
        return list(response.get("projects", []))

    def list_devices(self) -> list:
        """
        List all available Device Farm devices.

        Returns:
            List of device dictionaries with platform, name, ARN, etc.
        """
        response: ListDevicesResultTypeDef = self.client.list_devices()
        return list(response.get("devices", []))

    def discover_project(self) -> str:
        """
        Auto-discover Device Farm project (returns first project found, creates one if none exist).

        Returns:
            Project ARN

        Raises:
            RuntimeError: If creation fails
        """
        try:
            projects = self.list_projects()

            if projects:
                project_arn = projects[0]["arn"]
                logger.debug(f"Discovered project: {project_arn}")
                return str(project_arn)

            logger.debug("No projects found, creating default project...")
            return self.create_default_project()

        except Exception as e:
            raise RuntimeError(f"Failed to discover project: {e}") from e

    def create_default_project(self) -> str:
        """
        Create a default Device Farm project for Nova Act actuation.

        Returns:
            Project ARN

        Raises:
            RuntimeError: If creation fails
        """
        try:
            project_name = "Nova Act Mobile Actuation"
            logger.debug(f"Creating default project: {project_name}")
            project_arn = self.create_project(project_name)
            logger.debug(f"Created project: {project_arn}")
            return project_arn
        except Exception as e:
            raise RuntimeError(f"Failed to create default project: {e}") from e

    def get_project_arn(self, project_arn_arg: str | None) -> str:
        """
        Get project ARN from CLI arg or auto-discovery.

        Args:
            project_arn_arg: Project ARN from command-line argument (or None)

        Returns:
            Project ARN string
        """
        if project_arn_arg:
            logger.debug(f"Using provided project ARN: {project_arn_arg}")
            return project_arn_arg

        logger.debug("No project ARN provided, auto-discovering...")
        return self.discover_project()

    def discover_device(self, platform: Platform) -> DeviceTypeDef:
        """Auto-discover the newest available device for the given platform.

        Filters to remote-access-enabled devices and picks the one with the
        highest OS version.

        Args:
            platform: Platform type

        Returns:
            Device dictionary from AWS

        Raises:
            RuntimeError: If no suitable device is found
        """
        try:
            devices = self.list_devices()
        except Exception as e:
            raise RuntimeError(f"Failed to discover {platform} device: {e}") from e

        df_platform: DevicePlatformType = platform.device_farm_platform

        candidates = [
            d
            for d in devices
            if d.get("platform") == df_platform and d.get("remoteAccessEnabled") is True
        ]

        if not candidates:
            platform_devices = [d for d in devices if d.get("platform") == df_platform]
            if platform_devices:
                raise RuntimeError(
                    f"No {platform} devices with remote access enabled found in Device Farm. "
                    f"Found {len(platform_devices)} device(s) but none support remote access."
                )
            raise RuntimeError(
                f"No {platform} devices found in Device Farm. "
                f"Available platforms: {set(d.get('platform', 'UNKNOWN') for d in devices)}"
            )

        if platform == Platform.IOS:
            candidates.sort(
                key=lambda d: (_iphone_model_key(d), _os_version_key(d)),
                reverse=True,
            )
        else:
            candidates.sort(key=_os_version_key, reverse=True)

        device = candidates[0]
        logger.debug(
            f"Auto-selected {platform} device: {device.get('name')} (OS {device.get('os')}, ARN: {device.get('arn')})"
        )
        return device

    def validate_device(self, device_arn: str, platform: Platform) -> DeviceTypeDef:
        """
        Validate device ARN format, fetch device info, and verify platform matches.

        Args:
            device_arn: Device ARN to validate
            platform: Expected platform

        Returns:
            Device info dictionary from AWS (DeviceTypeDef)

        Raises:
            ValueError: If ARN format is invalid
            RuntimeError: If device does not exist, is inaccessible, or platform mismatch
        """
        # Validate ARN format
        if "arn:aws:devicefarm:" not in device_arn:
            raise ValueError(
                f"Invalid device ARN format: {device_arn}. "
                "Device ARN should contain 'arn:aws:devicefarm:'"
            )

        try:
            # Fetch device info
            response: GetDeviceResultTypeDef = self.client.get_device(arn=device_arn)
            device = response["device"]

            # Verify platform matches
            device_platform = device.get("platform", "")
            expected_platform: DevicePlatformType = platform.device_farm_platform

            if device_platform != expected_platform:
                raise RuntimeError(
                    f"Platform mismatch: Device {device_arn} is {device_platform}, "
                    f"but expected {expected_platform}. Please provide a {platform} device ARN."
                )

            logger.debug(f"Validated device: {device.get('name')} ({device_platform})")
            return device

        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to validate device {device_arn}: {e}") from e

    def get_device(
        self, device_arn_arg: str | None, platform: Platform
    ) -> DeviceTypeDef:
        """
        Get device from argument or auto-discovery.

        Args:
            device_arn_arg: Device ARN from command-line argument (or None)
            platform: Platform type

        Returns:
            Device dictionary with 'arn', 'name', 'platform', 'os', etc.

        Raises:
            RuntimeError: If device ARN is invalid or platform mismatch
        """
        if device_arn_arg:
            logger.debug(f"Using device ARN: {device_arn_arg}")
            return self.validate_device(device_arn_arg, platform)

        logger.debug(f"No device ARN provided, auto-discovering {platform} device...")
        return self.discover_device(platform)

    @staticmethod
    def extract_platform_version(device_dict: DeviceTypeDef) -> str:
        """
        Extract platform version from device dictionary.

        Args:
            device_dict: Device dictionary from AWS

        Returns:
            Platform version string (e.g., "11" or "17.0")
        """
        os_version = device_dict.get("os", "")
        # Extract version number from OS string (e.g., "11" from "11" or "17.0" from "17.0")
        return str(os_version)

    def setup_session(
        self,
        project_arn: str | None,
        device_arn: str | None,
        platform: Platform,
        app_name: str | None = None,
        app_path: str | None = None,
        app_arn: str | None = None,
        app_type: UploadTypeType = "ANDROID_APP",
        force_app_upload: bool = False,
    ) -> DeviceFarmSessionResult:
        """Set up a complete Device Farm session.

        Orchestrates project/device discovery, app upload, session creation,
        and app installation. Returns a DeviceFarmSessionResult with the endpoint URL
        and device metadata.

        Args:
            project_arn: Device Farm project ARN (None to auto-discover)
            device_arn: Device ARN (None to auto-discover)
            platform: Target platform (ANDROID/IOS)
            app_name: Display name for upload and session naming (None for pre-installed apps)
            app_path: Path to .apk/.ipa file (None to skip upload)
            app_arn: Pre-existing upload ARN (skips upload and lookup entirely)
            app_type: Device Farm upload type (e.g., "ANDROID_APP")
            force_app_upload: Force upload even if app already exists

        Returns:
            DeviceFarmSessionResult with endpoint URL and device metadata
        """
        logger.info("=== Device Farm Session Setup ===")

        # Step 1: Resolve project
        logger.info("[1/5] Resolving project...")
        resolved_project_arn = self.get_project_arn(project_arn)
        logger.info(f"✓ Project: {resolved_project_arn}")

        # Step 2: Resolve device
        logger.info("[2/5] Resolving device...")
        device = self.get_device(device_arn, platform)
        resolved_device_arn = device.get("arn", "")
        device_name = device.get("name", "Unknown Device")
        platform_version = self.extract_platform_version(device)
        logger.info(f"✓ Device: {device_name} ({platform} {platform_version})")

        # Step 3: Resolve app ARN
        if app_arn:
            # Pre-existing ARN provided — skip upload entirely
            logger.info(f"[3/5] Using provided app ARN: {app_arn[:80]}...")
        elif app_path:
            if not app_name:
                raise ValueError(
                    "app_name is required when uploading an app (app_path is set). "
                    "Provide app_name or derive it from the file path."
                )
            upload_name = app_name
            if not upload_name.endswith((".apk", ".ipa")):
                upload_name = f"{upload_name}{platform.app_file_extension}"

            logger.info("[3/5] Resolving upload...")
            if not force_app_upload:
                existing_arn = self.find_existing_upload(
                    project_arn=resolved_project_arn,
                    upload_name=upload_name,
                    upload_type=app_type,
                )
                if existing_arn:
                    app_arn = existing_arn
                    logger.info(f"✓ App: {upload_name} (reused)")

            if not app_arn:
                app_arn = self.upload_app(
                    project_arn=resolved_project_arn,
                    app_path=app_path,
                    upload_name=upload_name,
                    upload_type=app_type,
                )
                logger.info(f"✓ App: {upload_name} (uploaded)")
        else:
            logger.warning(
                "[3/5] No app path or ARN provided — assuming app is pre-installed on device. "
                "If your app is not a system app, provide --app-path or --app-arn."
            )

        # Step 4: Create session (with appArn so Device Farm pre-installs before RUNNING)
        logger.info("[4/5] Creating session...")
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        session_name = (
            f"Nova Act {app_name} - {timestamp}"
            if app_name
            else f"Nova Act - {timestamp}"
        )
        session_arn = self.create_session(
            project_arn=resolved_project_arn,
            device_arn=resolved_device_arn,
            session_name=session_name,
            app_arn=app_arn,
        )
        logger.info(f"✓ Session: {session_arn}")

        try:
            # Step 5: Wait for session — app is installed once RUNNING
            logger.info("[5/5] Waiting for session to reach RUNNING state...")

            def check_session_running() -> bool:
                response: GetRemoteAccessSessionResultTypeDef = (
                    self.client.get_remote_access_session(arn=session_arn)
                )
                session = response["remoteAccessSession"]
                status = session.get("status", "")
                logger.debug(f"Session status: {status}")
                if status == "RUNNING":
                    return True
                if status in ("COMPLETED", "STOPPING"):
                    message = session.get("message", "")
                    raise RuntimeError(
                        f"Session entered terminal state {status}"
                        + (f": {message}" if message else "")
                    )
                print(".", end="", flush=True)
                return False

            poll_until(
                check_session_running,
                Config.MAX_WAIT_SECONDS,
                Config.POLL_INTERVAL_SECONDS,
                f"Session failed to reach RUNNING state after {Config.MAX_WAIT_SECONDS} seconds",
            )
            print()  # newline after dots
            logger.info("✓ Session is RUNNING — app is installed and ready")

            # Extract endpoint
            endpoint_url = self.get_session_endpoint(session_arn)
            logger.info(f"✓ Endpoint: {endpoint_url[:80]}...")

            # Re-fetch session to get the real ARN (initial ARN may have placeholder IDs)
            running_response: GetRemoteAccessSessionResultTypeDef = (
                self.client.get_remote_access_session(arn=session_arn)
            )
            session_arn = str(
                running_response["remoteAccessSession"].get("arn", session_arn)
            )

        except BaseException:
            # Clean up session on any failure — timeout, terminal state, KeyboardInterrupt
            logger.warning("Session setup failed — stopping Device Farm session")
            self.stop_session(session_arn)
            raise

        # Print console URL for easy access
        project_id = resolved_project_arn.split(":")[-1]
        session_id = session_arn.split("/")[-1]
        console_url = (
            f"https://us-west-2.console.aws.amazon.com/devicefarm/home"
            f"#/mobile/projects/{project_id}/sessions/{session_id}/00000/"
        )
        logger.info(f"✓ Console: {console_url}")

        logger.info("=== Device Farm Session Setup Complete ===")

        return DeviceFarmSessionResult(
            endpoint_url=endpoint_url,
            session_arn=session_arn,
            device_name=device_name,
            platform_version=platform_version,
        )

    def stop_session(self, session_arn: str) -> None:
        """
        Stop a remote access session.

        Best-effort — logs a warning if the session is already gone (e.g., timed out
        or stopped from the AWS console) instead of raising.

        Args:
            session_arn: Session ARN to stop
        """
        from botocore.exceptions import ClientError

        try:
            logger.info("=== Stopping Device Farm Session ===")
            self.client.stop_remote_access_session(arn=session_arn)
            logger.info("✓ Session stopped")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "NotFoundException":
                logger.warning(f"Session already terminated (not found): {session_arn}")
            else:
                logger.error(f"Failed to stop session: {e}")
                raise RuntimeError(f"Failed to stop session: {e}") from e
        except Exception as e:
            logger.error(f"Failed to stop session: {e}")
            raise RuntimeError(f"Failed to stop session: {e}") from e

    


