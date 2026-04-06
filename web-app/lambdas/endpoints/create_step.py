import json
import logging
from typing import Any, Dict
from uuid import uuid4
import boto3
from utils import get_table_name, create_response, get_current_timestamp, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create a step for a use case in Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with created step
    """
    try:
        # Validate scopes
        user_identity, error_response = require_scopes(event, ['api/usecases.write'])
        if error_response:
            return error_response
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        usecase_id = body.get('usecaseId')
        sort = body.get('sort')
        instruction = body.get('instruction')
        step_type = body.get('step_type', 'navigation')  # Default to navigation
        secret_key = body.get('secret_key', '')
        validation_type = body.get('validation_type', '')
        validation_operator = body.get('validation_operator', '')
        validation_value = body.get('validation_value', '')
        capture_variable = body.get('capture_variable', '')
        assertion_variable = body.get('assertion_variable', '')
        value_type = body.get('value_type', '')
        enable_advanced_click_types = body.get('enable_advanced_click_types', False)
        value_source = body.get('value_source', '')
        
        if not usecase_id or sort is None or not instruction:
            return create_response(400, {'error': 'Missing required fields'})
        
        # Generate UUID and timestamp
        step_id = str(uuid4())
        now = get_current_timestamp()
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Create step item
        step = {
            'pk': f'USECASE#{usecase_id}',
            'sk': f'STEP#{step_id}',
            'id': step_id,
            'sort': sort,
            'instruction': instruction,
            'step_type': step_type,
            'secret_key': secret_key,
            'validation_type': validation_type,
            'validation_operator': validation_operator,
            'validation_value': validation_value,
            'capture_variable': capture_variable,
            'assertion_variable': assertion_variable,
            'value_type': value_type,
            'enable_advanced_click_types': enable_advanced_click_types,
            'value_source': value_source,
            'created_at': now
        }
        
        # Put item in DynamoDB
        table.put_item(Item=step)
        
        return create_response(201, step)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error creating step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
