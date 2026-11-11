"""Tests for the apps command group."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from qa_studio_cli.cli import cli
from qa_studio_cli.models.errors import ApiError


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    return MagicMock()


def invoke_apps(runner, mock_client, args):
    """Helper to invoke apps subcommands with auth mocked out."""
    with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
         patch("qa_studio_cli.api.client.load_config") as mock_config, \
         patch("qa_studio_cli.api.client.get_valid_token", return_value="fake-token"), \
         patch("qa_studio_cli.api.client.ApiClient", return_value=mock_client):
        mock_config.return_value = MagicMock(api_url="https://fake-api.example.com")
        return runner.invoke(cli, args)


class TestAppsReassign:
    """Tests for 'qa-studio apps reassign'."""

    def test_apps_reassign_success(self, runner, mock_client):
        """Reassigning an application returns success message."""
        mock_client.post.return_value = {}

        result = invoke_apps(runner, mock_client, [
            "apps", "reassign", "--app", "app-xyz", "--to-team", "team-2", "--yes"
        ])

        assert result.exit_code == 0
        assert "app-xyz reassigned to team team-2" in result.output
        mock_client.post.assert_called_once_with(
            "/applications/app-xyz/reassign", json_body={"target_team_id": "team-2"}
        )

    def test_apps_reassign_403_non_admin(self, runner, mock_client):
        """Reassigning without admin permission shows 403 error."""
        mock_client.post.side_effect = ApiError(403, "Insufficient permissions. Only admins can reassign applications.")

        result = invoke_apps(runner, mock_client, [
            "apps", "reassign", "--app", "app-xyz", "--to-team", "team-2", "--yes"
        ])

        assert result.exit_code == 1
        assert "403" in result.output or "permission" in result.output.lower()

    def test_apps_reassign_not_found(self, runner, mock_client):
        """Reassigning a nonexistent application shows 404 error."""
        mock_client.post.side_effect = ApiError(404, "Resource not found.")

        result = invoke_apps(runner, mock_client, [
            "apps", "reassign", "--app", "nonexistent", "--to-team", "team-2", "--yes"
        ])

        assert result.exit_code == 1
        assert "404" in result.output or "not found" in result.output.lower()


APP = "app-1"
VARS_PATH = f"/applications/{APP}/variables"
SECRETS_PATH = f"/applications/{APP}/secrets"


def invoke(runner, mock_client, args, input_text=None):
    """``invoke_apps`` with stdin for prompts."""
    with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
         patch("qa_studio_cli.api.client.load_config") as mock_config, \
         patch("qa_studio_cli.api.client.get_valid_token", return_value="fake-token"), \
         patch("qa_studio_cli.api.client.ApiClient", return_value=mock_client):
        mock_config.return_value = MagicMock(api_url="https://fake-api.example.com")
        return runner.invoke(cli, args, input=input_text)


class TestAppsVariablesList:
    def test_table(self, runner, mock_client):
        mock_client.get.return_value = {"variables": [
            {"key": "base_api", "value": "https://api.example.com"},
            {"key": "tenant", "value": "acme"},
        ]}
        result = invoke(runner, mock_client, ["apps", "variables", "list", APP])
        assert result.exit_code == 0
        assert result.output == (
            "Key       Value\n"
            "───────────────\n"
            "base_api  https://api.example.com\n"
            "tenant    acme\n"
        )
        mock_client.get.assert_called_once_with(VARS_PATH)

    def test_empty(self, runner, mock_client):
        mock_client.get.return_value = {"variables": []}
        result = invoke(runner, mock_client, ["apps", "variables", "list", APP])
        assert result.exit_code == 0
        assert result.output == "No variables set on this application.\n"

    def test_json(self, runner, mock_client):
        mock_client.get.return_value = {"variables": [{"key": "a", "value": "1"}]}
        result = invoke(runner, mock_client, ["apps", "variables", "list", APP, "--output", "json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == [{"key": "a", "value": "1"}]

    def test_json_empty_is_empty_list(self, runner, mock_client):
        mock_client.get.return_value = {"variables": []}
        result = invoke(runner, mock_client, ["apps", "variables", "list", APP, "--output", "json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_403_names_the_read_scope(self, runner, mock_client):
        mock_client.get.side_effect = ApiError(403, "Insufficient permissions.")
        result = invoke(runner, mock_client, ["apps", "variables", "list", APP])
        assert result.exit_code == 1
        assert "[403] Insufficient permissions." in result.output
        assert "api/applications.read" in result.output


class TestAppsVariablesSet:
    def test_merges_into_existing_list_and_posts_whole_list(self, runner, mock_client):
        mock_client.get.return_value = {"variables": [
            {"key": "base_api", "value": "old"}, {"key": "tenant", "value": "acme"},
        ]}
        mock_client.post.return_value = {"variables": []}
        result = invoke(runner, mock_client, [
            "apps", "variables", "set", APP, "base_api=https://new.example.com", "region=eu",
        ])
        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once_with(VARS_PATH, json_body={"variables": [
            {"key": "base_api", "value": "https://new.example.com"},
            {"key": "tenant", "value": "acme"},
            {"key": "region", "value": "eu"},
        ]})
        assert result.output == f"✓ Set 2 variable(s) on application {APP} (3 total).\n"

    def test_value_may_contain_equals_and_be_empty(self, runner, mock_client):
        mock_client.get.return_value = {"variables": []}
        mock_client.post.return_value = {"variables": []}
        result = invoke(runner, mock_client, ["apps", "variables", "set", APP, "q=a=b", "empty="])
        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once_with(VARS_PATH, json_body={"variables": [
            {"key": "q", "value": "a=b"}, {"key": "empty", "value": ""},
        ]})

    @pytest.mark.parametrize("arg,fragment", [
        ("no_equals", "KEY=VALUE"),
        ("=value", "empty key"),
        ("1bad=x", "not a valid variable key"),
        ("a-b=x", "not a valid variable key"),
    ])
    def test_malformed_assignment_is_a_usage_error(self, runner, mock_client, arg, fragment):
        result = invoke(runner, mock_client, ["apps", "variables", "set", APP, arg])
        assert result.exit_code == 2
        assert fragment in result.output
        mock_client.get.assert_not_called()
        mock_client.post.assert_not_called()

    def test_duplicate_key_is_a_usage_error(self, runner, mock_client):
        result = invoke(runner, mock_client, ["apps", "variables", "set", APP, "a=1", "a=2"])
        assert result.exit_code == 2
        assert "more than once" in result.output
        mock_client.post.assert_not_called()

    def test_requires_at_least_one_assignment(self, runner, mock_client):
        result = invoke(runner, mock_client, ["apps", "variables", "set", APP])
        assert result.exit_code == 2
        mock_client.post.assert_not_called()

    def test_help_says_read_modify_write(self, runner, mock_client):
        result = invoke(runner, mock_client, ["apps", "variables", "set", "--help"])
        assert result.exit_code == 0
        assert "whole list" in result.output

    def test_403_names_the_write_scope(self, runner, mock_client):
        mock_client.get.return_value = {"variables": []}
        mock_client.post.side_effect = ApiError(403, "Insufficient permissions.")
        result = invoke(runner, mock_client, ["apps", "variables", "set", APP, "a=1"])
        assert result.exit_code == 1
        assert "api/applications.write" in result.output

    def test_400_from_server_exits_1(self, runner, mock_client):
        mock_client.get.return_value = {"variables": []}
        mock_client.post.side_effect = ApiError(400, "variables: List should have at most 100 items")
        result = invoke(runner, mock_client, ["apps", "variables", "set", APP, "a=1"])
        assert result.exit_code == 1
        assert "[400]" in result.output


class TestAppsVariablesUnset:
    def test_removes_keys_and_posts_remaining_list(self, runner, mock_client):
        mock_client.get.return_value = {"variables": [
            {"key": "a", "value": "1"}, {"key": "b", "value": "2"}, {"key": "c", "value": "3"},
        ]}
        mock_client.post.return_value = {"variables": []}
        result = invoke(runner, mock_client, ["apps", "variables", "unset", APP, "a", "c"])
        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once_with(VARS_PATH, json_body={"variables": [{"key": "b", "value": "2"}]})
        assert result.output == f"✓ Removed 2 variable(s) from application {APP} (1 remaining).\n"

    def test_unknown_key_fails_without_writing(self, runner, mock_client):
        mock_client.get.return_value = {"variables": [{"key": "a", "value": "1"}]}
        result = invoke(runner, mock_client, ["apps", "variables", "unset", APP, "a", "zzz"])
        assert result.exit_code == 1
        assert "zzz" in result.output
        mock_client.post.assert_not_called()


class TestAppsSecretsList:
    def test_table_shows_keys_never_values(self, runner, mock_client):
        mock_client.get.return_value = {"secrets": [
            {"key": "admin_password", "secret_name": "qa/application/app-1/admin_password",
             "description": "Secret for application app-1", "created_at": "2026-01-02T03:04:05Z"},
        ]}
        result = invoke(runner, mock_client, ["apps", "secrets", "list", APP])
        assert result.exit_code == 0
        assert result.output == (
            "Key             Created At\n"
            "──────────────────────────\n"
            "admin_password  2026-01-02T03:04:05Z\n"
        )
        mock_client.get.assert_called_once_with(SECRETS_PATH)

    def test_empty(self, runner, mock_client):
        mock_client.get.return_value = {"secrets": []}
        result = invoke(runner, mock_client, ["apps", "secrets", "list", APP])
        assert result.exit_code == 0
        assert result.output == "No secrets set on this application.\n"

    def test_json(self, runner, mock_client):
        rows = [{"key": "k", "secret_name": "n", "description": "d", "created_at": "t"}]
        mock_client.get.return_value = {"secrets": rows}
        result = invoke(runner, mock_client, ["apps", "secrets", "list", APP, "--output", "json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == rows

    def test_403_names_the_read_scope(self, runner, mock_client):
        mock_client.get.side_effect = ApiError(403, "Insufficient permissions.")
        result = invoke(runner, mock_client, ["apps", "secrets", "list", APP])
        assert result.exit_code == 1
        assert "api/applications.read" in result.output


class TestAppsSecretsSet:
    def test_prompts_hidden_and_posts_value(self, runner, mock_client):
        mock_client.post.return_value = {"created": ["admin_password"], "updated": []}
        result = invoke(runner, mock_client, ["apps", "secrets", "set", APP, "admin_password"],
                        input_text="hunter2\n")
        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once_with(
            SECRETS_PATH, json_body={"secrets": [{"key": "admin_password", "value": "hunter2"}]}
        )
        assert "hunter2" not in result.output
        assert f"✓ Secret admin_password created on application {APP}." in result.output

    def test_updated_message(self, runner, mock_client):
        mock_client.post.return_value = {"created": [], "updated": ["admin_password"]}
        result = invoke(runner, mock_client, ["apps", "secrets", "set", APP, "admin_password"],
                        input_text="hunter2\n")
        assert result.exit_code == 0, result.output
        assert f"✓ Secret admin_password updated on application {APP}." in result.output

    def test_value_file_strips_one_trailing_newline_and_never_echoes(self, runner, mock_client, tmp_path):
        value_file = tmp_path / "pw.txt"
        value_file.write_text("s3cr3t-value\n", encoding="utf-8")
        mock_client.post.return_value = {"created": ["pw"], "updated": []}
        result = invoke(runner, mock_client, ["apps", "secrets", "set", APP, "pw", "--value-file", str(value_file)])
        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once_with(
            SECRETS_PATH, json_body={"secrets": [{"key": "pw", "value": "s3cr3t-value"}]}
        )
        assert "s3cr3t-value" not in result.output

    def test_empty_prompt_value_is_a_usage_error(self, runner, mock_client):
        result = invoke(runner, mock_client, ["apps", "secrets", "set", APP, "pw"], input_text="\n")
        assert result.exit_code == 2
        assert "must not be empty" in result.output
        mock_client.post.assert_not_called()

    def test_empty_value_file_is_a_usage_error(self, runner, mock_client, tmp_path):
        value_file = tmp_path / "pw.txt"
        value_file.write_text("\n", encoding="utf-8")
        result = invoke(runner, mock_client, ["apps", "secrets", "set", APP, "pw", "--value-file", str(value_file)])
        assert result.exit_code == 2
        assert "must not be empty" in result.output
        mock_client.post.assert_not_called()

    def test_missing_value_file_is_a_usage_error(self, runner, mock_client, tmp_path):
        result = invoke(runner, mock_client, [
            "apps", "secrets", "set", APP, "pw", "--value-file", str(tmp_path / "nope.txt"),
        ])
        assert result.exit_code == 2
        mock_client.post.assert_not_called()

    def test_invalid_key_is_a_usage_error(self, runner, mock_client):
        result = invoke(runner, mock_client, ["apps", "secrets", "set", APP, "bad key"], input_text="x\n")
        assert result.exit_code == 2
        assert "not a valid secret key" in result.output
        mock_client.post.assert_not_called()

    def test_403_names_the_write_scope_and_hides_value(self, runner, mock_client):
        mock_client.post.side_effect = ApiError(403, "Insufficient permissions.")
        result = invoke(runner, mock_client, ["apps", "secrets", "set", APP, "pw"], input_text="hunter2\n")
        assert result.exit_code == 1
        assert "api/applications.write" in result.output
        assert "hunter2" not in result.output


class TestAppsSecretsDelete:
    def test_delete_with_yes(self, runner, mock_client):
        result = invoke(runner, mock_client, ["apps", "secrets", "delete", APP, "pw", "--yes"])
        assert result.exit_code == 0, result.output
        mock_client._request.assert_called_once_with("DELETE", SECRETS_PATH, json={"secret_key": "pw"})
        assert result.output == f"✓ Secret pw deleted from application {APP}.\n"

    def test_declined_confirmation_aborts(self, runner, mock_client):
        result = invoke(runner, mock_client, ["apps", "secrets", "delete", APP, "pw"], input_text="n\n")
        assert result.exit_code == 0
        assert result.output == f"Delete secret pw from application {APP}? [y/N]: n\nAborted.\n"
        mock_client._request.assert_not_called()

    def test_404(self, runner, mock_client):
        mock_client._request.side_effect = ApiError(404, "Resource not found.")
        result = invoke(runner, mock_client, ["apps", "secrets", "delete", APP, "pw", "-y"])
        assert result.exit_code == 1
        assert "[404]" in result.output

    def test_403_names_the_write_scope(self, runner, mock_client):
        mock_client._request.side_effect = ApiError(403, "Insufficient permissions.")
        result = invoke(runner, mock_client, ["apps", "secrets", "delete", APP, "pw", "-y"])
        assert result.exit_code == 1
        assert "api/applications.write" in result.output


DATASETS_PATH = f"/applications/{APP}/datasets"
DS = "ds-1"
DATASET = {
    "dataset_id": DS, "name": "customers", "description": "Staging customers",
    "columns": ["email", "role"], "rows": [["a@x.test", "admin"], ["b@x.test", "viewer"]],
    "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z", "created_by": "qa",
}


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


class TestAppsDatasetsList:
    def test_table(self, runner, mock_client):
        mock_client.get.return_value = {"datasets": [
            {"dataset_id": DS, "name": "customers", "description": "", "column_count": 2, "row_count": 5,
             "updated_at": "2026-01-02T00:00:00Z"},
            {"dataset_id": "dataset-0002", "name": "B", "description": "", "column_count": 1, "row_count": 100,
             "updated_at": "2026-01-03T00:00:00Z"},
        ]}
        result = invoke(runner, mock_client, ["apps", "datasets", "list", APP])
        assert result.exit_code == 0, result.output
        assert result.output == (
            "ID            Name       Columns  Rows  Updated At\n"
            "──────────────────────────────────────────────────\n"
            "ds-1          customers        2     5  2026-01-02T00:00:00Z\n"
            "dataset-0002  B                1   100  2026-01-03T00:00:00Z\n"
        )
        mock_client.get.assert_called_once_with(DATASETS_PATH)

    def test_empty(self, runner, mock_client):
        mock_client.get.return_value = {"datasets": []}
        result = invoke(runner, mock_client, ["apps", "datasets", "list", APP])
        assert result.exit_code == 0
        assert result.output == "No datasets in this application.\n"

    def test_json(self, runner, mock_client):
        rows = [{"dataset_id": DS, "name": "customers", "column_count": 2, "row_count": 5}]
        mock_client.get.return_value = {"datasets": rows}
        result = invoke(runner, mock_client, ["apps", "datasets", "list", APP, "--output", "json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == rows

    def test_403_names_the_read_scope(self, runner, mock_client):
        mock_client.get.side_effect = ApiError(403, "Insufficient permissions.")
        result = invoke(runner, mock_client, ["apps", "datasets", "list", APP])
        assert result.exit_code == 1
        assert "api/applications.read" in result.output


class TestAppsDatasetsGet:
    def test_table(self, runner, mock_client):
        mock_client.get.return_value = {"dataset": DATASET}
        result = invoke(runner, mock_client, ["apps", "datasets", "get", APP, DS])
        assert result.exit_code == 0, result.output
        assert result.output == (
            "ID:          ds-1\n"
            "Name:        customers\n"
            "Description: Staging customers\n"
            "Updated At:  2026-01-02T00:00:00Z\n"
            "\n"
            "email     role\n"
            "──────────────\n"
            "a@x.test  admin\n"
            "b@x.test  viewer\n"
        )
        mock_client.get.assert_called_once_with(f"{DATASETS_PATH}/{DS}")

    def test_json(self, runner, mock_client):
        mock_client.get.return_value = {"dataset": DATASET}
        result = invoke(runner, mock_client, ["apps", "datasets", "get", APP, DS, "--output", "json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == DATASET

    def test_csv_round_trips_into_create(self, runner, mock_client, tmp_path):
        mock_client.get.return_value = {"dataset": {**DATASET, "rows": [["a@x.test", "admin, senior"]]}}
        result = invoke(runner, mock_client, ["apps", "datasets", "get", APP, DS, "--output", "csv"])
        assert result.exit_code == 0
        assert result.output == 'email,role\na@x.test,"admin, senior"\n'
        from qa_studio_cli.runner.dataset_file import read_dataset_csv
        assert read_dataset_csv(_write(tmp_path, "out.csv", result.output)) == {
            "columns": ["email", "role"], "rows": [["a@x.test", "admin, senior"]],
        }

    def test_404(self, runner, mock_client):
        mock_client.get.side_effect = ApiError(404, "Resource not found.")
        result = invoke(runner, mock_client, ["apps", "datasets", "get", APP, DS])
        assert result.exit_code == 1
        assert "[404]" in result.output


class TestAppsDatasetsCreate:
    def test_csv_file_maps_to_body(self, runner, mock_client, tmp_path):
        path = _write(tmp_path, "rows.csv", "email,role\na@x.test,admin\n\nb@x.test,viewer\n")
        mock_client.post.return_value = {"dataset": DATASET}
        result = invoke(runner, mock_client, [
            "apps", "datasets", "create", APP, "customers", "--file", path, "--description", "Staging customers",
        ])
        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once_with(DATASETS_PATH, json_body={
            "name": "customers", "description": "Staging customers",
            "columns": ["email", "role"], "rows": [["a@x.test", "admin"], ["b@x.test", "viewer"]],
        })
        assert result.output == f"✓ Dataset created: customers (ID: {DS}; 2 columns, 2 rows)\n"

    def test_json_file_maps_to_body(self, runner, mock_client, tmp_path):
        path = _write(tmp_path, "rows.json", json.dumps({"columns": ["email"], "rows": [["a@x.test"]]}))
        mock_client.post.return_value = {"dataset": {**DATASET, "columns": ["email"], "rows": [["a@x.test"]]}}
        result = invoke(runner, mock_client, ["apps", "datasets", "create", APP, "customers", "--file", path])
        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once_with(DATASETS_PATH, json_body={
            "name": "customers", "description": "", "columns": ["email"], "rows": [["a@x.test"]],
        })

    def test_json_output(self, runner, mock_client, tmp_path):
        path = _write(tmp_path, "rows.csv", "email\na@x.test\n")
        mock_client.post.return_value = {"dataset": DATASET}
        result = invoke(runner, mock_client, [
            "apps", "datasets", "create", APP, "customers", "--file", path, "--output", "json",
        ])
        assert result.exit_code == 0
        assert json.loads(result.output) == DATASET

    def test_file_is_required(self, runner, mock_client):
        result = invoke(runner, mock_client, ["apps", "datasets", "create", APP, "customers"])
        assert result.exit_code == 2
        assert "--file" in result.output
        mock_client.post.assert_not_called()

    def test_missing_file_is_a_usage_error(self, runner, mock_client, tmp_path):
        result = invoke(runner, mock_client, [
            "apps", "datasets", "create", APP, "customers", "--file", str(tmp_path / "nope.csv"),
        ])
        assert result.exit_code == 2
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize("name,text,fragment", [
        ("rows.csv", "", "header row"),
        ("rows.csv", "email,1bad\na@x.test,x\n", 'repeat column "1bad" is not a valid identifier'),
        ("rows.csv", "email,Time\na@x.test,x\n", 'repeat column "Time" is a reserved name'),
        ("rows.json", "{not json", "invalid JSON"),
        ("rows.json", '{"columns": ["email"]}', "rows"),
        ("rows.json", '{"columns": ["email"], "rows": [["a", "b"]]}', "row 1 has 2 cells but 1 cells are expected"),
        ("rows.json", '{"columns": ["email"], "rows": [[1]]}', "must contain only string cells"),
        ("rows.txt", "email\na\n", ".csv or .json"),
    ])
    def test_invalid_file_fails_before_the_request_with_server_strings(
        self, runner, mock_client, tmp_path, name, text, fragment,
    ):
        path = _write(tmp_path, name, text)
        result = invoke(runner, mock_client, ["apps", "datasets", "create", APP, "customers", "--file", path])
        assert result.exit_code == 2, result.output
        assert fragment in result.output
        mock_client.post.assert_not_called()

    def test_400_lists_server_errors(self, runner, mock_client, tmp_path):
        path = _write(tmp_path, "rows.csv", "email\na@x.test\n")
        errors = ['dataset name "1bad" is invalid (letters, digits, spaces, underscores and hyphens; '
                  'must start with a letter or underscore; at most 64 characters)']
        mock_client.post.side_effect = ApiError(
            400, json.dumps({"error": "; ".join(errors), "errors": errors}),
            response_data={"error": "; ".join(errors), "errors": errors},
        )
        result = invoke(runner, mock_client, ["apps", "datasets", "create", APP, "1bad", "--file", path])
        assert result.exit_code == 1
        assert result.output.startswith('[400] dataset name "1bad" is invalid')
        assert '  - dataset name "1bad" is invalid' in result.output

    def test_409_name_conflict(self, runner, mock_client, tmp_path):
        path = _write(tmp_path, "rows.csv", "email\na@x.test\n")
        body = {"error": 'a dataset named "customers" already exists in this application'}
        mock_client.post.side_effect = ApiError(409, json.dumps(body), response_data=body)
        result = invoke(runner, mock_client, ["apps", "datasets", "create", APP, "customers", "--file", path])
        assert result.exit_code == 1
        assert result.output == '[409] a dataset named "customers" already exists in this application\n'

    def test_403_names_the_write_scope(self, runner, mock_client, tmp_path):
        path = _write(tmp_path, "rows.csv", "email\na@x.test\n")
        mock_client.post.side_effect = ApiError(403, "Insufficient permissions.")
        result = invoke(runner, mock_client, ["apps", "datasets", "create", APP, "customers", "--file", path])
        assert result.exit_code == 1
        assert "api/applications.write" in result.output


class TestAppsDatasetsUpdate:
    def test_rename_only_keeps_rows(self, runner, mock_client):
        mock_client.get.return_value = {"dataset": DATASET}
        mock_client.put.return_value = {"dataset": {**DATASET, "name": "clients"}}
        result = invoke(runner, mock_client, ["apps", "datasets", "update", APP, DS, "--name", "clients"])
        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once_with(f"{DATASETS_PATH}/{DS}")
        mock_client.put.assert_called_once_with(f"{DATASETS_PATH}/{DS}", json_body={
            "name": "clients", "description": "Staging customers",
            "columns": ["email", "role"], "rows": [["a@x.test", "admin"], ["b@x.test", "viewer"]],
        })
        assert result.output == f"✓ Dataset updated: clients (ID: {DS}; 2 columns, 2 rows)\n"

    def test_file_replaces_table_and_description_can_be_cleared(self, runner, mock_client, tmp_path):
        path = _write(tmp_path, "rows.csv", "email\nc@x.test\n")
        mock_client.get.return_value = {"dataset": DATASET}
        mock_client.put.return_value = {"dataset": {**DATASET, "columns": ["email"], "rows": [["c@x.test"]]}}
        result = invoke(runner, mock_client, [
            "apps", "datasets", "update", APP, DS, "--file", path, "--description", "",
        ])
        assert result.exit_code == 0, result.output
        mock_client.put.assert_called_once_with(f"{DATASETS_PATH}/{DS}", json_body={
            "name": "customers", "description": "", "columns": ["email"], "rows": [["c@x.test"]],
        })

    def test_requires_a_change(self, runner, mock_client):
        result = invoke(runner, mock_client, ["apps", "datasets", "update", APP, DS])
        assert result.exit_code == 2
        assert "--name" in result.output and "--file" in result.output
        mock_client.get.assert_not_called()
        mock_client.put.assert_not_called()

    def test_invalid_file_fails_before_any_request(self, runner, mock_client, tmp_path):
        path = _write(tmp_path, "rows.csv", "")
        result = invoke(runner, mock_client, ["apps", "datasets", "update", APP, DS, "--file", path])
        assert result.exit_code == 2
        mock_client.get.assert_not_called()
        mock_client.put.assert_not_called()

    def test_json_output(self, runner, mock_client):
        mock_client.get.return_value = {"dataset": DATASET}
        mock_client.put.return_value = {"dataset": DATASET}
        result = invoke(runner, mock_client, [
            "apps", "datasets", "update", APP, DS, "--name", "customers", "--output", "json",
        ])
        assert result.exit_code == 0
        assert json.loads(result.output) == DATASET

    def test_404_on_read(self, runner, mock_client):
        mock_client.get.side_effect = ApiError(404, "Resource not found.")
        result = invoke(runner, mock_client, ["apps", "datasets", "update", APP, DS, "--name", "x"])
        assert result.exit_code == 1
        assert "[404]" in result.output
        mock_client.put.assert_not_called()


class TestAppsDatasetsDelete:
    def test_delete_with_yes(self, runner, mock_client):
        mock_client.delete.return_value = None
        result = invoke(runner, mock_client, ["apps", "datasets", "delete", APP, DS, "--yes"])
        assert result.exit_code == 0, result.output
        mock_client.delete.assert_called_once_with(f"{DATASETS_PATH}/{DS}")
        assert result.output == f"✓ Dataset {DS} deleted from application {APP}.\n"

    def test_declined_confirmation_aborts(self, runner, mock_client):
        result = invoke(runner, mock_client, ["apps", "datasets", "delete", APP, DS], input_text="n\n")
        assert result.exit_code == 0
        assert result.output == f"Delete dataset {DS} from application {APP}? [y/N]: n\nAborted.\n"
        mock_client.delete.assert_not_called()

    def test_409_lists_referencing_usecases(self, runner, mock_client):
        body = {
            "error": "dataset is referenced by repeat steps of this application; remove the references first",
            "usecases": [{"usecase_id": "uc-1", "name": "Checkout"}, {"usecase_id": "uc-2", "name": "Login"}],
        }
        mock_client.delete.side_effect = ApiError(409, json.dumps(body), response_data=body)
        result = invoke(runner, mock_client, ["apps", "datasets", "delete", APP, DS, "-y"])
        assert result.exit_code == 1
        assert result.output == (
            "[409] dataset is referenced by repeat steps of this application; remove the references first\n"
            "Referenced by:\n"
            "  - Checkout (uc-1)\n"
            "  - Login (uc-2)\n"
        )

    def test_403_names_the_write_scope(self, runner, mock_client):
        mock_client.delete.side_effect = ApiError(403, "Insufficient permissions.")
        result = invoke(runner, mock_client, ["apps", "datasets", "delete", APP, DS, "-y"])
        assert result.exit_code == 1
        assert "api/applications.write" in result.output
