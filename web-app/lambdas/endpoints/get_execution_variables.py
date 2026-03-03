import logging
from typing import Any, Dict, List
import boto3
from utils import create_response, get_table_name, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get execution variables (both defined and runtime).
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with variables and runtime_variables
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/executions.read'])
        if error:
            return error
        
        logger.info(f"Request: {event}")
        
        # Get parameters from path
        path_params = event.get('pathParameters', {})
        execution_id = path_params.get('executionId')
        usecase_id = path_params.get('id')
        
        if not execution_id or not usecase_id:
            return create_response(400, {'error': 'Missing required parameters'})
        
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Initialize response with empty arrays
        variables = []
        runtime_variables = []
        
        # Query use case variables (defined variables)
        try:
            usecase_response = table.get_item(
                Key={
                    'pk': f'USECASE#{usecase_id}',
                    'sk': 'USECASE_VARIABLES'
                }
            )
            
            if 'Item' in usecase_response:
                raw_variables = usecase_response['Item'].get('variables', [])
                # Ensure keys are lowercase for frontend compatibility
                variables = []
                for var in raw_variables:
                    if isinstance(var, dict):
                        # Handle both uppercase and lowercase keys
                        variables.append({
                            'key': var.get('key') or var.get('Key', ''),
                            'value': var.get('value') or var.get('Value', '')
                        })
                    else:
                        variables.append(var)
        except Exception as e:
            logger.warning(f"Error querying use case variables: {str(e)}")
        
        # Query execution variables (merged variables and runtime variables)
        execution_variables = {}
        try:
            execution_response = table.get_item(
                Key={
                    'pk': f'EXECUTION#{execution_id}',
                    'sk': 'EXECUTION_VARIABLES'
                }
            )
            
            if 'Item' in execution_response:
                runtime_variables = execution_response['Item'].get('runtime_variables', [])
                # Also read merged variables stored by execute_test_suite
                # These contain usecase vars + CLI overrides already merged
                merged_vars = execution_response['Item'].get('variables', {})
                if isinstance(merged_vars, dict) and merged_vars:
                    execution_variables = merged_vars
        except Exception as e:
            logger.warning(f"Error querying execution variables: {str(e)}")
        
        logger.info(f"Successfully retrieved execution variables for execution {execution_id}")
        
        return create_response(200, {
            'variables': variables,
            'runtime_variables': runtime_variables,
            'execution_variables': execution_variables
        })
        
    except Exception as e:
        logger.error(f"Error getting execution variables: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
