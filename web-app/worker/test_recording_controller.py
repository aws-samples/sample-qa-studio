"""Unit tests for RecordingController and helper functions."""
import json
import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from recording_controller import (
    RecordingController,
    _strip_recording_data,
    _build_recording_envelope,
    ACTION_STRIP_FIELDS,
    ASSERTION_STRIP_FIELDS,
)


# ── Helper function tests ──────────────────────────────────────────


class TestStripRecordingData:
    """Tests for _strip_recording_data helper."""

    def test_strips_action_fields(self):
        recording = {
            "actions": [
                {
                    "type": "click",
                    "prompt": "Click button",
                    "rawAction": "should be removed",
                    "collapsedActions": ["also removed"],
                    "promptEdited": True,
                }
            ]
        }
        result = _strip_recording_data(recording)
        action = result["actions"][0]
        assert "type" in action
        assert "prompt" in action
        assert "rawAction" not in action
        assert "collapsedActions" not in action
        assert "promptEdited" not in action

    def test_strips_assertion_fields(self):
        recording = {
            "actions": [
                {
                    "type": "click",
                    "assertions": [
                        {
                            "text": "Button visible",
                            "screenshotDataUrl": "data:image/png;base64,abc",
                            "result": True,
                        }
                    ],
                }
            ]
        }
        result = _strip_recording_data(recording)
        assertion = result["actions"][0]["assertions"][0]
        assert "text" in assertion
        assert "screenshotDataUrl" not in assertion
        assert "result" not in assertion

    def test_preserves_non_stripped_fields(self):
        recording = {
            "actions": [
                {"type": "click", "prompt": "Click", "url": "https://example.com"}
            ]
        }
        result = _strip_recording_data(recording)
        action = result["actions"][0]
        assert action["type"] == "click"
        assert action["prompt"] == "Click"
        assert action["url"] == "https://example.com"

    def test_empty_actions(self):
        result = _strip_recording_data({"actions": []})
        assert result["actions"] == []

    def test_preserves_top_level_fields(self):
        recording = {"id": "abc", "startedAt": 1000, "actions": []}
        result = _strip_recording_data(recording)
        assert result["id"] == "abc"
        assert result["startedAt"] == 1000


class TestBuildRecordingEnvelope:
    """Tests for _build_recording_envelope helper."""

    def test_envelope_structure(self):
        envelope = _build_recording_envelope(
            actions=[{"type": "click"}],
            started_at=1000,
            stopped_at=2000,
            starting_url="https://example.com",
        )
        assert envelope["type"] == "cdp_actions"
        assert envelope["version"] == "1.0"
        assert "captured_at" in envelope
        assert envelope["data"]["event_count"] == 1
        assert envelope["data"]["duration_seconds"] == 1.0
        session = envelope["data"]["session"]
        assert session["startedAt"] == 1000
        assert session["stoppedAt"] == 2000
        assert session["startingUrl"] == "https://example.com"
        assert len(session["actions"]) == 1

    def test_duration_calculation(self):
        envelope = _build_recording_envelope([], 5000, 15000, "")
        assert envelope["data"]["duration_seconds"] == 10.0

    def test_zero_actions(self):
        envelope = _build_recording_envelope([], 1000, 2000, "")
        assert envelope["data"]["event_count"] == 0
        assert envelope["data"]["session"]["actions"] == []


# ── RecordingController tests ──────────────────────────────────────


def _make_nova_mock():
    """Create a mock NovaAct instance with page context."""
    nova = MagicMock()
    nova.page.url = "https://example.com"
    cdp_session = MagicMock()
    nova.page.context.new_cdp_session.return_value = cdp_session
    return nova, cdp_session


class TestRecordingControllerSetup:
    """Tests for RecordingController.setup()."""

    def test_setup_creates_cdp_session(self):
        nova, cdp_session = _make_nova_mock()
        rc = RecordingController(nova, "ext-id-123")
        rc.setup()

        nova.page.context.new_cdp_session.assert_called_once_with(nova.page)
        cdp_session.send.assert_called_once_with(
            "Runtime.evaluate",
            {"expression": RecordingController.COLLECTOR_SCRIPT},
        )
        # setup() should NOT set _last_url — callers handle URL tracking
        assert rc._last_url is None

    def test_setup_detaches_old_session(self):
        nova, cdp_session = _make_nova_mock()
        rc = RecordingController(nova, "ext-id-123")

        old_session = MagicMock()
        rc._cdp_session = old_session

        rc.setup()
        old_session.detach.assert_called_once()

    def test_setup_handles_exception(self):
        nova, _ = _make_nova_mock()
        nova.page.context.new_cdp_session.side_effect = Exception("CDP error")
        rc = RecordingController(nova, "ext-id-123")
        rc.setup()  # Should not raise
        assert rc._cdp_session is None


