import logging
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response
from resource_auth import require_resource_access, usecase_from_path

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('view', usecase_from_path, scopes=['api/usecases.read'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get use case hooks from Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with use case hooks
    """
    try:
        # Get use case ID from path parameters
        usecase_id = event['pathParameters']['id']  # validated by the resolver
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get the use case hooks
        response = table.get_item(
            Key={
                'pk': f'USECASE#{usecase_id}',
                'sk': 'HOOKS'
            }
        )
        
        item = response.get('Item')
        
        # Return empty hooks if none exist
        if not item:
            return create_response(200, {
                'before_script': '',
                'after_script': ''
            })
        
        return create_response(200, item)
        
    except Exception as e:
        logger.error(f"Error getting use case hooks: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
