# Implementation Plan: Runner Log Capture

## Overview

Implement suite-level log capture, per-usecase log isolation via thread filtering, nova-act console log suppression, two new suite artifact API endpoints (upload + list via S3), CDK wiring, and a frontend LogViewer component. Implementation proceeds bottom-up: log filters → suite log capture → artifact modifications → API endpoints → CDK → frontend → wiring in main.py.

## Tasks

- [x] 1. Create log filters module
  - [x] 1.1 Create `qa-studio-ci-runner/src/utils/log_filters.py` with `ThreadLogFilter` and `NovaActLogFilter`
    - Implement `ThreadLogFilter(logging.Filter)` that accepts a `thread_id` in `__init__` and returns `record.thread == self.thread_id` in `filter()`
    - Implement `NovaActLogFilter(logging.Filter)` that returns `not record.name.startswith('nova_act')` in `filter()`
    - _Requirements: 3.1, 5.1_

  - [x]* 1.2 Write property test for ThreadLogFilter
    - **Property 3: Thread-based log isolation**
    - Generate random thread IDs and log records, verify filter accepts iff `record.thread == thread_id`
    - **Validates: Requirements 3.1, 3.2**

  - [x]* 1.3 Write property test for NovaActLogFilter
    - **Property 4: NovaActLogFilter rejects nova_act hierarchy**
    - Generate random logger names, verify filter rejects iff name starts with `nova_act`
    - **Validates: Requirements 5.1**

  - [x]* 1.4 Write unit tests for log filters in `qa-studio-ci-runner/tests/test_log_filters.py`
    - `test_thread_filter_accepts_matching_thread`
    - `test_thread_filter_rejects_different_thread`
    - `test_nova_act_filter_rejects_nova_act_logger`
    - `test_nova_act_filter_rejects_nova_act_sublogger` (e.g. `nova_act.browser`)
    - `test_nova_act_filter_accepts_other_loggers`
    - _Requirements: 3.1, 3.2, 5.1_

- [x] 2. Create SuiteLogCapture module
  - [x] 2.1 Create `qa-studio-ci-runner/src/execution/suite_log_capture.py` with `SuiteLogCapture` class
    - `__init__(self, suite_execution_id: str)` — set `log_dir` to `~/.ci_runner/{suite_execution_id}`, `log_path` to `suite_logs.txt`
    - `start() -> Path | None` — create directory, attach `FileHandler` (level=DEBUG, format `%(asctime)s - %(name)s - %(levelname)s - %(message)s`) to root logger, return path or `None` on `OSError`
    - `stop() -> Path | None` — flush, close, remove handler from root logger, return path if file exists
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x]* 2.2 Write property test for suite log capture
    - **Property 1: Suite log captures all log records**
    - Generate random logger names and messages, emit while handler is active, verify all appear in suite log file
    - **Validates: Requirements 1.2, 3.3, 5.2**

  - [x]* 2.3 Write property test for suite log format
    - **Property 2: Suite log format consistency**
    - Generate random log records, verify each line matches `<timestamp> - <logger_name> - <LEVEL> - <message>` pattern
    - **Validates: Requirements 1.3**

  - [x]* 2.4 Write unit tests for SuiteLogCapture in `qa-studio-ci-runner/tests/test_suite_log_capture.py`
    - `test_start_creates_log_file_and_handler` — verify file created and handler added to root logger
    - `test_stop_removes_handler_and_flushes` — verify handler removed after stop()
    - `test_start_returns_none_on_directory_failure` — mock `Path.mkdir` to raise `OSError`, verify returns `None`
    - `test_log_path_uses_suite_execution_id` — verify correct path structure
    - _Requirements: 1.1, 1.3, 1.4, 1.5_

- [x] 3. Modify existing runner modules for log isolation and nova-act filtering
  - [x] 3.1 Modify `ArtifactCapture.setup_logs()` in `qa-studio-ci-runner/src/execution/artifacts.py` to attach `ThreadLogFilter`
    - Import `ThreadLogFilter` from `src.utils.log_filters` and `threading`
    - After creating the `FileHandler`, call `file_handler.addFilter(ThreadLogFilter(threading.get_ident()))`
    - _Requirements: 3.1, 3.2, 3.4_

  - [x] 3.2 Modify `setup_logging()` in `qa-studio-ci-runner/src/utils/logger.py` to attach `NovaActLogFilter`
    - Import `NovaActLogFilter` from `.log_filters`
    - Add `console_handler.addFilter(NovaActLogFilter())` after creating the `StreamHandler`
    - Set `root_logger.setLevel(logging.DEBUG)` so file handlers get all records
    - _Requirements: 5.1, 5.4_

  - [x]* 3.3 Write unit tests for modified `setup_logs()` in `qa-studio-ci-runner/tests/test_artifact_capture.py`
    - `test_setup_logs_attaches_thread_filter` — verify `ThreadLogFilter` is added to the file handler
    - `test_setup_logs_thread_filter_uses_current_thread` — verify filter uses calling thread's ID
    - _Requirements: 3.1, 3.2_

  - [x]* 3.4 Write unit tests for modified `setup_logging()` in `qa-studio-ci-runner/tests/test_logger.py`
    - `test_setup_logging_attaches_nova_act_filter` — verify `NovaActLogFilter` on console handler
    - `test_setup_logging_sets_root_level_debug` — verify root logger level is DEBUG
    - _Requirements: 5.1, 5.4_

