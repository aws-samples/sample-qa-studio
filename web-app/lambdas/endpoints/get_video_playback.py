"""
AWS Lambda function to return video playback data for a given execution.

Inspects the execution record's trigger_type to determine the recording type:
- Worker path (OnDemand, Scheduled, OnDemandHeadless): returns rrweb batch metadata
- CICD-runner path (ci_runner): returns a presigned S3 download URL for the video file

GET /api/usecase/{id}/executions/{executionId}/video
Scope: api/executions.read
"""
import json
import logging
from typing import Any, Dict, Tuple

import boto3
from botocore.exceptions import ClientError
from utils import create_response, get_table_name, get_bucket_name, require_scopes

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Trigger types that map to rrweb playback
RRWEB_TRIGGER_TYPES = {"OnDemand", "Scheduled", "OnDemandHeadless"}
# Trigger types that map to video playback
VIDEO_TRIGGER_TYPES = {"ci_runner"}


def get_dynamodb_client():
    """Get DynamoDB client (lazy initialization for testing)."""
    return boto3.client("dynamodb")


def get_s3_client():
    """Get Amazon S3 client (lazy initialization for testing)."""
    return boto3.client("s3")


def classify_playback_type(trigger_type: str) -> str:
    """
    Map trigger_type to playback type.

    Args:
        trigger_type: The trigger_type value from the execution record.

    Returns:
        "rrweb" for worker-path triggers, "video" for ci_runner.

    Raises:
        ValueError: If trigger_type is not recognized.
    """
    if trigger_type in RRWEB_TRIGGER_TYPES:
        return "rrweb"
    if trigger_type in VIDEO_TRIGGER_TYPES:
        return "video"
    raise ValueError(f"Unknown trigger_type: {trigger_type}")


def get_rrweb_playback_data(
    s3_client, bucket: str, usecase_id: str, execution_id: str
) -> Tuple[list, dict]:
    """
    Retrieve rrweb recording metadata from S3.

    Follows the same S3 listing pattern as list_recording_batches.py:
    1. List objects at {usecase_id}/{execution_id}/recording/ with delimiter to find session folder
    2. Load metadata.json from the session folder
    3. List batch files (batch_*.ndjson.gz) and extract sorted batch IDs

    Args:
        s3_client: Boto3 S3 client
        bucket: Amazon S3 bucket name
        usecase_id: Usecase ID
        execution_id: Execution ID

    Returns:
        Tuple of (batch_ids, metadata)

    Raises:
        FileNotFoundError: If no recording folder or batch files found
        ClientError: On S3 errors
    """
    recording_base_prefix = f"{usecase_id}/{execution_id}/recording/"

    # Find the session folder
    response = s3_client.list_objects_v2(
        Bucket=bucket,
        Prefix=recording_base_prefix,
        Delimiter="/",
        MaxKeys=10,
    )

    common_prefixes = response.get("CommonPrefixes", [])
    if not common_prefixes:
        raise FileNotFoundError("No recording folder found")

    folder_prefix = common_prefixes[0]["Prefix"]
    logger.info(f"Found recording folder: {folder_prefix}")

    # Load metadata.json
    metadata_key = f"{folder_prefix.rstrip('/')}/metadata.json"
    try:
        meta_response = s3_client.get_object(Bucket=bucket, Key=metadata_key)
        metadata = json.loads(meta_response["Body"].read().decode("utf-8"))
    except ClientError:
        logger.warning(f"Could not load metadata from {metadata_key}")
        metadata = {}

    # List batch files
    batch_response = s3_client.list_objects_v2(
        Bucket=bucket,
        Prefix=f"{folder_prefix}batch_",
    )

    contents = batch_response.get("Contents", [])
    if not contents:
        raise FileNotFoundError("No batch files found in recording folder")

    batch_ids = []
    for obj in contents:
        key = obj["Key"]
        filename = key.split("/")[-1]
        if filename.startswith("batch_") and filename.endswith(".gz"):
            batch_id = filename.replace("batch_", "").replace(".gz", "").replace(".ndjson", "")
            batch_ids.append(batch_id)

    batch_ids.sort()

    if not batch_ids:
        raise FileNotFoundError("No batch files found in recording folder")

    return batch_ids, metadata


