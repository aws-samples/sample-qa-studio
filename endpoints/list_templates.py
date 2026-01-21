import logging
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import get_table_name, create_response

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to list all templates from DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with list of templates
    """
    try:
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Query DynamoDB for all templates
        response = table.query(
            KeyConditionExpression=Key('pk').eq('TEMPLATES') & Key('sk').begins_with('TEMPLATE#')
        )
        
        templates = response.get('Items', [])
        
        # Return successful response
        return create_response(200, {'templates': templates})
        
    except Exception as e:
        logger.error(f"Error listing templates: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