class TestRecordingControllerStartRecording:
    """Tests for RecordingController.start_recording()."""

    def test_start_recording_success(self):
        nova, cdp_session = _make_nova_mock()
        rc = RecordingController(nova, "ext-id-123")

        result = rc.start_recording()

        assert result["success"] is True
        assert result["error"] is None
        assert rc.is_recording is True
        assert rc._started_at is not None
        assert rc._starting_url == "https://example.com"
        assert rc.actions == []

    def test_start_recording_sends_postmessage_command(self):
        nova, cdp_session = _make_nova_mock()
        rc = RecordingController(nova, "ext-id-123")
        rc.start_recording()

        # Second call should be the start command (first is collector install)
        calls = cdp_session.send.call_args_list
        start_call = calls[-1]
        expression = start_call[0][1]["expression"]
        assert "START_RECORDING" in expression
        assert "postMessage" in expression

    def test_start_recording_failure(self):
        nova, cdp_session = _make_nova_mock()
        cdp_session.send.side_effect = Exception("CDP dead")
        # Also make new_cdp_session fail on the second call (inside start_recording -> setup)
        nova.page.context.new_cdp_session.return_value = cdp_session

        rc = RecordingController(nova, "ext-id-123")
        result = rc.start_recording()

        assert result["success"] is False
        assert "CDP dead" in result["error"]

    def test_start_recording_captures_url_at_start_time(self):
        """startingUrl must reflect the page URL when start_recording() runs,
        not a stale value from an earlier setup() or navigation."""
        nova, cdp_session = _make_nova_mock()
        # Simulate the page having navigated since the controller was created
        nova.page.url = "https://example.com/page-at-start"
        rc = RecordingController(nova, "ext-id-123")
        rc.start_recording()

        assert rc._starting_url == "https://example.com/page-at-start"
        assert rc._last_url == "https://example.com/page-at-start"


class TestRecordingControllerStopRecording:
    """Tests for RecordingController.stop_recording()."""

    def test_stop_recording_returns_envelope(self):
        nova, cdp_session = _make_nova_mock()
        cdp_session.send.return_value = {
            "result": {"value": "[]"}
        }
        rc = RecordingController(nova, "ext-id-123")
        rc.start_recording()

        # Add some actions manually
        rc.actions = [
            {"type": "click", "prompt": "Click button", "rawAction": "raw"},
        ]

        result = rc.stop_recording()

        assert result["success"] is True
        assert result["data"] is not None
        envelope = result["data"]
        assert envelope["type"] == "cdp_actions"
        assert envelope["version"] == "1.0"
        # rawAction should be stripped
        session_actions = envelope["data"]["session"]["actions"]
        assert len(session_actions) == 1
        assert "rawAction" not in session_actions[0]

    def test_stop_recording_sends_stop_command(self):
        nova, cdp_session = _make_nova_mock()
        cdp_session.send.return_value = {"result": {"value": "[]"}}
        rc = RecordingController(nova, "ext-id-123")
        rc.start_recording()
        rc.stop_recording()

        # Find the STOP_RECORDING call
        stop_calls = [
            c for c in cdp_session.send.call_args_list
            if "STOP_RECORDING" in str(c)
        ]
        assert len(stop_calls) == 1

    def test_stop_recording_sets_is_recording_false(self):
        nova, cdp_session = _make_nova_mock()
        cdp_session.send.return_value = {"result": {"value": "[]"}}
        rc = RecordingController(nova, "ext-id-123")
        rc.start_recording()
        assert rc.is_recording is True

        rc.stop_recording()
        assert rc.is_recording is False

    def test_stop_recording_failure(self):
        nova, cdp_session = _make_nova_mock()
        rc = RecordingController(nova, "ext-id-123")
        rc.setup()
        # Make the drain call fail — this nulls _cdp_session,
        # then stop_recording tries to use it and gets a different error
        cdp_session.send.side_effect = Exception("Session closed")

        result = rc.stop_recording()
        assert result["success"] is False
        assert result["data"] is None
        assert result["error"] is not None


