# Implementation Plan: WP2 Runner Integration

## Overview

Enhance the existing `qa-studio-ci-runner` to support single use case execution (local-only and remote modes), token file authentication, and a CLI wrapper for `qa-studio run`. Tasks are ordered by dependency: data models → auth changes → settings → URL utility → UseCaseAPI → engine local mode → main orchestration → CLI parser → CLI wrapper → backward compat verification.

## Tasks

- [x] 1. Define new Pydantic data models
  - [x] 1.1 Create new data models in `qa-studio-ci-runner/src/execution/models.py`
    - Add `UseCaseMetadata(BaseModel)` with fields: `id`, `name`, `starting_url`, `executing_region`, `model_id` (optional)
    - Add `UseCaseStep(BaseModel)` with fields: `step_id`, `step_type`, `instruction`, `sort`, `expected_value` (optional), `capture_variable` (optional), `operator` (optional)
    - Add `TokenFileData(BaseModel)` with fields: `access_token`, `refresh_token` (optional), `expires_at` (optional), `token_type` (default "Bearer")
    - Add `StepResultDetail(BaseModel)` with fields: `step_id` (alias "stepId"), `status`, `duration`, `error` (optional); set `populate_by_name = True`
    - Add `ArtifactPaths(BaseModel)` with fields: `video` (optional), `logs` (optional)
    - Add `LocalExecutionResult(BaseModel)` with fields: `status`, `usecase_id` (alias "usecaseId"), `usecase_name` (alias "usecaseName"), `duration`, `steps` (list[StepResultDetail]), `artifacts` (ArtifactPaths); set `populate_by_name = True`
    - Add `RemoteExecutionResult(BaseModel)` with fields: `status`, `usecase_id` (alias "usecaseId"), `usecase_name` (alias "usecaseName"), `execution_id` (alias "executionId"), `duration`, `steps` (list[StepResultDetail]); set `populate_by_name = True`
    - _Requirements: 2.8, 3.9, 7.5_

  - [ ]* 1.2 Write unit tests for new data models (`tests/test_models.py`)
    - Test `LocalExecutionResult` serializes to camelCase JSON via `model_dump(by_alias=True)`
    - Test `RemoteExecutionResult` serializes to camelCase JSON via `model_dump(by_alias=True)`
    - Test `TokenFileData` validates `access_token` is required
    - Test `UseCaseMetadata` and `UseCaseStep` field defaults
    - _Requirements: 2.8, 3.9, 7.5_

  - [ ]* 1.3 Write property test for execution result JSON output
    - **Property 3: Execution result JSON contains all required fields**
    - For any valid `LocalExecutionResult`, `model_dump(by_alias=True)` contains keys: `status`, `usecaseId`, `usecaseName`, `duration`, `steps`, `artifacts`
    - For any valid `RemoteExecutionResult`, `model_dump(by_alias=True)` contains keys: `status`, `usecaseId`, `usecaseName`, `executionId`, `duration`, `steps`
    - **Validates: Requirements 2.8, 3.9, 7.5**

- [x] 2. Implement token file authentication
  - [x] 2.1 Modify `OAuthClient` in `qa-studio-ci-runner/src/auth/oauth_client.py`
    - Make `client_id`, `client_secret`, `token_endpoint` optional (default `None`)
    - Add `token_file` parameter (default `None`)
    - On init: if `token_file` provided, validate file exists and contains `access_token`; set `_use_token_file = True`
    - On init: if client credentials provided, use existing flow; set `_use_token_file = False`
    - On init: if neither provided, raise `AuthenticationError` with descriptive message
    - Add `_read_token_file()` method: read JSON, validate `access_token` field, raise `AuthenticationError` if file missing or field absent
    - Modify `get_access_token()`: if `_use_token_file`, call `_read_token_file()` (re-read every time, no caching)
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 4.7, 4.8_

  - [ ]* 2.2 Write unit tests for token file auth (`tests/test_token_file_auth.py`)
    - Test valid token file returns access token
    - Test non-existent file raises `AuthenticationError` with file path in message
    - Test file without `access_token` field raises `AuthenticationError`
    - Test invalid JSON raises `AuthenticationError`
    - Test no auth configured raises `AuthenticationError`
    - Test client credentials mode still works unchanged
    - Test `get_access_token()` re-reads file on each call (write new token, verify returned)
    - _Requirements: 4.2, 4.3, 4.5, 4.6, 4.7, 4.8_

  - [ ]* 2.3 Write property tests for token file auth (`tests/test_token_file_auth.py`)
    - **Property 5: Token file authentication reads from file without client credentials flow**
    - For any valid token string written to a temp file, `OAuthClient(token_file=path).get_access_token()` returns that token
    - **Validates: Requirements 4.2, 4.3**
    - **Property 6: Invalid token file raises descriptive error**
    - For any non-existent path, `OAuthClient(token_file=path)` raises `AuthenticationError` containing the path string
    - For any JSON without `access_token`, `OAuthClient(token_file=path)` raises `AuthenticationError`
    - **Validates: Requirements 4.5, 4.6**
    - **Property 7: Token file re-read on each access**
    - For any two distinct token strings, writing token1 then calling `get_access_token()`, then writing token2 and calling `get_access_token()` again, returns token2
    - **Validates: Requirements 4.7**

