import json
import logging
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response, get_current_timestamp, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to update a template in Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/templates.write'])
        if error:
            return error
        
        # Get template ID from path parameters
        template_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        name = body.get('name')
        description = body.get('description')
        category = body.get('category')
        tags = body.get('tags')
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Build update expression
        now = get_current_timestamp()
        
        # Update the template with adjusted pk/sk structure
        response = table.update_item(
            Key={
                'pk': 'TEMPLATES',
                'sk': f'TEMPLATE#{template_id}'
            },
            UpdateExpression='SET #name = :name, #desc = :desc, category = :category, tags = :tags, updated_at = :updated_at ADD version :inc',
            ExpressionAttributeNames={
                '#name': 'name',
                '#desc': 'description'
            },
            ExpressionAttributeValues={
                ':name': name,
                ':desc': description,
                ':category': category,
                ':tags': tags,
                ':updated_at': now,
                ':inc': 1
            },
            ReturnValues='ALL_NEW'
        )
        
        updated_item = response.get('Attributes', {})
        
        return create_response(200, {
            'message': 'Template updated successfully',
            'template': updated_item
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error updating template: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
