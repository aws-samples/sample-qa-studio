"""Tests for the Playwright startup retry loop in
``ExecutionEngine._execute_usecase_sync``.

Nova Act's browser startup (Playwright init) occasionally fails transiently
with ``StartFailed``.  The engine retries up to 3 attempts with linear
backoff (3s, 6s, 9s) and fails immediately for any other exception.

These tests stub the ``nova_act`` SDK (it lives in the optional ``[runner]``
extras) following the pattern in ``test_engine_browser_provisioner.py``.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


# --- Stub external deps so engine import succeeds without the runner extras.

sys.modules.setdefault("nova_act", ModuleType("nova_act"))
_nova = sys.modules["nova_act"]
if not hasattr(_nova, "NovaAct"):
    _nova.NovaAct = type("NovaAct", (), {})
if not hasattr(_nova, "BOOL_SCHEMA"):
    _nova.BOOL_SCHEMA = {"type": "boolean"}
if not hasattr(_nova, "Workflow"):
    _nova.Workflow = type("Workflow", (), {})


# Stub nova_act.types and nova_act.types.errors so the engine's
# ``from nova_act.types.errors import StartFailed`` import resolves when the
# real SDK is absent. Register the stub exception only if one is not already
# present — when the real SDK is installed, ``setdefault`` is a no-op and the
# engine binds the real ``StartFailed`` class instead.
sys.modules.setdefault("nova_act.types", ModuleType("nova_act.types"))
_errors_mod = sys.modules.setdefault(
    "nova_act.types.errors", ModuleType("nova_act.types.errors")
)
if not hasattr(_errors_mod, "StartFailed"):
    class _StubStartFailed(Exception):
        """Stub of nova_act.types.errors.StartFailed (browser startup failure)."""

    _errors_mod.StartFailed = _StubStartFailed

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


# Import the exact ``StartFailed`` the engine catches. Depending on whether the
# real SDK is installed, this is either the real class or the stub registered
# above — either way it is the binding the engine's ``except StartFailed`` uses,
# so raising it in tests is correct regardless of import order in the suite.
from qa_studio_cli.runner.engine import ExecutionEngine, StartFailed  # noqa: E402


@pytest.fixture
def engine():
    return ExecutionEngine()


@pytest.fixture
def call_args():
    """Common args for ``_execute_usecase_sync``.

    ``execution_details`` can be empty since ``_execute_with_nova_act`` is
    fully mocked in every test.
    """
    artifact_capture = MagicMock()
    artifact_capture.bind_to_current_thread = MagicMock(return_value=None)
    return {
        "execution_details": {},
        "usecase_id": "uc-1",
        "execution_id": "exec-1",
        "artifact_capture": artifact_capture,
        "artifact_uploader": MagicMock(),
    }


class TestStartRetry:
    def test_retries_then_succeeds_on_third_attempt(self, engine, call_args):
        """StartFailed twice then success → 3 calls, sleeps [3, 6]."""
        success = {"success": True}
        with (
            patch.object(
                engine,
                "_execute_with_nova_act",
                side_effect=[StartFailed("boom"), StartFailed("boom"), success],
            ) as mock_exec,
            patch("qa_studio_cli.runner.engine.time.sleep") as mock_sleep,
        ):
            result = engine._execute_usecase_sync(**call_args)

        assert result == success
        assert mock_exec.call_count == 3
        assert [c.args[0] for c in mock_sleep.call_args_list] == [3, 6]

    def test_exhausts_retries_and_returns_failure(self, engine, call_args):
        """StartFailed 3 times → success=False, sleeps [3, 6]."""
        with (
            patch.object(
                engine,
                "_execute_with_nova_act",
                side_effect=StartFailed("still failing"),
            ) as mock_exec,
            patch("qa_studio_cli.runner.engine.time.sleep") as mock_sleep,
        ):
            result = engine._execute_usecase_sync(**call_args)

        assert result["success"] is False
        assert "Nova Act execution failed" in result["error"]
        assert mock_exec.call_count == 3
        assert [c.args[0] for c in mock_sleep.call_args_list] == [3, 6]

    def test_non_retryable_error_fails_immediately(self, engine, call_args):
        """Generic RuntimeError → 1 call, no sleep, success=False."""
        with (
            patch.object(
                engine,
                "_execute_with_nova_act",
                side_effect=RuntimeError("unexpected"),
            ) as mock_exec,
            patch("qa_studio_cli.runner.engine.time.sleep") as mock_sleep,
        ):
            result = engine._execute_usecase_sync(**call_args)

        assert result["success"] is False
        assert "Nova Act execution failed" in result["error"]
        assert mock_exec.call_count == 1
        mock_sleep.assert_not_called()

    def test_backoff_values_are_three_times_attempt(self, engine, call_args):
        """Backoff is exactly 3 * attempt → sleeps [3, 6] for 2 retries."""
        with (
            patch.object(
                engine,
                "_execute_with_nova_act",
                side_effect=[StartFailed("a"), StartFailed("b"), {"success": True}],
            ),
            patch("qa_studio_cli.runner.engine.time.sleep") as mock_sleep,
        ):
            engine._execute_usecase_sync(**call_args)

        assert [c.args[0] for c in mock_sleep.call_args_list] == [3, 6]
