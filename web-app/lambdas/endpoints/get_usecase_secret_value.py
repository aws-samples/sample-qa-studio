"""AWS Lambda handler to get the actual value of a specific usecase secret."""
import logging
import re
from typing import Any, Dict
import boto3
from utils import get_secret_prefix, create_response, extract_user_identity
from resource_auth import require_resource_access, usecase_from_path
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Secret keys become part of the Secrets Manager name; keep them to a safe charset.
SECRET_KEY_PATTERN = re.compile(r'^[A-Za-z0-9_.-]{1,128}$')


@require_resource_access('execute', usecase_from_path, scopes=['api/usecases.execute'], allow_worker=True)
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Get the value of a specific secret for a usecase.
    Path: GET /usecase/{id}/secrets/{secret_key}/value
    Scope: api/usecases.execute
    Access: execute on the owning application (Executor+ of the owning team,
    a shared team with an execute grant, a bound M2M client), or the worker
    for its own active execution. Viewers are denied.
    Returns the decrypted secret value from AWS Secrets Manager.
    """
    try:
        path_params = event.get('pathParameters') or {}
        usecase_id = path_params['id']  # validated by usecase_from_path
        secret_key = path_params.get('secret_key')
        if not secret_key:
            return create_response(400, {'error': 'Missing secret key'})
        if not SECRET_KEY_PATTERN.match(secret_key):
            return create_response(400, {'error': 'Invalid secret key'})

        identity = extract_user_identity(event)
        # Access log: who read which key. Never the value.
        logger.info(
            f"secret_value_access: type={identity.get('identity_type')} "
            f"sub={identity.get('sub')} client_id={identity.get('client_id')} "
            f"usecase={usecase_id} key={secret_key}"
        )

        prefix = get_secret_prefix()
        secret_name = f"{prefix}/usecase/{usecase_id}/{secret_key}"
        secrets_client = boto3.client('secretsmanager')
        try:
            response = secrets_client.get_secret_value(SecretId=secret_name)
            secret_value = response.get('SecretString')
            if secret_value is None:
                return create_response(404, {'error': f"Secret '{secret_key}' has no value"})
            return create_response(200, {
                'key': secret_key,
                'value': secret_value,
            })
        except secrets_client.exceptions.ResourceNotFoundException:
            return create_response(404, {'error': f"Secret '{secret_key}' not found"})
        except Exception as e:
            logger.error(f"Error retrieving secret value: {str(e)}", exc_info=True)
            return create_response(500, {'error': 'Failed to retrieve secret value'})
    except Exception as e:
        logger.error(f"Error in get_usecase_secret_value: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