- [x] 3. Checkpoint - Ensure token file auth tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Update Settings for optional auth
  - [x] 4.1 Modify `Settings` in `qa-studio-ci-runner/src/config/settings.py`
    - Make `oauth_client_id`, `oauth_client_secret`, `oauth_token_endpoint` optional with default `None`
    - Keep `api_endpoint` required
    - Add `from_env_optional_auth()` classmethod: load `API_ENDPOINT` (required), load OAuth env vars as optional (no `KeyError` if missing)
    - Keep existing `from_env()` unchanged for backward compatibility (OAuth fields still required there)
    - Relax `validate_https_url` validator to skip `None` values for `oauth_token_endpoint`
    - _Requirements: 4.4, 9.1, 9.3_

  - [ ]* 4.2 Write unit tests for Settings changes (`tests/test_settings.py`)
    - Test `from_env_optional_auth()` succeeds with only `API_ENDPOINT` set
    - Test `from_env_optional_auth()` returns `None` for OAuth fields when not set
    - Test `from_env()` still requires all OAuth fields (backward compat)
    - _Requirements: 4.4, 9.3_

  - [ ]* 4.3 Write property test for Settings optional auth
    - **Property 8: Settings does not require OAuth env vars in token-file mode**
    - For any valid HTTPS API endpoint URL, `from_env_optional_auth()` succeeds with only `API_ENDPOINT` set and returns `api_endpoint` matching the input
    - **Validates: Requirements 4.4**

- [x] 5. Implement URL override utility
  - [x] 5.1 Create `apply_base_url_override()` in `qa-studio-ci-runner/src/utils/url.py`
    - Use `urllib.parse.urlparse` and `urlunparse`
    - Replace scheme and netloc from `base_url`, preserve path, params, query, fragment from `original_url`
    - _Requirements: 6.1_

  - [ ]* 5.2 Write unit tests for URL override (`tests/test_url_override.py`)
    - Test origin replacement preserves path and query
    - Test with localhost:3000 as base URL
    - Test with trailing slash on base URL
    - Test with empty path
    - Test with fragment
    - _Requirements: 6.1_

  - [ ]* 5.3 Write property test for URL override
    - **Property 10: URL override preserves path and query**
    - For any original URL with path/query and any base URL, the result has the base URL's scheme+netloc and the original's path+query+fragment
    - **Validates: Requirements 6.1**

- [x] 6. Implement UseCaseAPI client
  - [x] 6.1 Create `UseCaseAPI` in `qa-studio-ci-runner/src/api/usecases.py`
    - Constructor takes `APIClient`
    - `get_usecase(usecase_id)` → `GET /usecase/{usecase_id}`, returns dict
    - `get_steps(usecase_id)` → `GET /usecase/{usecase_id}/steps`, returns list
    - `get_variables(usecase_id)` → `GET /usecase/{usecase_id}/variables`, returns dict
    - `get_secrets(usecase_id)` → `GET /usecase/{usecase_id}/secrets`, returns list
    - `create_execution(usecase_id, trigger_type, base_url, variables, region, model_id)` → `POST /usecase/{usecase_id}/execute`, returns dict
    - All methods propagate `APIError` from `APIClient`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [ ]* 6.2 Write unit tests for UseCaseAPI (`tests/test_usecase_api.py`)
    - Test each method calls the correct endpoint path (mock `APIClient`)
    - Test `create_execution` sends trigger_type, base_url, variables in POST body
    - Test API error propagation (mock 404, 401, 500 responses)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [ ]* 6.3 Write property test for API error propagation
    - **Property 9: UseCaseAPI propagates API errors**
    - For any HTTP status code >= 400 and any response body, `UseCaseAPI` methods raise `APIError` with matching `status_code` and `response`
    - **Validates: Requirements 5.7**

