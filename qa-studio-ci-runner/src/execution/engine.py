"""Parallel test execution engine using real Nova Act SDK with local browsers.

Each usecase runs in its own thread (via asyncio.to_thread) with its own
local browser instance and NovaAct session. The async orchestration layer
(execute_all / execute_usecase) is preserved for parallel execution.
"""

import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from nova_act import NovaAct, Workflow

from ..api.executions import ExecutionAPI
from ..utils.errors import sanitize_error_message
from .artifacts import ArtifactCapture
from .artifact_uploader import ArtifactUploader
from .models import StepResult
from .step_executor import StepExecutor
from .workflow_manager import WorkflowManager

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Parallel test execution engine using real Nova Act SDK with local browsers."""

    def __init__(self, execution_api: ExecutionAPI, suite_execution_id: str, keep_artifacts: bool = False):
        self.execution_api = execution_api
        self.suite_execution_id = suite_execution_id
        self.keep_artifacts = keep_artifacts
        logger.info("ExecutionEngine initialized")

    # ------------------------------------------------------------------
    # Async orchestration (unchanged interface)
    # ------------------------------------------------------------------

    async def execute_all(self, executions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute all use cases in parallel via asyncio.gather."""
        logger.info(f"Starting parallel execution of {len(executions)} use cases...")

        tasks = [self.execute_usecase(execution) for execution in executions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed: List[Dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_msg = sanitize_error_message(str(result))
                logger.error(f"Execution {executions[i]['execution_id']} raised exception: {error_msg}")
                processed.append({
                    "execution_id": executions[i]["execution_id"],
                    "usecase_id": executions[i]["usecase_id"],
                    "usecase_name": executions[i]["usecase_name"],
                    "status": "failed",
                    "error": error_msg,
                    "duration": 0,
                })
            else:
                processed.append(result)

        return processed

    async def execute_usecase(self, execution: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single use case. Wraps sync Nova Act work in a thread."""
        execution_id = execution["execution_id"]
        usecase_id = execution["usecase_id"]
        usecase_name = execution["usecase_name"]

        logger.info(f"[{usecase_name}] Starting execution: {execution_id}")
        start_time = datetime.utcnow()

        # Setup artifact capture & uploader
        execution_dir = Path.home() / ".ci_runner" / self.suite_execution_id / execution_id
        execution_dir.mkdir(parents=True, exist_ok=True)
        artifact_capture = ArtifactCapture(execution_id, execution_dir / "artifacts")
        artifact_capture.setup_recording()
        artifact_capture.setup_logs()
        artifact_uploader = ArtifactUploader(self.execution_api.client)

        try:
            # Update status to running
            await self.execution_api.update_status(
                usecase_id=usecase_id,
                execution_id=execution_id,
                status="running",
            )

            # Fetch execution details (steps, variables, etc.)
            execution_details = await self.execution_api.get_execution(
                usecase_id=usecase_id,
                execution_id=execution_id,
            )

            # Run synchronous Nova Act execution in a thread
            result = await asyncio.to_thread(
                self._execute_usecase_sync,
                execution_details,
                usecase_id,
                execution_id,
                artifact_capture,
                artifact_uploader,
            )

            duration = (datetime.utcnow() - start_time).total_seconds()
            final_status = "success" if result["success"] else "failed"

            await self.execution_api.update_status(
                usecase_id=usecase_id,
                execution_id=execution_id,
                status=final_status,
                error_message=result.get("error"),
            )

            # Upload execution-level artifacts (logs)
            execution_artifacts = artifact_capture.get_execution_artifacts()
            await artifact_uploader.upload_execution_artifacts(
                usecase_id=usecase_id,
                execution_id=execution_id,
                artifacts=execution_artifacts,
            )

            status_label = "PASSED" if result["success"] else "FAILED"
            logger.info(f"[{usecase_name}] Completed: {status_label} ({duration:.1f}s)")

            return {
                "execution_id": execution_id,
                "usecase_id": usecase_id,
                "usecase_name": usecase_name,
                "status": final_status,
                "error": result.get("error"),
                "duration": duration,
            }

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            sanitized_error = sanitize_error_message(str(e))
            logger.error(f"[{usecase_name}] Failed: {sanitized_error}")

            try:
                await self.execution_api.update_status(
                    usecase_id=usecase_id,
                    execution_id=execution_id,
                    status="failed",
                    error_message=sanitized_error,
                )
            except Exception as api_err:
                logger.error(f"Failed to update status: {sanitize_error_message(str(api_err))}")

            return {
                "execution_id": execution_id,
                "usecase_id": usecase_id,
                "usecase_name": usecase_name,
                "status": "failed",
                "error": sanitized_error,
                "duration": duration,
            }

        finally:
            if self.keep_artifacts:
                artifact_capture.close_log_handler()
                logger.info(f"Keeping local artifacts at: {artifact_capture.temp_dir}")
            else:
                artifact_capture.cleanup()

    # ------------------------------------------------------------------
    # Synchronous execution (runs inside asyncio.to_thread)
    # ------------------------------------------------------------------

    @staticmethod
    def _run_async(coro) -> Any:
        """Run an async coroutine from synchronous code by spinning up a
        fresh event loop in a disposable thread.  This avoids the
        'Cannot run the event loop while another loop is running' error
        that occurs when Nova Act / Playwright already owns the thread's
        event loop."""
        def _worker():
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_worker).result()

    def _execute_usecase_sync(
        self,
        execution_details: Dict[str, Any],
        usecase_id: str,
        execution_id: str,
        artifact_capture: "ArtifactCapture",
        artifact_uploader: "ArtifactUploader",
    ) -> Dict[str, Any]:
        """Synchronous entry point for Nova Act execution.

        Runs inside asyncio.to_thread.  Any async API calls (step status
        updates, artifact uploads) are dispatched via _run_async which
        creates a throwaway thread + event loop to avoid conflicts with
        the event loop that Nova Act / Playwright manages internally.
        """
        # Bind the log filter to this worker thread so only this
        # usecase's logs are captured in its log file.
        artifact_capture.bind_to_current_thread()

        try:
            return self._execute_with_nova_act(
                execution_details, usecase_id, execution_id,
                artifact_capture, artifact_uploader,
            )
        except Exception as e:
            sanitized = sanitize_error_message(str(e))
            logger.error(f"Nova Act execution failed: {sanitized}")
            return {"success": False, "error": f"Nova Act execution failed: {sanitized}"}

    def _execute_with_nova_act(
        self,
        execution_details: Dict[str, Any],
        usecase_id: str,
        execution_id: str,
        artifact_capture: "ArtifactCapture",
        artifact_uploader: "ArtifactUploader",
    ) -> Dict[str, Any]:
        """Execute test steps using real Nova Act GA Service with a local browser."""

        starting_url = execution_details.get("starting_url", "")
        steps = execution_details.get("steps", [])
        variables = execution_details.get("variables", {})
        headers = execution_details.get("headers", {})

        # Create logs directory for this execution
        execution_dir = Path.home() / ".ci_runner" / self.suite_execution_id / execution_id
        logs_dir = str(execution_dir / "nova_act_logs")
        os.makedirs(logs_dir, exist_ok=True)

        # Build NovaAct kwargs — local browser
        headless = os.getenv("HEADLESS", "true").lower() != "false"
        nova_kwargs: Dict[str, Any] = {
            "starting_page": starting_url,
            "headless": headless,
            "logs_directory": logs_dir,
            "record_video": True,
        }

        # GA Service mode — create workflow
        region = os.getenv("AWS_REGION", "us-east-1")
        wf_manager = WorkflowManager()
        workflow_name = wf_manager.ensure_workflow(usecase_id)
        model_id = execution_details.get("model_id") or "nova-act-v1.0"

        with Workflow(
            workflow_definition_name=workflow_name,
            model_id=model_id,
            boto_session_kwargs={"region_name": region},
        ) as workflow:
            nova_kwargs["workflow"] = workflow
            return self._run_steps_with_nova(
                nova_kwargs, steps, variables, headers,
                starting_url, usecase_id, execution_id,
                artifact_capture, artifact_uploader, logs_dir,
            )

    def _run_steps_with_nova(
        self,
        nova_kwargs: Dict[str, Any],
        steps: List[Dict[str, Any]],
        variables: Dict[str, str],
        headers: Dict[str, str],
        starting_url: str,
        usecase_id: str,
        execution_id: str,
        artifact_capture: "ArtifactCapture",
        artifact_uploader: "ArtifactUploader",
        logs_dir: str,
    ) -> Dict[str, Any]:
        """Open NovaAct context and execute steps sequentially."""
        downloads_dir = Path.home() / ".ci_runner" / self.suite_execution_id / execution_id / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)

        with NovaAct(**nova_kwargs) as nova:
            # Capture Nova Act session ID (non-fatal)
            try:
                session_id = nova.get_session_id()
                if session_id:
                    self._run_async(
                        self.execution_api.update_session_id(
                            usecase_id=usecase_id,
                            execution_id=execution_id,
                            session_id=session_id,
                        )
                    )
                    logger.info(f"Captured Nova Act session ID: {session_id}")
                else:
                    logger.warning("nova.get_session_id() returned None")
            except Exception as e:
                logger.warning(f"Failed to capture Nova Act session ID: {sanitize_error_message(str(e))}")

            # Set custom HTTP headers if present
            if headers:
                parsed_headers = {
                    k: self._resolve_variables(v, variables, {})
                    for k, v in headers.items()
                }
                nova.page.set_extra_http_headers(parsed_headers)
                nova.go_to_url(starting_url)

            executor = StepExecutor(
                nova,
                downloads_dir=downloads_dir,
                secrets_resolver=self.execution_api.get_secret_value,
            )
            runtime_variables: Dict[str, str] = {}

            for step in steps:
                # The execution step ID is in the sk field: EXECUTION_STEP#{uuid}
                # This is what the API expects for step status updates
                sk = step.get("sk", "")
                execution_step_id = sk.replace("EXECUTION_STEP#", "") if sk.startswith("EXECUTION_STEP#") else step.get("step_id", "")
                sort_order = step.get("sort", 0)

                # Resolve variables in instruction
                instruction = self._resolve_variables(
                    step.get("instruction", ""), variables, runtime_variables,
                )
                resolved_step = {**step, "instruction": instruction, "usecase_id": usecase_id, "execution_id": execution_id}

                logger.info(f"Executing step {sort_order}: {instruction}")

                step_result: StepResult = executor.execute(
                    resolved_step, variables, runtime_variables,
                )

                # Report step status to API (non-fatal if it fails)
                step_status = "success" if step_result.success else "failed"
                try:
                    self._run_async(
                        self.execution_api.update_step_status(
                            usecase_id=usecase_id,
                            execution_id=execution_id,
                            step_id=execution_step_id,
                            status=step_status,
                            error_message=sanitize_error_message(step_result.logs) if step_result.logs else None,
                            actual_value=step_result.actual_value or None,
                            act_id=step_result.act_id or None,
                            logs=sanitize_error_message(step_result.logs) if step_result.logs else None,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to update step status: {sanitize_error_message(str(e))}")

                # Capture and upload step screenshot (non-fatal if it fails)
                try:
                    screenshot_path = artifact_capture.capture_step_screenshot(
                        nova.page, execution_step_id, sort_order,
                    )
                    if screenshot_path:
                        step_artifacts = artifact_capture.get_step_artifacts(execution_step_id)
                        self._run_async(
                            artifact_uploader.upload_step_artifacts(
                                usecase_id=usecase_id,
                                execution_id=execution_id,
                                step_id=execution_step_id,
                                artifacts=step_artifacts,
                            )
                        )
                except Exception as e:
                    logger.warning(f"Failed to capture/upload step screenshot: {sanitize_error_message(str(e))}")

                # Capture runtime variables from retrieve_value steps
                if (
                    step_result.success
                    and step.get("step_type") == "retrieve_value"
                    and step.get("capture_variable")
                    and step_result.actual_value
                ):
                    runtime_variables[step["capture_variable"]] = step_result.actual_value
                    logger.info(f"Captured runtime variable: {step['capture_variable']} = {step_result.actual_value}")

                # Stop on first failure
                if not step_result.success:
                    sanitized_logs = sanitize_error_message(step_result.logs)
                    logger.error(f"Step {sort_order} failed: {sanitized_logs}")
                    result = {
                        "success": False,
                        "error": f"Step {sort_order} failed: {sanitized_logs}",
                    }
                    break
            else:
                result = {"success": True}

        # NovaAct context has closed — collect and upload HTML trace logs
        self._upload_trace_logs(logs_dir, usecase_id, execution_id, artifact_uploader)

        return result

    def _upload_trace_logs(
        self,
        logs_dir: str,
        usecase_id: str,
        execution_id: str,
        artifact_uploader: "ArtifactUploader",
    ) -> None:
        """Collect all Nova Act trace files from logs_dir and upload as execution artifacts.
        
        Nova Act creates a nested directory structure under logs_directory:
          {session_id}/act_{act_id}_{description}.html
          {session_id}/act_{act_id}_{description}.json
        
        Files are uploaded preserving the relative path so the S3 key becomes:
          {usecase_id}/{execution_id}/{relative_path_from_logs_dir}
        """
        logs_path = Path(logs_dir)
        all_files = sorted(f for f in logs_path.rglob("*") if f.is_file())
        if not all_files:
            logger.info("No Nova Act trace files found to upload")
            return

        logger.info(f"Found {len(all_files)} Nova Act trace file(s) to upload")
        for trace_file in all_files:
            relative_path = str(trace_file.relative_to(logs_path))
            # Use 'recording' artifact type for video files, 'trace' for everything else
            artifact_type = "recording" if trace_file.suffix.lower() in (".webm", ".mp4") else "trace"
            try:
                self._run_async(
                    artifact_uploader._upload_execution_artifact(
                        usecase_id=usecase_id,
                        execution_id=execution_id,
                        artifact_type=artifact_type,
                        artifact_path=trace_file,
                        relative_path=relative_path,
                    )
                )
                logger.info(f"Uploaded {artifact_type} file: {relative_path}")
            except Exception as e:
                logger.warning(f"Failed to upload {artifact_type} file {relative_path}: {sanitize_error_message(str(e))}")

    # ------------------------------------------------------------------
    # Variable resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_variables(
        text: str,
        variables: Dict[str, str],
        runtime_variables: Dict[str, str],
    ) -> str:
        """Replace {{variable}} placeholders. Runtime vars take precedence."""
        merged = {**variables, **runtime_variables}

        def replace(match):
            var_name = match.group(1)
            if var_name in merged:
                return merged[var_name]
            logger.warning(f"Variable not found: {var_name}")
            return match.group(0)  # Leave unchanged

        return re.sub(r"\{\{(\w+)\}\}", replace, text)
