import os
import json
import logging
from typing import Any, Dict
import boto3
from utils import create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Valid Amazon Cognito groups
VALID_GROUPS = ['users', 'admins']


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to update a user's group membership in Amazon Cognito user pool.
    Requires api/admin scope.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with updated user groups
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
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})
        
        new_groups = body.get('groups', [])
        
        # Validate groups
        if not isinstance(new_groups, list):
            return create_response(400, {'error': 'Groups must be an array'})
        
        invalid_groups = [g for g in new_groups if g not in VALID_GROUPS]
        if invalid_groups:
            return create_response(400, {
                'error': f'Invalid groups: {", ".join(invalid_groups)}',
                'valid_groups': VALID_GROUPS
            })
        
        # Get user pool ID from environment
        user_pool_id = os.environ.get('USER_POOL_ID')
        if not user_pool_id:
            logger.error("USER_POOL_ID environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize Amazon Cognito client
        cognito_client = boto3.client('cognito-idp')
        
        # Verify user exists
        try:
            cognito_client.admin_get_user(
                UserPoolId=user_pool_id,
                Username=user_id
            )
        except cognito_client.exceptions.UserNotFoundException:
            return create_response(404, {'error': 'User not found'})
        
        # Get current groups
        try:
            current_groups_response = cognito_client.admin_list_groups_for_user(
                UserPoolId=user_pool_id,
                Username=user_id
            )
            current_groups = [g['GroupName'] for g in current_groups_response.get('Groups', [])]
        except Exception as e:
            logger.error(f"Failed to get current groups: {str(e)}")
            return create_response(500, {'error': 'Failed to get current groups'})
        
        # Remove user from old groups
        for group in current_groups:
            if group not in new_groups:
                try:
                    cognito_client.admin_remove_user_from_group(
                        UserPoolId=user_pool_id,
                        Username=user_id,
                        GroupName=group
                    )
                    logger.info(f"Removed user {user_id} from group {group}")
                except Exception as e:
                    logger.error(f"Failed to remove user from group {group}: {str(e)}")
        
        # Add user to new groups
        for group in new_groups:
            if group not in current_groups:
                try:
                    cognito_client.admin_add_user_to_group(
                        UserPoolId=user_pool_id,
                        Username=user_id,
                        GroupName=group
                    )
                    logger.info(f"Added user {user_id} to group {group}")
                except Exception as e:
                    logger.error(f"Failed to add user to group {group}: {str(e)}")
                    return create_response(500, {'error': f'Failed to add user to group {group}'})
        
        result = {
            'username': user_id,
            'groups': new_groups,
            'message': 'User groups updated successfully'
        }
        
        return create_response(200, result)
        
    except Exception as e:
        logger.error(f"Error updating user groups: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
