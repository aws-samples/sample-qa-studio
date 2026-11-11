"""Template insert / apply report the secrets the copied ``secret`` steps need.

Secrets are only ever created through ``POST /usecase/{id}/secrets`` with a
value.  ``import_template`` and ``apply_template`` therefore write nothing for
a secret step — they return ``missingSecrets`` (distinct ``secret_key`` values
of the inserted steps, omitted when empty) so the UI / CLI can ask for the
values, exactly like ``POST /import`` does for its ``secrets`` list.
"""
import json
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

import apply_template  # noqa: E402
import import_template  # noqa: E402
import import_usecase  # noqa: E402
from authz_test_support import APP_ID, make_event, resource_access_granted  # noqa: E402
from fake_table import FakeTable  # noqa: E402
from secret_steps import secret_keys_of_steps  # noqa: E402
from test_import_export_repeat import _import  # noqa: E402


@pytest.fixture(autouse=True)
def _access_granted():
    """Handler-logic tests: ownership is covered by the *_access tests."""
    with resource_access_granted():
        yield

TEMPLATE = {"pk": "TEMPLATES", "sk": "TEMPLATE#t1", "id": "t1", "name": "Login", "version": 1}
TEMPLATE_STEPS = [
    {"pk": "TEMPLATE#t1", "sk": "STEP#ts1", "id": "ts1", "sort": 1, "step_type": "browser",
     "instruction": "Open login", "browser_action": "navigate", "browser_args": '{"url": "https://e.test"}'},
    {"pk": "TEMPLATE#t1", "sk": "STEP#ts2", "id": "ts2", "sort": 2, "step_type": "secret",
     "instruction": "Click into the username field.", "secret_key": "username"},
    {"pk": "TEMPLATE#t1", "sk": "STEP#ts3", "id": "ts3", "sort": 3, "step_type": "secret",
     "instruction": "Click into the password field.", "secret_key": "password"},
    # same key twice → reported once
    {"pk": "TEMPLATE#t1", "sk": "STEP#ts4", "id": "ts4", "sort": 4, "step_type": "secret",
     "instruction": "Click into the password confirmation field.", "secret_key": "password"},
]
USECASE = {"pk": "USECASES", "sk": "USECASE#uc-1", "id": "uc-1"}


class TestSecretKeysOfSteps:
    def test_distinct_keys_of_secret_steps_in_order(self):
        assert secret_keys_of_steps(TEMPLATE_STEPS) == ["username", "password"]

    def test_ignores_non_secret_steps_and_blank_keys(self):
        steps = [{"step_type": "navigation", "secret_key": "x"}, {"step_type": "secret", "secret_key": ""},
                 {"step_type": "secret"}]
        assert secret_keys_of_steps(steps) == []


def _run(module, table, event):
    with patch.object(module, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        boto_mock.client.side_effect = AssertionError("template lambdas must not touch Secrets Manager")
        return module.handler(event, None)


def _event(body, path, scope):
    return make_event(path=path, body=body, scopes=scope)


def _secret_records(table, usecase_id):
    return table.by_prefix(f"USECASE#{usecase_id}", "SECRET#")


class TestImportTemplate:
    SCOPE = "api/usecases.write api/templates.read"

    def test_reports_missing_secrets_and_writes_no_secret_records(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE])
        response = _run(import_template, table, _event({"template_id": "t1"}, {"id": "uc-1"}, self.SCOPE))
        assert response["statusCode"] == 201, response["body"]
        body = json.loads(response["body"])
        assert body["missingSecrets"] == ["username", "password"]
        assert body["steps_created"] == 4
        assert _secret_records(table, "uc-1") == []

    def test_template_without_secret_steps_omits_missing_secrets(self):
        table = FakeTable([TEMPLATE, TEMPLATE_STEPS[0], USECASE])
        response = _run(import_template, table, _event({"template_id": "t1"}, {"id": "uc-1"}, self.SCOPE))
        assert response["statusCode"] == 201, response["body"]
        assert "missingSecrets" not in json.loads(response["body"])


class TestApplyTemplate:
    SCOPE = "api/templates.read api/usecases.write"

    def test_reports_missing_secrets_for_new_usecase(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS])
        response = _run(apply_template, table, _event({"name": "Login copy", "application_id": APP_ID}, {"id": "t1"}, self.SCOPE))
        assert response["statusCode"] == 200, response["body"]
        body = json.loads(response["body"])
        assert body["missingSecrets"] == ["username", "password"]
        assert _secret_records(table, body["usecaseId"]) == []

    def test_no_secret_steps_omits_missing_secrets(self):
        table = FakeTable([TEMPLATE, TEMPLATE_STEPS[0]])
        response = _run(apply_template, table, _event({"name": "Login copy", "application_id": APP_ID}, {"id": "t1"}, self.SCOPE))
        assert "missingSecrets" not in json.loads(response["body"])


class TestImportUsecaseUnchanged:
    """``POST /import`` keeps its historical contract: SECRET# records for the
    export's ``secrets`` list and ``missingSecrets`` in the response."""

    PAYLOAD = {
        "exportVersion": "1.0", "exportedAt": "2025-01-01T00:00:00Z",
        "usecase": {"name": "Login"},
        "steps": [{"sort": 1, "instruction": "Click into the password field.", "step_type": "secret",
                   "secret_key": "password"}],
        "secrets": [{"key": "password", "description": "Login password"}],
    }

    def test_records_and_missing_secrets(self):
        response, captured = _import(self.PAYLOAD)
        assert response["statusCode"] == 200, response["body"]
        assert json.loads(response["body"])["missingSecrets"] == ["password"]
        records = [i for i in captured if i["sk"] == "SECRET#password"]
        assert len(records) == 1
        assert records[0]["description"] == "Login password"
        assert records[0]["secret_name"].endswith("/password")

    def test_no_secrets_manager_client(self):
        """Secrets Manager rejects empty values, so the lambda never creates secrets (and has no IAM for it)."""
        assert "secretsmanager" not in open(import_usecase.__file__).read()
