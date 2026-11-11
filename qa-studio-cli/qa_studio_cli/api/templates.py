"""Template API operations (``/templates``, ``/templates/{id}[/usages]``, ``/usecase/{id}/import-template``)."""

from typing import Any, Dict, List, Optional

from qa_studio_cli.api.client import ApiClient

#: ``insert_position`` value the server treats as "append".
APPEND_POSITION = -1


class TemplateAPI:
    """Template API operations.

    Response bodies are snake_case (DynamoDB items); these methods return the
    raw dicts / lists and the commands decide typing via ``models.api``.
    """

    def __init__(self, client: ApiClient):
        self.client = client

    def list_templates(self) -> List[Dict[str, Any]]:
        """``GET /templates`` → the ``templates`` list."""
        response = self.client.get("/templates")
        return response.get("templates", []) or []

    def get_template(self, template_id: str) -> Dict[str, Any]:
        """``GET /templates/{id}`` → template metadata (404 → ``ApiError``)."""
        return self.client.get(f"/templates/{template_id}")

    def list_steps(self, template_id: str) -> List[Dict[str, Any]]:
        """``GET /templates/{id}/steps`` → steps sorted by ``sort``."""
        response = self.client.get(f"/templates/{template_id}/steps")
        steps = response.get("steps", []) or []
        return sorted(steps, key=lambda s: int(s.get("sort", 0) or 0))

    def get_variables(self, template_id: str) -> List[Dict[str, Any]]:
        """``GET /templates/{id}/variables`` → the ``variables`` list (empty when none)."""
        response = self.client.get(f"/templates/{template_id}/variables")
        return response.get("variables", []) or []

    def import_template(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """``POST /templates/import`` with a template-file payload → ``{id, name, stepsCreated}``."""
        return self.client.post("/templates/import", json_body=payload)

    def replace_template(self, template_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """``PUT /templates/{id}`` with a template-file payload (steps matched by ``id``).

        → ``{id, name, version, stepsCreated, stepsUpdated, stepsDeleted}``.
        """
        return self.client.put(f"/templates/{template_id}", json_body=payload)

    def delete_template(self, template_id: str) -> None:
        """``DELETE /templates/{id}`` → ``204`` (linked use-case steps are kept, unlinked)."""
        self.client.delete(f"/templates/{template_id}")

    def get_usages(self, template_id: str) -> List[Dict[str, Any]]:
        """``GET /templates/{id}/usages`` → the ``usages`` list (``{usecase_id, name}`` each)."""
        response = self.client.get(f"/templates/{template_id}/usages")
        return response.get("usages", []) or []

    def insert_into_usecase(
        self, usecase_id: str, template_id: str, position: Optional[int]
    ) -> Dict[str, Any]:
        """``POST /usecase/{id}/import-template``.

        ``position`` is 1-based (the template's first step becomes step N);
        ``None`` appends.
        """
        return self.client.post(
            f"/usecase/{usecase_id}/import-template",
            json_body={
                "template_id": template_id,
                "insert_position": APPEND_POSITION if position is None else position,
            },
        )
