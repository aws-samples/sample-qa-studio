import logging
from types import SimpleNamespace
from nova_act import NovaAct
from models import ExecutionStep

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

def execute_navigation_step(nova: NovaAct, step: ExecutionStep):
  """Run a navigation step through Nova Act (wizard path).

  The bbox step cache and trajectory replay are gone from the worker: the
  CLI runner (``qa-studio run``) owns trajectory replay for batch runs, and
  the wizard always records fresh actions.

  Returns ``(result, success, logs)``.
  """
  logger.info(f"Executing navigation step {step.sort}: {step.instruction}")
  try:
    # Build the instruction with optional advanced click types prompt
    instruction = step.instruction
    if getattr(step, 'enable_advanced_click_types', False):
      instruction = f"{click_base_prompt}\n\n{step.instruction}"

    result = nova.act(instruction)
    logger.info(f"Navigation step {step.sort} completed with status: success")
    return result, True, ""

  except Exception as e:
    logger.error(f"Error executing navigation step {step.sort}: {str(e)}")
    # Minimal result object so callers can read result.metadata.act_id
    result = SimpleNamespace()
    result.metadata = SimpleNamespace()
    result.metadata.act_id = e.metadata.act_id if hasattr(e, 'metadata') else "error"
    logger.info(f"Navigation step {step.sort} completed with status: error")
    return result, False, str(e)
