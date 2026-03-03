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
    Lambda handler to list users from Cognito User Pool with their groups.
    Requires api/admin scope.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with list of users and their groups
    """
    try:
        # Validate scope (requires admin)
        user_identity, error_response = require_scopes(event, ['api/admin'])
        if error_response:
            return error_response
        
        # Get user pool ID from environment
        user_pool_id = os.environ.get('USER_POOL_ID')
        if not user_pool_id:
            logger.error("USER_POOL_ID environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize Cognito client
        cognito_client = boto3.client('cognito-idp')
        
        # List users from Cognito User Pool
        users = []
        pagination_token = None
        
        while True:
            if pagination_token:
                response = cognito_client.list_users(
                    UserPoolId=user_pool_id,
                    PaginationToken=pagination_token
                )
            else:
                response = cognito_client.list_users(UserPoolId=user_pool_id)
            
            # Format users
            for user in response.get('Users', []):
                username = user.get('Username', '')
                
                # Extract attributes
                attributes = {}
                email = ''
                for attr in user.get('Attributes', []):
                    attr_name = attr.get('Name', '')
                    attr_value = attr.get('Value', '')
                    attributes[attr_name] = attr_value
                    
                    if attr_name == 'email':
                        email = attr_value
                
                # Get user's groups
                groups = []
                try:
                    groups_response = cognito_client.admin_list_groups_for_user(
                        UserPoolId=user_pool_id,
                        Username=username
                    )
                    groups = [g['GroupName'] for g in groups_response.get('Groups', [])]
                except Exception as e:
                    logger.warning(f"Failed to get groups for user {username}: {str(e)}")
                
                # Format created date
                created_at = ''
                if 'UserCreateDate' in user:
                    created_date = user['UserCreateDate']
                    if isinstance(created_date, datetime):
                        created_at = created_date.strftime('%Y-%m-%dT%H:%M:%SZ')
                
                user_obj = {
                    'username': username,
                    'email': email,
                    'groups': groups,
                    'status': user.get('UserStatus', ''),
                    'enabled': user.get('Enabled', False),
                    'created_at': created_at
                }
                
                users.append(user_obj)
            
            pagination_token = response.get('PaginationToken')
            if not pagination_token:
                break
        
        return create_response(200, {'users': users})
        
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
