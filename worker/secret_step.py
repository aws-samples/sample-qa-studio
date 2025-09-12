import logging
from nova_act import NovaAct, BOOL_SCHEMA
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
    result = nova.act(f"{step.instruction} you must return a bool if the action was successful", schema=BOOL_SCHEMA)
    
    # Type the secret value
    nova.page.keyboard.type(secret_value)
    
    # Check if the action was successful
    if not result.parsed_response:
      success = False
      logs = f"Secret step failed: Action was not successful. Got: {result.parsed_response}"
        
  except SecretsMissingException as e:
    logger.error(f"Secret missing for step {step.sort}: {str(e)}")
    success = False
    logs = str(e)
    # Create a minimal result object to prevent None access errors
    from types import SimpleNamespace
    result = SimpleNamespace()
    result.metadata = SimpleNamespace()
    result.metadata.act_id = "error"
    result.parsed_response = "Secret missing"
    
  except Exception as e:
    logger.error(f"Error executing secret step {step.sort}: {str(e)}")
    success = False
    logs = str(e)
    # Create a minimal result object to prevent None access errors
    from types import SimpleNamespace
    result = SimpleNamespace()
    result.metadata = SimpleNamespace()
    result.metadata.act_id = "error"
    result.parsed_response = "Exception occurred"

  status = "success" if success else "error"
  logger.info(f"Secret step {step.sort} completed with status: {status}")
  
  return result, success, logs