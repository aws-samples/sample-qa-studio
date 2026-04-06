import logging
from nova_act import NovaAct
from models import ExecutionStep
from utils import STRING_SCHEMA, NUMBER_SCHEMA, BOOL_SCHEMA

logger = logging.getLogger(__name__)

def execute_retrieve_value_step(nova: NovaAct, step: ExecutionStep):
    """Execute a retrieve value step to capture data from the page"""
    logger.info(f"Executing retrieve value step {step.sort}: {step.instruction}")
    
    result = None
    success = True
    logs = ''
    retrieved_value = ''

    # Programmatic URL extraction — bypasses vision model entirely
    if getattr(step, 'value_source', '') == 'url':
        import re
        try:
            current_url = nova.page.url
            logger.info(f"Extracting from URL: {current_url}")
            pattern = step.instruction.strip() if step.instruction else None
            if pattern:
                match = re.search(pattern, current_url)
                if match and match.groups():
                    retrieved_value = match.group(1)
                elif match:
                    retrieved_value = match.group(0)
                else:
                    success = False
                    logs = f"Regex pattern '{pattern}' did not match URL: {current_url}"
            else:
                retrieved_value = current_url
            logger.info(f"URL extraction result: {retrieved_value}")
        except Exception as e:
            success = False
            logs = f"URL extraction failed: {str(e)}"

        from types import SimpleNamespace
        result = SimpleNamespace()
        result.metadata = SimpleNamespace()
        result.metadata.act_id = "url_extract"
        result.parsed_response = retrieved_value

        status = "success" if success else "error"
        logger.info(f"Step: {step.sort} Type: retrieve_value Source: url Status: {status} Retrieved: {retrieved_value}")
        return result, success, logs, retrieved_value

    try:
        schema = STRING_SCHEMA
        if hasattr(step, 'value_type') and step.value_type:
            if step.value_type == 'number':
                schema = NUMBER_SCHEMA
            elif step.value_type == 'bool':
                schema = BOOL_SCHEMA
            # Default to STRING_SCHEMA for 'string' or unknown types
        
        # Execute the instruction to retrieve the value
        result = nova.act_get(step.instruction, schema=schema)
        
        # Convert result to string for consistent storage
        if result and result.parsed_response is not None:
            retrieved_value = str(result.parsed_response)
            # Strip surrounding quotes if present (for string values)
            if step.value_type == 'string' or not hasattr(step, 'value_type'):
                retrieved_value = retrieved_value.strip().strip('"').strip("'")
            logger.info(f"Retrieved value: {retrieved_value}")
        else:
            success = False
            logs = "No value retrieved from page"
            logger.warning(f"Step {step.sort}: {logs}")

    except Exception as e:
        logger.error(f"Error executing retrieve value step {step.sort}: {str(e)}")
        success = False
        logs = f"Retrieve value step failed with exception: {str(e)}"
        retrieved_value = ''
        
        # Create a minimal result object to prevent None access errors
        from types import SimpleNamespace
        result = SimpleNamespace()
        result.metadata = SimpleNamespace()
        result.metadata.act_id = e.metadata.act_id if hasattr(e, 'metadata') else "error"
        result.parsed_response = "Exception occurred"

    status = "success" if success else "error"
    logger.info(f"Step: {step.sort} Type: retrieve_value Status: {status} Retrieved: {retrieved_value}")

    return result, success, logs, retrieved_value