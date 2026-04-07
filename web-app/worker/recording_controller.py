"""
Recording Controller - Manages recording lifecycle via CDP communication with the
NovaActRecorder Chrome extension.

Collects actions via a page-level JS snippet that accumulates postMessages into
window.__novaActions, drained periodically via Runtime.evaluate. Navigation is
tracked Python-side by comparing page.url between drains.

Fields stripped from each action for compact storage:
  - actions[].rawAction, collapsedActions, promptEdited
  - actions[].assertions[].screenshotDataUrl, result
"""

import json
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Fields to strip from each action entry
ACTION_STRIP_FIELDS = {"rawAction", "collapsedActions", "promptEdited"}

# Fields to strip from each assertion within an action
ASSERTION_STRIP_FIELDS = {"screenshotDataUrl", "result"}


def _strip_recording_data(recording: dict) -> dict:
    """Strip non-essential fields from the recording session data.

    Removes large/redundant fields that are only needed for the extension's
    own replay/UI features, not for use case generation.

    Args:
        recording: Raw RecordingSession dict from the extension.

    Returns:
        Cleaned RecordingSession dict with stripped fields removed.
    """
    actions = recording.get("actions", [])
    stripped_actions = []

    for action in actions:
        stripped_action = {
            k: v for k, v in action.items() if k not in ACTION_STRIP_FIELDS
        }

        # Strip assertion fields
        if "assertions" in stripped_action:
            stripped_action["assertions"] = [
                {k: v for k, v in assertion.items() if k not in ASSERTION_STRIP_FIELDS}
                for assertion in stripped_action["assertions"]
            ]

        stripped_actions.append(stripped_action)

    return {**recording, "actions": stripped_actions}


