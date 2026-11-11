"""Tests for ``runner.main.run_usecase`` and its per-use-case executors.

The API layer and the engine are mocked; the assertions are about control
flow — what is fetched, what is executed, what is printed, and the exit
code.
"""

from __future__ import annotations

import json
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

try:  # pragma: no cover - environment dependent
    import nova_act  # noqa: F401
    import tenacity  # noqa: F401
except ImportError:  # pragma: no cover - environment dependent
    sys.modules.setdefault("nova_act", ModuleType("nova_act"))
    sys.modules.setdefault("tenacity", ModuleType("tenacity"))

from qa_studio_cli.runner import main as main_mod  # noqa: E402


def _usecase(uid="u-1", name="Login"):
    return {
        "id": uid, "name": name, "starting_url": "https://example.test",
        "test_platform": "web", "executing_region": "eu-central-1",
        "model_id": "nova-act-v1.0",
    }


@pytest.fixture
def api_mocks():
    usecase_api = MagicMock()
    usecase_api.get_usecase.return_value = _usecase()
    usecase_api.get_steps.return_value = []
    usecase_api.get_variables.return_value = {}
    usecase_api.get_secrets.return_value = []
    with (
        patch.object(main_mod, "_validate_aws_session"),
        patch.object(main_mod, "_build_api_client", return_value=MagicMock()),
        patch.object(main_mod, "UseCaseAPI", return_value=usecase_api),
    ):
        yield usecase_api


@pytest.fixture
def engine_cls():
    engine = MagicMock()
    engine.execute_usecase_local.return_value = {
        "status": "success", "usecaseId": "u-1", "usecaseName": "Login",
        "duration": 1.0, "steps": [], "artifacts": {},
    }
    with patch.object(main_mod, "ExecutionEngine", return_value=engine) as cls:
        cls.instance = engine
        yield cls


class TestExecuteUsecaseLocal:
    """``_execute_usecase_local`` returns the engine result and never exits."""

    def test_returns_engine_result_without_exiting(self, api_mocks, engine_cls):
        result = main_mod._execute_usecase_local(
            usecase_id="u-1",
            usecase=_usecase(),
            usecase_api=api_mocks,
            base_url=None,
            variables={},
            region=None,
            model_id=None,
        )
        assert result is engine_cls.instance.execute_usecase_local.return_value
        # The definition is passed in; the executor must not refetch it.
        api_mocks.get_usecase.assert_not_called()
        api_mocks.get_steps.assert_called_once_with("u-1")

    def test_uses_name_from_definition(self, api_mocks, engine_cls):
        main_mod._execute_usecase_local(
            usecase_id="u-1",
            usecase=_usecase(name="Checkout"),
            usecase_api=api_mocks,
            base_url="http://localhost:3000",
            variables={"k": "v"},
            region=None,
            model_id=None,
        )
        _, kwargs = engine_cls.instance.execute_usecase_local.call_args
        assert kwargs["usecase_name"] == "Checkout"
        # No --region: the engine keeps boto's default chain (AWS_REGION, profile).
        assert kwargs["region"] is None
        assert kwargs["starting_url"].startswith("http://localhost:3000")
        assert kwargs["variables"] == {"k": "v"}

    def test_region_flag_reaches_the_local_engine(self, api_mocks, engine_cls):
        main_mod._execute_usecase_local(
            usecase_id="u-1", usecase=_usecase(), usecase_api=api_mocks,
            base_url=None, variables={}, region="eu-west-1", model_id=None,
        )
        assert engine_cls.instance.execute_usecase_local.call_args.kwargs["region"] == "eu-west-1"

    def test_agentcore_rejected(self, api_mocks, engine_cls):
        with pytest.raises(RuntimeError, match="agentcore"):
            main_mod._execute_usecase_local(
                usecase_id="u-1", usecase=_usecase(), usecase_api=api_mocks,
                base_url=None, variables={}, region=None, model_id=None,
                browser="agentcore",
            )


