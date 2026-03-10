import json
import os
import logging
import secrets
import string
from typing import Any, Dict
import boto3
from utils import create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def generate_secure_password(length: int = 16) -> str:
    """
    Generate a cryptographically secure random password that meets Amazon Cognito requirements.
    Generates a password with at least one uppercase, lowercase, digit, and symbol character.
    """
    # Use symbols that are definitely accepted by Amazon Cognito
    symbols = "!@#$%^&*"
    
    # Include at least one of each required character type
    password_chars = [
        secrets.choice(string.ascii_uppercase),  # At least one uppercase
        secrets.choice(string.ascii_lowercase),  # At least one lowercase
        secrets.choice(string.digits),           # At least one digit
        secrets.choice(symbols),                 # At least one symbol
    ]
    
    # Fill the rest with random characters from all categories
    all_chars = string.ascii_letters + string.digits + symbols
    password_chars.extend(secrets.choice(all_chars) for _ in range(length - 4))
    
    # Shuffle to avoid predictable patterns
    secrets.SystemRandom().shuffle(password_chars)
    
    return ''.join(password_chars)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create a user in Amazon Cognito user pool.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with created user info
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/admin'])
        if error:
            return error
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        email = body.get('email')
        groups = body.get('groups', [])  # Required list of groups to add user to
        
        if not email:
            return create_response(400, {'error': 'Email is required'})
        
        # Validate groups - at least one group is required
        if not groups:
            return create_response(400, {'error': 'At least one group must be specified'})
        
        if not isinstance(groups, list):
            return create_response(400, {'error': 'Groups must be an array'})
        
        valid_groups = ['users', 'admins']
        invalid_groups = [g for g in groups if g not in valid_groups]
        if invalid_groups:
            return create_response(400, {
                'error': f'Invalid groups: {", ".join(invalid_groups)}. Valid groups are: {", ".join(valid_groups)}'
            })
        
        # Get user pool ID from environment
        user_pool_id = os.environ.get('USER_POOL_ID')
        if not user_pool_id:
            logger.error("USER_POOL_ID environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize Amazon Cognito client
        cognito_client = boto3.client('cognito-idp')
        
        # Generate a secure random password
        temporary_password = generate_secure_password(16)
        
        # Create user in Amazon Cognito
        response = cognito_client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'false'}
            ],
            TemporaryPassword=temporary_password
            # Don't set MessageAction - this allows Amazon Cognito to send the default welcome message
        )
        
        user = response.get('User', {})
        username = user.get('Username', '')
        
        # Add user to specified groups (required)
        added_groups = []
        group_errors = []
        for group in groups:
            try:
                logger.info(f"Attempting to add user {username} to group {group}")
                cognito_client.admin_add_user_to_group(
                    UserPoolId=user_pool_id,
                    Username=username,
                    GroupName=group
                )
                added_groups.append(group)
                logger.info(f"✅ Successfully added user {username} to group {group}")
            except cognito_client.exceptions.ResourceNotFoundException as e:
                error_msg = f"Group '{group}' does not exist in user pool"
                logger.error(f"❌ {error_msg}: {str(e)}")
                group_errors.append(error_msg)
            except Exception as e:
                error_msg = f"Failed to add user to group '{group}': {str(e)}"
                logger.error(f"❌ {error_msg}", exc_info=True)
                group_errors.append(error_msg)
        
        # If no groups were added successfully, return error
        if not added_groups and groups:
            return create_response(500, {
                'error': 'Failed to add user to any groups',
                'details': group_errors,
                'username': username
            })
        
        result = {
            'username': username,
            'email': email,
            'status': user.get('UserStatus', ''),
            'groups': added_groups
        }
        
        # Include warnings if some groups failed
        if group_errors:
            result['warnings'] = group_errors
        
        logger.info(f"✅ User creation complete: {username}, groups: {added_groups}")
        return create_response(201, result)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
