import logging
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get use case variables from DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with use case variables
    """
    try:
        # Validate scopes
        user_identity, error_response = require_scopes(event, ['api/usecases.read'])
        if error_response:
            return error_response
        
        # Get use case ID from path parameters
        usecase_id = event.get('pathParameters', {}).get('id')
        if not usecase_id:
            return create_response(400, {'error': 'Missing use case ID'})
        
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get the use case variables
        response = table.get_item(
            Key={
                'pk': f'USECASE#{usecase_id}',
                'sk': 'USECASE_VARIABLES'
            }
        )
        
        item = response.get('Item')
        
        # Return empty variables if none exist
        if not item:
            return create_response(200, {'variables': []})
        
        # Convert keys to lowercase for frontend compatibility
        raw_variables = item.get('variables', [])
        variables = []
        for var in raw_variables:
            if isinstance(var, dict):
                # Handle both uppercase and lowercase keys
                variables.append({
                    'key': var.get('key') or var.get('Key', ''),
                    'value': var.get('value') or var.get('Value', '')
                })
            else:
                variables.append(var)
        
        return create_response(200, {'variables': variables})
        
    except Exception as e:
        logger.error(f"Error getting use case variables: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
