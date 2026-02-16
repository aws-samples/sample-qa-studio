import os
import logging
from typing import Any, Dict
from datetime import datetime
import boto3
from utils import create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get a specific user from Cognito User Pool with their groups.
    Requires api/admin scope.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with user details and groups
    """
    try:
        # Validate scope (requires admin)
        user_identity, error_response = require_scopes(event, ['api/admin'])
        if error_response:
            return error_response
        
        # Get user ID from path parameters
        path_parameters = event.get('pathParameters', {})
        user_id = path_parameters.get('userId')
        
        if not user_id:
            return create_response(400, {'error': 'User ID is required'})
        
        # Get user pool ID from environment
        user_pool_id = os.environ.get('USER_POOL_ID')
        if not user_pool_id:
            logger.error("USER_POOL_ID environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize Cognito client
        cognito_client = boto3.client('cognito-idp')
        
        # Get user details
        try:
            user_response = cognito_client.admin_get_user(
                UserPoolId=user_pool_id,
                Username=user_id
            )
        except cognito_client.exceptions.UserNotFoundException:
            return create_response(404, {'error': 'User not found'})
        
        # Extract attributes
        email = ''
        for attr in user_response.get('UserAttributes', []):
            if attr.get('Name') == 'email':
                email = attr.get('Value', '')
                break
        
        # Get user's groups
        groups = []
        try:
            groups_response = cognito_client.admin_list_groups_for_user(
                UserPoolId=user_pool_id,
                Username=user_id
            )
            groups = [g['GroupName'] for g in groups_response.get('Groups', [])]
        except Exception as e:
            logger.warning(f"Failed to get groups for user {user_id}: {str(e)}")
        
        # Format created date
        created_at = ''
        if 'UserCreateDate' in user_response:
            created_date = user_response['UserCreateDate']
            if isinstance(created_date, datetime):
                created_at = created_date.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        user_obj = {
            'username': user_response.get('Username', ''),
            'email': email,
            'groups': groups,
            'status': user_response.get('UserStatus', ''),
            'enabled': user_response.get('Enabled', True),
            'created_at': created_at
        }
        
        return create_response(200, user_obj)
        
    except Exception as e:
        logger.error(f"Error getting user: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
