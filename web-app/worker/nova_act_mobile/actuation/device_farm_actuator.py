"""Device Farm actuator that extends MobileActuator with session lifecycle.

Provisions a Device Farm remote access session in start() and tears it down in stop(),
so the actuator can be handed directly to NovaAct without external session management.
"""

from typing import Any

from nova_act.util.logging import setup_logging

from nova_act_mobile.actuation.appium_instance_options import (
    AppiumInstanceOptions,
)
from nova_act_mobile.actuation.mobile_actuator import (
    MobileActuator,
)
from nova_act_mobile.app import MobileAppConfig
from nova_act_mobile.device_farm import (
    DeviceFarmClient,
    DeviceFarmSessionResult,
    DeviceFarmUploadConfig,
)
from nova_act_mobile.platform import Platform

_LOGGER = setup_logging(__name__)

_DEFAULT_ADB_EXEC_TIMEOUT_MS = 60000


class DeviceFarmActuator(MobileActuator):
    """Mobile actuator that provisions its own Device Farm session.

    Extends MobileActuator to manage the full Device Farm lifecycle:
    - start(): provisions Device Farm session, then starts Appium driver
    - stop(): stops Appium driver, then tears down Device Farm session

    Example:
        app = MobileAppConfig.for_android(app_package="com.example", app_activity=".Main")
        upload = DeviceFarmUploadConfig(app_name="my-app", app_path="/path/to/app.apk")

        with NovaAct(
            actuator=DeviceFarmActuator(app_config=app, upload_config=upload),
            starting_page=MobileActuator.app_url(app.app_identifier),
        ) as nova:
            nova.act("...")
    """

    def __init__(
        self,
        app_config: MobileAppConfig,
        upload_config: DeviceFarmUploadConfig | None = None,
        project_arn: str | None = None,
        device_arn: str | None = None,
        adb_exec_timeout_ms: int = _DEFAULT_ADB_EXEC_TIMEOUT_MS,
    ):
        """Initialize Device Farm actuator.

        Does not call super().__init__() — the parent is initialized in start()
        once Device Farm provides the Appium endpoint.

        Args:
            app_config: Mobile app identity (platform, package/activity/bundle_id)
            upload_config: Device Farm upload configuration (app binary path, ARN, etc.).
                None if testing a pre-installed app.
            project_arn: Device Farm project ARN (optional, auto-discovers if None)
            device_arn: Device Farm device ARN (optional, auto-discovers if None)
            adb_exec_timeout_ms: ADB command timeout in milliseconds (default: 60000)
        """
        # Intentionally skip super().__init__() — we don't have AppiumInstanceOptions
        # until Device Farm gives us an endpoint in start().
        self._app_config = app_config
        self._upload_config = upload_config
        self._project_arn = project_arn
        self._device_arn = device_arn
        self._adb_exec_timeout_ms = adb_exec_timeout_ms
        self._df_client = DeviceFarmClient()
        self._session_result: DeviceFarmSessionResult | None = None

    def _build_appium_options(
        self, session_result: DeviceFarmSessionResult
    ) -> AppiumInstanceOptions:
        """Build AppiumInstanceOptions from a Device Farm session result."""
        common_options = {
            "appium_server_url": session_result.endpoint_url,
            "platform": self._app_config.platform,
            "device_name": session_result.device_name,
            "no_reset": True,
            "auto_launch": False,
            "record_video": True,
            "additional_capabilities": {
                "appium:adbExecTimeout": self._adb_exec_timeout_ms,
            },
        }

        if self._app_config.platform == Platform.ANDROID:
            return AppiumInstanceOptions(
                **common_options,
                app_package=self._app_config.app_package,
                app_activity=self._app_config.app_activity,
            )
        elif self._app_config.platform == Platform.IOS:
            return AppiumInstanceOptions(
                **common_options,
                bundle_id=self._app_config.bundle_id,
            )

        raise ValueError(f"Unsupported platform: {self._app_config.platform}")

    @property
    def started(self, **kwargs: Any) -> bool:  # type: ignore[explicit-any]
        """Check if the actuator is fully started."""
        if self._session_result is None:
            return False
        return super().started

    def start(self, **kwargs: Any) -> None:  # type: ignore[explicit-any]
        """Provision Device Farm session, then start Appium driver."""
        if self._session_result is not None:
            _LOGGER.warning("Device Farm session already provisioned")
            super().start(**kwargs)
            return

        _LOGGER.info("Provisioning Device Farm session...")
        self._session_result = self._df_client.setup_session(
            project_arn=self._project_arn,
            device_arn=self._device_arn,
            platform=self._app_config.platform,
            app_name=self._upload_config.app_name if self._upload_config else None,
            app_path=self._upload_config.app_path if self._upload_config else None,
            app_arn=self._upload_config.app_arn if self._upload_config else None,
            app_type=self._app_config.platform.device_farm_upload_type,
            force_app_upload=self._upload_config.force_upload
            if self._upload_config
            else False,
        )

        appium_options = self._build_appium_options(self._session_result)
        super().__init__(appium_options=appium_options)
        super().start(**kwargs)

    def stop(self, **kwargs: Any) -> None:  # type: ignore[explicit-any]
        """Stop Appium driver, then tear down Device Farm session.

        Preserves the session ARN in `stopped_session_arn` so callers can
        download the video artifact later (Device Farm needs several minutes
        after stop to finalize artifacts).
        """
        if self._session_result is not None:
            # Preserve ARN for post-stop video download
            self._stopped_session_arn = self._session_result.session_arn

            try:
                super().stop(**kwargs)
            except Exception as e:
                _LOGGER.error(f"Failed to stop Appium driver: {e}")

        if self._session_result is not None:
            try:
                self._df_client.stop_session(
                    session_arn=self._session_result.session_arn
                )
            except Exception as e:
                _LOGGER.error(f"Failed to stop Device Farm session: {e}")
            finally:
                self._session_result = None

    @property
    def stopped_session_arn(self) -> str | None:
        """Session ARN from the last stopped session, for post-stop artifact retrieval."""
        return getattr(self, "_stopped_session_arn", None)


    @property
    def session_result(self) -> DeviceFarmSessionResult | None:
        """The active Device Farm session result, if provisioned."""
        return self._session_result
