"""Delete the live-view record for an execution.

Implements R-API-2.  Called by the runner's agentcore browser
provisioner during teardown (both success and failure paths).

Route: ``DELETE /api/usecase/{id}/executions/{executionId}/live-view``
Scope: ``api/executions.write``
Response: ``204`` on success (per 02_api-design.md); ``404`` if the
record was already gone.  Idempotent from the caller's perspective when
treated as "best-effort cleanup" — the runner ignores 404.
"""

from __future__ import annotations

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

    table_name = get_table_name()
    key = {
        'pk': {'S': f'EXECUTION#{execution_id}'},
        'sk': {'S': 'LIVE_VIEW'},
    }

    # Delete conditionally so we can distinguish 404 from 204.
    try:
        _dynamodb.delete_item(
            TableName=table_name,
            Key=key,
            ConditionExpression='attribute_exists(pk)',
        )
    except ClientError as exc:
        code = exc.response.get('Error', {}).get('Code', '')
        if code == 'ConditionalCheckFailedException':
            return create_response(404, {'error': 'Live view not found'})
        return create_response(500, {'error': 'Failed to delete live view'})

    return create_response(204, None)
