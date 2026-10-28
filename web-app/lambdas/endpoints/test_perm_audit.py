"""
Tests for the permission audit logger (perm_audit.py).

Covers:
- log_permission_change emits correct structure
- log_denial emits correct structure
- Exception in logging does not raise
"""

import json
import os
import sys
import logging
import pytest
from unittest.mock import patch, MagicMock

# Ensure the endpoints directory is on the path
sys.path.insert(0, os.path.dirname(__file__))

from perm_audit import log_permission_change, log_denial


class TestLogPermissionChange:
    """Tests for permission change logging."""

    def test_emits_correct_structure(self, caplog):
        """Emits structured JSON with all required fields."""
        actor = {'sub': 'actor-sub', 'email': 'actor@example.com'}
        target = {'user_sub': 'target-sub'}
        details = {'old_role': 'viewer', 'new_role': 'editor'}

        with caplog.at_level(logging.INFO, logger='perm_audit'):
            log_permission_change(actor, 'role_change', target, details)

        assert len(caplog.records) == 1
        record = caplog.records[0]
        parsed = json.loads(record.message)

        assert parsed['event_type'] == 'permission_change'
        assert parsed['actor'] == actor
        assert parsed['action'] == 'role_change'
        assert parsed['target'] == target
        assert parsed['details'] == details
        assert 'timestamp' in parsed

    def test_timestamp_is_iso8601(self, caplog):
        """Timestamp follows ISO 8601 format."""
        with caplog.at_level(logging.INFO, logger='perm_audit'):
            log_permission_change({'sub': 'x'}, 'test', {}, {})

        parsed = json.loads(caplog.records[0].message)
        timestamp = parsed['timestamp']
        # Should match format like 2026-06-22T12:00:00Z
        assert timestamp.endswith('Z')
        assert 'T' in timestamp

    def test_never_raises_on_serialization_error(self):
        """Exception during JSON serialization does not propagate."""
        # Pass non-serializable object
        class BadObj:
            pass

        # Should NOT raise
        log_permission_change(BadObj(), 'test', {}, {})


class TestLogDenial:
    """Tests for access denial logging."""

    def test_emits_correct_structure(self, caplog):
        """Emits structured JSON with all required fields."""
        actor = {'sub': 'denied-sub', 'email': 'user@example.com'}

        with caplog.at_level(logging.WARNING, logger='perm_audit'):
            log_denial(actor, '/api/apps/123', 'Insufficient permissions')

        assert len(caplog.records) == 1
        record = caplog.records[0]
        parsed = json.loads(record.message)

        assert parsed['event_type'] == 'access_denied'
        assert parsed['actor'] == actor
        assert parsed['endpoint'] == '/api/apps/123'
        assert parsed['reason'] == 'Insufficient permissions'
        assert 'timestamp' in parsed

    def test_uses_warning_level(self, caplog):
        """Denial logs use WARNING level."""
        with caplog.at_level(logging.WARNING, logger='perm_audit'):
            log_denial({'sub': 'x'}, '/test', 'denied')

        assert caplog.records[0].levelname == 'WARNING'

    def test_never_raises_on_logger_error(self):
        """Exception in the logger itself does not propagate."""
        with patch('perm_audit.logger.warning', side_effect=RuntimeError("Logger broken")):
            # Should NOT raise
            log_denial({'sub': 'x'}, '/test', 'reason')

    def test_never_raises_on_serialization_error(self):
        """Non-serializable actor does not cause a raise."""
        class BadObj:
            pass

        # Should NOT raise
        log_denial(BadObj(), '/test', 'reason')
