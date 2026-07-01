"""Tests for mobile metadata plumbing in ExecutionEngine (T2.12)."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


# Stub external deps before importing engine — matches other engine-level
# test files in this suite.
sys.modules.setdefault("nova_act", ModuleType("nova_act"))
_nova_mod = sys.modules["nova_act"]
if not hasattr(_nova_mod, "NovaAct"):
    _nova_mod.NovaAct = type("NovaAct", (), {})
if not hasattr(_nova_mod, "BOOL_SCHEMA"):
    _nova_mod.BOOL_SCHEMA = {"type": "boolean"}
if not hasattr(_nova_mod, "Workflow"):
    _nova_mod.Workflow = type("Workflow", (), {})

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


from qa_studio_cli.runner.engine import (  # noqa: E402
    ExecutionEngine,
    _extract_session_arn,
)


# ---------------------------------------------------------------------------
# _extract_session_arn
# ---------------------------------------------------------------------------


class TestExtractSessionArn:
    def test_none_actuator_returns_none(self):
        assert _extract_session_arn(None) is None

    def test_stopped_arn_preferred(self):
        """If both populated, the terminal ARN wins."""
        actuator = SimpleNamespace(
            stopped_session_arn="arn:stopped",
            session_result=SimpleNamespace(arn="arn:live"),
        )
        assert _extract_session_arn(actuator) == "arn:stopped"

    def test_session_result_object_shape(self):
        actuator = SimpleNamespace(
            stopped_session_arn=None,
            session_result=SimpleNamespace(arn="arn:live"),
        )
        assert _extract_session_arn(actuator) == "arn:live"

    def test_session_result_dict_shape(self):
        actuator = SimpleNamespace(
            stopped_session_arn=None,
            session_result={"arn": "arn:live"},
        )
        assert _extract_session_arn(actuator) == "arn:live"

    def test_nothing_populated_returns_none(self):
        actuator = SimpleNamespace(
            stopped_session_arn=None, session_result=None,
        )
        assert _extract_session_arn(actuator) is None

    def test_unknown_shape_returns_none(self):
        """Defensive against future nova_act_mobile changes."""
        actuator = SimpleNamespace(
            stopped_session_arn=None,
            session_result=SimpleNamespace(),  # no `arn` attribute
        )
        assert _extract_session_arn(actuator) is None


# ---------------------------------------------------------------------------
# _persist_mobile_metadata
# ---------------------------------------------------------------------------


def _engine_with_mock_api():
    api = MagicMock()
    api.update_mobile_metadata = AsyncMock()
    engine = ExecutionEngine(execution_api=api, suite_execution_id="standalone")
    return engine, api


class TestPersistMobileMetadata:
    def test_all_none_is_noop(self):
        engine, api = _engine_with_mock_api()
        engine._persist_mobile_metadata("uc-1", "ex-1")
        api.update_mobile_metadata.assert_not_called()

    def test_forwards_session_arn(self):
        engine, api = _engine_with_mock_api()
        engine._persist_mobile_metadata(
            "uc-1", "ex-1",
            device_farm_session_arn="arn:aws:devicefarm:us-west-2:1:session:a",
        )
        api.update_mobile_metadata.assert_awaited_once_with(
            usecase_id="uc-1",
            execution_id="ex-1",
            device_farm_session_arn="arn:aws:devicefarm:us-west-2:1:session:a",
            device_name=None,
            device_os_version=None,
        )

    def test_forwards_device_details(self):
        engine, api = _engine_with_mock_api()
        engine._persist_mobile_metadata(
            "uc-1", "ex-1",
            device_farm_session_arn="arn:stopped",
            device_name="Pixel 6",
            device_os_version="Android 13",
        )
        api.update_mobile_metadata.assert_awaited_once_with(
            usecase_id="uc-1",
            execution_id="ex-1",
            device_farm_session_arn="arn:stopped",
            device_name="Pixel 6",
            device_os_version="Android 13",
        )

    def test_api_failure_is_swallowed(self):
        engine, api = _engine_with_mock_api()
        api.update_mobile_metadata.side_effect = RuntimeError("server down")
        # Must not raise — metadata is best-effort.
        engine._persist_mobile_metadata(
            "uc-1", "ex-1", device_farm_session_arn="arn:x",
        )
