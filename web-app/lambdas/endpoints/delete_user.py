import os
import logging
from typing import Any, Dict
from urllib.parse import unquote
import boto3
from utils import create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to delete a user from Amazon Cognito user pool.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/admin'])
        if error:
            return error
        
        # Get username from path parameters
        encoded_username = event.get('pathParameters', {}).get('username')
        if not encoded_username:
            logger.error("Username parameter is required")
            return create_response(400, {'error': 'Username is required'})
        
        # URL decode the username to handle special characters like @
        username = unquote(encoded_username)
        
        # Get user pool ID from environment
        user_pool_id = os.environ.get('USER_POOL_ID')
        if not user_pool_id:
            logger.error("USER_POOL_ID environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize Amazon Cognito client
        cognito_client = boto3.client('cognito-idp')
        
        # Delete user from Amazon Cognito
        cognito_client.admin_delete_user(
            UserPoolId=user_pool_id,
            Username=username
        )
        
        # Return 204 No Content (successful deletion with no body)
        return {
            'statusCode': 204,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            },
            'body': ''
        }
        
    except Exception as e:
        logger.error(f"Error deleting user with username '{encoded_username}': {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Failed to delete user'})