class TestExecuteUsecaseRemote:
    """``_execute_usecase_remote`` returns a dumped RemoteExecutionResult."""

    def test_creates_execution_and_returns_dump(self, api_mocks, engine_cls):
        api_mocks.create_execution.return_value = {"executionId": "ex-9"}
        with (
            patch.object(main_mod, "ExecutionAPI"),
            patch.object(
                main_mod.asyncio, "run",
                side_effect=[{"usecase_name": "Login"}, {"status": "failed", "duration": 3, "usecase_name": "Login"}],
            ),
        ):
            result = main_mod._execute_usecase_remote(
                usecase_id="u-1", usecase_api=api_mocks, api_client=MagicMock(),
                base_url=None, variables={}, region=None, model_id=None,
            )
        assert result["executionId"] == "ex-9"
        assert result["status"] == "failed"
        assert result["usecaseName"] == "Login"
        api_mocks.create_execution.assert_called_once()

    def test_attaches_to_given_execution(self, api_mocks, engine_cls):
        with (
            patch.object(main_mod, "ExecutionAPI"),
            patch.object(
                main_mod.asyncio, "run",
                side_effect=[{"usecase_name": "Login"}, {"status": "success", "duration": 1}],
            ),
        ):
            result = main_mod._execute_usecase_remote(
                usecase_id="u-1", usecase_api=api_mocks, api_client=MagicMock(),
                base_url=None, variables={}, region=None, model_id=None,
                execution_id="ex-1",
            )
        assert result["executionId"] == "ex-1"
        api_mocks.create_execution.assert_not_called()

    def test_definition_name_wins_over_execution_record(self, api_mocks, engine_cls):
        """Single-use-case execution records carry no ``usecase_name``; the
        definition fetched by ``run_usecase`` provides the real name."""
        api_mocks.create_execution.return_value = {"executionId": "ex-9"}
        with (
            patch.object(main_mod, "ExecutionAPI"),
            patch.object(
                main_mod.asyncio, "run",
                side_effect=[{"status": "pending"}, {"status": "success", "duration": 1}],
            ),
        ):
            result = main_mod._execute_usecase_remote(
                usecase_id="u-1", usecase_api=api_mocks, api_client=MagicMock(),
                base_url=None, variables={}, region=None, model_id=None,
                usecase_name="Checkout",
            )
        execution = engine_cls.instance.execute_usecase.call_args.args[0]
        assert execution["usecase_name"] == "Checkout"
        assert result["usecaseName"] == "Checkout"

    def test_falls_back_to_execution_record_name_then_id(self, api_mocks, engine_cls):
        api_mocks.create_execution.return_value = {"executionId": "ex-9"}
        with (
            patch.object(main_mod, "ExecutionAPI"),
            patch.object(
                main_mod.asyncio, "run",
                side_effect=[{"status": "pending"}, {"status": "success", "duration": 1}],
            ),
        ):
            main_mod._execute_usecase_remote(
                usecase_id="u-1", usecase_api=api_mocks, api_client=MagicMock(),
                base_url=None, variables={}, region=None, model_id=None,
            )
        execution = engine_cls.instance.execute_usecase.call_args.args[0]
        assert execution["usecase_name"] == "u-1"

    def test_run_usecase_passes_definition_name_to_remote(self, api_mocks, engine_cls):
        api_mocks.get_usecase.return_value = _usecase(name="Checkout")
        api_mocks.create_execution.return_value = {"executionId": "ex-9"}
        with (
            patch.object(main_mod, "ExecutionAPI"),
            patch.object(
                main_mod.asyncio, "run",
                side_effect=[{"status": "pending"}, {"status": "success", "duration": 1}],
            ),
        ):
            with pytest.raises(SystemExit):
                main_mod.run_usecase(usecase_ids=["u-1"], local_only=False)
        execution = engine_cls.instance.execute_usecase.call_args.args[0]
        assert execution["usecase_name"] == "Checkout"


class TestRunUsecaseSingle:
    """Single-ID behaviour must stay byte-identical to the pre-feature CLI."""

    def test_json_output_is_bare_result_and_exit_0(self, api_mocks, engine_cls, capsys):
        with pytest.raises(SystemExit) as exc:
            main_mod.run_usecase(usecase_ids=["u-1"], local_only=True)
        assert exc.value.code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["usecaseId"] == "u-1"
        assert "results" not in out

    def test_failed_result_exits_1(self, api_mocks, engine_cls, capsys):
        engine_cls.instance.execute_usecase_local.return_value["status"] = "failed"
        with pytest.raises(SystemExit) as exc:
            main_mod.run_usecase(usecase_ids=["u-1"], local_only=True)
        assert exc.value.code == 1

    def test_human_output_has_no_summary_block(self, api_mocks, engine_cls, capsys):
        with pytest.raises(SystemExit):
            main_mod.run_usecase(usecase_ids=["u-1"], local_only=True, output_format="human")
        out = capsys.readouterr().out
        assert "QA Studio - Local Execution" in out
        assert "Run Summary" not in out

    def test_unknown_usecase_exits_2(self, api_mocks, engine_cls):
        api_mocks.get_usecase.side_effect = RuntimeError("404")
        with pytest.raises(SystemExit) as exc:
            main_mod.run_usecase(usecase_ids=["nope"], local_only=True)
        assert exc.value.code == 2
        engine_cls.instance.execute_usecase_local.assert_not_called()

    def test_execution_id_warns_in_local_only(self, api_mocks, engine_cls, caplog):
        with pytest.raises(SystemExit):
            main_mod.run_usecase(usecase_ids=["u-1"], local_only=True, execution_id="ex-1")
        assert "--execution-id is ignored in --local-only mode" in caplog.text


