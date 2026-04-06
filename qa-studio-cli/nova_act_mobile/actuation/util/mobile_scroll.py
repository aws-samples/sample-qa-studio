"""Mobile scroll/swipe action implementation."""

from appium.webdriver.webdriver import WebDriver
from nova_act.tools.browser.interface.types.scroll_types import ScrollDirection
from nova_act.types.api.step import BboxTLBR
from nova_act.util.logging import setup_logging
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput

_LOGGER = setup_logging(__name__)

# Default scroll distances as percentage of element size
_DEFAULT_SCROLL_PERCENTAGE = 0.7


def mobile_scroll(
    driver: WebDriver,
    direction: ScrollDirection,
    bbox: BboxTLBR,
    value: float | None = None,
) -> None:
    """Perform a swipe gesture within the specified bounding box.

    Args:
        driver: Appium WebDriver instance.
        direction: Direction to scroll (up, down, left, right).
        bbox: Bounding box defining the scrollable area (BboxTLBR).
        value: Optional scroll amount. If provided, represents pixels to scroll.
               If None, scrolls by a percentage of the element size.

    Raises:
        ValueError: If direction is not supported.
    """
    # Calculate center and boundaries of the bbox
    center_x = (bbox.left + bbox.right) / 2
    center_y = (bbox.top + bbox.bottom) / 2

    # Calculate width and height from BboxTLBR
    width = bbox.right - bbox.left
    height = bbox.bottom - bbox.top

    # Determine scroll distance
    if value is not None:
        scroll_distance = abs(value)
    else:
        # Use percentage of element size
        if direction in ("up", "down"):
            scroll_distance = height * _DEFAULT_SCROLL_PERCENTAGE
        else:  # left or right
            scroll_distance = width * _DEFAULT_SCROLL_PERCENTAGE

    _LOGGER.info(
        f"Mobile scroll {direction} - bbox: top={bbox.top}, left={bbox.left}, "
        f"bottom={bbox.bottom}, right={bbox.right} (w={width:.0f}, h={height:.0f}), "
        f"distance={scroll_distance:.0f}px"
    )

    # Calculate start and end points for the swipe
    start_x, start_y, end_x, end_y = _calculate_swipe_coordinates(
        direction=direction,
        center_x=int(center_x),
        center_y=int(center_y),
        distance=int(scroll_distance),
        bbox=bbox,
    )

    _LOGGER.info(f"Swipe coordinates: ({start_x},{start_y}) → ({end_x},{end_y})")

    # Perform the swipe gesture
    _perform_swipe(driver, start_x, start_y, end_x, end_y)


