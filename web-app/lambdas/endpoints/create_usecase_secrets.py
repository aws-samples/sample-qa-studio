import json
import logging
from typing import Any, Dict
import boto3
from botocore.exceptions import ClientError
from utils import get_secret_prefix, create_response, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create or update use case secrets in AWS Secrets Manager.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        # Validate scopes
        user_identity, error_response = require_scopes(event, ['api/usecases.write'])
        if error_response:
            return error_response
        
        logger.info(f"Received request: {event}")
        
        # Get use case ID from path parameters
        usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        secrets = body.get('secrets', [])
        
        # Get secret prefix from environment
        prefix = get_secret_prefix()
        
        # Initialize Secrets Manager client
        secrets_client = boto3.client('secretsmanager')
        
        # Create or update secrets
        for secret in secrets:
            secret_key = secret.get('key')
            secret_value = secret.get('value')
            
            if not secret_key or not secret_value:
                continue
            
            secret_name = f"{prefix}/usecase/{usecase_id}/{secret_key}"
            
            try:
                # Try to create the secret first
                secrets_client.create_secret(
                    Name=secret_name,
                    SecretString=secret_value,
                    Description=f"Secret for usecase {usecase_id}",
                    Tags=[
                        {'Key': 'usecase_id', 'Value': usecase_id},
                        {'Key': 'managed_by', 'Value': prefix}
                    ]
                )
            except ClientError as e:
                # If secret already exists, update it
                if e.response['Error']['Code'] == 'ResourceExistsException':
                    try:
                        secrets_client.update_secret(
                            SecretId=secret_name,
                            SecretString=secret_value
                        )
                    except Exception as update_err:
                        logger.error(f"Error updating secret {secret_name}: {str(update_err)}")
                        return create_response(500, {'error': f'Failed to update secret {secret_key}'})
                else:
                    logger.error(f"Error creating secret {secret_name}: {str(e)}")
                    return create_response(500, {'error': f'Failed to create secret {secret_key}'})
        
        return create_response(200, {
            'message': 'Secrets created/updated successfully',
            'count': len(secrets)
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error creating use case secrets: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
