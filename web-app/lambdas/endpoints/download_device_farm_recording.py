"""
Device Farm Recording Downloader Lambda

SQS-triggered Lambda that downloads a video recording from a Device Farm session
and uploads it to S3. By the time this runs, the SQS delay (5 min) has given
Device Farm enough time to finalize session artifacts.

Retries via SQS visibility timeout if the session hasn't reached a terminal state yet.
After max retries, the message goes to a DLQ.
"""

import json
import logging
import os
import uuid
import time as _time
from typing import Any, Dict, Optional
from urllib.request import urlopen

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEVICE_FARM_REGION = "us-west-2"


class SessionNotReady(Exception):
    """Raised when the Device Farm session hasn't finalized yet. Triggers SQS retry."""
    pass


def find_video_artifact(df_client, session_arn: str) -> Optional[tuple]:
    """Find and download the VIDEO artifact from Device Farm."""
    for art_type in ["FILE", "SCREENSHOT", "LOG"]:
        try:
            response = df_client.list_artifacts(arn=session_arn, type=art_type)
            for artifact in response.get("artifacts", []):
                a_type = artifact.get("type", "")
                ext = artifact.get("extension", "")
                url = artifact.get("url", "")
                name = artifact.get("name", "")

                is_video = (
                    a_type == "VIDEO"
                    or ext in ("mp4", "webm", "mov")
                    or "video" in name.lower()
                )
                if is_video and url:
                    logger.info("Found video: name=%s, type=%s, ext=%s", name, a_type, ext)
                    with urlopen(url, timeout=60) as resp:
                        return (resp.read(), ext or "mp4")
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code == "AccessDeniedException":
                logger.error("Missing devicefarm:ListArtifacts permission: %s", e)
                return None
            logger.warning("Error listing %s artifacts: %s", art_type, e)
        except Exception as e:
            logger.warning("Error fetching %s artifacts: %s", art_type, e)
    return None


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """SQS-triggered handler. Each record contains one recording download request."""
    s3_bucket = os.environ["S3_BUCKET"]
    table_name = os.environ["DYNAMODB_TABLE_NAME"]
    df_client = boto3.client("devicefarm", region_name=DEVICE_FARM_REGION)
    s3_client = boto3.client("s3")
    dynamodb = boto3.client("dynamodb")

    for record in event.get("Records", []):
        msg = json.loads(record["body"])
        session_arn = msg["session_arn"]
        usecase_id = msg["usecase_id"]
        execution_id = msg["execution_id"]
        nova_session_id = msg.get("nova_session_id", execution_id)

        log_prefix = f"[exec:{execution_id}]"

        try:
            logger.info(
                "%s Processing recording for session %s", log_prefix, session_arn
            )

            # Check session status
            try:
                resp = df_client.get_remote_access_session(arn=session_arn)
                status = resp["remoteAccessSession"].get("status", "")
                logger.info("%s Session status: %s", log_prefix, status)
                if status not in ("COMPLETED", "ERRORED", "STOPPED"):
                    logger.info(
                        "%s Session still in %s state — will retry via SQS",
                        log_prefix, status,
                    )
                    raise SessionNotReady(status)
            except ClientError as e:
                logger.warning("%s Could not check session status: %s", log_prefix, e)

            # Download video
            result = find_video_artifact(df_client, session_arn)
            if not result:
                logger.warning("%s No video artifact found", log_prefix)
                return {"statusCode": 200}

            video_bytes, ext = result
            content_type = "video/mp4" if ext == "mp4" else f"video/{ext}"
            recording_key = (
                f"{usecase_id}/{execution_id}/recording/"
                f"{nova_session_id}/session_recording.{ext}"
            )

            s3_client.put_object(
                Bucket=s3_bucket,
                Key=recording_key,
                Body=video_bytes,
                ContentType=content_type,
            )

            logger.info(
                "%s Uploaded recording (%d bytes) to s3://%s/%s",
                log_prefix, len(video_bytes), s3_bucket, recording_key,
            )

            # Create artifact record in DynamoDB
            artifact_id = str(uuid.uuid4())
            created_at = _time.strftime("%Y-%m-%dT%H:%M:%S.000Z", _time.gmtime())
            dynamodb.put_item(
                TableName=table_name,
                Item={
                    "pk": {"S": f"EXECUTION#{execution_id}"},
                    "sk": {"S": f"ARTIFACT#{artifact_id}"},
                    "artifact_id": {"S": artifact_id},
                    "execution_id": {"S": execution_id},
                    "type": {"S": "recording"},
                    "filename": {"S": f"session_recording.{ext}"},
                    "content_type": {"S": content_type},
                    "s3_bucket": {"S": s3_bucket},
                    "s3_key": {"S": recording_key},
                    "upload_status": {"S": "uploaded"},
                    "created_at": {"S": created_at},
                },
            )
            logger.info(
                "%s Created artifact record %s", log_prefix, artifact_id
            )

        except SessionNotReady:
            # Re-raise so SQS retries after visibility timeout
            raise
        except Exception as e:
            logger.error(
                "%s Failed to process recording: %s", log_prefix, e, exc_info=True
            )
            raise

    return {"statusCode": 200}
