"""Row-variable resolution for expanded repeat steps (runner side).

Precedence: usecase variables < row variables < runtime captures < built-ins.
Expanded steps (``repeat_row_index`` present) never replay or save a
trajectory because ``step_id`` is shared by every row.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from qa_studio_cli.runner.step_executor import StepExecutor
from qa_studio_cli.runner.template_parser import TemplateParser


# ---------------------------------------------------------------------------
# TemplateParser.parse_instruction(text, row_variables=...)
# ---------------------------------------------------------------------------

class TestTemplateParserRowVariables:
    @pytest.mark.parametrize(
        "user, row, runtime, expected",
        [
            ({}, {"email": "row"}, {}, "row"),
            ({"email": "user"}, {"email": "row"}, {}, "row"),              # row > user
            ({"email": "user"}, {"email": "row"}, {"email": "rt"}, "rt"),  # runtime > row
            ({"email": "user"}, {}, {}, "user"),                           # no row value
            ({"email": "user"}, None, {}, "user"),                         # None == no rows
        ],
    )
    def test_precedence_table(self, user, row, runtime, expected):
        parser = TemplateParser(variables=user, runtime_variables=runtime)
        assert parser.parse_instruction("{{email}}", row_variables=row) == expected

    def test_builtins_win_over_row_variables(self):
        parser = TemplateParser(execution_id="exec-1")
        out = parser.parse_instruction("{{ExecutionID}}", row_variables={"ExecutionID": "nope"})
        assert out == "exec-1"

    def test_unique_id_stable_across_rows(self):
        parser = TemplateParser()
        first = parser.parse_instruction("{{UniqueID}}", row_variables={"a": "1"})
        second = parser.parse_instruction("{{UniqueID}}", row_variables={"a": "2"})
        assert first == second

    def test_row_variables_do_not_leak_into_later_calls(self):
        parser = TemplateParser(variables={"email": "user"})
        assert parser.parse_instruction("{{email}}", row_variables={"email": "row"}) == "row"
        assert parser.parse_instruction("{{email}}") == "user"

    def test_repeat_index_and_total(self):
        parser = TemplateParser()
        out = parser.parse_instruction(
            "{{RepeatIndex}}/{{RepeatTotal}}",
            row_variables={"RepeatIndex": "2", "RepeatTotal": "3"},
        )
        assert out == "2/3"

    def test_without_row_variables_unchanged(self):
        parser = TemplateParser(variables={"a": "1"}, runtime_variables={"b": "2"})
        assert parser.parse_instruction("{{a}}-{{b}}") == "1-2"


# ---------------------------------------------------------------------------
# StepExecutor._execute_assertion resolves against the merged set
# ---------------------------------------------------------------------------

class TestAssertionAgainstMergedVariables:
    def _step(self, var="role", expected="admin"):
        return {
            "step_type": "assertion", "assertion_variable": var,
            "validation_type": "string", "validation_operator": "exact",
            "validation_value": expected,
        }

    def test_column_value_can_be_asserted(self):
        executor = StepExecutor(MagicMock())
        result = executor.execute(self._step(), {"role": "admin"}, {})
        assert result.success is True
        assert result.actual_value == "admin"

    def test_runtime_capture_shadows_same_named_column(self):
        executor = StepExecutor(MagicMock())
        result = executor.execute(self._step(expected="captured"), {"role": "admin"}, {"role": "captured"})
        assert result.success is True
        assert result.actual_value == "captured"

    def test_missing_in_both_is_variable_not_found(self):
        executor = StepExecutor(MagicMock())
        result = executor.execute(self._step(var="ghost"), {"role": "admin"}, {"other": "x"})
        assert result.success is False
        assert result.actual_value == "VARIABLE_NOT_FOUND"

    def test_legacy_two_arg_call_still_works(self):
        executor = StepExecutor(MagicMock())
        result = executor._execute_assertion(self._step(expected="rt"), {"role": "rt"})
        assert result.success is True


# ---------------------------------------------------------------------------
# Navigation inside a repeat never touches the trajectory cache
# ---------------------------------------------------------------------------

class TestNavigationCacheOffInsideRepeat:
    def _manager(self):
        mgr = MagicMock()
        mgr.is_recording_enabled = True
        return mgr

    def test_no_replay_and_no_save_when_row_index_present(self):
        nova = MagicMock()
        traj = self._manager()
        executor = StepExecutor(nova, trajectory_manager=traj, enable_cache=True)
        step = {
            "step_type": "navigation", "instruction": "click", "step_id": "s1",
            "trajectory_s3_key": "some/key", "repeat_row_index": 1, "repeat_row_total": 2,
        }
        result = executor.execute(step, {}, {})
        assert result.success is True
        nova.act.assert_called_once_with("click")
        traj.replay_step.assert_not_called()
        traj.save_trajectory.assert_not_called()

    def test_no_cleanup_queued_on_failure_inside_repeat(self):
        nova = MagicMock()
        nova.act.side_effect = RuntimeError("boom")
        traj = self._manager()
        executor = StepExecutor(nova, trajectory_manager=traj, enable_cache=True)
        step = {
            "step_type": "navigation", "instruction": "click", "step_id": "s1",
            "trajectory_s3_key": "some/key", "repeat_row_index": 1,
        }
        result = executor.execute(step, {}, {})
        assert result.success is False
        traj.record_clear.assert_not_called()

    def test_plain_step_still_replays(self):
        nova = MagicMock()
        traj = self._manager()
        traj.replay_step.return_value = MagicMock(duration_ms=1)
        executor = StepExecutor(nova, trajectory_manager=traj, enable_cache=True)
        step = {"step_type": "navigation", "instruction": "click", "step_id": "s1", "trajectory_s3_key": "k"}
        result = executor.execute(step, {}, {})
        assert result.act_id == "trajectory_replay"


# ---------------------------------------------------------------------------
# Engine helpers shared by both loops
# ---------------------------------------------------------------------------

class TestEngineRowHelpers:
    def test_merge_row_variables(self):
        from qa_studio_cli.runner.engine import _merge_row_variables

        step = {"row_variables": {"email": "row", "role": "admin"}}
        merged = _merge_row_variables(step, {"email": "user", "base": "x"})
        assert merged == {"email": "row", "base": "x", "role": "admin"}

    def test_merge_without_row_variables_returns_same_dict(self):
        from qa_studio_cli.runner.engine import _merge_row_variables

        variables = {"a": "1"}
        assert _merge_row_variables({}, variables) is variables

    def test_merge_ignores_non_dict_row_variables(self):
        from qa_studio_cli.runner.engine import _merge_row_variables

        variables = {"a": "1"}
        assert _merge_row_variables({"row_variables": "junk"}, variables) is variables


class TestLocalLoopMergesRowVariables:
    """The local loop hands ``{**variables, **row_variables}`` to the executor."""

    def test_executor_receives_merged_variables(self):
        from qa_studio_cli.runner.browser import BrowserHandle
        from qa_studio_cli.runner.engine import ExecutionEngine
        from qa_studio_cli.models.execution import StepResult

        calls = []

        class _FakeExecutor:
            def __init__(self, *_a, **_kw):
                pass

            def execute(self, step, variables, runtime_variables):
                calls.append((step["instruction"], dict(variables)))
                return StepResult(success=True)

        class _FakeNovaAct:
            def __init__(self, **_kwargs):
                self.page = MagicMock()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class _FakeWorkflow:
            def __init__(self, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        steps = [
            {"step_id": "c1", "sort": 1, "step_type": "navigation", "instruction": "Type {{email}}",
             "repeat_row_index": 1, "repeat_row_total": 2,
             "row_variables": {"email": "a@x.test", "RepeatIndex": "1", "RepeatTotal": "2"}},
            {"step_id": "c1", "sort": 2, "step_type": "navigation", "instruction": "Type {{email}}",
             "repeat_row_index": 2, "repeat_row_total": 2,
             "row_variables": {"email": "b@x.test", "RepeatIndex": "2", "RepeatTotal": "2"}},
            {"step_id": "p1", "sort": 3, "step_type": "navigation", "instruction": "Type {{email}}"},
        ]
        with (
            patch("qa_studio_cli.runner.engine.NovaAct", _FakeNovaAct),
            patch("qa_studio_cli.runner.engine.Workflow", _FakeWorkflow),
            patch("qa_studio_cli.runner.engine.StepExecutor", _FakeExecutor),
            patch("qa_studio_cli.runner.engine.WorkflowManager") as wf,
            patch("qa_studio_cli.runner.engine.LocalBrowserProvisioner") as prov,
        ):
            wf.return_value.ensure_workflow.return_value = "wf-1"
            prov.return_value.provision.return_value = BrowserHandle(nova_kwargs={"starting_page": "https://e.test/"})
            result = ExecutionEngine().execute_usecase_local(
                usecase_id="u-1", usecase_name="n", starting_url="https://e.test/",
                steps=steps, variables={"email": "user@x.test", "base": "1"},
                secrets=[], region="us-east-1", model_id="m",
            )

        assert result["status"] == "success"
        assert [c[0] for c in calls] == ["Type a@x.test", "Type b@x.test", "Type user@x.test"]
        assert calls[0][1] == {"email": "a@x.test", "base": "1", "RepeatIndex": "1", "RepeatTotal": "2"}
        assert calls[2][1] == {"email": "user@x.test", "base": "1"}
        # Row metadata is reported on the step results.
        rows = [(s.get("repeat_row_index"), s.get("repeat_row_total")) for s in result["steps"]]
        assert rows == [(1, 2), (2, 2), (None, None)]
