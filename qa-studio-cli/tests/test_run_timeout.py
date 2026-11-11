"""``qa-studio run --timeout``: a whole-run limit, unset by default.

Covers the deadline itself, the cooperative stop (between use cases and
between steps, local and remote), the hard stop for a stuck step, and the
exit code (3).
"""

from __future__ import annotations

import json
import sys
import threading
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:  # pragma: no cover - environment dependent
    import nova_act  # noqa: F401
    import tenacity  # noqa: F401
except ImportError:  # pragma: no cover - environment dependent
    sys.modules.setdefault("nova_act", ModuleType("nova_act"))
    sys.modules.setdefault("tenacity", ModuleType("tenacity"))

from qa_studio_cli.models.execution import StepResult  # noqa: E402
from qa_studio_cli.runner import deadline as deadline_mod  # noqa: E402
from qa_studio_cli.runner import engine as engine_mod  # noqa: E402
from qa_studio_cli.runner import main as main_mod  # noqa: E402
from qa_studio_cli.runner import progress  # noqa: E402
from qa_studio_cli.runner.browser import BrowserHandle  # noqa: E402
from qa_studio_cli.runner.deadline import EXIT_TIMEOUT, RunDeadline, run_bounded  # noqa: E402
from qa_studio_cli.runner.engine import ExecutionEngine  # noqa: E402


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def fake_deadline_start(clock):
    """Make ``RunDeadline.start`` build deadlines on the fake clock."""
    created = []

    def _start(cls, seconds):
        d = cls(seconds, clock=clock)
        if seconds:
            created.append(d)
        return d

    with patch.object(RunDeadline, "start", classmethod(_start)):
        yield created


# ---------------------------------------------------------------------------
# RunDeadline
# ---------------------------------------------------------------------------


class TestRunDeadline:
    def test_no_timeout_means_an_unlimited_deadline(self):
        """Always present (SIGTERM can terminate it), never expires by time."""
        d = RunDeadline.start(None)
        assert d.seconds is None and not d.expired()

    def test_expires_after_the_given_seconds(self, clock):
        d = RunDeadline(10, clock=clock)
        assert not d.expired() and d.remaining() == 10
        clock.advance(9.5)
        assert not d.expired()
        clock.advance(0.5)
        assert d.expired() and d.remaining() == 0

    @pytest.mark.parametrize("seconds", [0, -1])
    def test_rejects_non_positive(self, seconds):
        with pytest.raises(ValueError):
            RunDeadline(seconds)

    def test_message_names_the_flag(self):
        assert RunDeadline(600).message == "Run timed out after 600s (--timeout)"

    def test_removed_cleanup_is_not_run(self):
        d = RunDeadline(1)
        keep, drop = MagicMock(), MagicMock()
        d.add_cleanup(keep)
        d.remove_cleanup(d.add_cleanup(drop))
        d.hard_stop_cleanup()
        keep.assert_called_once()
        drop.assert_not_called()

    def test_hard_stop_cleanup_is_best_effort(self):
        d = RunDeadline(1)
        api = MagicMock()
        api.update_status = AsyncMock(side_effect=RuntimeError("api down"))
        d.track_execution(api, "u-1", "ex-1")
        first = MagicMock(side_effect=RuntimeError("boom"))
        second = MagicMock()
        d.add_cleanup(first)
        d.add_cleanup(second)
        d.hard_stop_cleanup()
        second.assert_called_once()


# ---------------------------------------------------------------------------
# run_bounded
# ---------------------------------------------------------------------------


class TestRunBounded:
    def test_without_time_limit_runs_on_a_worker_thread(self):
        """The main thread only watches, so SIGTERM surfaces there."""
        caller = threading.current_thread()
        seen = []
        assert run_bounded(RunDeadline.start(None), lambda: seen.append(threading.current_thread()) or 7) == 7
        assert seen and seen[0] is not caller

    def test_returns_value_and_reraises_system_exit(self, clock):
        d = RunDeadline(60, clock=clock)
        assert run_bounded(d, lambda: "ok") == "ok"

        def _exit():
            sys.exit(1)

        with pytest.raises(SystemExit) as exc:
            run_bounded(d, _exit)
        assert exc.value.code == 1

    def test_stuck_step_triggers_hard_stop(self, clock):
        """A step that blocks past the deadline: executions are failed,
        browsers torn down, exit code 3 — without waiting for the step."""
        d = RunDeadline(5, clock=clock)
        api = MagicMock()
        api.update_status = AsyncMock()
        d.track_execution(api, "u-1", "ex-1")
        teardown = MagicMock()
        d.add_cleanup(teardown)
        release = threading.Event()

        def _stuck():
            clock.advance(10)
            release.wait(5)

        with (
            patch.object(deadline_mod, "_exit_now", side_effect=SystemExit(EXIT_TIMEOUT)) as exit_now,
            patch.object(progress, "run_timed_out") as announced,
        ):
            with pytest.raises(SystemExit) as exc:
                run_bounded(d, _stuck, grace_seconds=0.05)
        release.set()

        assert exc.value.code == EXIT_TIMEOUT
        exit_now.assert_called_once_with(EXIT_TIMEOUT)
        announced.assert_called_once_with("Run timed out after 5s (--timeout)")
        teardown.assert_called_once()
        api.update_status.assert_awaited_once_with(
            usecase_id="u-1", execution_id="ex-1",
            status="failed", error_message="Run timed out after 5s (--timeout)",
        )


