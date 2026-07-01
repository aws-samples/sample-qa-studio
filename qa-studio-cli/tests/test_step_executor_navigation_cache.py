"""Tests for ``StepExecutor._execute_navigation`` three-tier logic (T2.10).

Verifies the integration between the navigation-step dispatcher and the
trajectory manager:

- tier 1 success → no Nova Act call, result is ``trajectory_replay``
- tier 1 failure → Nova Act called + pending cache-field cleanup queued
- Nova Act success with recording enabled → save_trajectory attempted
- No trajectory manager → baseline behaviour unchanged
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


# Stub nova_act at module import time — matches other step_executor tests.
sys.modules.setdefault("nova_act", ModuleType("nova_act"))
_nova_mod = sys.modules["nova_act"]
if not hasattr(_nova_mod, "NovaAct"):
    _nova_mod.NovaAct = type("NovaAct", (), {})
if not hasattr(_nova_mod, "BOOL_SCHEMA"):
    _nova_mod.BOOL_SCHEMA = {"type": "boolean"}
if not hasattr(_nova_mod, "Workflow"):
    _nova_mod.Workflow = type("Workflow", (), {})


from qa_studio_cli.models.execution import TrajectoryReplayError  # noqa: E402
from qa_studio_cli.runner.step_executor import StepExecutor  # noqa: E402


def _nav_step(*, step_id="step-1", trajectory_key=None, sk=None):
    step = {
        "step_type": "navigation",
        "instruction": "click the button",
        "step_id": step_id,
    }
    if trajectory_key is not None:
        step["trajectory_s3_key"] = trajectory_key
    if sk is not None:
        step["sk"] = sk
    return step


def _traj_manager():
    """Mock trajectory manager with is_recording_enabled=True by default."""
    mgr = MagicMock()
    mgr.is_recording_enabled = True
    return mgr


class TestTier1TrajectoryReplay:
    def test_replay_success_skips_nova_act(self):
        nova = MagicMock()
        traj = _traj_manager()
        traj.replay_step.return_value = MagicMock(duration_ms=123)

        executor = StepExecutor(
            nova, trajectory_manager=traj, enable_cache=True,
        )
        step = _nav_step(trajectory_key="uc-1/trajectories/step-1.json")

        result = executor.execute(step, variables={}, runtime_variables={})

        assert result.success is True
        assert result.act_id == "trajectory_replay"
        nova.act.assert_not_called()
        traj.replay_step.assert_called_once()

    def test_replay_failure_falls_through_to_nova_act(self):
        nova = MagicMock()
        fake_result = MagicMock()
        fake_result.metadata.act_id = "novaact-123"
        nova.act.return_value = fake_result

        traj = _traj_manager()
        traj.replay_step.side_effect = TrajectoryReplayError(
            "replay borked", s3_key="uc-1/trajectories/step-1.json",
        )

        executor = StepExecutor(
            nova, trajectory_manager=traj, enable_cache=True,
        )
        step = _nav_step(trajectory_key="uc-1/trajectories/step-1.json")

        result = executor.execute(step, variables={}, runtime_variables={})

        assert result.success is True
        assert result.act_id == "novaact-123"
        nova.act.assert_called_once()
        # Replay was attempted and succeeded → save_trajectory refreshes
        # the recording on the next pass.
        traj.save_trajectory.assert_called_once()

    def test_cache_disabled_skips_replay(self):
        nova = MagicMock()
        nova.act.return_value = MagicMock(metadata=MagicMock(act_id="a1"))

        traj = _traj_manager()

        executor = StepExecutor(
            nova, trajectory_manager=traj, enable_cache=False,
        )
        step = _nav_step(trajectory_key="uc-1/trajectories/step-1.json")

        result = executor.execute(step, variables={}, runtime_variables={})

        assert result.success is True
        nova.act.assert_called_once()
        traj.replay_step.assert_not_called()

    def test_no_trajectory_key_skips_replay(self):
        nova = MagicMock()
        nova.act.return_value = MagicMock(metadata=MagicMock(act_id="a1"))

        traj = _traj_manager()

        executor = StepExecutor(
            nova, trajectory_manager=traj, enable_cache=True,
        )
        step = _nav_step(trajectory_key=None)

        result = executor.execute(step, variables={}, runtime_variables={})

        assert result.success is True
        nova.act.assert_called_once()
        traj.replay_step.assert_not_called()


class TestTier3WithTrajectoryRecording:
    def test_saves_trajectory_on_fresh_success(self):
        nova = MagicMock()
        fresh_result = MagicMock()
        fresh_result.metadata.act_id = "act-1"
        nova.act.return_value = fresh_result

        traj = _traj_manager()

        executor = StepExecutor(
            nova, trajectory_manager=traj, enable_cache=True,
        )
        # No prior trajectory key — first run records.
        step = _nav_step()

        result = executor.execute(step, variables={}, runtime_variables={})

        assert result.success is True
        traj.save_trajectory.assert_called_once_with("step-1", fresh_result)

    def test_no_save_when_recording_disabled(self):
        nova = MagicMock()
        nova.act.return_value = MagicMock(metadata=MagicMock(act_id="a1"))

        traj = _traj_manager()
        traj.is_recording_enabled = False

        executor = StepExecutor(
            nova, trajectory_manager=traj, enable_cache=True,
        )
        step = _nav_step()

        executor.execute(step, variables={}, runtime_variables={})
        traj.save_trajectory.assert_not_called()


class TestNovaActFailureQueuesCleanup:
    def test_replay_attempted_then_nova_act_failed_queues_clear(self):
        nova = MagicMock()
        nova.act.side_effect = RuntimeError("nova blew up")

        traj = _traj_manager()
        traj.replay_step.side_effect = TrajectoryReplayError(
            "replay also dead", s3_key="uc-1/trajectories/step-1.json",
        )

        executor = StepExecutor(
            nova, trajectory_manager=traj, enable_cache=True,
        )
        step = _nav_step(trajectory_key="uc-1/trajectories/step-1.json")

        result = executor.execute(step, variables={}, runtime_variables={})

        assert result.success is False
        # Cache cleanup for trajectory fields is queued via record_clear.
        traj.record_clear.assert_called_once()
        args = traj.record_clear.call_args.args
        assert args[0] == "step-1"
        assert args[1] == ["trajectory_s3_key", "trajectory_last_updated"]

    def test_no_prior_replay_no_cleanup_on_failure(self):
        """If replay wasn't even attempted, there's nothing stale to clean."""
        nova = MagicMock()
        nova.act.side_effect = RuntimeError("nova blew up")

        traj = _traj_manager()

        executor = StepExecutor(
            nova, trajectory_manager=traj, enable_cache=True,
        )
        step = _nav_step()  # no trajectory_s3_key

        result = executor.execute(step, variables={}, runtime_variables={})
        assert result.success is False
        traj.record_clear.assert_not_called()


class TestBaselineWithoutTrajectoryManager:
    """Ensure removing the manager leaves the original behaviour intact."""

    def test_execute_matches_plain_nova_act(self):
        nova = MagicMock()
        nova.act.return_value = MagicMock(metadata=MagicMock(act_id="a1"))

        executor = StepExecutor(nova)
        step = _nav_step()

        result = executor.execute(step, variables={}, runtime_variables={})
        assert result.success is True
        assert result.act_id == "a1"
        nova.act.assert_called_once()

    def test_nova_act_failure_surfaces_as_step_failure(self):
        nova = MagicMock()
        nova.act.side_effect = RuntimeError("boom")

        executor = StepExecutor(nova)
        step = _nav_step()

        result = executor.execute(step, variables={}, runtime_variables={})
        assert result.success is False
        assert "boom" in result.logs
