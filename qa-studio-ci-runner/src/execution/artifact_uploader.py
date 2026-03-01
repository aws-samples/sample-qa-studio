"""Upload artifacts to S3 via presigned URLs."""

import asyncio
import logging
import requests
from pathlib import Path
from typing import Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

from ..api.client import APIClient

logger = logging.getLogger(__name__)


class ArtifactUploader:
    """Upload artifacts to S3 via presigned URLs."""
    
    def __init__(self, api_client: APIClient):
        """
        Initialize artifact uploader.
        
        Args:
            api_client: API client for requesting presigned URLs
        """
        self.api_client = api_client
    
    async def upload_execution_artifacts(
        self,
        usecase_id: str,
        execution_id: str,
        artifacts: Dict[str, Path]
    ):
        """
        Upload execution-level artifacts.
        
        Args:
            usecase_id: Usecase UUID
            execution_id: Execution UUID
            artifacts: Dict mapping artifact type to file path
        """
        for artifact_type, artifact_path in artifacts.items():
            try:
                await self._upload_execution_artifact(
                    usecase_id=usecase_id,
                    execution_id=execution_id,
                    artifact_type=artifact_type,
                    artifact_path=artifact_path
                )
                logger.info(f"Uploaded {artifact_type} artifact for execution {execution_id}")
            except Exception as e:
                logger.error(f"Failed to upload {artifact_type} artifact: {e}")
                # Don't raise - continue with other artifacts
    
    async def upload_step_artifacts(
        self,
        usecase_id: str,
        execution_id: str,
        step_id: str,
        artifacts: Dict[str, Path]
    ):
        """
        Upload step-level artifacts.
        
        Args:
            usecase_id: Usecase UUID
            execution_id: Execution UUID
            step_id: Step UUID
            artifacts: Dict mapping artifact type to file path
        """
        for artifact_type, artifact_path in artifacts.items():
            try:
                await self._upload_step_artifact(
                    usecase_id=usecase_id,
                    execution_id=execution_id,
                    step_id=step_id,
                    artifact_type=artifact_type,
                    artifact_path=artifact_path
                )
                logger.debug(f"Uploaded {artifact_type} artifact for step {step_id}")
            except Exception as e:
                logger.warning(f"Failed to upload {artifact_type} artifact for step: {e}")
                # Don't raise - continue with other artifacts
    async def upload_suite_artifacts(
        self,
        suite_id: str,
        suite_execution_id: str,
        artifacts: dict[str, Path],
    ) -> None:
        """
        Upload suite-level artifacts via the suite artifact endpoint.

        Args:
            suite_id: Suite UUID
            suite_execution_id: Suite execution UUID
            artifacts: Dict mapping artifact type to file path
        """
        for artifact_type, artifact_path in artifacts.items():
            try:
                await self._upload_suite_artifact(
                    suite_id=suite_id,
                    suite_execution_id=suite_execution_id,
                    artifact_type=artifact_type,
                    artifact_path=artifact_path,
                )
                logger.info(f"Uploaded suite {artifact_type} artifact")
            except Exception as e:
                logger.error(f"Failed to upload suite {artifact_type} artifact: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _upload_suite_artifact(
        self,
        suite_id: str,
        suite_execution_id: str,
        artifact_type: str,
        artifact_path: Path,
    ) -> None:
        """
        Upload single suite-level artifact with retry.

        No DynamoDB confirm step — S3-direct storage.

        Args:
            suite_id: Suite UUID
            suite_execution_id: Suite execution UUID
            artifact_type: Type of artifact (e.g. logs)
            artifact_path: Path to artifact file

        Raises:
            Exception: If all retries fail
        """
        response = await asyncio.to_thread(
            self.api_client.post,
            f"/test-suites/{suite_id}/executions/{suite_execution_id}/artifacts",
            {
                'type': artifact_type,
                'filename': artifact_path.name,
                'content_type': self._get_content_type(artifact_path),
            },
        )

        upload_url = response['upload_url']

        with open(artifact_path, 'rb') as f:
            upload_response = await asyncio.to_thread(
                requests.put,
                upload_url,
                data=f,
                headers={'Content-Type': self._get_content_type(artifact_path)},
            )
            upload_response.raise_for_status()

    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _upload_execution_artifact(
        self,
        usecase_id: str,
        execution_id: str,
        artifact_type: str,
        artifact_path: Path,
        relative_path: str = None
    ):
        """
        Upload single execution-level artifact with retry.
        
        Args:
            usecase_id: Usecase UUID
            execution_id: Execution UUID
            artifact_type: Type of artifact (recording, logs, trace)
            artifact_path: Path to artifact file
            relative_path: Optional relative path to preserve directory structure in S3
            
        Raises:
            Exception: If all retries fail
        """
        # Build request payload
        payload = {
            'type': artifact_type,
            'filename': artifact_path.name,
            'content_type': self._get_content_type(artifact_path)
        }
        if relative_path:
            payload['path'] = relative_path
        
        # Get presigned URL from API
        response = await asyncio.to_thread(
            self.api_client.post,
            f"/usecase/{usecase_id}/executions/{execution_id}/artifacts",
            payload
        )
        
        upload_url = response['upload_url']
        artifact_id = response.get('artifact_id')
        
        # Upload to S3
        with open(artifact_path, 'rb') as f:
            upload_response = await asyncio.to_thread(
                requests.put,
                upload_url,
                data=f,
                headers={'Content-Type': self._get_content_type(artifact_path)}
            )
            upload_response.raise_for_status()
        
        # Confirm upload in DynamoDB
        if artifact_id:
            try:
                await asyncio.to_thread(
                    self.api_client.patch,
                    f"/usecase/{usecase_id}/executions/{execution_id}/artifacts/{artifact_id}",
                    {}
                )
            except Exception as e:
                logger.warning(f"Failed to confirm artifact upload: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _upload_step_artifact(
        self,
        usecase_id: str,
        execution_id: str,
        step_id: str,
        artifact_type: str,
        artifact_path: Path
    ):
        """
        Upload single step-level artifact with retry.
        
        Args:
            usecase_id: Usecase UUID
            execution_id: Execution UUID
            step_id: Step UUID
            artifact_type: Type of artifact (screenshot, trace)
            artifact_path: Path to artifact file
            
        Raises:
            Exception: If all retries fail
        """
        # Get presigned URL from API
        response = await asyncio.to_thread(
            self.api_client.post,
            f"/usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/artifacts",
            {
                'filename': artifact_path.name,
                'content_type': self._get_content_type(artifact_path)
            }
        )
        
        upload_url = response['upload_url']
        artifact_id = response.get('artifact_id')
        
        # Upload to S3
        with open(artifact_path, 'rb') as f:
            upload_response = await asyncio.to_thread(
                requests.put,
                upload_url,
                data=f,
                headers={'Content-Type': self._get_content_type(artifact_path)}
            )
            upload_response.raise_for_status()
        
        # Confirm upload in DynamoDB
        if artifact_id:
            try:
                await asyncio.to_thread(
                    self.api_client.patch,
                    f"/usecase/{usecase_id}/executions/{execution_id}/artifacts/{artifact_id}",
                    {}
                )
            except Exception as e:
                logger.warning(f"Failed to confirm step artifact upload: {e}")
    
    @staticmethod
    def _get_content_type(path: Path) -> str:
        """
        Get content type based on file extension.
        
        Args:
            path: File path
            
        Returns:
            MIME type string
        """
        extension = path.suffix.lower()
        content_types = {
            '.webm': 'video/webm',
            '.txt': 'text/plain',
            '.png': 'image/png',
            '.json': 'application/json',
            '.html': 'text/html'
        }
        return content_types.get(extension, 'application/octet-stream')
