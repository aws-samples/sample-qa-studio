import logging
from typing import Any, Dict, List
from datetime import datetime
import boto3
from utils import get_secret_prefix, create_response, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get use case secrets from AWS Secrets Manager.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with list of secrets
    """
    try:
        # Validate scopes
        user_identity, error_response = require_scopes(event, ['api/usecases.read'])
        if error_response:
            return error_response
        
        logger.info(f"Received request: {event}")
        
        # Get use case ID from path parameters
        usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        
        # Get secret prefix from environment
        prefix = get_secret_prefix()
        
        # Initialize Secrets Manager client
        secrets_client = boto3.client('secretsmanager')
        
        # List secrets with the usecase tag
        try:
            response = secrets_client.list_secrets(
                Filters=[
                    {
                        'Key': 'tag-key',
                        'Values': ['usecase_id']
                    },
                    {
                        'Key': 'tag-value',
                        'Values': [usecase_id]
                    }
                ]
            )
        except Exception as e:
            logger.error(f"Error listing secrets: {str(e)}", exc_info=True)
            return create_response(500, {'error': 'Failed to list secrets'})
        
        # Filter and format secrets
        secrets = []
        secret_prefix = f"{prefix}/usecase/{usecase_id}/"
        
        for secret in response.get('SecretList', []):
            secret_name = secret.get('Name', '')
            
            if secret_name.startswith(secret_prefix):
                # Extract the key name from the secret name
                key_name = secret_name[len(secret_prefix):]
                
                # Format created date
                created_at = ''
                if 'CreatedDate' in secret:
                    created_date = secret['CreatedDate']
                    if isinstance(created_date, datetime):
                        created_at = created_date.strftime('%Y-%m-%dT%H:%M:%SZ')
                
                secret_info = {
                    'key': key_name,
                    'secret_name': secret_name,
                    'description': secret.get('Description', ''),
                    'created_at': created_at
                }
                
                secrets.append(secret_info)
        
        return create_response(200, {'secrets': secrets})
        
    except Exception as e:
        logger.error(f"Error getting use case secrets: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