# ---------------------------------------------------------------------------
# Between use cases (runner.main)
# ---------------------------------------------------------------------------


def _usecase(uid, name):
    return {"id": uid, "name": name, "starting_url": "https://e.test", "test_platform": "web"}


@pytest.fixture
def two_usecases():
    usecase_api = MagicMock()
    defs = {"u-1": _usecase("u-1", "Login"), "u-2": _usecase("u-2", "Checkout")}
    usecase_api.get_usecase.side_effect = lambda uid: defs[uid]
    usecase_api.get_steps.return_value = []
    usecase_api.get_variables.return_value = {}
    usecase_api.get_secrets.return_value = []
    engine = MagicMock()
    with (
        patch.object(main_mod, "_validate_aws_session"),
        patch.object(main_mod, "_build_api_client", return_value=MagicMock()),
        patch.object(main_mod, "UseCaseAPI", return_value=usecase_api),
        patch.object(main_mod, "ExecutionEngine", return_value=engine) as engine_cls,
    ):
        yield engine, engine_cls


def _result(uid, status="success"):
    return {"status": status, "usecaseId": uid, "usecaseName": uid,
            "duration": 1.0, "steps": [], "artifacts": {}}


class TestBetweenUsecases:
    def test_no_timeout_runs_everything_and_engine_gets_an_unlimited_deadline(self, two_usecases, capsys):
        engine, engine_cls = two_usecases
        engine.execute_usecase_local.side_effect = lambda **kw: _result(kw["usecase_id"])
        with pytest.raises(SystemExit) as exc:
            main_mod.run_usecase(usecase_ids=["u-1", "u-2"], local_only=True)
        assert exc.value.code == 0
        assert engine.execute_usecase_local.call_count == 2
        assert all(c.kwargs["deadline"].seconds is None for c in engine_cls.call_args_list)

    def test_expiry_after_first_usecase_skips_the_rest_and_exits_3(
            self, two_usecases, clock, fake_deadline_start, capsys):
        engine, engine_cls = two_usecases

        def _exec(**kw):
            clock.advance(601)
            return _result(kw["usecase_id"])

        engine.execute_usecase_local.side_effect = _exec
        with patch.object(progress, "run_timed_out") as announced:
            with pytest.raises(SystemExit) as exc:
                main_mod.run_usecase(usecase_ids=["u-1", "u-2"], local_only=True, timeout=600)

        assert exc.value.code == EXIT_TIMEOUT
        assert engine.execute_usecase_local.call_count == 1
        summary = json.loads(capsys.readouterr().out)
        assert [r["status"] for r in summary["results"]] == ["success", "skipped"]
        assert summary["results"][1]["error"] == "Run timed out after 600s (--timeout)"
        announced.assert_called_once()
        # The engine got the same deadline the loop checks.
        assert engine_cls.call_args.kwargs["deadline"] is fake_deadline_start[0]

    def test_run_that_passes_is_a_pass_even_after_the_deadline(
            self, two_usecases, clock, fake_deadline_start):
        engine, _ = two_usecases

        def _exec(**kw):
            clock.advance(601)
            return _result(kw["usecase_id"])

        engine.execute_usecase_local.side_effect = _exec
        with pytest.raises(SystemExit) as exc:
            main_mod.run_usecase(usecase_ids=["u-1"], local_only=True, timeout=600)
        assert exc.value.code == 0

    def test_single_usecase_cut_short_exits_3(self, two_usecases, clock, fake_deadline_start, capsys):
        engine, _ = two_usecases

        def _exec(**kw):
            clock.advance(601)
            return _result(kw["usecase_id"], status="failed")

        engine.execute_usecase_local.side_effect = _exec
        with patch.object(progress, "run_timed_out"):
            with pytest.raises(SystemExit) as exc:
                main_mod.run_usecase(usecase_ids=["u-1"], local_only=True, timeout=600)
        assert exc.value.code == EXIT_TIMEOUT
        assert json.loads(capsys.readouterr().out)["status"] == "failed"


# ---------------------------------------------------------------------------
# Between steps (engine)
# ---------------------------------------------------------------------------


