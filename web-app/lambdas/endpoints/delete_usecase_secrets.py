import logging
import json
from typing import Any, Dict
import boto3
from botocore.exceptions import ClientError
from utils import create_response, no_content_response, get_secret_prefix, aws_error_code
from resource_auth import require_resource_access, usecase_from_path

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', usecase_from_path, scopes=['api/usecases.write'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to delete a usecase secret.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with deletion result
    """
    try:
        # Get usecase ID from path
        usecase_id = event['pathParameters']['id']  # validated by usecase_from_path
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid request body'})
        
        secret_key = body.get('secret_key', '')
        if not secret_key:
            return create_response(400, {'error': 'secret_key is required'})
        
        # Initialize Secrets Manager client
        secrets_client = boto3.client('secretsmanager')
        
        # Build secret name
        secret_name = f"{get_secret_prefix()}/usecase/{usecase_id}/{secret_key}"
        
        # Delete the secret (with immediate deletion)
        try:
            secrets_client.delete_secret(
                SecretId=secret_name,
                ForceDeleteWithoutRecovery=True
            )
        except ClientError as e:
            logger.error(f"Error deleting usecase secret: {aws_error_code(e)}")
            return create_response(500, {'error': f'Failed to delete secret {secret_key}'})
        
        logger.info(f"Successfully deleted secret {secret_key} for usecase {usecase_id}")
        
        return no_content_response()
        
    except Exception as e:
        logger.error(f"Error deleting secret: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
