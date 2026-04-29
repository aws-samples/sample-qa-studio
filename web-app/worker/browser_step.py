"""Browser step executor for the worker."""

import ipaddress
import json
import logging
from urllib.parse import urlparse

from models import ExecutionStep

logger = logging.getLogger(__name__)

# IP ranges that must never be navigated to from the worker
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),      # link-local / ECS metadata
    ipaddress.ip_network("10.0.0.0/8"),           # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),        # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),       # RFC 1918
    ipaddress.ip_network("127.0.0.0/8"),          # loopback
    ipaddress.ip_network("fd00::/8"),             # IPv6 ULA
    ipaddress.ip_network("::1/128"),              # IPv6 loopback
    ipaddress.ip_network("fe80::/10"),            # IPv6 link-local
]


def _validate_navigate_url(url: str) -> str | None:
    """Validate a navigation URL. Returns an error message or None if valid."""
    try:
        parsed = urlparse(url)
    except Exception:
        return f"Invalid URL: {url}"
    if parsed.scheme not in ("http", "https"):
        return f"URL scheme must be http or https, got '{parsed.scheme}'"
    hostname = parsed.hostname or ""
    if not hostname:
        return "URL must include a hostname"
    try:
        addr = ipaddress.ip_address(hostname)
        for network in _BLOCKED_NETWORKS:
            if addr in network:
                return f"Navigation to {hostname} is blocked (internal/metadata address)"
    except ValueError:
        pass  # hostname is a DNS name, not an IP — allowed
    return None


def execute_browser_step(nova, step: ExecutionStep):
    """Execute a browser step (reload, back, forward, navigate).

    Returns:
        (result, success, logs) — same shape as url_step / navigation_step.
    """
    action = step.browser_action
    if not action:
        return None, False, "browser_action is required"

    args = _parse_args(step.browser_args)

    try:
        page = nova.page
        match action:
            case "reload":
                return _do_reload(page, args)
            case "back":
                return _do_back(page)
            case "forward":
                return _do_forward(page)
            case "navigate":
                return _do_navigate(nova, args)
            case _:
                return None, False, f"Unknown browser_action: '{action}'"
    except Exception as exc:
        logger.error(f"Browser step '{action}' failed: {exc}")
        return None, False, str(exc)


def _parse_args(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return {}


def _do_reload(page, args: dict):
    hard = args.get("hard", False)
    if hard:
        page.evaluate("() => location.reload()")
    else:
        page.reload()
    logger.info(f"Browser reload (hard={hard}) completed")
    return None, True, ""


def _do_back(page):
    url_before = page.url
    response = page.go_back()
    if response is None and page.url == url_before:
        return None, False, "Browser back failed: no previous history entry"
    logger.info(f"Browser back: {url_before} -> {page.url}")
    return None, True, ""


def _do_forward(page):
    url_before = page.url
    response = page.go_forward()
    if response is None and page.url == url_before:
        return None, False, "Browser forward failed: no forward history entry"
    logger.info(f"Browser forward: {url_before} -> {page.url}")
    return None, True, ""


def _do_navigate(nova, args: dict):
    url = args.get("url", "")
    if not url:
        return None, False, "browser_args.url is required for navigate action"
    error = _validate_navigate_url(url)
    if error:
        return None, False, error
    nova.go_to_url(url)
    logger.info(f"Browser navigate to: {url}")
    return None, True, ""
