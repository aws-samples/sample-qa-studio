"""Mobile actuator for Nova Act using Appium.

Implements BrowserActuatorBase to drive iOS and Android devices through Appium.
Infrastructure-agnostic — works with any Appium server (local, Device Farm,
BrowserStack, etc.). For Device Farm integration, see DeviceFarmActuator.
"""

import time
from datetime import UTC, datetime
from typing import Any, Literal, NamedTuple
from urllib.parse import quote, unquote

from appium.webdriver.webdriver import WebDriver
from nova_act import JSONType
from nova_act.tools.browser.default.util.bbox_parser import parse_bbox_string
from nova_act.tools.browser.interface.browser import (
    BrowserActuatorBase,
    BrowserObservation,
)
from nova_act.tools.browser.interface.types.click_types import ClickOptions
from nova_act.tools.browser.interface.types.dimensions_dict import DimensionsDict
from nova_act.tools.browser.interface.types.scroll_types import ScrollDirection
from nova_act.types.api.step import BboxTLBR
from nova_act.util.logging import setup_logging

from nova_act_mobile.actuation.appium_driver_manager import (
    AppiumDriverManagerBase,
)
from nova_act_mobile.actuation.appium_instance_manager import (
    AppiumInstanceManager,
)
from nova_act_mobile.actuation.appium_instance_options import (
    AppiumInstanceOptions,
)
from nova_act_mobile.actuation.util.mobile_app_management import (
    launch_app,
    open_deep_link,
)
from nova_act_mobile.actuation.util.mobile_click import (
    mobile_click,
)
from nova_act_mobile.actuation.util.mobile_observation import (
    get_screen_dimensions,
    get_ui_hierarchy,
    parse_ui_hierarchy,
    take_mobile_screenshot,
)
from nova_act_mobile.actuation.util.mobile_scroll import (
    mobile_scroll,
)
from nova_act_mobile.actuation.util.mobile_type import (
    mobile_type,
)
from nova_act_mobile.actuation.util.mobile_wait import (
    _is_session_error,
    wait_for_app_idle,
)
from nova_act_mobile.platform import Platform

_LOGGER = setup_logging(__name__)

_MAX_OBSERVATION_RETRIES = 3
_SESSION_RECOVERY_BACKOFF_S = 3.0
_APP_URL_PREFIX = "https://"
_DEEP_LINK_PATH = "/deeplink/"
_ACTIVITY_PATH = "/activity/"


