# Runner Log Capture - Design Document

## Feature Information
- **Feature**: Runner Log Capture
- **Version**: 1.0
- **Status**: Design Phase
- **Dependencies**: WP4 (Artifact Management), WP1c (Artifact Presigned URL Endpoints)

---

## Overview

This feature addresses two gaps in the CI/CD runner's logging infrastructure:

1. **Suite-level log capture**: Currently, logs are only captured per-usecase via `ArtifactCapture.setup_logs()`. There is no mechanism to capture the full suite lifecycle (authentication, setup, parallel orchestration, summary generation) into a single log file uploaded as a suite-level artifact.

2. **Usecase log isolation**: The current `setup_logs()` attaches a `FileHandler` to the root logger without any thread-based filtering. When usecases run in parallel via `asyncio.to_thread`, log records from all threads bleed into every usecase's log file.

3. **Nova-act console noise**: The `nova_act` library emits verbose browser automation logs to the console `StreamHandler`, making CLI output hard to read.

4. **Frontend log viewing**: Users currently have no way to view log content directly in the UI — they must download artifact files manually.

### Key Design Decisions

- **Thread-based log filtering**: Use Python's `logging.Filter` with `threading.get_ident()` to scope usecase file handlers to their execution thread. This works because each usecase runs in its own thread via `asyncio.to_thread`.
- **S3-direct artifact discovery (no DynamoDB record for suite artifacts)**: Instead of creating a DynamoDB record per suite artifact, the runner uploads directly to a deterministic S3 key path (`suites/{suite_id}/{suite_execution_id}/{filename}`). The list endpoint uses S3 `ListObjectsV2` with the prefix to discover artifacts and generates presigned download URLs. This eliminates the need for a confirm/PATCH endpoint and simplifies the upload flow.
- **Reuse existing `ArtifactUploader`**: Extend with a new `upload_suite_artifacts()` method that hits the new suite artifact endpoint, keeping the retry logic and upload pattern consistent.
- **Existing OAuth scopes**: The CDK stack defines `api/suite.write` and `api/suite.read` (singular). The new endpoints will use these existing scopes — no new scopes needed.

---

## Architecture

### High-Level Flow

```
main.py::run_runner()
    │
    ├─ 1. setup_logging() — console handler + nova-act filter
    │
    ├─ 2. SuiteLogCapture.start() — attach suite-level file handler to root logger
    │
    ├─ 3. ExecutionEngine.execute_all()
    │      │
    │      └─ For each usecase (parallel via asyncio.to_thread):
    │           ├─ ArtifactCapture.setup_logs() — per-usecase file handler WITH thread filter
    │           ├─ Execute steps with Nova Act
    │           ├─ ArtifactCapture.close_log_handler() — remove per-usecase handler
    │           └─ Upload usecase artifacts (existing flow)
    │
    ├─ 4. SuiteLogCapture.stop() — flush & close suite file handler
    │
    └─ 5. ArtifactUploader.upload_suite_artifacts() — upload suite log via new endpoint
```

### Component Interaction

```
┌──────────────────────────────────────────────────────┐
│  main.py::run_runner()                               │
│                                                      │
│  1. setup_logging(verbose) — adds console handler    │
│     + NovaActLogFilter on console StreamHandler      │
│  2. SuiteLogCapture(suite_execution_id).start()      │
│  3. ExecutionEngine.execute_all(executions)           │
│  4. SuiteLogCapture.stop()                           │
│  5. ArtifactUploader.upload_suite_artifacts(...)      │
└──────────┬───────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────┐
│  ExecutionEngine.execute_usecase()                   │
│                                                      │
│  Per usecase (each in its own thread):               │
│  - ArtifactCapture.setup_logs()                      │
│    → FileHandler + ThreadLogFilter(current_thread)   │
│  - Execute steps                                     │
│  - close_log_handler() removes handler               │
│  - Upload usecase artifacts (existing endpoint)      │
└──────────┬───────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────┐
│  New: Suite Artifact Upload Endpoint (POST)          │
│  /test-suites/{suiteId}/executions/{execId}/artifacts│
│                                                      │
│  - Validates suite execution exists                  │
│  - Generates presigned S3 upload URL                 │
│  - S3 key: suites/{suiteId}/{execId}/{filename}      │
│  - No DynamoDB artifact record created               │
│  - Scope: api/suite.write                            │
└──────────┬───────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────┐
│  New: Suite Artifact List Endpoint (GET)             │
│  /test-suites/{suiteId}/executions/{execId}/artifacts│
│                                                      │
│  - S3 ListObjectsV2 prefix:                         │
│    suites/{suiteId}/{execId}/                        │
│  - Generates presigned download URLs per object      │
│  - Scope: api/suite.read                             │
└──────────────────────────────────────────────────────┘
```

