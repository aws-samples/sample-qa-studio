"""Manage Nova Act trajectory recording, storage, and replay.

This module provides the TrajectoryManager class which handles:
- Uploading trajectory files to S3 after successful nova.act() calls
- Downloading trajectory files from S3 for replay
- Updating STEP records in DynamoDB with trajectory references
- Detecting whether the current Nova Act backend supports replayable=True
- Managing local temporary files for trajectory download/upload

The replay mechanism is based on the nova-act-samples trajectory replay pattern:
https://github.com/amazon-agi-labs/nova-act-samples/blob/main/examples/trajectory/trajectory_replay/runner.py

It uses the SDK's internal ProgramRunner to re-execute recorded programs through the actuator.
"""

import inspect
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import ReplayResult, TrajectoryReplayError

logger = logging.getLogger(__name__)

# Maximum seconds to wait for a trajectory replay before timing out.
# Override via TRAJECTORY_REPLAY_TIMEOUT_S environment variable.
TRAJECTORY_REPLAY_TIMEOUT_S = int(os.getenv('TRAJECTORY_REPLAY_TIMEOUT_S', '30'))


class TrajectoryManager:
    """Manages Nova Act trajectory recording, storage, and replay.

    Attributes:
        s3_client: boto3 S3 client for trajectory upload/download.
        s3_bucket: S3 bucket name for trajectory storage.
        usecase_id: Current usecase identifier.
        execution_id: Current execution identifier.
        dynamo_table: DynamoDB table resource for STEP record updates.
        logs_directory: Local directory for temporary trajectory files.
        replayable_supported: Whether the current NovaAct backend supports replayable=True.
    """

    def __init__(
        self,
        s3_client,
        s3_bucket: str,
        usecase_id: str,
        execution_id: str,
        dynamo_table,
        logs_directory: str,
        replayable_supported: bool = False,
    ):
        self.s3_client = s3_client
        self.s3_bucket = s3_bucket
        self.usecase_id = usecase_id
        self.execution_id = execution_id
        self.dynamo_table = dynamo_table
        self.logs_directory = logs_directory
        self.replayable_supported = replayable_supported

    @property
    def is_recording_enabled(self) -> bool:
        """Whether trajectory recording is active for this execution."""
        return self.replayable_supported

    @staticmethod
    def detect_replayable_support(nova_act_class) -> bool:
        """Probe whether the given NovaAct class accepts ``replayable=True``.

        Uses ``inspect.signature`` to check if ``replayable`` is in the
        ``__init__`` parameters.  Does **not** instantiate the class.

        Args:
            nova_act_class: The NovaAct class (not an instance).

        Returns:
            True if the ``replayable`` keyword argument exists in ``__init__``.
        """
        try:
            sig = inspect.signature(nova_act_class.__init__)
            return 'replayable' in sig.parameters
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def save_trajectory(self, step_id: str, result) -> Optional[str]:
        """Upload trajectory file from a ``nova.act()`` result to S3 and update the STEP record.

        Args:
            step_id: The STEP record's step_id (used in the DynamoDB key).
            result: Nova Act result object (may have ``trajectory_file_path``).

        Returns:
            S3 key of the uploaded trajectory, or ``None`` if no trajectory is
            available or an error occurred.
        """
        trajectory_path = getattr(result, 'trajectory_file_path', None)
        if not trajectory_path or not Path(trajectory_path).exists():
            logger.debug(f"No trajectory file for step {step_id}")
            return None

        s3_key = f"{self.usecase_id}/{self.execution_id}/trajectories/{step_id}.json"

        try:
            # Upload to S3
            with open(trajectory_path, 'rb') as f:
                self.s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Body=f,
                    ContentType='application/json',
                )

            # Update STEP record in DynamoDB
            timestamp = datetime.utcnow().isoformat() + 'Z'
            self.dynamo_table.update_item(
                Key={
                    'pk': f'USECASE#{self.usecase_id}',
                    'sk': f'STEP#{step_id}',
                },
                UpdateExpression='SET trajectory_s3_key = :tk, trajectory_last_updated = :ts',
                ExpressionAttributeValues={
                    ':tk': s3_key,
                    ':ts': timestamp,
                },
            )

            logger.info(f"Saved trajectory for step {step_id} to s3://{self.s3_bucket}/{s3_key}")
            return s3_key

        except Exception as e:
            logger.warning(f"Failed to save trajectory for step {step_id}: {e}")
            return None

    def clear_cache_fields(self, step_id: str, fields: list) -> None:
        """Remove specified cache fields from a STEP record using DynamoDB REMOVE.

        Non-fatal: logs a warning on failure, never raises.

        Args:
            step_id: The step ID (used in sk=STEP#{step_id})
            fields: List of field names to remove (e.g., ["cached_steps", "cache_last_updated"])
        """
        try:
            if not fields:
                return

            remove_expression = 'REMOVE ' + ', '.join(fields)
            self.dynamo_table.update_item(
                Key={
                    'pk': f'USECASE#{self.usecase_id}',
                    'sk': f'STEP#{step_id}',
                },
                UpdateExpression=remove_expression,
            )
            logger.info(f"Cleared cache fields {fields} for step {step_id}")
        except Exception as e:
            logger.warning(f"Cache cleanup: failed to remove cache fields for step {step_id}: {e}")

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------

    def replay_step(self, nova, step) -> ReplayResult:
        """Download trajectory from S3 and replay it using ProgramRunner.

        Args:
            nova: Active NovaAct instance with a browser session.
            step: ``ExecutionStep`` with ``trajectory_s3_key`` set.

        Returns:
            ``ReplayResult`` with success status and metadata.

        Raises:
            TrajectoryReplayError: If download, deserialization, or replay fails,
                or if the replay exceeds ``TRAJECTORY_REPLAY_TIMEOUT_S``.
        """
        from nova_act.impl.trajectory.types import Trajectory
        from nova_act.impl.program.runner import ProgramRunner

        s3_key = step.trajectory_s3_key
        local_path: Optional[str] = None
        start_time = time.time()
        timeout = TRAJECTORY_REPLAY_TIMEOUT_S

        try:
            # Download trajectory to a temp file
            local_path = os.path.join(self.logs_directory, f"replay_{step.step_id}.json")
            self.s3_client.download_file(self.s3_bucket, s3_key, local_path)

            # Deserialize using the SDK's pydantic model
            with open(local_path) as f:
                trajectory = Trajectory.model_validate_json(f.read())

            # Build tool map from the NovaAct instance's registered tools.
            # NOTE: accesses private attributes — coupled to SDK internals.
            tool_map = {tool.tool_name: tool for tool in nova._client_tools}

            # Create ProgramRunner and replay each trajectory step's program
            program_runner = ProgramRunner(nova._event_handler, verbose=False)

            for traj_step in trajectory.steps:
                # Timeout check before each trajectory step
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    raise TrajectoryReplayError(
                        message=f"Replay timed out after {elapsed:.1f}s (limit {timeout}s) for {s3_key}",
                        s3_key=s3_key,
                    )

                executable = traj_step.program.compile(tool_map)
                program_result = program_runner.run(executable)

                # Check for errors
                if exception_result := program_result.has_exception():
                    if exception_result.error is not None:
                        raise exception_result.error
                # Check for early return (task complete)
                elif program_result.has_return():
                    break

            duration_ms = int((time.time() - start_time) * 1000)
            return ReplayResult(
                success=True,
                duration_ms=duration_ms,
                trajectory_s3_key=s3_key,
            )

        except TrajectoryReplayError:
            raise

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            raise TrajectoryReplayError(
                message=f"Replay failed for {s3_key}: {e}",
                s3_key=s3_key,
                cause=e,
            )

        finally:
            # Clean up temp file
            if local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError as cleanup_err:
                    logger.warning(f"Failed to clean up temp trajectory file {local_path}: {cleanup_err}")
