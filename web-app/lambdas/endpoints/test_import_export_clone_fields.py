"""Browser / transform / date / network steps survive import, export and clone.

Regression for the bug where ``qa-studio tests import`` stored a ``browser``
step without ``browser_action`` (and export / clone lost browser, transform
and ``value_format`` configuration).  All three lambdas copy through
``step_copy.copy_step_fields``; this pins the behaviour end-to-end.
"""
import json
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("TABLE_NAME", "test-table")

import clone_usecase  # noqa: E402
from authz_test_support import make_event, resource_access_granted  # noqa: E402
from step_copy import copy_step_fields  # noqa: E402
from test_import_export_repeat import _export, _import  # noqa: E402

#: Field → value per step type.  ``network_mock_passthrough=False`` and
#: ``network_timeout=0`` guard the "falsy but present" rule.
SOURCE_STEPS = [
    {"pk": "USECASE#uc-1", "sk": "STEP#s1", "id": "s1", "sort": 1, "step_type": "browser",
     "instruction": "Open the login page", "browser_action": "navigate",
     "browser_args": '{"url": "https://e.test/login"}', "enable_advanced_click_types": True},
    {"pk": "USECASE#uc-1", "sk": "STEP#s2", "id": "s2", "sort": 2, "step_type": "transform",
     "instruction": "Add 2", "transform_operation": "math",
     "transform_args": '{"expression": "{{n}} + 2"}', "capture_variable": "n2"},
    {"pk": "USECASE#uc-1", "sk": "STEP#s3", "id": "s3", "sort": 3, "step_type": "retrieve_value",
     "instruction": "Read the order date", "capture_variable": "order_date",
     "value_type": "date", "value_source": "page", "value_format": "%d.%m.%Y"},
    {"pk": "USECASE#uc-1", "sk": "STEP#s4", "id": "s4", "sort": 4, "step_type": "network_assertion",
     "instruction": "Orders API", "network_url_pattern": "**/api/orders", "network_method": "POST",
     "network_request_body": '{"id": 1}', "network_body_match_type": "contains",
     "network_mock_response": '{"ok": true}', "network_mock_passthrough": False, "network_timeout": 0,
     "network_response_body": '{"ok": true}', "network_response_body_match_type": "exact",
     "network_response_status": 201},
]

_IDENTITY = ("pk", "sk", "id", "sort", "created_at", "parent_step_id")


def _definition(step):
    """Everything about a step except identity / ordering."""
    return {k: v for k, v in step.items() if k not in _IDENTITY}


def _clone(steps):
    table = MagicMock()
    table.get_item.side_effect = lambda Key: (
        {"Item": {"name": "Src", "starting_url": "https://e.test/"}} if Key["sk"] == "USECASE#uc-1" else {}
    )
    table.query.return_value = {"Items": list(steps)}
    put_items = []
    table.put_item.side_effect = lambda Item: put_items.append(Item)
    resource = MagicMock()
    resource.Table.return_value = table
    secrets = MagicMock()
    secrets.list_secrets.return_value = {"SecretList": []}
    event = make_event("editor_a", path={"id": "uc-1"}, body={"name": "Copy"}, scopes="api/usecases.write")
    with patch.object(clone_usecase, "boto3") as boto_mock, resource_access_granted():
        boto_mock.resource.return_value = resource
        boto_mock.client.return_value = secrets
        response = clone_usecase.handler(event, None)
    assert response["statusCode"] == 200, response["body"]
    return sorted((i for i in put_items if i["sk"].startswith("STEP#")), key=lambda s: s["sort"])


def _import_payload(steps):
    return {
        "exportVersion": "1.0", "exportedAt": "2025-01-01T00:00:00Z",
        "usecase": {"name": "Login", "starting_url": "https://e.test/"},
        "steps": [{"sort": s["sort"], **_definition(s)} for s in steps],
    }


class TestExportKeepsAllFields:
    def test_every_step_type_exported_verbatim(self):
        exported = _export(SOURCE_STEPS)["steps"]
        assert [_definition(s) for s in exported] == [_definition(s) for s in SOURCE_STEPS]

    def test_falsy_values_kept(self):
        network = _export(SOURCE_STEPS)["steps"][3]
        assert network["network_mock_passthrough"] is False
        assert network["network_timeout"] == 0


class TestImportKeepsAllFields:
    def test_every_step_type_persisted_verbatim(self):
        response, captured = _import(_import_payload(SOURCE_STEPS))
        assert response["statusCode"] == 200, response["body"]
        stored = sorted((i for i in captured if i["sk"].startswith("STEP#")), key=lambda s: s["sort"])
        assert [_definition(s) for s in stored] == [_definition(s) for s in SOURCE_STEPS]

    def test_browser_action_is_stored(self):
        """The original live bug."""
        _, captured = _import(_import_payload(SOURCE_STEPS[:1]))
        browser = next(i for i in captured if i["sk"].startswith("STEP#"))
        assert browser["browser_action"] == "navigate"
        assert browser["browser_args"] == '{"url": "https://e.test/login"}'


class TestCloneKeepsAllFields:
    def test_every_step_type_cloned_verbatim(self):
        cloned = _clone(SOURCE_STEPS)
        assert [_definition(s) for s in cloned] == [_definition(s) for s in SOURCE_STEPS]
        assert all(s["pk"] != "USECASE#uc-1" for s in cloned)


class TestRoundTrip:
    def test_export_then_import_is_lossless(self):
        exported = _export(SOURCE_STEPS)
        response, captured = _import(exported)
        assert response["statusCode"] == 200, response["body"]
        stored = sorted((i for i in captured if i["sk"].startswith("STEP#")), key=lambda s: s["sort"])
        assert [copy_step_fields(s) for s in stored] == [copy_step_fields(s) for s in SOURCE_STEPS]
        assert [s["sort"] for s in stored] == [1, 2, 3, 4]
