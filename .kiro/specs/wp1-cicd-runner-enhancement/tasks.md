# Implementation Plan: WP1 - CI/CD Runner Enhancement

## Overview

Extend the CI/CD runner to support single use case execution (`--usecase-id`) and local-only mode (`--local-only`). Implementation uses Python with Click CLI, Pydantic models, and hypothesis for property-based testing. All changes are within `cicd-runner/`.

## Tasks

- [ ] 1. Add Pydantic output models for local execution results
  - [x] 1.1 Add `LocalStepResult`, `LocalArtifacts`, and `LocalExecutionResult` Pydantic models to `cicd-runner/src/execution/models.py`
    - `LocalStepResult` with fields: `step_id` (alias `stepId`), `instruction`, `status`, `duration`, `screenshot` (optional)
    - `LocalArtifacts` with fields: `video` (optional), `logs` (optional)
    - `LocalExecutionResult` with fields: `status`, `usecase_id` (alias `usecaseId`), `usecase_name` (alias `usecaseName`), `duration`, `steps` (list of `LocalStepResult`), `artifacts` (`LocalArtifacts`)
    - Use `serialization_alias` for camelCase JSON output and `model_config = {"populate_by_name": True}`
    - _Requirements: 4.8, 4.9, 4.10_

  - [ ]* 1.2 Write property test for JSON output schema (Property 6)
    - **Property 6: Local-only JSON output contains all required fields**
    - Generate random `LocalExecutionResult` instances via hypothesis custom strategies, serialize with `model_dump(by_alias=True)`, verify all required top-level and nested fields are present with correct camelCase keys
    - **Validates: Requirements 4.8, 4.9, 4.10**

  - [ ]* 1.3 Write property test for stdout valid JSON (Property 10)
    - **Property 10: Local-only stdout contains only valid parseable JSON**
    - Generate random `LocalExecutionResult` instances, serialize to JSON string via `model_dump_json(by_alias=True)`, verify `json.loads()` succeeds and round-trips correctly
    - **Validates: Requirements 8.4, 8.5**

  - [ ]* 1.4 Write unit tests for output models
    - Test `LocalExecutionResult` serializes to correct camelCase JSON
    - Test `LocalStepResult` includes all required fields
    - Test artifact paths point to correct directory pattern
    - _Requirements: 4.8, 4.9, 4.10_

