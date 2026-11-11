import json
import logging
from typing import Any, Dict
import boto3
from botocore.exceptions import ClientError
from resource_auth import require_resource_access, app_from_path
from secret_names import SECRET_KEY_PATTERN, application_secret_name
from utils import aws_error_code, create_response, get_secret_prefix, no_content_response, request_log_summary

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', app_from_path, scopes=['api/applications.write'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    DELETE /applications/{id}/secrets — delete one application secret.

    Body ``{secret_key}`` (same shape as ``DELETE /usecase/{id}/secrets`` so the
    frontend adapter is shared). Deletes without a recovery window; ``204``.
    """
    logger.info(f"Received request: {request_log_summary(event)}")
    app_id = event['pathParameters']['id']  # validated by app_from_path

    try:
        body = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid request body'})
    secret_key = body.get('secret_key', '') if isinstance(body, dict) else ''
    if not secret_key or not isinstance(secret_key, str):
        return create_response(400, {'error': 'secret_key is required'})
    if not SECRET_KEY_PATTERN.match(secret_key):
        return create_response(400, {'error': 'Invalid secret key'})

    secrets_client = boto3.client('secretsmanager')
    try:
        secrets_client.delete_secret(
            SecretId=application_secret_name(get_secret_prefix(), app_id, secret_key),
            ForceDeleteWithoutRecovery=True,
        )
    except ClientError as e:
        if aws_error_code(e) == 'ResourceNotFoundException':
            return create_response(404, {'error': f"Secret '{secret_key}' not found"})
        logger.error(f"Error deleting application secret: {aws_error_code(e)}")
        return create_response(500, {'error': f'Failed to delete secret {secret_key}'})

    logger.info(f"Deleted secret {secret_key} for application {app_id}")
    return no_content_response()
