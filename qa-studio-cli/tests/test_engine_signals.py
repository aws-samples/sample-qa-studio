"""SIGTERM makes ``qa-studio run`` report a terminal state (microvm-runner, task 01).

The main thread only *watches* the run (``run_bounded``); SIGTERM is turned
into :class:`RunnerTerminated` there, the run's :class:`RunDeadline` is
terminated, and the engine's existing deadline checks / ``finally`` blocks do
the rest: fail the current step, tear the browser down, PATCH the execution
``failed`` with a ``terminated:`` / ``timeout:`` message, exit non-zero.
"""

from __future__ import annotations

import asyncio
import math
import os
import signal
import sys
import threading
import time
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:  # pragma: no cover - environment dependent
    import nova_act  # noqa: F401
    import tenacity  # noqa: F401
except ImportError:  # pragma: no cover - environment dependent
    sys.modules.setdefault("nova_act", ModuleType("nova_act"))
    sys.modules.setdefault("tenacity", ModuleType("tenacity"))

from qa_studio_cli.cli import cli  # noqa: E402
from qa_studio_cli.models.errors import ApiError  # noqa: E402
from qa_studio_cli.runner import deadline as deadline_mod  # noqa: E402
from qa_studio_cli.runner import engine as engine_mod  # noqa: E402
from qa_studio_cli.runner import main as main_mod  # noqa: E402
from qa_studio_cli.runner import progress  # noqa: E402
from qa_studio_cli.runner.deadline import (  # noqa: E402
    EXIT_TERMINATED,
    EXIT_TIMEOUT,
    RunDeadline,
    run_bounded,
)
from qa_studio_cli.runner.engine import ExecutionEngine  # noqa: E402
from qa_studio_cli.runner.termination import (  # noqa: E402
    MAX_DURATION_ENV,
    TERMINATION_REASON_ENV,
    RunnerTerminated,
    Termination,
    resolve_termination,
    sigterm_raises,
)

TERMINATED_MESSAGE = "terminated: run stopped by SIGTERM"


def _sigterm_self() -> None:
    os.kill(os.getpid(), signal.SIGTERM)


