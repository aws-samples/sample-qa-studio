"""``--dataset-file [LABEL=]PATH`` parsing, CSV reading and label resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from qa_studio_cli.cli import cli
from qa_studio_cli.models.errors import ApiError
from qa_studio_cli.runner.dataset_file import (
    DatasetFileError,
    parse_dataset_file_option,
    read_dataset_csv,
    resolve_repeat_datasets,
)


def _write(tmp_path: Path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


class TestParseOption:
    def test_path_only(self):
        assert parse_dataset_file_option("users.csv") == (None, "users.csv")

    def test_label_and_path(self):
        assert parse_dataset_file_option("Login as each user=users.csv") == ("Login as each user", "users.csv")

    def test_label_may_contain_equals(self):
        assert parse_dataset_file_option("a=b=c.csv") == ("a=b", "c.csv")

    def test_empty_label_rejected(self):
        with pytest.raises(DatasetFileError):
            parse_dataset_file_option("=users.csv")

    def test_empty_path_rejected(self):
        with pytest.raises(DatasetFileError):
            parse_dataset_file_option("label=")


class TestReadCsv:
    def test_happy_path_strings_and_blank_lines(self, tmp_path):
        path = _write(tmp_path, "u.csv", "email,role\na@x.test,admin\n\nb@x.test,7\n")
        assert read_dataset_csv(path) == {
            "columns": ["email", "role"],
            "rows": [["a@x.test", "admin"], ["b@x.test", "7"]],
        }

    def test_file_not_found(self, tmp_path):
        with pytest.raises(DatasetFileError, match="not found"):
            read_dataset_csv(str(tmp_path / "missing.csv"))

    def test_empty_file(self, tmp_path):
        path = _write(tmp_path, "e.csv", "")
        with pytest.raises(DatasetFileError, match="header"):
            read_dataset_csv(path)

    def test_header_only_has_no_rows(self, tmp_path):
        path = _write(tmp_path, "h.csv", "email,role\n")
        with pytest.raises(DatasetFileError, match="at least 1 row"):
            read_dataset_csv(path)

    def test_missing_cell_is_empty_string(self, tmp_path):
        path = _write(tmp_path, "m.csv", "email,role\na@x.test\n")
        assert read_dataset_csv(path)["rows"] == [["a@x.test", ""]]

    def test_extra_cells_rejected(self, tmp_path):
        path = _write(tmp_path, "x.csv", "email\na,b\n")
        with pytest.raises(DatasetFileError, match="more cells"):
            read_dataset_csv(path)

    def test_invalid_header_name(self, tmp_path):
        path = _write(tmp_path, "bad.csv", "e mail\nx\n")
        with pytest.raises(DatasetFileError, match="identifier"):
            read_dataset_csv(path)

    def test_row_cap(self, tmp_path):
        path = _write(tmp_path, "big.csv", "a\n" + "x\n" * 101)
        with pytest.raises(DatasetFileError, match="at most 100 rows"):
            read_dataset_csv(path)

    def test_column_cap(self, tmp_path):
        cols = ",".join(f"c{i}" for i in range(21))
        path = _write(tmp_path, "wide.csv", cols + "\n" + ",".join(["x"] * 21) + "\n")
        with pytest.raises(DatasetFileError, match="at most 20 columns"):
            read_dataset_csv(path)

    def test_utf8_content(self, tmp_path):
        path = _write(tmp_path, "utf.csv", "name\nJürgen\n")
        assert read_dataset_csv(path)["rows"] == [["Jürgen"]]


REPEAT = {"id": "r1", "step_type": "repeat", "instruction": "Users", "repeat_columns": ["email", "role"]}
OTHER = {"id": "r2", "step_type": "repeat", "instruction": "Other", "repeat_columns": ["n"]}
PLAIN = {"id": "p", "step_type": "navigation", "instruction": "x"}
DATASET = {"columns": ["role", "email"], "rows": [["admin", "a"]]}


class TestResolveLabels:
    def test_explicit_label(self):
        out = resolve_repeat_datasets([("Users", DATASET)], [REPEAT, OTHER, PLAIN])
        assert out == {"Users": DATASET}

    def test_single_repeat_label_inferred(self):
        out = resolve_repeat_datasets([(None, DATASET)], [REPEAT, PLAIN])
        assert out == {"Users": DATASET}

    def test_no_label_with_multiple_repeats(self):
        with pytest.raises(DatasetFileError, match="LABEL=PATH"):
            resolve_repeat_datasets([(None, DATASET)], [REPEAT, OTHER])

    def test_no_label_with_no_repeat(self):
        with pytest.raises(DatasetFileError, match="no repeat step"):
            resolve_repeat_datasets([(None, DATASET)], [PLAIN])

    def test_unknown_label(self):
        with pytest.raises(DatasetFileError, match='no repeat step with label "Nope"'):
            resolve_repeat_datasets([("Nope", DATASET)], [REPEAT])

    def test_column_mismatch(self):
        bad = {"columns": ["email", "team"], "rows": [["a", "b"]]}
        with pytest.raises(DatasetFileError, match="do not match"):
            resolve_repeat_datasets([("Users", bad)], [REPEAT])

    def test_duplicate_label(self):
        with pytest.raises(DatasetFileError, match="more than once"):
            resolve_repeat_datasets([("Users", DATASET), ("Users", DATASET)], [REPEAT])

    def test_empty_entries(self):
        assert resolve_repeat_datasets([], [REPEAT]) is None


# ---------------------------------------------------------------------------
# run command wiring
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_runner_main():
    mock_main = MagicMock()
    mock_main.run_usecase = MagicMock(side_effect=SystemExit(0))
    mock_main.run_runner = MagicMock(side_effect=SystemExit(0))
    with patch.dict("sys.modules", {"qa_studio_cli.runner.main": mock_main}):
        yield mock_main


class TestRunCommandDatasetFile:
    def test_with_suite_id_is_usage_error(self, runner, tmp_path):
        path = _write(tmp_path, "u.csv", "email\na\n")
        result = runner.invoke(cli, ["run", "--suite-id", "s1", "--dataset-file", path])
        assert result.exit_code == 2
        assert "--dataset-file" in result.output and "--usecase-id" in result.output

    def test_file_not_found_is_usage_error(self, runner, tmp_path):
        result = runner.invoke(cli, ["run", "--usecase-id", "u1", "--dataset-file", str(tmp_path / "nope.csv")])
        assert result.exit_code == 2
        assert "not found" in result.output

    def test_empty_csv_is_usage_error(self, runner, tmp_path):
        path = _write(tmp_path, "e.csv", "")
        result = runner.invoke(cli, ["run", "--usecase-id", "u1", "--dataset-file", path])
        assert result.exit_code == 2
        assert "header" in result.output

    def test_happy_path_passes_entries(self, runner, mock_runner_main, tmp_path):
        path = _write(tmp_path, "u.csv", "email,role\na,admin\n")
        result = runner.invoke(cli, [
            "run", "--usecase-id", "u1", "--dataset-file", f"Login as each user={path}",
        ])
        assert result.exit_code == 0, result.output
        entries = mock_runner_main.run_usecase.call_args.kwargs["repeat_dataset_files"]
        assert entries == [("Login as each user", {"columns": ["email", "role"], "rows": [["a", "admin"]]})]

    def test_without_flag_passes_empty_list(self, runner, mock_runner_main):
        runner.invoke(cli, ["run", "--usecase-id", "u1"])
        assert mock_runner_main.run_usecase.call_args.kwargs["repeat_dataset_files"] == []


class TestRunnerMainDatasetWiring:
    """Remote mode puts ``repeat_datasets`` in the create_execution body; local mode expands."""

    def _usecase_api(self, steps):
        api = MagicMock()
        api.get_usecase.return_value = {"name": "UC", "starting_url": "https://e.test/"}
        api.get_steps.return_value = steps
        api.get_variables.return_value = {}
        api.get_secrets.return_value = []
        api.create_execution.return_value = {"executionId": "exec-1"}
        return api

    _STEPS = [
        {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "Users",
         "repeat_columns": ["email"], "repeat_rows": [["stored"]]},
        {"id": "c1", "sort": 2, "step_type": "navigation", "instruction": "{{email}}", "parent_step_id": "r1"},
    ]

    def test_remote_mode_sends_datasets(self):
        from qa_studio_cli.runner import main as runner_main

        api = self._usecase_api(self._STEPS)
        dataset = {"columns": ["email"], "rows": [["o1"]]}
        with (
            patch.object(runner_main, "ExecutionAPI") as exec_api_cls,
            patch.object(runner_main, "ExecutionEngine") as engine_cls,
            patch.object(runner_main.asyncio, "run", side_effect=lambda coro: {"usecase_name": "UC"}),
            patch.object(runner_main, "ArtifactUploader"),
        ):
            engine_cls.return_value.execute_usecase.return_value = {"status": "success"}
            runner_main._execute_usecase_remote(
                usecase_id="u-1", usecase_api=api, api_client=MagicMock(),
                base_url=None, variables={}, region=None, model_id=None,
                repeat_dataset_files=[(None, dataset)],
            )
        assert api.create_execution.call_args.kwargs["repeat_datasets"] == {"Users": dataset}
        api.get_steps.assert_called_once_with("u-1")

    def test_remote_mode_without_datasets_does_not_fetch_steps(self):
        from qa_studio_cli.runner import main as runner_main

        api = self._usecase_api(self._STEPS)
        with (
            patch.object(runner_main, "ExecutionAPI"),
            patch.object(runner_main, "ExecutionEngine") as engine_cls,
            patch.object(runner_main.asyncio, "run", side_effect=lambda coro: {"usecase_name": "UC"}),
            patch.object(runner_main, "ArtifactUploader"),
        ):
            engine_cls.return_value.execute_usecase.return_value = {"status": "success"}
            runner_main._execute_usecase_remote(
                usecase_id="u-1", usecase_api=api, api_client=MagicMock(),
                base_url=None, variables={}, region=None, model_id=None,
            )
        assert api.create_execution.call_args.kwargs["repeat_datasets"] is None
        api.get_steps.assert_not_called()

    def test_local_mode_resolves_label_and_expands(self):
        from qa_studio_cli.runner import main as runner_main

        api = self._usecase_api(self._STEPS)
        dataset = {"columns": ["email"], "rows": [["o1"], ["o2"]]}
        with patch.object(runner_main, "ExecutionEngine") as engine_cls:
            engine_cls.return_value.execute_usecase_local.return_value = {"status": "success", "steps": []}
            runner_main._execute_usecase_local(
                usecase_id="u-1", usecase={"name": "UC", "starting_url": "https://e.test/"},
                usecase_api=api,
                base_url=None, variables={}, region=None, model_id=None,
                repeat_dataset_files=[(None, dataset)],
            )
        passed = engine_cls.return_value.execute_usecase_local.call_args.kwargs["steps"]
        assert [s["row_variables"]["email"] for s in passed] == ["o1", "o2"]

    def test_unknown_label_exits_2(self):
        from qa_studio_cli.runner import main as runner_main

        api = self._usecase_api(self._STEPS)
        with (
            patch.object(runner_main, "_validate_aws_session"),
            patch.object(runner_main, "_build_api_client"),
            patch.object(runner_main, "UseCaseAPI", return_value=api),
            patch.object(runner_main, "ExecutionEngine") as engine_cls,
        ):
            with pytest.raises(SystemExit) as exc:
                runner_main.run_usecase(
                    usecase_ids=["u-1"], local_only=True,
                    repeat_dataset_files=[("Nope", {"columns": ["email"], "rows": [["x"]]})],
                )
        assert exc.value.code == 2
        engine_cls.assert_not_called()


class TestRunnerMainDatasetRefWiring:
    """Local mode resolves ``dataset_id`` through the application API before expansion.

    Remote mode is untouched (the server resolves at execution creation).
    """

    _USECASE = {"name": "UC", "starting_url": "https://e.test/", "application_id": "app-1"}
    _REF_STEPS = [
        {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "Users", "dataset_id": "ds-1"},
        {"id": "c1", "sort": 2, "step_type": "navigation", "instruction": "{{email}}", "parent_step_id": "r1"},
    ]
    _DATASET = {"dataset_id": "ds-1", "name": "customers", "columns": ["email"], "rows": [["a1"], ["a2"]]}

    def _usecase_api(self, steps, usecase=None):
        api = MagicMock()
        api.get_usecase.return_value = usecase or self._USECASE
        api.get_steps.return_value = steps
        api.get_variables.return_value = {}
        api.get_secrets.return_value = []
        return api

    def _run_local(self, api, engine_cls, **kwargs):
        from qa_studio_cli.runner import main as runner_main

        engine_cls.return_value.execute_usecase_local.return_value = {"status": "success", "steps": []}
        runner_main._execute_usecase_local(
            usecase_id="u-1", usecase=self._USECASE, usecase_api=api,
            base_url=None, variables={}, region=None, model_id=None, **kwargs,
        )
        return engine_cls.return_value.execute_usecase_local.call_args.kwargs["steps"]

    def test_injected_fetcher_resolves_the_reference_before_expansion(self):
        from qa_studio_cli.runner import main as runner_main

        api = self._usecase_api(self._REF_STEPS)
        fetched = []

        def fetch(dataset_id):
            fetched.append(dataset_id)
            return self._DATASET

        with patch.object(runner_main, "ExecutionEngine") as engine_cls:
            passed = self._run_local(api, engine_cls, dataset_fetcher=fetch)
        assert fetched == ["ds-1"]
        assert [s["row_variables"]["email"] for s in passed] == ["a1", "a2"]

    def test_default_fetcher_reads_through_applications_api_bound_to_the_usecase_application(self):
        from qa_studio_cli.runner import main as runner_main

        api = self._usecase_api(self._REF_STEPS)
        with (
            patch.object(runner_main, "ExecutionEngine") as engine_cls,
            patch.object(runner_main, "ApplicationsAPI") as apps_api_cls,
        ):
            apps_api_cls.return_value.get_dataset.return_value = self._DATASET
            passed = self._run_local(api, engine_cls)
        apps_api_cls.assert_called_once_with(api.client)
        apps_api_cls.return_value.get_dataset.assert_called_once_with("app-1", "ds-1")
        assert [s["row_variables"]["email"] for s in passed] == ["a1", "a2"]

    def test_inline_repeat_never_touches_the_applications_api(self):
        from qa_studio_cli.runner import main as runner_main

        steps = [
            {"id": "r1", "sort": 1, "step_type": "repeat", "instruction": "Users",
             "repeat_columns": ["email"], "repeat_rows": [["stored"]]},
            {"id": "c1", "sort": 2, "step_type": "navigation", "instruction": "{{email}}", "parent_step_id": "r1"},
        ]
        api = self._usecase_api(steps)
        with (
            patch.object(runner_main, "ExecutionEngine") as engine_cls,
            patch.object(runner_main, "ApplicationsAPI") as apps_api_cls,
        ):
            passed = self._run_local(api, engine_cls)
        apps_api_cls.return_value.get_dataset.assert_not_called()
        assert [s["row_variables"]["email"] for s in passed] == ["stored"]

    def test_dataset_file_override_wins_over_the_application_dataset(self):
        from qa_studio_cli.runner import main as runner_main

        api = self._usecase_api(self._REF_STEPS)
        override = {"columns": ["email"], "rows": [["o1"], ["o2"], ["o3"]]}
        with patch.object(runner_main, "ExecutionEngine") as engine_cls:
            passed = self._run_local(
                api, engine_cls, dataset_fetcher=lambda _id: self._DATASET,
                repeat_dataset_files=[("Users", override)],
            )
        assert [s["row_variables"]["email"] for s in passed] == ["o1", "o2", "o3"]

    def test_missing_dataset_exits_2_before_any_engine(self, caplog):
        from qa_studio_cli.runner import main as runner_main

        api = self._usecase_api(self._REF_STEPS)
        with (
            patch.object(runner_main, "_validate_aws_session"),
            patch.object(runner_main, "_build_api_client"),
            patch.object(runner_main, "UseCaseAPI", return_value=api),
            patch.object(runner_main, "ApplicationsAPI") as apps_api_cls,
            patch.object(runner_main, "ExecutionEngine") as engine_cls,
        ):
            apps_api_cls.return_value.get_dataset.side_effect = ApiError(404, "Resource not found.")
            with pytest.raises(SystemExit) as exc:
                runner_main.run_usecase(usecase_ids=["u-1"], local_only=True)
        assert exc.value.code == 2
        engine_cls.assert_not_called()
        assert "dataset ds-1 not found in application app-1" in caplog.text

    def test_403_from_datasets_route_exits_2_with_scope_hint(self, caplog):
        from qa_studio_cli.runner import main as runner_main

        api = self._usecase_api(self._REF_STEPS)
        with (
            patch.object(runner_main, "_validate_aws_session"),
            patch.object(runner_main, "_build_api_client"),
            patch.object(runner_main, "UseCaseAPI", return_value=api),
            patch.object(runner_main, "ApplicationsAPI") as apps_api_cls,
            patch.object(runner_main, "ExecutionEngine") as engine_cls,
        ):
            apps_api_cls.return_value.get_dataset.side_effect = ApiError(403, "Insufficient permissions.")
            with pytest.raises(SystemExit) as exc:
                runner_main.run_usecase(usecase_ids=["u-1"], local_only=True)
        assert exc.value.code == 2
        engine_cls.assert_not_called()
        assert "--local-only with application datasets needs the api/applications.read scope" in caplog.text

    def test_remote_mode_does_not_resolve_references(self):
        from qa_studio_cli.runner import main as runner_main

        api = self._usecase_api(self._REF_STEPS)
        api.create_execution.return_value = {"executionId": "exec-1"}
        with (
            patch.object(runner_main, "ExecutionAPI"),
            patch.object(runner_main, "ExecutionEngine") as engine_cls,
            patch.object(runner_main, "ApplicationsAPI") as apps_api_cls,
            patch.object(runner_main.asyncio, "run", side_effect=lambda coro: {"usecase_name": "UC"}),
            patch.object(runner_main, "ArtifactUploader"),
        ):
            engine_cls.return_value.execute_usecase.return_value = {"status": "success"}
            runner_main._execute_usecase_remote(
                usecase_id="u-1", usecase_api=api, api_client=MagicMock(),
                base_url=None, variables={}, region=None, model_id=None,
            )
        apps_api_cls.assert_not_called()
