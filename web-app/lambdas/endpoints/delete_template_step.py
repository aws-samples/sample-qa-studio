import logging
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to delete a template step from Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/templates.write'])
        if error:
            return error
        
        # Get template ID and step ID from path parameters
        template_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error

        step_id, error = validate_path_id(event.get('pathParameters', {}).get('stepId'), 'step ID')
        if error:
            return error
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Delete the step
        table.delete_item(
            Key={
                'pk': f'TEMPLATE#{template_id}',
                'sk': f'STEP#{step_id}'
            }
        )
        
        return create_response(200, {'message': 'Step deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting template step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
