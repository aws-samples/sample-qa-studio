import logging
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to delete a step from Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/usecases.write'])
        if error:
            return error
        
        # Get usecase ID and step ID from path parameters
        usecase_id = event.get('pathParameters', {}).get('id')
        step_id = event.get('pathParameters', {}).get('stepId')
        
        if not usecase_id or not step_id:
            return create_response(400, {'error': 'Missing usecase ID or step ID'})
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Delete the step
        table.delete_item(
            Key={
                'pk': f'USECASE#{usecase_id}',
                'sk': f'STEP#{step_id}'
            }
        )
        
        return create_response(200, {
            'status': 'step deleted',
            'stepId': step_id
        })
        
    except Exception as e:
        logger.error(f"Error deleting step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