def _spin(seconds: float = 1.0) -> None:
    """Execute bytecode for a while so a pending signal handler can run."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        time.sleep(0.01)


@pytest.fixture(autouse=True)
def _clean_termination_env(monkeypatch):
    monkeypatch.delenv(TERMINATION_REASON_ENV, raising=False)
    monkeypatch.delenv(MAX_DURATION_ENV, raising=False)


@pytest.fixture(autouse=True)
def _sigterm_default_restored():
    """Every test must leave SIGTERM exactly as it found it."""
    before = signal.getsignal(signal.SIGTERM)
    yield
    assert signal.getsignal(signal.SIGTERM) is before


# ---------------------------------------------------------------------------
# Reason mapping (env contract with the supervisor)
# ---------------------------------------------------------------------------


class TestResolveTermination:
    def test_default_is_terminated(self):
        assert resolve_termination({}) == Termination(
            reason="terminated", message=TERMINATED_MESSAGE,
        )

    def test_timeout_reason_without_ceiling(self):
        t = resolve_termination({TERMINATION_REASON_ENV: "timeout"})
        assert t.reason == "timeout"
        assert t.message == "timeout: run exceeded the configured ceiling"

    def test_timeout_reason_includes_the_configured_ceiling(self):
        t = resolve_termination({TERMINATION_REASON_ENV: "timeout", MAX_DURATION_ENV: "3600"})
        assert t.message == "timeout: run exceeded the configured ceiling of 3600s"

    def test_unknown_reason_falls_back_to_terminated(self, caplog):
        with caplog.at_level("WARNING"):
            t = resolve_termination({TERMINATION_REASON_ENV: "banana"})
        assert t.reason == "terminated"
        assert "banana" in caplog.text

    def test_invalid_ceiling_is_ignored(self, caplog):
        with caplog.at_level("WARNING"):
            t = resolve_termination({TERMINATION_REASON_ENV: "timeout", MAX_DURATION_ENV: "soon"})
        assert t.message == "timeout: run exceeded the configured ceiling"
        assert MAX_DURATION_ENV in caplog.text


# ---------------------------------------------------------------------------
# Signal → exception in the main thread
# ---------------------------------------------------------------------------


class TestSigtermRaises:
    def test_raises_runner_terminated_in_the_main_thread(self):
        assert threading.current_thread() is threading.main_thread()
        with pytest.raises(RunnerTerminated) as exc:
            with sigterm_raises():
                _sigterm_self()
                _spin()
        assert exc.value.termination.message == TERMINATED_MESSAGE
        assert not isinstance(exc.value, Exception), "must not be swallowed by `except Exception`"

    def test_reason_is_read_when_the_signal_arrives(self, monkeypatch):
        with pytest.raises(RunnerTerminated) as exc:
            with sigterm_raises():
                monkeypatch.setenv(TERMINATION_REASON_ENV, "timeout")
                monkeypatch.setenv(MAX_DURATION_ENV, "60")
                _sigterm_self()
                _spin()
        assert exc.value.termination.message == "timeout: run exceeded the configured ceiling of 60s"

    def test_previous_handler_is_restored(self):
        previous = signal.getsignal(signal.SIGTERM)
        with sigterm_raises():
            assert signal.getsignal(signal.SIGTERM) is not previous
        assert signal.getsignal(signal.SIGTERM) is previous

    def test_not_installed_off_the_main_thread(self, caplog):
        seen = {}

        def _target():
            with sigterm_raises():
                seen["handler"] = signal.getsignal(signal.SIGTERM)

        t = threading.Thread(target=_target)
        with caplog.at_level("WARNING"):
            t.start()
            t.join(5)
        assert seen["handler"] is signal.getsignal(signal.SIGTERM)
        assert "main thread" in caplog.text


# ---------------------------------------------------------------------------
# RunDeadline without a time limit, terminated externally
# ---------------------------------------------------------------------------


class TestUnlimitedDeadline:
    def test_start_without_timeout_is_unlimited_but_present(self):
        d = RunDeadline.start(None)
        assert isinstance(d, RunDeadline)
        assert d.seconds is None
        assert not d.expired()
        assert d.remaining() == math.inf
        assert not d.terminated

    def test_terminate_expires_it_with_the_termination_message(self):
        d = RunDeadline.start(None)
        d.terminate(Termination(reason="terminated", message=TERMINATED_MESSAGE))
        assert d.expired() and d.terminated
        assert d.remaining() == 0.0
        assert d.message == TERMINATED_MESSAGE
        assert d.exit_code == EXIT_TERMINATED

    def test_first_termination_wins(self):
        d = RunDeadline(600)
        d.terminate(Termination(reason="timeout", message="timeout: x"))
        d.terminate(Termination(reason="terminated", message=TERMINATED_MESSAGE))
        assert d.message == "timeout: x"
        assert d.exit_code == EXIT_TIMEOUT

    def test_time_expiry_keeps_the_timeout_exit_code(self):
        clock = MagicMock(return_value=0.0)
        d = RunDeadline(10, clock=clock)
        clock.return_value = 11.0
        assert d.expired() and not d.terminated
        assert d.exit_code == EXIT_TIMEOUT
        assert d.message == "Run timed out after 10s (--timeout)"

    def test_hard_stop_cleanup_uses_the_termination_message(self):
        d = RunDeadline.start(None)
        api = MagicMock()
        api.update_status = AsyncMock()
        d.track_execution(api, "u-1", "ex-1")
        d.terminate(resolve_termination({}))
        d.hard_stop_cleanup()
        api.update_status.assert_awaited_once_with(
            usecase_id="u-1", execution_id="ex-1",
            status="failed", error_message=TERMINATED_MESSAGE,
        )


# ---------------------------------------------------------------------------
# run_bounded: the watcher
# ---------------------------------------------------------------------------


class TestRunBoundedTermination:
    def test_handler_is_active_only_while_the_run_is_running(self):
        before = signal.getsignal(signal.SIGTERM)
        seen = {}

        def _fn():
            seen["handler"] = signal.getsignal(signal.SIGTERM)
            seen["thread"] = threading.current_thread()
            return "ok"

        assert run_bounded(RunDeadline.start(None), _fn) == "ok"
        assert seen["handler"] is not before, "SIGTERM handler installed for the run"
        assert seen["thread"] is not threading.main_thread(), "body runs off the main thread"
        assert signal.getsignal(signal.SIGTERM) is before

    def test_cooperative_stop_sees_the_terminated_deadline(self):
        """The body polls the deadline like the engine does between steps."""
        d = RunDeadline.start(None)

        def _fn():
            _sigterm_self()
            end = time.monotonic() + 5
            while not d.expired() and time.monotonic() < end:
                time.sleep(0.01)
            return d.message

        with (
            patch.object(deadline_mod, "_exit_now") as exit_now,
            patch.object(progress, "run_terminated") as announced,
        ):
            assert run_bounded(d, _fn, termination_grace_seconds=5) == TERMINATED_MESSAGE
        exit_now.assert_not_called()
        announced.assert_called_once_with(TERMINATED_MESSAGE)

    def test_stuck_step_is_hard_stopped_with_the_terminated_reason(self):
        d = RunDeadline.start(None)
        api = MagicMock()
        api.update_status = AsyncMock()
        d.track_execution(api, "u-1", "ex-1")
        teardown = MagicMock()
        d.add_cleanup(teardown)
        release = threading.Event()

        def _stuck():
            _sigterm_self()
            release.wait(5)

        with (
            patch.object(deadline_mod, "_exit_now", side_effect=SystemExit(EXIT_TERMINATED)) as exit_now,
            patch.object(progress, "run_terminated") as announced,
            patch.object(progress, "run_timed_out") as timed_out,
        ):
            with pytest.raises(SystemExit) as exc:
                run_bounded(d, _stuck, termination_grace_seconds=0.05)
        release.set()

        assert exc.value.code == EXIT_TERMINATED
        exit_now.assert_called_once_with(EXIT_TERMINATED)
        announced.assert_called_once_with(TERMINATED_MESSAGE)
        timed_out.assert_not_called()
        teardown.assert_called_once()
        api.update_status.assert_awaited_once_with(
            usecase_id="u-1", execution_id="ex-1",
            status="failed", error_message=TERMINATED_MESSAGE,
        )

    def test_timeout_reason_from_the_parent_exits_3(self, monkeypatch):
        monkeypatch.setenv(TERMINATION_REASON_ENV, "timeout")
        monkeypatch.setenv(MAX_DURATION_ENV, "600")
        d = RunDeadline.start(None)
        api = MagicMock()
        api.update_status = AsyncMock()
        d.track_execution(api, "u-1", "ex-1")
        release = threading.Event()

        def _stuck():
            _sigterm_self()
            release.wait(5)

        with (
            patch.object(deadline_mod, "_exit_now", side_effect=SystemExit(EXIT_TIMEOUT)) as exit_now,
            patch.object(progress, "run_terminated"),
        ):
            with pytest.raises(SystemExit):
                run_bounded(d, _stuck, termination_grace_seconds=0.05)
        release.set()

        exit_now.assert_called_once_with(EXIT_TIMEOUT)
        message = api.update_status.await_args.kwargs["error_message"]
        assert message == "timeout: run exceeded the configured ceiling of 600s"

    def test_second_sigterm_skips_the_rest_of_the_grace(self):
        d = RunDeadline.start(None)
        release = threading.Event()

        def _stuck():
            _sigterm_self()
            end = time.monotonic() + 5
            while not d.terminated and time.monotonic() < end:
                time.sleep(0.01)
            time.sleep(0.1)
            _sigterm_self()
            release.wait(10)

        started = time.monotonic()
        with (
            patch.object(deadline_mod, "_exit_now", side_effect=SystemExit(EXIT_TERMINATED)) as exit_now,
            patch.object(progress, "run_terminated"),
        ):
            with pytest.raises(SystemExit):
                run_bounded(d, _stuck, termination_grace_seconds=30)
        release.set()

        assert time.monotonic() - started < 5
        exit_now.assert_called_once_with(EXIT_TERMINATED)


# ---------------------------------------------------------------------------
# Engine: the remote execution reports the termination
# ---------------------------------------------------------------------------


def _remote_engine(deadline, update_status=None):
    api = MagicMock()
    api.update_status = update_status or AsyncMock()
    api.get_execution = AsyncMock(return_value={"test_platform": "web"})
    api.client = MagicMock()
    return ExecutionEngine(execution_api=api, deadline=deadline), api


def _run_execute_usecase(engine, sync_result):
    with (
        patch.object(engine_mod, "ArtifactUploader") as uploader_cls,
        patch.object(engine_mod, "ArtifactCapture", return_value=MagicMock()),
        patch.object(engine, "_execute_usecase_sync", side_effect=sync_result),
        patch.object(progress, "test_started"),
    ):
        uploader_cls.return_value.upload_execution_artifacts = AsyncMock()
        return asyncio.run(engine.execute_usecase(
            {"execution_id": "ex-1", "usecase_id": "u-1", "usecase_name": "Login"},
        ))


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))


class TestEngineReportsTermination:
    def test_step_killed_by_the_signal_is_reported_as_terminated(self, home):
        """SIGTERM hits the process group: Playwright dies, ``nova.act`` raises.
        The execution must still say *terminated*, with the symptom attached."""
        deadline = RunDeadline.start(None)
        engine, api = _remote_engine(deadline)

        def _sync(*_a, **_kw):
            deadline.terminate(resolve_termination({}))
            return {"success": False, "error": "Nova Act execution failed: Connection closed"}

        result = _run_execute_usecase(engine, _sync)

        final = api.update_status.await_args_list[-1].kwargs
        assert final["status"] == "failed"
        assert final["error_message"] == (
            f"{TERMINATED_MESSAGE} (Nova Act execution failed: Connection closed)"
        )
        assert result["status"] == "failed"
        assert result["error"].startswith("terminated:")

    def test_cooperative_stop_message_is_not_duplicated(self, home):
        deadline = RunDeadline.start(None)
        engine, api = _remote_engine(deadline)

        def _sync(*_a, **_kw):
            deadline.terminate(resolve_termination({}))
            return {"success": False, "error": deadline.message}

        _run_execute_usecase(engine, _sync)
        assert api.update_status.await_args_list[-1].kwargs["error_message"] == TERMINATED_MESSAGE

    def test_a_run_that_passed_before_the_signal_stays_a_pass(self, home):
        deadline = RunDeadline.start(None)
        engine, api = _remote_engine(deadline)

        def _sync(*_a, **_kw):
            deadline.terminate(resolve_termination({}))
            return {"success": True}

        result = _run_execute_usecase(engine, _sync)
        final = api.update_status.await_args_list[-1].kwargs
        assert (final["status"], final["error_message"]) == ("success", None)
        assert result["error"] is None

    def test_exception_after_the_signal_is_reported_as_terminated(self, home):
        deadline = RunDeadline.start(None)
        engine, api = _remote_engine(deadline)

        def _sync(*_a, **_kw):
            deadline.terminate(resolve_termination({}))
            raise RuntimeError("socket closed")

        result = _run_execute_usecase(engine, _sync)
        final = api.update_status.await_args_list[-1].kwargs
        assert final["status"] == "failed"
        assert final["error_message"] == f"{TERMINATED_MESSAGE} (socket closed)"
        assert result["status"] == "failed"

    def test_terminal_execution_rejecting_the_patch_is_logged_not_raised(self, home, caplog):
        """``stop_execution`` wrote ``stopped`` first: the API answers 409."""
        deadline = RunDeadline.start(None)
        update_status = AsyncMock(side_effect=[
            {},  # running
            ApiError(409, "Execution is already terminal"),
        ])
        engine, api = _remote_engine(deadline, update_status=update_status)

        def _sync(*_a, **_kw):
            deadline.terminate(resolve_termination({}))
            return {"success": False, "error": deadline.message}

        with caplog.at_level("ERROR"):
            result = _run_execute_usecase(engine, _sync)

        assert result["status"] == "failed"
        assert api.update_status.await_count == 2, "no retry PATCH against a terminal execution"
        assert "already terminal" in caplog.text

    def test_remote_step_loop_fails_the_next_step_with_the_termination(self, home):
        """Same code path as ``--timeout`` between steps, different message."""
        from qa_studio_cli.models.execution import StepResult

        deadline = RunDeadline.start(None)
        api = MagicMock()
        for name in ("update_status", "update_session_id", "update_step_status",
                     "create_live_view", "delete_live_view"):
            setattr(api, name, AsyncMock())
        api.get_secret_value = MagicMock(return_value=None)
        api.client = MagicMock()
        engine = ExecutionEngine(execution_api=api, deadline=deadline)
        uploader = MagicMock()
        uploader.upload_step_artifacts = AsyncMock()
        steps = [
            {"step_id": "s1", "sk": "EXECUTION_STEP#s1", "sort": 1, "step_type": "navigation", "instruction": "Open"},
            {"step_id": "s2", "sk": "EXECUTION_STEP#s2", "sort": 2, "step_type": "navigation", "instruction": "Click"},
        ]
        details = {"test_platform": "web", "starting_url": "https://e.test/", "steps": steps,
                   "variables": {}, "headers": {}, "model_id": "m"}
        executed = []

        class _Executor:
            def __init__(self, *_a, **_kw):
                pass

            def execute(self, step, variables, runtime_variables):
                executed.append(step["step_id"])
                deadline.terminate(resolve_termination({}))  # SIGTERM lands mid-step
                return StepResult(success=True)

        class _Ctx:
            def __init__(self, **_kw):
                self.page = MagicMock()
                self.go_to_url = MagicMock()

            def get_session_id(self):
                return "sess-1"

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

        from qa_studio_cli.runner.browser import BrowserHandle

        teardown = MagicMock()
        handle = BrowserHandle(nova_kwargs={"starting_page": "https://e.test/"}, teardown=teardown)
        with (
            patch.object(engine_mod, "NovaAct", _Ctx),
            patch.object(engine_mod, "Workflow", _Ctx),
            patch.object(engine_mod, "StepExecutor", _Executor),
            patch.object(engine_mod, "WorkflowManager") as wf,
            patch.object(engine, "_build_browser_provisioner") as prov,
            patch.object(progress, "step_started"),
        ):
            wf.return_value.ensure_workflow.return_value = "wf-1"
            prov.return_value.provision.return_value = handle
            result = engine._execute_with_nova_act(details, "u-1", "ex-1", MagicMock(), uploader)

        assert executed == ["s1"]
        assert result == {"success": False, "error": TERMINATED_MESSAGE}
        last = api.update_step_status.await_args_list[-1].kwargs
        assert (last["step_id"], last["status"], last["error_message"]) == ("s2", "failed", TERMINATED_MESSAGE)
        teardown.assert_called_once(), "browser torn down on the normal finally path"
        assert deadline._cleanups == {}, "teardown unregistered from the hard stop"


# ---------------------------------------------------------------------------
# Exit code of a terminated run (runner.main)
# ---------------------------------------------------------------------------


class TestApplyTimeout:
    def test_terminated_run_exits_143_without_a_second_announcement(self):
        d = RunDeadline.start(None)
        d.terminate(resolve_termination({}))
        with patch.object(progress, "run_timed_out") as announced:
            assert main_mod._apply_timeout(1, d) == EXIT_TERMINATED
        announced.assert_not_called()

    def test_timeout_reason_exits_3(self):
        d = RunDeadline.start(None)
        d.terminate(resolve_termination({TERMINATION_REASON_ENV: "timeout"}))
        with patch.object(progress, "run_timed_out"):
            assert main_mod._apply_timeout(1, d) == EXIT_TIMEOUT

    def test_passed_run_is_a_pass(self):
        d = RunDeadline.start(None)
        d.terminate(resolve_termination({}))
        assert main_mod._apply_timeout(0, d) == 0

    def test_unlimited_deadline_does_not_change_the_exit_code(self):
        assert main_mod._apply_timeout(1, RunDeadline.start(None)) == 1


# ---------------------------------------------------------------------------
# Progress line
# ---------------------------------------------------------------------------


class TestProgressLine:
    def test_run_terminated_uses_the_run_stopped_line_shape(self, capsys, monkeypatch):
        from datetime import datetime

        monkeypatch.setattr(progress, "_now", lambda: datetime(2026, 5, 1, 14, 2, 11))
        progress.run_terminated(TERMINATED_MESSAGE)
        progress.run_timed_out("Run timed out after 5s (--timeout)")
        assert capsys.readouterr().err == (
            f"[14:02:11] ERROR {TERMINATED_MESSAGE}\n"
            "[14:02:11] ERROR Run timed out after 5s (--timeout)\n"
        )


# ---------------------------------------------------------------------------
# Handler installed only for the `run` command
# ---------------------------------------------------------------------------


class TestHandlerOnlyForRun:
    def test_other_commands_leave_sigterm_alone(self, cli_runner):
        with patch.object(signal, "signal") as sig:
            result = cli_runner.invoke(cli, ["tests", "--help"])
        assert result.exit_code == 0
        assert not any(c.args and c.args[0] == signal.SIGTERM for c in sig.call_args_list)

    def test_run_command_installs_it(self, cli_runner):
        before = signal.getsignal(signal.SIGTERM)
        seen = {}

        def _body(**_kw):
            seen["handler"] = signal.getsignal(signal.SIGTERM)
            raise SystemExit(0)

        with (
            patch.object(main_mod, "_run_usecases", side_effect=_body),
            patch("qa_studio_cli.utils.logger.setup_logging"),
        ):
            result = cli_runner.invoke(cli, ["run", "--usecase-id", "u-1", "--local-only"])
        assert result.exit_code == 0, result.output
        assert seen["handler"] is not before
        assert signal.getsignal(signal.SIGTERM) is before


# ---------------------------------------------------------------------------
# Whole process: SIGTERM from the outside, real exit code
# ---------------------------------------------------------------------------


_STUCK_RUNNER = """
import sys, threading, time
from qa_studio_cli.runner.deadline import RunDeadline, run_bounded

