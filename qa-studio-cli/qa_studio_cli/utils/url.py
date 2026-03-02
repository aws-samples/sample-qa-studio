"""URL override utilities for base URL replacement."""

from urllib.parse import urlparse, urlunparse


def apply_base_url_override(original_url: str, base_url: str) -> str:
    """Replace the origin of original_url with base_url, preserving path and query.

    Example:
        apply_base_url_override(
            "https://staging.example.com/login?foo=bar",
            "http://localhost:3000"
        ) -> "http://localhost:3000/login?foo=bar"
    """
    original = urlparse(original_url)
    override = urlparse(base_url)
    return urlunparse((
        override.scheme,
        override.netloc,
        original.path,
        original.params,
        original.query,
        original.fragment,
    ))
