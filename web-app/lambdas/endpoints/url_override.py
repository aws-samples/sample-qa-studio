"""URL override utility for test suite execution."""
from urllib.parse import urlparse, urlunparse
from typing import Optional


def apply_base_url_override(original_url: str, base_url: Optional[str]) -> str:
    """
    Replace domain/origin while preserving path and query parameters.
    
    Implementation:
    1. Parse original URL into components
    2. Parse base URL into components
    3. Replace scheme and netloc from base URL
    4. Keep path, params, query, fragment from original
    5. Reconstruct URL
    
    Args:
        original_url: Original starting URL
        base_url: Override base URL (None = no override)
    
    Returns:
        Modified URL or original if base_url is None
    
    Examples:
        >>> apply_base_url_override(
        ...     "https://staging.example.com/login?foo=bar",
        ...     "https://prod.example.com"
        ... )
        "https://prod.example.com/login?foo=bar"
        
        >>> apply_base_url_override(
        ...     "http://localhost:3000/app/dashboard",
        ...     "https://example.com"
        ... )
        "https://example.com/app/dashboard"
        
        >>> apply_base_url_override(
        ...     "https://example.com/path",
        ...     None
        ... )
        "https://example.com/path"
    """
    if not base_url:
        return original_url
    
    parsed_original = urlparse(original_url)
    parsed_base = urlparse(base_url)
    
    # Replace scheme and netloc (domain), keep everything else
    return urlunparse((
        parsed_base.scheme,
        parsed_base.netloc,
        parsed_original.path,
        parsed_original.params,
        parsed_original.query,
        parsed_original.fragment
    ))
