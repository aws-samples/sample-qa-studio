# Work Package 4: Artifact Management - Design Document

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP4 - Artifact Management
- **Version**: 1.0
- **Status**: Design Phase
- **Dependencies**: WP1c (Artifact Presigned URL Endpoints), WP3 (Execution Engine)

---

## Design Overview

This workpackage implements artifact capture (videos, traces, logs, screenshots) during test execution and uploads them to S3 using presigned URLs obtained from the API. Artifacts are associated with executions and steps for later viewing in the platform UI.

### Key Design Principles
1. **Comprehensive Capture**: Capture all artifact types (recording, logs, screenshots, traces)
2. **Fault Tolerance**: Artifact failures don't fail tests - log errors and continue
3. **Direct S3 Upload**: Use presigned URLs to upload directly to S3
4. **Retry Logic**: Retry failed uploads with exponential backoff
5. **Clean Temporary Storage**: Always clean up temporary files after upload

---

## Architecture

### High-Level Flow

```
ExecutionEngine
    ↓
1. Setup artifact capture (recording, logs)
2. Execute test with Nova Act SDK
3. Capture step artifacts (screenshot, trace) after each step
4. Upload step artifacts immediately
5. After execution completes, upload execution artifacts
6. Clean up temporary files
```

### Component Interaction

```
┌─────────────────────────────────────────────────┐
│         ExecutionEngine                          │
│                                                  │
│  1. Create ArtifactCapture                      │
│  2. Setup recording & logs                      │
│  3. Execute with Nova Act                       │
│  4. For each step:                              │
│     - Capture screenshot & trace                │
│     - Upload via ArtifactUploader               │
│  5. Upload execution artifacts                  │
│  6. Cleanup temporary files                     │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│         ArtifactCapture                          │
│                                                  │
│  - setup_recording() → Path                     │
│  - setup_logs() → Path                          │
│  - capture_step_screenshot() → Path             │
│  - capture_step_trace() → Path                  │
│  - get_execution_artifacts() → Dict             │
│  - get_step_artifacts() → Dict                  │
│  - cleanup()                                     │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│         ArtifactUploader                         │
│                                                  │
│  - upload_execution_artifacts()                 │
│  - upload_step_artifacts()                      │
│  - _upload_execution_artifact() [with retry]    │
│  - _upload_step_artifact() [with retry]         │
│  - _get_content_type()                          │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│         Platform API                             │
│                                                  │
│  POST /usecase/{id}/executions/{id}/artifacts   │
│  POST /usecase/{id}/executions/{id}/steps/      │
│       {id}/artifacts                             │
│                                                  │
│  Returns: presigned S3 URL                      │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│         S3 Bucket                                │
│                                                  │
│  PUT to presigned URL                           │
│  Stores artifact file                           │
└─────────────────────────────────────────────────┘
```

---

## Components and Interfaces

### 1. Artifact Capture (`src/execution/artifacts.py`)

**Purpose**: Capture artifacts during test execution and manage temporary storage.

**Class Definition**:

```python
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ArtifactCapture:
    """Capture artifacts during test execution."""
    
    def __init__(self, execution_id: str, temp_dir: Path):
        """
        Initialize artifact capture.
        
        Args:
            execution_id: Execution UUID
            temp_dir: Base temporary directory for artifacts
        """
        self.execution_id = execution_id
        self.temp_dir = temp_dir / execution_id
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        self.recording_path = None
        self.log_path = None
        self.step_artifacts = {}
    
    def setup_recording(self) -> Path:
        """
        Setup video recording path.
        
        Returns:
            Path to recording file
        """
        self.recording_path = self.temp_dir / "recording.webm"
        return self.recording_path
    
    def setup_logs(self) -> Path:
        """
        Setup log file path and configure logging.
        
        Returns:
            Path to log file
        """
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
        """
        Capture screenshot after step execution.
        
        Args:
            session: Nova Act browser session
            step_id: Step UUID
            step_number: Step number for filename
            
        Returns:
            Path to screenshot file, or None if capture failed
        """
        try:
            screenshot_path = self.temp_dir / f"step_{step_number}_screenshot.png"
            await session.screenshot(path=str(screenshot_path))
            
            if step_id not in self.step_artifacts:
                self.step_artifacts[step_id] = {}
            self.step_artifacts[step_id]['screenshot'] = screenshot_path
            
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
        """
        Capture trace data for step.
        
        Args:
            session: Nova Act browser session
            step_id: Step UUID
            step_number: Step number for filename
            
        Returns:
            Path to trace file, or None if capture failed
        """
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
        """
        Get paths to execution-level artifacts.
        
        Returns:
            Dict mapping artifact type to file path
        """
        artifacts = {}
        
        if self.recording_path and self.recording_path.exists():
            artifacts['recording'] = self.recording_path
        
        if self.log_path and self.log_path.exists():
            artifacts['logs'] = self.log_path
        
        return artifacts
    
    def get_step_artifacts(self, step_id: str) -> Dict[str, Path]:
        """
        Get paths to step-level artifacts.
        
        Args:
            step_id: Step UUID
            
        Returns:
            Dict mapping artifact type to file path
        """
        return self.step_artifacts.get(step_id, {})
    
    def cleanup(self):
        """Clean up temporary artifact files."""
        import shutil
        if self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
                logger.debug(f"Cleaned up temporary artifacts: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup artifacts: {e}")
```

