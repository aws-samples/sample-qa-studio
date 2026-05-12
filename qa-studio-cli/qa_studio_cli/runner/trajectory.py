"""Trajectory recording, storage, and replay — CLI side.

Mirrors the behavioural contract of
``web-app/worker/trajectory_manager.py`` so the navigation-step executor
can treat the worker and the CLI as interchangeable cache backends.
The difference: this implementation never touches S3 or DynamoDB
directly.  All storage goes through the Studio API (R-API-5) and the
presigned URLs it vends.

Three surface-level methods mirror the worker:

- :meth:`replay_step` — download the recorded trajectory, replay it via
  Nova Act's internal ``ProgramRunner``.  Raises
  :class:`~qa_studio_cli.models.execution.TrajectoryReplayError` on any
  failure so the navigation-step executor can fall back to Nova Act.
- :meth:`save_trajectory` — reserve a presigned PUT URL, upload the
  freshly-recorded trajectory JSON.  The server atomically records the
  pointer as part of issuing the URL — see
  ``web-app/lambdas/endpoints/create_trajectory_upload_url.py``.  Best
  effort: a failure here simply skips the save.
- :meth:`record_clear` — remember which fields the navigation-step
  executor wants cleaned up on the step-definition record because
  their cache data is stale.  The engine drains the queue into the next
  ``update_step_status`` call via the ``clear_cache_fields`` parameter,
  per R-API-6.

Coupling to Nova Act SDK internals is identical to the worker's
implementation (``nova_act.impl.trajectory.types.Trajectory``,
``nova_act.impl.program.runner.ProgramRunner``) — a known risk
documented in the spec's Risks section.  A signature-probe via
:func:`detect_replayable_support` avoids errors on SDK builds that
lack ``replayable=True`` support.
"""

from __future__ import annotations

import inspect
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import List, Optional

import requests

from qa_studio_cli.api.executions import ExecutionAPI
from qa_studio_cli.models.execution import (
    ReplayResult,
    TrajectoryReplayError,
)

logger = logging.getLogger(__name__)


# Seconds to wait for a full trajectory replay before timing out.  Matches
# the worker's envvar so both runtimes honour the same override.
_REPLAY_TIMEOUT_S = int(os.getenv("TRAJECTORY_REPLAY_TIMEOUT_S", "30"))


