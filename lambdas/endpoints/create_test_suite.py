import logging
import json
import boto3
from typing import Any, Dict
from utils import (
    create_response,
    get_table_name,
    get_current_timestamp,
    require_scopes,
    generate_uuid7
)
from test_suite_schema import create_test_suite_item

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create a new test suite.
    
    Validates user has write access to specified scope, generates UUID,
    creates suite item in DynamoDB with all required fields, and returns
    the created suite object.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with created test suite
    """
    try:
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})
        
        # Validate required fields
        name = body.get('name', '').strip()
        description = body.get('description', '').strip()
        scope = body.get('scope', '').strip()
        tags = body.get('tags', [])
        
        if not name:
            return create_response(400, {'error': 'name is required'})
        
        if len(name) < 3 or len(name) > 100:
            return create_response(400, {'error': 'name must be between 3 and 100 characters'})
        
        if not description:
            return create_response(400, {'error': 'description is required'})
        
        if len(description) > 500:
            return create_response(400, {'error': 'description must be 500 characters or less'})
        
        # Auto-generate scope from name if not provided
        if not scope:
            # Convert name to kebab-case for scope
            scope_name = name.lower().replace(' ', '-').replace('_', '-')
            # Remove any characters that aren't alphanumeric or hyphens
            scope_name = ''.join(c for c in scope_name if c.isalnum() or c == '-')
            # Remove consecutive hyphens
            while '--' in scope_name:
                scope_name = scope_name.replace('--', '-')
            # Remove leading/trailing hyphens
            scope_name = scope_name.strip('-')
            scope = f'suite:{scope_name}'
        
        # Validate scope format if provided (should be like 'suite:name')
        if not scope.startswith('suite:'):
            return create_response(400, {'error': 'scope must start with "suite:"'})
        
        if not isinstance(tags, list):
            return create_response(400, {'error': 'tags must be an array'})
        
        # Validate scope access (requires api/suite.write or admin)
        user_identity, error_response = require_scopes(event, ['api/suite.write'])
        if error_response:
            return error_response
        
        user_identity_str = user_identity.get('identity', '')
        
        logger.info(f"Creating test suite for user: {user_identity_str}")
        
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Generate suite ID and timestamp
        suite_id = generate_uuid7()
        now = get_current_timestamp()
        
        # Extract optional schedule fields
        schedule_enabled = body.get('schedule_enabled', False)
        schedule_expression = body.get('schedule_expression')
        schedule_timezone = body.get('schedule_timezone')
        
        # Create test suite item using schema utility
        suite_item = create_test_suite_item(
            suite_id=suite_id,
            name=name,
            description=description,
            scope=scope,
            tags=tags,
            created_by=user_identity_str,
            created_at=now,
            schedule_enabled=schedule_enabled,
            schedule_expression=schedule_expression,
            schedule_timezone=schedule_timezone
        )
        
        # Write to DynamoDB
        table.put_item(Item=suite_item)
        
        logger.info(f"Successfully created test suite {suite_id}")
        
        # Return the created suite (remove pk/sk from response)
        response_suite = {k: v for k, v in suite_item.items() if k not in ['pk', 'sk']}
        
        return create_response(201, response_suite)
        
    except Exception as e:
        logger.error(f"Error creating test suite: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
