"""Wizard lambdas copy the shared step-field list.

``add_wizard_step`` (body → temporary EXECUTION_STEP#) and
``accept_wizard_step`` (EXECUTION_STEP# → permanent STEP#) used to carry
their own copy of the optional-field list and had drifted (no
``value_format``).  Both now iterate ``step_copy.COPYABLE_STEP_FIELDS``.
"""
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

import accept_wizard_step  # noqa: E402
import add_wizard_step  # noqa: E402
from authz_test_support import make_event, resource_access_granted  # noqa: E402
from fake_table import FakeTable  # noqa: E402
from step_copy import copy_step_fields  # noqa: E402


@pytest.fixture(autouse=True)
def _access_granted():
    """Handler-logic tests: ownership is covered by the *_access tests."""
    with resource_access_granted():
        yield

DATE_STEP = {
    "instruction": "Read the order date", "step_type": "retrieve_value",
    "capture_variable": "order_date", "value_type": "date", "value_source": "page",
    "value_format": "%d.%m.%Y",
}
BROWSER_STEP = {
    "instruction": "Open the login page", "step_type": "browser",
    "browser_action": "navigate", "browser_args": '{"url": "https://e.test/login"}',
    "enable_advanced_click_types": False,
}


def _event(body=None, path=None):
    return make_event(path=path or {}, body=body, scopes="api/usecases.write")


def _run(module, table, event):
    with patch.object(module, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        return module.handler(event, None)


class TestAddWizardStep:
    def test_date_and_browser_fields_persisted(self):
        for body in (DATE_STEP, BROWSER_STEP):
            table = FakeTable()
            # the session's usecaseId rides in the body (WizardSessionRequest)
            response = _run(add_wizard_step, table,
                            _event({**body, "usecaseId": "uc-1"}, {"sessionId": "sess-1"}))
            assert response["statusCode"] == 201, response["body"]
            stored = table.by_prefix("EXECUTION#sess-1", "EXECUTION_STEP#")[0]
            for field, value in body.items():
                assert stored[field] == value, field
            assert stored["acceptance_status"] == "pending_acceptance"

    def test_no_inline_field_list(self):
        source = open(add_wizard_step.__file__).read()
        assert "COPYABLE_STEP_FIELDS" in source
        assert "'network_url_pattern'" not in source


class TestAcceptWizardStep:
    def _accept(self, execution_step_fields):
        execution_step = {
            "pk": "EXECUTION#sess-1", "sk": "EXECUTION_STEP#es-1", "step_id": "es-1", "sort": 0,
            "created_at": "t", "acceptance_status": "pending_acceptance", "temporary": True,
            **execution_step_fields,
        }
        table = FakeTable([execution_step])
        response = _run(accept_wizard_step, table,
                        _event(None, {"sessionId": "sess-1", "stepId": "es-1", "usecaseId": "uc-1"}))
        assert response["statusCode"] == 200, response["body"]
        return table.by_prefix("USECASE#uc-1", "STEP#")[0]

    def test_date_fields_copied_to_permanent_step(self):
        permanent = self._accept(DATE_STEP)
        assert copy_step_fields(permanent) == DATE_STEP
        assert permanent["value_format"] == "%d.%m.%Y"

    def test_browser_fields_copied_to_permanent_step(self):
        permanent = self._accept(BROWSER_STEP)
        assert copy_step_fields(permanent) == BROWSER_STEP
        assert permanent["enable_advanced_click_types"] is False

    def test_runtime_and_wizard_fields_not_copied(self):
        permanent = self._accept({**BROWSER_STEP, "trajectory_s3_key": "k", "cached_steps": "[]"})
        for field in ("trajectory_s3_key", "cached_steps", "acceptance_status", "temporary", "step_id"):
            assert field not in permanent, field

    def test_no_inline_field_list(self):
        source = open(accept_wizard_step.__file__).read()
        assert "COPYABLE_STEP_FIELDS" in source
        assert "'network_url_pattern'" not in source
