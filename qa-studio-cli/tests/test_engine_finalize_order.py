"""The runner uploads artifacts before it sets the final execution status.

A cloud worker's execution capability (X-QA-Execution-Token) is only valid
while the execution is pending/running, so every call for the execution
has to happen before the final status update.
"""
from __future__ import annotations

import asyncio
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

# Stub the optional runner extras, as in test_engine_start_retry.py.
sys.modules.setdefault("nova_act", ModuleType("nova_act"))
_nova = sys.modules["nova_act"]
for _name, _value in (("NovaAct", type("NovaAct", (), {})), ("BOOL_SCHEMA", {"type": "boolean"}),
                      ("Workflow", type("Workflow", (), {}))):
    if not hasattr(_nova, _name):
        setattr(_nova, _name, _value)
sys.modules.setdefault("nova_act.types", ModuleType("nova_act.types"))
_errors_mod = sys.modules.setdefault("nova_act.types.errors", ModuleType("nova_act.types.errors"))
if not hasattr(_errors_mod, "StartFailed"):
    _errors_mod.StartFailed = type("StartFailed", (Exception,), {})

from qa_studio_cli.runner import engine as engine_mod  # noqa: E402
from qa_studio_cli.runner.engine import ExecutionEngine  # noqa: E402


def _run(test_platform="web", success=True):
    calls = []
    execution_api = MagicMock()
    execution_api.client = MagicMock()

    async def update_status(**kwargs):
        calls.append(("status", kwargs["status"]))

    async def get_execution(**kwargs):
        return {"test_platform": test_platform, "device_farm_session_arn": "arn:session"}

    async def request_recording_download(**kwargs):
        calls.append(("recording", None))

    execution_api.update_status = AsyncMock(side_effect=update_status)
    execution_api.get_execution = AsyncMock(side_effect=get_execution)
    execution_api.request_recording_download = AsyncMock(side_effect=request_recording_download)

    uploader = MagicMock()

    async def upload(**kwargs):
        calls.append(("artifacts", None))

    uploader.upload_execution_artifacts = AsyncMock(side_effect=upload)

    engine = ExecutionEngine(execution_api=execution_api)
    with patch.object(engine_mod, "ArtifactUploader", return_value=uploader), \
            patch.object(engine_mod, "ArtifactCapture", return_value=MagicMock()), \
            patch.object(engine, "_execute_usecase_sync", return_value={"success": success}):
        result = asyncio.run(engine.execute_usecase(
            {"execution_id": "ex-1", "usecase_id": "uc-1", "usecase_name": "UC"}))
    return calls, result


def test_artifacts_uploaded_before_final_status():
    calls, result = _run()
    assert calls == [("status", "running"), ("artifacts", None), ("status", "success")]
    assert result["status"] == "success"


def test_mobile_recording_requested_before_final_status():
    calls, _ = _run(test_platform="mobile", success=False)
    assert calls == [("status", "running"), ("artifacts", None), ("recording", None), ("status", "failed")]
