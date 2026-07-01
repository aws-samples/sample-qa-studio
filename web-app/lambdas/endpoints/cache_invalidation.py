"""Shared cache-invalidation helpers for failed/rebuilt use cases.

Clears the four cache-related fields from every step-definition record
belonging to a use case AND batch-deletes the corresponding trajectory
blobs from S3. Used by:

* :mod:`update_usecase` — when the use case itself is edited and any
  existing cache data may no longer be valid for the new step layout.
* :mod:`update_execution_status` — when an execution transitions to
  ``failed`` (Option C: coarse but reliable cache invalidation on
  failure — see the RCA in the cli-tui spec's history).
* :mod:`handle_task_state_change` — same behaviour, but triggered when
  an ECS task crashes/exits without the runner reporting status.

Contract
--------
* All three functions are **best-effort**. A DynamoDB / S3 failure on a
  subset of items logs a warning and continues; nothing raises. The
  primary action the caller is performing (status update, usecase
  update) has already completed by the time we invalidate, and the
  invalidation itself must never be the reason a caller fails.
* The DynamoDB pagination and S3 batch-deletion limits are handled
  internally. Large usecases (>1000 steps or >1000 trajectory files)
  are iterated until exhausted.

Fields removed
--------------
``cached_steps``, ``cache_last_updated``, ``trajectory_s3_key``,
``trajectory_last_updated``. These match the allow-list used by
``update_execution_step_status`` for per-step cleanup (R-API-6) and
are the only attributes carrying cache state on the step-definition
record.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)


CACHE_FIELDS = (
    "cached_steps",
    "cache_last_updated",
    "trajectory_s3_key",
    "trajectory_last_updated",
)


def clear_step_cache_fields(table: Any, usecase_id: str) -> None:
    """Query all STEP records for a use case and REMOVE the cache fields.

    Args:
        table: ``boto3.resource('dynamodb').Table(...)`` handle.
        usecase_id: Use case whose step definitions should be cleared.

    Each individual step update is wrapped in try/except so a single
    step failure doesn't abort cleanup of the rest. Handles DynamoDB
    pagination.
    """
    remove_expr = "REMOVE " + ", ".join(CACHE_FIELDS)
    try:
        query_kwargs = {
            "KeyConditionExpression": (
                Key("pk").eq(f"USECASE#{usecase_id}")
                & Key("sk").begins_with("STEP#")
            ),
        }
        while True:
            response = table.query(**query_kwargs)
            items = response.get("Items", [])
            for item in items:
                step_sk = item["sk"]
                try:
                    table.update_item(
                        Key={"pk": f"USECASE#{usecase_id}", "sk": step_sk},
                        UpdateExpression=remove_expr,
                    )
                except Exception as exc:
                    logger.warning(
                        "Cache cleanup: failed to remove cache fields for "
                        "step %s in usecase %s: %s",
                        step_sk, usecase_id, exc,
                    )

            last_key = response.get("LastEvaluatedKey")
            if last_key:
                query_kwargs["ExclusiveStartKey"] = last_key
            else:
                break
    except Exception as exc:
        logger.warning(
            "Cache cleanup: failed to query steps for usecase %s: %s",
            usecase_id, exc,
        )


def delete_trajectory_files(s3_client: Any, s3_bucket: str, usecase_id: str) -> None:
    """Delete all trajectory JSON files under a usecase's S3 prefix.

    Filters the ``{usecase_id}/`` listing to the trajectory path pattern
    (``{usecase_id}/<something>/trajectories/*.json``) and batch-deletes
    up to 1000 keys per ``delete_objects`` call.

    Args:
        s3_client: ``boto3.client('s3')`` handle.
        s3_bucket: Bucket containing the trajectory artifacts.
        usecase_id: Use case whose trajectories should be removed.
    """
    try:
        trajectory_pattern = re.compile(
            rf"^{re.escape(usecase_id)}/[^/]+/trajectories/[^/]+\.json$"
        )
        continuation_token = None

        while True:
            list_kwargs = {
                "Bucket": s3_bucket,
                "Prefix": f"{usecase_id}/",
            }
            if continuation_token:
                list_kwargs["ContinuationToken"] = continuation_token

            response = s3_client.list_objects_v2(**list_kwargs)
            contents = response.get("Contents", [])

            keys_to_delete = [
                {"Key": obj["Key"]}
                for obj in contents
                if trajectory_pattern.match(obj["Key"])
            ]

            # S3 delete_objects caps at 1000 keys per call.
            while keys_to_delete:
                batch = keys_to_delete[:1000]
                keys_to_delete = keys_to_delete[1000:]
                try:
                    s3_client.delete_objects(
                        Bucket=s3_bucket,
                        Delete={"Objects": batch, "Quiet": True},
                    )
                except Exception as exc:
                    logger.warning(
                        "Cache cleanup: failed to delete trajectory files batch "
                        "for usecase %s: %s",
                        usecase_id, exc,
                    )

            if response.get("IsTruncated"):
                continuation_token = response.get("NextContinuationToken")
            else:
                break
    except Exception as exc:
        logger.warning(
            "Cache cleanup: failed to delete trajectory files for usecase %s: %s",
            usecase_id, exc,
        )


def cleanup_cache_artifacts(table: Any, usecase_id: str, s3_bucket: str) -> None:
    """Clear DynamoDB cache fields and delete S3 trajectory files.

    Non-fatal: logs warnings on any underlying failure. Skips the S3
    pass entirely if ``s3_bucket`` is empty so unit tests can exercise
    the DDB path in isolation.

    Args:
        table: ``boto3.resource('dynamodb').Table(...)`` handle.
        usecase_id: Use case whose cache should be wiped.
        s3_bucket: Bucket containing trajectory artifacts (may be ``""``).
    """
    try:
        clear_step_cache_fields(table, usecase_id)
        if s3_bucket:
            s3_client = boto3.client("s3")
            delete_trajectory_files(s3_client, s3_bucket, usecase_id)
    except Exception as exc:
        logger.warning(
            "Cache cleanup: unexpected error for usecase %s: %s",
            usecase_id, exc,
        )
