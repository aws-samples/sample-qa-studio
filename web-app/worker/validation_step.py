import re
import logging
from nova_act import NovaAct, BOOL_SCHEMA
from models import ExecutionStep

from utils import STRING_SCHEMA, NUMBER_SCHEMA
from transform.date_compare import evaluate_date_assertion
from transform.date_parser import DateParseError

logger = logging.getLogger(__name__)

def execute_validation_step(nova: NovaAct, step: ExecutionStep):
  logger.info(f"Executing validation step {step.sort}: {step.instruction} ({step.validation_type} validation)")
  logger.info(f"Expected value (after variable substitution): {step.validation_value}")
  result = None
  success = True
  logs = ''
  expected_value = None
  actual_value = None

  try:
    if step.validation_type == 'bool':
      result = nova.act_get(step.instruction, schema=BOOL_SCHEMA)
      expected_value = step.validation_value.lower() == 'true'
      actual_value = result.parsed_response
      
      if actual_value != expected_value:
        success = False
          
    elif step.validation_type == 'string' and step.validation_operator == 'exact':
      result = nova.act_get(step.instruction, schema=STRING_SCHEMA)
      # Strip whitespace and remove surrounding quotes if present
      expected_value = step.validation_value.strip().strip('"').strip("'")
      actual_value = str(result.parsed_response).strip().strip('"').strip("'") if result.parsed_response is not None else ""
          
      if actual_value != expected_value:
        success = False
    
    elif step.validation_type == 'string' and step.validation_operator == 'exact_case_insensitive':
      result = nova.act_get(step.instruction, schema=STRING_SCHEMA)
      # Strip whitespace and remove surrounding quotes if present
      expected_value = step.validation_value.strip().strip('"').strip("'").lower()
      actual_value = str(result.parsed_response).strip().strip('"').strip("'").lower() if result.parsed_response is not None else ""
          
      if actual_value != expected_value:
        success = False
    
    elif step.validation_type == 'string' and step.validation_operator == 'contains':
      result = nova.act_get(step.instruction, schema=STRING_SCHEMA)
      # Strip whitespace and remove surrounding quotes if present
      expected_value = step.validation_value.strip().strip('"').strip("'")
      actual_value = str(result.parsed_response).strip().strip('"').strip("'") if result.parsed_response is not None else ""
      
      if not re.search(re.escape(expected_value), actual_value):
        success = False

    elif step.validation_type == 'string' and step.validation_operator == 'contains_case_insensitive':
      result = nova.act_get(step.instruction, schema=STRING_SCHEMA)
      # Strip whitespace and remove surrounding quotes if present
      expected_value = step.validation_value.strip().strip('"').strip("'")
      actual_value = str(result.parsed_response).strip().strip('"').strip("'") if result.parsed_response is not None else ""
      
      if not re.search(re.escape(expected_value), actual_value, re.IGNORECASE):
        success = False

    elif step.validation_type == 'string' and step.validation_operator == 'not_equal':
      result = nova.act_get(step.instruction, schema=STRING_SCHEMA)
      # Strip whitespace and remove surrounding quotes if present
      expected_value = step.validation_value.strip().strip('"').strip("'")
      actual_value = str(result.parsed_response).strip().strip('"').strip("'") if result.parsed_response is not None else ""
          
      if actual_value == expected_value:
        success = False

    # number equals
    elif step.validation_type == 'number' and step.validation_operator == 'equals':
      result = nova.act_get(step.instruction, schema=NUMBER_SCHEMA)
      expected_value = float(step.validation_value)
      actual_value = float(result.parsed_response) if result.parsed_response is not None else 0.0
      
      if actual_value != expected_value:
        success = False

    # number greater_then
    elif step.validation_type == 'number' and step.validation_operator == 'greater_then':
      result = nova.act_get(step.instruction, schema=NUMBER_SCHEMA)
      expected_value = float(step.validation_value)
      actual_value = float(result.parsed_response) if result.parsed_response is not None else 0.0
      
      if actual_value <= expected_value:
        success = False

    # number less_then
    elif step.validation_type == 'number' and step.validation_operator == 'less_then':
      result = nova.act_get(step.instruction, schema=NUMBER_SCHEMA)
      expected_value = float(step.validation_value)
      actual_value = float(result.parsed_response) if result.parsed_response is not None else 0.0
      
      if actual_value >= expected_value:
        success = False

    # number greater_or_equal
    elif step.validation_type == 'number' and step.validation_operator == 'greater_or_equal_then':
      result = nova.act_get(step.instruction, schema=NUMBER_SCHEMA)
      expected_value = float(step.validation_value)
      actual_value = float(result.parsed_response) if result.parsed_response is not None else 0.0
      
      if actual_value < expected_value:
        success = False

    # number less_or_equal
    elif step.validation_type == 'number' and step.validation_operator == 'less_or_equal_then':
      result = nova.act_get(step.instruction, schema=NUMBER_SCHEMA)
      expected_value = float(step.validation_value)
      actual_value = float(result.parsed_response) if result.parsed_response is not None else 0.0
      
      if actual_value > expected_value:
        success = False

    elif step.validation_type == 'date':
      # Extract the page value as a string; date parsing happens on our side
      # (Nova has no date schema). The date_compare helper handles operator
      # dispatch, equals_within JSON payload, and the naive-vs-aware warning.
      result = nova.act_get(step.instruction, schema=STRING_SCHEMA)
      actual_value = str(result.parsed_response) if result.parsed_response is not None else ""
      expected_value = step.validation_value
      try:
        success, logs = evaluate_date_assertion(
          actual=actual_value,
          validation_value=expected_value,
          operator=step.validation_operator,
        )
      except (DateParseError, ValueError) as exc:
        success = False
        logs = f"Date validation error: {exc}"

    else:
      logger.error(f"Unknown validation type '{step.validation_type}' for step {step.sort}")
      result = nova.act_get(step.instruction, schema=BOOL_SCHEMA)
      expected_value = "unknown"
      actual_value = result.parsed_response if result else None

  except Exception as e:
    logger.error(f"Error executing validation step {step.sort}: {str(e)}")
    success = False
    expected_value = step.validation_value if hasattr(step, 'validation_value') else "unknown"
    actual_value = ""
    # Create a minimal result object to prevent None access errors
    from types import SimpleNamespace
    result = SimpleNamespace()
    result.metadata = SimpleNamespace()
    result.metadata.act_id = e.metadata.act_id if hasattr(e, 'metadata') else "error"
    result.parsed_response = "Exception occurred"
    logs = str(e)

  status = "success" if success else "error"
  logger.info(f"Step: {step.sort} Type: {step.validation_type} Operator: {step.validation_operator} Status: {status} Expected {expected_value} Got {actual_value}")

  return result, success, logs, str(actual_value)