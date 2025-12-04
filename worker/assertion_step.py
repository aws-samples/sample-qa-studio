import re
import logging
from models import ExecutionStep

logger = logging.getLogger(__name__)

def execute_assertion_step(step: ExecutionStep, runtime_variables: dict):
    """
    Execute an assertion step that compares a runtime variable against an expected value.
    This step does not trigger any nova.act() actions - it only performs comparisons.
    
    Args:
        step: ExecutionStep containing assertion configuration
        runtime_variables: Dictionary of runtime variables captured during execution
    
    Returns:
        tuple: (result_object, success, logs, actual_value)
    """
    logger.info(f"Executing assertion step {step.sort}: comparing runtime variable '{step.assertion_variable}' {step.validation_operator} '{step.validation_value}'")
    
    success = True
    logs = ''
    expected_value = step.validation_value
    actual_value = None

    # Create a minimal result object for consistency with other step types
    from types import SimpleNamespace
    result = SimpleNamespace()
    result.metadata = SimpleNamespace()
    result.metadata.act_id = ''

    try:
        # Get the actual value from runtime variables
        if step.assertion_variable not in runtime_variables:
            success = False
            logs = f"Runtime variable '{step.assertion_variable}' not found"
            actual_value = "VARIABLE_NOT_FOUND"
            logger.error(f"Assertion step {step.sort}: {logs}")
            return result, success, logs, str(actual_value)
        
        actual_value = runtime_variables[step.assertion_variable]
        logger.info(f"Retrieved runtime variable '{step.assertion_variable}': {actual_value}")
        
        # Perform the assertion based on validation type and operator
        if step.validation_type == 'bool':
            expected_bool = expected_value.lower() == 'true'
            actual_bool = str(actual_value).lower() == 'true'
            
            if actual_bool != expected_bool:
                success = False
                logs = f"Boolean assertion failed: expected {expected_bool}, got {actual_bool}"
            
        elif step.validation_type == 'string' and step.validation_operator == 'exact':
            expected_str = str(expected_value).strip()
            actual_str = str(actual_value).strip()
            
            if actual_str != expected_str:
                success = False
                logs = f"String exact match failed: expected '{expected_str}', got '{actual_str}'"
        
        elif step.validation_type == 'string' and step.validation_operator == 'exact_case_insensitive':
            expected_str = str(expected_value).strip().lower()
            actual_str = str(actual_value).strip().lower()
            
            if actual_str != expected_str:
                success = False
                logs = f"String exact match (case insensitive) failed: expected '{expected_str}', got '{actual_str}'"
        
        elif step.validation_type == 'string' and step.validation_operator == 'contains':
            expected_str = str(expected_value).strip()
            actual_str = str(actual_value).strip()
            
            if not re.search(re.escape(expected_str), actual_str):
                success = False
                logs = f"String contains failed: '{actual_str}' does not contain '{expected_str}'"

        elif step.validation_type == 'string' and step.validation_operator == 'contains_case_insensitive':
            expected_str = str(expected_value).strip()
            actual_str = str(actual_value).strip()
            
            if not re.search(re.escape(expected_str), actual_str, re.IGNORECASE):
                success = False
                logs = f"String contains (case insensitive) failed: '{actual_str}' does not contain '{expected_str}'"

        elif step.validation_type == 'number' and step.validation_operator == 'equals':
            try:
                expected_num = float(expected_value)
                actual_num = float(actual_value)
                
                if actual_num != expected_num:
                    success = False
                    logs = f"Number equals failed: expected {expected_num}, got {actual_num}"
            except ValueError as e:
                success = False
                logs = f"Number conversion failed: {str(e)}"

        elif step.validation_type == 'number' and step.validation_operator == 'greater_then':
            try:
                expected_num = float(expected_value)
                actual_num = float(actual_value)
                
                if actual_num <= expected_num:
                    success = False
                    logs = f"Number greater than failed: {actual_num} is not greater than {expected_num}"
            except ValueError as e:
                success = False
                logs = f"Number conversion failed: {str(e)}"

        elif step.validation_type == 'number' and step.validation_operator == 'less_then':
            try:
                expected_num = float(expected_value)
                actual_num = float(actual_value)
                
                if actual_num >= expected_num:
                    success = False
                    logs = f"Number less than failed: {actual_num} is not less than {expected_num}"
            except ValueError as e:
                success = False
                logs = f"Number conversion failed: {str(e)}"

        elif step.validation_type == 'number' and step.validation_operator == 'greater_or_equal_then':
            try:
                expected_num = float(expected_value)
                actual_num = float(actual_value)
                
                if actual_num < expected_num:
                    success = False
                    logs = f"Number greater or equal failed: {actual_num} is not >= {expected_num}"
            except ValueError as e:
                success = False
                logs = f"Number conversion failed: {str(e)}"

        elif step.validation_type == 'number' and step.validation_operator == 'less_or_equal_then':
            try:
                expected_num = float(expected_value)
                actual_num = float(actual_value)
                
                if actual_num > expected_num:
                    success = False
                    logs = f"Number less or equal failed: {actual_num} is not <= {expected_num}"
            except ValueError as e:
                success = False
                logs = f"Number conversion failed: {str(e)}"

        else:
            logger.error(f"Unknown validation type '{step.validation_type}' or operator '{step.validation_operator}' for assertion step {step.sort}")
            success = False
            logs = f"Unknown validation type '{step.validation_type}' or operator '{step.validation_operator}'"

    except Exception as e:
        logger.error(f"Error executing assertion step {step.sort}: {str(e)}")
        success = False
        logs = f"Exception during assertion: {str(e)}"
        actual_value = "ERROR"
        result.metadata.act_id = e.metadata.act_id if hasattr(e, 'metadata') else "error"

    status = "success" if success else "error"
    logger.info(f"Assertion step {step.sort}: {step.validation_type} {step.validation_operator} - Status: {status}")
    
    if not success:
        logger.error(f"Assertion failed: {logs}")

    return result, success, logs, str(actual_value)