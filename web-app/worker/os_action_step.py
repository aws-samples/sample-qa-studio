"""OS-level browser action step executor.

Uses the AgentCore InvokeBrowser API to perform OS-level actions
(keyboard shortcuts, key presses, mouse clicks) that CDP cannot handle,
such as dismissing permission dialogs or interacting with native OS prompts.
"""

import logging
import time
import boto3
from models import ExecutionStep

logger = logging.getLogger(__name__)


def _get_data_plane_client(region: str):
    """Create a bedrock-agentcore data plane client for InvokeBrowser."""
    return boto3.client(
        'bedrock-agentcore',
        region_name=region,
        endpoint_url=f"https://bedrock-agentcore.{region}.amazonaws.com"
    )


def _parse_os_action(instruction: str) -> list:
    """Parse instruction into a list of InvokeBrowser actions.

    Supports:
      - "press escape"           -> keyPress escape
      - "press tab"              -> keyPress tab
      - "press enter"            -> keyPress enter
      - "press tab enter"        -> keyPress tab, then keyPress enter
      - "type hello world"       -> keyType "hello world"
      - "shortcut ctrl a"        -> keyShortcut ["ctrl", "a"]
      - "click 100 200"          -> mouseClick x=100 y=200
      - "click 100 200 right"    -> mouseClick x=100 y=200 button=RIGHT
    """
    actions = []
    text = instruction.strip().lower()

    if text.startswith("type "):
        # keyType: "type hello world" -> types "hello world"
        content = instruction.strip()[5:]  # preserve original case
        actions.append({"keyType": {"text": content}})

    elif text.startswith("shortcut "):
        # keyShortcut: "shortcut ctrl a" -> ["ctrl", "a"]
        keys = text[9:].split()
        actions.append({"keyShortcut": {"keys": keys}})

    elif text.startswith("click "):
        # mouseClick: "click 100 200" or "click 100 200 right"
        parts = text[6:].split()
        if len(parts) >= 2:
            action = {
                "x": int(parts[0]),
                "y": int(parts[1]),
                "button": "LEFT",
                "clickCount": 1,
            }
            if len(parts) >= 3:
                action["button"] = parts[2].upper()
            actions.append({"mouseClick": action})

    elif text.startswith("press "):
        # keyPress: "press escape" or "press tab enter" (multiple keys in sequence)
        keys = text[6:].split()
        for key in keys:
            actions.append({"keyPress": {"key": key, "presses": 1}})

    else:
        # Default: treat as a single key press
        actions.append({"keyPress": {"key": text, "presses": 1}})

    return actions


def execute_os_action_step(nova, step: ExecutionStep, region: str):
    """Execute an OS-level browser action step via InvokeBrowser API."""
    logger.info(f"Executing OS action step {step.sort}: {step.instruction}")
    result = None
    success = True
    logs = ""

    try:
        session_id = nova.get_session_id()
        if not session_id:
            raise ValueError("No Nova Act session ID available for OS action")

        dp_client = _get_data_plane_client(region)
        actions = _parse_os_action(step.instruction)

        if not actions:
            raise ValueError(f"Could not parse OS action from instruction: {step.instruction}")

        for i, action in enumerate(actions):
            logger.info(f"  OS action {i+1}/{len(actions)}: {action}")
            response = dp_client.invoke_browser(
                browserIdentifier="aws.browser.v1",
                sessionId=session_id,
                action=action,
            )

            # Check result status
            action_type = list(action.keys())[0]
            action_result = response.get("result", {}).get(action_type, {})
            status = action_result.get("status", "UNKNOWN")

            if status != "SUCCESS":
                error = action_result.get("error", "Unknown error")
                raise RuntimeError(f"OS action {action_type} failed: {error}")

            # Small delay between sequential actions
            if i < len(actions) - 1:
                time.sleep(0.3)

        logger.info(f"OS action step {step.sort} completed successfully")

    except Exception as e:
        logger.error(f"Error executing OS action step {step.sort}: {str(e)}")
        success = False
        logs = str(e)
        from types import SimpleNamespace
        result = SimpleNamespace()
        result.metadata = SimpleNamespace()
        result.metadata.act_id = "error"

    return result, success, logs
