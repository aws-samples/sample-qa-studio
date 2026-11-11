"""Parity: the CLI ``repeat_expansion`` mirror behaves exactly like the Lambda module.

Both are driven by ``web-app/lambdas/endpoints/fixtures/repeat_expansion_cases.json``.
Skipped when the monorepo fixture is not present (standalone CLI install).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from qa_studio_cli.runner.repeat_expansion import RepeatExpansionError, expand_repeat_steps


def _find_fixture() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "web-app" / "lambdas" / "endpoints" / "fixtures" / "repeat_expansion_cases.json"
        if candidate.exists():
            return candidate
    return None


_FIXTURE = _find_fixture()
_CASES = json.loads(_FIXTURE.read_text())["cases"] if _FIXTURE else []


@pytest.mark.skipif(_FIXTURE is None, reason="Lambda fixture not present (standalone CLI install)")
@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_fixture_case(case):
    overrides = case.get("overrides")
    if "error" in case:
        with pytest.raises(RepeatExpansionError) as excinfo:
            expand_repeat_steps(case["steps"], overrides)
        assert case["error"] in str(excinfo.value), str(excinfo.value)
    else:
        assert expand_repeat_steps(case["steps"], overrides) == case["expected"]


def test_module_docstring_names_the_lambda_source():
    import qa_studio_cli.runner.repeat_expansion as mod

    assert "web-app/lambdas/endpoints/repeat_expansion.py" in (mod.__doc__ or "")


class TestLocalOnlyPathExpandsBeforeEngine:
    """``_execute_usecase_local`` unrolls repeats and fails fast (exit 2) on errors."""

    def _usecase_api(self, steps):
        api = MagicMock()
        api.get_usecase.return_value = {"name": "UC", "starting_url": "https://e.test/"}
        api.get_steps.return_value = steps
        api.get_variables.return_value = {}
        api.get_secrets.return_value = []
        return api

    def test_engine_receives_expanded_steps(self, capsys):
        from qa_studio_cli.runner import main as runner_main

        steps = [
            {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "Users",
             "repeat_columns": ["email"], "repeat_rows": [["a"], ["b"]]},
            {"id": "c1", "sort": 2, "step_type": "navigation", "instruction": "{{email}}", "parent_step_id": "r1"},
        ]
        with patch.object(runner_main, "ExecutionEngine") as engine_cls:
            engine_cls.return_value.execute_usecase_local.return_value = {"status": "success", "steps": []}
            result = runner_main._execute_usecase_local(
                usecase_id="u-1", usecase={"name": "UC", "starting_url": "https://e.test/"},
                usecase_api=self._usecase_api(steps),
                base_url=None, variables={}, region=None, model_id=None,
            )
        assert result["status"] == "success"
        passed = engine_cls.return_value.execute_usecase_local.call_args.kwargs["steps"]
        assert [s["row_variables"]["email"] for s in passed] == ["a", "b"]
        assert [s["sort"] for s in passed] == [1, 2]

    def test_invalid_repeat_fails_before_engine(self):
        from qa_studio_cli.runner import main as runner_main

        steps = [
            {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "Lonely",
             "repeat_columns": ["email"], "repeat_rows": [["a"]]},
        ]
        with patch.object(runner_main, "ExecutionEngine") as engine_cls:
            with pytest.raises(RepeatExpansionError, match="Lonely"):
                runner_main._execute_usecase_local(
                    usecase_id="u-1", usecase={"name": "UC", "starting_url": "https://e.test/"},
                    usecase_api=self._usecase_api(steps),
                    base_url=None, variables={}, region=None, model_id=None,
                )
        engine_cls.assert_not_called()

    def test_run_usecase_exits_2_on_expansion_error(self):
        from qa_studio_cli.runner import main as runner_main

        steps = [
            {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "Lonely",
             "repeat_columns": ["email"], "repeat_rows": [["a"]]},
        ]
        with (
            patch.object(runner_main, "_validate_aws_session"),
            patch.object(runner_main, "_build_api_client"),
            patch.object(runner_main, "UseCaseAPI", return_value=self._usecase_api(steps)),
            patch.object(runner_main, "ExecutionEngine") as engine_cls,
        ):
            with pytest.raises(SystemExit) as exc:
                runner_main.run_usecase(usecase_ids=["u-1"], local_only=True)
        assert exc.value.code == 2
        engine_cls.assert_not_called()

    def test_dataset_override_is_applied_locally(self):
        from qa_studio_cli.runner import main as runner_main

        steps = [
            {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "Users",
             "repeat_columns": ["email"], "repeat_rows": [["stored"]]},
            {"id": "c1", "sort": 2, "step_type": "navigation", "instruction": "{{email}}", "parent_step_id": "r1"},
        ]
        with patch.object(runner_main, "ExecutionEngine") as engine_cls:
            engine_cls.return_value.execute_usecase_local.return_value = {"status": "success", "steps": []}
            runner_main._execute_usecase_local(
                usecase_id="u-1", usecase={"name": "UC", "starting_url": "https://e.test/"},
                usecase_api=self._usecase_api(steps),
                base_url=None, variables={}, region=None, model_id=None,
                repeat_dataset_files=[(None, {"columns": ["email"], "rows": [["o1"], ["o2"], ["o3"]]})],
            )
        passed = engine_cls.return_value.execute_usecase_local.call_args.kwargs["steps"]
        assert [s["row_variables"]["email"] for s in passed] == ["o1", "o2", "o3"]
