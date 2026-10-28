import json
import logging
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response, get_current_timestamp
from resource_auth import require_resource_access, usecase_from_path

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', usecase_from_path, scopes=['api/usecases.write'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create or update use case headers in Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        # Get use case ID from path parameters
        usecase_id = event['pathParameters']['id']  # validated by the resolver
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        headers = body.get('headers', {})
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Create timestamp
        now = get_current_timestamp()
        
        # Create or update headers record
        headers_item = {
            'pk': f'USECASE#{usecase_id}',
            'sk': 'HEADERS',
            'headers': headers,
            'created_at': now
        }
        
        # Put item in DynamoDB
        table.put_item(Item=headers_item)
        
        return create_response(200, {'message': 'Headers saved successfully'})
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error creating use case headers: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
