import json
import os
import logging
import secrets
import string
from typing import Any, Dict
import boto3
from utils import create_response

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def generate_secure_password(length: int = 16) -> str:
    """
    Generate a cryptographically secure random password that meets Cognito requirements.
    Ensures at least one uppercase, lowercase, digit, and symbol character.
    """
    # Use symbols that are definitely accepted by Cognito
    symbols = "!@#$%^&*"
    
    # Ensure we have at least one of each required character type
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
    Lambda handler to create a user in Cognito User Pool.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with created user info
    """
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        email = body.get('email')
        
        if not email:
            return create_response(400, {'error': 'Email is required'})
        
        # Get user pool ID from environment
        user_pool_id = os.environ.get('USER_POOL_ID')
        if not user_pool_id:
            logger.error("USER_POOL_ID environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize Cognito client
        cognito_client = boto3.client('cognito-idp')
        
        # Generate a secure random password
        temporary_password = generate_secure_password(16)
        
        # Create user in Cognito
        response = cognito_client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'false'}
            ],
            TemporaryPassword=temporary_password
            # Don't set MessageAction - this allows Cognito to send the default welcome message
        )
        
        user = response.get('User', {})
        
        result = {
            'username': user.get('Username', ''),
            'email': email,
            'status': user.get('UserStatus', '')
        }
        
        return create_response(201, result)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
