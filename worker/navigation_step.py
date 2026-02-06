import logging
from nova_act import NovaAct, BOOL_SCHEMA
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
agentClick(bbox, 'left-double') performs a double-click on the bbox.

Prompt: 
"""

def execute_navigation_step(nova: NovaAct, step: ExecutionStep):
  logger.info(f"Executing navigation step {step.sort}: {step.instruction}")
  result = None
  success = True
  logs = ""
  
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
    from types import SimpleNamespace
    result = SimpleNamespace()
    result.metadata = SimpleNamespace()
    result.metadata.act_id = e.metadata.act_id if hasattr(e, 'metadata') else "error"

  status = "success" if success else "error"
  logger.info(f"Navigation step {step.sort} completed with status: {status}")
  
  return result, success, logs