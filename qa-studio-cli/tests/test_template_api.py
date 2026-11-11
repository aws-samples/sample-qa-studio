"""``TemplateAPI`` wraps the template endpoints; response models unwrap snake_case bodies."""

from unittest.mock import MagicMock

import pytest

from qa_studio_cli.api.templates import TemplateAPI
from qa_studio_cli.models.api import (
    ImportTemplateResponse,
    InsertTemplateResponse,
    ReplaceTemplateResponse,
    TemplateModel,
    TemplateStepModel,
    TemplateUsageModel,
)

TEMPLATE_ID = "3f1c0000-0000-4000-8000-000000000001"


@pytest.fixture
def client():
    return MagicMock()


class TestTemplateAPI:
    def test_list_templates_unwraps_templates_key(self, client):
        client.get.return_value = {"templates": [{"id": TEMPLATE_ID, "name": "Login"}]}
        assert TemplateAPI(client).list_templates() == [{"id": TEMPLATE_ID, "name": "Login"}]
        client.get.assert_called_once_with("/templates")

    def test_list_templates_empty_or_missing_key(self, client):
        client.get.return_value = {}
        assert TemplateAPI(client).list_templates() == []

    def test_get_template(self, client):
        client.get.return_value = {"id": TEMPLATE_ID, "name": "Login"}
        assert TemplateAPI(client).get_template(TEMPLATE_ID) == {"id": TEMPLATE_ID, "name": "Login"}
        client.get.assert_called_once_with(f"/templates/{TEMPLATE_ID}")

    def test_list_steps_sorted_by_sort(self, client):
        client.get.return_value = {"steps": [
            {"id": "b", "sort": 2, "step_type": "secret", "instruction": "pw", "secret_key": "password"},
            {"id": "a", "sort": 1, "step_type": "navigation", "instruction": "open"},
        ]}
        steps = TemplateAPI(client).list_steps(TEMPLATE_ID)
        assert [s["id"] for s in steps] == ["a", "b"]
        client.get.assert_called_once_with(f"/templates/{TEMPLATE_ID}/steps")

    def test_get_variables_unwraps_variables_key(self, client):
        client.get.return_value = {"pk": "TEMPLATE#x", "sk": "VARIABLES", "variables": [{"key": "a", "value": "1"}]}
        assert TemplateAPI(client).get_variables(TEMPLATE_ID) == [{"key": "a", "value": "1"}]
        client.get.assert_called_once_with(f"/templates/{TEMPLATE_ID}/variables")

    def test_get_variables_missing_record(self, client):
        client.get.return_value = {"variables": []}
        assert TemplateAPI(client).get_variables(TEMPLATE_ID) == []

    def test_import_template_posts_file_payload(self, client):
        payload = {"templateVersion": "1.0", "template": {"name": "Login"}, "steps": [{"sort": 1}]}
        client.post.return_value = {"id": TEMPLATE_ID, "name": "Login", "stepsCreated": 1}
        assert TemplateAPI(client).import_template(payload) == {"id": TEMPLATE_ID, "name": "Login", "stepsCreated": 1}
        client.post.assert_called_once_with("/templates/import", json_body=payload)

    def test_insert_into_usecase_with_position(self, client):
        client.post.return_value = {"steps_created": 3}
        TemplateAPI(client).insert_into_usecase("uc-1", TEMPLATE_ID, 2)
        client.post.assert_called_once_with(
            "/usecase/uc-1/import-template", json_body={"template_id": TEMPLATE_ID, "insert_position": 2}
        )

    def test_insert_into_usecase_append_when_position_none(self, client):
        client.post.return_value = {"steps_created": 3}
        TemplateAPI(client).insert_into_usecase("uc-1", TEMPLATE_ID, None)
        client.post.assert_called_once_with(
            "/usecase/uc-1/import-template", json_body={"template_id": TEMPLATE_ID, "insert_position": -1}
        )

    def test_delete_template(self, client):
        client.delete.return_value = None
        assert TemplateAPI(client).delete_template(TEMPLATE_ID) is None
        client.delete.assert_called_once_with(f"/templates/{TEMPLATE_ID}")

    def test_get_usages_unwraps_usages_key(self, client):
        client.get.return_value = {"usages": [{"usecase_id": "uc-1", "name": "Checkout"}], "count": 1}
        assert TemplateAPI(client).get_usages(TEMPLATE_ID) == [{"usecase_id": "uc-1", "name": "Checkout"}]
        client.get.assert_called_once_with(f"/templates/{TEMPLATE_ID}/usages")

    def test_get_usages_missing_key(self, client):
        client.get.return_value = {}
        assert TemplateAPI(client).get_usages(TEMPLATE_ID) == []

    def test_replace_template_puts_file_payload(self, client):
        payload = {"templateVersion": "1.0", "template": {"name": "Login"}, "steps": [{"id": "ts1", "sort": 1}]}
        client.put.return_value = {"id": TEMPLATE_ID, "name": "Login", "version": 4,
                                   "stepsCreated": 0, "stepsUpdated": 1, "stepsDeleted": 0}
        assert TemplateAPI(client).replace_template(TEMPLATE_ID, payload)["version"] == 4
        client.put.assert_called_once_with(f"/templates/{TEMPLATE_ID}", json_body=payload)


