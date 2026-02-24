# Work Package 4: Artifact Management

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP4 - Artifact Management
- **Estimated Duration**: 4 days
- **Dependencies**: WP1c (Artifact Presigned URL Endpoints), WP3 (Execution Engine)
- **Status**: Not Started

---

## Overview

Implement artifact capture (videos, traces, logs, screenshots) during test execution and upload them to S3 using presigned URLs obtained from the API. Artifacts are associated with executions and steps for later viewing in the platform UI.

---

## User Stories

### US1: As a CI/CD runner, I need to capture execution recordings
**Acceptance Criteria**:
- Runner captures video recording of entire test execution
- Recording is saved in WebM format
- Recording includes all browser interactions
- Recording is captured even if test fails

### US2: As a CI/CD runner, I need to capture execution logs
**Acceptance Criteria**:
- Runner captures all execution logs (info, warnings, errors)
- Logs include timestamps and log levels
- Logs are saved as plain text file
- Logs include Nova Act SDK output

### US3: As a CI/CD runner, I need to capture step-level artifacts
**Acceptance Criteria**:
- Runner captures screenshot after each step
- Runner captures trace data for each step
- Screenshots are saved in PNG format
- Traces are saved in JSON format

### US4: As a CI/CD runner, I need to upload artifacts to S3
**Acceptance Criteria**:
- Runner requests presigned URLs from API
- Runner uploads artifacts directly to S3
- Upload failures are retried with exponential backoff
- Upload errors are logged but don't fail the test
- Artifacts are associated with correct execution/step

---

## Technical Requirements

### Artifact Types

**Execution-Level Artifacts**:
- `recording.webm` - Video recording of entire execution
- `logs.txt` - Execution logs

**Step-Level Artifacts**:
- `screenshot.png` - Screenshot after step execution
- `trace.json` - Playwright trace data for step

### Artifact Capture

**Nova Act SDK Configuration**:
```python
client = NovaActClient(
    region=region,
    model_id=model_id,
    recording=True,  # Enable video recording
    tracing=True     # Enable trace capture
)
```

---

## Implementation Details

### 1. Artifact Capture

**File**: `src/execution/artifacts.py`

```python
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ArtifactCapture:
    """Capture artifacts during test execution."""
    
    def __init__(self, execution_id: str, temp_dir: Path):
        self.execution_id = execution_id
        self.temp_dir = temp_dir / execution_id
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        self.recording_path = None
        self.log_path = None
        self.step_artifacts = {}
    
    def setup_recording(self) -> Path:
        """Setup video recording path."""
        self.recording_path = self.temp_dir / "recording.webm"
        return self.recording_path
    
    def setup_logs(self) -> Path:
        """Setup log file path."""
        self.log_path = self.temp_dir / "logs.txt"
        
        # Create file handler for this execution
        file_handler = logging.FileHandler(self.log_path)
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        
        # Add handler to root logger
        logging.getLogger().addHandler(file_handler)
        
        return self.log_path
    
    async def capture_step_screenshot(
        self,
        session,
        step_id: str,
        step_number: int
    ) -> Optional[Path]:
        """Capture screenshot after step execution."""
        try:
            screenshot_path = self.temp_dir / f"step_{step_number}_screenshot.png"
            await session.screenshot(path=str(screenshot_path))
            
            self.step_artifacts[step_id] = {
                'screenshot': screenshot_path
            }
            
            logger.debug(f"Captured screenshot for step {step_number}")
            return screenshot_path
            
        except Exception as e:
            logger.warning(f"Failed to capture screenshot for step {step_number}: {e}")
            return None
    
    async def capture_step_trace(
        self,
        session,
        step_id: str,
        step_number: int
    ) -> Optional[Path]:
        """Capture trace data for step."""
        try:
            trace_path = self.temp_dir / f"step_{step_number}_trace.json"
            await session.save_trace(path=str(trace_path))
            
            if step_id not in self.step_artifacts:
                self.step_artifacts[step_id] = {}
            self.step_artifacts[step_id]['trace'] = trace_path
            
            logger.debug(f"Captured trace for step {step_number}")
            return trace_path
            
        except Exception as e:
            logger.warning(f"Failed to capture trace for step {step_number}: {e}")
            return None
    
    def get_execution_artifacts(self) -> Dict[str, Path]:
        """Get paths to execution-level artifacts."""
        artifacts = {}
        
        if self.recording_path and self.recording_path.exists():
            artifacts['recording'] = self.recording_path
        
        if self.log_path and self.log_path.exists():
            artifacts['logs'] = self.log_path
        
        return artifacts
    
    def get_step_artifacts(self, step_id: str) -> Dict[str, Path]:
        """Get paths to step-level artifacts."""
        return self.step_artifacts.get(step_id, {})
    
    def cleanup(self):
        """Clean up temporary artifact files."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
```

### 2. Artifact Upload

**File**: `src/execution/artifact_uploader.py`

