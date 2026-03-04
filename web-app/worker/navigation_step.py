import logging
import json
import time
from types import SimpleNamespace
from nova_act import NovaAct, BOOL_SCHEMA
from models import ExecutionStep
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

def execute_navigation_step(nova: NovaAct, step: ExecutionStep, enable_cache: bool = False):
  logger.info(f"Executing navigation step {step.sort}: {step.instruction}")
  result = None
  success = True
  logs = ""
  
  # Check cache eligibility: enable_cache from execution + cached_steps on the step
  cached_steps = getattr(step, 'cached_steps', None)
  
  # Attempt cache execution only if enabled on execution AND step has cache data
  if enable_cache and cached_steps and cached_steps.strip():
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
    except json.JSONDecodeError as e:
      # Cached steps JSON is malformed or corrupted
      logger.warning(f"Failed to parse cached_steps for step {step.sort}: {e}, falling back to Nova Act")
    except Exception as e:
      # Catch-all for unexpected errors (e.g., browser crashes, network issues)
      logger.warning(f"Unexpected error during cache execution for step {step.sort}: {e}, falling back to Nova Act")
  else:
    # Log cache miss reasons for observability
    # This helps identify why cache wasn't used (disabled vs. no data available)
    if not enable_cache:
      logger.info(f"Cache miss for step {step.sort}: caching disabled")
    elif not cached_steps or not cached_steps.strip():
      logger.info(f"Cache miss for step {step.sort}: no cached steps available")
  
  try:
    # Build the instruction with optional advanced click types prompt
    instruction = step.instruction
    if hasattr(step, 'enable_advanced_click_types') and step.enable_advanced_click_types:
      instruction = f"{click_base_prompt}\n\n{step.instruction}"
    
    result = nova.act(instruction)
          
  except Exception as e:
    logger.error(f"Error executing navigation step {step.sort}: {str(e)}")
    success = False
    logs = str(e)
    # Create a minimal result object to prevent None access errors
    result = SimpleNamespace()
    result.metadata = SimpleNamespace()
    result.metadata.act_id = e.metadata.act_id if hasattr(e, 'metadata') else "error"

  status = "success" if success else "error"
  logger.info(f"Navigation step {step.sort} completed with status: {status}")
  
  return result, success, logs