import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, DynamoDBEncoder, validate_path_id
from resource_auth import require_resource_access, execution_from_path
import json

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('view', execution_from_path, scopes=['api/executions.read'], allow_worker=True)
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
        # Get parameters from path
        execution_id, error = validate_path_id(event.get('pathParameters', {}).get('executionId'), 'execution ID')
        if error:
            return error
        usecase_id = event['pathParameters']['id']  # validated by the resolver
        
        # Initialize Amazon DynamoDB client
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
