"""Create the live-view record for an execution.

Implements R-API-2.  Called by the runner's agentcore browser
provisioner after ``start_browser`` returns a CloudFront live-view URL.

Route: ``POST /api/usecase/{id}/executions/{executionId}/live-view``
Scope: ``api/executions.write``
Body:  ``{"live_view_url": "https://..."}``

DynamoDB item: ``(pk='EXECUTION#{exec}', sk='LIVE_VIEW')`` with the URL
and a created_at timestamp.  If a record already exists it is replaced
(last-writer-wins — the browser has restarted mid-execution).
"""

from __future__ import annotations

import json
from typing import Any, Dict
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

from utils import (
    create_response,
    get_current_timestamp,
    get_table_name,
    require_scopes,
    validate_path_id,
)

_dynamodb = boto3.client('dynamodb')

_MAX_URL_LENGTH = 2048


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

    live_view_url = body.get('live_view_url')
    if not live_view_url or not isinstance(live_view_url, str):
        return create_response(
            400, {'error': 'live_view_url is required and must be a string'},
        )
    if len(live_view_url) > _MAX_URL_LENGTH:
        return create_response(
            400,
            {'error': f'live_view_url exceeds maximum length of {_MAX_URL_LENGTH}'},
        )

    # Reject non-https URLs — live views are served over TLS only.
    try:
        parsed = urlparse(live_view_url)
    except Exception:
        return create_response(400, {'error': 'live_view_url is not a valid URL'})
    if parsed.scheme not in ('http', 'https'):
        return create_response(
            400, {'error': 'live_view_url scheme must be http or https'},
        )
    if not parsed.hostname:
        return create_response(400, {'error': 'live_view_url must include a host'})

    # --- Write -------------------------------------------------------------
    table_name = get_table_name()
    timestamp = get_current_timestamp()
    try:
        _dynamodb.put_item(
            TableName=table_name,
            Item={
                'pk': {'S': f'EXECUTION#{execution_id}'},
                'sk': {'S': 'LIVE_VIEW'},
                'live_view_url': {'S': live_view_url},
                'created_at': {'S': timestamp},
            },
        )
    except ClientError:
        return create_response(500, {'error': 'Failed to create live view'})

    return create_response(200, {'status': 'ok'})