def get_video_playback_data(
    dynamodb, table_name: str, bucket: str, execution_id: str
) -> Tuple[str, str, int]:
    """
    Retrieve video recording artifact and generate a presigned download URL.

    Queries DynamoDB for artifact records, filters for type=recording with
    upload_status=uploaded, then generates a presigned S3 GET URL.

    Args:
        dynamodb: Boto3 DynamoDB client
        table_name: DynamoDB table name
        bucket: Amazon S3 bucket name (fallback if artifact record lacks s3_bucket)
        execution_id: Execution ID

    Returns:
        Tuple of (download_url, content_type, expires_in)

    Raises:
        FileNotFoundError: If no uploaded recording artifact found
        ClientError: On DynamoDB/S3 errors
    """
    response = dynamodb.query(
        TableName=table_name,
        KeyConditionExpression="pk = :pk AND begins_with(sk, :sk_prefix)",
        ExpressionAttributeValues={
            ":pk": {"S": f"EXECUTION#{execution_id}"},
            ":sk_prefix": {"S": "ARTIFACT#"},
        },
    )

    items = response.get("Items", [])

    # Filter for recording artifacts with upload_status=uploaded
    recording_artifact = None
    for item in items:
        item_type = item.get("type", {}).get("S", "")
        upload_status = item.get("upload_status", {}).get("S", "")
        if item_type == "recording" and upload_status == "uploaded":
            recording_artifact = item
            break

    if not recording_artifact:
        raise FileNotFoundError("No uploaded recording artifact found")

    s3_key = recording_artifact["s3_key"]["S"]
    s3_bucket = recording_artifact.get("s3_bucket", {}).get("S", bucket)
    content_type = recording_artifact.get("content_type", {}).get("S", "video/webm")

    expires_in = 3600
    s3_client = get_s3_client()
    download_url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": s3_bucket, "Key": s3_key},
        ExpiresIn=expires_in,
    )

    return download_url, content_type, expires_in


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Return video playback data for a given execution.

    Path Parameters:
        id: Usecase ID
        executionId: Execution ID

    Returns:
        200: Playback data (rrweb or video depending on trigger_type)
        400: Missing path parameters or unsupported trigger_type
        403: Insufficient permissions
        404: Execution not found or no recording available
        500: Internal server error
    """
    # Validate scope
    user_identity, error_response = require_scopes(event, ["api/executions.read"])
    if error_response:
        return error_response

    # Parse path parameters
    path_params = event.get("pathParameters") or {}
    usecase_id = path_params.get("id")
    execution_id = path_params.get("executionId")

    if not usecase_id or not execution_id:
        return create_response(400, {
            "error": "Missing required path parameters",
            "message": "usecase_id and execution_id are required",
        })

    try:
        dynamodb = get_dynamodb_client()
        table_name = get_table_name()
        bucket = get_bucket_name()
    except Exception as e:
        logger.error(f"Configuration error: {str(e)}")
        return create_response(500, {
            "error": "Configuration error",
            "message": "Internal server error",
        })

    try:
        # Retrieve execution record
        response = dynamodb.get_item(
            TableName=table_name,
            Key={
                "pk": {"S": f"USECASE_EXECUTION#{usecase_id}"},
                "sk": {"S": f"EXECUTION#{execution_id}"},
            },
        )

        if "Item" not in response:
            return create_response(404, {
                "error": "Execution not found",
                "message": f"No execution found with ID: {execution_id}",
            })

        execution_record = response["Item"]
        trigger_type = execution_record.get("trigger_type", {}).get("S", "")
        test_platform = execution_record.get("test_platform", {}).get("S", "web")

        # Mobile executions always use video playback (Device Farm mp4)
        if test_platform == "mobile":
            playback_type = "video"
        else:
            # Classify playback type based on trigger_type
            try:
                playback_type = classify_playback_type(trigger_type)
            except ValueError:
                return create_response(400, {
                    "error": "Unsupported trigger type",
                    "message": f"trigger_type '{trigger_type}' is not supported",
                })

        # Build response based on playback type
        if playback_type == "rrweb":
            s3_client = get_s3_client()
            try:
                batches, metadata = get_rrweb_playback_data(
                    s3_client, bucket, usecase_id, execution_id
                )
            except FileNotFoundError:
                return create_response(404, {
                    "error": "Recording not found",
                    "message": "No recording available for this execution",
                })

            return create_response(200, {
                "playback_type": "rrweb",
                "execution_id": execution_id,
                "trigger_type": trigger_type,
                "batches": batches,
                "metadata": metadata,
            })

        else:  # playback_type == "video"
            try:
                download_url, content_type, expires_in = get_video_playback_data(
                    dynamodb, table_name, bucket, execution_id
                )
            except FileNotFoundError:
                return create_response(404, {
                    "error": "Recording not found",
                    "message": "No recording available for this execution",
                })

            return create_response(200, {
                "playback_type": "video",
                "execution_id": execution_id,
                "trigger_type": trigger_type,
                "download_url": download_url,
                "content_type": content_type,
                "expires_in": expires_in,
            })

    except ClientError as e:
        logger.error(f"AWS error in get_video_playback: {str(e)}", exc_info=True)
        return create_response(500, {"error": "Internal server error"})
    except Exception as e:
        logger.error(f"Unexpected error in get_video_playback: {str(e)}", exc_info=True)
        return create_response(500, {"error": "Internal server error"})
