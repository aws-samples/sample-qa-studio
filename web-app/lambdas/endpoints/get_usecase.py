import logging
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get a specific use case from Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with use case data
    """
    try:
        # Validate scope (requires usecases.read or admin)
        user_identity, error_response = require_scopes(event, ['api/usecases.read'])
        if error_response:
            return error_response
        
        # Get use case ID from path parameters
        usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get the use case
        response = table.get_item(
            Key={
                'pk': 'USECASES',
                'sk': f'USECASE#{usecase_id}'
            }
        )
        
        usecase = response.get('Item')
        
        if not usecase:
            return create_response(404, {'error': 'Use case not found'})
        
        # Transform to camelCase for API response
        usecase['enableCache'] = usecase.get('enable_cache', False)
        
        return create_response(200, usecase)
        
    except Exception as e:
        logger.error(f"Error getting use case: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