- [x] 2. Create UseCaseAPI client
  - [x] 2.1 Create `cicd-runner/src/api/usecases.py` with `UseCaseAPI` class
    - Follow the same pattern as `TestSuiteAPI` (constructor takes `APIClient`)
    - Implement `get_usecase(usecase_id)` → `GET /usecase/{usecase_id}`
    - Implement `get_steps(usecase_id)` → `GET /usecase/{usecase_id}/steps`
    - Implement `get_variables(usecase_id)` → `GET /usecase/{usecase_id}/variables` (parse list format to dict)
    - Implement `get_secrets(usecase_id)` → `GET /usecase/{usecase_id}/secrets`
    - Implement `execute_usecase(usecase_id, base_url, variables, region, model_id)` → `POST /usecase/{usecase_id}/execute?trigger-type=ci_runner`
    - All methods use `self.client.get()` / `self.client.post()`, inheriting Bearer token auth
    - Errors propagate as `APIError` with status code and response body (handled by `APIClient._handle_response`)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 2.2 Write property test for UseCaseAPI endpoint paths (Property 3)
    - **Property 3: UseCaseAPI calls the correct endpoint for each method**
    - Generate random UUIDs via `st.uuids()`, mock `APIClient`, verify each method calls the correct URL path
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

  - [ ]* 2.3 Write property test for UseCaseAPI error propagation (Property 4)
    - **Property 4: UseCaseAPI propagates API errors with status code and body**
    - Generate random HTTP error codes via `st.sampled_from([400, 401, 403, 404, 500, 502, 503])`, mock `APIClient` to raise `APIError`, verify the error propagates with correct status code and body
    - **Validates: Requirements 3.5**

  - [ ]* 2.4 Write unit tests for UseCaseAPI
    - Test successful fetch of metadata, steps, variables, secrets
    - Test 404 response raises `APIError` with correct status code
    - Test variables response parsed from list format to dict format
    - Test `execute_usecase` sends correct payload with trigger-type
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Modify CLI parser for new flags and validation
  - [x] 4.1 Modify `cicd-runner/src/cli/parser.py` to add `--usecase-id` and `--local-only` flags
    - Change `--suite-id` from `required=True` to `default=None`
    - Add `--usecase-id` option (`default=None`, type `str`, help text)
    - Add `--local-only` flag (`is_flag=True`, `default=False`, help text)
    - Add validation: reject if both `--suite-id` and `--usecase-id` provided (mutually exclusive)
    - Add validation: reject if neither `--suite-id` nor `--usecase-id` provided
    - Add validation: reject if `--local-only` provided without `--usecase-id`
    - Route: `--suite-id` → `run_runner()`, `--usecase-id --local-only` → `run_usecase_local()`, `--usecase-id` → `run_usecase()`
    - All existing flags (`--base-url`, `--var`, `--region`, `--model-id`, `--verbose`, `--timeout`, `--keep-artifacts`) continue to work with `--usecase-id`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4_

  - [ ]* 4.2 Write property test for CLI flag validation (Property 1)
    - **Property 1: CLI flag validation rejects invalid combinations**
    - Generate random flag combinations (both set, neither set, local-only without usecase-id), verify CLI rejects with appropriate error and non-zero exit code
    - **Validates: Requirements 1.2, 1.3, 2.2**

  - [ ]* 4.3 Write property test for CLI routing (Property 2)
    - **Property 2: CLI routing dispatches to the correct execution function**
    - Generate valid flag combos, mock `run_runner`, `run_usecase_local`, `run_usecase`, verify the correct function is called
    - **Validates: Requirements 1.4, 2.3, 2.4, 7.1**

  - [ ]* 4.4 Write unit tests for CLI parser
    - Test `--suite-id` only → calls `run_runner` (backward compatibility)
    - Test `--usecase-id` only → calls `run_usecase`
    - Test `--usecase-id --local-only` → calls `run_usecase_local`
    - Test `--usecase-id --local-only --base-url http://localhost:3000 --var key=val` → correct args passed
    - Test both flags → error
    - Test neither flag → error
    - Test `--local-only` without `--usecase-id` → error
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 7.1_

