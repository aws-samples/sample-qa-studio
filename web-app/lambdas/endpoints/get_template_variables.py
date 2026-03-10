import logging
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get template variables from Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with template variables
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/templates.read'])
        if error:
            return error
        
        # Get template ID from path parameters
        template_id = event.get('pathParameters', {}).get('id')
        if not template_id:
            return create_response(400, {'error': 'Missing template ID'})
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get the template variables
        response = table.get_item(
            Key={
                'pk': f'TEMPLATE#{template_id}',
                'sk': 'VARIABLES'
            }
        )
        
        template_vars = response.get('Item')
        
        # Return empty variables if none exist
        if not template_vars:
            template_vars = {
                'variables': []
            }
        
        return create_response(200, template_vars)
        
    except Exception as e:
        logger.error(f"Error getting template variables: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
