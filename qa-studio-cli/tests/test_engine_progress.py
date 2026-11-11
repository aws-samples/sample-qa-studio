"""The engine announces tests and steps through ``runner.progress``.

Both step loops (local-only ``execute_usecase_local`` and the remote
``_run_steps_with_nova``) must call ``progress.step_started`` with the
*resolved* step and instruction, prefixing the test name only when the
engine was built with ``show_test_name_on_steps=True`` (suite runs).
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:  # pragma: no cover - environment dependent
    import nova_act  # noqa: F401
    import tenacity  # noqa: F401
except ImportError:  # pragma: no cover - environment dependent
    sys.modules.setdefault("nova_act", ModuleType("nova_act"))
    _nova = sys.modules["nova_act"]
    if not hasattr(_nova, "NovaAct"):
        _nova.NovaAct = type("NovaAct", (), {})
    if not hasattr(_nova, "BOOL_SCHEMA"):
        _nova.BOOL_SCHEMA = {"type": "boolean"}
    if not hasattr(_nova, "Workflow"):
        _nova.Workflow = type("Workflow", (), {})
    sys.modules.setdefault("tenacity", ModuleType("tenacity"))
    _t = sys.modules["tenacity"]
    if not hasattr(_t, "retry"):
        def _retry(*_a, **_kw):
            def _wrap(fn):
                return fn
            return _wrap
        _t.retry = _retry
        _t.stop_after_attempt = lambda *a, **kw: None
        _t.wait_exponential = lambda *a, **kw: None
        _t.retry_if_exception_type = lambda *a, **kw: None

from qa_studio_cli.models.execution import StepResult  # noqa: E402
from qa_studio_cli.runner import engine as engine_mod  # noqa: E402
from qa_studio_cli.runner import progress  # noqa: E402
from qa_studio_cli.runner.browser import BrowserHandle  # noqa: E402
from qa_studio_cli.runner.engine import ExecutionEngine  # noqa: E402


class _FakeNovaAct:
    def __init__(self, **_kwargs):
        self.page = MagicMock()
        self.go_to_url = MagicMock()

    def get_session_id(self):
        return "sess-1"

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class _FakeWorkflow:
    def __init__(self, **_kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class _FakeExecutor:
    def __init__(self, *_a, **_kw):
        pass

    def execute(self, step, variables, runtime_variables):
        return StepResult(success=True)


STEPS = [
    {"step_id": "s1", "sort": 1, "step_type": "navigation", "instruction": "Open {{base}}/login"},
    {
        "step_id": "s2", "sort": 2, "step_type": "validation",
        "instruction": "Check greeting", "validation_value": "Hi {{user}}",
    },
    {
        "step_id": "s3", "sort": 3, "step_type": "navigation", "instruction": "Type {{email}}",
        "repeat_row_index": 2, "repeat_row_total": 2,
        "row_variables": {"email": "b@x.test", "RepeatIndex": "2", "RepeatTotal": "2"},
    },
]
VARIABLES = {"base": "https://e.test", "user": "Jane", "email": "a@x.test"}


@pytest.fixture
def fakes():
    handle = BrowserHandle(nova_kwargs={"starting_page": "https://e.test/"})
    with (
        patch.object(engine_mod, "NovaAct", _FakeNovaAct),
        patch.object(engine_mod, "Workflow", _FakeWorkflow),
        patch.object(engine_mod, "StepExecutor", _FakeExecutor),
        patch.object(engine_mod, "WorkflowManager") as wf,
        patch.object(engine_mod, "LocalBrowserProvisioner") as prov,
        patch.object(progress, "step_started") as step_started,
        patch.object(progress, "test_started") as test_started,
    ):
        wf.return_value.ensure_workflow.return_value = "wf-1"
        prov.return_value.provision.return_value = handle
        yield {"step_started": step_started, "test_started": test_started}


def _step_calls(mock):
    """``[(label, instruction, validation, test_name), ...]`` from step_started calls."""
    out = []
    for call in mock.call_args_list:
        step, instruction = call.args
        out.append((
            progress.step_label(step), instruction,
            step.get("validation_value"), call.kwargs.get("test_name"),
        ))
    return out


class TestLocalLoop:
    def _run(self, engine):
        return engine.execute_usecase_local(
            usecase_id="u-1", usecase_name="Login", starting_url="https://e.test/",
            steps=STEPS, variables=VARIABLES, secrets=[], region="us-east-1", model_id="m",
        )

    def test_step_started_gets_resolved_step_and_instruction(self, fakes):
        result = self._run(ExecutionEngine())
        assert result["status"] == "success"
        assert _step_calls(fakes["step_started"]) == [
            ("Step 1", "Open https://e.test/login", None, None),
            ("Step 2", "Check greeting", "Hi Jane", None),
            ("Step 3 (row 2/2)", "Type b@x.test", None, None),
        ]

    def test_suite_mode_prefixes_test_name(self, fakes):
        self._run(ExecutionEngine(show_test_name_on_steps=True))
        assert {c[3] for c in _step_calls(fakes["step_started"])} == {"Login"}

    def test_local_loop_does_not_announce_test(self, fakes):
        # main._execute_usecase_local announces the test; the engine must not duplicate it.
        self._run(ExecutionEngine())
        fakes["test_started"].assert_not_called()

    def test_show_test_name_default_is_false(self):
        assert ExecutionEngine().show_test_name_on_steps is False


def _remote_engine(**engine_kwargs):
    api = MagicMock()
    for name in (
        "update_status", "get_execution", "update_session_id", "update_step_status",
        "create_live_view", "delete_live_view", "update_mobile_metadata",
    ):
        setattr(api, name, AsyncMock())
    api.get_secret_value = MagicMock(return_value=None)
    api.client = MagicMock()
    return ExecutionEngine(execution_api=api, **engine_kwargs), api


def _details():
    return {
        "test_platform": "web",
        "starting_url": "https://e.test/",
        "steps": STEPS,
        "variables": VARIABLES,
        "headers": {},
        "model_id": "nova-act-v1.0",
        "usecase_name": "Login",
    }


class TestRemoteLoop:
    def _run(self, engine, **kwargs):
        uploader = MagicMock()
        uploader.upload_step_artifacts = AsyncMock()
        return engine._execute_with_nova_act(
            _details(), "u-1", "ex-1", MagicMock(), uploader, **kwargs,
        )

    def test_step_started_gets_resolved_step_and_instruction(self, fakes, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        engine, _ = _remote_engine()
        result = self._run(engine, usecase_name="Login")
        assert result["success"] is True
        assert _step_calls(fakes["step_started"]) == [
            ("Step 1", "Open https://e.test/login", None, None),
            ("Step 2", "Check greeting", "Hi Jane", None),
            ("Step 3 (row 2/2)", "Type b@x.test", None, None),
        ]

    def test_suite_mode_prefixes_test_name(self, fakes, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        engine, _ = _remote_engine(show_test_name_on_steps=True)
        self._run(engine, usecase_name="Login")
        assert {c[3] for c in _step_calls(fakes["step_started"])} == {"Login"}

    def test_execute_usecase_announces_test_with_execution_id(self, fakes, tmp_path, monkeypatch):
        import asyncio

        monkeypatch.setenv("HOME", str(tmp_path))
        engine, api = _remote_engine()
        api.get_execution = AsyncMock(return_value=_details())
        with (
            patch.object(engine_mod, "ArtifactUploader") as uploader_cls,
            patch.object(engine_mod, "ArtifactCapture", return_value=MagicMock()),
            patch.object(engine, "_execute_usecase_sync", return_value={"success": True}) as sync,
        ):
            uploader_cls.return_value.upload_execution_artifacts = AsyncMock()
            asyncio.run(engine.execute_usecase(
                {"execution_id": "ex-1", "usecase_id": "u-1", "usecase_name": "Login"},
            ))
        fakes["test_started"].assert_called_once_with("Login", execution_id="ex-1")
        # The name is threaded down to the step loop.
        assert sync.call_args.kwargs["usecase_name"] == "Login"


def test_engine_has_no_private_step_label():
    assert not hasattr(engine_mod, "_step_label")