### Logging Handler Architecture

```
Root Logger (level=DEBUG)
  │
  ├─ StreamHandler (console) ─── NovaActLogFilter (rejects nova_act.*)
  │                               level = INFO (or DEBUG if verbose)
  │
  ├─ FileHandler (suite log) ─── NO filter (captures everything)
  │   path: ~/.ci_runner/{suite_execution_id}/suite_logs.txt
  │   level = DEBUG
  │
  ├─ FileHandler (usecase A) ─── ThreadLogFilter(thread_id_A)
  │   path: ~/.ci_runner/{suite_exec_id}/{exec_id_A}/artifacts/logs.txt
  │   level = DEBUG
  │
  └─ FileHandler (usecase B) ─── ThreadLogFilter(thread_id_B)
      path: ~/.ci_runner/{suite_exec_id}/{exec_id_B}/artifacts/logs.txt
      level = DEBUG
```

---

## Components and Interfaces

### 1. SuiteLogCapture (`src/execution/suite_log_capture.py`) — NEW

**Purpose**: Manage suite-level log file capture across the entire runner execution.

```python
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class SuiteLogCapture:
    """Capture all logs for the entire suite execution into a single file."""

    def __init__(self, suite_execution_id: str):
        self.suite_execution_id = suite_execution_id
        self.log_dir = Path.home() / ".ci_runner" / suite_execution_id
        self.log_path = self.log_dir / "suite_logs.txt"
        self._handler: logging.FileHandler | None = None

    def start(self) -> Path | None:
        """Create log directory and attach file handler to root logger.
        
        Returns:
            Path to suite log file, or None if setup failed.
        """
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning(f"Cannot create suite log directory: {e}")
            return None

        handler = logging.FileHandler(self.log_path)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logging.getLogger().addHandler(handler)
        self._handler = handler
        return self.log_path

    def stop(self) -> Path | None:
        """Flush and close the suite log handler. Returns path if log exists."""
        if self._handler:
            try:
                self._handler.flush()
                self._handler.close()
                logging.getLogger().removeHandler(self._handler)
            except Exception:
                pass
            self._handler = None
        return self.log_path if self.log_path.exists() else None
```

### 2. ThreadLogFilter (`src/utils/log_filters.py`) — NEW

**Purpose**: Provide logging filters for thread-based isolation and nova-act suppression.

```python
import logging
import threading

class ThreadLogFilter(logging.Filter):
    """Only accept log records from a specific thread."""

    def __init__(self, thread_id: int):
        super().__init__()
        self.thread_id = thread_id

    def filter(self, record: logging.LogRecord) -> bool:
        return record.thread == self.thread_id


class NovaActLogFilter(logging.Filter):
    """Reject log records from the nova_act logger hierarchy."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith('nova_act')
```

### 3. Modifications to `ArtifactCapture` (`src/execution/artifacts.py`)

**Change**: `setup_logs()` attaches a `ThreadLogFilter` to the file handler so only logs from the current usecase's thread are captured.

