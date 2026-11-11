import logging
from typing import Any, Dict, List
import boto3
from utils import get_secret_prefix, create_response, request_log_summary
from resource_auth import require_resource_access, usecase_from_path
from permissions_repo import get_usecase_owner
from secret_names import application_secret_prefix, list_secrets_by_tag, usecase_secret_prefix

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _effective_secrets(secrets_client, prefix: str, usecase_id: str, application_id: str) -> List[Dict[str, str]]:
    """
    Use-case secrets followed by the owning application's secrets whose key is
    not shadowed by a use-case key. Every row carries ``source``.
    """
    rows = [
        {**secret, 'source': 'usecase'}
        for secret in list_secrets_by_tag(
            secrets_client, 'usecase_id', usecase_id, usecase_secret_prefix(prefix, usecase_id))
    ]
    if not application_id:
        return rows
    shadowed = {row['key'] for row in rows}
    rows.extend(
        {**secret, 'source': 'application'}
        for secret in list_secrets_by_tag(
            secrets_client, 'application_id', application_id, application_secret_prefix(prefix, application_id))
        if secret['key'] not in shadowed
    )
    return rows


@require_resource_access('view', usecase_from_path, scopes=['api/usecases.read'], allow_worker=True)
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /usecase/{id}/secrets — the use case's effective secret keys.

    Lists the use case's own secrets plus the inherited application secrets
    (``source: "usecase" | "application"``); a use-case key shadows the
    application key of the same name. Values are never returned.
    """
    try:
        logger.info(f"Received request: {request_log_summary(event)}")
        
        # Get use case ID from path parameters
        usecase_id = event['pathParameters']['id']  # validated by usecase_from_path
        application_id = (get_usecase_owner(usecase_id) or {}).get('application_id') or ''
        
        # Get secret prefix from environment
        prefix = get_secret_prefix()
        
        # Initialize Secrets Manager client
        secrets_client = boto3.client('secretsmanager')
        
        try:
            secrets = _effective_secrets(secrets_client, prefix, usecase_id, application_id)
        except Exception as e:
            logger.error(f"Error listing secrets: {str(e)}", exc_info=True)
            return create_response(500, {'error': 'Failed to list secrets'})
        
        return create_response(200, {'secrets': secrets})
        
    except Exception as e:
        logger.error(f"Error getting use case secrets: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
