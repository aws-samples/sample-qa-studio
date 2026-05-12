"""Vend a presigned GET URL for a step's trajectory JSON.

Implements the download-side of R-API-5.  Called by the CLI runner
before executing a navigation step, to check whether a trajectory is
available for replay.

Route: ``GET /api/usecase/{id}/steps/{stepId}/trajectory/download-url``
Scope: ``api/executions.write`` (trajectories are part of the cache
       pipeline, which is execution-write-scope per design).
Responses: ``200`` with URL; ``404`` when no trajectory is recorded for
       the step.
"""

from __future__ import annotations

import os
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

from utils import (
    create_response,
    get_table_name,
    require_scopes,
    validate_path_id,
)

_s3 = boto3.client('s3')
_dynamodb = boto3.client('dynamodb')

_DOWNLOAD_EXPIRES_IN = 900  # 15 minutes


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

    # --- Look up pointer on the step record -------------------------------
    try:
        response = _dynamodb.get_item(
            TableName=get_table_name(),
            Key={
                'pk': {'S': f'USECASE#{usecase_id}'},
                'sk': {'S': f'STEP#{step_id}'},
            },
        )
    except ClientError:
        return create_response(500, {'error': 'Failed to read step record'})

    item = response.get('Item')
    if not item:
        return create_response(404, {'error': 'Step not found'})
    key_attr = item.get('trajectory_s3_key')
    if not key_attr or not key_attr.get('S'):
        return create_response(404, {'error': 'No trajectory recorded for this step'})
    s3_key = key_attr['S']

    # --- Vend the presigned URL -------------------------------------------
    bucket = os.environ.get('BUCKET_NAME')
    if not bucket:
        return create_response(500, {'error': 'BUCKET_NAME not configured'})
    try:
        download_url = _s3.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': bucket, 'Key': s3_key},
            ExpiresIn=_DOWNLOAD_EXPIRES_IN,
        )
    except ClientError:
        return create_response(500, {'error': 'Failed to generate download URL'})

    return create_response(200, {
        'download_url': download_url,
        'expires_in': _DOWNLOAD_EXPIRES_IN,
    })
