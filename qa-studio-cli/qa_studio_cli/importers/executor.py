"""Import execution and secrets handling for test case import."""

import copy
import logging
from dataclasses import dataclass, field
from typing import Optional

from qa_studio_cli.api.client import ApiClient
from qa_studio_cli.importers.scanner import ScanResult
from qa_studio_cli.models.api import ImportUsecaseResponse
from qa_studio_cli.models.errors import ApiError
from qa_studio_cli.utils.url import apply_base_url_override

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Result of importing a single file."""

    file_name: str
    success: bool
    usecase_id: str = ""
    error_message: str = ""
    missing_secrets: list[str] = field(default_factory=list)


def import_single(
    client: ApiClient,
    scan_result: ScanResult,
    base_url: Optional[str] = None,
    region: Optional[str] = None,
) -> ImportResult:
    """Send a single validated payload to POST /api/import."""
    payload_dict = scan_result.payload.model_dump(by_alias=False)

    if base_url:
        original_url = payload_dict["usecase"].get("starting_url", "")
        payload_dict["usecase"]["starting_url"] = apply_base_url_override(original_url, base_url) if original_url else base_url

    if region:
        payload_dict["regionOverride"] = region

    try:
        data = client.post("/api/import", json_body=payload_dict)
        response = ImportUsecaseResponse.model_validate(data)

        if not response.success:
            return ImportResult(
                file_name=scan_result.file_name,
                success=False,
                error_message=response.message or "Import failed",
            )

        missing = data.get("missingSecrets", [])
        return ImportResult(
            file_name=scan_result.file_name,
            success=True,
            usecase_id=response.usecase_id,
            missing_secrets=missing,
        )
    except ApiError as e:
        return ImportResult(
            file_name=scan_result.file_name,
            success=False,
            error_message=str(e),
        )
    except Exception as e:
        return ImportResult(
            file_name=scan_result.file_name,
            success=False,
            error_message=f"Unexpected error: {e}",
        )


def set_secret_value(
    client: ApiClient,
    usecase_id: str,
    secret_key: str,
    secret_value: str,
) -> bool:
    """Set a secret value via POST /api/usecase/{id}/secrets (create/update)."""
    try:
        client.post(
            f"/api/usecase/{usecase_id}/secrets",
            json_body={"secrets": [{"key": secret_key, "value": secret_value}]},
        )
        return True
    except Exception as e:
        logger.warning(
            "Failed to set secret '%s' for usecase %s: %s",
            secret_key, usecase_id, e,
        )
        return False


def execute_imports(
    client: ApiClient,
    valid_results: list[ScanResult],
    base_url: Optional[str] = None,
    region: Optional[str] = None,
    secret_values: Optional[dict[str, dict[str, str]]] = None,
) -> list[ImportResult]:
    """Import all valid files sequentially, set secrets if provided.

    Args:
        client: Authenticated API client.
        valid_results: List of valid ScanResults to import.
        base_url: Optional base URL override for all imports.
        region: Optional executing region override for all imports.
        secret_values: Optional dict mapping file_name -> {secret_key: value}.
    """
    results: list[ImportResult] = []

    for scan_result in valid_results:
        result = import_single(client, scan_result, base_url=base_url, region=region)
        results.append(result)

        # Set secret values if import succeeded and values provided
        if result.success and secret_values:
            file_secrets = secret_values.get(scan_result.file_name, {})
            for key, value in file_secrets.items():
                set_secret_value(client, result.usecase_id, key, value)

    return results
