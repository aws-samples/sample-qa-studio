import logging
from nova_act import NovaAct
from models import ExecutionStep

logger = logging.getLogger(__name__)

def execute_url_step(nova: NovaAct, step: ExecutionStep):
    """Execute a URL step to navigate to a custom URL"""
    logger.info(f"Executing URL step {step.sort}: navigating to {step.instruction}")
    result = None
    success = True
    logs = ""
    
    try:
        # Use nova.go_to_url to navigate to the specified URL
        nova.go_to_url(step.instruction)
        logger.info(f"Successfully navigated to URL: {step.instruction}")
        
    except Exception as e:
        logger.error(f"Error executing URL step {step.sort}: {str(e)}")
        success = False
        logs = str(e)
        # Create a minimal result object to prevent None access errors
        from types import SimpleNamespace
        result = SimpleNamespace()
        result.metadata = SimpleNamespace()
        result.metadata.act_id = "error"
        result.parsed_response = f"Failed to navigate to {step.instruction}"

    status = "success" if success else "error"
    logger.info(f"URL step {step.sort} completed with status: {status}")
    
    return result, success, logs