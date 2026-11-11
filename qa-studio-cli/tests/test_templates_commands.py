"""``qa-studio templates list | get | create``."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from qa_studio_cli.cli import cli
from qa_studio_cli.models.errors import ApiError
from qa_studio_cli.models.import_schema import TemplateFilePayload

LOGIN_ID = "3f1c0000-0000-4000-8000-000000000001"
SETUP_ID = "3f1c0000-0000-4000-8000-000000000002"

TEMPLATES = [
    {"id": LOGIN_ID, "name": "Login – Shop", "category": "auth", "description": "Logs in", "version": 3,
     "tags": ["shop"], "created_by": "qa@example.com", "created_at": "2025-01-01T00:00:00Z"},
    {"id": SETUP_ID, "name": "Cookie banner", "category": "", "version": 1},
]
LOGIN_STEPS = [
    {"id": "s2", "sort": 2, "step_type": "secret", "instruction": "Click into the username field.",
     "secret_key": "shop_username"},
    {"id": "s1", "sort": 1, "step_type": "browser", "instruction": "Open login", "browser_action": "navigate"},
    {"id": "s3", "sort": 3, "step_type": "secret", "instruction": "Click into the password field.",
     "secret_key": "shop_password"},
    {"id": "s4", "sort": 4, "step_type": "secret", "instruction": "Confirm.", "secret_key": "shop_password"},
]
LOGIN_VARIABLES = [{"key": "base", "value": "https://e.test"}]
STEP_COUNTS = {LOGIN_ID: LOGIN_STEPS, SETUP_ID: [{"id": "x", "sort": 1, "step_type": "navigation", "instruction": "Dismiss."}]}


USAGES = [{"usecase_id": "uc-checkout", "name": "Checkout"}, {"usecase_id": "uc-refund", "name": "Refund"}]


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    client = MagicMock()

    def get(path, params=None):
        if path == "/templates":
            return {"templates": TEMPLATES}
        if path == f"/templates/{LOGIN_ID}":
            return TEMPLATES[0]
        if path == f"/templates/{LOGIN_ID}/steps":
            return {"steps": LOGIN_STEPS}
        if path == f"/templates/{LOGIN_ID}/variables":
            return {"variables": LOGIN_VARIABLES}
        if path == f"/templates/{LOGIN_ID}/usages":
            return {"usages": USAGES, "count": len(USAGES)}
        if path == f"/templates/{SETUP_ID}":
            return TEMPLATES[1]
        if path == f"/templates/{SETUP_ID}/steps":
            return {"steps": STEP_COUNTS[SETUP_ID]}
        if path == f"/templates/{SETUP_ID}/variables":
            return {"variables": []}
        if path == f"/templates/{SETUP_ID}/usages":
            return {"usages": [], "count": 0}
        raise ApiError(404, "Resource not found.")

    client.get.side_effect = get
    client.post.return_value = {"id": LOGIN_ID, "name": "Login – Shop", "stepsCreated": 3}
    client.delete.return_value = None
    return client


def _invoke(runner, mock_client, args, input_text=None):
    with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
         patch("qa_studio_cli.api.client.load_config") as mock_config, \
         patch("qa_studio_cli.api.client.get_valid_token", return_value="fake-token"), \
         patch("qa_studio_cli.api.client.ApiClient", return_value=mock_client):
        mock_config.return_value = MagicMock(api_url="https://fake-api.example.com")
        return runner.invoke(cli, ["templates", *args], input=input_text)


def _template_file(tmp_path: Path, **overrides) -> Path:
    data = {
        "templateVersion": "1.0",
        "template": {"name": "Login – Shop", "description": "Logs in", "category": "auth", "tags": ["shop"]},
        "steps": [
            {"sort": 1, "step_type": "browser", "instruction": "Open login", "browser_action": "navigate",
             "browser_args": '{"url": "https://e.test"}'},
            {"sort": 2, "step_type": "secret", "instruction": "Click into the username field.", "secret_key": "shop_username"},
            {"sort": 3, "step_type": "secret", "instruction": "Click into the password field.", "secret_key": "shop_password"},
        ],
        "variables": [{"key": "base", "value": "https://e.test"}],
    }
    data.update(overrides)
    path = tmp_path / "login-shop.json"
    path.write_text(json.dumps(data))
    return path


class TestList:
    def test_human_table(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["list"])
        assert result.exit_code == 0, result.output
        assert "ID" in result.output and "Steps" in result.output and "Category" in result.output
        assert LOGIN_ID in result.output and "Login – Shop" in result.output and "auth" in result.output
        assert SETUP_ID in result.output and "Cookie banner" in result.output
        # step counts come from one /steps call per template
        line = next(l for l in result.output.splitlines() if LOGIN_ID in l)
        assert " 4 " in f" {line} " or "4" in line.split(LOGIN_ID)[1]

    def test_json(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["list", "--format", "json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert [t["id"] for t in data] == [LOGIN_ID, SETUP_ID]
        assert data[0]["name"] == "Login – Shop"
        assert data[0]["version"] == 3
        assert data[0]["stepCount"] == 4
        assert data[1]["stepCount"] == 1

    def test_empty(self, runner, mock_client):
        mock_client.get.side_effect = lambda path, params=None: {"templates": []}
        result = _invoke(runner, mock_client, ["list"])
        assert result.exit_code == 0
        assert "No templates found." in result.output

    def test_api_error(self, runner, mock_client):
        mock_client.get.side_effect = ApiError(403, "Insufficient permissions.")
        result = _invoke(runner, mock_client, ["list"])
        assert result.exit_code == 1
        assert "Insufficient permissions" in result.output


class TestGet:
    def test_human(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["get", LOGIN_ID])
        assert result.exit_code == 0, result.output
        out = result.output
        assert "Login – Shop" in out and "auth" in out and "3" in out
        # steps ordered by sort, type + instruction
        assert out.index("[browser] Open login") < out.index("[secret] Click into the username field.")
        assert "base" in out and "https://e.test" in out
        # distinct secret keys in step order
        assert "shop_username, shop_password" in out

    def test_json(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["get", LOGIN_ID, "--format", "json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["template"]["id"] == LOGIN_ID
        assert [s["sort"] for s in data["steps"]] == [1, 2, 3, 4]
        assert data["variables"] == LOGIN_VARIABLES
        assert data["secretKeys"] == ["shop_username", "shop_password"]
        assert data["usages"] == USAGES

    def test_human_lists_usages(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["get", LOGIN_ID])
        assert result.exit_code == 0, result.output
        assert "Used by (2):" in result.output
        assert "  Checkout (uc-checkout)" in result.output
        assert "  Refund (uc-refund)" in result.output

    def test_human_without_usages(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["get", SETUP_ID])
        assert result.exit_code == 0, result.output
        assert "Used by (0):" in result.output
        assert result.output.split("Used by (0):")[1].strip().startswith("—")

    def test_not_found(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["get", "does-not-exist"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestDelete:
    PROMPT_USED = 'Template "Login – Shop" is used by 2 tests (steps are kept, template link removed). Delete?'
    PROMPT_UNUSED = 'Template "Cookie banner" is not used by any test. Delete?'

    def test_prompt_with_usages_and_confirm(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["delete", LOGIN_ID], input_text="y\n")
        assert result.exit_code == 0, result.output
        assert self.PROMPT_USED in result.output
        assert f"✓ Template {LOGIN_ID} deleted." in result.output
        mock_client.delete.assert_called_once_with(f"/templates/{LOGIN_ID}")

    def test_singular_test(self, runner, mock_client):
        original = mock_client.get.side_effect

        def get(path, params=None):
            if path == f"/templates/{LOGIN_ID}/usages":
                return {"usages": USAGES[:1], "count": 1}
            return original(path, params)

        mock_client.get.side_effect = get
        result = _invoke(runner, mock_client, ["delete", LOGIN_ID], input_text="y\n")
        assert 'is used by 1 test (steps are kept' in result.output

    def test_prompt_without_usages(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["delete", SETUP_ID], input_text="y\n")
        assert result.exit_code == 0, result.output
        assert self.PROMPT_UNUSED in result.output
        mock_client.delete.assert_called_once_with(f"/templates/{SETUP_ID}")

    def test_decline_aborts_with_exit_0(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["delete", LOGIN_ID], input_text="n\n")
        assert result.exit_code == 0, result.output
        assert "Aborted." in result.output
        mock_client.delete.assert_not_called()

    def test_yes_skips_prompt(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["delete", LOGIN_ID, "--yes"])
        assert result.exit_code == 0, result.output
        assert "Delete?" not in result.output
        assert f"✓ Template {LOGIN_ID} deleted." in result.output
        mock_client.delete.assert_called_once_with(f"/templates/{LOGIN_ID}")

    def test_short_yes_flag(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["delete", LOGIN_ID, "-y"])
        assert result.exit_code == 0
        mock_client.delete.assert_called_once()

    def test_unknown_template_is_404_before_prompt(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["delete", "does-not-exist"], input_text="y\n")
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
        assert "Delete?" not in result.output
        mock_client.delete.assert_not_called()

    def test_api_error_on_delete(self, runner, mock_client):
        mock_client.delete.side_effect = ApiError(403, "Insufficient permissions. Missing required scopes: api/templates.write")
        result = _invoke(runner, mock_client, ["delete", LOGIN_ID, "--yes"])
        assert result.exit_code == 1
        assert "api/templates.write" in result.output


class TestCreate:
    def test_creates_and_prints_id(self, runner, mock_client, tmp_path):
        path = _template_file(tmp_path)
        result = _invoke(runner, mock_client, ["create", str(path)])
        assert result.exit_code == 0, result.output
        assert f"✓ Template created: Login – Shop (ID: {LOGIN_ID})" in result.output
        posted_path, kwargs = mock_client.post.call_args[0][0], mock_client.post.call_args[1]
        assert posted_path == "/templates/import"
        body = kwargs["json_body"]
        assert body["templateVersion"] == "1.0"
        assert body["template"]["name"] == "Login – Shop"
        assert body["steps"][0]["browser_action"] == "navigate"
        assert body["variables"] == [{"key": "base", "value": "https://e.test"}]

    def test_json_output(self, runner, mock_client, tmp_path):
        path = _template_file(tmp_path)
        result = _invoke(runner, mock_client, ["create", str(path), "--format", "json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == {"id": LOGIN_ID, "name": "Login – Shop", "stepsCreated": 3}

    def test_dry_run_validates_only(self, runner, mock_client, tmp_path):
        path = _template_file(tmp_path)
        result = _invoke(runner, mock_client, ["create", str(path), "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "valid" in result.output.lower()
        assert "shop_username" in result.output and "shop_password" in result.output
        mock_client.post.assert_not_called()

    def test_dry_run_json(self, runner, mock_client, tmp_path):
        path = _template_file(tmp_path)
        result = _invoke(runner, mock_client, ["create", str(path), "--dry-run", "--format", "json"])
        data = json.loads(result.output)
        assert data["valid"] is True
        assert data["name"] == "Login – Shop"
        assert data["stepCount"] == 3
        assert data["secretKeys"] == ["shop_username", "shop_password"]

    def test_validation_errors_per_field(self, runner, mock_client, tmp_path):
        path = _template_file(tmp_path, template={"name": ""}, templateVersion="9")
        result = _invoke(runner, mock_client, ["create", str(path)])
        assert result.exit_code == 1
        assert "templateVersion" in result.output
        assert "template.name" in result.output
        mock_client.post.assert_not_called()

    def test_placeholder_in_template_file_rejected(self, runner, mock_client, tmp_path):
        steps = [{"sort": 1, "step_type": "template", "template_id": SETUP_ID}]
        path = _template_file(tmp_path, steps=steps)
        result = _invoke(runner, mock_client, ["create", str(path)])
        assert result.exit_code == 1
        assert "templates cannot contain template steps" in result.output
        mock_client.post.assert_not_called()

    def test_malformed_json(self, runner, mock_client, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{not json")
        result = _invoke(runner, mock_client, ["create", str(path)])
        assert result.exit_code == 1
        assert "broken.json" in result.output
        mock_client.post.assert_not_called()

    def test_missing_file_is_usage_error(self, runner, mock_client, tmp_path):
        result = _invoke(runner, mock_client, ["create", str(tmp_path / "nope.json")])
        assert result.exit_code == 2

    def test_api_error(self, runner, mock_client, tmp_path):
        mock_client.post.side_effect = ApiError(403, "Insufficient permissions. Missing required scopes: api/templates.write")
        result = _invoke(runner, mock_client, ["create", str(_template_file(tmp_path))])
        assert result.exit_code == 1
        assert "api/templates.write" in result.output


class TestExport:
    def _exported(self, result):
        return json.loads(result.output)

    def test_stdout_is_a_valid_template_file_with_step_ids(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["export", LOGIN_ID])
        assert result.exit_code == 0, result.output
        data = self._exported(result)
        assert data["templateVersion"] == "1.0"
        assert data["template"] == {"name": "Login – Shop", "description": "Logs in", "category": "auth", "tags": ["shop"]}
        assert [s["id"] for s in data["steps"]] == ["s1", "s2", "s3", "s4"]
        assert [s["sort"] for s in data["steps"]] == [1, 2, 3, 4]
        assert data["steps"][0]["browser_action"] == "navigate"
        assert data["steps"][1]["secret_key"] == "shop_username"
        assert data["variables"] == LOGIN_VARIABLES
        # round trip: the export parses as a template file and keeps the ids
        payload = TemplateFilePayload.model_validate(data)
        assert [s.id for s in payload.steps] == ["s1", "s2", "s3", "s4"]

    def test_key_order_is_stable(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["export", LOGIN_ID])
        step = self._exported(result)["steps"][0]
        keys = list(step.keys())
        assert keys[:4] == ["id", "sort", "step_type", "instruction"]
        assert keys[4:] == sorted(keys[4:])

    def test_server_only_and_empty_fields_are_not_emitted(self, runner, mock_client):
        original = mock_client.get.side_effect

        def get(path, params=None):
            if path == f"/templates/{LOGIN_ID}/steps":
                return {"steps": [{
                    "pk": f"TEMPLATE#{LOGIN_ID}", "sk": "STEP#s1", "id": "s1", "sort": 1, "step_type": "navigation",
                    "instruction": "Open", "created_at": "2025-01-01T00:00:00Z", "updated_at": "x",
                    "secret_key": "", "validation_value": None, "network_mock_passthrough": False,
                    "network_timeout": 0, "unknown_server_field": "nope",
                }]}
            return original(path, params)

        mock_client.get.side_effect = get
        result = _invoke(runner, mock_client, ["export", LOGIN_ID])
        step = self._exported(result)["steps"][0]
        for absent in ("pk", "sk", "created_at", "updated_at", "secret_key", "validation_value", "unknown_server_field"):
            assert absent not in step
        # authored falsy values that the server keeps are kept here too
        assert step["network_mock_passthrough"] is False
        assert step["network_timeout"] == 0

    def test_steps_renumbered_from_sort_order(self, runner, mock_client):
        original = mock_client.get.side_effect

        def get(path, params=None):
            if path == f"/templates/{LOGIN_ID}/steps":
                return {"steps": [{"id": "b", "sort": 20, "step_type": "navigation", "instruction": "b"},
                                  {"id": "a", "sort": 5, "step_type": "navigation", "instruction": "a"}]}
            return original(path, params)

        mock_client.get.side_effect = get
        data = self._exported(_invoke(runner, mock_client, ["export", LOGIN_ID]))
        assert [(s["id"], s["sort"]) for s in data["steps"]] == [("a", 1), ("b", 2)]

    def test_output_file(self, runner, mock_client, tmp_path):
        target = tmp_path / "out" / "login.json"
        target.parent.mkdir()
        result = _invoke(runner, mock_client, ["export", LOGIN_ID, "--output", str(target)])
        assert result.exit_code == 0, result.output
        assert f"✓ Exported Login – Shop (4 steps) to {target}" in result.output
        text = target.read_text(encoding="utf-8")
        assert text.endswith("\n")
        data = json.loads(text)
        assert data["template"]["name"] == "Login – Shop"
        assert "  \"templateVersion\"" in text  # indent=2

    def test_unwritable_output_is_exit_1(self, runner, mock_client, tmp_path):
        result = _invoke(runner, mock_client, ["export", LOGIN_ID, "--output", str(tmp_path / "missing-dir" / "x.json")])
        assert result.exit_code == 1
        assert "missing-dir" in result.output

    def test_not_found(self, runner, mock_client):
        result = _invoke(runner, mock_client, ["export", "does-not-exist"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_api_error(self, runner, mock_client):
        mock_client.get.side_effect = ApiError(403, "Insufficient permissions.")
        result = _invoke(runner, mock_client, ["export", LOGIN_ID])
        assert result.exit_code == 1
        assert "Insufficient permissions" in result.output


class TestUpdate:
    """``templates update <id> <file> [--dry-run]`` — plan against the current template, then ``PUT``."""

    def _file(self, tmp_path, steps=None, **template):
        return _template_file(
            tmp_path,
            template={"name": "Login – Shop", "description": "Logs in", "category": "auth", "tags": ["shop"], **template},
            steps=steps if steps is not None else [
                {"id": "s1", "sort": 1, "step_type": "browser", "instruction": "Open login", "browser_action": "navigate"},
                {"id": "s2", "sort": 2, "step_type": "secret", "instruction": "Click into the username field.",
                 "secret_key": "shop_username"},
                {"id": "s3", "sort": 3, "step_type": "secret", "instruction": "Click into the password field (edited).",
                 "secret_key": "shop_password"},
                {"sort": 4, "step_type": "navigation", "instruction": "Brand new"},
                # s4 is absent → deleted
            ],
        )

    @pytest.fixture(autouse=True)
    def _replace_response(self, mock_client):
        mock_client.put.return_value = {"id": LOGIN_ID, "name": "Login – Shop", "version": 4,
                                        "stepsCreated": 1, "stepsUpdated": 3, "stepsDeleted": 1}

    def test_dry_run_plan_human(self, runner, mock_client, tmp_path):
        result = _invoke(runner, mock_client, ["update", LOGIN_ID, str(self._file(tmp_path, description="Logs in v2")), "--dry-run"])
        assert result.exit_code == 0, result.output
        assert 'Plan for "Login – Shop": 3 steps updated, 1 created, 1 deleted; metadata changed: description' in result.output
        mock_client.put.assert_not_called()

    def test_dry_run_plan_json(self, runner, mock_client, tmp_path):
        result = _invoke(runner, mock_client, ["update", LOGIN_ID, str(self._file(tmp_path, tags=["shop", "x"])), "--dry-run", "--format", "json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == {
            "valid": True, "plan": {"created": 1, "updated": 3, "deleted": 1, "metadataChanged": ["tags"]},
        }
        mock_client.put.assert_not_called()

    def test_dry_run_no_metadata_change(self, runner, mock_client, tmp_path):
        result = _invoke(runner, mock_client, ["update", LOGIN_ID, str(self._file(tmp_path)), "--dry-run"])
        assert "metadata changed: —" in result.output

    def test_unknown_id_stops_before_put(self, runner, mock_client, tmp_path):
        steps = [{"id": "s1", "sort": 1, "step_type": "navigation", "instruction": "a"},
                 {"id": "ghost", "sort": 2, "step_type": "navigation", "instruction": "b"}]
        result = _invoke(runner, mock_client, ["update", LOGIN_ID, str(self._file(tmp_path, steps=steps))])
        assert result.exit_code == 1
        assert f"steps[1]: id ghost does not belong to template {LOGIN_ID}" in result.output
        mock_client.put.assert_not_called()

    def test_update_sends_payload_and_prints_result(self, runner, mock_client, tmp_path):
        result = _invoke(runner, mock_client, ["update", LOGIN_ID, str(self._file(tmp_path))])
        assert result.exit_code == 0, result.output
        assert "✓ Template updated: Login – Shop (version 4; 3 updated, 1 created, 1 deleted)" in result.output
        path, kwargs = mock_client.put.call_args[0][0], mock_client.put.call_args[1]
        assert path == f"/templates/{LOGIN_ID}"
        body = kwargs["json_body"]
        assert body["templateVersion"] == "1.0"
        assert body["template"]["name"] == "Login – Shop"
        assert [s.get("id") for s in body["steps"]] == ["s1", "s2", "s3", None]
        assert body["steps"][0]["browser_action"] == "navigate"
        assert "secret_key" not in body["steps"][0]  # exclude_none
        assert body["variables"] == [{"key": "base", "value": "https://e.test"}]

    def test_update_json_output(self, runner, mock_client, tmp_path):
        result = _invoke(runner, mock_client, ["update", LOGIN_ID, str(self._file(tmp_path)), "--format", "json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["id"] == LOGIN_ID and data["version"] == 4
        assert (data["steps_created"], data["steps_updated"], data["steps_deleted"]) == (1, 3, 1)

    def test_invalid_file_renders_like_create(self, runner, mock_client, tmp_path):
        path = self._file(tmp_path, steps=[{"id": "s1", "sort": 1, "step_type": "navigation", "instruction": "a"},
                                           {"id": "s1", "sort": 2, "step_type": "navigation", "instruction": "b"}])
        result = _invoke(runner, mock_client, ["update", LOGIN_ID, str(path)])
        assert result.exit_code == 1
        assert "is not a valid template file" in result.output
        assert "duplicate step id s1" in result.output
        mock_client.put.assert_not_called()
        mock_client.get.assert_not_called()

    def test_missing_file_is_usage_error(self, runner, mock_client, tmp_path):
        result = _invoke(runner, mock_client, ["update", LOGIN_ID, str(tmp_path / "nope.json")])
        assert result.exit_code == 2

    def test_template_not_found(self, runner, mock_client, tmp_path):
        result = _invoke(runner, mock_client, ["update", "does-not-exist", str(self._file(tmp_path))])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
        mock_client.put.assert_not_called()

    def test_api_400_surfaced(self, runner, mock_client, tmp_path):
        mock_client.put.side_effect = ApiError(400, "template too large for an atomic update (max 98 steps)")
        result = _invoke(runner, mock_client, ["update", LOGIN_ID, str(self._file(tmp_path))])
        assert result.exit_code == 1
        assert "too large" in result.output


class TestRegistration:
    def test_group_help_lists_commands(self, runner):
        result = runner.invoke(cli, ["templates", "--help"])
        assert result.exit_code == 0
        for name in ("list", "get", "create", "delete", "export", "update"):
            assert name in result.output
