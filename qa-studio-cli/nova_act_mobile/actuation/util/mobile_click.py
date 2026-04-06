"""Mobile click/tap action implementation using W3C touch actions."""

from typing import Literal

from appium.webdriver.webdriver import WebDriver
from nova_act.tools.browser.interface.types.click_types import ClickOptions
from nova_act.types.api.step import BboxTLBR
from nova_act.util.logging import setup_logging
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput

_LOGGER = setup_logging(__name__)


def mobile_click(
    bbox: BboxTLBR,
    driver: WebDriver,
    click_type: Literal["left", "left-double", "right"] = "left",
    click_options: ClickOptions | None = None,
) -> None:
    """Perform a mobile tap action at the center of the specified bounding box.

    Args:
        bbox: Bounding box defining the tap target (BboxTLBR).
        driver: Appium WebDriver instance.
        click_type: Type of click to perform.
        click_options: Additional click options (delays, modifiers, etc.).

    Raises:
        ValueError: If click type is not supported on mobile.
    """
    # Calculate center coordinates from BboxTLBR
    center_x = (bbox.left + bbox.right) / 2
    center_y = (bbox.top + bbox.bottom) / 2

    _LOGGER.debug(f"Mobile click at ({center_x}, {center_y}) with type '{click_type}'")

    # Handle different click types
    if click_type == "right":
        # Right-click is typically long-press on mobile
        _perform_long_press(driver, int(center_x), int(center_y), click_options)
    elif click_type == "left-double":
        # Double tap
        _perform_double_tap(driver, int(center_x), int(center_y), click_options)
    else:  # "left" - standard tap
        _perform_tap(driver, int(center_x), int(center_y), click_options)


def _perform_tap(
    driver: WebDriver,
    x: int,
    y: int,
    click_options: ClickOptions | None = None,
) -> None:
    """Perform a single tap action.

    Args:
        driver: Appium WebDriver instance.
        x: X coordinate for the tap.
        y: Y coordinate for the tap.
        click_options: Optional click options (currently unused for mobile).
    """
    # Use W3C Actions API for more reliable touch actions
    actions = ActionBuilder(driver, mouse=PointerInput("touch", "finger"))  # type: ignore[no-untyped-call]

    # Perform tap: move to position, press, and release
    actions.pointer_action.move_to_location(x, y)  # type: ignore[no-untyped-call]
    actions.pointer_action.pointer_down()  # type: ignore[no-untyped-call]
    actions.pointer_action.pause(0.1)  # Brief pause for tap recognition
    actions.pointer_action.pointer_up()  # type: ignore[no-untyped-call]

    actions.perform()


def _perform_double_tap(
    driver: WebDriver,
    x: int,
    y: int,
    click_options: ClickOptions | None = None,
) -> None:
    """Perform a double tap action.

    Args:
        driver: Appium WebDriver instance.
        x: X coordinate for the tap.
        y: Y coordinate for the tap.
        click_options: Optional click options (currently unused for mobile).
    """
    actions = ActionBuilder(driver, mouse=PointerInput("touch", "finger"))  # type: ignore[no-untyped-call]

    # First tap
    actions.pointer_action.move_to_location(x, y)  # type: ignore[no-untyped-call]
    actions.pointer_action.pointer_down()  # type: ignore[no-untyped-call]
    actions.pointer_action.pause(0.05)
    actions.pointer_action.pointer_up()  # type: ignore[no-untyped-call]

    # Short pause between taps
    actions.pointer_action.pause(0.1)

    # Second tap
    actions.pointer_action.pointer_down()  # type: ignore[no-untyped-call]
    actions.pointer_action.pause(0.05)
    actions.pointer_action.pointer_up()  # type: ignore[no-untyped-call]

    actions.perform()


def _perform_long_press(
    driver: WebDriver,
    x: int,
    y: int,
    click_options: ClickOptions | None = None,
) -> None:
    """Perform a long press action (mobile equivalent of right-click).

    Args:
        driver: Appium WebDriver instance.
        x: X coordinate for the long press.
        y: Y coordinate for the long press.
        click_options: Optional click options (currently unused for mobile).
    """
    # Default press duration: 1 second
    duration = 1.0

    actions = ActionBuilder(driver, mouse=PointerInput("touch", "finger"))  # type: ignore[no-untyped-call]

    # Perform long press: move, press, hold, release
    actions.pointer_action.move_to_location(x, y)  # type: ignore[no-untyped-call]
    actions.pointer_action.pointer_down()  # type: ignore[no-untyped-call]
    actions.pointer_action.pause(duration)
    actions.pointer_action.pointer_up()  # type: ignore[no-untyped-call]

    actions.perform()
