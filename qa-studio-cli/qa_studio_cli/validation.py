"""Client-side validation for QA Studio CLI."""

import json
import re
from urllib.parse import urlparse


VALID_BROWSER_ACTIONS = {"reload", "back", "forward", "navigate"}

VALID_TRANSFORM_OPERATIONS = {
    "math", "round", "floor", "ceil", "abs", "min", "max",
    "concat", "upper", "lower", "trim", "replace", "substring", "length",
    "to_number", "to_string", "to_int", "regex_extract", "format",
}


def validate_step(step: dict) -> tuple[bool, list[str]]:
    """Validate a step dict based on its step_type.

    Returns (is_valid, errors).  Only validates browser and transform
    step types; other step types are accepted without additional checks.
    """
    step_type = step.get("step_type", "")
    if step_type == "browser":
        return validate_browser_step(step)
    if step_type == "transform":
        return validate_transform_step(step)
    return True, []


def validate_browser_step(step: dict) -> tuple[bool, list[str]]:
    """Validate a browser step."""
    errors: list[str] = []
    action = step.get("browser_action")
    if not action:
        errors.append("browser_action is required for browser steps")
        return False, errors
    if action not in VALID_BROWSER_ACTIONS:
        errors.append(
            f"Invalid browser_action '{action}'. Must be one of: {', '.join(sorted(VALID_BROWSER_ACTIONS))}"
        )
    args_raw = step.get("browser_args")
    if args_raw:
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except (json.JSONDecodeError, TypeError):
            errors.append("browser_args must be valid JSON")
            return len(errors) == 0, errors
        if action == "navigate" and not args.get("url"):
            errors.append("browser_args.url is required for navigate action")
    elif action == "navigate":
        errors.append("browser_args with url is required for navigate action")
    return len(errors) == 0, errors


def validate_transform_step(step: dict) -> tuple[bool, list[str]]:
    """Validate a transform step."""
    errors: list[str] = []
    operation = step.get("transform_operation")
    if not operation:
        errors.append("transform_operation is required for transform steps")
        return False, errors
    if operation not in VALID_TRANSFORM_OPERATIONS:
        errors.append(
            f"Invalid transform_operation '{operation}'. Must be one of: {', '.join(sorted(VALID_TRANSFORM_OPERATIONS))}"
        )
    if not step.get("capture_variable"):
        errors.append("capture_variable is required for transform steps")
    args_raw = step.get("transform_args")
    if not args_raw:
        errors.append("transform_args is required for transform steps")
    else:
        try:
            json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except (json.JSONDecodeError, TypeError):
            errors.append("transform_args must be valid JSON")
    return len(errors) == 0, errors


def validate_journey_description(journey: str) -> tuple[bool, list[str]]:
    """
    Validate user journey description against API requirements.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    if not journey or not journey.strip():
        errors.append("User journey description is required")
        return False, errors
    
    journey = journey.strip()
    
    # Length validation
    if len(journey) < 50:
        errors.append(f"User journey must be at least 50 characters (currently {len(journey)})")
    
    if len(journey) > 2000:
        errors.append(f"User journey must be 2000 characters or less (currently {len(journey)})")
    
    # Word count validation
    words = journey.split()
    if len(words) < 10:
        errors.append(f"User journey should contain at least 10 words (currently {len(words)})")
    
    return len(errors) == 0, errors


def validate_url(url: str) -> tuple[bool, list[str]]:
    """
    Validate starting URL.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    if not url or not url.strip():
        errors.append("Starting URL is required")
        return False, errors
    
    url = url.strip()
    
    try:
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            errors.append("Invalid URL format. Must include protocol (http:// or https://)")
    except Exception:
        errors.append("Invalid URL format")
    
    return len(errors) == 0, errors


def validate_title(title: str) -> tuple[bool, list[str]]:
    """
    Validate test title.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    if not title or not title.strip():
        errors.append("Title is required")
        return False, errors
    
    title = title.strip()
    
    if len(title) < 3:
        errors.append(f"Title must be at least 3 characters (currently {len(title)})")
    
    if len(title) > 100:
        errors.append(f"Title must be 100 characters or less (currently {len(title)})")
    
    return len(errors) == 0, errors


VALID_REGIONS = ['us-east-1', 'us-west-2', 'ap-southeast-2', 'eu-central-1']


def validate_region(region: str) -> tuple[bool, list[str]]:
    """
    Validate AWS region.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    if not region or not region.strip():
        errors.append("Region is required")
        return False, errors
    
    if region not in VALID_REGIONS:
        errors.append(f"Invalid region. Must be one of: {', '.join(VALID_REGIONS)}")
    
    return len(errors) == 0, errors