- [x] 7. Checkpoint - Ensure utility and API client tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement ExecutionEngine local-only support
  - [x] 8.1 Add `execute_usecase_local()` method to `ExecutionEngine` in `qa-studio-ci-runner/src/execution/engine.py`
    - Make `execution_api` and `suite_execution_id` constructor params optional (default `None`) for local-only mode
    - Method signature: `execute_usecase_local(usecase_id, usecase_name, starting_url, steps, variables, secrets, region, model_id)`
    - Create artifacts directory at `/tmp/qa-studio-artifacts/<usecase-id>/`
    - Execute steps sequentially using Nova Act SDK (reuse `_resolve_variables`, `StepExecutor`)
    - Stop on first step failure, set status to `"failed"`
    - On all steps success, set status to `"success"`
    - Store video recording and logs in the local artifacts directory
    - Return `LocalExecutionResult` model (serialized via `model_dump(by_alias=True)`)
    - No API calls for status updates or artifact uploads
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 2.4, 2.5, 2.6, 2.7_

  - [ ]* 8.2 Write unit tests for `execute_usecase_local` (`tests/test_engine_local.py`)
    - Test all steps pass → status "success", all step results present
    - Test step N fails → status "failed", only steps 1..N have results
    - Test artifacts directory created at `/tmp/qa-studio-artifacts/<usecase-id>/`
    - Test no API calls made (mock `execution_api` and verify zero calls)
    - Test result contains all required fields (usecaseId, usecaseName, duration, steps, artifacts)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ]* 8.3 Write property tests for local execution
    - **Property 1: Local-only mode makes no remote state changes**
    - For any use case executed via `execute_usecase_local`, the mock `execution_api` receives zero calls
    - **Validates: Requirements 2.4, 2.6, 2.7**
    - **Property 4: Local artifacts stored at convention path**
    - For any UUID usecase_id, artifacts are stored under `/tmp/qa-studio-artifacts/<usecase-id>/`
    - **Validates: Requirements 2.5, 7.6**
    - **Property 12: Step failure stops execution and sets failed status**
    - For any step sequence where step N fails, result status is "failed" and only N step results are returned
    - **Validates: Requirements 7.3, 7.4**

- [x] 9. Implement variable merge utility
  - [x] 9.1 Create `merge_variables()` helper in `qa-studio-ci-runner/src/utils/variables.py`
    - Accept `api_variables` (dict) and `cli_overrides` (dict)
    - Return merged dict where CLI overrides take precedence
    - _Requirements: 6.2_

  - [ ]* 9.2 Write property test for variable merge
    - **Property 11: Variable merge with CLI precedence**
    - For any two dicts, merged result contains all keys from both, and for shared keys the CLI override value wins
    - **Validates: Requirements 6.2**

- [x] 10. Implement `run_usecase()` orchestration in main module
  - [x] 10.1 Add `run_usecase()` function to `qa-studio-ci-runner/src/main.py`
    - Parameters: `usecase_id`, `local_only`, `token_file`, `base_url`, `variables`, `region`, `model_id`, `timeout`
    - Load settings via `from_env_optional_auth()` if `token_file` provided, else `from_env()`
    - Validate AWS session via `validate_aws_session()`
    - Create `OAuthClient` with token file or client credentials
    - Create `APIClient` and `UseCaseAPI`
    - **Local-only path**: fetch usecase metadata/steps/variables/secrets via `UseCaseAPI`, apply `base_url` override via `apply_base_url_override()`, merge variables via `merge_variables()`, apply region/model_id overrides, call `engine.execute_usecase_local()`, print JSON to stdout, exit 0/1
    - **Remote path**: call `usecase_api.create_execution()` with overrides, fetch execution details via `ExecutionAPI`, execute with tracking (status updates, artifact uploads), print JSON to stdout, exit 0/1
    - On unexpected error: exit 2
    - _Requirements: 2.3, 2.4, 2.8, 2.9, 2.10, 2.11, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 10.2 Modify existing `run_runner()` to accept optional `token_file` parameter
    - When `token_file` provided: use `from_env_optional_auth()` for settings, create `OAuthClient` with token file
    - When `token_file` not provided: use existing `from_env()` and client credentials (unchanged behavior)
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ]* 10.3 Write unit tests for `run_usecase()` (`tests/test_main_usecase.py`)
    - Test local-only path: mocks `UseCaseAPI` calls, verifies `execute_usecase_local` called, verifies JSON output
    - Test remote path: mocks `create_execution`, verifies execution tracking flow
    - Test token file auth path: verifies `OAuthClient` created with token_file
    - Test exit code 0 on success, 1 on test failure, 2 on unexpected error
    - _Requirements: 2.8, 2.9, 2.10, 2.11, 3.6, 3.7, 3.8, 3.9_

  - [ ]* 10.4 Write property test for exit code mapping
    - **Property 2: Exit code reflects execution outcome**
    - For any execution result, exit code is 0 when status "success", 1 when "failed", 2 on exception
    - **Validates: Requirements 2.9, 2.10, 2.11, 3.6, 3.7, 3.8, 9.5**

