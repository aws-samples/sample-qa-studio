import logging
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import create_response, get_table_name, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to check if user is subscribed to usecase notifications.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with subscription status
    """
    try:
        # Validate scopes (read permission to check subscription status)
        user_identity, error_response = require_scopes(event, ['api/usecases.read'])
        if error_response:
            return error_response
        
        # Get user email from identity (fallback to username if no email)
        user_email = user_identity.get('email') or user_identity.get('identity', 'unknown')
        
        # Get usecase ID from path
        path_params = event.get('pathParameters', {})
        usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        
        # Initialize Amazon DynamoDB
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Query for subscription records for this user and usecase
        response = table.query(
            KeyConditionExpression=Key('pk').eq(f'USECASE#{usecase_id}') & Key('sk').begins_with('NOTIFICATION#'),
            FilterExpression='email = :email',
            ExpressionAttributeValues={
                ':email': user_email
            },
            Limit=1  # We only need to know if at least one exists
        )
        
        is_subscribed = len(response.get('Items', [])) > 0
        
        return create_response(200, {
            'is_subscribed': is_subscribed,
            'email': user_email
        })
        
    except Exception as e:
        logger.error(f"Error checking subscription: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
