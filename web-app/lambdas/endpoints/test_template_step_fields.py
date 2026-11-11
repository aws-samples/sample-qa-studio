"""Template lambdas preserve every step-definition field.

Browser, transform and date (``retrieve_value``) steps used to lose their
configuration when stored as template steps and again when a template was
applied / imported into a usecase.  All five lambdas now go through
``step_copy`` (``COPYABLE_STEP_FIELDS`` / ``copy_step_fields``).
"""
import json
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

import apply_template  # noqa: E402
import create_template_step  # noqa: E402
import import_template  # noqa: E402
import update_step_from_template  # noqa: E402
import update_template_step  # noqa: E402
from authz_test_support import APP_ID, make_event, resource_access_granted  # noqa: E402
from fake_table import FakeTable  # noqa: E402
from step_copy import COPYABLE_STEP_FIELDS, copy_step_fields  # noqa: E402


@pytest.fixture(autouse=True)
def _access_granted():
    """Handler-logic tests: ownership is covered by the *_access tests."""
    with resource_access_granted():
        yield

TEMPLATE = {"pk": "TEMPLATES", "sk": "TEMPLATE#t1", "id": "t1", "name": "Login", "version": 3}

#: Authored step bodies (what the UI sends to create_template_step).
STEP_BODIES = [
    {"sort": 1, "instruction": "Open the login page", "step_type": "browser",
     "browser_action": "navigate", "browser_args": '{"url": "https://e.test/login"}',
     "enable_advanced_click_types": True},
    {"sort": 2, "instruction": "Add 2", "step_type": "transform",
     "transform_operation": "math", "transform_args": '{"expression": "{{n}} + 2"}',
     "capture_variable": "n2"},
    {"sort": 3, "instruction": "Read the order date", "step_type": "retrieve_value",
     "capture_variable": "order_date", "value_type": "date", "value_source": "page",
     "value_format": "%d.%m.%Y"},
    {"sort": 4, "instruction": "Orders API", "step_type": "network_assertion",
     "network_url_pattern": "**/api/orders", "network_method": "POST",
     "network_mock_passthrough": False, "network_timeout": 0, "network_response_status": 201},
]

TEMPLATE_STEPS = [
    {"pk": "TEMPLATE#t1", "sk": f"STEP#ts{body['sort']}", "id": f"ts{body['sort']}", "created_at": "t", **body}
    for body in STEP_BODIES
]


def _event(body=None, path=None, scope="api/templates.write"):
    return make_event(path=path, body=body, scopes=scope)


def _run(module, table, event):
    with patch.object(module, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        return module.handler(event, None)


def _definitions(steps):
    return [copy_step_fields(s) for s in sorted(steps, key=lambda s: s["sort"])]


class TestCreateTemplateStep:
    @pytest.mark.parametrize("body", STEP_BODIES, ids=lambda b: b["step_type"])
    def test_every_field_persisted(self, body):
        table = FakeTable([TEMPLATE])
        response = _run(create_template_step, table, _event(body, {"id": "t1"}))
        assert response["statusCode"] == 201, response["body"]
        stored = table.by_prefix("TEMPLATE#t1", "STEP#")[0]
        for field, value in body.items():
            assert stored[field] == value, field

    def test_no_inline_field_list(self):
        source = open(create_template_step.__file__).read()
        assert "COPYABLE_STEP_FIELDS" in source
        assert "'network_url_pattern'" not in source


class TestUpdateTemplateStep:
    def _update(self, body, existing):
        table = FakeTable([TEMPLATE, existing])
        response = _run(update_template_step, table, _event(body, {"id": "t1", "stepId": existing["id"]}))
        assert response["statusCode"] == 200, response["body"]
        return table.get("TEMPLATE#t1", existing["sk"]), table.update_calls[0]

    def test_browser_fields_written_when_sent(self):
        stored, call = self._update(STEP_BODIES[0], TEMPLATE_STEPS[0] | {"browser_action": "reload"})
        assert stored["browser_action"] == "navigate"
        assert stored["browser_args"] == '{"url": "https://e.test/login"}'
        assert stored["enable_advanced_click_types"] is True
        # reserved-word safe: every attribute is aliased
        assert all(part.strip().startswith("#") for part in call["UpdateExpression"][4:].split(","))

    def test_date_fields_written_when_sent(self):
        stored, _ = self._update(STEP_BODIES[2], TEMPLATE_STEPS[2] | {"value_format": "%Y"})
        assert stored["value_format"] == "%d.%m.%Y"
        assert stored["value_source"] == "page"

    def test_legacy_fields_always_set_with_empty_default(self):
        stored, call = self._update(
            {"sort": 1, "instruction": "x", "step_type": "navigation"},
            TEMPLATE_STEPS[0] | {"secret_key": "old", "validation_value": "v"},
        )
        for legacy in ("secret_key", "capture_variable", "validation_type", "validation_operator",
                       "validation_value", "assertion_variable", "value_type"):
            assert stored[legacy] == "", legacy
            assert f":{legacy}" in call["ExpressionAttributeValues"]

    def test_optional_fields_untouched_when_absent(self):
        existing = TEMPLATE_STEPS[0] | {"browser_action": "reload", "network_timeout": 5}
        stored, call = self._update({"sort": 1, "instruction": "x", "step_type": "browser"}, existing)
        assert stored["browser_action"] == "reload"
        assert stored["network_timeout"] == 5
        assert ":browser_action" not in call["ExpressionAttributeValues"]
        assert ":network_timeout" not in call["ExpressionAttributeValues"]

    def test_no_inline_field_list(self):
        source = open(update_template_step.__file__).read()
        assert "COPYABLE_STEP_FIELDS" in source
        assert "'network_url_pattern'" not in source


class TestApplyTemplate:
    def test_steps_keep_all_fields(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS])
        response = _run(apply_template, table, _event({"name": "From template", "application_id": APP_ID}, {"id": "t1"},
                                                      "api/templates.read api/usecases.write"))
        assert response["statusCode"] == 200, response["body"]
        usecase_id = json.loads(response["body"])["usecaseId"]
        copied = table.by_prefix(f"USECASE#{usecase_id}", "STEP#")
        assert len(copied) == 4
        assert _definitions(copied) == _definitions(TEMPLATE_STEPS)
        network = next(s for s in copied if s["step_type"] == "network_assertion")
        assert network["network_mock_passthrough"] is False
        assert network["network_timeout"] == 0

    def test_no_inline_field_list(self):
        source = open(apply_template.__file__).read()
        assert "copy_step_fields" in source
        assert "'network_url_pattern'" not in source