def _result(uid, name, status="success"):
    return {
        "status": status, "usecaseId": uid, "usecaseName": name,
        "duration": 1.0, "steps": [], "artifacts": {},
    }


@pytest.fixture
def two_usecases(api_mocks, engine_cls):
    """Two definitions ``u-1``/``u-2``; the engine answers per usecase_id."""
    defs = {"u-1": _usecase("u-1", "Login"), "u-2": _usecase("u-2", "Checkout")}
    api_mocks.get_usecase.side_effect = lambda uid: defs[uid]
    outcomes = {"u-1": "success", "u-2": "success"}

    def _exec(**kwargs):
        uid = kwargs["usecase_id"]
        return _result(uid, defs[uid]["name"], outcomes[uid])

    engine_cls.instance.execute_usecase_local.side_effect = _exec
    return outcomes


class TestRunUsecaseMulti:
    """Two or more IDs: sequential loop, summary, exit codes."""

    def test_all_pass_prints_summary_and_exits_0(self, two_usecases, engine_cls, capsys):
        with pytest.raises(SystemExit) as exc:
            main_mod.run_usecase(usecase_ids=["u-1", "u-2"], local_only=True)
        assert exc.value.code == 0
        summary = json.loads(capsys.readouterr().out)
        assert (summary["total"], summary["passed"], summary["failed"], summary["skipped"]) == (2, 2, 0, 0)
        assert [r["usecaseId"] for r in summary["results"]] == ["u-1", "u-2"]
        assert engine_cls.instance.execute_usecase_local.call_count == 2

    def test_one_fails_both_run_exit_1(self, two_usecases, engine_cls, capsys):
        two_usecases["u-1"] = "failed"
        with pytest.raises(SystemExit) as exc:
            main_mod.run_usecase(usecase_ids=["u-1", "u-2"], local_only=True)
        assert exc.value.code == 1
        summary = json.loads(capsys.readouterr().out)
        assert [r["status"] for r in summary["results"]] == ["failed", "success"]
        assert engine_cls.instance.execute_usecase_local.call_count == 2

    def test_fail_fast_skips_remaining(self, two_usecases, engine_cls, capsys):
        two_usecases["u-1"] = "failed"
        with pytest.raises(SystemExit) as exc:
            main_mod.run_usecase(usecase_ids=["u-1", "u-2"], local_only=True, fail_fast=True)
        assert exc.value.code == 1
        summary = json.loads(capsys.readouterr().out)
        assert [r["status"] for r in summary["results"]] == ["failed", "skipped"]
        assert summary["results"][1]["usecaseName"] == "Checkout"
        assert engine_cls.instance.execute_usecase_local.call_count == 1

    def test_unknown_id_exits_2_before_anything_runs(self, two_usecases, api_mocks, engine_cls):
        api_mocks.get_usecase.side_effect = lambda uid: {"u-1": _usecase()}[uid]
        with pytest.raises(SystemExit) as exc:
            main_mod.run_usecase(usecase_ids=["u-1", "missing"], local_only=True)
        assert exc.value.code == 2
        engine_cls.instance.execute_usecase_local.assert_not_called()

    def test_executor_exception_is_recorded_as_failed(self, two_usecases, engine_cls, capsys):
        def _boom(**kwargs):
            if kwargs["usecase_id"] == "u-1":
                raise RuntimeError("browser crashed")
            return _result("u-2", "Checkout")

        engine_cls.instance.execute_usecase_local.side_effect = _boom
        with pytest.raises(SystemExit) as exc:
            main_mod.run_usecase(usecase_ids=["u-1", "u-2"], local_only=True)
        assert exc.value.code == 1
        summary = json.loads(capsys.readouterr().out)
        assert summary["results"][0]["status"] == "failed"
        assert "browser crashed" in summary["results"][0]["error"]
        assert summary["results"][1]["status"] == "success"

    def test_human_prints_each_detail_then_summary(self, two_usecases, capsys):
        two_usecases["u-2"] = "failed"
        with pytest.raises(SystemExit):
            main_mod.run_usecase(usecase_ids=["u-1", "u-2"], local_only=True, output_format="human")
        out = capsys.readouterr().out
        assert out.count("QA Studio - Local Execution") == 2
        assert out.rstrip().endswith("\u2713 Login\n\u2717 Checkout")
        assert "Passed: 1/2" in out

    def test_remote_entries_carry_execution_id(self, two_usecases, api_mocks, engine_cls, capsys):
        api_mocks.create_execution.side_effect = [{"executionId": "ex-1"}, {"executionId": "ex-2"}]
        with (
            patch.object(main_mod, "ExecutionAPI"),
            patch.object(
                main_mod.asyncio, "run",
                side_effect=[
                    {"usecase_name": "Login"}, {"status": "success", "duration": 1},
                    {"usecase_name": "Checkout"}, {"status": "success", "duration": 1},
                ],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main_mod.run_usecase(usecase_ids=["u-1", "u-2"], local_only=False)
        assert exc.value.code == 0
        summary = json.loads(capsys.readouterr().out)
        assert [r["executionId"] for r in summary["results"]] == ["ex-1", "ex-2"]


class TestRunSuiteLocal:
    """``_run_suite_local`` delegates to the shared local executor."""

    @pytest.fixture
    def suite_api(self):
        api = MagicMock()
        api.get_suite.return_value = {"name": "Smoke"}
        api.list_usecases.return_value = [
            {"usecaseId": "u-1", "usecaseName": "Login"},
            {"usecaseId": "u-2", "usecaseName": "Checkout"},
        ]
        with patch.object(main_mod, "TestSuiteAPI", return_value=api):
            yield api

    def test_shared_executor_called_once_per_usecase_with_prefetched_definition(
        self, two_usecases, api_mocks, suite_api, capsys,
    ):
        with patch.object(
            main_mod, "_execute_usecase_local",
            side_effect=lambda **kw: _result(kw["usecase_id"], kw["usecase"]["name"]),
        ) as executor:
            with pytest.raises(SystemExit) as exc:
                main_mod.run_runner(suite_id="s-1", local_only=True)
        assert exc.value.code == 0
        calls = [c.kwargs for c in executor.call_args_list]
        assert [c["usecase_id"] for c in calls] == ["u-1", "u-2"]
        assert calls[1]["usecase"]["name"] == "Checkout"
        # Definitions are fetched exactly once each — by the suite loop, not the executor.
        assert api_mocks.get_usecase.call_count == 2
        out = json.loads(capsys.readouterr().out)
        assert [r["usecaseId"] for r in out] == ["u-1", "u-2"]

    def test_all_definitions_fetched_before_any_execution(self, two_usecases, api_mocks, suite_api, engine_cls):
        order = []
        api_mocks.get_usecase.side_effect = lambda uid: order.append(("fetch", uid)) or _usecase(uid, uid)
        engine_cls.instance.execute_usecase_local.side_effect = (
            lambda **kw: order.append(("run", kw["usecase_id"])) or _result(kw["usecase_id"], kw["usecase_id"])
        )
        with pytest.raises(SystemExit):
            main_mod.run_runner(suite_id="s-1", local_only=True)
        assert order == [("fetch", "u-1"), ("fetch", "u-2"), ("run", "u-1"), ("run", "u-2")]

    def test_secrets_fetch_failure_is_a_runner_error(self, two_usecases, api_mocks, suite_api, engine_cls):
        api_mocks.get_secrets.side_effect = RuntimeError("403 forbidden")
        with pytest.raises(SystemExit) as exc:
            main_mod.run_runner(suite_id="s-1", local_only=True)
        assert exc.value.code == 2
        engine_cls.instance.execute_usecase_local.assert_not_called()

    def test_one_engine_per_usecase(self, two_usecases, suite_api, engine_cls):
        with pytest.raises(SystemExit):
            main_mod.run_runner(suite_id="s-1", local_only=True, headful=True, local_browser="chrome")
        assert engine_cls.call_count == 2
        selection = engine_cls.call_args.kwargs["browser_selection"]
        assert selection.local_browser == "chrome"
        assert selection.headless is False

    def test_failed_usecase_gives_exit_1_and_table(self, two_usecases, suite_api, capsys):
        two_usecases["u-2"] = "failed"
        with pytest.raises(SystemExit) as exc:
            main_mod.run_runner(suite_id="s-1", local_only=True, output_format="human")
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "Suite: Smoke" in out
        assert "✗ Checkout" in out


class TestProgressWiring:
    """``runner.progress`` announcements and the suite-only step prefix."""

    @pytest.fixture
    def progress_mocks(self):
        from qa_studio_cli.runner import progress

        with (
            patch.object(progress, "test_started") as test_started,
            patch.object(progress, "step_started") as step_started,
        ):
            yield {"test_started": test_started, "step_started": step_started}

    @pytest.fixture
    def suite_api(self):
        api = MagicMock()
        api.get_suite.return_value = {"name": "Smoke"}
        api.list_usecases.return_value = [
            {"usecaseId": "u-1", "usecaseName": "Login"},
            {"usecaseId": "u-2", "usecaseName": "Checkout"},
        ]
        with patch.object(main_mod, "TestSuiteAPI", return_value=api):
            yield api

    def test_local_executor_announces_test_without_execution_id(self, api_mocks, engine_cls, progress_mocks):
        main_mod._execute_usecase_local(
            usecase_id="u-1", usecase=_usecase(name="Checkout"), usecase_api=api_mocks,
            base_url=None, variables={}, region=None, model_id=None,
        )
        progress_mocks["test_started"].assert_called_once_with("Checkout")

    def test_single_run_engine_has_no_step_prefix(self, api_mocks, engine_cls, progress_mocks):
        with pytest.raises(SystemExit):
            main_mod.run_usecase(usecase_ids=["u-1"], local_only=True)
        assert engine_cls.call_args.kwargs["show_test_name_on_steps"] is False

    def test_multi_run_engine_has_no_step_prefix(self, two_usecases, engine_cls, progress_mocks):
        with pytest.raises(SystemExit):
            main_mod.run_usecase(usecase_ids=["u-1", "u-2"], local_only=True)
        assert all(c.kwargs["show_test_name_on_steps"] is False for c in engine_cls.call_args_list)

    def test_local_suite_engines_prefix_steps(self, two_usecases, suite_api, engine_cls, progress_mocks):
        with pytest.raises(SystemExit):
            main_mod.run_runner(suite_id="s-1", local_only=True)
        assert engine_cls.call_count == 2
        assert all(c.kwargs["show_test_name_on_steps"] is True for c in engine_cls.call_args_list)

    def test_remote_suite_engine_prefixes_steps(self, api_mocks, suite_api, engine_cls, progress_mocks):
        suite_api.execute_suite.return_value = {
            "suite_execution_id": "se-1", "execution_ids": [{"execution_id": "ex-1"}],
        }
        results = [{"execution_id": "ex-1", "usecase_id": "u-1", "usecase_name": "Login",
                    "status": "success", "duration": 1, "error": None}]
        with (
            patch.object(main_mod, "ExecutionAPI"),
            patch.object(main_mod, "SuiteLogCapture") as capture_cls,
            patch.object(main_mod.asyncio, "run", side_effect=[results, None]),
        ):
            capture_cls.return_value.stop.return_value = None
            with pytest.raises(SystemExit) as exc:
                main_mod.run_runner(suite_id="s-1", local_only=False)
        assert exc.value.code == 0
        assert engine_cls.call_args.kwargs["show_test_name_on_steps"] is True

    def test_remote_single_run_engine_has_no_step_prefix(self, api_mocks, engine_cls, progress_mocks):
        api_mocks.create_execution.return_value = {"executionId": "ex-9"}
        with (
            patch.object(main_mod, "ExecutionAPI"),
            patch.object(
                main_mod.asyncio, "run",
                side_effect=[{"usecase_name": "Login"}, {"status": "success", "duration": 1}],
            ),
        ):
            main_mod._execute_usecase_remote(
                usecase_id="u-1", usecase_api=api_mocks, api_client=MagicMock(),
                base_url=None, variables={}, region=None, model_id=None,
            )
        assert engine_cls.call_args.kwargs["show_test_name_on_steps"] is False