```python
def setup_logs(self) -> Path:
    """Setup log file with thread-scoped filtering."""
    self.log_path = self.temp_dir / "logs.txt"

    file_handler = logging.FileHandler(self.log_path)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

    # Filter to only capture logs from this usecase's thread
    file_handler.addFilter(ThreadLogFilter(threading.get_ident()))

    logging.getLogger().addHandler(file_handler)
    self._log_handler = file_handler
    return self.log_path
```

### 4. Modifications to `setup_logging()` (`src/utils/logger.py`)

**Change**: Attach `NovaActLogFilter` to the console `StreamHandler`.

```python
def setup_logging(verbose: bool) -> None:
    from .log_filters import NovaActLogFilter

    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    console_handler.addFilter(NovaActLogFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Always DEBUG so file handlers get everything
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
```

### 5. Modifications to `ArtifactUploader` (`src/execution/artifact_uploader.py`)

**Change**: Add `upload_suite_artifacts()` method that uses the new suite artifact endpoint.

```python
async def upload_suite_artifacts(
    self,
    suite_id: str,
    suite_execution_id: str,
    artifacts: dict[str, Path],
) -> None:
    """Upload suite-level artifacts via the suite artifact endpoint."""
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
```

### 6. Modifications to `main.py::run_runner()`

**Change**: Wrap the execution flow with `SuiteLogCapture` start/stop and upload suite artifacts after execution completes.

```python
# After ExecutionEngine is initialized, before execute_all:
suite_log_capture = SuiteLogCapture(suite_execution_id)
suite_log_path = suite_log_capture.start()

# ... existing execute_all and summary logic ...

# After summary, before sys.exit:
suite_log_capture.stop()
if suite_log_path and suite_log_path.exists():
    artifact_uploader = ArtifactUploader(api_client)
    asyncio.run(artifact_uploader.upload_suite_artifacts(
        suite_id=suite_id,
        suite_execution_id=suite_execution_id,
        artifacts={'logs': suite_log_path},
    ))
```

### 7. Suite Artifact Upload Endpoint (`lambdas/endpoints/generate_suite_artifact_url.py`) — NEW

**Purpose**: Generate presigned S3 URL for suite-level artifacts. No DynamoDB record is created — artifacts are discovered via S3 ListObjectsV2 at read time.

**Path**: `POST /test-suites/{suiteId}/executions/{executionId}/artifacts`

**Scope**: `api/suite.write`

**Handler logic**:
1. Validate `api/suite.write` scope
2. Parse `suiteId` and `executionId` from path parameters
3. Parse `type`, `filename`, `content_type` from request body
4. Validate suite execution exists: `get_item(pk=SUITE_EXECUTION#{suiteId}, sk=EXECUTION#{executionId})`
5. Sanitize filename
6. Generate S3 key: `suites/{suite_id}/{suite_execution_id}/{filename}`
7. Generate presigned upload URL (PUT, 1 hour expiry)
8. Return `{ upload_url, expires_in, s3_key }`

### 8. Suite Artifact List Endpoint (`lambdas/endpoints/list_suite_artifacts.py`) — NEW

**Purpose**: List artifacts for a suite execution by querying S3 directly and generate presigned download URLs.

**Path**: `GET /test-suites/{suiteId}/executions/{executionId}/artifacts`

**Scope**: `api/suite.read`

**Handler logic**:
1. Validate `api/suite.read` scope
2. Parse `suiteId` and `executionId` from path parameters
3. S3 `ListObjectsV2` with prefix `suites/{suite_id}/{suite_execution_id}/`
4. For each S3 object found, derive `filename` from the key suffix and infer `type`/`content_type` from the filename extension
5. Generate presigned download URL (GET, 1 hour) for each object
6. Return JSON array of `{ filename, type, content_type, download_url, size, last_modified }`

### 9. Frontend: LogViewer Component (`frontend/src/components/common/LogViewer.tsx`) — NEW

**Purpose**: Reusable component for displaying log content in a Cloudscape `CodeView`.

```typescript
interface LogViewerProps {
  downloadUrl: string | null;
  loading?: boolean;
}

// States: loading → loaded (CodeView with line numbers) | error (Alert with retry)
```

