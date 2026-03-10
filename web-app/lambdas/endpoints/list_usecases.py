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
    Lambda handler to list all use cases from Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with list of use cases
    """
    logger.info(f"Headers: {event.get('headers', {})}")
    
    try:
        # Validate scope (requires usecases.read or admin)
        user_identity, error_response = require_scopes(event, ['api/usecases.read'])
        if error_response:
            return error_response
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Query Amazon DynamoDB for all use cases
        response = table.query(
            KeyConditionExpression=Key('pk').eq('USECASES') & Key('sk').begins_with('USECASE#')
        )
        
        usecases = response.get('Items', [])
        
        # Return successful response
        return create_response(200, {'usecases': usecases})
        
    except Exception as e:
        logger.error(f"Error listing use cases: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