**Key Methods**:
- `setup_recording()`: Returns path for Nova Act SDK to save recording
- `setup_logs()`: Configures file logging for this execution
- `capture_step_screenshot()`: Captures screenshot after step, returns path or None
- `capture_step_trace()`: Captures trace after step, returns path or None
- `get_execution_artifacts()`: Returns dict of execution-level artifacts
- `get_step_artifacts()`: Returns dict of step-level artifacts for a step
- `cleanup()`: Removes temporary directory and all artifacts

**Error Handling**:
- Screenshot/trace capture failures are logged but don't raise exceptions
- Returns None on failure to allow execution to continue
- Cleanup failures are logged but don't raise exceptions

---

### 2. Artifact Uploader (`src/execution/artifact_uploader.py`)

**Purpose**: Upload artifacts to S3 via presigned URLs with retry logic.

**Class Definition**:

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
        """
        Upload single execution-level artifact with retry.
        
        Args:
            usecase_id: Usecase UUID
            execution_id: Execution UUID
            artifact_type: Type of artifact (recording, logs)
            artifact_path: Path to artifact file
            
        Raises:
            Exception: If all retries fail
        """
        # Get presigned URL from API
        import asyncio
        response = await asyncio.to_thread(
            self.api_client.post,
            f"/usecase/{usecase_id}/executions/{execution_id}/artifacts",
            {
                'type': artifact_type,
                'filename': artifact_path.name,
                'content_type': self._get_content_type(artifact_path)
            }
        )
        
        upload_url = response['upload_url']
        
        # Upload to S3
        with open(artifact_path, 'rb') as f:
            upload_response = await asyncio.to_thread(
                requests.put,
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
        import asyncio
        response = await asyncio.to_thread(
            self.api_client.post,
            f"/usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/artifacts",
            {
                'filename': artifact_path.name,
                'content_type': self._get_content_type(artifact_path)
            }
        )
        
        upload_url = response['upload_url']
        
        # Upload to S3
        with open(artifact_path, 'rb') as f:
            upload_response = await asyncio.to_thread(
                requests.put,
                upload_url,
                data=f,
                headers={'Content-Type': self._get_content_type(artifact_path)}
            )
            upload_response.raise_for_status()
    
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
            '.json': 'application/json'
        }
        return content_types.get(extension, 'application/octet-stream')
