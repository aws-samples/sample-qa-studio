"""
Permission audit logger (C-9).

Emits structured JSON logs for permission changes and access denials.
Designed for CloudWatch Logs Insights querying.

CRITICAL: This module NEVER raises exceptions. A logging failure must not
break the request. Both functions are wrapped in try/except with pass.
"""

import logging
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def log_permission_change(actor: dict, action: str, target: dict, details: dict) -> None:
    """
    Log a permission change event (role assignment, access grant, etc.).

    Emits structured JSON via logger.info for CloudWatch Logs Insights.

    Args:
        actor: Dict with actor info (e.g. {'sub': '...', 'email': '...'}).
        action: Action type (e.g. 'role_change', 'team_create', 'grant_access').
        target: Dict with target info (e.g. {'user_sub': '...'} or {'team_id': '...'}).
        details: Action-specific context dict.

    Returns:
        None. Never raises.
    """
    try:
        logger.info(json.dumps({
            'event_type': 'permission_change',
            'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'actor': actor,
            'action': action,
            'target': target,
            'details': details,
        }))
    except Exception:
        pass  # Never fatal


def log_denial(actor: dict, endpoint: str, reason: str) -> None:
    """
    Log an access denial event (403 response).

    Emits structured JSON via logger.warning for CloudWatch Logs Insights.

    Args:
        actor: Dict with actor info (e.g. {'sub': '...', 'email': '...'}).
        endpoint: The endpoint path that was denied.
        reason: Human-readable denial reason.

    Returns:
        None. Never raises.
    """
    try:
        logger.warning(json.dumps({
            'event_type': 'access_denied',
            'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'actor': actor,
            'endpoint': endpoint,
            'reason': reason,
        }))
    except Exception:
        pass  # Never fatal
