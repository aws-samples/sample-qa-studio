"""Tests for the browser step executor."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models import ExecutionStep
from browser_step import execute_browser_step


def _make_step(**overrides) -> ExecutionStep:
    defaults = dict(
        pk="EXECUTION#e1", sk="EXECUTION_STEP#s1", step_id="s1", sort=1,
        instruction="", artefact="", logs=[], created_at="2026-01-01",
        secret_key="", step_type="browser", validation_type="",
        validation_operator="", validation_value="", capture_variable="",
        value_type="", assertion_variable="",
    )
    defaults.update(overrides)
    return ExecutionStep(**defaults)


def _make_nova(url="https://example.com", go_back_response=object(), go_forward_response=object()):
    """Create a mock NovaAct with a mock page."""
    nova = MagicMock()
    page = MagicMock()
    page.url = url
    page.go_back.return_value = go_back_response
    page.go_forward.return_value = go_forward_response
    nova.page = page
    return nova


class TestReload:
    def test_soft_reload(self):
        nova = _make_nova()
        step = _make_step(browser_action="reload")
        _, success, logs = execute_browser_step(nova, step)
        assert success
        nova.page.reload.assert_called_once()

    def test_hard_reload(self):
        nova = _make_nova()
        step = _make_step(
            browser_action="reload",
            browser_args=json.dumps({"hard": True}),
        )
        _, success, logs = execute_browser_step(nova, step)
        assert success
        nova.page.evaluate.assert_called_once_with("() => location.reload()")
        nova.page.reload.assert_not_called()

    def test_soft_reload_default(self):
        nova = _make_nova()
        step = _make_step(
            browser_action="reload",
            browser_args=json.dumps({"hard": False}),
        )
        _, success, _ = execute_browser_step(nova, step)
        assert success
        nova.page.reload.assert_called_once()


class TestBack:
    def test_back_success(self):
        nova = _make_nova()
        # Simulate URL change after go_back
        nova.page.go_back.side_effect = lambda: setattr(nova.page, 'url', 'https://example.com/prev') or object()
        step = _make_step(browser_action="back")
        _, success, logs = execute_browser_step(nova, step)
        assert success

    def test_back_no_history(self):
        nova = _make_nova(go_back_response=None)
        step = _make_step(browser_action="back")
        _, success, logs = execute_browser_step(nova, step)
        assert not success
        assert "no previous history" in logs.lower()

    def test_back_url_unchanged_with_response(self):
        """Even if go_back returns something, if URL didn't change, it's still OK
        (some pages may have same URL with different state)."""
        nova = _make_nova(go_back_response=object())
        step = _make_step(browser_action="back")
        _, success, _ = execute_browser_step(nova, step)
        # response is not None, so success even if URL unchanged
        assert success


class TestForward:
    def test_forward_success(self):
        nova = _make_nova()
        nova.page.go_forward.side_effect = lambda: setattr(nova.page, 'url', 'https://example.com/next') or object()
        step = _make_step(browser_action="forward")
        _, success, _ = execute_browser_step(nova, step)
        assert success

    def test_forward_no_history(self):
        nova = _make_nova(go_forward_response=None)
        step = _make_step(browser_action="forward")
        _, success, logs = execute_browser_step(nova, step)
        assert not success
        assert "no forward history" in logs.lower()


class TestNavigate:
    def test_navigate_success(self):
        nova = _make_nova()
        step = _make_step(
            browser_action="navigate",
            browser_args=json.dumps({"url": "https://example.com/page"}),
        )
        _, success, _ = execute_browser_step(nova, step)
        assert success
        nova.go_to_url.assert_called_once_with("https://example.com/page")

    def test_navigate_missing_url(self):
        nova = _make_nova()
        step = _make_step(
            browser_action="navigate",
            browser_args=json.dumps({}),
        )
        _, success, logs = execute_browser_step(nova, step)
        assert not success
        assert "url is required" in logs.lower()


class TestEdgeCases:
    def test_missing_browser_action(self):
        nova = _make_nova()
        step = _make_step(browser_action=None)
        _, success, logs = execute_browser_step(nova, step)
        assert not success
        assert "browser_action is required" in logs

    def test_unknown_action(self):
        nova = _make_nova()
        step = _make_step(browser_action="close_tab")
        _, success, logs = execute_browser_step(nova, step)
        assert not success
        assert "Unknown browser_action" in logs

    def test_result_is_always_none(self):
        nova = _make_nova()
        step = _make_step(browser_action="reload")
        result, success, _ = execute_browser_step(nova, step)
        assert result is None
        assert success