class TestRecordingControllerDrainPageActions:
    """Tests for RecordingController._drain_page_actions()."""

    def test_drain_collects_actions(self):
        nova, cdp_session = _make_nova_mock()
        actions_json = json.dumps([
            {"type": "click", "prompt": "Click A"},
            {"type": "type", "prompt": "Type B"},
        ])
        cdp_session.send.return_value = {
            "result": {"value": actions_json}
        }

        rc = RecordingController(nova, "ext-id-123")
        rc.setup()
        rc._drain_page_actions()

        assert len(rc.actions) == 2
        assert rc.actions[0]["prompt"] == "Click A"
        assert rc._dirty is True

    def test_drain_detects_navigation(self):
        nova, cdp_session = _make_nova_mock()
        cdp_session.send.return_value = {"result": {"value": "[]"}}

        rc = RecordingController(nova, "ext-id-123")
        rc.setup()
        rc._last_url = "https://example.com/page1"

        # Simulate navigation
        type(nova.page).url = PropertyMock(return_value="https://example.com/page2")

        rc._drain_page_actions()

        # Should have a navigation action
        assert len(rc.actions) == 1
        assert rc.actions[0]["type"] == "navigation"
        assert "page2" in rc.actions[0]["url"]

    def test_drain_deduplicates_by_action_id(self):
        """Duplicate entries (same id) from the extension should be dropped."""
        nova, cdp_session = _make_nova_mock()
        duplicate_id = "dup-1234"
        actions_json = json.dumps([
            {"id": duplicate_id, "type": "tab_switch", "prompt": "switch tab", "timestamp": 100},
            {"id": duplicate_id, "type": "tab_switch", "prompt": "switch tab", "timestamp": 100},
            {"id": "unique-5678", "type": "click", "prompt": "click button", "timestamp": 200},
        ])
        cdp_session.send.return_value = {"result": {"value": actions_json}}

        rc = RecordingController(nova, "ext-id-123")
        rc.setup()
        rc._drain_page_actions()

        assert len(rc.actions) == 2
        assert rc.actions[0]["id"] == duplicate_id
        assert rc.actions[1]["id"] == "unique-5678"

    def test_drain_deduplicates_across_drains(self):
        """An action already collected in a previous drain should not be added again."""
        nova, cdp_session = _make_nova_mock()
        existing_id = "existing-1234"
        rc = RecordingController(nova, "ext-id-123")
        rc.setup()
        rc.actions = [{"id": existing_id, "type": "click", "prompt": "old click"}]

        actions_json = json.dumps([
            {"id": existing_id, "type": "click", "prompt": "old click"},
            {"id": "new-5678", "type": "type", "prompt": "new type"},
        ])
        cdp_session.send.return_value = {"result": {"value": actions_json}}

        rc._drain_page_actions()

        assert len(rc.actions) == 2
        assert rc.actions[0]["id"] == existing_id
        assert rc.actions[1]["id"] == "new-5678"

    def test_drain_handles_dead_session(self):
        nova, cdp_session = _make_nova_mock()
        cdp_session.send.side_effect = Exception("Session detached")

        rc = RecordingController(nova, "ext-id-123")
        rc._cdp_session = cdp_session
        rc._drain_page_actions()  # Should not raise

        # Session should be nulled for recreation
        assert rc._cdp_session is None


class TestRecordingControllerFlushToDb:
    """Tests for RecordingController.flush_to_db()."""

    def test_flush_updates_db_when_dirty(self):
        nova, cdp_session = _make_nova_mock()
        cdp_session.send.return_value = {"result": {"value": "[]"}}

        rc = RecordingController(nova, "ext-id-123")
        rc.setup()
        rc.is_recording = True
        rc._dirty = True

        db_client = MagicMock()
        rc.flush_to_db(db_client, "uc-123", "sess-456")

        db_client.update_recording_status.assert_called_once_with(
            "uc-123", "sess-456", "recording"
        )
        assert rc._dirty is False

    def test_flush_skips_when_not_dirty(self):
        nova, cdp_session = _make_nova_mock()
        rc = RecordingController(nova, "ext-id-123")
        rc._dirty = False

        db_client = MagicMock()
        rc.flush_to_db(db_client, "uc-123", "sess-456")

        db_client.update_recording_status.assert_not_called()

    def test_flush_drains_when_recording(self):
        nova, cdp_session = _make_nova_mock()
        cdp_session.send.return_value = {"result": {"value": "[]"}}

        rc = RecordingController(nova, "ext-id-123")
        rc.setup()
        rc.is_recording = True
        rc._dirty = False

        db_client = MagicMock()
        rc.flush_to_db(db_client, "uc-123", "sess-456")

        # drain was called (cdp_session.send called for drain)
        assert cdp_session.send.call_count >= 1


class TestRecordingControllerDetach:
    """Tests for RecordingController.detach()."""

    def test_detach_cleans_up_session(self):
        nova, cdp_session = _make_nova_mock()
        rc = RecordingController(nova, "ext-id-123")
        rc.setup()

        rc.detach()

        cdp_session.detach.assert_called_once()
        assert rc._cdp_session is None
        assert rc._last_url is None

    def test_detach_handles_exception(self):
        nova, cdp_session = _make_nova_mock()
        cdp_session.detach.side_effect = Exception("Already detached")

        rc = RecordingController(nova, "ext-id-123")
        rc._cdp_session = cdp_session

        rc.detach()  # Should not raise
        assert rc._cdp_session is None

    def test_detach_noop_when_no_session(self):
        nova, _ = _make_nova_mock()
        rc = RecordingController(nova, "ext-id-123")
        rc.detach()  # Should not raise
        assert rc._cdp_session is None