class TestImportTemplate:
    def test_steps_keep_all_fields_and_template_linkage(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, {"pk": "USECASES", "sk": "USECASE#uc-1", "id": "uc-1"}])
        response = _run(import_template, table, _event({"template_id": "t1"}, {"id": "uc-1"},
                                                       "api/usecases.write api/templates.read"))
        assert response["statusCode"] == 201, response["body"]
        inserted = table.by_prefix("USECASE#uc-1", "STEP#")
        assert len(inserted) == 4
        assert _definitions(inserted) == _definitions(TEMPLATE_STEPS)
        for step in inserted:
            assert step["template_id"] == "t1"
            assert step["template_version"] == 3
            assert step["template_step_id"].startswith("ts")

    def test_no_inline_field_list(self):
        """Copies through ``template_expansion.build_linked_steps`` (which uses ``copy_step_fields``)."""
        source = open(import_template.__file__).read()
        assert "build_linked_steps" in source
        assert "'network_url_pattern'" not in source


class TestUpdateStepFromTemplate:
    def test_copies_value_format_and_browser_fields(self):
        linked = {
            "pk": "USECASE#uc-1", "sk": "STEP#s1", "id": "s1", "sort": 7, "created_at": "t",
            "instruction": "old", "step_type": "retrieve_value",
            "template_id": "t1", "template_step_id": "ts3", "template_version": 1,
        }
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, {"pk": "USECASES", "sk": "USECASE#uc-1", "id": "uc-1"}, linked])
        response = _run(update_step_from_template, table,
                        _event(None, {"id": "uc-1", "stepId": "s1"}, "api/usecases.write api/templates.read"))
        assert response["statusCode"] == 200, response["body"]
        updated = table.get("USECASE#uc-1", "STEP#s1")
        assert copy_step_fields(updated) == copy_step_fields(TEMPLATE_STEPS[2])
        assert updated["value_format"] == "%d.%m.%Y"
        assert updated["sort"] == 7 and updated["created_at"] == "t"
        assert updated["template_version"] == 3

    def test_stale_fields_from_previous_template_version_are_dropped(self):
        linked = {
            "pk": "USECASE#uc-1", "sk": "STEP#s1", "id": "s1", "sort": 1, "created_at": "t",
            "instruction": "old", "step_type": "browser", "browser_action": "reload", "browser_args": '{"hard": true}',
            "template_id": "t1", "template_step_id": "ts4", "template_version": 1,
        }
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, {"pk": "USECASES", "sk": "USECASE#uc-1", "id": "uc-1"}, linked])
        response = _run(update_step_from_template, table,
                        _event(None, {"id": "uc-1", "stepId": "s1"}, "api/usecases.write api/templates.read"))
        assert response["statusCode"] == 200, response["body"]
        updated = table.get("USECASE#uc-1", "STEP#s1")
        assert "browser_action" not in updated
        assert updated["network_url_pattern"] == "**/api/orders"

    def test_no_inline_field_list(self):
        source = open(update_step_from_template.__file__).read()
        assert "copy_step_fields" in source
        assert "'network_url_pattern'" not in source


def test_template_lambdas_cover_every_definition_field():
    """Belt and braces: the shared list is what the tests above exercise."""
    exercised = set().union(*(b.keys() for b in STEP_BODIES))
    for field in ("browser_action", "browser_args", "transform_operation", "transform_args",
                  "value_source", "value_format", "enable_advanced_click_types"):
        assert field in exercised and field in COPYABLE_STEP_FIELDS
