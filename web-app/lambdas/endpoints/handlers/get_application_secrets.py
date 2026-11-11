import logging
from typing import Any, Dict
import boto3
from resource_auth import require_resource_access, app_from_path
from secret_names import application_secret_prefix, list_secrets_by_tag
from utils import create_response, get_secret_prefix, request_log_summary

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('view', app_from_path, scopes=['api/applications.read'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /applications/{id}/secrets — list the application's secret keys.

    Secrets are listed from Secrets Manager by the ``application_id`` tag and
    the ``{prefix}/application/{id}/`` name prefix; values are never returned.
    """
    logger.info(f"Received request: {request_log_summary(event)}")
    app_id = event['pathParameters']['id']  # validated by app_from_path
    prefix = get_secret_prefix()
    secrets_client = boto3.client('secretsmanager')
    try:
        secrets = list_secrets_by_tag(
            secrets_client, 'application_id', app_id, application_secret_prefix(prefix, app_id))
    except Exception as e:
        logger.error(f"Error listing application secrets: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Failed to list secrets'})
    return create_response(200, {'secrets': secrets})
