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
    no_content_response,
    get_table_name,
    validate_path_id,
)
from resource_auth import require_resource_access, execution_from_path

_dynamodb = boto3.client('dynamodb')


@require_resource_access('execute', execution_from_path, scopes=['api/executions.write'], allow_worker=True)
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # --- Path params -------------------------------------------------------
    path = event.get('pathParameters') or {}
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

    return no_content_response()
