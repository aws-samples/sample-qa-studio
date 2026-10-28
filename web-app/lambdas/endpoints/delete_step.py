import logging
from typing import Any, Dict
import boto3
from utils import no_content_response, get_table_name, create_response, validate_path_id
from resource_auth import require_resource_access, usecase_from_path

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', usecase_from_path, scopes=['api/usecases.write'])
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
        # Get usecase ID and step ID from path parameters
        usecase_id = event['pathParameters']['id']  # validated by the resolver

        step_id, error = validate_path_id(event.get('pathParameters', {}).get('stepId'), 'step ID')
        if error:
            return error
        
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
        
        return no_content_response()
        
    except Exception as e:
        logger.error(f"Error deleting step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
