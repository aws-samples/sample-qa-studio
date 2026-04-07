"""Client-side validation for QA Studio CLI."""

import re
from urllib.parse import urlparse


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