def _calculate_swipe_coordinates(
    direction: ScrollDirection,
    center_x: int,
    center_y: int,
    distance: int,
    bbox: BboxTLBR,
) -> tuple[int, int, int, int]:
    """Calculate start and end coordinates for a swipe gesture.

    Args:
        direction: Direction to scroll.
        center_x: X coordinate of the element center.
        center_y: Y coordinate of the element center.
        distance: Distance to scroll in pixels.
        bbox: Bounding box to constrain the swipe within (BboxTLBR).

    Returns:
        Tuple of (start_x, start_y, end_x, end_y) coordinates.

    Raises:
        ValueError: If direction is not supported.
    """
    # Calculate width and height
    height = bbox.bottom - bbox.top
    width = bbox.right - bbox.left

    if direction == "down":
        # To scroll down (reveal content below), swipe UP (from bottom to top)
        start_x = center_x
        start_y = min(center_y + distance // 2, int(bbox.top + height - 10))
        end_x = center_x
        end_y = max(center_y - distance // 2, int(bbox.top + 10))

    elif direction == "up":
        # To scroll up (reveal content above), swipe DOWN (from top to bottom)
        start_x = center_x
        start_y = max(center_y - distance // 2, int(bbox.top + 10))
        end_x = center_x
        end_y = min(center_y + distance // 2, int(bbox.top + height - 10))

    elif direction == "right":
        # To scroll right (reveal content on right), swipe LEFT (from right to left)
        start_x = min(center_x + distance // 2, int(bbox.left + width - 10))
        start_y = center_y
        end_x = max(center_x - distance // 2, int(bbox.left + 10))
        end_y = center_y

    elif direction == "left":
        # To scroll left (reveal content on left), swipe RIGHT (from left to right)
        start_x = max(center_x - distance // 2, int(bbox.left + 10))
        start_y = center_y
        end_x = min(center_x + distance // 2, int(bbox.left + width - 10))
        end_y = center_y

    else:
        raise ValueError(f"Unsupported scroll direction: {direction}")

    return start_x, start_y, end_x, end_y


def _perform_swipe(
    driver: WebDriver,
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int = 300,
) -> None:
    """Perform a swipe gesture from start to end coordinates.

    Args:
        driver: Appium WebDriver instance.
        start_x: Starting X coordinate.
        start_y: Starting Y coordinate.
        end_x: Ending X coordinate.
        end_y: Ending Y coordinate.
        duration_ms: Duration of the swipe in milliseconds.
    """
    _LOGGER.debug(f"Performing swipe from ({start_x}, {start_y}) to ({end_x}, {end_y})")

    # Try platform-specific scroll methods first for better reliability
    platform = str(driver.capabilities.get("platformName", "")).lower()

    if "android" in platform:
        success = _try_android_scroll(driver, start_x, start_y, end_x, end_y)
        if success:
            return

    # Fallback to W3C Actions API
    _perform_swipe_with_actions(driver, start_x, start_y, end_x, end_y, duration_ms)


def _try_android_scroll(
    driver: WebDriver, start_x: int, start_y: int, end_x: int, end_y: int
) -> bool:
    """Try Android-specific scroll methods.

    Args:
        driver: Appium WebDriver instance.
        start_x: Starting X coordinate.
        start_y: Starting Y coordinate.
        end_x: Ending X coordinate.
        end_y: Ending Y coordinate.

    Returns:
        True if scroll succeeded, False if method not available.
    """
    try:
        # Try Appium's scroll method (most reliable for Android)
        driver.swipe(start_x, start_y, end_x, end_y, duration=300)
        _LOGGER.debug("Android swipe succeeded")
        return True
    except AttributeError:
        # swipe method not available, try mobile: gesture
        try:
            # Android UIAutomator2 mobile gesture
            direction = (
                "up"
                if end_y < start_y
                else (
                    "down"
                    if end_y > start_y
                    else "left"
                    if end_x < start_x
                    else "right"
                )
            )
            driver.execute_script(
                "mobile: swipeGesture",
                {
                    "left": min(start_x, end_x),
                    "top": min(start_y, end_y),
                    "width": max(abs(end_x - start_x), 100),
                    "height": max(abs(end_y - start_y), 100),
                    "direction": direction,
                    "percent": 0.75,
                },
            )
            _LOGGER.debug("Android swipeGesture succeeded")
            return True
        except Exception as e:
            _LOGGER.debug(f"Android scroll methods not available: {e}")
            return False
    except Exception as e:
        _LOGGER.debug(f"Android swipe failed: {e}")
        return False


def _perform_swipe_with_actions(
    driver: WebDriver,
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int = 300,
) -> None:
    """Perform swipe using W3C Actions API (fallback method).

    Args:
        driver: Appium WebDriver instance.
        start_x: Starting X coordinate.
        start_y: Starting Y coordinate.
        end_x: Ending X coordinate.
        end_y: Ending Y coordinate.
        duration_ms: Duration of the swipe in milliseconds.
    """
    _LOGGER.info(
        f"Using W3C Actions for swipe: ({start_x},{start_y}) → ({end_x},{end_y})"
    )

    from selenium.webdriver.common.actions import interaction

    finger_input = PointerInput(interaction.POINTER_TOUCH, "finger")  # type: ignore[no-untyped-call]
    actions = ActionBuilder(driver, mouse=finger_input)

    # Move to start position, press down, drag to end, release
    actions.pointer_action.move_to_location(start_x, start_y)  # type: ignore[no-untyped-call]
    actions.pointer_action.pointer_down()  # type: ignore[no-untyped-call]
    actions.pointer_action.pause(0.1)  # Small pause after press

    # Add intermediate points for smoother, more recognizable swipe
    steps = 5  # Fewer steps for more dramatic movement
    duration_per_step = (duration_ms / 1000.0) / steps

    for i in range(1, steps + 1):
        intermediate_x = start_x + (end_x - start_x) * i // steps
        intermediate_y = start_y + (end_y - start_y) * i // steps
        actions.pointer_action.pause(duration_per_step)
        actions.pointer_action.move_to_location(intermediate_x, intermediate_y)  # type: ignore[no-untyped-call]

    actions.pointer_action.pause(0.1)  # Small pause before release
    actions.pointer_action.pointer_up()  # type: ignore[no-untyped-call]

    # Execute the action
    actions.perform()
    _LOGGER.info("W3C Actions swipe completed")
