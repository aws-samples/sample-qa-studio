import json
import logging
from typing import Any, Dict
import boto3
from uuid import uuid4
from utils import get_table_name, create_response, get_current_timestamp, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create a new template in DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with created template
    """
    # Validate scopes - creating templates requires write permission
    user_identity, error = require_scopes(event, ['api/templates.write'])
    if error:
        return error
    
    try:
        # Get user email from identity
        email = user_identity.get('email') or user_identity.get('identity', 'unknown')
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        name = body.get('name')
        description = body.get('description', '')
        category = body.get('category', '')
        tags = body.get('tags', [])
        
        if not name:
            return create_response(400, {'error': 'Missing required field: name'})
        
        # Generate UUID and timestamp
        template_id = str(uuid4())
        now = get_current_timestamp()
        
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Create template item with adjusted pk/sk structure
        # pk = 'TEMPLATES' (for querying all templates)
        # sk = 'TEMPLATE#{id}' (for unique identification)
        template = {
            'pk': 'TEMPLATES',
            'sk': f'TEMPLATE#{template_id}',
            'id': template_id,
            'name': name,
            'description': description,
            'category': category,
            'tags': tags,
            'created_by': email,
            'created_at': now,
            'updated_at': now,
            'version': 1
        }
        
        # Put item in DynamoDB
        table.put_item(Item=template)
        
        return create_response(201, template)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error creating template: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