- [x] 5. Implement main orchestration functions
  - [x] 5.1 Add `run_usecase_local()` function to `cicd-runner/src/main.py`
    - Authenticate via `OAuthClient` (client_credentials grant)
    - Load settings via `Settings.from_env()`
    - Validate AWS session via `validate_aws_session()`
    - Initialize `APIClient` + `UseCaseAPI`
    - Fetch use case definition (metadata, steps, variables, secrets) via `UseCaseAPI`
    - Apply overrides: `--base-url` replaces `starting_url`, `--var` merges with variables (CLI precedence), `--region` replaces `executing_region`, `--model-id` replaces `model_id`
    - Prepare artifact directory `/tmp/qa-studio-artifacts/{usecase_id}/` (create or clear)
    - Execute via `ExecutionEngine.execute_usecase_local()`
    - Build `LocalExecutionResult` from engine output
    - Write JSON to stdout via `model_dump_json(by_alias=True)`, all logs to stderr
    - Exit with code 0 (all pass), 1 (any fail), or 2 (internal error)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 6.1, 6.2, 6.3, 6.4, 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.5_

  - [x] 5.2 Add `run_usecase()` function to `cicd-runner/src/main.py`
    - Authenticate via `OAuthClient`
    - Load settings, validate AWS session
    - Initialize `APIClient` + `UseCaseAPI`
    - Create execution record via `UseCaseAPI.execute_usecase()`
    - Execute via existing `ExecutionEngine.execute_usecase()` flow
    - Print summary, exit with code 0/1/2
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 5.3 Write property test for variable merge precedence (Property 8)
    - **Property 8: Variable merge gives CLI overrides precedence**
    - Generate two dicts (use case vars and CLI vars) with overlapping keys via `st.dictionaries(st.text(min_size=1), st.text())`, verify merged dict contains all keys with CLI values taking precedence
    - **Validates: Requirements 6.2**

  - [ ]* 5.4 Write property test for CLI override flags (Property 9)
    - **Property 9: CLI override flags replace use case defaults**
    - Generate use case defaults and override values, verify engine receives CLI-provided values instead of defaults when overrides are present
    - **Validates: Requirements 6.1, 6.3, 6.4**

  - [ ]* 5.5 Write property test for artifact directory management (Property 11)
    - **Property 11: Artifact directory is created and cleaned before execution**
    - Generate random usecase IDs, optionally pre-create directory with files, verify directory exists and is empty before execution starts
    - **Validates: Requirements 9.1, 9.5**

  - [ ]* 5.6 Write unit tests for `run_usecase_local()` and `run_usecase()`
    - Test `run_usecase_local` calls UseCaseAPI methods in correct order
    - Test `run_usecase_local` applies base_url override
    - Test `run_usecase_local` merges variables with CLI precedence
    - Test `run_usecase_local` writes JSON to stdout
    - Test `run_usecase_local` exits with code 0 on success, 1 on failure, 2 on error
    - Test `run_usecase` creates execution record via POST
    - Test `run_usecase` follows existing execution flow
    - _Requirements: 4.1-4.11, 5.1-5.5, 6.1-6.4, 8.1-8.5, 9.1-9.5_

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement local execution in ExecutionEngine
  - [x] 7.1 Add `execute_usecase_local()` method to `cicd-runner/src/execution/engine.py`
    - Reuse existing `_execute_with_nova_act` and `_run_steps_with_nova` internals
    - Add `local_only` parameter to `_run_steps_with_nova` that gates API status updates and artifact uploads
    - When `local_only=True`: skip `execution_api.update_step_status()`, skip `artifact_uploader.upload_step_artifacts()`, skip `execution_api.update_session_id()`
    - When `local_only=True`: store step screenshots as `step-{step-number}-screenshot.png` in the provided artifact directory
    - When `local_only=True`: continue executing remaining steps after a failure (don't break on first failure)
    - Return structured dict with step results and local artifact paths
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 4.9, 4.11, 9.2, 9.3, 9.4_

  - [ ]* 7.2 Write property test for local-only isolation (Property 5)
    - **Property 5: Local-only mode produces no remote side effects**
    - Generate random step sequences, mock `ExecutionAPI` and `ArtifactUploader`, execute in local-only mode, verify zero calls to create execution records, upload artifacts, or send status updates
    - **Validates: Requirements 4.2, 4.3, 4.4**

  - [ ]* 7.3 Write property test for continue after step failure (Property 12)
    - **Property 12: Local-only execution continues after step failure**
    - Generate step sequences with failures at random positions via `st.lists(st.booleans(), min_size=2)`, verify all steps are attempted and overall status is "failed" when any step fails
    - **Validates: Requirements 4.11**

  - [ ]* 7.4 Write property test for exit code correctness (Property 7)
    - **Property 7: Exit code reflects execution outcome**
    - Generate random step outcomes via `st.lists(st.sampled_from(["success", "failed"]))`, verify exit code is 0 when all pass, 1 when any fail
    - **Validates: Requirements 5.3, 5.4, 5.5, 8.1, 8.2, 8.3**

  - [ ]* 7.5 Write unit tests for `execute_usecase_local()`
    - Test steps execute in order
    - Test failed step doesn't stop subsequent steps in local-only mode
    - Test artifacts stored in correct directory with correct naming
    - Test no API calls made during local-only execution
    - Test video recording path included in result
    - _Requirements: 4.2-4.11, 9.2-9.4_

- [x] 8. Wire everything together and verify backward compatibility
  - [x] 8.1 Verify existing suite execution is unchanged
    - Run existing `test_main.py` tests to confirm `run_runner()` behavior is preserved
    - Verify `--suite-id` flag still works as before (existing flow: OAuth → fetch suite → create suite execution → parallel execution → upload → status → summary → exit code)
    - Verify existing exit code semantics: 0 for all passed, 1 for any failed, 2 for runner error
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 8.2 Write integration-style unit tests for full CLI → execution flow
    - Test `cicd-runner --usecase-id <id> --local-only` end-to-end with mocked API and engine
    - Test `cicd-runner --usecase-id <id> --local-only --base-url http://localhost:3000 --var username=testuser --var env=local` with mocked API
    - Test `cicd-runner --usecase-id <id>` (normal mode) with mocked API
    - Test `cicd-runner --suite-id <id>` still works (backward compatibility)
    - _Requirements: 1.1-1.5, 2.1-2.4, 7.1-7.4_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (12 properties total)
- Unit tests validate specific examples and edge cases
- Implementation language: Python (matching existing codebase)
- Test framework: pytest + hypothesis (already in use)
- All new test files go in `cicd-runner/tests/`
