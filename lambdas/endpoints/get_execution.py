import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, DynamoDBEncoder, require_scopes
import json

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get execution details.
    Accessible by both user tokens and M2M tokens.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with execution details
    """
    try:
        # Validate scope (requires executions.read or admin)
        user_identity, error_response = require_scopes(event, ['api/executions.read'])
        if error_response:
            return error_response
        
        # Get parameters from path
        path_params = event.get('pathParameters', {})
        execution_id = path_params.get('executionId')
        usecase_id = path_params.get('id')
        
        if not execution_id or not usecase_id:
            return create_response(400, {'error': 'ExecutionId and UsecaseId are required'})
        
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get execution from DynamoDB
        response = table.get_item(
            Key={
                'pk': f'USECASE_EXECUTION#{usecase_id}',
                'sk': f'EXECUTION#{execution_id}'
            }
        )
        
        if 'Item' not in response:
            return create_response(404, {'error': 'Execution not found'})
        
        execution = response['Item']
        
        return create_response(200, execution)
        
    except Exception as e:
        logger.error(f"Error getting execution: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
