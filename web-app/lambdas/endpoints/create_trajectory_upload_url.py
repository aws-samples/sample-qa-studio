"""Vend a presigned PUT URL for a step's trajectory JSON + set the pointer.

Implements the upload-side of R-API-5.  Called by the CLI runner after a
successful ``nova.act()`` call when trajectory recording is enabled.

Route: ``POST /api/usecase/{id}/steps/{stepId}/trajectory/upload-url``
Scope: ``api/executions.write``
Body (optional): ``{"content_type": "application/json"}``

DynamoDB step record: ``(pk='USECASE#{usecase}', sk='STEP#{step}')``.
``trajectory_s3_key`` + ``trajectory_last_updated`` are set atomically
with the presigned-URL response, so the runner can upload and rely on
the pointer immediately.  If the PUT fails for any reason, the pointer
is stale — a later replay attempt will 404 on the object and clear the
pointer via the cache-fields cleanup flag (R-API-6).  See
``.kiro/specs/cli-unified-runner/design.md`` for the trade-off.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

from utils import (
    create_response,
    get_current_timestamp,
    get_table_name,
    require_scopes,
    validate_path_id,
)

_s3 = boto3.client('s3')
_dynamodb = boto3.client('dynamodb')

_ALLOWED_CONTENT_TYPES = {'application/json'}
_DEFAULT_CONTENT_TYPE = 'application/json'
_UPLOAD_EXPIRES_IN = 900  # 15 minutes


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
    step_id, error = validate_path_id(path.get('stepId'), 'step ID')
    if error:
        return error

    # --- Body (optional) ---------------------------------------------------
    content_type = _DEFAULT_CONTENT_TYPE
    raw_body = event.get('body')
    if raw_body:
        try:
            body = json.loads(raw_body)
        except (ValueError, TypeError):
            return create_response(400, {'error': 'Invalid JSON in request body'})
        if not isinstance(body, dict):
            return create_response(400, {'error': 'Request body must be a JSON object'})
        content_type = body.get('content_type', _DEFAULT_CONTENT_TYPE)
        if content_type not in _ALLOWED_CONTENT_TYPES:
            return create_response(
                400,
                {'error': f'content_type must be one of {sorted(_ALLOWED_CONTENT_TYPES)}'},
            )

    # --- Compose the S3 key and vend the URL -------------------------------
    import os  # local to keep top-level imports minimal
    bucket = os.environ.get('BUCKET_NAME')
    if not bucket:
        return create_response(500, {'error': 'BUCKET_NAME not configured'})

    s3_key = f'{usecase_id}/trajectories/{step_id}.json'
    try:
        upload_url = _s3.generate_presigned_url(
            ClientMethod='put_object',
            Params={
                'Bucket': bucket,
                'Key': s3_key,
                'ContentType': content_type,
            },
            ExpiresIn=_UPLOAD_EXPIRES_IN,
        )
    except ClientError:
        return create_response(500, {'error': 'Failed to generate upload URL'})

    # --- Atomically set the pointer on the step record --------------------
    timestamp = get_current_timestamp()
    try:
        _dynamodb.update_item(
            TableName=get_table_name(),
            Key={
                'pk': {'S': f'USECASE#{usecase_id}'},
                'sk': {'S': f'STEP#{step_id}'},
            },
            UpdateExpression=(
                'SET trajectory_s3_key = :k, trajectory_last_updated = :t'
            ),
            ExpressionAttributeValues={
                ':k': {'S': s3_key},
                ':t': {'S': timestamp},
            },
        )
    except ClientError:
        return create_response(500, {'error': 'Failed to record trajectory pointer'})

    return create_response(200, {
        'upload_url': upload_url,
        's3_key': s3_key,
        'expires_in': _UPLOAD_EXPIRES_IN,
    })
