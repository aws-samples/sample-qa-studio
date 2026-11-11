"""Tests for how ``runner.main`` threads Electron launch options into the
engine (electron-testing task 3).

``run_usecase`` / ``run_runner`` are exercised with the API layer and the
engine mocked; the assertions are about *what the engine is constructed
with* and *what ``test_platform`` the local path forwards*.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

try:  # pragma: no cover - environment dependent
    import nova_act  # noqa: F401
    import tenacity  # noqa: F401
except ImportError:  # pragma: no cover - environment dependent
    sys.modules.setdefault("nova_act", ModuleType("nova_act"))
    _nova = sys.modules["nova_act"]
    for _name, _val in (
        ("NovaAct", type("NovaAct", (), {})),
        ("BOOL_SCHEMA", {"type": "boolean"}),
        ("Workflow", type("Workflow", (), {})),
    ):
        if not hasattr(_nova, _name):
            setattr(_nova, _name, _val)
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

from qa_studio_cli.runner import main as main_mod  # noqa: E402
from qa_studio_cli.runner.browser import ElectronLaunchConfig  # noqa: E402


def _usecase(platform="electron"):
    return {
        "id": "u-1", "name": "Harness", "starting_url": "",
        "test_platform": platform, "executing_region": "eu-central-1",
        "model_id": "nova-act-v1.0",
        **({"bundle_id": "com.productharness.desktop"} if platform == "electron" else {}),
    }


@pytest.fixture
def api_mocks():
    """Patch the API client/UseCaseAPI so no network happens."""
    usecase_api = MagicMock()
    usecase_api.get_usecase.return_value = _usecase()
    usecase_api.get_steps.return_value = []
    usecase_api.get_variables.return_value = {}
    usecase_api.get_secrets.return_value = []
    with (
        patch.object(main_mod, "_validate_aws_session"),
        patch.object(main_mod, "_build_api_client", return_value=MagicMock()),
        patch.object(main_mod, "UseCaseAPI", return_value=usecase_api),
    ):
        yield usecase_api


@pytest.fixture
def engine_cls():
    engine = MagicMock()
    engine.execute_usecase_local.return_value = {"status": "success", "usecaseName": "Harness", "duration": 1}
    with patch.object(main_mod, "ExecutionEngine", return_value=engine) as cls:
        cls.instance = engine
        yield cls


class TestRunUsecaseLocal:
    def test_builds_launch_config_and_forwards_platform(self, api_mocks, engine_cls, tmp_path):
        with pytest.raises(SystemExit) as exc:
            main_mod.run_usecase(
                usecase_ids=["u-1"], local_only=True,
                app_path="/Apps/Harness.app", app_args=["--x"], app_user_data_dir=str(tmp_path),
            )
        assert exc.value.code == 0
        _, kwargs = engine_cls.call_args
        launch = kwargs["electron_launch"]
        assert launch == ElectronLaunchConfig(
            app_path="/Apps/Harness.app", app_args=("--x",), user_data_dir=str(tmp_path),
        )
        _, exec_kwargs = engine_cls.instance.execute_usecase_local.call_args
        assert exec_kwargs["test_platform"] == "electron"
        assert exec_kwargs["mobile_config"] is None
        assert exec_kwargs["bundle_id"] == "com.productharness.desktop"

    def test_no_app_path_means_no_launch_config(self, api_mocks, engine_cls):
        api_mocks.get_usecase.return_value = _usecase("web")
        with pytest.raises(SystemExit):
            main_mod.run_usecase(usecase_ids=["u-1"], local_only=True)
        _, kwargs = engine_cls.call_args
        assert kwargs["electron_launch"] is None
        _, exec_kwargs = engine_cls.instance.execute_usecase_local.call_args
        assert exec_kwargs["test_platform"] == "web"

    def test_mobile_app_path_still_lands_in_mobile_config(self, api_mocks, engine_cls):
        api_mocks.get_usecase.return_value = {
            **_usecase("mobile"), "platform": "ANDROID",
            "app_package": "com.x", "app_activity": ".Main",
        }
        with pytest.raises(SystemExit):
            main_mod.run_usecase(usecase_ids=["u-1"], local_only=True, app_path="/tmp/app.apk")
        _, exec_kwargs = engine_cls.instance.execute_usecase_local.call_args
        assert exec_kwargs["mobile_config"]["app_path"] == "/tmp/app.apk"
        assert exec_kwargs["test_platform"] == "mobile"


class TestRunUsecaseRemote:
    def test_launch_config_reaches_engine(self, api_mocks, engine_cls):
        engine_cls.instance.execute_usecase = MagicMock()
        with (
            patch.object(main_mod, "ExecutionAPI") as exec_api_cls,
            patch.object(main_mod.asyncio, "run", side_effect=[{"usecase_name": "Harness"}, {"status": "success", "duration": 1}]),
        ):
            exec_api_cls.return_value = MagicMock()
            with pytest.raises(SystemExit) as exc:
                main_mod.run_usecase(
                    usecase_ids=["u-1"], local_only=False, execution_id="ex-1",
                    app_path="/Apps/Harness.app",
                )
        assert exc.value.code == 0
        _, kwargs = engine_cls.call_args
        assert kwargs["electron_launch"] == ElectronLaunchConfig(app_path="/Apps/Harness.app")


class TestRunRunner:
    def test_local_suite_threads_launch_config_and_platform(self, api_mocks, engine_cls):
        suite_api = MagicMock()
        suite_api.get_suite.return_value = {"name": "Suite"}
        suite_api.list_usecases.return_value = [{"usecaseId": "u-1", "usecaseName": "Harness"}]
        with patch.object(main_mod, "TestSuiteAPI", return_value=suite_api):
            with pytest.raises(SystemExit) as exc:
                main_mod.run_runner(
                    suite_id="s-1", local_only=True,
                    app_path="/Apps/Harness.app", app_args=["a"],
                )
        assert exc.value.code == 0
        _, kwargs = engine_cls.call_args
        assert kwargs["electron_launch"] == ElectronLaunchConfig(app_path="/Apps/Harness.app", app_args=("a",))
        _, exec_kwargs = engine_cls.instance.execute_usecase_local.call_args
        assert exec_kwargs["test_platform"] == "electron"

    def test_remote_suite_threads_launch_config(self, api_mocks, engine_cls):
        suite_api = MagicMock()
        suite_api.get_suite.return_value = {"name": "Suite"}
        suite_api.execute_suite.return_value = {"suite_execution_id": "se-1", "execution_ids": []}
        with (
            patch.object(main_mod, "TestSuiteAPI", return_value=suite_api),
            patch.object(main_mod, "ExecutionAPI"),
            patch.object(main_mod, "SuiteLogCapture"),
            patch.object(main_mod.asyncio, "run", side_effect=[[], None]),
            patch.object(main_mod, "SummaryFormatter"),
            patch.object(main_mod, "determine_exit_code", return_value=0),
        ):
            with pytest.raises(SystemExit):
                main_mod.run_runner(suite_id="s-1", local_only=False, app_path="/Apps/Harness.app")
        _, kwargs = engine_cls.call_args
        assert kwargs["electron_launch"] == ElectronLaunchConfig(app_path="/Apps/Harness.app")
