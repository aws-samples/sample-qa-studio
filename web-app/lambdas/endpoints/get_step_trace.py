"""Lambda handler for fetching and parsing JSON trace data for an execution step."""
import lambda_init  # noqa: F401 — Must be first to set up Python path
import json
import logging
import re
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from pydantic import BaseModel

from utils import create_response, get_bucket_name, get_table_name, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TraceStep(BaseModel):
    step_num: int
    thought: str
    action: str
    screenshot: str  # base64 encoded PNG
    time_s: float


class TraceMetadata(BaseModel):
    session_id: str
    act_id: str
    num_steps_executed: int
    start_time: float
    end_time: float
    prompt: str
    time_worked_s: float


class StepTraceResponse(BaseModel):
    trace_steps: List[TraceStep]
    metadata: TraceMetadata


# ---------------------------------------------------------------------------
# Trace parsing
# ---------------------------------------------------------------------------

def parse_trace_json(raw_json: str) -> StepTraceResponse:
    """
    Parse raw JSON trace content into a validated StepTraceResponse.

    Args:
        raw_json: Raw JSON string from the S3 trace file.

    Returns:
        Validated StepTraceResponse model.

    Raises:
        ValueError: If the JSON is malformed or missing required fields.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    try:
        steps_raw = data.get("steps")
        metadata_raw = data.get("metadata")

        if steps_raw is None or metadata_raw is None:
            raise ValueError("Missing required top-level fields: 'steps' and 'metadata'")

        trace_steps = [TraceStep(**s) for s in steps_raw]
        metadata = TraceMetadata(**metadata_raw)

        return StepTraceResponse(trace_steps=trace_steps, metadata=metadata)
    except (TypeError, KeyError) as exc:
        raise ValueError(f"Invalid trace structure: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Failed to parse trace data: {exc}") from exc


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------

def find_trace_s3_key(
    s3_client,
    bucket: str,
    usecase_id: str,
    execution_id: str,
    session_id: str,
    act_id: str,
) -> Optional[str]:
    """
    Discover the S3 key for a _calls.json trace file by listing objects with
    the act prefix and matching the act_id.

    S3 keys follow the pattern:
        {usecaseId}/{executionId}/{sessionId}/act_{actId}_{instruction}_calls.json

    Args:
        s3_client: boto3 S3 client
        bucket: S3 bucket name
        usecase_id: Usecase identifier
        execution_id: Execution identifier
        session_id: Nova Act session identifier
        act_id: Act identifier to match

    Returns:
        The full S3 key if found, otherwise None.
    """
    prefix = f"{usecase_id}/{execution_id}/{session_id}/act_{act_id}"
    logger.info(f"Listing S3 objects with prefix={prefix} in bucket={bucket}")

    try:
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    except ClientError:
        logger.error(f"S3 error listing objects with prefix={prefix}", exc_info=True)
        return None

    if "Contents" not in response:
        return None

    pattern = re.compile(rf".*act_{re.escape(act_id)}_.*_calls\.json$")
    for obj in response["Contents"]:
        key = obj["Key"]
        if pattern.match(key):
            logger.info(f"Found trace file: {key}")
            return key

    return None


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Fetch and return parsed JSON trace data for a single execution step.

    Route: GET /usecase/{id}/executions/{executionId}/steps/{stepId}/trace
    Scope: api/executions.read
    """
    try:
        # --- Scope validation ---
        user_identity, error = require_scopes(event, ["api/executions.read"])
        if error:
            return error

        # --- Path parameters ---
        params = event.get("pathParameters") or {}
        usecase_id = params.get("id")
        execution_id = params.get("executionId")
        step_id = params.get("stepId")

        if not usecase_id or not execution_id or not step_id:
            return create_response(400, {"error": "Missing required parameters"})

        logger.info(
            f"get_step_trace: usecaseId={usecase_id}, executionId={execution_id}, stepId={step_id}"
        )

        # --- DynamoDB setup ---
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(get_table_name())

        # --- 1. Look up execution step by sort value to get act_id ---
        # stepId from the URL is the sort value, not the SK UUID.
        # Query all EXECUTION_STEP# records and find the one matching sort.
        step_query = table.query(
            KeyConditionExpression=Key("pk").eq(f"EXECUTION#{execution_id}")
            & Key("sk").begins_with("EXECUTION_STEP#")
        )

        step_item = None
        for item in step_query.get("Items", []):
            # sort is stored as a number (Decimal)
            if str(item.get("sort", "")) == str(step_id):
                step_item = item
                break

        if not step_item:
            return create_response(404, {"error": "Execution step not found"})

        act_id = step_item.get("act_id")

        if not act_id:
            return create_response(404, {"error": "No trace available for this step"})
        if act_id == "cached":
            return create_response(404, {"error": "No trace available for cached step"})
        if act_id == "error":
            return create_response(404, {"error": "No trace available for errored step"})

        # --- 2. Look up execution to get nova_session_id ---
        exec_response = table.get_item(
            Key={
                "pk": f"USECASE_EXECUTION#{usecase_id}",
                "sk": f"EXECUTION#{execution_id}",
            }
        )

        exec_item = exec_response.get("Item")
        if not exec_item:
            return create_response(404, {"error": "Execution not found"})

        session_id = exec_item.get("nova_session_id")
        if not session_id:
            return create_response(404, {"error": "Execution has no session ID"})

        # --- 3. Find and fetch JSON trace from S3 ---
        bucket = get_bucket_name()
        s3_client = boto3.client("s3")

        s3_key = find_trace_s3_key(
            s3_client, bucket, usecase_id, execution_id, session_id, act_id
        )

        if not s3_key:
            return create_response(404, {"error": "Trace file not found"})

        try:
            s3_response = s3_client.get_object(Bucket=bucket, Key=s3_key)
            raw_json = s3_response["Body"].read().decode("utf-8")
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchKey":
                return create_response(404, {"error": "Trace file not found"})
            logger.error(f"S3 error fetching trace file {s3_key}: {exc}", exc_info=True)
            return create_response(500, {"error": "Internal server error"})

        # --- 4. Parse and return ---
        try:
            trace = parse_trace_json(raw_json)
        except ValueError:
            logger.warning(f"Failed to parse trace JSON from {s3_key}", exc_info=True)
            return create_response(404, {"error": "Failed to parse trace data"})

        return create_response(200, trace.model_dump())

    except Exception as exc:
        logger.error(f"Unexpected error in get_step_trace: {exc}", exc_info=True)
        return create_response(500, {"error": "Internal server error"})
