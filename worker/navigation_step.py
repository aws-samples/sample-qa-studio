import logging
from nova_act import NovaAct, BOOL_SCHEMA
from models import ExecutionStep

logger = logging.getLogger(__name__)

def execute_navigation_step(nova: NovaAct, step: ExecutionStep):
  logger.info(f"Executing navigation step {step.sort}: {step.instruction}")
  result = None
  success = True
  logs = ""
  
  try:
    result = nova.act(f"{step.instruction}")
          
  except Exception as e:
    logger.error(f"Error executing navigation step {step.sort}: {str(e)}")
    success = False
    logs = str(e)
    # Create a minimal result object to prevent None access errors
    from types import SimpleNamespace
    result = SimpleNamespace()
    result.metadata = SimpleNamespace()
    result.metadata.act_id = "error"
    result.parsed_response = "Exception occurred"

  status = "success" if success else "error"
  logger.info(f"Navigation step {step.sort} completed with status: {status}")
  
  return result, success, logs