class TrajectoryManager:
    """API-backed trajectory cache for the CLI runner.

    Not thread-safe.  One manager per execution.
    """

    def __init__(
        self,
        execution_api: ExecutionAPI,
        usecase_id: str,
        execution_id: str,
        logs_directory: str,
        replayable_supported: bool = False,
    ) -> None:
        self._execution_api = execution_api
        self._usecase_id = usecase_id
        self._execution_id = execution_id
        self._logs_directory = logs_directory
        self._replayable_supported = replayable_supported
        # Pending cache-field cleanup per step.  Drained by the engine
        # on the next update_step_status call — see record_clear().
        self._pending_clears: dict[str, List[str]] = {}

    @property
    def is_recording_enabled(self) -> bool:
        """Whether trajectory recording should be attempted on this run.

        Tied to SDK support for ``replayable=True``; when the SDK doesn't
        expose recordings, there's nothing to save.
        """
        return self._replayable_supported

    # ------------------------------------------------------------------
    # SDK capability probe (static — matches worker)
    # ------------------------------------------------------------------

    @staticmethod
    def detect_replayable_support(nova_act_class) -> bool:
        """Return True if ``NovaAct.__init__`` accepts ``replayable=``.

        Mirrors the worker's probe exactly.  Doesn't instantiate the
        class; inspects the signature only.
        """
        try:
            sig = inspect.signature(nova_act_class.__init__)
        except (TypeError, ValueError):
            return False
        return "replayable" in sig.parameters

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------

    def replay_step(self, nova, step) -> ReplayResult:
        """Fetch and replay the recorded trajectory for ``step``.

        The step must carry a non-empty ``trajectory_s3_key`` attribute or
        dict entry — the navigation-step executor checks this before
        calling.  Any failure path raises :class:`TrajectoryReplayError`.
        """
        # Lazy import — these internals are only available on SDKs that
        # support replayable=True.
        from nova_act.impl.trajectory.types import Trajectory
        from nova_act.impl.program.runner import ProgramRunner

        step_id = _step_attr(step, "step_id") or _step_attr(step, "sk") or ""
        s3_key = _step_attr(step, "trajectory_s3_key") or ""
        if not step_id:
            raise TrajectoryReplayError(
                "step is missing step_id — cannot replay",
                s3_key=s3_key,
            )

        start_time = time.time()
        download_url: Optional[str]
        try:
            download_url = self._execution_api.get_trajectory_download_url(
                self._usecase_id, step_id,
            )
        except Exception as exc:  # API failure
            raise TrajectoryReplayError(
                f"failed to request trajectory download URL for step {step_id}: {exc}",
                s3_key=s3_key,
                cause=exc,
            )
        if not download_url:
            raise TrajectoryReplayError(
                f"no trajectory recorded for step {step_id}",
                s3_key=s3_key,
            )

        local_path: Optional[str] = None
        try:
            # Download trajectory JSON to a temp file under logs_directory
            # so it lands alongside the other per-execution artifacts.
            Path(self._logs_directory).mkdir(parents=True, exist_ok=True)
            local_path = os.path.join(
                self._logs_directory, f"replay_{step_id}.json",
            )
            _download_to_file(download_url, local_path)

            with open(local_path) as f:
                trajectory = Trajectory.model_validate_json(f.read())

            # SDK internal: build tool map from NovaAct's registered tools.
            tool_map = {tool.tool_name: tool for tool in nova._client_tools}
            program_runner = ProgramRunner(nova._event_handler, verbose=False)

            for traj_step in trajectory.steps:
                elapsed = time.time() - start_time
                if elapsed > _REPLAY_TIMEOUT_S:
                    raise TrajectoryReplayError(
                        f"replay timed out after {elapsed:.1f}s "
                        f"(limit {_REPLAY_TIMEOUT_S}s) for step {step_id}",
                        s3_key=s3_key,
                    )

                executable = traj_step.program.compile(tool_map)
                program_result = program_runner.run(executable)

                exception_result = program_result.has_exception()
                if exception_result and exception_result.error is not None:
                    raise exception_result.error
                if program_result.has_return():
                    break

            duration_ms = int((time.time() - start_time) * 1000)
            return ReplayResult(
                success=True,
                duration_ms=duration_ms,
                trajectory_s3_key=s3_key,
            )

        except TrajectoryReplayError:
            raise
        except Exception as exc:
            raise TrajectoryReplayError(
                f"replay failed for step {step_id}: {exc}",
                s3_key=s3_key,
                cause=exc,
            )
        finally:
            if local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError as cleanup_err:
                    logger.warning(
                        "Failed to clean up temp trajectory file %s: %s",
                        local_path, cleanup_err,
                    )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def save_trajectory(self, step_id: str, result) -> Optional[str]:
        """Upload the trajectory file emitted by ``nova.act(...)``.

        Returns the S3 key the server assigned, or ``None`` on any failure
        (best-effort; trajectory recording must never fail the execution).
        """
        trajectory_path = getattr(result, "trajectory_file_path", None)
        if not trajectory_path or not Path(trajectory_path).exists():
            logger.debug("No trajectory file produced for step %s", step_id)
            return None

        try:
            url_response = self._execution_api.create_trajectory_upload_url(
                self._usecase_id, step_id,
            )
            if not url_response:
                return None
            upload_url = url_response.get("upload_url")
            s3_key = url_response.get("s3_key")
            if not upload_url or not s3_key:
                logger.warning(
                    "Trajectory upload URL response missing fields for step %s",
                    step_id,
                )
                return None

            with open(trajectory_path, "rb") as f:
                put_response = requests.put(
                    upload_url,
                    data=f,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
            if not put_response.ok:
                logger.warning(
                    "Trajectory upload failed for step %s: HTTP %s",
                    step_id, put_response.status_code,
                )
                return None

            logger.info("Saved trajectory for step %s (s3_key=%s)", step_id, s3_key)
            return s3_key
        except Exception as exc:
            logger.warning(
                "Failed to save trajectory for step %s: %s", step_id, exc,
            )
            return None

    # ------------------------------------------------------------------
    # Cache-field cleanup (deferred)
    # ------------------------------------------------------------------

    def record_clear(self, step_id: str, fields: List[str]) -> None:
        """Queue cache-field removal for the given step.

        The engine drains the queue on the next ``update_step_status`` call
        via the ``clear_cache_fields`` param so cleanup piggybacks the
        existing API round-trip instead of adding another.
        """
        if not fields:
            return
        bucket = self._pending_clears.setdefault(step_id, [])
        for field in fields:
            if field not in bucket:
                bucket.append(field)

    def drain_clear(self, step_id: str) -> List[str]:
        """Return (and forget) queued cache-field cleanups for ``step_id``."""
        return self._pending_clears.pop(step_id, [])

    # Backwards-compatible alias matching the worker's method name.  Some
    # callers (or future shared code paths) refer to it as
    # ``clear_cache_fields``; we keep both names so a port of the worker's
    # navigation-step logic doesn't require rewriting call sites.
    def clear_cache_fields(self, step_id: str, fields: List[str]) -> None:
        """Queue cache-field removal (alias for :meth:`record_clear`).

        Exists for parity with ``web-app/worker/trajectory_manager.py``.
        Deferred, not immediate — the engine flushes queued clears into
        the next status update.
        """
        self.record_clear(step_id, fields)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _step_attr(step, name: str):
    """Read ``name`` from either a dict-shaped or object-shaped step."""
    if isinstance(step, dict):
        return step.get(name)
    return getattr(step, name, None)


def _download_to_file(url: str, local_path: str) -> None:
    """Stream a presigned GET response to disk.

    Raises on any HTTP error so the caller can convert to
    :class:`TrajectoryReplayError`.
    """
    with requests.get(url, stream=True, timeout=30) as resp:
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
