"""Return the custom HTTP headers configured for an execution.

Implements R-API-4.  Called by the CLI runner to fetch the headers the
frontend stored when the execution was created, so the runner can set
them via ``nova.page.set_extra_http_headers`` before navigation.

Route: ``GET /api/usecase/{id}/executions/{executionId}/headers``
Scope: ``api/executions.read``

Returns ``{"headers": {...}}`` always — an empty object when no headers
record exists (the runner treats "none" and "empty" identically).
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
    _user_identity, error_response = require_scopes(event, ['api/executions.read'])
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

    # --- Read --------------------------------------------------------------
    table_name = get_table_name()
    try:
        response = _dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'EXECUTION#{execution_id}'},
                'sk': {'S': 'HEADERS'},
            },
        )
    except ClientError:
        return create_response(500, {'error': 'Failed to read execution headers'})

    item = response.get('Item') or {}
    headers_attr = item.get('headers') or {}
    headers_map = headers_attr.get('M') or {} if isinstance(headers_attr, dict) else {}
    # DynamoDB returns M typed values ({'S': 'value'}); unwrap to plain dict.
    headers = {k: v.get('S', '') for k, v in headers_map.items() if isinstance(v, dict)}

    return create_response(200, {'headers': headers})