marker = sys.argv[1]
d = RunDeadline.start(None)
d.add_cleanup(lambda: open(marker, "w").write(d.message))
print("ready", flush=True)
run_bounded(d, lambda: threading.Event().wait(30), termination_grace_seconds=0.2)
"""


class TestProcessExit:
    @pytest.mark.parametrize("env_reason, expected_code, prefix", [
        ({}, EXIT_TERMINATED, "terminated:"),
        ({TERMINATION_REASON_ENV: "timeout", MAX_DURATION_ENV: "60"}, EXIT_TIMEOUT, "timeout:"),
    ])
    def test_sigterm_runs_cleanups_and_exits_non_zero(self, tmp_path, env_reason, expected_code, prefix):
        import subprocess

        marker = tmp_path / "cleanup-ran"
        proc = subprocess.Popen(
            [sys.executable, "-c", _STUCK_RUNNER, str(marker)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, **env_reason},
        )
        try:
            assert proc.stdout.readline().strip() == "ready"
            proc.send_signal(signal.SIGTERM)
            _, stderr = proc.communicate(timeout=20)
        finally:
            proc.kill()

        assert proc.returncode == expected_code, stderr
        assert marker.read_text().startswith(prefix)
        assert f"ERROR {prefix}" in stderr, "announced on stderr"
