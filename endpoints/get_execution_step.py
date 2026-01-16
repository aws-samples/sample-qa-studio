import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, DynamoDBEncoder
import json

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get execution step details.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with execution step details
    """
    try:
        # Get parameters from path
        path_params = event.get('pathParameters', {})
        step_id = path_params.get('stepId')
        execution_id = path_params.get('executionId')
        
        if not step_id or not execution_id:
            return create_response(400, {'error': 'StepId and ExecutionId are required'})
        
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get execution step from DynamoDB
        response = table.get_item(
            Key={
                'pk': f'EXECUTION_STEP#{step_id}',
                'sk': f'EXECUTION#{execution_id}'
            }
        )
        
        if 'Item' not in response:
            return create_response(404, {'error': 'Execution step not found'})
        
        execution_step = response['Item']
        
        return create_response(200, execution_step)
        
    except Exception as e:
        logger.error(f"Error getting execution step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
