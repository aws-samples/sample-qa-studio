import logging
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import get_table_name, create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to delete a template and all its associated items from DynamoDB.
    
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
        template_id = event.get('pathParameters', {}).get('id')
        if not template_id:
            return create_response(400, {'error': 'Missing template ID'})
        
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Query all items for this template with adjusted pk/sk structure
        # First get the main template record
        response = table.get_item(
            Key={
                'pk': 'TEMPLATES',
                'sk': f'TEMPLATE#{template_id}'
            }
        )
        
        if not response.get('Item'):
            return create_response(404, {'error': 'Template not found'})
        
        # Delete the template record
        table.delete_item(
            Key={
                'pk': 'TEMPLATES',
                'sk': f'TEMPLATE#{template_id}'
            }
        )
        
        # Also query and delete any related items (steps, variables) with old structure
        # This handles templates that might still use the old TEMPLATE#{id} pk structure
        old_structure_response = table.query(
            KeyConditionExpression=Key('pk').eq(f'TEMPLATE#{template_id}')
        )
        
        old_items = old_structure_response.get('Items', [])
        
        # Delete old structure items in batches if they exist
        if old_items:
            with table.batch_writer() as batch:
                for item in old_items:
                    batch.delete_item(
                        Key={
                            'pk': item['pk'],
                            'sk': item['sk']
                        }
                    )
        
        return create_response(200, {'message': 'Template deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting template: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