def _build_recording_envelope(actions: list, started_at: int, stopped_at: int, starting_url: str) -> dict:
    """Build a RecordingData envelope from collected actions.

    Args:
        actions: List of stripped action dicts.
        started_at: Recording start timestamp (ms since epoch).
        stopped_at: Recording stop timestamp (ms since epoch).
        starting_url: URL where recording started.

    Returns:
        RecordingData envelope dict ready for JSON serialization.
    """
    import uuid
    duration_seconds = round((stopped_at - started_at) / 1000.0, 2) if started_at and stopped_at else None

    session = {
        "id": str(uuid.uuid4()),
        "startedAt": started_at,
        "stoppedAt": stopped_at,
        "tabId": 0,  # Not available via CDP drain
        "startingUrl": starting_url,
        "actions": actions,
    }

    return {
        "type": "cdp_actions",
        "version": "1.0",
        "data": {
            "session": session,
            "event_count": len(actions),
            "duration_seconds": duration_seconds,
        },
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


class RecordingController:
    """Recording controller using a page-level action collector with fast polling.

    Installs a JS collector on the page that accumulates NOVA_RECORDER_ACTION
    postMessages into window.__novaActions. The worker drains this array
    periodically via a simple Runtime.evaluate — no postMessage round-trip.

    Navigation is tracked Python-side by comparing page.url between drains
    (JS-side tracking fails because window globals reset on navigation).
    """

    # Collector script: idempotent, listens for NOVA_RECORDER_ENTRY and NOVA_RECORDER_SCREENSHOT.
    COLLECTOR_SCRIPT = (
        "if(!window.__novaActions)window.__novaActions=[];"
        "if(!window.__novaScreenshots)window.__novaScreenshots={};"
        "if(!window.__novaListenerAttached){"
        "window.__novaListenerAttached=true;"
        "window.addEventListener('message',function(e){"
        "if(e.data&&e.data.type==='NOVA_RECORDER_ENTRY')"
        "window.__novaActions.push(e.data.entry);"
        "if(e.data&&e.data.type==='NOVA_RECORDER_SCREENSHOT')"
        "window.__novaScreenshots[e.data.actionId]=e.data.dataUrl;"
        "});"
        "}"
    )

    def __init__(self, nova, extension_id: str):
        """Initialize the recording controller.

        Args:
            nova: NovaAct instance with an active browser session.
            extension_id: Chrome extension ID for the NovaActRecorder extension.
        """
        self.nova = nova
        self.extension_id = extension_id
        self.actions = []
        self.screenshots = {}
        self.is_recording = False
        self._cdp_session = None
        self._dirty = False
        self._last_url = None
        self._started_at = None
        self._starting_url = None

    def setup(self):
        """Create a fresh CDP session and install the collector.

        Does NOT update _last_url or _starting_url — callers handle that.
        """
        self.detach()
        try:
            self._cdp_session = self.nova.page.context.new_cdp_session(self.nova.page)
            self._cdp_session.send("Runtime.evaluate", {
                "expression": self.COLLECTOR_SCRIPT
            })
            logger.info(f"Recording collector installed on {self.nova.page.url}")
        except Exception as e:
            logger.error(f"Failed to set up recording collector: {e}")

    def _drain_page_actions(self):
        """Re-install collector, drain actions, then check for navigation.

        Navigation check comes AFTER draining so that a click that triggers
        navigation appears before the 'Navigate to ...' entry.
        """
        if not self._cdp_session:
            return
        try:
            # Re-install collector (idempotent) + drain in one round-trip
            result = self._cdp_session.send("Runtime.evaluate", {
                "expression": (
                    self.COLLECTOR_SCRIPT +
                    "var __r=JSON.stringify(window.__novaActions||[]);"
                    "window.__novaActions=[];__r;"
                ),
                "returnByValue": True
            })
            value = result.get("result", {}).get("value", "[]")
            new_actions = json.loads(value) if value else []
            tab_switched = False
            if new_actions:
                # Deduplicate by action id
                seen_ids = {a.get("id") for a in self.actions if a.get("id")}
                unique_actions = []
                for action in new_actions:
                    aid = action.get("id")
                    if aid and aid in seen_ids:
                        continue
                    if aid:
                        seen_ids.add(aid)
                    unique_actions.append(action)
                if len(unique_actions) < len(new_actions):
                    logger.info(f"Deduplicated {len(new_actions) - len(unique_actions)} duplicate actions")
                new_actions = unique_actions

            if new_actions:
                self.actions.extend(new_actions)
                self._dirty = True
                logger.info(f"Drained {len(new_actions)} actions from page (total: {len(self.actions)})")
                # Track tab switches so we follow the active tab
                for action in new_actions:
                    if action.get("type") == "tab_switch" and action.get("url"):
                        self._last_url = action["url"]
                        tab_switched = True
                        logger.info(f"Tab switch detected, now tracking: {self._last_url}")

            # Drain screenshots separately to avoid huge single evaluations
            try:
                ss_result = self._cdp_session.send("Runtime.evaluate", {
                    "expression": (
                        "var __ss=JSON.stringify(window.__novaScreenshots||{});"
                        "window.__novaScreenshots={};"
                        "__ss;"
                    ),
                    "returnByValue": True
                })
                ss_value = ss_result.get("result", {}).get("value", "{}")
                new_screenshots = json.loads(ss_value) if ss_value else {}
                if new_screenshots:
                    self.screenshots.update(new_screenshots)
                    logger.info(f"Drained {len(new_screenshots)} screenshots (total: {len(self.screenshots)})")
            except Exception as ss_err:
                logger.warning(f"Error draining screenshots: {ss_err}")

            # Check for navigation after draining; skip if tab switch just occurred
            try:
                current_url = self.nova.page.url
                if not tab_switched and self._last_url and current_url != self._last_url:
                    logger.info(f"Navigation detected: {self._last_url} -> {current_url}")
                    self.actions.append({
                        "type": "navigation",
                        "prompt": f"Navigate to {current_url}",
                        "url": current_url,
                        "timestamp": int(time.time() * 1000),
                        "isIntent": False,
                        "assertions": [],
                        "id": str(__import__("uuid").uuid4()),
                    })
                    self._last_url = current_url
                    self._dirty = True
            except Exception as nav_err:
                logger.warning(f"Error checking URL: {nav_err}")
        except Exception as e:
            logger.warning(f"Error draining page actions: {e}")
            # Session might be dead — null it so setup() recreates
            self._cdp_session = None

    def _get_active_page(self):
        """Find the page matching _last_url, falls back to nova.page."""
        try:
            pages = self.nova.page.context.pages
            if self._last_url:
                for page in pages:
                    try:
                        if page.url == self._last_url:
                            return page
                    except Exception:
                        continue
        except Exception:
            pass
        return self.nova.page

    def start_recording(self) -> dict:
        """Send START_RECORDING command to extension and begin collecting actions.

        Returns:
            dict with keys:
                - success (bool): Whether recording started successfully.
                - error (str | None): Error message if start failed.
        """
        try:
            # Always recreate session on start (avoids stale session after stop/navigation)
            self.setup()
            # Capture URL before postMessage to avoid race with navigation
            current_url = self.nova.page.url
            self._cdp_session.send("Runtime.evaluate", {
                "expression": (
                    "window.__novaActions=[];"
                    "window.postMessage({type:'NOVA_RECORDER_CMD',command:'START_RECORDING',payload:{}}, '*');"
                )
            })
            self.is_recording = True
            self._started_at = int(time.time() * 1000)
            self._starting_url = current_url
            self._last_url = current_url
            self.actions = []
            self.screenshots = {}
            self._dirty = True
            logger.info(f"Recording started via CDP bridge (starting at {self._last_url})")
            return {"success": True, "error": None}
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return {"success": False, "error": str(e)}

    def stop_recording(self) -> dict:
        """Send STOP_RECORDING command and build the recording data envelope.

        Drains remaining actions before stopping, then builds the RecordingData
        envelope with all collected actions.

        Returns:
            dict with keys:
                - success (bool): Whether recording stopped and data was built.
                - data (dict | None): RecordingData envelope dict, or None on failure.
                - error (str | None): Error message if stop failed.
        """
        try:
            if not self._cdp_session:
                self.setup()

            # Drain remaining actions before stopping
            self._drain_page_actions()

            # Send stop command and await extension acknowledgement
            self._cdp_session.send("Runtime.evaluate", {
                "expression": (
                    "new Promise((resolve) => {"
                    "  const timeout = setTimeout(() => {"
                    "    window.removeEventListener('message', handler);"
                    "    resolve({done: true, timedOut: true});"
                    "  }, 15000);"
                    "  function handler(e) {"
                    "    if (e.data && e.data.type === 'NOVA_RECORDER_RESPONSE'"
                    "        && e.data.command === 'STOP_RECORDING') {"
                    "      window.removeEventListener('message', handler);"
                    "      clearTimeout(timeout);"
                    "      resolve({done: true, timedOut: false});"
                    "    }"
                    "  }"
                    "  window.addEventListener('message', handler);"
                    "  window.postMessage({type:'NOVA_RECORDER_CMD',command:'STOP_RECORDING',payload:{}}, '*');"
                    "})"
                ),
                "awaitPromise": True,
                "returnByValue": True
            })
            logger.info("Extension STOP_RECORDING completed")

            self.is_recording = False
            stopped_at = int(time.time() * 1000)

            # Strip non-essential fields from collected actions
            stripped_actions = []
            for action in self.actions:
                stripped = {k: v for k, v in action.items() if k not in ACTION_STRIP_FIELDS}
                if "assertions" in stripped:
                    stripped["assertions"] = [
                        {k: v for k, v in a.items() if k not in ASSERTION_STRIP_FIELDS}
                        for a in stripped["assertions"]
                    ]
                stripped_actions.append(stripped)

            # Build the RecordingData envelope
            envelope = _build_recording_envelope(
                actions=stripped_actions,
                started_at=self._started_at or (stopped_at - 1000),
                stopped_at=stopped_at,
                starting_url=self._starting_url or "",
            )

            action_count = len(stripped_actions)
            logger.info(f"Recording stopped via CDP bridge, {action_count} actions captured")

            return {"success": True, "data": envelope, "screenshots": self.screenshots, "error": None}

        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            return {"success": False, "data": None, "screenshots": {}, "error": str(e)}

    def flush_to_db(self, db_client, usecase_id: str, session_id: str):
        """Drain page actions and update recording status in DynamoDB if dirty.

        Called from the command loop on each iteration to keep DDB in sync.
        """
        if self.is_recording:
            self._drain_page_actions()
        if not self._dirty:
            return
        try:
            db_client.update_recording_status(usecase_id, session_id, "recording")
            self._dirty = False
        except Exception as e:
            logger.error(f"Error flushing recording status to DB: {e}")

    def detach(self):
        """Clean up CDP session."""
        if self._cdp_session:
            try:
                self._cdp_session.detach()
            except Exception:
                pass
            self._cdp_session = None
        self._last_url = None
