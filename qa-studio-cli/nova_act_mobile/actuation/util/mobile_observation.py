"""Mobile observation utilities for screenshots and UI hierarchy extraction."""

import xml.etree.ElementTree as ET

from appium.webdriver.webdriver import WebDriver
from nova_act.types.api.step import BboxTLWH
from nova_act.util.logging import setup_logging

from nova_act_mobile.platform import Platform

_LOGGER = setup_logging(__name__)


def take_mobile_screenshot(driver: WebDriver) -> str:
    """Take a screenshot and return it as a base64-encoded data URL.

    Returns a JPEG data URL to avoid RGBA/JPEG incompatibility in downstream
    image processing (JPEG does not support alpha channel).

    Args:
        driver: Appium WebDriver instance.

    Returns:
        Base64-encoded JPEG screenshot with data URL prefix.

    Raises:
        ValueError: If screenshot cannot be captured.
    """
    import base64
    import io

    from PIL import Image

    try:
        screenshot_base64 = driver.get_screenshot_as_base64()
        png_bytes = base64.b64decode(screenshot_base64)
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        jpeg_buffer = io.BytesIO()
        img.save(jpeg_buffer, format="JPEG", quality=85)
        jpeg_base64 = base64.b64encode(jpeg_buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{jpeg_base64}"

    except Exception as e:
        _LOGGER.error(f"Failed to take screenshot: {e}")
        raise ValueError(f"Could not capture screenshot: {e}") from e


def get_ui_hierarchy(driver: WebDriver) -> str:
    """Get the UI hierarchy (page source) as XML.

    Args:
        driver: Appium WebDriver instance.

    Returns:
        XML string representing the UI hierarchy.

    Raises:
        ValueError: If UI hierarchy cannot be retrieved.
    """
    try:
        page_source = driver.page_source
        return page_source
    except Exception as e:
        _LOGGER.error(f"Failed to get UI hierarchy: {e}")
        raise ValueError(f"Could not retrieve UI hierarchy: {e}") from e


def parse_ui_hierarchy(
    xml_source: str, platform: Platform
) -> tuple[dict[int, BboxTLWH], str]:
    """Parse XML UI hierarchy into a simplified format with bounding boxes.

    Args:
        xml_source: XML string of the UI hierarchy.
        platform: Platform name (iOS or Android) for platform-specific parsing.

    Returns:
        Tuple of (id_to_bbox_map, simplified_dom) where:
        - id_to_bbox_map: Mapping of element IDs to bounding boxes
        - simplified_dom: Human-readable simplified DOM structure

    Raises:
        ValueError: If XML cannot be parsed.
    """
    try:
        root = ET.fromstring(xml_source)

        id_to_bbox_map: dict[int, BboxTLWH] = {}
        simplified_dom_lines: list[str] = []
        element_id = 0

        def parse_element(elem: ET.Element, depth: int = 0) -> None:
            """Recursively parse UI elements."""
            nonlocal element_id

            # Extract element information based on platform
            if platform == Platform.ANDROID:
                elem_type = elem.tag
                elem_name = elem.get("content-desc", "")
                elem_label = elem.get("text", "")
                elem_value = elem.get("resource-id", "")
                visible = elem.get("visible-to-user", "true") == "true"
                enabled = elem.get("enabled", "true") == "true"

                # Check clickable attribute - if not present, default to true for enabled elements
                # This allows interactive widgets without explicit clickable="true" to be included
                clickable_attr = elem.get("clickable")
                if clickable_attr is not None:
                    clickable = clickable_attr == "true"
                else:
                    # If clickable is not specified, assume it's clickable if enabled
                    clickable = enabled

                # Android bounds format: [x1,y1][x2,y2]
                bounds_str = elem.get("bounds", "")

            elif platform == Platform.IOS:
                elem_type = elem.get("type", "")
                elem_name = elem.get("name", "")
                elem_label = elem.get("label", "")
                elem_value = elem.get("value", "")
                visible = elem.get("visible", "true") == "true"
                enabled = elem.get("enabled", "true") == "true"

                # For iOS, filter out non-interactive container types
                # Common interactive types: Button, TextField, SecureTextField, SearchField, Switch, Slider, etc.
                # Common non-interactive containers: Application, Window, NavigationBar, TabBar, etc.
                non_interactive_types = {
                    "XCUIElementTypeApplication",
                    "XCUIElementTypeWindow",
                    "XCUIElementTypeOther",
                    "XCUIElementTypeScrollView",
                    "XCUIElementTypeNavigationBar",
                    "XCUIElementTypeTabBar",
                    "XCUIElementTypeToolbar",
                    "XCUIElementTypeStatusBar",
                }
                clickable = elem_type not in non_interactive_types

                # iOS bounds format: {{x,y},{w,h}}
                bounds_str = (
                    elem.get("x", "")
                    + ","
                    + elem.get("y", "")
                    + ","
                    + elem.get("width", "")
                    + ","
                    + elem.get("height", "")
                )

            # Parse bounding box
            bbox = _parse_bounds(bounds_str, platform)

            # Only include visible, interactive elements in the maps
            # For both platforms, check clickable and enabled
            is_interactive = clickable and enabled
            if (
                bbox
                and visible
                and is_interactive
                and (bbox["width"] > 0 and bbox["height"] > 0)
            ):
                current_id = element_id
                id_to_bbox_map[current_id] = bbox

                # Build simplified DOM representation
                indent = "  " * depth
                attributes = []

                if elem_type:
                    attributes.append(f"type={elem_type}")
                if elem_name:
                    attributes.append(f"name={elem_name[:30]}")
                if elem_label and elem_label != elem_name:
                    attributes.append(f"label={elem_label[:30]}")
                if elem_value and elem_value not in (elem_name, elem_label):
                    attributes.append(f"value={elem_value[:30]}")

                attr_str = " ".join(attributes) if attributes else "element"
                simplified_dom_lines.append(f"{indent}[{current_id}] {attr_str}")

                element_id += 1

            # Recursively parse children
            for child in elem:
                parse_element(child, depth + 1)

        # Start parsing from root
        parse_element(root)

        simplified_dom = "\n".join(simplified_dom_lines)
        return id_to_bbox_map, simplified_dom

    except ET.ParseError as e:
        _LOGGER.error(f"Failed to parse UI hierarchy XML: {e}")
        raise ValueError(f"Invalid UI hierarchy XML: {e}") from e
    except Exception as e:
        _LOGGER.error(f"Error parsing UI hierarchy: {e}")
        raise ValueError(f"Could not parse UI hierarchy: {e}") from e


def _parse_bounds(bounds_str: str, platform: Platform) -> BboxTLWH | None:
    """Parse bounds string into BboxTLWH format.

    Args:
        bounds_str: Bounds string in platform-specific format.
        platform: Platform type.

    Returns:
        BboxTLWH dictionary or None if bounds cannot be parsed.
    """
    try:
        if platform == Platform.ANDROID:
            # Android format: "[x1,y1][x2,y2]"
            if not bounds_str or "][" not in bounds_str:
                return None

            # Extract coordinates
            # First replace "]" with nothing, then "[" with nothing, keeping the comma separator
            bounds_str = bounds_str.replace("][", ",").replace("[", "").replace("]", "")
            coords = [int(x.strip()) for x in bounds_str.split(",")]

            if len(coords) != 4:
                return None

            x1, y1, x2, y2 = coords
            return {"y": y1, "x": x1, "width": x2 - x1, "height": y2 - y1}

        elif platform == Platform.IOS:
            # iOS format: "x,y,width,height"
            if not bounds_str or bounds_str.count(",") != 3:
                return None

            parts = bounds_str.split(",")
            x = int(parts[0])
            y = int(parts[1])
            width = int(parts[2])
            height = int(parts[3])

            return {"y": y, "x": x, "width": width, "height": height}

    except (ValueError, IndexError) as e:
        _LOGGER.debug(f"Could not parse bounds '{bounds_str}': {e}")
        return None


def get_screen_dimensions(driver: WebDriver) -> dict[str, int]:
    """Get the screen dimensions and scroll information.

    Args:
        driver: Appium WebDriver instance.

    Returns:
        Dictionary containing screen dimensions with keys:
        - scrollHeight: Total scrollable height
        - scrollWidth: Total scrollable width
        - scrollTop: Current vertical scroll position
        - scrollLeft: Current horizontal scroll position
        - windowHeight: Visible window height
        - windowWidth: Visible window width

    Raises:
        ValueError: If dimensions cannot be retrieved.
    """
    try:
        # Get window size
        window_size = driver.get_window_size()
        width = window_size["width"]
        height = window_size["height"]

        # For mobile apps, scroll dimensions typically match window dimensions
        # unless dealing with scrollable content
        return {
            "scrollHeight": height,
            "scrollWidth": width,
            "scrollTop": 0,
            "scrollLeft": 0,
            "windowHeight": height,
            "windowWidth": width,
        }

    except Exception as e:
        _LOGGER.error(f"Failed to get screen dimensions: {e}")
        raise ValueError(f"Could not retrieve screen dimensions: {e}") from e
