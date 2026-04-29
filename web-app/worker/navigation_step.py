import logging
import json
import os
import time
from types import SimpleNamespace
from nova_act import NovaAct, BOOL_SCHEMA
from models import ExecutionStep, TrajectoryReplayError
from cache_executor import execute_cached_steps, CacheExecutionError

logger = logging.getLogger(__name__)

click_base_prompt = """
The `agentClick` statement supports a `clickType` argument to specify the type of click to perform.

Syntax:
agentClick(bbox: string, clickType: string): Clicks the specified box with the given click type.

Available clickType options:
- 'left': Single left click (default)
- 'left-double': Double left click
- 'right': Right click

Example:
agentClick("bbox", "left-double") performs a double-click on the bbox.

Prompt: 
"""

def execute_navigation_step(nova: NovaAct, step: ExecutionStep, enable_cache: bool = False, trajectory_manager=None):
  logger.info(f"Executing navigation step {step.sort}: {step.instruction}")
  result = None
  success = True
  logs = ""

  # TIER 1: Trajectory replay (preferred — fastest, most faithful)
  trajectory_s3_key = getattr(step, 'trajectory_s3_key', None)
  enable_trajectory = os.getenv('ENABLE_TRAJECTORY_REPLAY', 'true').lower() != 'false'
  trajectory_replay_attempted = False
  playwright_cache_failed = False

  if enable_cache and trajectory_manager and trajectory_s3_key and enable_trajectory:
    trajectory_replay_attempted = True
    try:
      replay_result = trajectory_manager.replay_step(nova, step)
      logger.info(f"Trajectory replay for step {step.sort} ({replay_result.duration_ms}ms)")

      result = SimpleNamespace()
      result.metadata = SimpleNamespace()
      result.metadata.act_id = "trajectory_replay"
      result.logs = ""
      return result, True, ""

    except TrajectoryReplayError as e:
      logger.warning(f"Trajectory replay failed for step {step.sort}: {e}, trying next tier")

  # TIER 2: Playwright cache (legacy) — only when no trajectory_s3_key
  cached_steps = getattr(step, 'cached_steps', None)

  if enable_cache and cached_steps and cached_steps.strip() and not trajectory_s3_key:
    try:
      # Parse cached steps JSON: convert string to list of action dictionaries
      # Expected format: [{"action": "click", "selector": "...", ...}, ...]
      parsed_steps = json.loads(cached_steps)

      # Execute cached steps using Playwright directly (bypasses Nova Act for speed)
      # Measure duration to track cache performance benefit (typically 40-60% faster)
      start_time = time.time()
      execute_cached_steps(nova, parsed_steps)
      duration_ms = int((time.time() - start_time) * 1000)

      logger.info(f"Cache hit for step {step.sort} (executed in {duration_ms}ms)")

      # Create cache result object that mimics Nova Act result structure
      # This ensures downstream code can handle cache results identically to Nova Act results
      result = SimpleNamespace()
      result.metadata = SimpleNamespace()
      result.metadata.act_id = "cached"  # Identifies this as a cached execution
      result.logs = ""

      return result, success, logs

    # Fallback handling: any cache execution failure should not break the test
    # We catch all exceptions and fall through to Nova Act execution below
    except CacheExecutionError as e:
      # Cache executor detected an issue (e.g., selector not found, action failed)
      logger.warning(f"Cache execution failed for step {step.sort}: {e}, falling back to Nova Act")
      playwright_cache_failed = True
    except json.JSONDecodeError as e:
      # Cached steps JSON is malformed or corrupted
      logger.warning(f"Failed to parse cached_steps for step {step.sort}: {e}, falling back to Nova Act")
      playwright_cache_failed = True
    except Exception as e:
      # Catch-all for unexpected errors (e.g., browser crashes, network issues)
      logger.warning(f"Unexpected error during cache execution for step {step.sort}: {e}, falling back to Nova Act")
      playwright_cache_failed = True
  else:
    # Log cache miss reasons for observability
    # This helps identify why cache wasn't used (disabled vs. no data available)
    if not enable_cache:
      logger.info(f"Cache miss for step {step.sort}: caching disabled")
    elif trajectory_s3_key:
      # trajectory_s3_key is set — Playwright cache is skipped in favour of trajectory replay
      logger.info(f"Cache miss for step {step.sort}: trajectory_s3_key present, Playwright cache skipped")
    elif not cached_steps or not cached_steps.strip():
      logger.info(f"Cache miss for step {step.sort}: no cached steps available")

  # TIER 3: Nova Act (always available as final fallback)
  try:
    # Build the instruction with optional advanced click types prompt
    instruction = step.instruction
    if hasattr(step, 'enable_advanced_click_types') and step.enable_advanced_click_types:
      instruction = f"{click_base_prompt}\n\n{step.instruction}"

    result = nova.act(instruction)

    # Record or refresh trajectory for future replay (non-blocking on failure)
    if trajectory_manager and trajectory_manager.is_recording_enabled:
      try:
        # Save trajectory: covers both fresh recording (no prior trajectory)
        # and stale refresh (trajectory replay was attempted but failed)
        if trajectory_replay_attempted or not trajectory_s3_key:
          trajectory_manager.save_trajectory(step.step_id, result)
      except Exception as save_err:
        logger.warning(f"Failed to save trajectory for step {step.sort}: {save_err}")

  except Exception as e:
    logger.error(f"Error executing navigation step {step.sort}: {str(e)}")
    success = False
    logs = str(e)
    # Create a minimal result object to prevent None access errors
    result = SimpleNamespace()
    result.metadata = SimpleNamespace()
    result.metadata.act_id = e.metadata.act_id if hasattr(e, 'metadata') else "error"

    # Clean up stale trajectory fields when trajectory replay failed and Nova Act also failed
    if trajectory_replay_attempted and not success:
      if trajectory_manager:
        try:
          trajectory_manager.clear_cache_fields(step.step_id, ["trajectory_s3_key", "trajectory_last_updated"])
        except Exception as cleanup_err:
          logger.warning(f"Cache cleanup: failed to clear trajectory fields for step {step.step_id}: {cleanup_err}")

  # Clean up stale Playwright cache fields when Playwright cache failed (regardless of Nova Act outcome)
  if playwright_cache_failed:
    if trajectory_manager:
      try:
        trajectory_manager.clear_cache_fields(step.step_id, ["cached_steps", "cache_last_updated"])
      except Exception as cleanup_err:
        logger.warning(f"Cache cleanup: failed to clear Playwright cache fields for step {step.step_id}: {cleanup_err}")

  status = "success" if success else "error"
  logger.info(f"Navigation step {step.sort} completed with status: {status}")

  return result, success, logs