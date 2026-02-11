import logging
import json
from typing import Any, Dict
from uuid import uuid4
import boto3
from utils import create_response, get_table_name, get_current_timestamp, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create a new template step.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with created step
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/templates.write'])
        if error:
            return error
        
        # Get template ID from path
        path_params = event.get('pathParameters', {})
        template_id = path_params.get('id')
        
        if not template_id:
            return create_response(400, {'error': 'Missing template ID'})
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})
        
        # Initialize AWS clients
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Generate step ID
        step_id = str(uuid4())
        now = get_current_timestamp()
        
        # Create step
        step = {
            'pk': f'TEMPLATE#{template_id}',
            'sk': f'STEP#{step_id}',
            'id': step_id,
            'sort': body.get('sort', 0),
            'instruction': body.get('instruction', ''),
            'step_type': body.get('step_type', ''),
            'created_at': now
        }
        
        # Add optional fields
        optional_fields = [
            'secret_key',
            'capture_variable',
            'validation_type',
            'validation_operator',
            'validation_value',
            'assertion_variable',
            'value_type'
        ]
        
        for field in optional_fields:
            if field in body:
                step[field] = body[field]
        
        # Save step
        table.put_item(Item=step)
        
        logger.info(f"Created template step {step_id} for template {template_id}")
        
        return create_response(201, step)
        
    except Exception as e:
        logger.error(f"Error creating template step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
