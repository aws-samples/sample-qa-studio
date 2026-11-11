"""Tests for ExecutionEngine's Electron dispatch (electron-testing task 3).

``test_platform == "electron"`` must route both the local-only and the
remote path through ``ElectronBrowserProvisioner``, gate web-only features
(header injection, trajectory replay) off, and always tear the app down.
Everything that would touch a real browser is replaced with fakes; the
provisioner class itself is patched so no process is spawned here (the
provisioner has its own subprocess-level tests).
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Stub nova_act / tenacity like the sibling engine tests do — but only when
# the real packages are absent, so this file also runs standalone on a
# machine that has the [runner] extra installed.
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

from qa_studio_cli.runner.browser import (  # noqa: E402
    BrowserHandle,
    BrowserSelection,
    ElectronLaunchConfig,
)
from qa_studio_cli.runner import engine as engine_mod  # noqa: E402
from qa_studio_cli.runner.engine import ExecutionEngine  # noqa: E402


ELECTRON_KWARGS = {
    "cdp_endpoint_url": "ws://127.0.0.1:5555/devtools/browser/abc",
    "cdp_use_existing_page": True,
    "ignore_screen_dims_check": True,
    "starting_page": "file:///app/out/renderer/index.html",
}


class _FakeNovaAct:
    captured: dict = {}
    instances: list = []

    def __init__(self, **kwargs):
        type(self).captured = dict(kwargs)
        self.page = MagicMock()
        self.go_to_url = MagicMock()
        type(self).instances.append(self)

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


@pytest.fixture
def fakes():
    """Patch NovaAct, Workflow, WorkflowManager and the Electron provisioner."""
    teardown = MagicMock()
    handle = BrowserHandle(nova_kwargs=dict(ELECTRON_KWARGS), teardown=teardown, metadata={"pid": 1})
    prov_cls = MagicMock()
    prov_cls.return_value.provision.return_value = handle
    _FakeNovaAct.captured = {}
    _FakeNovaAct.instances = []
    with (
        patch.object(engine_mod, "NovaAct", _FakeNovaAct),
        patch.object(engine_mod, "Workflow", _FakeWorkflow),
        patch.object(engine_mod, "WorkflowManager") as wf,
        patch.object(engine_mod, "ElectronBrowserProvisioner", prov_cls),
        patch.object(engine_mod, "_cdp_use_existing_page_supported", True),
    ):
        wf.return_value.ensure_workflow.return_value = "wf-1"
        yield {"provisioner_cls": prov_cls, "teardown": teardown, "handle": handle}


LAUNCH = ElectronLaunchConfig(app_path="/Apps/Harness.app", app_args=["--x"])


# ---------------------------------------------------------------------------
# Local-only path
# ---------------------------------------------------------------------------


class TestLocalPath:
    def _run(self, engine, steps=None, **overrides):
        kwargs = dict(
            usecase_id="u-1", usecase_name="Harness", starting_url="",
            steps=steps or [], variables={}, secrets=[], region="eu-central-1",
            model_id="nova-act-v1.0", test_platform="electron",
        )
        kwargs.update(overrides)
        return engine.execute_usecase_local(**kwargs)

    def test_dispatches_to_electron_provisioner(self, fakes):
        engine = ExecutionEngine(electron_launch=LAUNCH)
        result = self._run(engine)
        assert result["status"] == "success"
        fakes["provisioner_cls"].assert_called_once_with(LAUNCH)
        ctx = fakes["provisioner_cls"].return_value.provision.call_args[0][0]
        assert ctx["usecase_id"] == "u-1"
        assert ctx["bundle_id"] is None
        kw = _FakeNovaAct.captured
        assert kw["cdp_endpoint_url"] == ELECTRON_KWARGS["cdp_endpoint_url"]
        assert kw["cdp_use_existing_page"] is True
        assert kw["ignore_screen_dims_check"] is True
        # Web-only extras must be off over CDP / for electron.
        assert "record_video" not in kw
        assert "replayable" not in kw
        fakes["teardown"].assert_called_once()

    def test_bundle_id_reaches_provisioner(self, fakes):
        engine = ExecutionEngine(electron_launch=LAUNCH)
        self._run(engine, bundle_id="com.productharness.desktop")
        ctx = fakes["provisioner_cls"].return_value.provision.call_args[0][0]
        assert ctx["bundle_id"] == "com.productharness.desktop"

    def test_missing_app_path_is_a_clear_error(self, fakes):
        engine = ExecutionEngine()  # no electron_launch
        result = self._run(engine)
        assert result["status"] == "failed"
        fakes["provisioner_cls"].assert_not_called()

    def test_missing_app_path_message_names_flag(self, fakes):
        engine = ExecutionEngine()
        with pytest.raises(RuntimeError, match="--app-path"):
            engine._build_electron_provisioner()

    def test_teardown_called_when_step_fails(self, fakes):
        engine = ExecutionEngine(electron_launch=LAUNCH)
        step = {"step_id": "s1", "step_type": "validation", "instruction": "x", "sort": 1}
        with patch.object(engine_mod, "StepExecutor") as se:
            se.return_value.execute.return_value = MagicMock(success=False, logs="boom", act_id="", actual_value="")
            result = self._run(engine, steps=[step])
        assert result["status"] == "failed"
        fakes["teardown"].assert_called_once()

    def test_teardown_called_when_nova_act_raises(self, fakes):
        engine = ExecutionEngine(electron_launch=LAUNCH)

        class _Boom(_FakeNovaAct):
            def __enter__(self):
                raise RuntimeError("cdp refused")

        with patch.object(engine_mod, "NovaAct", _Boom):
            result = self._run(engine)
        assert result["status"] == "failed"
        fakes["teardown"].assert_called_once()

    def test_web_platform_still_uses_local_provisioner(self, fakes):
        engine = ExecutionEngine(electron_launch=LAUNCH)
        local_handle = BrowserHandle(nova_kwargs={"starting_page": "https://x.test/"})
        with patch.object(engine_mod, "LocalBrowserProvisioner") as local_cls:
            local_cls.return_value.provision.return_value = local_handle
            result = self._run(engine, test_platform="web", starting_url="https://x.test/")
        assert result["status"] == "success"
        fakes["provisioner_cls"].assert_not_called()
        assert _FakeNovaAct.captured.get("record_video") is True

    def test_unsupported_sdk_fails_clearly(self, fakes):
        engine = ExecutionEngine(electron_launch=LAUNCH)
        with patch.object(engine_mod, "_cdp_use_existing_page_supported", False):
            with pytest.raises(RuntimeError, match="cdp_use_existing_page"):
                engine._build_electron_provisioner()


# ---------------------------------------------------------------------------
# Remote path
# ---------------------------------------------------------------------------


def _remote_engine(launch=LAUNCH, **engine_kwargs):
    api = MagicMock()
    for name in (
        "update_status", "get_execution", "update_session_id", "update_step_status",
        "create_live_view", "delete_live_view", "update_mobile_metadata",
    ):
        setattr(api, name, AsyncMock())
    api.get_secret_value = MagicMock(return_value=None)
    api.client = MagicMock()
    engine = ExecutionEngine(execution_api=api, electron_launch=launch, **engine_kwargs)
    return engine, api


def _details(**over):
    d = {
        "test_platform": "electron",
        "starting_url": "",
        "steps": [],
        "variables": {},
        "headers": {"X-Test": "1"},
        "model_id": "nova-act-v1.0",
        "bundle_id": "com.productharness.desktop",
    }
    d.update(over)
    return d


class TestRemotePath:
    def test_dispatches_and_tears_down(self, fakes, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        engine, api = _remote_engine()
        capture = MagicMock()
        uploader = MagicMock()
        uploader.upload_step_artifacts = AsyncMock()
        result = engine._execute_with_nova_act(_details(), "u-1", "ex-1", capture, uploader)
        assert result["success"] is True
        fakes["provisioner_cls"].assert_called_once_with(LAUNCH)
        ctx = fakes["provisioner_cls"].return_value.provision.call_args[0][0]
        assert ctx["execution_id"] == "ex-1"
        assert ctx["bundle_id"] == "com.productharness.desktop"
        kw = _FakeNovaAct.captured
        assert kw["cdp_use_existing_page"] is True
        assert "record_video" not in kw
        assert "replayable" not in kw
        # Headers are a web-only feature: no set_extra_http_headers / go_to_url.
        nova = _FakeNovaAct.instances[-1]
        nova.page.set_extra_http_headers.assert_not_called()
        nova.go_to_url.assert_not_called()
        fakes["teardown"].assert_called_once()
        # No live view for electron.
        api.create_live_view.assert_not_called()

    def test_non_local_browser_mode_rejected(self, fakes, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        engine, api = _remote_engine(browser_selection=BrowserSelection(mode="agentcore"))
        with pytest.raises(RuntimeError, match="--browser"):
            engine._execute_with_nova_act(_details(), "u-1", "ex-1", MagicMock(), MagicMock())
        fakes["provisioner_cls"].assert_not_called()

    def test_missing_launch_config_raises(self, fakes, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        engine, api = _remote_engine(launch=None)
        with pytest.raises(RuntimeError, match="--app-path"):
            engine._execute_with_nova_act(_details(), "u-1", "ex-1", MagicMock(), MagicMock())
