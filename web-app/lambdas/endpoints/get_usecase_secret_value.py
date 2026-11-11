"""AWS Lambda handler to get the actual value of a specific usecase secret."""
import logging
from typing import Any, Dict, List, Optional, Tuple
import boto3
from utils import get_secret_prefix, create_response, extract_user_identity
from resource_auth import require_resource_access, usecase_from_path
from permissions_repo import get_usecase_owner
from secret_names import SECRET_KEY_PATTERN, application_secret_name, usecase_secret_name
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _resolve(secrets_client, candidates: List[Tuple[str, str]]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Fetch the first candidate ``(source, secret_name)`` that exists.

    Returns ``(source, response)``; ``('none', None)`` when every candidate is
    missing. Any error other than ResourceNotFound propagates.
    """
    for source, secret_name in candidates:
        try:
            return source, secrets_client.get_secret_value(SecretId=secret_name)
        except secrets_client.exceptions.ResourceNotFoundException:
            continue
    return 'none', None


@require_resource_access('execute', usecase_from_path, scopes=['api/usecases.execute'], allow_worker=True)
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Get the value of a specific secret for a usecase.
    Path: GET /usecase/{id}/secrets/{secret_key}/value
    Scope: api/usecases.execute
    Access: execute on the owning application (Executor+ of the owning team,
    a shared team with an execute grant, a bound M2M client), or the worker
    for its own active execution. Viewers are denied.
    Resolution: the use-case secret first, then the owning application's
    secret of the same key (after authorization, never instead of it).
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

        prefix = get_secret_prefix()
        candidates = [('usecase', usecase_secret_name(prefix, usecase_id, secret_key))]
        application_id = (get_usecase_owner(usecase_id) or {}).get('application_id') or ''
        if application_id:
            candidates.append(('application', application_secret_name(prefix, application_id, secret_key)))

        secrets_client = boto3.client('secretsmanager')
        try:
            source, response = _resolve(secrets_client, candidates)
        except Exception as e:
            logger.error(f"Error retrieving secret value: {str(e)}", exc_info=True)
            return create_response(500, {'error': 'Failed to retrieve secret value'})

        identity = extract_user_identity(event)
        # Access log: who read which key and which layer answered. Never the value.
        logger.info(
            f"secret_value_access: type={identity.get('identity_type')} "
            f"sub={identity.get('sub')} client_id={identity.get('client_id')} "
            f"usecase={usecase_id} key={secret_key} source={source}"
        )

        if response is None:
            return create_response(404, {'error': f"Secret '{secret_key}' not found"})
        secret_value = response.get('SecretString')
        if secret_value is None:
            return create_response(404, {'error': f"Secret '{secret_key}' has no value"})
        return create_response(200, {
            'key': secret_key,
            'value': secret_value,
        })
    except Exception as e:
        logger.error(f"Error in get_usecase_secret_value: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
