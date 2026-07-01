"""Tests for ExecutionEngine's live-view publish/delete helpers (T2.11).

The helpers exist so the AgentCore provisioner (T2.6, not yet built) can
plug in without touching engine plumbing — they are invoked around the
step loop from ``_execute_with_nova_act`` via the ``BrowserHandle``
contract.  Until AgentCore lands, tests exercise the helpers directly.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest


# Stub nova_act at module import time — engine.py imports NovaAct.
sys.modules.setdefault("nova_act", ModuleType("nova_act"))
_nova_mod = sys.modules["nova_act"]
if not hasattr(_nova_mod, "NovaAct"):
    _nova_mod.NovaAct = type("NovaAct", (), {})
if not hasattr(_nova_mod, "BOOL_SCHEMA"):
    _nova_mod.BOOL_SCHEMA = {"type": "boolean"}
if not hasattr(_nova_mod, "Workflow"):
    _nova_mod.Workflow = type("Workflow", (), {})

# Stub tenacity (runner extra) — artifact_uploader imports retry decorators.
# We use a no-op decorator so code importing the module doesn't fail.
sys.modules.setdefault("tenacity", ModuleType("tenacity"))
_tenacity_mod = sys.modules["tenacity"]
if not hasattr(_tenacity_mod, "retry"):
    def _retry(*_a, **_kw):
        def _wrap(fn):
            return fn
        return _wrap
    _tenacity_mod.retry = _retry
    _tenacity_mod.stop_after_attempt = lambda *a, **kw: None
    _tenacity_mod.wait_exponential = lambda *a, **kw: None


from qa_studio_cli.runner.browser.handle import BrowserHandle  # noqa: E402
from qa_studio_cli.runner.engine import ExecutionEngine  # noqa: E402


def _engine_with_mock_api():
    api = MagicMock()
    api.create_live_view = AsyncMock()
    api.delete_live_view = AsyncMock()
    engine = ExecutionEngine(execution_api=api, suite_execution_id="standalone")
    return engine, api


class TestPublishLiveView:
    def test_no_handle_no_publish(self):
        engine, api = _engine_with_mock_api()
        published = engine._publish_live_view(None, "uc-1", "ex-1")
        assert published is False
        api.create_live_view.assert_not_called()

    def test_handle_without_url_no_publish(self):
        engine, api = _engine_with_mock_api()
        handle = BrowserHandle(nova_kwargs={"starting_page": "https://x.test/"})
        published = engine._publish_live_view(handle, "uc-1", "ex-1")
        assert published is False
        api.create_live_view.assert_not_called()

    def test_handle_with_url_publishes_and_reports_true(self):
        engine, api = _engine_with_mock_api()
        handle = BrowserHandle(
            nova_kwargs={"cdp_endpoint_url": "wss://x.test/cdp"},
            live_view_url="https://live.example/session-abc",
        )
        published = engine._publish_live_view(handle, "uc-1", "ex-1")
        assert published is True
        api.create_live_view.assert_awaited_once_with(
            usecase_id="uc-1",
            execution_id="ex-1",
            live_view_url="https://live.example/session-abc",
        )

    def test_api_failure_swallowed_returns_false(self):
        engine, api = _engine_with_mock_api()
        api.create_live_view.side_effect = RuntimeError("server went boom")
        handle = BrowserHandle(live_view_url="https://live.example/abc")
        published = engine._publish_live_view(handle, "uc-1", "ex-1")
        assert published is False


class TestDeleteLiveView:
    def test_delegates_to_api(self):
        engine, api = _engine_with_mock_api()
        engine._delete_live_view("uc-1", "ex-1")
        api.delete_live_view.assert_awaited_once_with(
            usecase_id="uc-1", execution_id="ex-1",
        )

    def test_swallows_failure(self):
        """A 404 or server failure must not propagate — teardown is best-effort."""
        engine, api = _engine_with_mock_api()
        api.delete_live_view.side_effect = RuntimeError("whatever")
        # Should not raise.
        engine._delete_live_view("uc-1", "ex-1")
