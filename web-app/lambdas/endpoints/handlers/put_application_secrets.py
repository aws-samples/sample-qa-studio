import lambda_init  # noqa: F401 — must be first import (pydantic)
import json
import logging
from typing import Any, Dict, List
import boto3
from pydantic import BaseModel, ValidationError, field_validator
from resource_auth import require_resource_access, app_from_path
from secret_names import SECRET_KEY_PATTERN, application_secret_name, upsert_secret
from utils import aws_error_code, create_response, get_secret_prefix, request_log_summary

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class ApplicationSecretEntry(BaseModel):
    """One ``{key, value}`` pair of the POST body."""
    key: str
    value: str

    @field_validator('key')
    @classmethod
    def _key_charset(cls, key: str) -> str:
        if not SECRET_KEY_PATTERN.match(key):
            raise ValueError('Invalid secret key')
        return key

    @field_validator('value')
    @classmethod
    def _value_not_empty(cls, value: str) -> str:
        # Secrets Manager rejects SecretString='' (ParamValidationError), so an
        # empty value can never be stored; fail the request up front.
        if not value:
            raise ValueError('value must not be empty')
        return value


class ApplicationSecretsRequest(BaseModel):
    """POST /applications/{id}/secrets body."""
    secrets: List[ApplicationSecretEntry]

    @field_validator('secrets')
    @classmethod
    def _non_empty_unique(cls, secrets: List[ApplicationSecretEntry]) -> List[ApplicationSecretEntry]:
        if not secrets:
            raise ValueError('secrets must be a non-empty list')
        keys = [s.key for s in secrets]
        if len(set(keys)) != len(keys):
            raise ValueError('Duplicate secret key')
        return secrets


def _validation_message(error: ValidationError) -> str:
    first = error.errors()[0]
    message = first['msg']
    # Pydantic prefixes messages raised from validators with "Value error, ".
    if message.startswith('Value error, '):
        return message[len('Value error, '):]
    field = '.'.join(str(p) for p in first['loc'])
    return f'Invalid value for {field}'


@require_resource_access('edit', app_from_path, scopes=['api/applications.write'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /applications/{id}/secrets — create or update application secrets.

    Body ``{secrets: [{key, value}]}``. Every entry is validated before the
    first write so a bad entry never leaves a partial result. Returns
    ``201 {created: [keys], updated: [keys]}``. Values are never logged.
    """
    logger.info(f"Received request: {request_log_summary(event)}")
    app_id = event['pathParameters']['id']  # validated by app_from_path

    try:
        request = ApplicationSecretsRequest(**json.loads(event.get('body') or '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except ValidationError as e:
        return create_response(400, {'error': _validation_message(e)})

    prefix = get_secret_prefix()
    secrets_client = boto3.client('secretsmanager')
    tags = [
        {'Key': 'application_id', 'Value': app_id},
        {'Key': 'managed_by', 'Value': prefix},
    ]
    result: Dict[str, List[str]] = {'created': [], 'updated': []}
    for secret in request.secrets:
        try:
            outcome = upsert_secret(
                secrets_client,
                application_secret_name(prefix, app_id, secret.key),
                secret.value,
                f"Secret for application {app_id}",
                tags,
            )
        except Exception as e:
            logger.error(f"Error creating/updating application secret: {aws_error_code(e)}")
            return create_response(500, {'error': f'Failed to create or update secret {secret.key}'})
        result[outcome].append(secret.key)

    logger.info(f"Application {app_id} secrets: created={len(result['created'])} updated={len(result['updated'])}")
    return create_response(201, result)
