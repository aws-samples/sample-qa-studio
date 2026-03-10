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
    Lambda handler to create or update template variables in Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with created variables
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
        variables = body.get('variables', [])
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Create timestamp
        now = get_current_timestamp()
        
        # Create template variables item
        template_vars = {
            'pk': f'TEMPLATE#{template_id}',
            'sk': 'VARIABLES',
            'variables': variables,
            'created_at': now
        }
        
        # Put item in DynamoDB
        table.put_item(Item=template_vars)
        
        return create_response(201, template_vars)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error creating template variables: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