- [x] 11. Update CLI parser with new flags and routing
  - [x] 11.1 Modify `qa-studio-ci-runner/src/cli/parser.py`
    - Make `--suite-id` optional (remove `required=True`)
    - Add `--usecase-id` option (default `None`)
    - Add `--local-only` flag (is_flag=True, default False)
    - Add `--token-file` option (default `None`)
    - Add validation: exactly one of `--suite-id` or `--usecase-id` required
    - Add validation: `--local-only` requires `--usecase-id`
    - Route `--suite-id` → `run_runner(token_file=token_file, ...)`
    - Route `--usecase-id` → `run_usecase(usecase_id, local_only, token_file, ...)`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 4.1_

  - [ ]* 11.2 Write unit tests for CLI parser (`tests/test_parser.py`)
    - Test neither flag → error message "Either --suite-id or --usecase-id is required"
    - Test both flags → error message "Cannot use both --suite-id and --usecase-id"
    - Test `--local-only` without `--usecase-id` → error message "--local-only requires --usecase-id"
    - Test `--suite-id` only → routes to `run_runner`
    - Test `--usecase-id` only → routes to `run_usecase`
    - Test `--usecase-id` + `--local-only` → routes to `run_usecase` with `local_only=True`
    - Test `--token-file` passed through to both paths
    - Test `--var` not in `key=value` format → error
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 4.1_

- [x] 12. Checkpoint - Ensure runner tests pass end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Implement CLI wrapper for `qa-studio run`
  - [x] 13.1 Create `execute_local()` in `qa-studio-cli/src/runner/executor.py`
    - Build subprocess command: `python -m qa_studio_ci_runner --usecase-id <id> --local-only --token-file ~/.qa-studio/token.json`
    - Append `--base-url <value>` if provided
    - Append `--var <key>=<value>` for each variable override
    - Run subprocess with `capture_output=True, text=True`
    - On exit code 0: parse stdout as JSON, return dict
    - On non-zero exit: raise `RuntimeError` with stderr content
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 13.2 Write unit tests for CLI wrapper (`tests/test_executor.py`)
    - Test command construction includes all flags (mock `subprocess.run`)
    - Test command construction with no optional flags
    - Test successful execution returns parsed JSON
    - Test failed execution raises `RuntimeError` with stderr
    - _Requirements: 8.1, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 13.3 Write property tests for CLI wrapper
    - **Property 13: CLI wrapper forwards all overrides to subprocess**
    - For any base URL and variable dict, the constructed command contains `--base-url <value>` and `--var <key>=<value>` for each override
    - **Validates: Requirements 8.4, 8.5**
    - **Property 14: CLI wrapper result handling**
    - For any valid JSON stdout with exit code 0, returns parsed dict; for any non-zero exit, raises `RuntimeError` containing stderr
    - **Validates: Requirements 8.6, 8.7**

- [x] 14. Verify backward compatibility
  - [x] 14.1 Add backward compatibility tests (`tests/test_backward_compat.py`)
    - Test `--suite-id` with client credentials → existing `run_runner` flow unchanged
    - Test `--suite-id` with `--token-file` → uses token file auth with suite execution
    - Test all existing CLI flags preserved and functional (`--base-url`, `--var`, `--region`, `--model-id`, `--verbose`, `--timeout`, `--keep-artifacts`)
    - Test exit code semantics: 0 for success, 1 for failure, 2 for error
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 15. Final checkpoint - Ensure all tests pass and coverage ≥70%
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest --cov=src tests/` in `qa-studio-ci-runner/` and verify ≥70% coverage
  - _Requirements: all_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All data models use Pydantic v2, consistent with existing codebase
- JSON output from the runner uses camelCase (via Pydantic aliases), per project convention
- The `qa-studio-ci-runner` existing behavior is fully preserved when using `--suite-id`
