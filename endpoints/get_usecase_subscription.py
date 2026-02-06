import logging
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import create_response, get_table_name

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
        # Get usecase ID from path
        path_params = event.get('pathParameters', {})
        usecase_id = path_params.get('id')
        
        if not usecase_id:
            return create_response(400, {'error': 'Missing usecase ID'})
        
        # Extract user email from JWT token claims
        request_context = event.get('requestContext', {})
        authorizer = request_context.get('authorizer', {})
        claims = authorizer.get('claims', {})
        user_email = claims.get('email', '')
        
        if not user_email:
            logger.error("No email found in JWT claims")
            return create_response(401, {'error': 'Unauthorized'})
        
        # Initialize DynamoDB
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