- [x] 4. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Add `upload_suite_artifacts` to ArtifactUploader
  - [x] 5.1 Add `upload_suite_artifacts()` and `_upload_suite_artifact()` methods to `qa-studio-ci-runner/src/execution/artifact_uploader.py`
    - `upload_suite_artifacts(suite_id, suite_execution_id, artifacts: dict[str, Path])` — iterate artifacts, call `_upload_suite_artifact`, log errors without raising
    - `_upload_suite_artifact(suite_id, suite_execution_id, artifact_type, artifact_path)` — decorated with `@retry(stop=stop_after_attempt(3))`, POST to `/test-suites/{suite_id}/executions/{suite_execution_id}/artifacts`, then PUT file to `upload_url` with correct content type
    - No DynamoDB confirm step (unlike execution artifacts)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x]* 5.2 Write unit tests for suite artifact upload in `qa-studio-ci-runner/tests/test_artifact_uploader.py`
    - `test_upload_suite_artifacts_calls_suite_endpoint` — verify correct API path
    - `test_upload_suite_artifact_retry_on_failure` — verify 3 retries with tenacity
    - `test_upload_suite_artifact_uploads_to_presigned_url` — verify PUT to S3 upload URL
    - `test_upload_suite_artifact_logs_error_on_failure` — verify error logged, no exception raised
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 6. Create suite artifact upload Lambda endpoint
  - [x] 6.1 Create `lambdas/endpoints/generate_suite_artifact_url.py`
    - POST handler at `/test-suites/{suiteId}/executions/{executionId}/artifacts`
    - Validate `api/suite.write` scope via `require_scopes()`
    - Parse `suiteId`, `executionId` from path parameters
    - Parse `type`, `filename`, `content_type` from JSON body
    - Validate suite execution exists: `get_item(pk=SUITE_EXECUTION#{suiteId}, sk=EXECUTION#{executionId})`
    - Sanitize filename
    - Generate S3 key: `suites/{suite_id}/{suite_execution_id}/{filename}`
    - Generate presigned PUT URL (1 hour expiry)
    - Return `{ upload_url, expires_in, s3_key }` — no DynamoDB artifact record
    - Follow patterns from `generate_execution_artifact_url.py`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x]* 6.2 Write property test for S3 key format
    - **Property 5: Suite artifact S3 key format**
    - Generate random `suite_id`, `suite_execution_id`, `filename`, verify key matches `suites/{suite_id}/{suite_execution_id}/{filename}`
    - **Validates: Requirements 4.2**

  - [x]* 6.3 Write property test for endpoint response completeness
    - **Property 6: Suite artifact upload endpoint response completeness**
    - Generate valid requests, verify response contains `upload_url` (HTTPS), `expires_in`, and `s3_key`
    - **Validates: Requirements 4.1, 4.3**

  - [x]* 6.4 Write unit tests in `lambdas/endpoints/test_generate_suite_artifact_url.py`
    - `test_handler_success` — valid request returns 200 with presigned URL
    - `test_handler_missing_fields_returns_400` — missing type/filename/content_type
    - `test_handler_missing_scope_returns_403` — missing `api/suite.write`
    - `test_handler_suite_execution_not_found_returns_404` — nonexistent execution
    - `test_no_dynamodb_artifact_record_created` — verify no DynamoDB write
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 7. Create suite artifact list Lambda endpoint
  - [x] 7.1 Create `lambdas/endpoints/list_suite_artifacts.py`
    - GET handler at `/test-suites/{suiteId}/executions/{executionId}/artifacts`
    - Validate `api/suite.read` scope via `require_scopes()`
    - S3 `ListObjectsV2` with prefix `suites/{suite_id}/{suite_execution_id}/`
    - For each object: derive `filename` from key suffix, infer `type`/`content_type` from extension
    - Generate presigned GET URL (1 hour) per object
    - Return `{ artifacts: [{ filename, type, content_type, download_url, size, last_modified }] }`
    - _Requirements: 6.6, 6.7_

  - [x]* 7.2 Write property test for S3 list discovery
    - **Property 7: Suite artifact list via S3 discovery**
    - Mock N S3 objects under prefix, verify list returns exactly N artifacts with all required fields
    - **Validates: Requirements 6.6**

  - [x]* 7.3 Write unit tests in `lambdas/endpoints/test_list_suite_artifacts.py`
    - `test_handler_success` — returns artifacts with download URLs
    - `test_handler_empty_results` — no S3 objects returns empty array
    - `test_handler_missing_scope_returns_403` — missing `api/suite.read`
    - `test_handler_infers_type_from_filename` — verify filename-to-type mapping (`.txt` → logs, `.webm` → recording)
    - `test_handler_s3_list_failure_returns_500` — S3 error handling
    - _Requirements: 6.6, 6.7_

