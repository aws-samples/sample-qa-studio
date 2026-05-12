"""Tests for the CLI-side TrajectoryManager (T2.10, R-API-5).

The replay path lazily imports ``nova_act.impl.trajectory.types`` and
``nova_act.impl.program.runner`` — both only exist on SDK builds that
support ``replayable=True``.  For tests we stub both before exercising
:meth:`TrajectoryManager.replay_step`, mirroring the approach other
CLI test modules use for NovaAct internals.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Stub Nova Act SDK internals so imports inside replay_step succeed
# ---------------------------------------------------------------------------


def _install_nova_act_stubs() -> None:
    # Root packages
    for name in (
        "nova_act",
        "nova_act.impl",
        "nova_act.impl.trajectory",
        "nova_act.impl.trajectory.types",
        "nova_act.impl.program",
        "nova_act.impl.program.runner",
    ):
        sys.modules.setdefault(name, ModuleType(name))

    # Trajectory class with a model_validate_json classmethod.
    traj_mod = sys.modules["nova_act.impl.trajectory.types"]
    if not hasattr(traj_mod, "Trajectory"):
        class _Trajectory:
            @classmethod
            def model_validate_json(cls, raw: str):
                return cls()
        traj_mod.Trajectory = _Trajectory

    # ProgramRunner — patched per-test via monkeypatch.
    runner_mod = sys.modules["nova_act.impl.program.runner"]
    if not hasattr(runner_mod, "ProgramRunner"):
        class _ProgramRunner:
            def __init__(self, *a, **kw):
                pass

            def run(self, executable):  # pragma: no cover
                raise AssertionError("tests must patch ProgramRunner")
        runner_mod.ProgramRunner = _ProgramRunner


_install_nova_act_stubs()


# Imports must happen after stubs are installed.
from qa_studio_cli.models.execution import (  # noqa: E402
    ReplayResult,
    TrajectoryReplayError,
)
from qa_studio_cli.runner.trajectory import TrajectoryManager  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api(download_url=None, upload_response=None, download_raises=None):
    api = MagicMock()
    if download_raises is not None:
        api.get_trajectory_download_url.side_effect = download_raises
    else:
        api.get_trajectory_download_url.return_value = download_url
    api.create_trajectory_upload_url.return_value = upload_response
    return api


def _make_manager(tmp_path, api=None, replayable_supported=True):
    return TrajectoryManager(
        execution_api=api or MagicMock(),
        usecase_id="uc-1",
        execution_id="ex-1",
        logs_directory=str(tmp_path),
        replayable_supported=replayable_supported,
    )


# ---------------------------------------------------------------------------
# Detect replayable support
# ---------------------------------------------------------------------------


class TestDetectReplayableSupport:
    def test_true_when_kwarg_present(self):
        class NovaActWithReplayable:
            def __init__(self, *, replayable: bool = False): ...

        assert TrajectoryManager.detect_replayable_support(NovaActWithReplayable) is True

    def test_false_when_kwarg_absent(self):
        class NovaActWithoutReplayable:
            def __init__(self, starting_page: str = ""): ...

        assert TrajectoryManager.detect_replayable_support(NovaActWithoutReplayable) is False

    def test_false_when_signature_unreadable(self):
        # Built-ins don't expose a signature — probe must not crash.
        assert TrajectoryManager.detect_replayable_support(object) is False


# ---------------------------------------------------------------------------
# Deferred cache-field cleanup queue
# ---------------------------------------------------------------------------


class TestDeferredClears:
    def test_record_and_drain(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.record_clear("step-1", ["trajectory_s3_key", "trajectory_last_updated"])
        drained = mgr.drain_clear("step-1")
        assert drained == ["trajectory_s3_key", "trajectory_last_updated"]
        # Second drain is empty.
        assert mgr.drain_clear("step-1") == []

    def test_record_dedupes(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.record_clear("step-1", ["trajectory_s3_key"])
        mgr.record_clear("step-1", ["trajectory_s3_key", "trajectory_last_updated"])
        assert mgr.drain_clear("step-1") == [
            "trajectory_s3_key", "trajectory_last_updated",
        ]

    def test_record_empty_is_noop(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.record_clear("step-1", [])
        assert mgr.drain_clear("step-1") == []

    def test_clear_cache_fields_alias(self, tmp_path):
        """Worker-compat alias queues the same way."""
        mgr = _make_manager(tmp_path)
        mgr.clear_cache_fields("step-1", ["trajectory_s3_key"])
        assert mgr.drain_clear("step-1") == ["trajectory_s3_key"]


# ---------------------------------------------------------------------------
# save_trajectory
# ---------------------------------------------------------------------------


class TestSaveTrajectory:
    def test_no_trajectory_file_returns_none(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = SimpleNamespace(trajectory_file_path=None)
        assert mgr.save_trajectory("step-1", result) is None

    def test_missing_file_path_returns_none(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = SimpleNamespace(
            trajectory_file_path=str(tmp_path / "does-not-exist.json"),
        )
        assert mgr.save_trajectory("step-1", result) is None

    def test_api_failure_returns_none(self, tmp_path):
        traj_file = tmp_path / "traj.json"
        traj_file.write_text('{"steps": []}')
        api = _make_api(upload_response=None)  # create URL call returns None
        mgr = _make_manager(tmp_path, api=api)
        result = SimpleNamespace(trajectory_file_path=str(traj_file))
        assert mgr.save_trajectory("step-1", result) is None

    def test_happy_path_uploads_and_returns_key(self, tmp_path, monkeypatch):
        traj_file = tmp_path / "traj.json"
        traj_file.write_text('{"steps": []}')
        api = _make_api(upload_response={
            "upload_url": "https://s3.example/put?sig=xyz",
            "s3_key": "uc-1/trajectories/step-1.json",
            "expires_in": 900,
        })
        mgr = _make_manager(tmp_path, api=api)

        put_response = MagicMock()
        put_response.ok = True
        put_response.status_code = 200
        put_mock = MagicMock(return_value=put_response)
        monkeypatch.setattr(
            "qa_studio_cli.runner.trajectory.requests.put", put_mock,
        )

        result = SimpleNamespace(trajectory_file_path=str(traj_file))
        assert mgr.save_trajectory("step-1", result) == "uc-1/trajectories/step-1.json"

        put_mock.assert_called_once()
        args, kwargs = put_mock.call_args
        assert args[0] == "https://s3.example/put?sig=xyz"
        assert kwargs["headers"]["Content-Type"] == "application/json"

    def test_upload_http_failure_returns_none(self, tmp_path, monkeypatch):
        traj_file = tmp_path / "traj.json"
        traj_file.write_text('{}')
        api = _make_api(upload_response={
            "upload_url": "https://s3.example/put",
            "s3_key": "k",
        })
        mgr = _make_manager(tmp_path, api=api)

        bad = MagicMock()
        bad.ok = False
        bad.status_code = 403
        monkeypatch.setattr(
            "qa_studio_cli.runner.trajectory.requests.put",
            MagicMock(return_value=bad),
        )

        result = SimpleNamespace(trajectory_file_path=str(traj_file))
        assert mgr.save_trajectory("step-1", result) is None


# ---------------------------------------------------------------------------
# replay_step
# ---------------------------------------------------------------------------


def _patch_program_runner(monkeypatch, *, fail_with=None, return_after_first=False):
    """Install a stub ProgramRunner with configurable outcome."""
    runner_mod = sys.modules["nova_act.impl.program.runner"]

    def make_result(*, success=True, has_return=False, error=None):
        res = MagicMock()
        res.has_return.return_value = has_return
        if error is None:
            res.has_exception.return_value = None
        else:
            err_holder = SimpleNamespace(error=error)
            res.has_exception.return_value = err_holder
        return res

    class StubRunner:
        def __init__(self, *a, **kw):
            self._calls = 0

        def run(self, executable):
            self._calls += 1
            if fail_with is not None:
                return make_result(error=fail_with)
            return make_result(has_return=return_after_first)

    monkeypatch.setattr(runner_mod, "ProgramRunner", StubRunner)
    return StubRunner


def _patch_trajectory_with_steps(monkeypatch, step_count: int = 1):
    """Install a stub Trajectory.model_validate_json that returns ``step_count`` steps."""
    traj_mod = sys.modules["nova_act.impl.trajectory.types"]

    class _TrajStep:
        def __init__(self):
            self.program = MagicMock()
            self.program.compile = MagicMock(return_value=MagicMock())

    class _Trajectory:
        def __init__(self, steps):
            self.steps = steps

        @classmethod
        def model_validate_json(cls, raw: str):
            return cls([_TrajStep() for _ in range(step_count)])

    monkeypatch.setattr(traj_mod, "Trajectory", _Trajectory)


class TestReplayStep:
    def test_no_download_url_raises_without_replay(self, tmp_path):
        api = _make_api(download_url=None)
        mgr = _make_manager(tmp_path, api=api)

        step = {"step_id": "step-1", "trajectory_s3_key": "uc-1/trajectories/step-1.json"}
        with pytest.raises(TrajectoryReplayError, match="no trajectory recorded"):
            mgr.replay_step(nova=MagicMock(), step=step)

    def test_missing_step_id_raises(self, tmp_path):
        api = _make_api(download_url="https://s3.example/get")
        mgr = _make_manager(tmp_path, api=api)

        step = {"trajectory_s3_key": "uc-1/trajectories/step-1.json"}
        with pytest.raises(TrajectoryReplayError, match="missing step_id"):
            mgr.replay_step(nova=MagicMock(), step=step)

    def test_download_failure_raises(self, tmp_path, monkeypatch):
        api = _make_api(download_url="https://s3.example/get")
        mgr = _make_manager(tmp_path, api=api)

        def fake_get(*a, **kw):
            raise RuntimeError("network down")

        monkeypatch.setattr("qa_studio_cli.runner.trajectory.requests.get", fake_get)

        step = {"step_id": "step-1", "trajectory_s3_key": "uc-1/trajectories/step-1.json"}
        with pytest.raises(TrajectoryReplayError, match="replay failed"):
            mgr.replay_step(nova=MagicMock(), step=step)

    def test_api_failure_wraps_as_replay_error(self, tmp_path):
        api = _make_api(download_raises=RuntimeError("api blew up"))
        mgr = _make_manager(tmp_path, api=api)

        step = {"step_id": "step-1", "trajectory_s3_key": "uc-1/trajectories/step-1.json"}
        with pytest.raises(TrajectoryReplayError, match="failed to request trajectory"):
            mgr.replay_step(nova=MagicMock(), step=step)

    def test_happy_path_returns_replay_result(self, tmp_path, monkeypatch):
        _patch_trajectory_with_steps(monkeypatch, step_count=2)
        _patch_program_runner(monkeypatch, return_after_first=False)

        api = _make_api(download_url="https://s3.example/get")
        mgr = _make_manager(tmp_path, api=api)

        # Fake a successful HTTP GET that writes to the temp file.
        class _Ctx:
            def __init__(self, chunks):
                self._chunks = chunks

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                for c in self._chunks:
                    yield c

        monkeypatch.setattr(
            "qa_studio_cli.runner.trajectory.requests.get",
            MagicMock(return_value=_Ctx([b'{"steps": []}'])),
        )

        # nova with fake internal attributes
        nova = MagicMock()
        nova._client_tools = []
        nova._event_handler = MagicMock()

        step = {"step_id": "step-1", "trajectory_s3_key": "uc-1/trajectories/step-1.json"}
        result = mgr.replay_step(nova=nova, step=step)
        assert isinstance(result, ReplayResult)
        assert result.success is True
        assert result.trajectory_s3_key == "uc-1/trajectories/step-1.json"
        assert result.duration_ms >= 0

    def test_program_error_raises_replay_error(self, tmp_path, monkeypatch):
        _patch_trajectory_with_steps(monkeypatch, step_count=1)
        _patch_program_runner(monkeypatch, fail_with=RuntimeError("program crashed"))

        api = _make_api(download_url="https://s3.example/get")
        mgr = _make_manager(tmp_path, api=api)

        class _Ctx:
            def __enter__(self): return self
            def __exit__(self, *exc): return False
            def raise_for_status(self): return None
            def iter_content(self, chunk_size):
                yield b'{"steps": []}'

        monkeypatch.setattr(
            "qa_studio_cli.runner.trajectory.requests.get",
            MagicMock(return_value=_Ctx()),
        )

        nova = MagicMock()
        nova._client_tools = []
        nova._event_handler = MagicMock()

        step = {"step_id": "step-1", "trajectory_s3_key": "k"}
        with pytest.raises(TrajectoryReplayError, match="replay failed"):
            mgr.replay_step(nova=nova, step=step)


# ---------------------------------------------------------------------------
# is_recording_enabled
# ---------------------------------------------------------------------------


class TestIsRecordingEnabled:
    def test_tracks_replayable_supported(self, tmp_path):
        assert _make_manager(tmp_path, replayable_supported=True).is_recording_enabled is True
        assert _make_manager(tmp_path, replayable_supported=False).is_recording_enabled is False
