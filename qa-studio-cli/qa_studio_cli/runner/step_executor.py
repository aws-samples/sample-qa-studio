"""Step execution dispatcher for Nova Act.

Routes each step to the correct Nova Act method based on step_type.
All nova_act imports are at module level since this module is only
loaded lazily via the run command.
"""

import logging
import os
import re
from pathlib import Path
from typing import Callable, Optional

from nova_act import NovaAct, BOOL_SCHEMA

from qa_studio_cli.models.execution import StepResult

logger = logging.getLogger(__name__)

STRING_SCHEMA = {"type": "string"}
NUMBER_SCHEMA = {"type": "number"}

CLICK_PROMPT = """
The `agentClick` statement supports a `clickType` argument to specify the type of click to perform.

Syntax:
agentClick(bbox: string, clickType: string): Clicks the specified box with the given click type.

Available clickType options:
- 'left': Single left click (default)
- 'left-double': Double left click
- 'right': Right click

Example:
agentClick("bbox", "left-double") performs a double-click on the bbox.

Prompt:
"""


class StepExecutor:
    """Executes individual test steps by type."""

    def __init__(
        self,
        nova: NovaAct,
        downloads_dir: Optional[Path] = None,
        secrets_resolver: Optional[Callable[[str, str], Optional[str]]] = None,
    ):
        self.nova = nova
        self.downloads_dir = downloads_dir or (Path.home() / ".ci_runner" / "downloads")
        self.secrets_resolver = secrets_resolver

    def execute(self, step: dict, variables: dict, runtime_variables: dict) -> StepResult:
        """Dispatch step execution by step_type."""
        step_type = step.get("step_type", "navigation")
        match step_type:
            case "navigation":
                return self._execute_navigation(step)
            case "validation":
                return self._execute_validation(step)
            case "retrieve_value":
                return self._execute_retrieve_value(step)
            case "url":
                return self._execute_url(step)
            case "assertion":
                return self._execute_assertion(step, runtime_variables)
            case "secret":
                return self._execute_secret(step)
            case "download":
                return self._execute_download(step)
            case _:
                logger.warning("Unknown step_type '%s', falling back to navigation", step_type)
                return self._execute_navigation(step)

    def _execute_navigation(self, step: dict) -> StepResult:
        instruction = step.get("instruction", "")
        if step.get("enable_advanced_click_types"):
            instruction = f"{CLICK_PROMPT}\n\n{instruction}"
        try:
            result = self.nova.act(instruction)
            act_id = self._extract_act_id(result)
            return StepResult(success=True, act_id=act_id)
        except Exception as e:
            act_id = self._extract_act_id_from_exception(e)
            return StepResult(success=False, act_id=act_id, logs=str(e))

    def _execute_validation(self, step: dict) -> StepResult:
        validation_type = step.get("validation_type", "string")
        operator = step.get("validation_operator", "exact")
        expected_raw = step.get("validation_value", "")
        instruction = step.get("instruction", "")
        schema = self._schema_for_type(validation_type)
        try:
            result = self.nova.act_get(instruction, schema=schema)
            act_id = self._extract_act_id(result)
            raw_value = result.parsed_response
            success = self._compare(validation_type, operator, expected_raw, raw_value)
            actual_str = str(raw_value) if raw_value is not None else ""
            logs = "" if success else (
                f"Validation failed: expected ({operator}) '{expected_raw}', got '{actual_str}'"
            )
            return StepResult(success=success, act_id=act_id, logs=logs, actual_value=actual_str)
        except Exception as e:
            act_id = self._extract_act_id_from_exception(e)
            return StepResult(success=False, act_id=act_id, logs=str(e))

    def _execute_retrieve_value(self, step: dict) -> StepResult:
        # Programmatic URL extraction — bypasses vision model
        if step.get("value_source") == "url":
            import re
            try:
                current_url = self.nova.page.url
                pattern = step.get("instruction", "").strip()
                if pattern:
                    match = re.search(pattern, current_url)
                    if match and match.groups():
                        value = match.group(1)
                    elif match:
                        value = match.group(0)
                    else:
                        return StepResult(success=False, act_id="url_extract",
                                          logs=f"Regex '{pattern}' did not match URL: {current_url}")
                else:
                    value = current_url
                return StepResult(success=True, act_id="url_extract", actual_value=value)
            except Exception as e:
                return StepResult(success=False, act_id="url_extract", logs=str(e))

        value_type = step.get("value_type", "string")
        instruction = step.get("instruction", "")
        schema = self._schema_for_type(value_type)
        try:
            result = self.nova.act_get(instruction, schema=schema)
            act_id = self._extract_act_id(result)
            raw_value = result.parsed_response
            if raw_value is None:
                return StepResult(success=False, act_id=act_id, logs="No value retrieved from page")
            actual_str = str(raw_value)
            if value_type in ("string", ""):
                actual_str = actual_str.strip().strip('"').strip("'")
            return StepResult(success=True, act_id=act_id, actual_value=actual_str)
        except Exception as e:
            act_id = self._extract_act_id_from_exception(e)
            return StepResult(success=False, act_id=act_id, logs=str(e))

    def _execute_url(self, step: dict) -> StepResult:
        instruction = step.get("instruction", "")
        try:
            self.nova.go_to_url(instruction)
            return StepResult(success=True)
        except Exception as e:
            return StepResult(success=False, logs=str(e))

    def _execute_assertion(self, step: dict, runtime_variables: dict) -> StepResult:
        var_name = step.get("assertion_variable", "")
        validation_type = step.get("validation_type", "string")
        operator = step.get("validation_operator", "exact")
        expected_raw = step.get("validation_value", "")
        if var_name not in runtime_variables:
            return StepResult(
                success=False, logs=f"Runtime variable '{var_name}' not found",
                actual_value="VARIABLE_NOT_FOUND",
            )
        actual_value = runtime_variables[var_name]
        success = self._compare(validation_type, operator, expected_raw, actual_value)
        logs = "" if success else (
            f"Assertion failed: {var_name} ({operator}) expected '{expected_raw}', got '{actual_value}'"
        )
        return StepResult(success=success, logs=logs, actual_value=str(actual_value))

    def _execute_secret(self, step: dict) -> StepResult:
        secret_key = step.get("secret_key", "")
        instruction = step.get("instruction", "")
        usecase_id = step.get("usecase_id", "")
        if not self.secrets_resolver:
            return StepResult(success=False, logs="No secrets resolver configured")
        try:
            secret_value = self.secrets_resolver(usecase_id, secret_key)
            if secret_value is None:
                return StepResult(success=False, logs=f"Secret key '{secret_key}' not found")
            result = self.nova.act(
                f"{instruction} you must return true if the action was successful",
                schema=BOOL_SCHEMA,
            )
            act_id = self._extract_act_id(result)
            self.nova.page.keyboard.type(secret_value)
            if not result.parsed_response:
                return StepResult(success=False, act_id=act_id, logs="Secret step action was not successful")
            return StepResult(success=True, act_id=act_id)
        except Exception as e:
            act_id = self._extract_act_id_from_exception(e)
            return StepResult(success=False, act_id=act_id, logs=str(e))

    def _execute_download(self, step: dict) -> StepResult:
        instruction = step.get("instruction", "")
        cdp_session = None
        download_data: dict = {"file": None, "filename": None}
        try:
            cdp_session = self.nova.page.context.new_cdp_session(self.nova.page)
            cdp_session.send("Network.enable")
            cdp_session.send("Network.setRequestInterception", {
                "patterns": [{"urlPattern": "*", "interceptionStage": "HeadersReceived"}],
            })

            def on_request_intercepted(event):
                self._handle_download_intercept(event, cdp_session, download_data)

            cdp_session.on("Network.requestIntercepted", on_request_intercepted)

            with self.nova.page.expect_download(timeout=20000) as download_info:
                result = self.nova.act(instruction)

            act_id = self._extract_act_id(result)
            playwright_download = download_info.value

            import time as _time
            _time.sleep(1)

            if download_data["file"]:
                temp_path = download_data["file"]
                filename = download_data["filename"]
            else:
                import urllib.request, ssl
                filename = playwright_download.suggested_filename
                self.downloads_dir.mkdir(parents=True, exist_ok=True)
                temp_path = str(self.downloads_dir / filename)
                # Validate URL scheme to prevent SSRF
                from urllib.parse import urlparse
                parsed_url = urlparse(playwright_download.url)
                if parsed_url.scheme not in ('http', 'https'):
                    raise ValueError(f"Unsupported URL scheme: {parsed_url.scheme}")
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(playwright_download.url, context=ctx) as resp:  # nosec B310
                    with open(temp_path, "wb") as f:
                        while chunk := resp.read(8192):
                            f.write(chunk)

            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

            return StepResult(
                success=True, act_id=act_id,
                actual_value=filename or "",
                logs=f"Downloaded: {filename}",
            )
        except Exception as e:
            act_id = self._extract_act_id_from_exception(e)
            return StepResult(success=False, act_id=act_id, logs=f"Download failed: {e}")
        finally:
            if cdp_session:
                try:
                    cdp_session.detach()
                except Exception:
                    pass

    def _handle_download_intercept(self, event: dict, cdp_session, download_data: dict) -> None:
        """Handle a CDP Network.requestIntercepted event for downloads."""
        interception_id = event.get("interceptionId")
        response_headers = event.get("responseHeaders", [])
        content_disposition = None
        if isinstance(response_headers, list):
            for h in response_headers:
                if isinstance(h, dict) and h.get("name", "").lower() == "content-disposition":
                    content_disposition = h.get("value", "")
                    break
        elif isinstance(response_headers, dict):
            content_disposition = (
                response_headers.get("content-disposition")
                or response_headers.get("Content-Disposition")
            )
        if content_disposition and "attachment" in content_disposition.lower():
            import urllib.parse
            filename = None
            match = re.search(r"filename\*=(?:UTF-8'')?([^;\s]+)", content_disposition)
            if match:
                filename = urllib.parse.unquote(match.group(1))
            else:
                match = re.search(r"filename[^;=\n]*=(['\"]?)(.+?)\1", content_disposition)
                if match:
                    filename = match.group(2)
            if not filename:
                url = event.get("request", {}).get("url", "")
                filename = urllib.parse.unquote(url.split("/")[-1].split("?")[0]) if url else "download"
            file_path = self._download_from_stream(cdp_session, interception_id, filename)
            if file_path:
                download_data["file"] = file_path
                download_data["filename"] = filename
        else:
            try:
                cdp_session.send("Network.continueInterceptedRequest", {"interceptionId": interception_id})
            except Exception:
                pass

    def _download_from_stream(self, cdp_session, interception_id: str, filename: str) -> Optional[str]:
        """Download file content from a CDP interception stream."""
        import base64
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        temp_path = str(self.downloads_dir / filename)
        try:
            resp = cdp_session.send(
                "Network.takeResponseBodyForInterceptionAsStream",
                {"interceptionId": interception_id},
            )
            stream_handle = resp.get("stream")
            if not stream_handle:
                return None
            with open(temp_path, "wb") as f:
                while True:
                    read_resp = cdp_session.send("IO.read", {"handle": stream_handle})
                    if read_resp.get("data"):
                        f.write(base64.b64decode(read_resp["data"]))
                    if read_resp.get("eof"):
                        break
            try:
                cdp_session.send("IO.close", {"handle": stream_handle})
            except Exception:
                pass
            try:
                cdp_session.send(
                    "Network.continueInterceptedRequest",
                    {"interceptionId": interception_id, "errorReason": "Aborted"},
                )
            except Exception:
                pass
            return temp_path
        except Exception as e:
            logger.error("Error downloading from stream: %s", e)
            return None

    @staticmethod
    def _schema_for_type(type_name: str) -> dict:
        if type_name == "number":
            return NUMBER_SCHEMA
        elif type_name == "bool":
            return BOOL_SCHEMA
        return STRING_SCHEMA

    @staticmethod
    def _compare(validation_type: str, operator: str, expected_raw, actual_raw) -> bool:
        """Compare expected vs actual using the given type and operator."""
        if validation_type == "bool":
            expected = str(expected_raw).lower() == "true"
            actual = str(actual_raw).lower() == "true" if actual_raw is not None else False
            return actual == expected
        if validation_type == "number":
            try:
                expected_num = float(expected_raw)
                actual_num = float(actual_raw) if actual_raw is not None else 0.0
            except (ValueError, TypeError):
                return False
            match operator:
                case "equals": return actual_num == expected_num
                case "greater_then": return actual_num > expected_num
                case "less_then": return actual_num < expected_num
                case "greater_or_equal_then": return actual_num >= expected_num
                case "less_or_equal_then": return actual_num <= expected_num
                case _: return actual_num == expected_num
        expected_str = str(expected_raw).strip().strip('"').strip("'")
        actual_str = str(actual_raw).strip().strip('"').strip("'") if actual_raw is not None else ""
        match operator:
            case "exact": return actual_str == expected_str
            case "exact_case_insensitive": return actual_str.lower() == expected_str.lower()
            case "contains": return bool(re.search(re.escape(expected_str), actual_str))
            case "contains_case_insensitive": return bool(re.search(re.escape(expected_str), actual_str, re.IGNORECASE))
            case "not_equal": return actual_str != expected_str
            case _: return actual_str == expected_str

    @staticmethod
    def _extract_act_id(result) -> str:
        if result and hasattr(result, "metadata") and hasattr(result.metadata, "act_id"):
            return result.metadata.act_id
        return ""

    @staticmethod
    def _extract_act_id_from_exception(e: Exception) -> str:
        if hasattr(e, "metadata") and hasattr(e.metadata, "act_id"):
            return e.metadata.act_id
        return "error"