Used in both `SuiteExecutionDetail` (suite logs) and `ExecutionDetail` (usecase logs).

---

## Data Models

### S3-Based Artifact Storage (No DynamoDB Record)

Suite artifacts are stored directly in S3 with a deterministic key path. There is no DynamoDB record for suite artifacts — the list endpoint discovers artifacts via S3 `ListObjectsV2`.

**Rationale**:
- Eliminates the need for a DynamoDB artifact record type, confirm/PATCH endpoint, and `upload_status` tracking
- S3 is the source of truth — if the object exists, the upload succeeded
- Deterministic key paths mean the list endpoint can discover all artifacts for a suite execution with a single prefix query
- Simpler upload flow: get presigned URL → PUT to S3 → done

### S3 Key Structure

**Suite-level artifacts**:
```
suites/{suite_id}/{suite_execution_id}/{filename}
```

Example:
```
suites/abc-123/exec-456/suite_logs.txt
```

**Existing usecase-level artifacts** (unchanged):
```
{usecase_id}/{execution_id}/logs.txt
{usecase_id}/{execution_id}/recording.webm
```

### Filename-to-Type Mapping

The list endpoint infers artifact `type` and `content_type` from the filename:

| Filename Pattern | Type | Content Type |
|---|---|---|
| `*.txt` | `logs` | `text/plain` |
| `*.webm` | `recording` | `video/webm` |
| `*.mp4` | `recording` | `video/mp4` |
| Other | `unknown` | `application/octet-stream` |

### Suite Artifact Upload API

**Request** (POST):
```json
{
    "type": "logs",
    "filename": "suite_logs.txt",
    "content_type": "text/plain"
}
```

**Response** (200):
```json
{
    "upload_url": "https://s3.amazonaws.com/...",
    "expires_in": 3600,
    "s3_key": "suites/{suite_id}/{suite_execution_id}/suite_logs.txt"
}
```

### Suite Artifact List API

**Response** (200):
```json
{
    "artifacts": [
        {
            "filename": "suite_logs.txt",
            "type": "logs",
            "content_type": "text/plain",
            "download_url": "https://s3.amazonaws.com/...",
            "size": 102400,
            "last_modified": "2024-01-15T10:30:00Z"
        }
    ]
}
```


---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Suite log captures all log records

*For any* logger name (including third-party names like `nova_act`, `urllib3`, etc.) and any log message, if a log record is emitted while the suite file handler is active, the suite log file shall contain that record.

**Validates: Requirements 1.2, 3.3, 5.2**

### Property 2: Suite log format consistency

*For any* log record written to the suite log file, the line shall match the pattern `<timestamp> - <logger_name> - <LEVEL> - <message>`, specifically the format `%(asctime)s - %(name)s - %(levelname)s - %(message)s`.

**Validates: Requirements 1.3**

### Property 3: Thread-based log isolation

*For any* log record and any `ThreadLogFilter` configured with a `thread_id`, the filter shall accept the record if and only if `record.thread == thread_id`. Consequently, when multiple usecases execute in parallel threads, each usecase's log file contains only records from its own thread.

**Validates: Requirements 3.1, 3.2**

### Property 4: NovaActLogFilter rejects nova_act hierarchy

*For any* log record, the `NovaActLogFilter` shall reject it if and only if the record's logger name starts with `nova_act`. All other logger names shall be accepted.

**Validates: Requirements 5.1**

### Property 5: Suite artifact S3 key format

*For any* valid `suite_id`, `suite_execution_id`, and `filename`, the generated S3 key for a suite artifact shall match the format `suites/{suite_id}/{suite_execution_id}/{filename}`.

**Validates: Requirements 4.2**

### Property 6: Suite artifact upload endpoint response completeness

*For any* valid POST request to the suite artifact endpoint with `type`, `filename`, and `content_type`, the response shall contain `upload_url` (a valid HTTPS URL), `expires_in`, and `s3_key`.

**Validates: Requirements 4.1, 4.3**

