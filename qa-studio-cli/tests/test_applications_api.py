"""``ApplicationsAPI`` wraps the ``/applications/{id}/{variables,secrets,datasets}`` routes."""

from unittest.mock import MagicMock

import pytest

from qa_studio_cli.api.applications import ApplicationsAPI

APP_ID = "0190a000-0000-7000-8000-000000000001"


@pytest.fixture
def client():
    return MagicMock()


class TestVariables:
    def test_get_variables_unwraps_variables_key(self, client):
        client.get.return_value = {"variables": [{"key": "a", "value": "1"}]}
        assert ApplicationsAPI(client).get_variables(APP_ID) == [{"key": "a", "value": "1"}]
        client.get.assert_called_once_with(f"/applications/{APP_ID}/variables")

    def test_get_variables_missing_or_null_key(self, client):
        client.get.return_value = {"variables": None}
        assert ApplicationsAPI(client).get_variables(APP_ID) == []
        client.get.return_value = {}
        assert ApplicationsAPI(client).get_variables(APP_ID) == []

    def test_put_variables_posts_whole_list_and_unwraps(self, client):
        variables = [{"key": "a", "value": "1"}, {"key": "b", "value": "2"}]
        client.post.return_value = {"variables": variables}
        assert ApplicationsAPI(client).put_variables(APP_ID, variables) == variables
        client.post.assert_called_once_with(
            f"/applications/{APP_ID}/variables", json_body={"variables": variables}
        )


class TestSecrets:
    def test_list_secrets_unwraps_secrets_key(self, client):
        rows = [{"key": "pw", "secret_name": "p/application/x/pw", "description": "", "created_at": "t"}]
        client.get.return_value = {"secrets": rows}
        assert ApplicationsAPI(client).list_secrets(APP_ID) == rows
        client.get.assert_called_once_with(f"/applications/{APP_ID}/secrets")

    def test_list_secrets_missing_key(self, client):
        client.get.return_value = {}
        assert ApplicationsAPI(client).list_secrets(APP_ID) == []

    def test_set_secrets_posts_key_value_pairs(self, client):
        client.post.return_value = {"created": ["pw"], "updated": []}
        result = ApplicationsAPI(client).set_secrets(APP_ID, {"pw": "hunter2"})
        assert result == {"created": ["pw"], "updated": []}
        client.post.assert_called_once_with(
            f"/applications/{APP_ID}/secrets",
            json_body={"secrets": [{"key": "pw", "value": "hunter2"}]},
        )

    def test_delete_secret_sends_secret_key_in_body(self, client):
        ApplicationsAPI(client).delete_secret(APP_ID, "pw")
        client._request.assert_called_once_with(
            "DELETE", f"/applications/{APP_ID}/secrets", json={"secret_key": "pw"}
        )


DATASET_ID = "0190a000-0000-7000-8000-00000000d5e7"
DATASET = {
    "dataset_id": DATASET_ID, "name": "customers", "description": "",
    "columns": ["email", "role"], "rows": [["a@x.test", "admin"]],
    "created_at": "t", "updated_at": "t", "created_by": "qa@example.com",
}


class TestDatasets:
    def test_list_datasets_unwraps_datasets_key(self, client):
        rows = [{"dataset_id": DATASET_ID, "name": "customers", "description": "",
                 "column_count": 2, "row_count": 1, "updated_at": "t"}]
        client.get.return_value = {"datasets": rows}
        assert ApplicationsAPI(client).list_datasets(APP_ID) == rows
        client.get.assert_called_once_with(f"/applications/{APP_ID}/datasets")

    def test_list_datasets_missing_key(self, client):
        client.get.return_value = {}
        assert ApplicationsAPI(client).list_datasets(APP_ID) == []

    def test_get_dataset_unwraps_dataset_key(self, client):
        client.get.return_value = {"dataset": DATASET}
        assert ApplicationsAPI(client).get_dataset(APP_ID, DATASET_ID) == DATASET
        client.get.assert_called_once_with(f"/applications/{APP_ID}/datasets/{DATASET_ID}")

    def test_create_dataset_posts_body_and_unwraps(self, client):
        body = {"name": "customers", "description": "", "columns": ["email"], "rows": [["a@x.test"]]}
        client.post.return_value = {"dataset": DATASET}
        assert ApplicationsAPI(client).create_dataset(APP_ID, body) == DATASET
        client.post.assert_called_once_with(f"/applications/{APP_ID}/datasets", json_body=body)

    def test_update_dataset_puts_full_body_and_unwraps(self, client):
        body = {"name": "customers", "description": "d", "columns": ["email"], "rows": [["a@x.test"]]}
        client.put.return_value = {"dataset": DATASET}
        assert ApplicationsAPI(client).update_dataset(APP_ID, DATASET_ID, body) == DATASET
        client.put.assert_called_once_with(f"/applications/{APP_ID}/datasets/{DATASET_ID}", json_body=body)

    def test_delete_dataset(self, client):
        client.delete.return_value = None
        assert ApplicationsAPI(client).delete_dataset(APP_ID, DATASET_ID) is None
        client.delete.assert_called_once_with(f"/applications/{APP_ID}/datasets/{DATASET_ID}")