```python
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
        self.api_client = api_client
    
    async def upload_execution_artifacts(
        self,
        usecase_id: str,
        execution_id: str,
        artifacts: Dict[str, Path]
    ):
        """Upload execution-level artifacts."""
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
    
    async def upload_step_artifacts(
        self,
        usecase_id: str,
        execution_id: str,
        step_id: str,
        artifacts: Dict[str, Path]
    ):
        """Upload step-level artifacts."""
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
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _upload_execution_artifact(
        self,
        usecase_id: str,
        execution_id: str,
        artifact_type: str,
        artifact_path: Path
    ):
        """Upload single execution-level artifact with retry."""
        # Get presigned URL
        response = self.api_client.post(
            f"/usecase/{usecase_id}/executions/{execution_id}/artifacts",
            data={
                'type': artifact_type,
                'filename': artifact_path.name,
                'content_type': self._get_content_type(artifact_path)
            }
        )
        
        upload_url = response['upload_url']
        
        # Upload to S3
        with open(artifact_path, 'rb') as f:
            upload_response = requests.put(
                upload_url,
                data=f,
                headers={'Content-Type': self._get_content_type(artifact_path)}
            )
            upload_response.raise_for_status()
    
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
        """Upload single step-level artifact with retry."""
        # Get presigned URL
        response = self.api_client.post(
            f"/usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/artifacts",
            data={
                'filename': artifact_path.name,
                'content_type': self._get_content_type(artifact_path)
            }
        )
        
        upload_url = response['upload_url']
        
        # Upload to S3
        with open(artifact_path, 'rb') as f:
            upload_response = requests.put(
                upload_url,
                data=f,
                headers={'Content-Type': self._get_content_type(artifact_path)}
            )
            upload_response.raise_for_status()
    
    @staticmethod
    def _get_content_type(path: Path) -> str:
        """Get content type based on file extension."""
        extension = path.suffix.lower()
        content_types = {
            '.webm': 'video/webm',
            '.txt': 'text/plain',
            '.png': 'image/png',
            '.json': 'application/json'
        }
        return content_types.get(extension, 'application/octet-stream')
```

### 3. Integration with Execution Engine

**File**: `src/execution/engine.py` (updated)

```python
async def execute_usecase(self, execution: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a single use case with artifact capture."""
    execution_id = execution['execution_id']
    usecase_id = execution['usecase_id']
    
    # Setup artifact capture
    artifact_capture = ArtifactCapture(execution_id, Path('/tmp/artifacts'))
    artifact_capture.setup_recording()
    artifact_capture.setup_logs()
    
    # Setup artifact uploader
    artifact_uploader = ArtifactUploader(self.api_client)
    
    try:
        # Execute with Nova Act SDK
        result = await self._execute_with_nova_act(
            execution_details,
            artifact_capture
        )
        
        # Upload execution-level artifacts
        execution_artifacts = artifact_capture.get_execution_artifacts()
        await artifact_uploader.upload_execution_artifacts(
            usecase_id=usecase_id,
            execution_id=execution_id,
            artifacts=execution_artifacts
        )
        
        return result
        
    finally:
        # Cleanup temporary files
        artifact_capture.cleanup()

async def _execute_step(
    self,
    session,
    step: Dict[str, Any],
    variables: Dict[str, str],
    artifact_capture: ArtifactCapture,
    artifact_uploader: ArtifactUploader,
    usecase_id: str,
    execution_id: str
):
    """Execute a single test step with artifact capture."""
    step_id = step['step_id']
    step_number = step['step_number']
    
    # Execute step
    instruction = self._replace_variables(step['instruction'], variables)
    result = await session.execute(instruction)
    
    if not result.success:
        raise ExecutionError(f"Step failed: {result.error}")
    
    # Capture step artifacts
    await artifact_capture.capture_step_screenshot(session, step_id, step_number)
    await artifact_capture.capture_step_trace(session, step_id, step_number)
    
    # Upload step artifacts
    step_artifacts = artifact_capture.get_step_artifacts(step_id)
    await artifact_uploader.upload_step_artifacts(
        usecase_id=usecase_id,
        execution_id=execution_id,
        step_id=step_id,
        artifacts=step_artifacts
    )
```

---

## Testing Requirements

### Unit Tests
- Test artifact capture setup
- Test screenshot capture
- Test trace capture
- Test log file creation
- Test presigned URL request
- Test S3 upload with retry logic
- Test content type detection

### Integration Tests
- Execute test and capture all artifacts
- Upload artifacts to S3
- Verify artifacts exist in S3
- Test artifact upload retry on failure
- Test artifact cleanup after upload

---

## Error Handling

- Artifact capture failures are logged but don't fail the test
- Upload failures are retried 3 times with exponential backoff
- If all retries fail, log error and continue
- Temporary files are always cleaned up (even on error)

---

## Success Criteria

- [ ] Video recordings captured for all executions
- [ ] Execution logs captured
- [ ] Screenshots captured for each step
- [ ] Traces captured for each step
- [ ] Artifacts uploaded to S3 via presigned URLs
- [ ] Upload retry logic working
- [ ] Temporary files cleaned up
- [ ] Unit test coverage ≥ 70%
- [ ] Integration tests pass
- [ ] Artifacts visible in platform UI