class _FakeNovaAct:
    def __init__(self, **_kwargs):
        self.page = MagicMock()
        self.go_to_url = MagicMock()

    def get_session_id(self):
        return "sess-1"

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class _FakeWorkflow:
    def __init__(self, **_kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


STEPS = [
    {"step_id": "s1", "sort": 1, "step_type": "navigation", "instruction": "Open login"},
    {"step_id": "s2", "sort": 2, "step_type": "navigation", "instruction": "Click sign in"},
]


@pytest.fixture
def engine_fakes(clock):
    executed = []

    class _SlowExecutor:
        """Every step takes 400 fake seconds."""

        def __init__(self, *_a, **_kw):
            pass

        def execute(self, step, variables, runtime_variables):
            executed.append(step["step_id"])
            clock.advance(400)
            return StepResult(success=True)

    handle = BrowserHandle(nova_kwargs={"starting_page": "https://e.test/"})
    with (
        patch.object(engine_mod, "NovaAct", _FakeNovaAct),
        patch.object(engine_mod, "Workflow", _FakeWorkflow),
        patch.object(engine_mod, "StepExecutor", _SlowExecutor),
        patch.object(engine_mod, "WorkflowManager") as wf,
        patch.object(engine_mod, "LocalBrowserProvisioner") as prov,
        patch.object(progress, "step_started"),
    ):
        wf.return_value.ensure_workflow.return_value = "wf-1"
        prov.return_value.provision.return_value = handle
        yield executed


class TestBetweenSteps:
    def test_local_loop_fails_the_next_step_with_the_timeout(self, engine_fakes, clock):
        engine = ExecutionEngine(deadline=RunDeadline(300, clock=clock))
        result = engine.execute_usecase_local(
            usecase_id="u-1", usecase_name="Login", starting_url="https://e.test/",
            steps=STEPS, variables={}, secrets=[], region="us-east-1", model_id="m",
        )
        assert engine_fakes == ["s1"]
        assert result["status"] == "failed"
        assert [s["status"] for s in result["steps"]] == ["success", "failed"]
        assert result["steps"][1]["error"] == "Run timed out after 300s (--timeout)"

    def test_local_loop_without_deadline_runs_all_steps(self, engine_fakes):
        result = ExecutionEngine().execute_usecase_local(
            usecase_id="u-1", usecase_name="Login", starting_url="https://e.test/",
            steps=STEPS, variables={}, secrets=[], region="us-east-1", model_id="m",
        )
        assert engine_fakes == ["s1", "s2"]
        assert result["status"] == "success"

    def test_remote_loop_marks_the_step_failed_through_the_api(
            self, engine_fakes, clock, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        api = MagicMock()
        for name in ("update_status", "update_session_id", "update_step_status",
                     "create_live_view", "delete_live_view"):
            setattr(api, name, AsyncMock())
        api.get_secret_value = MagicMock(return_value=None)
        api.client = MagicMock()
        engine = ExecutionEngine(execution_api=api, deadline=RunDeadline(300, clock=clock))
        uploader = MagicMock()
        uploader.upload_step_artifacts = AsyncMock()
        details = {"test_platform": "web", "starting_url": "https://e.test/", "steps": [
            {**s, "sk": f"EXECUTION_STEP#{s['step_id']}"} for s in STEPS
        ], "variables": {}, "headers": {}, "model_id": "m"}

        result = engine._execute_with_nova_act(details, "u-1", "ex-1", MagicMock(), uploader)

        assert engine_fakes == ["s1"]
        assert result == {"success": False, "error": "Run timed out after 300s (--timeout)"}
        last = api.update_step_status.await_args_list[-1].kwargs
        assert (last["step_id"], last["status"], last["error_message"]) == (
            "s2", "failed", "Run timed out after 300s (--timeout)")

    def test_owned_browser_is_registered_for_the_hard_stop_and_released(self, clock):
        teardown = MagicMock()
        deadline = RunDeadline(300, clock=clock)
        engine = ExecutionEngine(deadline=deadline)
        token = engine._register_teardown(BrowserHandle(nova_kwargs={}, teardown=teardown))
        assert token is not None
        engine._unregister_teardown(token)
        deadline.hard_stop_cleanup()
        teardown.assert_not_called()
        assert engine._register_teardown(BrowserHandle(nova_kwargs={})) is None

    def test_execute_usecase_tracks_the_execution_while_running(self, clock, tmp_path, monkeypatch):
        import asyncio

        monkeypatch.setenv("HOME", str(tmp_path))
        deadline = RunDeadline(300, clock=clock)
        api = MagicMock()
        api.update_status = AsyncMock()
        api.get_execution = AsyncMock(return_value={"test_platform": "web"})
        api.client = MagicMock()
        engine = ExecutionEngine(execution_api=api, deadline=deadline)
        seen = {}

        def _sync(*_a, **_kw):
            seen["tracked"] = dict(deadline._executions)
            return {"success": True}

        with (
            patch.object(engine_mod, "ArtifactUploader") as uploader_cls,
            patch.object(engine_mod, "ArtifactCapture", return_value=MagicMock()),
            patch.object(engine, "_execute_usecase_sync", side_effect=_sync),
            patch.object(progress, "test_started"),
        ):
            uploader_cls.return_value.upload_execution_artifacts = AsyncMock()
            asyncio.run(engine.execute_usecase(
                {"execution_id": "ex-1", "usecase_id": "u-1", "usecase_name": "Login"},
            ))

        assert list(seen["tracked"]) == [("u-1", "ex-1")]
        assert deadline._executions == {}
