"""Upload artifacts to S3 via presigned URLs."""

import asyncio
import logging
from pathlib import Path
from typing import Dict

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from qa_studio_cli.api.client import ApiClient

logger = logging.getLogger(__name__)


class ArtifactUploader:
    """Upload artifacts to S3 via presigned URLs."""

    def __init__(self, api_client: ApiClient):
        self.api_client = api_client

    async def upload_execution_artifacts(
        self,
        usecase_id: str,
        execution_id: str,
        artifacts: Dict[str, Path],
    ):
        """Upload execution-level artifacts."""
        for artifact_type, artifact_path in artifacts.items():
            try:
                await self._upload_execution_artifact(
                    usecase_id=usecase_id,
                    execution_id=execution_id,
                    artifact_type=artifact_type,
                    artifact_path=artifact_path,
                )
                logger.info("Uploaded %s artifact for execution %s", artifact_type, execution_id)
            except Exception as e:
                logger.error("Failed to upload %s artifact: %s", artifact_type, e)

    async def upload_step_artifacts(
        self,
        usecase_id: str,
        execution_id: str,
        step_id: str,
        artifacts: Dict[str, Path],
    ):
        """Upload step-level artifacts."""
        for artifact_type, artifact_path in artifacts.items():
            try:
                await self._upload_step_artifact(
                    usecase_id=usecase_id,
                    execution_id=execution_id,
                    step_id=step_id,
                    artifact_type=artifact_type,
                    artifact_path=artifact_path,
                )
                logger.debug("Uploaded %s artifact for step %s", artifact_type, step_id)
            except Exception as e:
                logger.warning("Failed to upload %s artifact for step: %s", artifact_type, e)

    async def upload_suite_artifacts(
        self,
        suite_id: str,
        suite_execution_id: str,
        artifacts: dict[str, Path],
    ) -> None:
        """Upload suite-level artifacts."""
        for artifact_type, artifact_path in artifacts.items():
            try:
                await self._upload_suite_artifact(
                    suite_id=suite_id,
                    suite_execution_id=suite_execution_id,
                    artifact_type=artifact_type,
                    artifact_path=artifact_path,
                )
                logger.info("Uploaded suite %s artifact", artifact_type)
            except Exception as e:
                logger.error("Failed to upload suite %s artifact: %s", artifact_type, e)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _upload_suite_artifact(
        self,
        suite_id: str,
        suite_execution_id: str,
        artifact_type: str,
        artifact_path: Path,
    ) -> None:
        """Upload single suite-level artifact with retry."""
        response = await asyncio.to_thread(
            self.api_client.post,
            f"/api/test-suites/{suite_id}/executions/{suite_execution_id}/artifacts",
            json_body={
                "type": artifact_type,
                "filename": artifact_path.name,
                "content_type": self._get_content_type(artifact_path),
            },
        )
        upload_url = response["upload_url"]
        with open(artifact_path, "rb") as f:
            upload_response = await asyncio.to_thread(
                requests.put,
                upload_url,
                data=f,
                headers={"Content-Type": self._get_content_type(artifact_path)},
            )
            upload_response.raise_for_status()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _upload_execution_artifact(
        self,
        usecase_id: str,
        execution_id: str,
        artifact_type: str,
        artifact_path: Path,
        relative_path: str = None,
    ):
        """Upload single execution-level artifact with retry."""
        payload = {
            "type": artifact_type,
            "filename": artifact_path.name,
            "content_type": self._get_content_type(artifact_path),
        }
        if relative_path:
            payload["path"] = relative_path

        response = await asyncio.to_thread(
            self.api_client.post,
            f"/api/usecase/{usecase_id}/executions/{execution_id}/artifacts",
            json_body=payload,
        )
        upload_url = response["upload_url"]
        artifact_id = response.get("artifact_id")

        with open(artifact_path, "rb") as f:
            upload_response = await asyncio.to_thread(
                requests.put,
                upload_url,
                data=f,
                headers={"Content-Type": self._get_content_type(artifact_path)},
            )
            upload_response.raise_for_status()

        if artifact_id:
            try:
                await asyncio.to_thread(
                    self.api_client.patch,
                    f"/api/usecase/{usecase_id}/executions/{execution_id}/artifacts/{artifact_id}",
                    json_body={},
                )
            except Exception as e:
                logger.warning("Failed to confirm artifact upload: %s", e)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _upload_step_artifact(
        self,
        usecase_id: str,
        execution_id: str,
        step_id: str,
        artifact_type: str,
        artifact_path: Path,
    ):
        """Upload single step-level artifact with retry."""
        response = await asyncio.to_thread(
            self.api_client.post,
            f"/api/usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/artifacts",
            json_body={
                "filename": artifact_path.name,
                "content_type": self._get_content_type(artifact_path),
            },
        )
        upload_url = response["upload_url"]
        artifact_id = response.get("artifact_id")

        with open(artifact_path, "rb") as f:
            upload_response = await asyncio.to_thread(
                requests.put,
                upload_url,
                data=f,
                headers={"Content-Type": self._get_content_type(artifact_path)},
            )
            upload_response.raise_for_status()

        if artifact_id:
            try:
                await asyncio.to_thread(
                    self.api_client.patch,
                    f"/api/usecase/{usecase_id}/executions/{execution_id}/artifacts/{artifact_id}",
                    json_body={},
                )
            except Exception as e:
                logger.warning("Failed to confirm step artifact upload: %s", e)

    @staticmethod
    def _get_content_type(path: Path) -> str:
        """Get content type based on file extension."""
        content_types = {
            ".webm": "video/webm",
            ".txt": "text/plain",
            ".png": "image/png",
            ".json": "application/json",
            ".html": "text/html",
        }
        return content_types.get(path.suffix.lower(), "application/octet-stream")
