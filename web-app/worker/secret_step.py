import logging
from nova_act import NovaAct
from models import ExecutionStep
from secrets_client import SecretsClient, SecretsMissingException
from utils import get_region

logger = logging.getLogger(__name__)

def execute_secret_step(nova: NovaAct, step: ExecutionStep, usecase_id: str):
  logger.info(f"Executing secret step {step.sort}: {step.instruction} (secret: {step.secret_key})")
  result = None
  success = True
  logs = ""
  
  try:
    secrets_client = SecretsClient(get_region())
    secret_value = secrets_client.get_secret_value(usecase_id, step.secret_key)
                            
    if secret_value is None:
        raise SecretsMissingException(f"Secret key '{step.secret_key}' not found")
    
    # Execute the instruction first, then type the secret
    result = nova.act(step.instruction)
    #print("RESULT")
    #print(result)
    
    # Type the secret value
    nova.page.keyboard.type(secret_value)
         
  except SecretsMissingException as e:
    logger.error(f"Secret missing for step {step.sort}: {str(e)}")
    success = False
    logs = str(e)
    # Create a minimal result object to prevent None access errors
    from types import SimpleNamespace
    result = SimpleNamespace()
    result.metadata = SimpleNamespace()
    result.metadata.act_id = e.metadata.act_id if hasattr(e, 'metadata') else "error"
    
  except Exception as e:
    logger.error(f"Error executing secret step {step.sort}: {str(e)}")
    success = False
    logs = str(e)
    # Create a minimal result object to prevent None access errors
    from types import SimpleNamespace
    result = SimpleNamespace()
    result.metadata = SimpleNamespace()
    result.metadata.act_id = "error"

  status = "success" if success else "error"
  logger.info(f"Secret step {step.sort} completed with status: {status}")
  
  return result, success, logs