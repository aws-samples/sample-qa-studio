"""Execution API operations with async wrappers."""

import asyncio
import logging
from typing import Any, Dict, Optional

from qa_studio_cli.api.client import ApiClient

logger = logging.getLogger(__name__)


class ExecutionAPI:
    """Execution API operations with async support."""

    def __init__(self, client: ApiClient):
        self.client = client

    async def get_execution(
        self, usecase_id: str, execution_id: str
    ) -> Dict[str, Any]:
        """Fetch execution details including steps and variables.

        Makes multiple API calls to compose the full execution object:
        1. GET /usecase/{id}/executions/{executionId}
        2. GET /usecase/{id}/executions/{executionId}/steps
        3. GET /usecase/{id}/executions/{executionId}/variables
        """
        execution = await asyncio.to_thread(
            self.client.get,
            f"/usecase/{usecase_id}/executions/{execution_id}",
        )

        try:
            steps_response = await asyncio.to_thread(
                self.client.get,
                f"/usecase/{usecase_id}/executions/{execution_id}/steps",
            )
            execution["steps"] = steps_response.get("steps", [])
        except Exception as e:
            logger.warning("Failed to fetch steps: %s", e)
            execution["steps"] = []

        try:
            vars_response = await asyncio.to_thread(
                self.client.get,
                f"/usecase/{usecase_id}/executions/{execution_id}/variables",
            )
            exec_vars = vars_response.get("execution_variables", {})
            if isinstance(exec_vars, dict) and exec_vars:
                execution["variables"] = exec_vars
            else:
                raw_vars = vars_response.get("variables", [])
                variables = {}
                if isinstance(raw_vars, list):
                    for v in raw_vars:
                        if isinstance(v, dict) and "key" in v and "value" in v:
                            variables[v["key"]] = v["value"]
                elif isinstance(raw_vars, dict):
                    variables = raw_vars
                execution["variables"] = variables
        except Exception as e:
            logger.warning("Failed to fetch variables: %s", e)
            execution["variables"] = {}

        return execution

    async def update_status(
        self,
        usecase_id: str,
        execution_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update execution status."""
        payload = {"status": status}
        if error_message is not None:
            payload["error_message"] = error_message
        return await asyncio.to_thread(
            self.client.patch,
            f"/usecase/{usecase_id}/executions/{execution_id}/status",
            payload,
        )

    async def update_suite_status(
        self,
        suite_id: str,
        suite_execution_id: str,
        status: str,
    ) -> Dict[str, Any]:
        """Update suite execution status."""
        return await asyncio.to_thread(
            self.client.patch,
            f"/test-suites/{suite_id}/executions/{suite_execution_id}/status",
            {"status": status},
        )

    async def update_step_status(
        self,
        usecase_id: str,
        execution_id: str,
        step_id: str,
        status: str,
        error_message: Optional[str] = None,
        actual_value: Optional[str] = None,
        act_id: Optional[str] = None,
        logs: Optional[str] = None,
        clear_cache_fields: Optional[list] = None,
        step_definition_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update individual step status via API.

        ``clear_cache_fields`` piggybacks the R-API-6 extension so stale
        cache pointers on the step-definition record can be removed in the
        same API round-trip as a status update.  Valid entries are
        ``trajectory_s3_key``, ``trajectory_last_updated``, ``cached_steps``,
        ``cache_last_updated``; anything else is rejected server-side.

        ``step_definition_id`` identifies the canonical STEP record to clear
        fields from.  Required when ``clear_cache_fields`` is set because
        the URL's ``step_id`` is the execution-step UUID, not the step
        definition UUID.
        """
        payload: Dict[str, Any] = {"status": status}
        if error_message is not None:
            payload["error_message"] = error_message
        if actual_value is not None:
            payload["actual_value"] = actual_value
        if act_id is not None:
            payload["act_id"] = act_id
        if logs is not None:
            payload["logs"] = logs
        if clear_cache_fields:
            payload["clear_cache_fields"] = list(clear_cache_fields)
            if step_definition_id:
                payload["step_definition_id"] = step_definition_id
        return await asyncio.to_thread(
            self.client.patch,
            f"/usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/status",
            payload,
        )

    async def update_session_id(
        self,
        usecase_id: str,
        execution_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """Persist Nova Act session ID to the execution record."""
        return await asyncio.to_thread(
            self.client.patch,
            f"/usecase/{usecase_id}/executions/{execution_id}/status",
            {"status": "running", "nova_session_id": session_id},
        )

    async def create_runtime_variable(
        self,
        usecase_id: str,
        execution_id: str,
        key: str,
        value: str,
    ) -> Dict[str, Any]:
        """Persist a single captured runtime variable to the execution record.

        Called per-capture by the remote execution loop so the frontend's
        execution-variables panel reflects runtime variables as they are
        captured, rather than only at execution completion.  Implements the
        consumer side of R-API-1 in
        ``.kiro/specs/cli-unified-runner/requirements.md``.

        The caller is responsible for deciding when to call this — typically
        only after a successful ``retrieve_value`` or ``transform`` step
        produced a non-empty ``actual_value``.  On API failure the caller
        should log a warning and continue; in-memory state (``runtime_variables``
        and the TemplateParser) remains authoritative for the rest of the
        current execution.
        """
        return await asyncio.to_thread(
            self.client.post,
            f"/usecase/{usecase_id}/executions/{execution_id}/runtime-variables",
            json_body={"key": key, "value": value},
        )

    async def create_live_view(
        self,
        usecase_id: str,
        execution_id: str,
        live_view_url: str,
    ) -> Dict[str, Any]:
        """Publish the live-view URL for an execution (R-API-2).

        Called by the runner after a browser provisioner returns a
        :class:`~qa_studio_cli.runner.browser.BrowserHandle` carrying a
        ``live_view_url`` (today: AgentCore only).  On failure the caller
        should log a warning — a missing live view is a UX regression, not
        a correctness issue.
        """
        return await asyncio.to_thread(
            self.client.post,
            f"/usecase/{usecase_id}/executions/{execution_id}/live-view",
            json_body={"live_view_url": live_view_url},
        )

    async def delete_live_view(
        self,
        usecase_id: str,
        execution_id: str,
    ) -> None:
        """Tear down a previously-published live view (R-API-2).

        Called in the finally-block once the browser session has ended.
        The server returns 204 on success and 404 when nothing was
        published — both are acceptable outcomes; callers should treat
        404 as "already gone".
        """
        try:
            await asyncio.to_thread(
                self.client.delete,
                f"/usecase/{usecase_id}/executions/{execution_id}/live-view",
            )
        except Exception as exc:
            # 404 is expected when create_live_view wasn't called (or the
            # server already cleared the record).  Any other failure is
            # logged by the caller via sanitize_error_message.
            message = str(exc)
            if "404" in message or "not found" in message.lower():
                return
            raise

    async def update_mobile_metadata(
        self,
        usecase_id: str,
        execution_id: str,
        device_farm_session_arn: Optional[str] = None,
        device_name: Optional[str] = None,
        device_os_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Partial-update the mobile metadata on an execution (R-API-3).

        At least one field must be provided (the server rejects empty
        bodies).  Missing fields are NOT cleared server-side — this is a
        partial update.  Called by the runner at two points in a mobile
        execution: right after the DeviceFarm session starts (ARN only),
        and again after the session stops (final ARN + optional device
        details).
        """
        payload: Dict[str, Any] = {}
        if device_farm_session_arn is not None:
            payload["device_farm_session_arn"] = device_farm_session_arn
        if device_name is not None:
            payload["device_name"] = device_name
        if device_os_version is not None:
            payload["device_os_version"] = device_os_version
        if not payload:
            raise ValueError(
                "update_mobile_metadata requires at least one field",
            )
        return await asyncio.to_thread(
            self.client.patch,
            f"/usecase/{usecase_id}/executions/{execution_id}/mobile-metadata",
            payload,
        )

    def get_trajectory_download_url(
        self,
        usecase_id: str,
        step_id: str,
    ) -> Optional[str]:
        """Fetch a presigned GET URL for a step's recorded trajectory.

        Returns the URL on success, or ``None`` when no trajectory has been
        recorded for the step (API returns 404).  Any other error raises.
        Synchronous because the caller is the navigation-step executor,
        which runs inside ``asyncio.to_thread`` already.

        Implements the consumer side of R-API-5 (download-url).
        """
        try:
            response = self.client.get(
                f"/usecase/{usecase_id}/steps/{step_id}/trajectory/download-url"
            )
        except Exception as exc:
            # The ApiClient raises on non-2xx.  Distinguish 404 (expected —
            # "no trajectory yet") from real errors so the caller can skip
            # replay without logging an error.
            message = str(exc)
            if "404" in message or "not found" in message.lower():
                return None
            raise
        return response.get("download_url")

    def create_trajectory_upload_url(
        self,
        usecase_id: str,
        step_id: str,
        content_type: str = "application/json",
    ) -> Optional[Dict[str, Any]]:
        """Reserve an S3 upload URL for a fresh trajectory JSON.

        Returns ``{"upload_url": str, "s3_key": str, "expires_in": int}`` or
        ``None`` on API failure.  The server atomically records the
        trajectory pointer on the step record when the URL is issued — see
        ``web-app/lambdas/endpoints/create_trajectory_upload_url.py``.

        Synchronous for the same reason as
        :meth:`get_trajectory_download_url`.

        Implements the consumer side of R-API-5 (upload-url).
        """
        try:
            return self.client.post(
                f"/usecase/{usecase_id}/steps/{step_id}/trajectory/upload-url",
                json_body={"content_type": content_type},
            )
        except Exception:
            return None

    def get_secret_value(self, usecase_id: str, secret_key: str) -> Optional[str]:
        """Fetch the decrypted value of a usecase secret via API."""
        try:
            response = self.client.get(
                f"/usecase/{usecase_id}/secrets/{secret_key}/value"
            )
            return response.get("value")
        except Exception:
            return None

    async def request_recording_download(
        self,
        usecase_id: str,
        execution_id: str,
        session_arn: str,
        nova_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Request async Device Farm recording download via the Studio API."""
        payload: Dict[str, Any] = {"session_arn": session_arn}
        if nova_session_id:
            payload["nova_session_id"] = nova_session_id
        return await asyncio.to_thread(
            self.client.post,
            f"/usecase/{usecase_id}/executions/{execution_id}/download-recording",
            json_body=payload,
        )

