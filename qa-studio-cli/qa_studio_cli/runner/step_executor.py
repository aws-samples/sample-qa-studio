"""Step execution dispatcher for Nova Act.

Routes each step to the correct Nova Act method based on step_type.
All nova_act imports are at module level since this module is only
loaded lazily via the run command.
"""

import base64
import json
import logging
import math
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from nova_act import NovaAct, BOOL_SCHEMA

from qa_studio_cli.models.execution import StepResult

logger = logging.getLogger(__name__)

STRING_SCHEMA = {"type": "string"}
NUMBER_SCHEMA = {"type": "number"}


def _safe_eval_math(expression: str, variables: dict | None = None) -> float | int:
    """Safe AST-based arithmetic evaluator. Mirrors worker/transform/math_evaluator.py."""
    import ast
    import operator as _op

    _MAX_EXPONENT = 1000
    _MAX_RESULT = 1e308  # prevent intermediate results from blowing up memory

    _BIN = {ast.Add: _op.add, ast.Sub: _op.sub, ast.Mult: _op.mul,
            ast.Div: _op.truediv, ast.Mod: _op.mod, ast.Pow: _op.pow}
    _UN = {ast.UAdd: _op.pos, ast.USub: _op.neg}
    variables = variables or {}

    def _check_magnitude(value, context="Result"):
        if isinstance(value, (int, float)) and abs(value) > _MAX_RESULT:
            raise ValueError(f"{context} magnitude too large (abs > {_MAX_RESULT})")
        return value

    def _walk(node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError(f"Non-numeric constant: {node.value!r}")
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValueError(f"Unknown variable: '{node.id}'")
            val = variables[node.id]
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise ValueError(f"Variable '{node.id}' must be numeric, got {type(val).__name__}: {val!r}")
            return val
        if isinstance(node, ast.BinOp):
            fn = _BIN.get(type(node.op))
            if not fn:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            left, right = _walk(node.left), _walk(node.right)
            if isinstance(node.op, ast.Pow):
                if isinstance(right, (int, float)) and abs(right) > _MAX_EXPONENT:
                    raise ValueError(f"Exponent too large: {right} (max {_MAX_EXPONENT})")
                if isinstance(left, (int, float)) and abs(left) > _MAX_EXPONENT:
                    raise ValueError(f"Base too large for exponentiation: {left}")
            result = fn(left, right)
            return _check_magnitude(result)
        if isinstance(node, ast.UnaryOp):
            fn = _UN.get(type(node.op))
            if not fn:
                raise ValueError(f"Unsupported unary: {type(node.op).__name__}")
            return fn(_walk(node.operand))
        raise ValueError(f"Disallowed expression: {type(node).__name__}")

    tree = ast.parse(expression.strip(), mode="eval")
    return _walk(tree.body)

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
            case "browser":
                return self._execute_browser(step)
            case "transform":
                return self._execute_transform(step, variables, runtime_variables)
            case "network_assertion":
                return self._execute_network_assertion(step)
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

            time.sleep(1)

            if download_data["file"]:
                temp_path = download_data["file"]
                filename = download_data["filename"]
            else:
                filename = playwright_download.suggested_filename
                self.downloads_dir.mkdir(parents=True, exist_ok=True)
                temp_path = str(self.downloads_dir / filename)
                # Validate URL scheme to prevent SSRF
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

    def _execute_browser(self, step: dict) -> StepResult:
        """Execute a browser step (reload, back, forward, navigate)."""
        action = step.get("browser_action", "")
        if not action:
            return StepResult(success=False, logs="browser_action is required")
        raw_args = step.get("browser_args")
        args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args else (raw_args or {})
        try:
            page = self.nova.page
            match action:
                case "reload":
                    if args.get("hard"):
                        page.evaluate("() => location.reload()")
                    else:
                        page.reload()
                    return StepResult(success=True)
                case "back":
                    url_before = page.url
                    response = page.go_back()
                    if response is None and page.url == url_before:
                        return StepResult(success=False, logs="Browser back failed: no previous history entry")
                    return StepResult(success=True)
                case "forward":
                    url_before = page.url
                    response = page.go_forward()
                    if response is None and page.url == url_before:
                        return StepResult(success=False, logs="Browser forward failed: no forward history entry")
                    return StepResult(success=True)
                case "navigate":
                    url = args.get("url", "")
                    if not url:
                        return StepResult(success=False, logs="browser_args.url is required for navigate")
                    _parsed = urlparse(url)
                    if _parsed.scheme not in ("http", "https"):
                        return StepResult(success=False, logs=f"URL scheme must be http or https, got '{_parsed.scheme}'")
                    self.nova.go_to_url(url)
                    return StepResult(success=True)
                case _:
                    return StepResult(success=False, logs=f"Unknown browser_action: '{action}'")
        except Exception as e:
            return StepResult(success=False, logs=str(e))

    def _execute_transform(self, step: dict, variables: dict, runtime_variables: dict) -> StepResult:
        """Execute a transform step (math, string ops, etc.)."""
        operation = step.get("transform_operation", "")
        if not operation:
            return StepResult(success=False, logs="transform_operation is required")
        capture_var = step.get("capture_variable", "")
        if not capture_var:
            return StepResult(success=False, logs="capture_variable is required for transform steps")
        try:
            raw_args = json.loads(step.get("transform_args", "{}") or "{}")
        except (ValueError, TypeError) as exc:
            return StepResult(success=False, logs=f"Invalid transform_args JSON: {exc}")

        # Resolve {{ variables }} in string args
        merged = {**variables, **runtime_variables}
        resolved = {}
        for k, v in raw_args.items():
            if isinstance(v, str):
                resolved[k] = re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: merged.get(m.group(1), m.group(0)), v)
            elif isinstance(v, list):
                resolved[k] = [
                    re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: merged.get(m.group(1), m.group(0)), i) if isinstance(i, str) else i
                    for i in v
                ]
            else:
                resolved[k] = v

        try:
            result = self._run_transform(operation, resolved)
        except Exception as exc:
            return StepResult(success=False, logs=f"Transform '{operation}' failed: {exc}")

        actual = str(result)
        return StepResult(success=True, actual_value=actual)

    @staticmethod
    def _run_transform(operation: str, args: dict):
        """Execute a single transform operation. Pure function, no side effects."""
        match operation:
            case "math":
                return _safe_eval_math(args.get("expression", ""))
            case "round":
                return round(float(args["value"]), int(args.get("digits", 0)))
            case "floor":
                return math.floor(float(args["value"]))
            case "ceil":
                return math.ceil(float(args["value"]))
            case "abs":
                return abs(float(args["value"]))
            case "min":
                vals = [float(v) for v in args["values"]]
                if not vals:
                    raise ValueError("min requires at least one value")
                return min(vals)
            case "max":
                vals = [float(v) for v in args["values"]]
                if not vals:
                    raise ValueError("max requires at least one value")
                return max(vals)
            case "concat":
                return "".join(str(v) for v in args.get("values", []))
            case "upper":
                return str(args["value"]).upper()
            case "lower":
                return str(args["value"]).lower()
            case "trim":
                return str(args["value"]).strip()
            case "replace":
                return str(args["value"]).replace(args["old"], args["new"])
            case "substring":
                end = int(args["end"]) if args.get("end") is not None else None
                return str(args["value"])[int(args["start"]):end]
            case "length":
                return len(str(args["value"]))
            case "to_number":
                try:
                    return float(args["value"])
                except ValueError:
                    raise ValueError(f"Cannot convert '{args['value']}' to number")
            case "to_string":
                return str(args["value"])
            case "to_int":
                try:
                    return int(float(args["value"]))
                except ValueError:
                    raise ValueError(f"Cannot convert '{args['value']}' to int")
            case "regex_extract":
                try:
                    m = re.search(args["pattern"], str(args["value"]))
                except re.error as exc:
                    raise ValueError(f"Invalid regex: {exc}")
                if not m:
                    raise ValueError(f"Pattern did not match")
                group = int(args.get("group", 0))
                try:
                    return m.group(group)
                except IndexError:
                    raise ValueError(f"Group {group} not found")
            case "format":
                if re.search(r'\{[^}]*[.\[]', args["template"]):
                    raise ValueError("Format template must not contain attribute or index access")
                return args["template"].format(*args.get("args", []))
            case _:
                raise ValueError(f"Unknown transform operation: '{operation}'")

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

    def _execute_network_assertion(self, step: dict) -> StepResult:
        """Execute a network_assertion step.

        Observe (and optionally mock) an HTTP request triggered by a Nova Act
        action, then optionally assert on the response.  Mirrors the worker
        executor — see ``web-app/worker/network_assertion_step.py``.

        Behaviour:
          - validates URL pattern, method allow-list, body/mock/response
            size caps, JSON validity
          - request match-type ∈ {exact, subset, schema}
          - response match-type ∈ {subset, schema} (``exact`` is rejected)
          - response status must be an integer in [100, 599] when set
          - captures ``response.body()`` after the response promise resolves
            and size-checks it always — an oversize response fails the step
            even with no body assertion configured
          - summary segments are included only when the corresponding
            assertion actually ran
          - uses try/finally to guarantee page.unroute() cleanup
          - truncates request/response bodies in logs to 500 chars
          - caching is not applied to this step type by design
        """
        import json as _json

        from qa_studio_cli.runner.network_matcher import (
            match_exact,
            match_schema,
            match_subset,
            validate_body_size,
        )

        DEFAULT_TIMEOUT_S = 15
        MAX_TIMEOUT_S = 120
        ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        REQUEST_MATCH_TYPES = {"exact", "subset", "schema"}
        RESPONSE_MATCH_TYPES = {"subset", "schema"}
        LOG_BODY_MAX = 500
        MIN_HTTP_STATUS = 100
        MAX_HTTP_STATUS = 599

        url_pattern = step.get("network_url_pattern") or ""
        if not url_pattern:
            return StepResult(
                success=False,
                logs="network_url_pattern is required for network_assertion steps",
            )

        method_expected = (step.get("network_method") or "").upper() or None
        if method_expected is not None and method_expected not in ALLOWED_METHODS:
            return StepResult(success=False, logs=f"invalid network_method: {method_expected!r}")

        expected_body = step.get("network_request_body")
        req_match_type = (step.get("network_body_match_type") or "exact").lower()
        if expected_body and req_match_type not in REQUEST_MATCH_TYPES:
            return StepResult(
                success=False, logs=f"invalid network_body_match_type: {req_match_type!r}"
            )

        ok, err = validate_body_size(expected_body)
        if not ok:
            return StepResult(success=False, logs=f"network_request_body: {err}")

        mock_raw = step.get("network_mock_response")
        ok, err = validate_body_size(mock_raw)
        if not ok:
            return StepResult(success=False, logs=f"network_mock_response: {err}")

        # Response-side validation.
        expected_response_body = step.get("network_response_body")
        resp_match_type_raw = step.get("network_response_body_match_type")
        resp_match_type = (resp_match_type_raw or "").lower() or None
        if expected_response_body and resp_match_type is None:
            resp_match_type = "subset"
        if resp_match_type is not None and resp_match_type not in RESPONSE_MATCH_TYPES:
            return StepResult(
                success=False,
                logs=(
                    f"invalid network_response_body_match_type: {resp_match_type!r} "
                    '("exact" is not permitted on the response side)'
                ),
            )

        ok, err = validate_body_size(expected_response_body)
        if not ok:
            return StepResult(success=False, logs=f"network_response_body: {err}")

        status_expected = None
        raw_status = step.get("network_response_status")
        if raw_status is not None:
            try:
                status_expected = int(raw_status)
            except (TypeError, ValueError):
                return StepResult(
                    success=False, logs="network_response_status must be an integer",
                )
            if status_expected < MIN_HTTP_STATUS or status_expected > MAX_HTTP_STATUS:
                return StepResult(
                    success=False,
                    logs=(
                        f"network_response_status must be between "
                        f"{MIN_HTTP_STATUS} and {MAX_HTTP_STATUS}"
                    ),
                )

        mock_cfg = None
        if mock_raw:
            try:
                mock_cfg = _json.loads(mock_raw)
            except (ValueError, TypeError) as exc:
                return StepResult(
                    success=False, logs=f"network_mock_response is not valid JSON: {exc}"
                )
            if not isinstance(mock_cfg, dict):
                return StepResult(
                    success=False, logs="network_mock_response must be a JSON object"
                )

        passthrough = bool(step.get("network_mock_passthrough"))

        raw_timeout = step.get("network_timeout")
        try:
            timeout_s = int(raw_timeout) if raw_timeout is not None else DEFAULT_TIMEOUT_S
        except (TypeError, ValueError):
            timeout_s = DEFAULT_TIMEOUT_S
        if timeout_s <= 0:
            timeout_s = DEFAULT_TIMEOUT_S
        timeout_s = min(timeout_s, MAX_TIMEOUT_S)
        timeout_ms = timeout_s * 1000

        page = getattr(self.nova, "page", None)
        if page is None:
            return StepResult(
                success=False,
                logs="nova.page is not available; cannot set up network interception",
            )

        def _serialize_body(body):
            if body is None:
                return ""
            if isinstance(body, (bytes, bytearray)):
                return body.decode("utf-8", errors="replace")
            if isinstance(body, str):
                return body
            return _json.dumps(body)

        def _build_handler(cfg: dict, pass_through: bool):
            status = cfg.get("status", 200)
            mock_body = cfg.get("body")
            mock_headers = cfg.get("headers") or {}
            if pass_through:
                def handler(route):
                    real = route.fetch()
                    merged_headers = {**(real.headers or {}), **mock_headers}
                    merged_body = (
                        _serialize_body(mock_body) if "body" in cfg else real.body()
                    )
                    merged_status = cfg.get("status", real.status)
                    route.fulfill(
                        status=merged_status, body=merged_body, headers=merged_headers,
                    )
            else:
                def handler(route):
                    route.fulfill(
                        status=status,
                        body=_serialize_body(mock_body),
                        headers=mock_headers,
                    )
            return handler

        def _truncate(body):
            if not body:
                return "<empty>"
            if len(body) <= LOG_BODY_MAX:
                return body
            return body[:LOG_BODY_MAX] + f"...<truncated {len(body) - LOG_BODY_MAX} chars>"

        def _capture_response_body(resp):
            try:
                data = resp.body()
            except Exception:
                return None
            if data is None:
                return None
            if isinstance(data, (bytes, bytearray)):
                return data.decode("utf-8", errors="replace")
            return str(data)

        def _dispatch_matcher(mt, expected, actual):
            if mt == "schema":
                return match_schema(expected, actual)
            if mt == "subset":
                return match_subset(expected, actual)
            return match_exact(expected, actual)

        # Import the runtime cap so the oversize-captured check uses the
        # same threshold as the pre-submit validators.
        from qa_studio_cli.runner.network_matcher import MAX_BODY_SIZE as _MAX_BODY

        route_registered = False
        act_id = ""
        try:
            if mock_cfg is not None:
                page.route(url_pattern, _build_handler(mock_cfg, passthrough))
                route_registered = True

            with page.expect_response(url_pattern, timeout=timeout_ms) as response_info:
                try:
                    act_result = self.nova.act(step.get("instruction", ""))
                    act_id = self._extract_act_id(act_result)
                except Exception as exc:
                    act_id = self._extract_act_id_from_exception(exc)
                    return StepResult(
                        success=False, act_id=act_id, logs=f"Nova Act action failed: {exc}",
                    )

            response = response_info.value
            request = response.request
            summary_parts = []

            # --- Request-side: method --------------------------------------
            if method_expected is not None:
                actual_method = (request.method or "").upper()
                if actual_method != method_expected:
                    return StepResult(
                        success=False,
                        act_id=act_id,
                        logs=f"method mismatch: expected {method_expected}, got {actual_method}",
                        actual_value=f"method={actual_method}:fail",
                    )
                summary_parts.append(f"method={method_expected}")

            # --- Request-side: body ----------------------------------------
            if expected_body:
                body = request.post_data
                if isinstance(body, (bytes, bytearray)):
                    body = body.decode("utf-8", errors="replace")
                logger.info(
                    "network_assertion step: captured %s %s body=%s",
                    request.method, request.url, _truncate(body),
                )
                if body is None:
                    return StepResult(
                        success=False,
                        act_id=act_id,
                        logs="captured request had no body",
                        actual_value=f"body_match={req_match_type}:fail",
                    )
                ok, diff = _dispatch_matcher(req_match_type, expected_body, body)
                if not ok:
                    return StepResult(
                        success=False,
                        act_id=act_id,
                        logs=f"request body mismatch ({req_match_type}): {diff}",
                        actual_value=f"body_match={req_match_type}:fail",
                    )
                summary_parts.append(f"body_match={req_match_type}:pass")
            else:
                logger.info(
                    "network_assertion step: captured %s %s",
                    request.method, request.url,
                )

            # --- Response capture + always size-check ----------------------
            captured_response_body = _capture_response_body(response)
            if captured_response_body is not None:
                body_bytes = len(captured_response_body.encode("utf-8"))
                if body_bytes > _MAX_BODY:
                    return StepResult(
                        success=False,
                        act_id=act_id,
                        logs=(
                            f"captured response body size {body_bytes} exceeds "
                            f"maximum {_MAX_BODY} bytes"
                        ),
                        actual_value="resp_body=cap:fail",
                    )

            # --- Response-side: status -------------------------------------
            if status_expected is not None:
                actual_status = getattr(response, "status", None)
                try:
                    actual_status_int = int(actual_status) if actual_status is not None else None
                except (TypeError, ValueError):
                    actual_status_int = None
                if actual_status_int != status_expected:
                    return StepResult(
                        success=False,
                        act_id=act_id,
                        logs=(
                            f"response status mismatch: expected {status_expected}, "
                            f"got {actual_status!r}"
                        ),
                        actual_value=f"resp_status={actual_status_int or actual_status}:fail",
                    )
                summary_parts.append(f"resp_status={status_expected}")

            # --- Response-side: body ---------------------------------------
            if expected_response_body:
                logger.info(
                    "network_assertion step: captured response status=%s body=%s",
                    getattr(response, "status", "?"),
                    _truncate(captured_response_body),
                )
                if captured_response_body is None:
                    return StepResult(
                        success=False,
                        act_id=act_id,
                        logs="captured response had no body",
                        actual_value=f"resp_body={resp_match_type}:fail",
                    )
                ok, diff = _dispatch_matcher(
                    resp_match_type, expected_response_body, captured_response_body,
                )
                if not ok:
                    return StepResult(
                        success=False,
                        act_id=act_id,
                        logs=f"response body mismatch ({resp_match_type}): {diff}",
                        actual_value=f"resp_body={resp_match_type}:fail",
                    )
                summary_parts.append(f"resp_body={resp_match_type}:pass")

            summary = " ".join(summary_parts) if summary_parts else "captured"
            return StepResult(success=True, act_id=act_id, actual_value=summary)

        except Exception as exc:
            err_name = type(exc).__name__
            if "Timeout" in err_name:
                msg = f"no request matched '{url_pattern}' within {timeout_s}s"
            else:
                msg = f"{err_name}: {exc}"
            return StepResult(success=False, act_id=act_id, logs=msg)
        finally:
            if route_registered:
                try:
                    page.unroute(url_pattern)
                except Exception as exc:
                    logger.warning("Failed to unroute %s: %s", url_pattern, exc)

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
