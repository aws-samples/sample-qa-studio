import logging
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import get_table_name, create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to list all execution steps for a specific execution from DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with list of execution steps
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/executions.read'])
        if error:
            return error
        
        # Get use case ID and execution ID from path parameters
        usecase_id = event.get('pathParameters', {}).get('id')
        execution_id = event.get('pathParameters', {}).get('executionId')
        
        logger.info(f"usecaseId: {usecase_id}, executionId: {execution_id}")
        
        if not usecase_id or not execution_id:
            return create_response(400, {'error': 'Missing use case ID or execution ID'})
        
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Query DynamoDB for all execution steps
        response = table.query(
            KeyConditionExpression=Key('pk').eq(f'EXECUTION#{execution_id}') & Key('sk').begins_with('EXECUTION_STEP#')
        )
        
        steps = response.get('Items', [])
        
        # Sort steps by sort field
        steps.sort(key=lambda x: x.get('sort', 0))
        
        # Return successful response
        return create_response(200, {'steps': steps})
        
    except Exception as e:
        logger.error(f"Error listing execution steps: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
