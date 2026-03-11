import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get live view URL for an execution.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with live view data
    """
    try:
        # Handle CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return create_response(200, {})
        
        if event.get('httpMethod') != 'GET':
            return create_response(405, {'error': 'method not allowed'})
        
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/executions.read'])
        if error:
            return error
        
        # Get execution ID from path
        path_params = event.get('pathParameters', {})
        execution_id, error = validate_path_id(event.get('pathParameters', {}).get('executionId'), 'execution ID')
        if error:
            return error
        
        # Initialize Amazon DynamoDB
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get live view record
        response = table.get_item(
            Key={
                'pk': f'EXECUTION#{execution_id}',
                'sk': 'LIVE_VIEW'
            }
        )
        
        if 'Item' not in response:
            return create_response(404, {'error': 'live view not found'})
        
        record = response['Item']
        
        logger.info(f"Retrieved live view for execution {execution_id}")
        
        return create_response(200, record)
        
    except Exception as e:
        logger.error(f"Error getting live view: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'failed to get live view'})
