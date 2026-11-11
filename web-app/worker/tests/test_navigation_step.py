"""Tests for the wizard's navigation step (Nova Act only; no step cache)."""

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock

from navigation_step import click_base_prompt, execute_navigation_step


def _step(**overrides):
    defaults = dict(sort=1, step_id="s1", instruction="Click Sign in",
                    enable_advanced_click_types=False)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_runs_the_instruction_through_nova_act():
    nova = MagicMock()
    nova.act.return_value = "act-result"

    result, success, logs = execute_navigation_step(nova, _step())

    nova.act.assert_called_once_with("Click Sign in")
    assert (result, success, logs) == ("act-result", True, "")


def test_advanced_click_types_prefix_the_prompt():
    nova = MagicMock()

    execute_navigation_step(nova, _step(enable_advanced_click_types=True))

    sent = nova.act.call_args.args[0]
    assert sent.startswith(click_base_prompt)
    assert sent.endswith("Click Sign in")


def test_failure_returns_error_result_with_act_id():
    nova = MagicMock()
    err = RuntimeError("element not found")
    err.metadata = SimpleNamespace(act_id="act-42")
    nova.act.side_effect = err

    result, success, logs = execute_navigation_step(nova, _step())

    assert success is False
    assert logs == "element not found"
    assert result.metadata.act_id == "act-42"


def test_failure_without_metadata_uses_error_act_id():
    nova = MagicMock()
    nova.act.side_effect = RuntimeError("boom")

    result, success, _ = execute_navigation_step(nova, _step())

    assert success is False
    assert result.metadata.act_id == "error"


def test_ignores_legacy_cache_fields_on_the_step():
    """A step that still carries bbox ``cached_steps`` runs through Nova Act."""
    nova = MagicMock()

    execute_navigation_step(nova, _step(cached_steps='[{"type":"click"}]', trajectory_s3_key="k"))

    nova.act.assert_called_once()


def test_signature_has_no_cache_parameters():
    assert list(inspect.signature(execute_navigation_step).parameters) == ["nova", "step"]