### Property 7: Suite artifact list via S3 discovery

*For any* set of N files uploaded to S3 under the prefix `suites/{suite_id}/{suite_execution_id}/`, the list endpoint shall return exactly N artifacts, each with a valid `filename`, `type`, `content_type`, `download_url`, `size`, and `last_modified`.

**Validates: Requirements 6.6**

---

## Error Handling

### Suite Log Directory Creation Failure

**Scenario**: `SuiteLogCapture.start()` cannot create `~/.ci_runner/{suite_execution_id}/`

**Cause**: Permission denied, disk full, read-only filesystem

**Handling**:
- Log a warning via the existing console handler
- Return `None` from `start()`
- Runner continues execution without suite-level log capture
- No suite log upload is attempted

```python
try:
    self.log_dir.mkdir(parents=True, exist_ok=True)
except OSError as e:
    logger.warning(f"Cannot create suite log directory: {e}")
    return None
```

### Suite Log Upload Failure

**Scenario**: Upload of suite log to S3 fails after 3 retry attempts

**Cause**: Network timeout, S3 unavailable, invalid presigned URL, API error

**Handling**:
- `tenacity` retries 3 times with exponential backoff (2s, 4s, 8s)
- After all retries fail, error is logged
- Runner exit code is based on test results, not upload success
- This matches the existing artifact upload fault tolerance pattern

### Suite Artifact Endpoint Errors

| Scenario | Status | Response |
|---|---|---|
| Missing required fields (`type`, `filename`, `content_type`) | 400 | `{ "error": "Missing required fields" }` |
| Invalid artifact type | 400 | `{ "error": "Invalid artifact type" }` |
| Missing/invalid OAuth scope | 403 | Handled by `require_scopes()` |
| Suite execution not found | 404 | `{ "error": "Suite execution not found" }` |
| S3 presigned URL generation failure | 500 | `{ "error": "Failed to generate presigned URL" }` |

### Suite Artifact List Endpoint Errors

| Scenario | Status | Response |
|---|---|---|
| Missing/invalid OAuth scope | 403 | Handled by `require_scopes()` |
| S3 ListObjectsV2 failure | 500 | `{ "error": "Failed to list artifacts" }` |
| S3 presigned download URL failure | 500 | `{ "error": "Failed to generate download URL" }` |

### Frontend Log Fetch Failure

**Scenario**: Fetching log content from presigned download URL fails

**Handling**:
- Display an `Alert` component with type `error` inside the log container
- Include a "Retry" button that re-fetches the log content
- Does not affect the rest of the page

---

## Testing Strategy

### Dual Testing Approach

- **Unit tests**: Verify specific examples, edge cases, error conditions, and integration points
- **Property tests**: Verify universal properties across all inputs using `hypothesis` (Python) and `fast-check` (TypeScript)
- Together: unit tests catch concrete bugs, property tests verify general correctness

### Property-Based Testing

**Python Library**: `hypothesis`
**TypeScript Library**: `fast-check`

**Configuration**:
- Minimum 100 iterations per property test
- Each test tagged with feature name and property number
- Tag format: `# Feature: runner-log-capture, Property {N}: {property_text}`

**Property Test Plan**:

| Property | Test File | Description |
|---|---|---|
| 1: Suite log captures all | `cicd-runner/tests/test_suite_log_capture.py` | Generate random logger names and messages, verify all appear in suite log |
| 2: Log format consistency | `cicd-runner/tests/test_suite_log_capture.py` | Generate random log records, verify each line matches format pattern |
| 3: Thread-based isolation | `cicd-runner/tests/test_log_filters.py` | Generate random thread IDs and log records, verify filter accepts iff thread matches |
| 4: NovaActLogFilter | `cicd-runner/tests/test_log_filters.py` | Generate random logger names, verify filter rejects iff name starts with `nova_act` |
| 5: S3 key format | `lambdas/endpoints/test_generate_suite_artifact_url.py` | Generate random suite_id, execution_id, filename, verify key format |
| 6: Endpoint response | `lambdas/endpoints/test_generate_suite_artifact_url.py` | Generate valid requests, verify response contains all required fields |
| 7: S3 list discovery | `lambdas/endpoints/test_list_suite_artifacts.py` | Upload N objects to S3 prefix, verify list returns N artifacts with required fields |

