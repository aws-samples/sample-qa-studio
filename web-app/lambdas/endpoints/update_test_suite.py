import logging
import json
import boto3
from typing import Any, Dict
from utils import (
    create_response,
    get_table_name,
    get_current_timestamp,
    require_scopes,
    validate_path_id)
from test_suite_schema import (
    get_test_suites_pk,
    get_suite_sk,
    get_suite_update_expression
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to update test suite metadata.
    
    Validates user has write access to suite scope, updates suite metadata
    (name, description, tags), updates the updated_at timestamp, and returns
    the updated suite object.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with updated test suite
    """
    try:
        # Extract suite_id from path parameters
        path_params = event.get('pathParameters', {})
        suite_id, error = validate_path_id(event.get('pathParameters', {}).get('suite_id'), 'suite ID')
        if error:
            return error
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})
        
        # Validate scope access (requires api/suite.write or admin)
        user_identity, error_response = require_scopes(event, ['api/suite.write'])
        if error_response:
            return error_response
        
        logger.info(f"Updating test suite {suite_id} for user: {user_identity.get('identity')}")
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get existing suite to validate it exists
        response = table.get_item(
            Key={
                'pk': get_test_suites_pk(),
                'sk': get_suite_sk(suite_id)
            }
        )
        
        # Check if suite exists
        if 'Item' not in response:
            logger.warning(f"Test suite {suite_id} not found")
            return create_response(404, {'error': 'Test suite not found'})
        
        suite = response['Item']
        
        # Extract and validate update fields
        name = body.get('name')
        description = body.get('description')
        tags = body.get('tags')
        
        # Validate name if provided
        if name is not None:
            name = name.strip()
            if not name:
                return create_response(400, {'error': 'name cannot be empty'})
            if len(name) < 3 or len(name) > 100:
                return create_response(400, {'error': 'name must be between 3 and 100 characters'})
        
        # Validate description if provided
        if description is not None:
            description = description.strip()
            if not description:
                return create_response(400, {'error': 'description cannot be empty'})
            if len(description) > 500:
                return create_response(400, {'error': 'description must be 500 characters or less'})
        
        # Validate tags if provided
        if tags is not None:
            if not isinstance(tags, list):
                return create_response(400, {'error': 'tags must be an array'})
        
        # Handle application_id (can be set or cleared)
        application_id = body.get('application_id')

        # Check if there are any fields to update
        if name is None and description is None and tags is None and application_id is None:
            return create_response(400, {'error': 'At least one field (name, description, tags, application_id) must be provided'})
        
        # Update timestamp
        now = get_current_timestamp()
        
        # Build update expression
        update_expression, expression_values, expression_names = get_suite_update_expression(
            name=name,
            description=description,
            tags=tags,
            updated_at=now
        )

        # Handle application_id separately (not part of the schema helper)
        if application_id is not None:
            if update_expression:
                update_expression += ', application_id = :application_id'
            else:
                update_expression = 'SET application_id = :application_id'
            expression_values[':application_id'] = application_id
        
        # Update the suite in DynamoDB
        update_kwargs = {
            'Key': {
                'pk': get_test_suites_pk(),
                'sk': get_suite_sk(suite_id)
            },
            'UpdateExpression': update_expression,
            'ExpressionAttributeValues': expression_values,
            'ReturnValues': 'ALL_NEW'
        }
        if expression_names:
            update_kwargs['ExpressionAttributeNames'] = expression_names
        
        update_response = table.update_item(**update_kwargs)
        
        updated_suite = update_response['Attributes']
        
        logger.info(f"Successfully updated test suite {suite_id}")
        
        # Return the updated suite (remove pk/sk from response)
        response_suite = {k: v for k, v in updated_suite.items() if k not in ['pk', 'sk']}
        
        return create_response(200, response_suite)
        
    except Exception as e:
        logger.error(f"Error updating test suite: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
