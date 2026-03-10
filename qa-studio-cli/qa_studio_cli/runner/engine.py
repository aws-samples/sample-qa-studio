"""Parallel test execution engine using real Nova Act SDK with local browsers.

Each usecase runs in its own thread (via asyncio.to_thread) with its own
local browser instance and NovaAct session. This module is only imported
lazily via the `run` command.
"""

import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from nova_act import NovaAct, Workflow

from qa_studio_cli.api.executions import ExecutionAPI
from qa_studio_cli.models.execution import StepResult
from qa_studio_cli.runner.artifacts import ArtifactCapture
from qa_studio_cli.runner.artifact_uploader import ArtifactUploader
from qa_studio_cli.runner.step_executor import StepExecutor
from qa_studio_cli.runner.workflow_manager import WorkflowManager
from qa_studio_cli.utils.errors import sanitize_error_message

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Parallel test execution engine using real Nova Act SDK with local browsers."""

    def __init__(
        self,
        execution_api: ExecutionAPI = None,
        suite_execution_id: str = None,
        keep_artifacts: bool = False,
    ):
        self.execution_api = execution_api
        self.suite_execution_id = suite_execution_id
        self.keep_artifacts = keep_artifacts
        logger.info("ExecutionEngine initialized")

    # ------------------------------------------------------------------
    # Local-only execution (no remote state management)
    # ------------------------------------------------------------------

    def execute_usecase_local(
        self,
        usecase_id: str,
        usecase_name: str,
        starting_url: str,
        steps: List[Dict[str, Any]],
        variables: Dict[str, str],
        secrets: list,
        headers: Dict[str, str],
        region: str,
        model_id: str,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute use case locally without remote state management."""
        from qa_studio_cli.models.execution import (
            LocalExecutionResult, StepResultDetail, ArtifactPaths,
        )

        start_time = datetime.utcnow()
        artifacts_dir = Path.home() / ".qa-studio" / "artifacts" / usecase_id
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = str(artifacts_dir / "nova_act_logs")
        os.makedirs(logs_dir, exist_ok=True)

        log_path = artifacts_dir / "logs.txt"
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        logging.getLogger().addHandler(file_handler)

        step_results: List[StepResultDetail] = []
        overall_status = "success"
        video_path = None

        try:
            headless = os.getenv("HEADLESS", "true").lower() != "false"
            nova_kwargs: Dict[str, Any] = {
                "starting_page": starting_url,
                "headless": headless,
                "logs_directory": logs_dir,
                "record_video": True,
            }
            if user_agent:
                nova_kwargs["user_agent"] = user_agent

            wf_manager = WorkflowManager()
            workflow_name = wf_manager.ensure_workflow(usecase_id)

            with Workflow(
                workflow_definition_name=workflow_name,
                model_id=model_id or "nova-act-v1.0",
                boto_session_kwargs={"region_name": region or "us-east-1"},
            ) as workflow:
                nova_kwargs["workflow"] = workflow

                with NovaAct(**nova_kwargs) as nova:
                    # Set custom HTTP headers if provided
                    if headers:
                        logger.info("Setting %d custom HTTP header(s)", len(headers))
                        nova.page.set_extra_http_headers(headers)
                        nova.go_to_url(starting_url)

                    secrets_dict = {s.get("key", s.get("secret_key", "")): s for s in secrets}

                    def _local_secret_resolver(uc_id: str, secret_key: str):
                        secret = secrets_dict.get(secret_key)
                        return secret.get("value") if secret else None

                    executor = StepExecutor(nova, secrets_resolver=_local_secret_resolver)
                    runtime_variables: Dict[str, str] = {}

                    for step in steps:
                        step_id = step.get("step_id", step.get("sk", ""))
                        sort_order = step.get("sort", 0)
                        step_start = datetime.utcnow()

                        instruction = self._resolve_variables(
                            step.get("instruction", ""), variables, runtime_variables,
                        )
                        resolved_step = {**step, "instruction": instruction, "usecase_id": usecase_id}

                        logger.info("[local] Executing step %d: %s", sort_order, instruction)
                        step_result: StepResult = executor.execute(resolved_step, variables, runtime_variables)

                        step_duration = (datetime.utcnow() - step_start).total_seconds()
                        step_status = "success" if step_result.success else "failed"

                        step_results.append(StepResultDetail(
                            step_id=step_id,
                            step_type=step.get("step_type", ""),
                            instruction=instruction,
                            status=step_status,
                            duration=step_duration,
                            error=sanitize_error_message(step_result.logs) if not step_result.success and step_result.logs else None,
                        ))

                        if (
                            step_result.success
                            and step.get("step_type") == "retrieve_value"
                            and step.get("capture_variable")
                            and step_result.actual_value
                        ):
                            runtime_variables[step["capture_variable"]] = step_result.actual_value

                        if not step_result.success:
                            overall_status = "failed"
                            logger.error("[local] Step %d failed: %s", sort_order, sanitize_error_message(step_result.logs))
                            break

            logs_path = Path(logs_dir)
            for f in logs_path.rglob("*"):
                if f.suffix.lower() in (".webm", ".mp4") and f.is_file():
                    video_path = str(f)
                    break

        except Exception as e:
            overall_status = "failed"
            logger.error("[local] Execution failed: %s", sanitize_error_message(str(e)))
        finally:
            file_handler.close()
            logging.getLogger().removeHandler(file_handler)

        duration = (datetime.utcnow() - start_time).total_seconds()

        result = LocalExecutionResult(
            status=overall_status,
            usecase_id=usecase_id,
            usecase_name=usecase_name,
            duration=duration,
            steps=step_results,
            artifacts=ArtifactPaths(
                video=video_path,
                logs=str(log_path) if log_path.exists() else None,
            ),
        )
        return result.model_dump(by_alias=True)

    # ------------------------------------------------------------------
    # Async orchestration
    # ------------------------------------------------------------------

    async def execute_all(self, executions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute all use cases in parallel via asyncio.gather."""
        logger.info("Starting parallel execution of %d use cases...", len(executions))
        tasks = [self.execute_usecase(execution) for execution in executions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed: List[Dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_msg = sanitize_error_message(str(result))
                logger.error("Execution %s raised exception: %s", executions[i]["execution_id"], error_msg)
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

        logger.info("[%s] Starting execution: %s", usecase_name, execution_id)
        start_time = datetime.utcnow()

        suite_id = self.suite_execution_id or "standalone"
        execution_dir = Path.home() / ".ci_runner" / suite_id / execution_id
        execution_dir.mkdir(parents=True, exist_ok=True)
        artifact_capture = ArtifactCapture(execution_id, execution_dir / "artifacts")
        artifact_capture.setup_recording()
        artifact_capture.setup_logs()
        artifact_uploader = ArtifactUploader(self.execution_api.client)

        try:
            await self.execution_api.update_status(
                usecase_id=usecase_id, execution_id=execution_id, status="running",
            )
            execution_details = await self.execution_api.get_execution(
                usecase_id=usecase_id, execution_id=execution_id,
            )
            result = await asyncio.to_thread(
                self._execute_usecase_sync,
                execution_details, usecase_id, execution_id,
                artifact_capture, artifact_uploader,
            )
            duration = (datetime.utcnow() - start_time).total_seconds()
            final_status = "success" if result["success"] else "failed"

            await self.execution_api.update_status(
                usecase_id=usecase_id, execution_id=execution_id,
                status=final_status, error_message=result.get("error"),
            )
            execution_artifacts = artifact_capture.get_execution_artifacts()
            await artifact_uploader.upload_execution_artifacts(
                usecase_id=usecase_id, execution_id=execution_id, artifacts=execution_artifacts,
            )

            status_label = "PASSED" if result["success"] else "FAILED"
            logger.info("[%s] Completed: %s (%.1fs)", usecase_name, status_label, duration)

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
            logger.error("[%s] Failed: %s", usecase_name, sanitized_error)
            try:
                await self.execution_api.update_status(
                    usecase_id=usecase_id, execution_id=execution_id,
                    status="failed", error_message=sanitized_error,
                )
            except Exception as api_err:
                logger.error("Failed to update status: %s", sanitize_error_message(str(api_err)))
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
                logger.info("Keeping local artifacts at: %s", artifact_capture.temp_dir)
            else:
                artifact_capture.cleanup()

    # ------------------------------------------------------------------
    # Synchronous execution (runs inside asyncio.to_thread)
    # ------------------------------------------------------------------

    @staticmethod
    def _run_async(coro) -> Any:
        """Run an async coroutine from synchronous code by spinning up a
        fresh event loop in a disposable thread."""
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
        artifact_capture: ArtifactCapture,
        artifact_uploader: ArtifactUploader,
    ) -> Dict[str, Any]:
        """Synchronous entry point for Nova Act execution."""
        artifact_capture.bind_to_current_thread()
        try:
            return self._execute_with_nova_act(
                execution_details, usecase_id, execution_id,
                artifact_capture, artifact_uploader,
            )
        except Exception as e:
            sanitized = sanitize_error_message(str(e))
            logger.error("Nova Act execution failed: %s", sanitized)
            return {"success": False, "error": f"Nova Act execution failed: {sanitized}"}

    def _execute_with_nova_act(
        self,
        execution_details: Dict[str, Any],
        usecase_id: str,
        execution_id: str,
        artifact_capture: ArtifactCapture,
        artifact_uploader: ArtifactUploader,
    ) -> Dict[str, Any]:
        """Execute test steps using real Nova Act GA Service with a local browser."""
        starting_url = execution_details.get("starting_url", "")
        steps = execution_details.get("steps", [])
        variables = execution_details.get("variables", {})
        headers = execution_details.get("headers", {})

        suite_id = self.suite_execution_id or "standalone"
        execution_dir = Path.home() / ".ci_runner" / suite_id / execution_id
        logs_dir = str(execution_dir / "nova_act_logs")
        os.makedirs(logs_dir, exist_ok=True)

        headless = os.getenv("HEADLESS", "true").lower() != "false"
        nova_kwargs: Dict[str, Any] = {
            "starting_page": starting_url,
            "headless": headless,
            "logs_directory": logs_dir,
            "record_video": True,
        }

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
        artifact_capture: ArtifactCapture,
        artifact_uploader: ArtifactUploader,
        logs_dir: str,
    ) -> Dict[str, Any]:
        """Open NovaAct context and execute steps sequentially."""
        suite_id = self.suite_execution_id or "standalone"
        downloads_dir = Path.home() / ".ci_runner" / suite_id / execution_id / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)

        with NovaAct(**nova_kwargs) as nova:
            try:
                session_id = nova.get_session_id()
                if session_id:
                    self._run_async(
                        self.execution_api.update_session_id(
                            usecase_id=usecase_id, execution_id=execution_id, session_id=session_id,
                        )
                    )
                    logger.info("Captured Nova Act session ID: %s", session_id)
                else:
                    logger.warning("nova.get_session_id() returned None")
            except Exception as e:
                logger.warning("Failed to capture Nova Act session ID: %s", sanitize_error_message(str(e)))

            if headers:
                parsed_headers = {
                    k: self._resolve_variables(v, variables, {})
                    for k, v in headers.items()
                }
                nova.page.set_extra_http_headers(parsed_headers)
                nova.go_to_url(starting_url)

            executor = StepExecutor(
                nova, downloads_dir=downloads_dir,
                secrets_resolver=self.execution_api.get_secret_value,
            )
            runtime_variables: Dict[str, str] = {}

            for step in steps:
                sk = step.get("sk", "")
                execution_step_id = sk.replace("EXECUTION_STEP#", "") if sk.startswith("EXECUTION_STEP#") else step.get("step_id", "")
                sort_order = step.get("sort", 0)

                instruction = self._resolve_variables(
                    step.get("instruction", ""), variables, runtime_variables,
                )
                resolved_step = {**step, "instruction": instruction, "usecase_id": usecase_id, "execution_id": execution_id}

                logger.info("Executing step %d: %s", sort_order, instruction)
                step_result: StepResult = executor.execute(resolved_step, variables, runtime_variables)

                step_status = "success" if step_result.success else "failed"
                try:
                    self._run_async(
                        self.execution_api.update_step_status(
                            usecase_id=usecase_id, execution_id=execution_id,
                            step_id=execution_step_id, status=step_status,
                            error_message=sanitize_error_message(step_result.logs) if step_result.logs else None,
                            actual_value=step_result.actual_value or None,
                            act_id=step_result.act_id or None,
                            logs=sanitize_error_message(step_result.logs) if step_result.logs else None,
                        )
                    )
                except Exception as e:
                    logger.warning("Failed to update step status: %s", sanitize_error_message(str(e)))

                try:
                    screenshot_path = artifact_capture.capture_step_screenshot(
                        nova.page, execution_step_id, sort_order,
                    )
                    if screenshot_path:
                        step_artifacts = artifact_capture.get_step_artifacts(execution_step_id)
                        self._run_async(
                            artifact_uploader.upload_step_artifacts(
                                usecase_id=usecase_id, execution_id=execution_id,
                                step_id=execution_step_id, artifacts=step_artifacts,
                            )
                        )
                except Exception as e:
                    logger.warning("Failed to capture/upload step screenshot: %s", sanitize_error_message(str(e)))

                if (
                    step_result.success
                    and step.get("step_type") == "retrieve_value"
                    and step.get("capture_variable")
                    and step_result.actual_value
                ):
                    runtime_variables[step["capture_variable"]] = step_result.actual_value
                    logger.info("Captured runtime variable: %s = %s", step["capture_variable"], step_result.actual_value)

                if not step_result.success:
                    sanitized_logs = sanitize_error_message(step_result.logs)
                    logger.error("Step %d failed: %s", sort_order, sanitized_logs)
                    result = {"success": False, "error": f"Step {sort_order} failed: {sanitized_logs}"}
                    break
            else:
                result = {"success": True}

        self._upload_trace_logs(logs_dir, usecase_id, execution_id, artifact_uploader)
        return result

    def _upload_trace_logs(
        self, logs_dir: str, usecase_id: str, execution_id: str,
        artifact_uploader: ArtifactUploader,
    ) -> None:
        """Collect all Nova Act trace files and upload as execution artifacts."""
        logs_path = Path(logs_dir)
        all_files = sorted(f for f in logs_path.rglob("*") if f.is_file())
        if not all_files:
            logger.info("No Nova Act trace files found to upload")
            return

        logger.info("Found %d Nova Act trace file(s) to upload", len(all_files))
        for trace_file in all_files:
            relative_path = str(trace_file.relative_to(logs_path))
            artifact_type = "recording" if trace_file.suffix.lower() in (".webm", ".mp4") else "trace"
            try:
                self._run_async(
                    artifact_uploader._upload_execution_artifact(
                        usecase_id=usecase_id, execution_id=execution_id,
                        artifact_type=artifact_type, artifact_path=trace_file,
                        relative_path=relative_path,
                    )
                )
                logger.info("Uploaded %s file: %s", artifact_type, relative_path)
            except Exception as e:
                logger.warning("Failed to upload %s file %s: %s", artifact_type, relative_path, sanitize_error_message(str(e)))

    # ------------------------------------------------------------------
    # Variable resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_variables(
        text: str, variables: Dict[str, str], runtime_variables: Dict[str, str],
    ) -> str:
        """Replace {{variable}} placeholders. Runtime vars take precedence."""
        merged = {**variables, **runtime_variables}

        def replace(match):
            var_name = match.group(1)
            if var_name in merged:
                return merged[var_name]
            logger.warning("Variable not found: %s", var_name)
            return match.group(0)

        return re.sub(r"\{\{(\w+)\}\}", replace, text)
