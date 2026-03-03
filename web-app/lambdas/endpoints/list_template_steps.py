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
    Lambda handler to list all steps for a specific template from DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with list of template steps
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
        
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Query DynamoDB for all steps of this template
        # Template steps use pk = TEMPLATE#{id} and sk starts with STEP#
        response = table.query(
            KeyConditionExpression=Key('pk').eq(f'TEMPLATE#{template_id}') & Key('sk').begins_with('STEP#')
        )
        
        steps = response.get('Items', [])
        
        # Sort steps by sort field if present
        steps.sort(key=lambda x: x.get('sort', 0))
        
        # Return successful response
        return create_response(200, {'steps': steps})
        
    except Exception as e:
        logger.error(f"Error listing template steps: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
