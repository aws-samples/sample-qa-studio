import logging
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get a specific template from DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with template data
    """
    try:
        # Get template ID from path parameters
        template_id = event.get('pathParameters', {}).get('id')
        if not template_id:
            return create_response(400, {'error': 'Missing template ID'})
        
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get the template with adjusted pk/sk structure
        response = table.get_item(
            Key={
                'pk': 'TEMPLATES',
                'sk': f'TEMPLATE#{template_id}'
            }
        )
        
        template = response.get('Item')
        
        if not template:
            return create_response(404, {'error': 'Template not found'})
        
        return create_response(200, template)
        
    except Exception as e:
        logger.error(f"Error getting template: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
