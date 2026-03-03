import logging
import json
from typing import Any, Dict
import boto3
from botocore.exceptions import ClientError
from utils import create_response, get_secret_prefix, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to update a usecase secret value.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with update confirmation
    """
    try:
        # Validate scopes
        user_identity, error_response = require_scopes(event, ['api/usecases.write'])
        if error_response:
            return error_response
        
        logger.info(f"Received request: {event}")
        
        # Get usecase ID from path
        path_params = event.get('pathParameters', {})
        usecase_id = path_params.get('id')
        
        if not usecase_id:
            return create_response(400, {'error': 'usecase ID is required'})
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid request body'})
        
        secret_key = body.get('secret_key', '')
        value = body.get('value', '')
        
        if not secret_key or not value:
            return create_response(400, {'error': 'secret_key and value are required'})
        
        # Initialize Secrets Manager client
        secrets_client = boto3.client('secretsmanager')
        
        secret_name = f"{get_secret_prefix()}/usecase/{usecase_id}/{secret_key}"
        
        # Update the secret value
        try:
            secrets_client.update_secret(
                SecretId=secret_name,
                SecretString=value
            )
        except ClientError as e:
            logger.error(f"Error updating secret {secret_name}: {str(e)}")
            return create_response(500, {'error': f'Failed to update secret {secret_key}'})
        
        logger.info(f"Successfully updated secret {secret_key} for usecase {usecase_id}")
        
        return create_response(200, {
            'message': 'Secret updated successfully',
            'secret_key': secret_key
        })
        
    except Exception as e:
        logger.error(f"Error updating usecase secret: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
