"""AWS Lambda handler to get the actual value of a specific usecase secret."""

import logging
from typing import Any, Dict
import boto3
from utils import get_secret_prefix, create_response, require_scopes, validate_path_id

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Get the value of a specific secret for a usecase.

    Path: GET /usecase/{id}/secrets/{secret_key}/value
    Scope: api/usecases.read

    Returns the decrypted secret value from AWS Secrets Manager.
    """
    try:
        user_identity, error_response = require_scopes(event, ['api/usecases.read'])
        if error_response:
            return error_response

        usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        secret_key = event.get('pathParameters', {}).get('secret_key')

        if not secret_key:
            return create_response(400, {'error': 'Missing secret key'})

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
