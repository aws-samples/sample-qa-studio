"""Upsert a single runtime variable on an execution.

Implements R-API-1.  Called by the runner once per
``retrieve_value``/``transform`` capture so the UI reflects runtime
variables incrementally rather than only at the end of an execution.

Route: ``POST /api/usecase/{id}/executions/{executionId}/runtime-variables``
Scope: ``api/executions.write``
Body:  ``{"key": string, "value": string | number | bool}``

DynamoDB layout (existing): one item per execution at
``(pk='EXECUTION#{exec}', sk='EXECUTION_VARIABLES')`` with a
``runtime_variables`` map attribute.  Keys inside the map may collide
with DynamoDB reserved words, so we always alias via
``ExpressionAttributeNames``.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

from utils import (
    create_response,
    get_table_name,
    require_scopes,
    validate_path_id,
)

# Module-level client; tests monkeypatch this attribute to inject mocks.
_dynamodb = boto3.client('dynamodb')

_MAX_KEY_LENGTH = 128
_MAX_VALUE_LENGTH = 4096


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # --- Auth --------------------------------------------------------------
    _user_identity, error_response = require_scopes(event, ['api/executions.write'])
    if error_response:
        return error_response

    # --- Path params -------------------------------------------------------
    path = event.get('pathParameters') or {}
    _, error = validate_path_id(path.get('id'), 'usecase ID')
    if error:
        return error
    execution_id, error = validate_path_id(path.get('executionId'), 'execution ID')
    if error:
        return error

    # --- Body --------------------------------------------------------------
    raw_body = event.get('body')
    if not raw_body:
        return create_response(400, {'error': 'Request body is required'})
    try:
        body = json.loads(raw_body)
    except (ValueError, TypeError):
        return create_response(400, {'error': 'Invalid JSON in request body'})
    if not isinstance(body, dict):
        return create_response(400, {'error': 'Request body must be a JSON object'})

    key = body.get('key')
    if not key or not isinstance(key, str):
        return create_response(400, {'error': 'key is required and must be a string'})
    if len(key) > _MAX_KEY_LENGTH:
        return create_response(
            400,
            {'error': f'key exceeds maximum length of {_MAX_KEY_LENGTH} characters'},
        )

    # ``value`` is coerced to a string on storage — runtime variables are
    # resolved via ``{{var}}`` substitution which is string-shaped.
    if 'value' not in body:
        return create_response(400, {'error': 'value is required'})
    raw_value = body['value']
    value = str(raw_value) if raw_value is not None else ''
    if len(value) > _MAX_VALUE_LENGTH:
        return create_response(
            400,
            {'error': f'value exceeds maximum length of {_MAX_VALUE_LENGTH} characters'},
        )

    # --- Verify execution variables record exists --------------------------
    table_name = get_table_name()
    try:
        get_resp = _dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'EXECUTION#{execution_id}'},
                'sk': {'S': 'EXECUTION_VARIABLES'},
            },
        )
    except ClientError:
        return create_response(500, {'error': 'Failed to read execution variables'})

    if 'Item' not in get_resp:
        return create_response(
            404,
            {'error': 'Execution variables record not found'},
        )

    # --- Upsert the variable into the map ---------------------------------
    # First attempt: direct nested-attribute set.  This works when the
    # ``runtime_variables`` map already exists on the record.
    update_kwargs = {
        'TableName': table_name,
        'Key': {
            'pk': {'S': f'EXECUTION#{execution_id}'},
            'sk': {'S': 'EXECUTION_VARIABLES'},
        },
        'UpdateExpression': 'SET runtime_variables.#k = :v',
        'ExpressionAttributeNames': {'#k': key},
        'ExpressionAttributeValues': {':v': {'S': value}},
    }

    try:
        _dynamodb.update_item(**update_kwargs)
    except ClientError as exc:
        code = exc.response.get('Error', {}).get('Code', '')
        if code != 'ValidationException':
            return create_response(500, {'error': 'Failed to update runtime variable'})
        # Fall back: the ``runtime_variables`` map is missing from the
        # record. Initialize it with if_not_exists and set the key.
        try:
            _dynamodb.update_item(
                TableName=table_name,
                Key=update_kwargs['Key'],
                UpdateExpression=(
                    'SET runtime_variables = if_not_exists(runtime_variables, :empty), '
                    'runtime_variables.#k = :v'
                ),
                ExpressionAttributeNames={'#k': key},
                ExpressionAttributeValues={
                    ':empty': {'M': {}},
                    ':v': {'S': value},
                },
            )
        except ClientError:
            return create_response(500, {'error': 'Failed to update runtime variable'})

    return create_response(200, {'status': 'ok', 'key': key})
