import json
import logging
from typing import Any, Dict
import boto3
from utils import get_secret_prefix, create_response, request_log_summary, aws_error_code
from resource_auth import require_resource_access, usecase_from_path
from secret_names import usecase_secret_name, upsert_secret

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', usecase_from_path, scopes=['api/usecases.write'])
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
        logger.info(f"Received request: {request_log_summary(event)}")
        
        # Get use case ID from path parameters
        usecase_id = event['pathParameters']['id']  # validated by usecase_from_path
        
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
            
            try:
                upsert_secret(
                    secrets_client,
                    usecase_secret_name(prefix, usecase_id, secret_key),
                    secret_value,
                    f"Secret for usecase {usecase_id}",
                    [
                        {'Key': 'usecase_id', 'Value': usecase_id},
                        {'Key': 'managed_by', 'Value': prefix}
                    ],
                )
            except Exception as e:
                logger.error(f"Error creating/updating usecase secret: {aws_error_code(e)}")
                return create_response(500, {'error': f'Failed to create or update secret {secret_key}'})
        
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
