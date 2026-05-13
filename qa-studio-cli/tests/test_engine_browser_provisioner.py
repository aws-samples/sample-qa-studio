"""Tests for ExecutionEngine._build_browser_provisioner (T2.6).

Verifies the engine picks the correct BrowserProvisioner class based on
the BrowserSelection it was constructed with, and raises clear errors
for invalid combinations.
"""

from __future__ import annotations

import sys
from types import ModuleType

import pytest


# Stub external deps — engine imports NovaAct, tenacity, etc.
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


# Stub bedrock_agentcore so agentcore selection can resolve during tests.
for _n in (
    "bedrock_agentcore",
    "bedrock_agentcore.tools",
    "bedrock_agentcore.tools.browser_client",
):
    sys.modules.setdefault(_n, ModuleType(_n))
from unittest.mock import MagicMock  # noqa: E402
sys.modules["bedrock_agentcore.tools.browser_client"].BrowserClient = MagicMock()


from qa_studio_cli.runner.browser import (  # noqa: E402
    BrowserSelection,
    CdpExternalBrowserProvisioner,
    LocalBrowserProvisioner,
)
from qa_studio_cli.runner.browser.agentcore import (  # noqa: E402
    AgentCoreBrowserProvisioner,
)
from qa_studio_cli.runner.engine import ExecutionEngine  # noqa: E402


class TestBuildBrowserProvisioner:
    def test_default_selection_is_local(self):
        engine = ExecutionEngine()
        provisioner = engine._build_browser_provisioner()
        assert isinstance(provisioner, LocalBrowserProvisioner)

    def test_local_selection(self):
        engine = ExecutionEngine(
            browser_selection=BrowserSelection(mode="local"),
        )
        assert isinstance(engine._build_browser_provisioner(), LocalBrowserProvisioner)

    def test_cdp_external_selection(self):
        engine = ExecutionEngine(
            browser_selection=BrowserSelection(
                mode="cdp-external",
                cdp_endpoint_url="wss://remote.example/cdp",
            ),
        )
        provisioner = engine._build_browser_provisioner()
        assert isinstance(provisioner, CdpExternalBrowserProvisioner)

    def test_cdp_external_without_url_raises(self):
        engine = ExecutionEngine(
            browser_selection=BrowserSelection(mode="cdp-external"),
        )
        with pytest.raises(RuntimeError, match="--cdp-endpoint-url"):
            engine._build_browser_provisioner()

    def test_agentcore_selection(self):
        engine = ExecutionEngine(
            browser_selection=BrowserSelection(mode="agentcore"),
        )
        provisioner = engine._build_browser_provisioner()
        assert isinstance(provisioner, AgentCoreBrowserProvisioner)

    def test_unknown_mode_raises(self):
        engine = ExecutionEngine(
            # type-check would catch this, but defensive code still helps
            # if someone bypasses the dataclass (e.g. dict-based config).
            browser_selection=BrowserSelection(mode="local"),
        )
        # Bypass the frozen dataclass to simulate a bad mode getting in.
        object.__setattr__(engine.browser_selection, "mode", "firefox")
        with pytest.raises(RuntimeError, match="Unknown browser mode"):
            engine._build_browser_provisioner()


# ---------------------------------------------------------------------------
# record_video integration with engine execution path
# ---------------------------------------------------------------------------
#
# The engine must NEVER pass ``record_video=True`` to NovaAct when the
# chosen browser implies a CDP connection. The unit tests in
# ``test_browser_provisioner`` pin the predicate; these tests verify
# the engine actually applies the predicate after merging in the
# provisioner's kwargs — the exact bug fixed when chrome-profile
# crashed with ``ValidationFailed("Cannot record video when connecting
# over CDP")``.


from unittest.mock import patch  # noqa: E402

from qa_studio_cli.runner.browser import BrowserHandle  # noqa: E402


def _captured_nova_kwargs_for_local_run(
    fake_provision_kwargs: dict,
) -> dict:
    """Exercise ``execute_usecase_local`` with mocked NovaAct / Workflow
    and return the kwargs the engine tried to pass to ``NovaAct(**kwargs)``.

    Heavy external deps are stubbed so the test stays honest about the
    surface it's exercising — the engine's kwargs-construction logic
    and the final hand-off into NovaAct. Everything that would hit a
    real browser, workflow service, or stepper is replaced with a
    no-op.
    """
    captured: dict = {}

    class _FakeNovaAct:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.page = MagicMock()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class _FakeWorkflow:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    fake_handle = BrowserHandle(nova_kwargs=fake_provision_kwargs)

    # Provisioner factory is patched so the test doesn't depend on a
    # real Chrome profile existing on disk (chrome-profile's real
    # provisioner triggers ``ensure_chrome_profile_copy``).
    with (
        patch("qa_studio_cli.runner.engine.NovaAct", _FakeNovaAct),
        patch("qa_studio_cli.runner.engine.Workflow", _FakeWorkflow),
        patch(
            "qa_studio_cli.runner.engine.WorkflowManager"
        ) as MockWfManager,
        patch(
            "qa_studio_cli.runner.engine.LocalBrowserProvisioner"
        ) as MockProvCls,
    ):
        MockWfManager.return_value.ensure_workflow.return_value = "wf-1"
        MockProvCls.return_value.provision.return_value = fake_handle

        engine = ExecutionEngine(
            browser_selection=BrowserSelection(
                mode="local", local_browser="chrome-profile"
            )
        )
        # Empty steps → the step loop is skipped so the test doesn't
        # need to mock the StepExecutor / TemplateParser.
        engine.execute_usecase_local(
            usecase_id="u-1",
            usecase_name="Checkout",
            starting_url="https://example.com/",
            steps=[],
            variables={},
            secrets=[],
            region="us-east-1",
            model_id="nova-act-v1.0",
        )
    return captured


class TestRecordVideoInEngineLocalPath:
    def test_chrome_profile_does_not_set_record_video(self):
        """Regression: chrome-profile's ``use_default_chrome_browser=True``
        means NovaAct refuses ``record_video`` over CDP — the engine
        must not pass it.
        """
        kwargs = _captured_nova_kwargs_for_local_run(
            fake_provision_kwargs={
                "starting_page": "https://example.com/",
                "use_default_chrome_browser": True,
                "clone_user_data_dir": False,
                "user_data_dir": "/tmp/fake-copy",
            }
        )
        assert "record_video" not in kwargs

    def test_plain_local_browser_still_sets_record_video(self):
        """Non-CDP browser (bundled Chromium / Chrome channel) keeps
        video recording enabled — the fix must not regress the common
        case where recording works fine.
        """
        kwargs = _captured_nova_kwargs_for_local_run(
            fake_provision_kwargs={"starting_page": "https://example.com/"}
        )
        assert kwargs.get("record_video") is True
