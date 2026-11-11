"""``qa-studio run --region`` in local mode (``ExecutionEngine.execute_usecase_local``).

The region reaches the browser provisioner context and the regional AWS
clients the local path creates (the S3 app-binary download for mobile).
Nova Act stays in ``NOVA_ACT_REGION`` and Device Farm in us-west-2.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

try:  # pragma: no cover - environment dependent
    import nova_act  # noqa: F401
except ImportError:  # pragma: no cover - environment dependent
    sys.modules.setdefault("nova_act", ModuleType("nova_act"))

from qa_studio_cli.runner import engine as engine_mod  # noqa: E402
from qa_studio_cli.runner.browser import BrowserHandle  # noqa: E402
from qa_studio_cli.runner.engine import ExecutionEngine  # noqa: E402
from qa_studio_cli.runner.workflow_manager import NOVA_ACT_REGION  # noqa: E402


class _FakeNovaAct:
    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class _RecordingWorkflow:
    calls = []

    def __init__(self, **kwargs):
        _RecordingWorkflow.calls.append(kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


@pytest.fixture
def local_fakes():
    _RecordingWorkflow.calls = []
    with (
        patch.object(engine_mod, "NovaAct", _FakeNovaAct),
        patch.object(engine_mod, "Workflow", _RecordingWorkflow),
        patch.object(engine_mod, "WorkflowManager") as wf,
        patch.object(engine_mod, "LocalBrowserProvisioner") as prov,
    ):
        wf.return_value.ensure_workflow.return_value = "wf-1"
        prov.return_value.provision.return_value = BrowserHandle(nova_kwargs={})
        yield prov


def _run(region, **kwargs):
    return ExecutionEngine().execute_usecase_local(
        usecase_id="u-1", usecase_name="Login", starting_url="https://e.test/",
        steps=[], variables={}, secrets=[], region=region, model_id="m", **kwargs,
    )


class TestLocalWebRegion:
    def test_region_reaches_the_provisioner_context(self, local_fakes):
        _run("eu-west-1")
        context = local_fakes.return_value.provision.call_args.args[0]
        assert context["region"] == "eu-west-1"

    def test_unset_region_stays_unset(self, local_fakes):
        _run(None)
        assert local_fakes.return_value.provision.call_args.args[0]["region"] is None

    def test_nova_act_keeps_its_fixed_region(self, local_fakes):
        _run("eu-west-1")
        assert _RecordingWorkflow.calls[0]["boto_session_kwargs"] == {"region_name": NOVA_ACT_REGION}


class TestLocalMobileRegion:
    def test_region_passed_to_mobile_actuator(self, local_fakes):
        engine = ExecutionEngine()
        with patch.object(engine, "_build_mobile_actuator",
                          return_value=(MagicMock(), "app://x")) as build:
            engine.execute_usecase_local(
                usecase_id="u-1", usecase_name="Mobile", starting_url="",
                steps=[], variables={}, secrets=[], region="eu-west-1", model_id="m",
                mobile_config={"platform": "ANDROID"}, test_platform="mobile",
            )
        assert build.call_args.kwargs["region"] == "eu-west-1"

    @pytest.mark.parametrize("region,expected_kwargs", [
        ("eu-west-1", {"region_name": "eu-west-1"}),
        (None, {}),
    ])
    def test_s3_app_binary_download_uses_the_region(self, region, expected_kwargs, monkeypatch, tmp_path):
        """No existing Device Farm upload → the binary is downloaded from S3
        with a client in ``--region`` (boto default chain when unset)."""
        monkeypatch.setenv("S3_BUCKET", "bucket-1")
        df_client = MagicMock()
        df_client.find_existing_upload.return_value = None
        mobile_pkgs = {
            "nova_act_mobile.actuation.device_farm_actuator": MagicMock(),
            "nova_act_mobile.actuation.mobile_actuator": MagicMock(),
            "nova_act_mobile.app": MagicMock(),
            "nova_act_mobile.device_farm": MagicMock(DeviceFarmClient=MagicMock(return_value=df_client)),
        }
        boto3_mod = MagicMock()
        with patch.dict(sys.modules, {**mobile_pkgs, "boto3": boto3_mod}):
            ExecutionEngine()._build_mobile_actuator({
                "platform": "ANDROID", "app_package": "p", "app_activity": "a",
                "app_binary_s3_path": "apps/app.apk",
            }, region=region)
        boto3_mod.client.assert_called_once_with("s3", **expected_kwargs)