```

**Key Methods**:
- `upload_execution_artifacts()`: Uploads all execution-level artifacts
- `upload_step_artifacts()`: Uploads all step-level artifacts
- `_upload_execution_artifact()`: Uploads single execution artifact with retry (3 attempts, exponential backoff)
- `_upload_step_artifact()`: Uploads single step artifact with retry (3 attempts, exponential backoff)
- `_get_content_type()`: Maps file extension to MIME type

**Retry Configuration**:
- 3 attempts maximum
- Exponential backoff: 2s, 4s, 8s (capped at 10s)
- Uses `tenacity` library for retry logic

**Error Handling**:
- Individual artifact upload failures are logged but don't stop other uploads
- After 3 failed attempts, exception is caught and logged
- Test execution continues even if artifact uploads fail

---

### 3. Integration with Execution Engine

**File**: `src/execution/engine.py` (modifications)

**Changes Required**:

1. Import new classes:
```python
from pathlib import Path
from .artifacts import ArtifactCapture
from .artifact_uploader import ArtifactUploader
```

2. Modify `execute_usecase()` method to setup artifact capture:
```python
async def execute_usecase(self, execution: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a single use case with artifact capture."""
    execution_id = execution['execution_id']
    usecase_id = execution['usecase_id']
    usecase_name = execution['usecase_name']
    
    # Setup artifact capture
    artifact_capture = ArtifactCapture(execution_id, Path('/tmp/artifacts'))
    artifact_capture.setup_recording()
    artifact_capture.setup_logs()
    
    # Setup artifact uploader
    artifact_uploader = ArtifactUploader(self.api_client)
    
    try:
        # ... existing execution logic ...
        
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
```

3. Modify `_execute_with_nova_act()` to enable recording and tracing:
```python
async def _execute_with_nova_act(
    self,
    execution_details: Dict[str, Any],
    artifact_capture: ArtifactCapture
) -> Dict[str, Any]:
    """Execute test using Nova Act SDK with artifact capture."""
    try:
        from nova_act_sdk import NovaActClient
        
        # Initialize Nova Act client with recording and tracing enabled
        client = NovaActClient(
            region=execution_details['executing_region'],
            model_id=execution_details['model_id'],
            recording=True,  # Enable video recording
            tracing=True     # Enable trace capture
        )
        
        # ... rest of execution logic ...
```

4. Modify `_execute_step()` to capture and upload step artifacts:
```python
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
    
    # Upload step artifacts immediately
    step_artifacts = artifact_capture.get_step_artifacts(step_id)
    await artifact_uploader.upload_step_artifacts(
        usecase_id=usecase_id,
        execution_id=execution_id,
        step_id=step_id,
        artifacts=step_artifacts
    )
```

---

## Data Models

### Artifact Paths

**Execution-Level Artifacts**:
```python
{
    'recording': Path('/tmp/artifacts/{execution_id}/recording.webm'),
    'logs': Path('/tmp/artifacts/{execution_id}/logs.txt')
}
```

**Step-Level Artifacts**:
```python
{
    'screenshot': Path('/tmp/artifacts/{execution_id}/step_{N}_screenshot.png'),
    'trace': Path('/tmp/artifacts/{execution_id}/step_{N}_trace.json')
}
```

### Presigned URL Request (Execution-Level)

**Request**:
```python
POST /usecase/{usecase_id}/executions/{execution_id}/artifacts
{
    'type': 'recording',  # or 'logs'
    'filename': 'recording.webm',
    'content_type': 'video/webm'
}
```

**Response**:
```python
{
    'artifact_id': 'uuid',
    'upload_url': 'https://s3.amazonaws.com/...',
    'expires_in': 3600,
    's3_key': 'artifacts/{usecase_id}/executions/{execution_id}/recording.webm'
}
```

### Presigned URL Request (Step-Level)

**Request**:
```python
POST /usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/artifacts
{
    'filename': 'screenshot.png',
    'content_type': 'image/png'
}
```

**Response**:
```python
{
    'artifact_id': 'uuid',
    'upload_url': 'https://s3.amazonaws.com/...',
    'expires_in': 3600,
    's3_key': 'artifacts/{usecase_id}/executions/{execution_id}/steps/{step_id}/screenshot.png'
}
```

---

## Error Handling

### Artifact Capture Failures

**Scenario**: Screenshot or trace capture fails

**Causes**:
- Nova Act SDK error
- Browser session closed
- File system error

**Handling**:
- Log warning with error details
- Return None from capture method
- Continue test execution
- Don't fail the test

**Example**:
```python
try:
    await session.screenshot(path=str(screenshot_path))
except Exception as e:
    logger.warning(f"Failed to capture screenshot for step {step_number}: {e}")
    return None
```

### Artifact Upload Failures

**Scenario**: Upload to S3 fails

**Causes**:
- Network timeout
- S3 service unavailable
- Invalid presigned URL
- File read error

**Handling**:
- Retry 3 times with exponential backoff (2s, 4s, 8s)
- Log error after all retries fail
- Continue with other artifacts
- Don't fail the test

**Example**:
```python
try:
    await self._upload_execution_artifact(...)
    logger.info(f"Uploaded {artifact_type} artifact")
except Exception as e:
    logger.error(f"Failed to upload {artifact_type} artifact: {e}")
    # Don't raise - continue with other artifacts
```

### API Request Failures

**Scenario**: Presigned URL request fails

**Causes**:
- API returns 400/404/500
- Network error
- Authentication failure

**Handling**:
- Retry via tenacity decorator (3 attempts)
- Log error after all retries fail
- Exception caught by upload method
- Continue with other artifacts

### Cleanup Failures

**Scenario**: Temporary file cleanup fails

**Causes**:
- File system error
- Permission denied
- Directory in use

**Handling**:
- Log warning
- Don't raise exception
- Allow execution to complete

**Example**:
```python
try:
    shutil.rmtree(self.temp_dir)
except Exception as e:
    logger.warning(f"Failed to cleanup artifacts: {e}")
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Recording Capture for All Executions

*For any* test execution, a recording file should be created in the temporary directory, regardless of whether the test passes or fails.

**Validates: Requirements US1.1, US1.4**

### Property 2: Artifact File Format Validation

*For any* captured artifact, the file extension should match the expected format: .webm for recordings, .txt for logs, .png for screenshots, and .json for traces.

**Validates: Requirements US1.2, US2.3, US3.3, US3.4**

### Property 3: Log File Structure

*For any* captured log file, each line should contain a timestamp, logger name, log level, and message, following the format: `YYYY-MM-DD HH:MM:SS - name - LEVEL - message`.

**Validates: Requirements US2.1, US2.2**

### Property 4: Nova Act SDK Logging

*For any* execution that uses Nova Act SDK, the log file should contain at least one log entry with "nova" or "Nova Act" in the logger name or message.

**Validates: Requirements US2.4**

### Property 5: Step Artifact Completeness

*For any* execution with N steps that complete successfully, there should be exactly N screenshot files and N trace files captured (or capture attempts logged if failures occur).

**Validates: Requirements US3.1, US3.2**

### Property 6: Presigned URL Request for Uploads

*For any* artifact upload attempt, the uploader should make a POST request to the appropriate artifacts endpoint with the correct usecase_id, execution_id, and optionally step_id.

**Validates: Requirements US4.1**

### Property 7: S3 Upload via Presigned URL

*For any* successful presigned URL request, the uploader should make a PUT request to the returned upload_url with the artifact file contents and correct Content-Type header.

**Validates: Requirements US4.2**

### Property 8: Upload Retry with Exponential Backoff

*For any* failed upload attempt, the uploader should retry up to 2 additional times (3 total attempts) with exponentially increasing wait times between attempts.

**Validates: Requirements US4.3**

### Property 9: Test Continuation on Upload Failure

*For any* artifact upload that fails after all retry attempts, the test execution should continue to completion and return a result (passed or failed based on test logic, not upload failure).

**Validates: Requirements US4.4**

### Property 10: Artifact Association Correctness

*For any* execution-level artifact upload, the API request should include the correct execution_id; for any step-level artifact upload, the API request should include both the correct execution_id and step_id.

**Validates: Requirements US4.5**

### Property 11: Temporary File Cleanup

*For any* execution, after all artifacts are uploaded (or upload attempts complete), the temporary directory for that execution should be removed from the file system.

**Validates: Implicit requirement for resource cleanup**

---

## Testing Strategy

### Dual Testing Approach

This feature requires both unit tests and property-based tests for comprehensive coverage:

- **Unit tests**: Verify specific examples, edge cases, and error conditions
- **Property tests**: Verify universal properties across all inputs

Together, these approaches provide comprehensive coverage where unit tests catch concrete bugs and property tests verify general correctness.

### Property-Based Testing

**Library**: `hypothesis` for Python

**Configuration**:
- Minimum 100 iterations per property test
- Each test tagged with feature name and property number
- Tag format: `# Feature: wp4-artifact-management, Property {N}: {property_text}`

**Property Test Examples**:

1. **Property 2: File Format Validation**
```python
from hypothesis import given, strategies as st

# Feature: wp4-artifact-management, Property 2: Artifact File Format Validation
@given(artifact_type=st.sampled_from(['recording', 'logs', 'screenshot', 'trace']))
def test_artifact_file_extension_matches_type(artifact_type):
    """For any artifact type, the file extension should match expected format."""
    expected_extensions = {
        'recording': '.webm',
        'logs': '.txt',
        'screenshot': '.png',
        'trace': '.json'
    }
    
    # Create artifact capture
    capture = ArtifactCapture('test-exec-id', Path('/tmp/test'))
    
    # Get appropriate path based on type
    if artifact_type == 'recording':
        path = capture.setup_recording()
    elif artifact_type == 'logs':
        path = capture.setup_logs()
    # ... etc
    
    assert path.suffix == expected_extensions[artifact_type]
```

2. **Property 8: Retry Behavior**
```python
# Feature: wp4-artifact-management, Property 8: Upload Retry with Exponential Backoff
@given(failure_count=st.integers(min_value=1, max_value=5))
def test_upload_retries_with_exponential_backoff(failure_count):
    """For any number of failures, uploader should retry up to 3 times."""
    # Mock API client and S3 to fail N times
    # Verify retry count is min(failure_count, 3)
    # Verify wait times follow exponential backoff
```

### Unit Testing

**Coverage Target**: 70% minimum

**Test Files**:
- `tests/test_artifact_capture.py`
- `tests/test_artifact_uploader.py`
- `tests/test_execution_engine_artifacts.py`

**Unit Test Coverage**:

1. **Artifact Capture Tests**:
   - Test setup_recording() creates correct path
   - Test setup_logs() creates file handler
   - Test capture_step_screenshot() with successful capture
   - Test capture_step_screenshot() with failure (returns None)
   - Test capture_step_trace() with successful capture
   - Test capture_step_trace() with failure (returns None)
   - Test get_execution_artifacts() returns existing files only
   - Test get_step_artifacts() returns correct artifacts for step
   - Test cleanup() removes temporary directory

2. **Artifact Uploader Tests**:
   - Test upload_execution_artifacts() with all artifact types
   - Test upload_step_artifacts() with screenshot and trace
   - Test _upload_execution_artifact() makes correct API call
   - Test _upload_step_artifact() makes correct API call
   - Test _get_content_type() for all file extensions
   - Test retry logic with mocked failures
   - Test upload continues after individual failure

3. **Execution Engine Integration Tests**:
   - Test execute_usecase() sets up artifact capture
   - Test execute_usecase() uploads execution artifacts
   - Test execute_usecase() cleans up artifacts
   - Test _execute_step() captures step artifacts
   - Test _execute_step() uploads step artifacts immediately
   - Test artifact capture doesn't fail test on error

### Integration Testing

**Test Scenarios**:

1. **End-to-End Artifact Flow**:
   - Execute real test with Nova Act SDK
   - Verify recording file created
   - Verify log file created with correct format
   - Verify screenshots captured for each step
   - Verify traces captured for each step
   - Verify all artifacts uploaded to S3
   - Verify temporary files cleaned up

2. **Artifact Upload with Real API**:
   - Request presigned URL from real API endpoint
   - Upload artifact to S3 using presigned URL
   - Verify artifact exists in S3
   - Verify artifact metadata in DynamoDB

3. **Failure Scenarios**:
   - Test with failing test (verify recording still captured)
   - Test with screenshot capture failure (verify test continues)
   - Test with upload failure (verify test continues)
   - Test with API error (verify retry logic)

### Manual Testing Checklist

- [ ] Run test suite with artifact capture enabled
- [ ] Verify recording.webm created and playable
- [ ] Verify logs.txt contains execution logs
- [ ] Verify screenshots captured for each step
- [ ] Verify traces captured for each step
- [ ] Verify artifacts uploaded to S3
- [ ] Verify artifacts visible in S3 console
- [ ] Verify artifact metadata in DynamoDB
- [ ] Test with failing test (verify artifacts still captured)
- [ ] Test with network issues (verify retry logic)
- [ ] Verify temporary files cleaned up after execution

---

## Dependencies

### Python Packages

**Add to `cicd-runner/requirements.txt`**:
```
tenacity>=8.2.0  # Retry logic with exponential backoff
```

**Already Available**:
- `requests` - HTTP client for S3 uploads
- `nova-act-sdk` - Browser automation with recording/tracing
- `asyncio` - Async execution support
- `pathlib` - File path handling

### Nova Act SDK Configuration

**Recording and Tracing**:
```python
client = NovaActClient(
    region=region,
    model_id=model_id,
    recording=True,  # Enable video recording
    tracing=True     # Enable trace capture
)
```

**Session Methods**:
- `session.screenshot(path=str)` - Capture screenshot
- `session.save_trace(path=str)` - Save trace data

### API Endpoints (from WP1c)

**Execution-Level Artifacts**:
- `POST /usecase/{id}/executions/{executionId}/artifacts`
- Requires scope: `api/execution.write`

**Step-Level Artifacts**:
- `POST /usecase/{id}/executions/{executionId}/steps/{stepId}/artifacts`
- Requires scope: `api/execution.write`

### File System

**Temporary Directory**:
- Base: `/tmp/artifacts/`
- Per-execution: `/tmp/artifacts/{execution_id}/`
- Automatically created and cleaned up

**Disk Space Considerations**:
- Recordings can be large (10-100 MB per execution)
- Ensure sufficient /tmp space in Lambda/container environment
- Cleanup is critical to avoid disk space issues

---

## Performance Considerations

### Artifact Capture Overhead

**Recording**:
- Minimal overhead (handled by Nova Act SDK)
- Recording happens in background during execution
- No impact on test execution time

**Screenshots**:
- ~100-500ms per screenshot
- Captured after each step completes
- Adds to total execution time

**Traces**:
- ~50-200ms per trace save
- Captured after each step completes
- Adds to total execution time

**Total Overhead**: ~150-700ms per step for artifact capture

### Upload Performance

**Parallel Uploads**:
- Step artifacts uploaded immediately after capture
- Execution artifacts uploaded after test completes
- Multiple executions upload in parallel (different tests)

**Upload Time**:
- Depends on artifact size and network speed
- Recordings: 10-100 MB → 5-30 seconds
- Screenshots: 100-500 KB → 1-3 seconds
- Traces: 10-100 KB → <1 second
- Logs: 10-100 KB → <1 second

**Optimization**:
- Use presigned URLs (direct S3 upload, no API Gateway)
- Upload step artifacts immediately (don't wait for test completion)
- Retry logic prevents transient failures

### Temporary Storage

**Disk Usage**:
- Per execution: 10-100 MB (mostly recording)
- Cleaned up after upload completes
- Multiple parallel executions share /tmp space

**Cleanup Timing**:
- Cleanup happens in `finally` block
- Guaranteed to run even if test fails
- Prevents disk space accumulation

---

## Security Considerations

### Presigned URL Security

**URL Expiration**:
- Presigned URLs expire after 1 hour
- Sufficient for artifact uploads
- URLs cannot be reused after expiration

**Upload-Only Access**:
- Presigned URLs only allow PUT operations
- Cannot be used to download or delete artifacts
- Enforced by S3 presigned URL parameters

### Artifact Content

**No Sensitive Data Validation**:
- Artifacts may contain sensitive data (passwords, tokens in screenshots)
- Runner does not validate or sanitize artifact content
- Responsibility of test authors to avoid sensitive data in tests

**Encryption**:
- Artifacts encrypted at rest in S3 (server-side encryption)
- Artifacts encrypted in transit (HTTPS for presigned URLs)

### File System Security

**Temporary Directory**:
- Uses `/tmp/artifacts/` with execution-specific subdirectories
- Each execution isolated in separate directory
- Cleaned up after upload to prevent data leakage

**File Permissions**:
- Artifacts created with default permissions
- Only accessible by runner process
- Removed after upload completes

---

## Monitoring & Observability

### Logging

**Artifact Capture Logs**:
```python
logger.debug(f"Captured screenshot for step {step_number}")
logger.warning(f"Failed to capture screenshot for step {step_number}: {e}")
```

**Artifact Upload Logs**:
```python
logger.info(f"Uploaded {artifact_type} artifact for execution {execution_id}")
logger.error(f"Failed to upload {artifact_type} artifact: {e}")
```

**Cleanup Logs**:
```python
logger.debug(f"Cleaned up temporary artifacts: {self.temp_dir}")
logger.warning(f"Failed to cleanup artifacts: {e}")
```

### Metrics

**Custom Metrics** (optional future enhancement):
- Artifact capture success rate
- Artifact upload success rate
- Average upload time per artifact type
- Retry count per artifact type
- Disk space usage

### Error Tracking

**Error Categories**:
- Artifact capture failures (screenshot, trace)
- Artifact upload failures (API, S3)
- Cleanup failures

**Error Handling**:
- All errors logged with context (execution_id, step_number, artifact_type)
- Errors don't fail tests (fault tolerance)
- Errors visible in execution logs for debugging

---

## Success Criteria

- [ ] Video recordings captured for all executions
- [ ] Execution logs captured with correct format
- [ ] Screenshots captured for each step
- [ ] Traces captured for each step
- [ ] Artifacts uploaded to S3 via presigned URLs
- [ ] Upload retry logic working (3 attempts, exponential backoff)
- [ ] Temporary files cleaned up after upload
- [ ] Artifact failures don't fail tests
- [ ] Unit test coverage ≥ 70%
- [ ] Property tests pass (100+ iterations each)
- [ ] Integration tests pass
- [ ] Artifacts visible in platform UI (verified manually)

