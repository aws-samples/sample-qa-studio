import json
import logging
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response, get_current_timestamp, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create or update use case hooks in Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        # Validate scopes
        user_identity, error_response = require_scopes(event, ['api/usecases.write'])
        if error_response:
            return error_response
        
        # Get use case ID from path parameters
        usecase_id = event.get('pathParameters', {}).get('id')
        if not usecase_id:
            return create_response(400, {'error': 'Missing use case ID'})
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        before_script = body.get('before_script', '')
        after_script = body.get('after_script', '')
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Create timestamp
        now = get_current_timestamp()
        
        # Create or update hooks record
        hooks = {
            'pk': f'USECASE#{usecase_id}',
            'sk': 'HOOKS',
            'before_script': before_script,
            'after_script': after_script,
            'created_at': now
        }
        
        # Put item in DynamoDB
        table.put_item(Item=hooks)
        
        return create_response(200, hooks)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error creating use case hooks: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
