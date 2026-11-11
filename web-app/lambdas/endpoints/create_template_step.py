import logging
import json
from typing import Any, Dict
from uuid import uuid4
import boto3
from utils import create_response, get_table_name, get_current_timestamp, require_scopes, validate_path_id
from repeat_validation import template_step_error
from step_copy import COPYABLE_STEP_FIELDS
from template_store import bump_template_version

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
        template_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})

        repeat_error = template_step_error(body)
        if repeat_error:
            return create_response(400, {'error': repeat_error})
        
        # Initialize Amazon DynamoDB client
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
        
        # Add optional fields (every authored field; ``if in body`` keeps
        # today's "client decides" rule, including explicit empty values)
        for field in COPYABLE_STEP_FIELDS:
            if field in body:
                step[field] = body[field]
        
        # Save step
        table.put_item(Item=step)
        bump_template_version(table, template_id)
        
        logger.info(f"Created template step {step_id} for template {template_id}")
        
        return create_response(201, step)
        
    except Exception as e:
        logger.error(f"Error creating template step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
