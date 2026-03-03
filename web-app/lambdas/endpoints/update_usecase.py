import json
import logging
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to update a use case in DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        # Validate scope (requires usecases.write or admin)
        user_identity, error_response = require_scopes(event, ['api/usecases.write'])
        if error_response:
            return error_response
        
        # Get use case ID from path parameters
        usecase_id = event.get('pathParameters', {}).get('id')
        if not usecase_id:
            return create_response(400, {'error': 'Missing use case ID'})
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        name = body.get('name')
        description = body.get('description')
        starting_url = body.get('starting_url')
        active = body.get('active')
        executing_region = body.get('executing_region', '').strip()
        # Use default region if empty
        if not executing_region:
            import os
            executing_region = os.environ.get('DEFAULT_REGION', 'us-east-1')
        model_id = body.get('model_id', '')
        tags = body.get('tags', [])
        
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Build update expression dynamically
        update_expression_parts = []
        expression_attribute_values = {}
        expression_attribute_names = {
            '#name': 'name'
        }
        
        # Always update these fields
        update_expression_parts.append('#name = :name')
        update_expression_parts.append('description = :description')
        update_expression_parts.append('starting_url = :starting_url')
        update_expression_parts.append('active = :active')
        update_expression_parts.append('executing_region = :executing_region')
        
        expression_attribute_values[':name'] = name
        expression_attribute_values[':description'] = description
        expression_attribute_values[':starting_url'] = starting_url
        expression_attribute_values[':active'] = active
        expression_attribute_values[':executing_region'] = executing_region
        
        # Update model_id if provided
        if model_id:
            update_expression_parts.append('model_id = :model_id')
            expression_attribute_values[':model_id'] = model_id
        
        # Only update tags if provided and not empty (DynamoDB String Sets cannot be empty)
        if tags:
            update_expression_parts.append('tags = :tags')
            expression_attribute_values[':tags'] = set(tags)  # Convert to set for DynamoDB
        
        update_expression = 'SET ' + ', '.join(update_expression_parts)
        
        # Update the use case
        table.update_item(
            Key={
                'pk': 'USECASES',
                'sk': f'USECASE#{usecase_id}'
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values
        )
        
        return create_response(200, {
            'status': 'usecase updated',
            'usecaseId': usecase_id
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error updating use case: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
