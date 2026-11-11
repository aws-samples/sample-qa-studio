"""``importers.template_resolver`` — fetch referenced templates once, mark files with unknown ones invalid."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from qa_studio_cli.importers.scanner import scan_all
from qa_studio_cli.importers.template_resolver import ResolvedTemplate, resolve_templates
from qa_studio_cli.models.errors import ApiError

LOGIN_ID = "3f1c0000-0000-4000-8000-000000000001"
SETUP_ID = "3f1c0000-0000-4000-8000-000000000002"
MISSING_ID = "3f1c0000-0000-4000-8000-00000000dead"

LOGIN_STEPS = [
    {"id": "s1", "sort": 1, "step_type": "browser", "instruction": "Open login"},
    {"id": "s2", "sort": 2, "step_type": "secret", "instruction": "user", "secret_key": "shop_username"},
    {"id": "s3", "sort": 3, "step_type": "secret", "instruction": "pw", "secret_key": "shop_password"},
]
SETUP_STEPS = [{"id": "x", "sort": 1, "step_type": "navigation", "instruction": "Dismiss."}]


def _write(tmp_path: Path, name: str, steps, secrets=()):
    payload = {
        "exportVersion": "1.0", "exportedAt": "2025-01-01T00:00:00Z",
        "usecase": {"name": name, "starting_url": "https://e.test"},
        "steps": steps, "secrets": list(secrets),
    }
    (tmp_path / f"{name}.json").write_text(json.dumps(payload))


def _placeholder(sort, template_id=LOGIN_ID):
    return {"sort": sort, "step_type": "template", "template_id": template_id}


def _step(sort, instruction="Do it", **extra):
    return {"sort": sort, "step_type": "navigation", "instruction": instruction, **extra}


@pytest.fixture
def client():
    client = MagicMock()

    def get(path, params=None):
        if path == f"/templates/{LOGIN_ID}":
            return {"id": LOGIN_ID, "name": "Login – Shop"}
        if path == f"/templates/{LOGIN_ID}/steps":
            return {"steps": LOGIN_STEPS}
        if path == f"/templates/{SETUP_ID}":
            return {"id": SETUP_ID, "name": "Cookie banner"}
        if path == f"/templates/{SETUP_ID}/steps":
            return {"steps": SETUP_STEPS}
        raise ApiError(404, "Resource not found.")

    client.get.side_effect = get
    return client


class TestResolveTemplates:
    def test_resolves_names_and_secret_keys(self, tmp_path, client):
        _write(tmp_path, "checkout", [_placeholder(1), _step(2)])
        results = scan_all(tmp_path)
        resolved = resolve_templates(client, results)

        assert resolved == {LOGIN_ID: ResolvedTemplate(id=LOGIN_ID, name="Login – Shop",
                                                       secret_keys=["shop_username", "shop_password"])}
        (result,) = results
        assert result.is_valid
        assert result.templates == [{"id": LOGIN_ID, "name": "Login – Shop"}]
        assert result.template_secret_keys == ["shop_username", "shop_password"]

    def test_shared_template_fetched_once(self, tmp_path, client):
        _write(tmp_path, "a", [_placeholder(1), _step(2)])
        _write(tmp_path, "b", [_step(1), _placeholder(2), _placeholder(3)])
        results = scan_all(tmp_path)
        resolve_templates(client, results)
        paths = [c.args[0] for c in client.get.call_args_list]
        assert paths.count(f"/templates/{LOGIN_ID}") == 1
        assert paths.count(f"/templates/{LOGIN_ID}/steps") == 1
        assert all(r.is_valid for r in results)

    def test_unknown_template_marks_every_using_file_invalid(self, tmp_path, client):
        _write(tmp_path, "a", [_placeholder(1, MISSING_ID), _step(2)])
        _write(tmp_path, "b", [_step(1), _placeholder(2, MISSING_ID)])
        _write(tmp_path, "c", [_placeholder(1, SETUP_ID), _step(2)])
        results = {r.file_name: r for r in scan_all(tmp_path)}
        resolve_templates(client, list(results.values()))

        assert not results["a.json"].is_valid
        assert results["a.json"].errors == [
            f"step 1: template {MISSING_ID} not found — run 'qa-studio templates list' or 'qa-studio templates create'"
        ]
        assert not results["b.json"].is_valid
        assert results["b.json"].errors[0].startswith("step 2: template")
        assert results["c.json"].is_valid
        assert results["c.json"].templates == [{"id": SETUP_ID, "name": "Cookie banner"}]

    def test_files_without_placeholders_make_no_calls(self, tmp_path, client):
        _write(tmp_path, "plain", [_step(1)])
        results = scan_all(tmp_path)
        assert resolve_templates(client, results) == {}
        client.get.assert_not_called()
        assert results[0].templates == []
        assert results[0].template_secret_keys == []

    def test_already_invalid_files_are_skipped(self, tmp_path, client):
        (tmp_path / "broken.json").write_text("{nope")
        results = scan_all(tmp_path)
        resolve_templates(client, results)
        client.get.assert_not_called()

    def test_other_api_errors_mark_file_invalid_loudly(self, tmp_path, client):
        client.get.side_effect = ApiError(403, "Insufficient permissions. Missing required scopes: api/templates.read")
        _write(tmp_path, "a", [_placeholder(1), _step(2)])
        results = scan_all(tmp_path)
        resolve_templates(client, results)
        assert not results[0].is_valid
        assert "api/templates.read" in results[0].errors[0]

    def test_secret_keys_combines_file_and_template_secrets(self, tmp_path, client):
        _write(tmp_path, "a", [_placeholder(1), _step(2)],
               secrets=[{"key": "shop_password", "description": "pw"}, {"key": "api_key"}])
        results = scan_all(tmp_path)
        resolve_templates(client, results)
        assert results[0].secret_keys() == ["shop_password", "api_key", "shop_username"]
        assert results[0].secrets_count == 3
