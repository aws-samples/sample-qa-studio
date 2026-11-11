"""Application configuration API (``/applications/{id}/{variables,secrets,datasets}``).

Application-level variables and secrets are inherited by every use case of
the application (precedence: application < use case < CLI run override);
datasets are referenced by repeat steps through ``dataset_id``.
Reads need the ``api/applications.read`` scope, writes ``api/applications.write``.
"""

from typing import Any, Dict, List, Mapping

from qa_studio_cli.api.client import ApiClient

READ_SCOPE = "api/applications.read"
WRITE_SCOPE = "api/applications.write"


class ApplicationsAPI:
    """Application configuration operations.

    Response bodies are snake_case (DynamoDB items); these methods return the
    raw dicts / lists and the commands decide how to render them.
    """

    def __init__(self, client: ApiClient):
        self.client = client

    # -- variables ----------------------------------------------------------

    def get_variables(self, app_id: str) -> List[Dict[str, Any]]:
        """``GET /applications/{id}/variables`` → the ``variables`` list (empty when none)."""
        response = self.client.get(f"/applications/{app_id}/variables")
        return response.get("variables", []) or []

    def put_variables(self, app_id: str, variables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """``POST /applications/{id}/variables`` — replaces the whole list → the stored list."""
        response = self.client.post(f"/applications/{app_id}/variables", json_body={"variables": variables})
        return response.get("variables", []) or []

    # -- secrets ------------------------------------------------------------

    def list_secrets(self, app_id: str) -> List[Dict[str, Any]]:
        """``GET /applications/{id}/secrets`` → ``[{key, secret_name, description, created_at}]`` (never values)."""
        response = self.client.get(f"/applications/{app_id}/secrets")
        return response.get("secrets", []) or []

    def set_secrets(self, app_id: str, secrets: Mapping[str, str]) -> Dict[str, List[str]]:
        """``POST /applications/{id}/secrets`` create-or-update → ``{created: [keys], updated: [keys]}``."""
        return self.client.post(
            f"/applications/{app_id}/secrets",
            json_body={"secrets": [{"key": key, "value": value} for key, value in secrets.items()]},
        )

    def delete_secret(self, app_id: str, key: str) -> None:
        """``DELETE /applications/{id}/secrets`` with body ``{secret_key}`` → ``204``.

        ``ApiClient.delete`` takes no body (the other DELETE routes are
        path-only), so this goes through the shared request method directly.
        """
        self.client._request("DELETE", f"/applications/{app_id}/secrets", json={"secret_key": key})

    # -- datasets -----------------------------------------------------------

    def list_datasets(self, app_id: str) -> List[Dict[str, Any]]:
        """``GET /applications/{id}/datasets`` → summary rows
        ``[{dataset_id, name, description, column_count, row_count, updated_at}]``."""
        response = self.client.get(f"/applications/{app_id}/datasets")
        return response.get("datasets", []) or []

    def get_dataset(self, app_id: str, dataset_id: str) -> Dict[str, Any]:
        """``GET /applications/{id}/datasets/{datasetId}`` → the full dataset with ``columns`` / ``rows``."""
        response = self.client.get(f"/applications/{app_id}/datasets/{dataset_id}")
        return response.get("dataset", response)

    def create_dataset(self, app_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """``POST /applications/{id}/datasets`` with ``{name, description?, columns, rows}`` → ``201 {dataset}``."""
        response = self.client.post(f"/applications/{app_id}/datasets", json_body=payload)
        return response.get("dataset", response)

    def update_dataset(self, app_id: str, dataset_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """``PUT /applications/{id}/datasets/{datasetId}`` — full replace → ``200 {dataset}``."""
        response = self.client.put(f"/applications/{app_id}/datasets/{dataset_id}", json_body=payload)
        return response.get("dataset", response)

    def delete_dataset(self, app_id: str, dataset_id: str) -> None:
        """``DELETE /applications/{id}/datasets/{datasetId}`` → ``204``.

        ``409`` (``ApiError`` with ``response_data.usecases``) when repeat steps reference it.
        """
        self.client.delete(f"/applications/{app_id}/datasets/{dataset_id}")
