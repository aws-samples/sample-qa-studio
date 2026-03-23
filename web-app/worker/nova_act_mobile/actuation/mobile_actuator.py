"""Mobile actuator for Nova Act using Appium.

Implements BrowserActuatorBase to drive iOS and Android devices through Appium.
Infrastructure-agnostic — works with any Appium server (local, Device Farm,
BrowserStack, etc.). For Device Farm integration, see DeviceFarmActuator.
"""

import time
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import quote, unquote

from appium.webdriver.webdriver import WebDriver
from nova_act import JSONType
from nova_act.tools.browser.default.util.bbox_parser import parse_bbox_string
from nova_act.tools.browser.interface.browser import (
    BrowserActuatorBase,
    BrowserObservation,
)
from nova_act.tools.browser.interface.types.click_types import ClickOptions
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
    smart_wait,
    wait_for_app_idle,
)
from nova_act_mobile.platform import Platform

_LOGGER = setup_logging(__name__)

_MAX_OBSERVATION_RETRIES = 3
_APP_URL_PREFIX = "https://"
_DEEP_LINK_PATH = "/deeplink/"


class MobileActuator(BrowserActuatorBase, AppiumDriverManagerBase):
    """Default actuator for Nova Act Mobile automation using Appium.

    This actuator provides mobile automation capabilities for iOS and Android
    devices using the Appium framework. It implements the BrowserActuatorBase
    interface to provide a consistent API compatible with browser automation.

    Can be constructed directly with AppiumInstanceOptions for any Appium server,
    or subclassed to add infrastructure provisioning (see DeviceFarmActuator).
    """

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
        self._pixel_ratio: float | None = None

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
        """Scale bbox from pixel space to point space for iOS real devices.

        iOS screenshots are in physical pixels but XCUITest expects touch
        coordinates in logical points. On simulators the ratio is 1 (no-op).
        On Android, UIAutomator2 uses pixel coordinates natively, so no
        scaling is needed.

        Args:
            bbox: Bounding box in screenshot pixel coordinates.

        Returns:
            Bounding box scaled to the driver's coordinate space.
        """
        if self._platform != Platform.IOS:
            return bbox

        if self._pixel_ratio is None:
            self._pixel_ratio = self._get_ios_pixel_ratio()

        if self._pixel_ratio == 1.0:
            return bbox

        r = self._pixel_ratio
        return BboxTLBR(
            top=bbox.top / r,
            left=bbox.left / r,
            bottom=bbox.bottom / r,
            right=bbox.right / r,
        )

    def _get_ios_pixel_ratio(self) -> float:
        """Compute the pixel ratio for an iOS device.

        iOS screenshots are captured in physical pixels, but XCUITest dispatches
        touch actions in logical points. On simulators the ratio is 1; on real
        Retina devices it is typically 2 or 3.

        Returns:
            The scale factor (pixels / points).
        """
        try:
            screenshot_base64 = self.driver.get_screenshot_as_base64()
            import base64
            import io

            from PIL import Image

            img = Image.open(io.BytesIO(base64.b64decode(screenshot_base64)))
            screenshot_width = img.width

            window_width = self.driver.get_window_size()["width"]
            if window_width > 0:
                ratio = screenshot_width / window_width
                _LOGGER.debug(
                    f"iOS pixel ratio: {ratio} "
                    f"(screenshot={screenshot_width}, window={window_width})"
                )
                return ratio
        except Exception as e:
            _LOGGER.warning(f"Failed to detect iOS pixel ratio: {e}")

        return 1.0

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
        mobile_type(bbox, value, self.driver, "pressEnter" if pressEnter else None)
        return None

    @staticmethod
    def app_url(app_identifier: str, deep_link: str | None = None) -> str:
        """Build a URL for use with NovaAct's starting_page or go_to_url.

        The Nova Act SDK requires valid https:// URLs for both starting_page and
        go_to_url. This method encodes a mobile app identifier (and optional deep
        link) into an https:// URL that the actuator knows how to decode and
        dispatch to the correct Appium action.

        Args:
            app_identifier: App package name (Android) or bundle ID (iOS).
                Example: "com.android.chrome", "com.apple.mobilesafari"
            deep_link: Optional deep link URL to open within the app.
                Example: "myapp://screen/detail?id=123"

        Returns:
            URL for use with starting_page or go_to_url:
            - App launch: "https://<app_identifier>"
            - Deep link:  "https://<app_identifier>/deeplink/<url_encoded_deep_link>"

        Examples:
            nova = NovaAct(starting_page=MobileActuator.app_url("com.tour.pgatour"))
            nova.go_to_url(MobileActuator.app_url("com.tour.pgatour", deep_link="pgatour://scores"))
        """
        if deep_link:
            return f"{_APP_URL_PREFIX}{app_identifier}{_DEEP_LINK_PATH}{quote(deep_link, safe='')}"
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
        else:
            launch_app(self.driver, path)
        return None

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

        smart_wait(self.driver, seconds)
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

        Returns:
            BrowserObservation containing:
            - activeURL: Current app identifier
            - browserDimensions: Screen dimensions
            - idToBboxMap: Element ID to bounding box mappings
            - screenshotBase64: Base64-encoded screenshot
            - simplifiedDOM: Simplified UI hierarchy
            - timestamp_ms: Observation timestamp
            - userAgent: Platform information

        Raises:
            Exception: If observation cannot be captured after retries.
        """
        for attempt in range(_MAX_OBSERVATION_RETRIES):
            try:
                # Get screen dimensions
                dimensions = get_screen_dimensions(self.driver)

                # Get platform info
                user_agent = self._platform_info

                # Get UI hierarchy and parse it
                ui_hierarchy_xml = get_ui_hierarchy(self.driver)
                id_to_bbox_map, simplified_dom = parse_ui_hierarchy(
                    ui_hierarchy_xml,
                    self._platform,
                )

                # Take screenshot
                screenshot_data_url = take_mobile_screenshot(self.driver)

                # Get current app identifier
                active_url = self._app_identifier

                return {
                    "activeURL": active_url,
                    "browserDimensions": {
                        "scrollHeight": dimensions["scrollHeight"],
                        "scrollLeft": dimensions["scrollLeft"],
                        "scrollTop": dimensions["scrollTop"],
                        "scrollWidth": dimensions["scrollWidth"],
                        "windowHeight": dimensions["windowHeight"],
                        "windowWidth": dimensions["windowWidth"],
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

                _LOGGER.warning(
                    f"Observation attempt {attempt + 1}/{_MAX_OBSERVATION_RETRIES} failed: {e}, retrying..."
                )
                # Wait briefly and retry
                wait_for_app_idle(self.driver)
                time.sleep(0.5)

        # Should not reach here, but make type checker happy
        raise RuntimeError("Failed to take observation after all retries")
