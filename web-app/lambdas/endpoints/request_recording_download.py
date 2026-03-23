"""
Request Device Farm Recording Download

API endpoint that enqueues a delayed SQS message to trigger the async
recording download Lambda. Called by the CLI after mobile test execution.
"""

import json
import logging
import os
from typing import Any, Dict

import boto3

from utils import create_response, require_scopes, validate_path_id

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DELAY_SECONDS = 300  # 5 minutes


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    user_identity, error_response = require_scopes(event, ["api/executions.write"])
    if error_response:
        return error_response

    params = event.get("pathParameters") or {}
    usecase_id, error = validate_path_id(params.get("id"), "usecase ID")
    if error:
        return error
    execution_id, error = validate_path_id(params.get("executionId"), "execution ID")
    if error:
        return error

    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return create_response(400, {"error": "Invalid JSON"})

    session_arn = body.get("session_arn")
    if not session_arn:
        return create_response(400, {"error": "session_arn is required"})

    # Validate ARN format
    if not session_arn.startswith("arn:aws:devicefarm:"):
        return create_response(400, {"error": "Invalid session_arn format — must be a Device Farm session ARN"})

    nova_session_id = body.get("nova_session_id", execution_id)
    queue_url = os.environ.get("RECORDING_QUEUE_URL")
    if not queue_url:
        return create_response(500, {"error": "Recording queue not configured"})

    sqs = boto3.client("sqs")
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({
            "session_arn": session_arn,
            "usecase_id": usecase_id,
            "execution_id": execution_id,
            "nova_session_id": nova_session_id,
        }),
        DelaySeconds=DELAY_SECONDS,
    )

    logger.info(
        "Enqueued recording download for execution %s, session %s",
        execution_id, session_arn,
    )

    return create_response(200, {
        "message": "Recording download requested",
        "delay_seconds": DELAY_SECONDS,
    })
