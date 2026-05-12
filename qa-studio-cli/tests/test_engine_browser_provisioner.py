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