class MobileActuator(BrowserActuatorBase, AppiumDriverManagerBase):
    """Default actuator for Nova Act Mobile automation using Appium.

    This actuator provides mobile automation capabilities for iOS and Android
    devices using the Appium framework. It implements the BrowserActuatorBase
    interface to provide a consistent API compatible with browser automation.

    Can be constructed directly with AppiumInstanceOptions for any Appium server,
    or subclassed to add infrastructure provisioning (see DeviceFarmActuator).
    """

    class _BboxScale(NamedTuple):
        """Precomputed scale factors: resized-screenshot-space → driver-space.

        Computed once per observation from the resized screenshot dimensions and
        the driver's coordinate space (logical points on iOS, pixels on Android).
        """

        sx: float
        sy: float

    def __init__(self, appium_options: AppiumInstanceOptions):
        """Initialize the mobile actuator.

        Args:
            appium_options: Configuration options for the Appium session.
        """
        self._appium_manager = AppiumInstanceManager(appium_options)
        self._platform = appium_options.platform
        self._app_identifier = (
            appium_options.app_package
            if appium_options.platform == Platform.ANDROID
            else appium_options.bundle_id
        ) or ""
        self._platform_info = (
            f"{appium_options.platform}/{appium_options.platform_version} "
            f"Device={appium_options.device_name} "
            f"Automation={appium_options.automation_name}"
        )
        # Precomputed scale factors for converting model bounding boxes
        # (in resized-screenshot space) to the driver's coordinate space.
        # Set on each observation; actions must not be called before the
        # first observation.
        self._bbox_scale: MobileActuator._BboxScale | None = None

    def start(self, **kwargs: Any) -> None:  # type: ignore[explicit-any]
        """Start the Appium driver session and launch the app.

        Args:
            **kwargs: Additional arguments. Supports:
                - starting_page: App URL from app_url() — used to launch the app.
                - session_logs_directory: Directory for session logs and recordings.
        """
        if not self._appium_manager.started:
            session_logs_directory = kwargs.get("session_logs_directory")
            self._appium_manager.start(session_logs_directory)

        starting_page = kwargs.get("starting_page")
        if starting_page:
            self.go_to_url(starting_page)

    def stop(self, **kwargs: Any) -> None:  # type: ignore[explicit-any]
        """Stop the Appium driver session.

        Args:
            **kwargs: Additional arguments (currently unused).
        """
        if self.started:
            self._appium_manager.stop()

    @property
    def started(self, **kwargs: Any) -> bool:  # type: ignore[explicit-any]
        """Check if the Appium driver is started.

        Returns:
            True if driver is active, False otherwise.
        """
        return self._appium_manager.started

    def get_driver(self) -> WebDriver:
        """Get the active Appium WebDriver instance.

        Returns:
            The active WebDriver instance.
        """
        return self._appium_manager.driver

    @property
    def driver(self) -> WebDriver:
        """The active Appium WebDriver managed by this instance.

        Returns:
            The active WebDriver instance.
        """
        return self._appium_manager.driver

    def _scale_bbox(self, bbox: BboxTLBR) -> BboxTLBR:
        """Scale bbox from resized-screenshot space to driver coordinate space.

        The model outputs bounding boxes in the resized screenshot's pixel
        coordinate space.  This method converts them to the coordinate space
        the Appium driver expects for touch actions:

        - Android (UIAutomator2): native pixel coordinates.
        - iOS (XCUITest): logical point coordinates.

        Args:
            bbox: Bounding box in resized-screenshot pixel coordinates.

        Returns:
            Bounding box in the driver's coordinate space.

        Raises:
            RuntimeError: If called before the first observation.
        """
        if self._bbox_scale is None:
            raise RuntimeError(
                "Cannot scale bounding box — no observation has been taken yet"
            )

        s = self._bbox_scale
        return BboxTLBR(
            top=bbox.top * s.sy,
            left=bbox.left * s.sx,
            bottom=bbox.bottom * s.sy,
            right=bbox.right * s.sx,
        )

    def agent_click(
        self,
        box: str,
        click_type: Literal["left", "left-double", "right"] | None = None,
        click_options: ClickOptions | None = None,
    ) -> JSONType:
        """Perform a tap action at the center of the specified box.

        Args:
            box: Bounding box string specifying the tap target.
            click_type: Type of click - "left" for tap, "left-double" for double tap,
                       "right" for long press.
            click_options: Additional click options (delays, etc.).

        Returns:
            None
        """
        bbox = self._scale_bbox(parse_bbox_string(box))
        mobile_click(bbox, self.driver, click_type or "left", click_options)
        return None

    def agent_hover(self, box: str) -> JSONType:
        """Hovers on the center of the specified box."""
        raise NotImplementedError("MobileActuator does not yet support agentHover.")

    def agent_scroll(
        self,
        direction: ScrollDirection,
        box: str,
        value: float | None = None,
    ) -> JSONType:
        """Perform a swipe gesture in the specified direction within the box.

        Args:
            direction: Direction to scroll (up, down, left, right).
            box: Bounding box string specifying the scrollable area.
            value: Optional scroll distance in pixels.

        Returns:
            None
        """
        bbox = self._scale_bbox(parse_bbox_string(box))
        mobile_scroll(self.driver, direction, bbox, value)
        return None

    def agent_type(self, value: str, box: str, pressEnter: bool = False) -> JSONType:
        """Type text into an element at the specified box.

        Args:
            value: Text to type.
            box: Bounding box string specifying the input element.
            pressEnter: Whether to press Enter/Return after typing.

        Returns:
            None
        """
        bbox = self._scale_bbox(parse_bbox_string(box))
        try:
            mobile_type(bbox, value, self.driver, "pressEnter" if pressEnter else None)
        except Exception as e:
            # Don't raise — let the agent attempt to recover from a bad type
            _LOGGER.warning(f"Type action failed for value '{value}': {e}")
        return None

    @staticmethod
    def app_url(
        app_identifier: str,
        deep_link: str | None = None,
        activity: str | None = None,
    ) -> str:
        """Build a URL for use with NovaAct's starting_page or go_to_url.

        The Nova Act SDK requires valid https:// URLs for both starting_page and
        go_to_url. This method encodes a mobile app identifier (and optional deep
        link or activity) into an https:// URL that the actuator knows how to
        decode and dispatch to the correct Appium action.

        Args:
            app_identifier: App package name (Android) or bundle ID (iOS).
                Example: "com.android.chrome", "com.apple.mobilesafari"
            deep_link: Optional deep link URL to open within the app.
                Example: "myapp://screen/detail?id=123"
            activity: Optional Android activity to launch via
                ``mobile: startActivity``. iOS has no activity concept —
                use deep links instead.
                Example: "com.example.app.Activities.DetailActivity"

        Returns:
            URL for use with starting_page or go_to_url:
            - App launch:      "https://<app_identifier>"
            - Deep link:       "https://<app_identifier>/deeplink/<encoded>"
            - Activity launch: "https://<app_identifier>/activity/<encoded>"

        Examples:
            nova = NovaAct(starting_page=MobileActuator.app_url("com.example.app"))
            nova.go_to_url(MobileActuator.app_url("com.example.app", deep_link="myapp://scores"))
            nova.go_to_url(MobileActuator.app_url("com.example.app", activity=".DetailActivity"))
        """
        if deep_link and activity:
            raise ValueError("deep_link and activity are mutually exclusive")
        if deep_link:
            return f"{_APP_URL_PREFIX}{app_identifier}{_DEEP_LINK_PATH}{quote(deep_link, safe='')}"
        if activity:
            return f"{_APP_URL_PREFIX}{app_identifier}{_ACTIVITY_PATH}{quote(activity, safe='')}"
        return f"{_APP_URL_PREFIX}{app_identifier}"

    def go_to_url(self, url: str) -> JSONType:
        """Navigate to a URL by launching an app or opening a deep link.

        Decodes URLs produced by app_url() and dispatches to the
        appropriate Appium action.

        Args:
            url: URL produced by app_url().

        Returns:
            None
        """

        path = url.removeprefix(_APP_URL_PREFIX)

        if _DEEP_LINK_PATH in path:
            app_identifier, _, encoded_deep_link = path.partition(_DEEP_LINK_PATH)
            deep_link = unquote(encoded_deep_link)
            open_deep_link(self.driver, deep_link, app_identifier)
        elif _ACTIVITY_PATH in path:
            # Android-only: launch a specific exported activity via
            # mobile: startActivity. iOS has no activity concept —
            # use deep links instead.
            app_identifier, _, encoded_activity = path.partition(_ACTIVITY_PATH)
            activity = unquote(encoded_activity)
            self.driver.execute_script(
                "mobile: startActivity",
                {
                    "intent": f"{app_identifier}/{activity}",
                },
            )
        else:
            launch_app(self.driver, path)
        return None

    def get_viewport_size(self) -> DimensionsDict:
        """Return the current screen dimensions."""
        dims = get_screen_dimensions(self.driver)
        return {"width": dims["windowWidth"], "height": dims["windowHeight"]}

    def _return(self, value: str | None) -> JSONType:
        """Complete execution and return a value.

        Args:
            value: Optional return value.

        Returns:
            The provided value.
        """
        return value

    def think(self, value: str) -> JSONType:
        """Log reasoning about the next action (no effect on environment).

        Args:
            value: Reasoning text.

        Returns:
            None
        """
        pass

    def throw_agent_error(self, value: str) -> JSONType:
        """Indicate that the requested task is not possible.

        Args:
            value: Error message explaining why task cannot be completed.

        Returns:
            The error message.
        """
        return value

    def wait(self, seconds: float) -> JSONType:
        """Pause execution for the specified duration.

        Args:
            seconds: Duration to wait in seconds. If 0, waits for app to become idle.

        Returns:
            None

        Raises:
            ValueError: If seconds is negative.
        """
        if seconds < 0:
            raise ValueError("Seconds must be non-negative")

        if seconds == 0:
            self.wait_for_page_to_settle()
        else:
            time.sleep(seconds)
        return None

    def wait_for_page_to_settle(self) -> JSONType:
        """Wait for the mobile app to reach an idle state.

        Returns:
            None
        """
        wait_for_app_idle(self.driver)
        return None

    def take_observation(self) -> BrowserObservation:
        """Capture the current state of the mobile app.

        The screenshot is resized to match the Nova Act model's expected pixel
        budget (~1.3 M pixels) while preserving the device's native aspect
        ratio.  ``browserDimensions`` reports the resized image dimensions so
        the model's coordinate space matches the screenshot it receives.

        Returns:
            BrowserObservation containing:
            - activeURL: Current app identifier
            - browserDimensions: Resized screenshot dimensions
            - idToBboxMap: Element ID to bounding box mappings
            - screenshotBase64: Base64-encoded resized screenshot
            - simplifiedDOM: Simplified UI hierarchy
            - timestamp_ms: Observation timestamp
            - userAgent: Platform information

        Raises:
            Exception: If observation cannot be captured after retries.
        """
        for attempt in range(_MAX_OBSERVATION_RETRIES):
            try:
                # Get platform info
                user_agent = self._platform_info

                # Get UI hierarchy and parse it
                ui_hierarchy_xml = get_ui_hierarchy(self.driver)
                id_to_bbox_map, simplified_dom = parse_ui_hierarchy(
                    ui_hierarchy_xml,
                    self.driver,
                )

                # Take screenshot (resized to model pixel budget)
                screenshot_data_url, img_w, img_h = take_mobile_screenshot(
                    self.driver,
                )

                # Precompute scale factors for bbox conversion.
                window_size = self.driver.get_window_size()
                self._bbox_scale = MobileActuator._BboxScale(
                    sx=window_size["width"] / img_w,
                    sy=window_size["height"] / img_h,
                )

                # Get current app identifier
                active_url = self._app_identifier

                return {
                    "activeURL": active_url,
                    "browserDimensions": {
                        "scrollHeight": img_h,
                        "scrollLeft": 0,
                        "scrollTop": 0,
                        "scrollWidth": img_w,
                        "windowHeight": img_h,
                        "windowWidth": img_w,
                    },
                    "idToBboxMap": id_to_bbox_map,
                    "screenshotBase64": screenshot_data_url,
                    "simplifiedDOM": simplified_dom,
                    "timestamp_ms": int(datetime.now(UTC).timestamp() * 1000),
                    "userAgent": user_agent,
                }

            except Exception as e:
                if attempt == _MAX_OBSERVATION_RETRIES - 1:
                    # Last attempt failed, re-raise
                    raise

                if _is_session_error(e):
                    # Known Device Farm transient: the console viewer
                    # temporarily takes over the WDA session. Back off
                    # longer to give it time to recover — no point
                    # running wait_for_app_idle on a dead session.
                    _LOGGER.info(
                        f"Session temporarily unavailable (attempt "
                        f"{attempt + 1}/{_MAX_OBSERVATION_RETRIES}), "
                        f"waiting {_SESSION_RECOVERY_BACKOFF_S}s for recovery..."
                    )
                    time.sleep(_SESSION_RECOVERY_BACKOFF_S)
                else:
                    _LOGGER.warning(
                        f"Observation attempt {attempt + 1}/{_MAX_OBSERVATION_RETRIES} "
                        f"failed: {e}, retrying..."
                    )
                    # Wait briefly and retry
                    wait_for_app_idle(self.driver)
                    time.sleep(0.5)

        # Should not reach here, but make type checker happy
        raise RuntimeError("Failed to take observation after all retries")