class TestModels:
    def test_template_model_from_snake_case_body(self):
        model = TemplateModel.model_validate({
            "id": TEMPLATE_ID, "name": "Login", "description": "d", "category": "auth", "tags": ["a"],
            "version": 3, "created_by": "qa@example.com", "created_at": "2025-01-01T00:00:00Z",
            "pk": "TEMPLATES", "sk": f"TEMPLATE#{TEMPLATE_ID}",
        })
        assert model.version == 3
        assert model.created_by == "qa@example.com"
        assert model.category == "auth"

    def test_template_model_defaults(self):
        model = TemplateModel.model_validate({"id": TEMPLATE_ID, "name": "Login"})
        assert (model.description, model.category, model.tags, model.version) == ("", "", [], 1)

    def test_template_step_model(self):
        step = TemplateStepModel.model_validate({
            "id": "s1", "sort": 2, "step_type": "secret", "instruction": "Click into the password field.",
            "secret_key": "password", "browser_action": None,
        })
        assert step.secret_key == "password"
        assert step.browser_action is None

    def test_template_step_model_defaults(self):
        step = TemplateStepModel.model_validate({"id": "s1"})
        assert (step.sort, step.step_type, step.instruction, step.secret_key) == (0, "navigation", "", None)

    def test_import_template_response_alias(self):
        response = ImportTemplateResponse.model_validate({"id": TEMPLATE_ID, "name": "Login", "stepsCreated": 4})
        assert response.steps_created == 4

    def test_insert_template_response_snake_and_camel(self):
        response = InsertTemplateResponse.model_validate(
            {"message": "ok", "steps_created": 3, "missingSecrets": ["password"]}
        )
        assert response.steps_created == 3
        assert response.missing_secrets == ["password"]

    def test_insert_template_response_defaults(self):
        response = InsertTemplateResponse.model_validate({"steps_created": 1})
        assert response.missing_secrets == []

    def test_template_usage_model(self):
        usage = TemplateUsageModel.model_validate({"usecase_id": "uc-1", "name": "Checkout"})
        assert (usage.usecase_id, usage.name) == ("uc-1", "Checkout")

    def test_replace_template_response_camel_case_body(self):
        response = ReplaceTemplateResponse.model_validate({
            "id": TEMPLATE_ID, "name": "Login", "version": 7, "stepsCreated": 1, "stepsUpdated": 4, "stepsDeleted": 0,
        })
        assert (response.version, response.steps_created, response.steps_updated, response.steps_deleted) == (7, 1, 4, 0)

    def test_replace_template_response_defaults(self):
        response = ReplaceTemplateResponse.model_validate({"id": TEMPLATE_ID})
        assert (response.name, response.version, response.steps_created) == ("", 0, 0)