### Unit Testing

**Coverage Target**: 70% minimum

**Test Files and Coverage**:

**`cicd-runner/tests/test_suite_log_capture.py`** (NEW):
- `test_start_creates_log_file_and_handler` — verify file created and handler added to root logger
- `test_stop_removes_handler_and_flushes` — verify handler removed after stop()
- `test_start_returns_none_on_directory_failure` — verify graceful degradation
- `test_log_path_uses_suite_execution_id` — verify correct path structure
- Property tests for Properties 1 and 2

**`cicd-runner/tests/test_log_filters.py`** (NEW):
- `test_thread_filter_accepts_matching_thread` — verify acceptance
- `test_thread_filter_rejects_different_thread` — verify rejection
- `test_nova_act_filter_rejects_nova_act_logger` — verify rejection of `nova_act`
- `test_nova_act_filter_rejects_nova_act_sublogger` — verify rejection of `nova_act.browser`
- `test_nova_act_filter_accepts_other_loggers` — verify acceptance of non-nova-act
- Property tests for Properties 3 and 4

**`cicd-runner/tests/test_artifact_capture.py`** (MODIFY):
- `test_setup_logs_attaches_thread_filter` — verify ThreadLogFilter is added to handler
- `test_setup_logs_thread_filter_uses_current_thread` — verify filter uses calling thread's ID

**`cicd-runner/tests/test_artifact_uploader.py`** (MODIFY):
- `test_upload_suite_artifacts_calls_suite_endpoint` — verify correct API path
- `test_upload_suite_artifact_retry_on_failure` — verify 3 retries
- `test_upload_suite_artifact_uploads_to_presigned_url` — verify PUT to S3 upload URL

**`lambdas/endpoints/test_generate_suite_artifact_url.py`** (NEW):
- `test_handler_success` — valid request returns 200 with presigned URL (no artifact_id)
- `test_handler_missing_fields_returns_400` — missing type/filename/content_type
- `test_handler_invalid_type_returns_400` — invalid artifact type
- `test_handler_missing_scope_returns_403` — missing api/suite.write
- `test_handler_suite_execution_not_found_returns_404` — nonexistent execution
- `test_s3_key_format` — verify key matches expected pattern
- `test_no_dynamodb_artifact_record_created` — verify no DynamoDB write for artifact
- Property tests for Properties 5, 6

**`lambdas/endpoints/test_list_suite_artifacts.py`** (NEW):
- `test_handler_success` — returns artifacts with download URLs from S3 ListObjectsV2
- `test_handler_empty_results` — no S3 objects returns empty array
- `test_handler_missing_scope_returns_403` — missing api/suite.read
- `test_handler_infers_type_from_filename` — verify filename-to-type mapping
- `test_handler_s3_list_failure_returns_500` — S3 error handling
- Property test for Property 7

**Frontend tests** (`frontend/src/components/common/__tests__/LogViewer.test.tsx`) (NEW):
- `test_renders_loading_state` — shows spinner while fetching
- `test_renders_log_content_in_code_view` — CodeView with line numbers
- `test_renders_error_with_retry` — error alert with retry button
- `test_retry_refetches_content` — clicking retry triggers re-fetch

### CDK Integration

- New Lambda functions added to API stack for suite artifact endpoints
- Route: `POST /test-suites/{suiteId}/executions/{executionId}/artifacts` → `generate_suite_artifact_url`
- Route: `GET /test-suites/{suiteId}/executions/{executionId}/artifacts` → `list_suite_artifacts`
- All routes use existing Cognito authorizer
- Scopes: `api/suite.write` (POST), `api/suite.read` (GET) — both already exist in CDK stack
