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
from typing import Any, Dict, List

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
            region: str,
            model_id: str,
            mobile_config: Dict[str, Any] | None = None,
        ) -> Dict[str, Any]:
            """Execute use case locally without remote state management."""
            from qa_studio_cli.models.execution import (
                LocalExecutionResult, StepResultDetail, ArtifactPaths,
            )

            start_time = datetime.utcnow()
            artifacts_dir = Path("/tmp/qa-studio-artifacts") / usecase_id
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
                    "headless": headless,
                    "logs_directory": logs_dir,
                    "record_video": True,
                }

                # Build mobile actuator if this is a mobile use case
                actuator = None
                if mobile_config:
                    actuator, effective_starting_page = self._build_mobile_actuator(mobile_config)
                    nova_kwargs["actuator"] = actuator
                    nova_kwargs["starting_page"] = effective_starting_page
                    nova_kwargs["ignore_screen_dims_check"] = True
                    nova_kwargs["ignore_https_errors"] = True
                else:
                    nova_kwargs["starting_page"] = starting_url

                wf_manager = WorkflowManager()
                workflow_name = wf_manager.ensure_workflow(usecase_id)

                with Workflow(
                    workflow_definition_name=workflow_name,
                    model_id=model_id or "nova-act-v1.0",
                    boto_session_kwargs={"region_name": region or "us-east-1"},
                ) as workflow:
                    nova_kwargs["workflow"] = workflow

                    with NovaAct(**nova_kwargs) as nova:
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

    def _build_mobile_actuator(self, mobile_config: Dict[str, Any]) -> tuple:
        """Build a DeviceFarmActuator from mobile config fields.

        Returns:
            Tuple of (actuator, starting_page_url)
        """
        import tempfile
        import boto3 as _boto3

        from nova_act_mobile.actuation.device_farm_actuator import DeviceFarmActuator
        from nova_act_mobile.actuation.mobile_actuator import MobileActuator
        from nova_act_mobile.app import MobileAppConfig
        from nova_act_mobile.device_farm import DeviceFarmUploadConfig

        platform_str = mobile_config.get("platform", "").upper()

        # Build MobileAppConfig
        if platform_str == "ANDROID":
            app_config = MobileAppConfig.for_android(
                app_package=mobile_config["app_package"],
                app_activity=mobile_config["app_activity"],
            )
        elif platform_str == "IOS":
            app_config = MobileAppConfig.for_ios(
                bundle_id=mobile_config["bundle_id"],
            )
        else:
            raise ValueError(f"Unsupported mobile platform: {platform_str}")

        # Resolve app binary: prefer app_path (local file) > app_arn > Device Farm lookup > S3 download
        upload_config = None
        app_path = mobile_config.get("app_path", "")
        app_arn = mobile_config.get("app_arn", "")
        app_binary_s3_path = mobile_config.get("app_binary_s3_path", "")

        if app_path:
            # Local file provided via --app-path — upload directly to Device Farm
            if not os.path.isfile(app_path):
                raise ValueError(f"App binary not found: {app_path}")
            filename = os.path.basename(app_path)
            logger.info("Using local app binary: %s", app_path)
            upload_config = DeviceFarmUploadConfig(
                app_name=filename,
                app_path=app_path,
            )
        elif app_arn:
            # App already uploaded to Device Farm — use the ARN directly
            logger.info("Using existing Device Farm app ARN: %s", app_arn[:80])
            upload_config = DeviceFarmUploadConfig(app_name="app", app_arn=app_arn)
        elif app_binary_s3_path:
            # Try to find an existing Device Farm upload by filename before downloading
            from nova_act_mobile.device_farm import DeviceFarmClient as DFClient

            filename = os.path.basename(app_binary_s3_path)
            # Ensure filename has the right extension
            if not filename.endswith((".apk", ".ipa")):
                ext = ".ipa" if platform_str == "IOS" else ".apk"
                filename = f"{filename}{ext}"

            df_client = DFClient()
            project_arn = mobile_config.get("device_farm_project_arn", "") or None
            resolved_project_arn = df_client.get_project_arn(project_arn)
            upload_type = app_config.platform.device_farm_upload_type

            existing_arn = df_client.find_existing_upload(
                project_arn=resolved_project_arn,
                upload_name=filename,
                upload_type=upload_type,
            )

            if existing_arn:
                logger.info("Found existing Device Farm upload for %s: %s", filename, existing_arn[:80])
                upload_config = DeviceFarmUploadConfig(app_name=filename, app_arn=existing_arn)
            else:
                # No existing upload — need to download from S3 and upload to Device Farm
                s3_bucket = os.environ.get("S3_BUCKET", "")
                if not s3_bucket:
                    raise ValueError(
                        f"App binary '{filename}' not found in Device Farm and S3_BUCKET "
                        "environment variable is not set. Either run the test from the web UI first "
                        "(to upload the binary to Device Farm), or set S3_BUCKET to download it."
                    )
                tmp_dir = tempfile.mkdtemp(prefix="qa_studio_mobile_")
                local_path = os.path.join(tmp_dir, filename)
                logger.info("Downloading app binary from s3://%s/%s", s3_bucket, app_binary_s3_path)
                s3_client = _boto3.client("s3")
                s3_client.download_file(s3_bucket, app_binary_s3_path, local_path)
                upload_config = DeviceFarmUploadConfig(
                    app_name=filename,
                    app_path=local_path,
                )

        # Build actuator
        device_arn = mobile_config.get("device_arn", "") or None
        project_arn = mobile_config.get("device_farm_project_arn", "") or None

        actuator = DeviceFarmActuator(
            app_config=app_config,
            upload_config=upload_config,
            project_arn=project_arn,
            device_arn=device_arn,
        )

        starting_page = MobileActuator.app_url(app_config.app_identifier)
        logger.info("Mobile actuator built: platform=%s, starting_page=%s", platform_str, starting_page)

        return actuator, starting_page



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

            # Request async recording download for mobile executions
            if execution_details.get("test_platform") == "mobile":
                try:
                    session_arn = execution_details.get("device_farm_session_arn", "")
                    # Also check if the actuator stored it
                    if not session_arn:
                        session_arn = result.get("device_farm_session_arn", "")
                    if session_arn:
                        await self.execution_api.request_recording_download(
                            usecase_id=usecase_id,
                            execution_id=execution_id,
                            session_arn=session_arn,
                        )
                        logger.info("[%s] Recording download requested", usecase_name)
                    else:
                        logger.warning("[%s] No Device Farm session ARN — cannot request recording", usecase_name)
                except Exception as rec_err:
                    logger.warning("[%s] Failed to request recording download: %s", usecase_name, rec_err)

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
        """Execute test steps using real Nova Act GA Service."""
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
            "headless": headless,
            "logs_directory": logs_dir,
            "record_video": True,
        }

        test_platform = execution_details.get("test_platform", "web")
        is_mobile = test_platform == "mobile"

        if is_mobile:
            # Parse app_identifier: Android = "package/activity", iOS = "bundle_id"
            app_identifier = execution_details.get("app_identifier", "")
            platform_val = execution_details.get("platform", "")
            app_package = ""
            app_activity = ""
            bundle_id = ""
            if platform_val == "ANDROID" and "/" in app_identifier:
                parts = app_identifier.split("/", 1)
                app_package = parts[0]
                app_activity = parts[1]
            elif platform_val == "IOS":
                bundle_id = app_identifier

            mobile_config = {
                "platform": platform_val,
                "app_package": app_package,
                "app_activity": app_activity,
                "bundle_id": bundle_id,
                "device_arn": execution_details.get("device_arn", ""),
                "app_binary_s3_path": execution_details.get("app_binary_s3_path", ""),
                "app_arn": execution_details.get("app_arn", ""),
                "device_farm_project_arn": execution_details.get("device_farm_project_arn", ""),
            }
            actuator, effective_starting_page = self._build_mobile_actuator(mobile_config)
            nova_kwargs["actuator"] = actuator
            nova_kwargs["starting_page"] = effective_starting_page
            nova_kwargs["ignore_screen_dims_check"] = True
            nova_kwargs["ignore_https_errors"] = True
        else:
            nova_kwargs["starting_page"] = starting_url

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
            result = self._run_steps_with_nova(
                nova_kwargs, steps, variables, headers,
                starting_url, usecase_id, execution_id,
                artifact_capture, artifact_uploader, logs_dir,
                is_mobile=is_mobile,
            )

            # Capture Device Farm session ARN for recording download
            if is_mobile and hasattr(actuator, 'stopped_session_arn') and actuator.stopped_session_arn:
                result["device_farm_session_arn"] = actuator.stopped_session_arn

            return result

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
        is_mobile: bool = False,
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

            # Headers and URL navigation are browser-only
            if headers and not is_mobile:
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

                # Screenshots via nova.page are browser-only
                if not is_mobile:
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
            is_video = trace_file.suffix.lower() in (".webm", ".mp4")
            is_session_recording = is_video and trace_file.name.startswith("session_video")
            artifact_type = "recording" if is_session_recording else "trace"
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
