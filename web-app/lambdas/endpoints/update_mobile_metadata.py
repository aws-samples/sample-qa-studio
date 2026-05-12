"""Update mobile metadata on an execution record.

Implements R-API-3.  Called by the CLI runner during and after a mobile
Device Farm session so the frontend can show the session ARN and device
details.

Route: ``PATCH /api/usecase/{id}/executions/{executionId}/mobile-metadata``
Scope: ``api/executions.write``
Body:  one or more of ``device_farm_session_arn``, ``device_name``,
       ``device_os_version`` (all optional strings).

DynamoDB item: ``(pk='USECASE_EXECUTION#{uc}', sk='EXECUTION#{exec}')``.
Only fields that are present in the body are updated.  Missing fields are
untouched (not cleared).  Empty body is a no-op 200.
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

_dynamodb = boto3.client('dynamodb')

# Fields the runner may set.  Keep the list closed; other attributes on
# the execution record are owned by other endpoints.
_ALLOWED_FIELDS = (
    'device_farm_session_arn',
    'device_name',
    'device_os_version',
)
_MAX_VALUE_LENGTH = 512
_DEVICE_FARM_ARN_PREFIX = 'arn:aws:devicefarm:'


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # --- Auth --------------------------------------------------------------
    _user_identity, error_response = require_scopes(event, ['api/executions.write'])
    if error_response:
        return error_response

    # --- Path params -------------------------------------------------------
    path = event.get('pathParameters') or {}
    usecase_id, error = validate_path_id(path.get('id'), 'usecase ID')
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

    # Collect allowed fields that are actually present (and non-empty).
    updates: Dict[str, str] = {}
    for field in _ALLOWED_FIELDS:
        if field not in body:
            continue
        value = body[field]
        if value is None:
            continue
        if not isinstance(value, str):
            return create_response(400, {'error': f'{field} must be a string'})
        if len(value) > _MAX_VALUE_LENGTH:
            return create_response(
                400,
                {'error': f'{field} exceeds maximum length of {_MAX_VALUE_LENGTH}'},
            )
        updates[field] = value

    # Reject unknown keys so callers don't silently set arbitrary
    # attributes. Field names not in _ALLOWED_FIELDS produce 400.
    unknown = [k for k in body.keys() if k not in _ALLOWED_FIELDS]
    if unknown:
        return create_response(
            400,
            {'error': f'Unknown fields: {", ".join(sorted(unknown))}'},
        )

    if not updates:
        return create_response(400, {'error': 'At least one field is required'})

    # Validate the ARN format if supplied.
    arn = updates.get('device_farm_session_arn')
    if arn and not arn.startswith(_DEVICE_FARM_ARN_PREFIX):
        return create_response(
            400,
            {'error': 'device_farm_session_arn must be a Device Farm ARN'},
        )

    # --- Write -------------------------------------------------------------
    table_name = get_table_name()
    set_parts = []
    expression_values: Dict[str, Any] = {}
    for i, (field, value) in enumerate(updates.items()):
        placeholder = f':v{i}'
        set_parts.append(f'{field} = {placeholder}')
        expression_values[placeholder] = {'S': value}

    try:
        _dynamodb.update_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                'sk': {'S': f'EXECUTION#{execution_id}'},
            },
            UpdateExpression='SET ' + ', '.join(set_parts),
            ExpressionAttributeValues=expression_values,
            ConditionExpression='attribute_exists(pk)',
        )
    except ClientError as exc:
        code = exc.response.get('Error', {}).get('Code', '')
        if code == 'ConditionalCheckFailedException':
            return create_response(404, {'error': 'Execution not found'})
        return create_response(500, {'error': 'Failed to update mobile metadata'})

    return create_response(200, {'status': 'ok', 'updated_fields': sorted(updates.keys())})
