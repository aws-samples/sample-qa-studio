"""Scope + use-case authorization on the three usecase↔template endpoints.

``import_template`` and ``update_step_from_template`` modify a use case's
steps, ``check_template_updates`` reads them.  All three are guarded by
``@require_resource_access`` on the use case in the path: scopes first, then
the owner lookup (404 when the use case is unknown), then the team check
against the use case's application.  The FakeTable only serves the handler
body; ownership comes from the patched ``resource_auth`` readers, exactly as
in production (``permissions_repo``), so the tests pin the contract rather
than the storage layout.
"""
import json
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

import check_template_updates  # noqa: E402
import import_template  # noqa: E402
import update_step_from_template  # noqa: E402
from authz_test_support import UC_ID, make_event, owned_resources  # noqa: E402
from fake_table import FakeTable  # noqa: E402

CREATOR_SUB = "creator-sub"
TEMPLATE = {"pk": "TEMPLATES", "sk": "TEMPLATE#t1", "id": "t1", "name": "Login", "version": 2}
TEMPLATE_STEP = {"pk": "TEMPLATE#t1", "sk": "STEP#ts1", "id": "ts1", "sort": 1,
                 "instruction": "Open", "step_type": "navigation"}
LINKED_STEP = {"pk": f"USECASE#{UC_ID}", "sk": "STEP#s1", "id": "s1", "sort": 1, "created_at": "t",
               "instruction": "old", "step_type": "navigation",
               "template_id": "t1", "template_step_id": "ts1", "template_version": 1}


def _table():
    return FakeTable([TEMPLATE, TEMPLATE_STEP, LINKED_STEP])


def _run(module, table, event, *, usecase_exists=True):
    """Run ``module.handler`` against ``table``; UC_ID is owned by TEAM_A's app
    (created by CREATOR_SUB) unless ``usecase_exists`` is False."""
    with patch.object(module, "boto3") as boto_mock, owned_resources(created_by=CREATOR_SUB):
        boto_mock.resource.return_value.Table.return_value = table
        if not usecase_exists:
            # owned_resources always knows UC_ID; forget it for the 404 case
            with patch("resource_auth.get_usecase_owner", return_value=None):
                return module.handler(event, None)
        return module.handler(event, None)


# (module, required scopes, body, path, success status, caller allowed on the happy path)
ENDPOINTS = [
    pytest.param(import_template, "api/usecases.write api/templates.read",
                 {"template_id": "t1"}, {"id": UC_ID}, 201, "editor_a", id="import_template"),
    pytest.param(update_step_from_template, "api/usecases.write api/templates.read",
                 None, {"id": UC_ID, "stepId": "s1"}, 200, "editor_a", id="update_step_from_template"),
    pytest.param(check_template_updates, "api/usecases.read api/templates.read",
                 None, {"id": UC_ID}, 200, "viewer_a", id="check_template_updates"),
]


@pytest.mark.parametrize("module,scopes,body,path,ok_status,caller", ENDPOINTS)
class TestTemplateEndpointAuthz:
    def test_happy_path(self, module, scopes, body, path, ok_status, caller):
        response = _run(module, _table(), make_event(caller, path=path, body=body, scopes=scopes))
        assert response["statusCode"] == ok_status, response["body"]

    def test_each_scope_is_required(self, module, scopes, body, path, ok_status, caller):
        for single in scopes.split():
            response = _run(module, _table(), make_event(caller, path=path, body=body, scopes=single))
            assert response["statusCode"] == 403, (single, response["body"])
            assert "Missing required scopes" in json.loads(response["body"])["message"]

    def test_foreign_team_is_403(self, module, scopes, body, path, ok_status, caller):
        table = _table()
        response = _run(module, table, make_event("editor_b", path=path, body=body, scopes=scopes))
        assert response["statusCode"] == 403, response["body"]
        assert json.loads(response["body"])["error"] == "Forbidden"
        assert table.put_calls == []

    def test_missing_usecase_is_404(self, module, scopes, body, path, ok_status, caller):
        table = _table()
        response = _run(module, table, make_event(caller, path=path, body=body, scopes=scopes),
                        usecase_exists=False)
        assert response["statusCode"] == 404, response["body"]
        assert json.loads(response["body"])["error"] == "Use case not found"
        assert table.put_calls == []

    def test_admin_bypass(self, module, scopes, body, path, ok_status, caller):
        response = _run(module, _table(), make_event("admin", path=path, body=body, scopes="api/admin"))
        assert response["statusCode"] == ok_status, response["body"]


class TestEditActions:
    SCOPES = "api/usecases.write api/templates.read"

    @pytest.mark.parametrize("module,body,path", [
        (import_template, {"template_id": "t1"}, {"id": UC_ID}),
        (update_step_from_template, None, {"id": UC_ID, "stepId": "s1"}),
    ], ids=["import_template", "update_step_from_template"])
    def test_viewer_in_owner_team_cannot_edit(self, module, body, path):
        table = _table()
        response = _run(module, table, make_event("viewer_a", path=path, body=body, scopes=self.SCOPES))
        assert response["statusCode"] == 403, response["body"]
        assert table.put_calls == []

    def test_creator_retains_edit(self):
        event = make_event("viewer_a", path={"id": UC_ID}, body={"template_id": "t1"},
                           scopes=self.SCOPES, sub=CREATOR_SUB)
        response = _run(import_template, _table(), event)
        assert response["statusCode"] == 201, response["body"]

    def test_check_updates_is_view_only(self):
        response = _run(check_template_updates, _table(),
                        make_event("viewer_a", path={"id": UC_ID}, scopes="api/usecases.read api/templates.read"))
        assert response["statusCode"] == 200
        assert json.loads(response["body"])["updates"][0]["has_update"] is True