- [x] 8. CDK stack updates for new Lambda endpoints
  - [x] 8.1 Add `generateSuiteArtifactUrlLambda` and `listSuiteArtifactsLambda` to `lib/lambda-stack.ts`
    - Define both lambdas with `TABLE_NAME` and `BUCKET_NAME` environment variables
    - Grant `tableReadPolicy` to both, `tableWritePolicy` not needed (no DynamoDB writes)
    - Grant `artefactsBucket.grantPut()` to generate lambda, `artefactsBucket.grantRead()` to list lambda
    - _Requirements: 4.2, 6.6_

  - [x] 8.2 Add routes to `lib/api-stack.ts`
    - Add `POST` on `suiteExecution` resource → `artifacts` sub-resource → `generateSuiteArtifactUrlLambda`
    - Add `GET` on same `artifacts` resource → `listSuiteArtifactsLambda`
    - Both routes use existing Cognito authorizer
    - _Requirements: 4.1, 4.5, 6.6, 6.7_

- [x] 9. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Create frontend LogViewer component and integrate
  - [x] 10.1 Create `frontend/src/components/common/LogViewer.tsx`
    - Props: `downloadUrl: string | null`, `loading?: boolean`
    - States: loading (Spinner), loaded (Cloudscape `CodeView` with line numbers, no syntax highlighting), error (Alert with retry button)
    - Fetch log content from `downloadUrl` using `fetch()`, store as text state
    - _Requirements: 6.3, 6.4, 6.5_

  - [x] 10.2 Integrate LogViewer into `SuiteExecutionDetail.tsx` for suite-level logs
    - Fetch suite artifacts from `GET /test-suites/{suite_id}/executions/{execution_id}/artifacts`
    - Find log artifact, pass its `download_url` to `LogViewer`
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 10.3 Integrate LogViewer into `ExecutionDetailRefactored.tsx` for usecase-level logs
    - When a usecase execution has a log artifact, render `LogViewer` with the same pattern
    - _Requirements: 6.8_

  - [x]* 10.4 Write unit tests for LogViewer in `frontend/src/components/common/__tests__/LogViewer.test.tsx`
    - `test_renders_loading_state` — shows spinner while fetching
    - `test_renders_log_content_in_code_view` — CodeView with line numbers
    - `test_renders_error_with_retry` — error alert with retry button
    - `test_retry_refetches_content` — clicking retry triggers re-fetch
    - _Requirements: 6.3, 6.4, 6.5_

- [x] 11. Wire suite log lifecycle into main.py
  - [x] 11.1 Modify `run_runner()` in `qa-studio-ci-runner/src/main.py`
    - Import `SuiteLogCapture`
    - After `execution_engine` init, create `SuiteLogCapture(suite_execution_id)` and call `start()`
    - After summary is printed and exit code determined, call `suite_log_capture.stop()`
    - If suite log path exists, call `artifact_uploader.upload_suite_artifacts(suite_id, suite_execution_id, {'logs': suite_log_path})`
    - Wrap upload in try/except — log error, do not change exit code
    - _Requirements: 1.1, 1.4, 2.1, 2.4_

  - [x]* 11.2 Write unit tests for suite log integration in `qa-studio-ci-runner/tests/test_main.py`
    - `test_run_runner_starts_suite_log_capture` — verify `SuiteLogCapture.start()` called
    - `test_run_runner_stops_suite_log_capture_on_success` — verify `stop()` called
    - `test_run_runner_stops_suite_log_capture_on_failure` — verify `stop()` called even on error
    - `test_run_runner_uploads_suite_log` — verify `upload_suite_artifacts` called with correct args
    - `test_run_runner_continues_on_upload_failure` — verify exit code unaffected by upload error
    - _Requirements: 1.1, 1.4, 2.1, 2.4_

- [x] 12. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- OAuth scopes: `api/suite.write` (POST upload), `api/suite.read` (GET list) — both already exist in CDK auth stack (singular form)
- Suite artifacts use S3-direct storage with no DynamoDB records — the list endpoint discovers via `ListObjectsV2`
- Property tests use `hypothesis` (Python) and `fast-check` (TypeScript) with minimum 100 iterations
- The `asyncio.to_thread` learning applies: suite artifact upload in `main.py` uses `asyncio.run()` which is safe since it's called from the main thread after all parallel execution is complete
