# Implementation Plan: Nova Act Runner Integration

## Overview

Replace the fictional `nova_act_sdk` integration in the CI/CD runner with the real Nova Act SDK, adapting patterns from the `worker/` directory. Implementation proceeds bottom-up: data models → browser management → step execution → variable resolution → engine rewrite → API extension → wiring.

## Tasks

- [x] 1. Update dependencies and create data models
  - [x] 1.1 Update `cicd-runner/requirements.txt` to include `bedrock_agentcore==1.0.5` (nova-act is already present)
    - Verify `nova-act==3.1.157.0` is already listed
    - Add `bedrock_agentcore==1.0.5`
    - _Requirements: 8.1_
  - [x] 1.2 Create `cicd-runner/src/execution/models.py` with `StepResult` dataclass
    - Define `StepResult` with fields: `success: bool`, `act_id: str = ""`, `logs: str = ""`, `actual_value: str = ""`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 2. Implement BrowserManager
  - [x] 2.1 Create `cicd-runner/src/execution/browser_manager.py`
    - Implement `BrowserManager.__init__()` accepting region, execution_role_arn, optional s3_bucket and s3_prefix
    - Implement `create_and_start()` that creates browser via boto3 `bedrock-agentcore-control`, polls until READY, starts session via `BrowserClient`, returns `(ws_url, cdp_headers)`
    - Implement `_wait_for_browser_ready()` with 600s max wait, 1s polling interval, handling READY/FAILED/DELETED statuses
    - Implement `cleanup()` that stops browser session and deletes browser resource, idempotent and safe for finally blocks
    - Support PUBLIC network mode, configure S3 recording when bucket is provided
    - Follow patterns from `worker/browser.py`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_
  - [ ]* 2.2 Write unit tests for BrowserManager in `cicd-runner/tests/test_browser_manager.py`
    - Test create_and_start happy path with mocked boto3 and BrowserClient
    - Test polling with CREATING → READY sequence
    - Test polling timeout raises error
    - Test polling with FAILED status raises error
    - Test cleanup idempotency
    - Test S3 recording configuration when bucket is set vs not set
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.8_
  - [ ]* 2.3 Write property test for browser polling state machine
    - **Property 1: Browser polling state machine**
    - Generate random sequences of statuses from {CREATING, PENDING, READY, FAILED, DELETED}
    - Verify: returns success iff READY appears before FAILED/DELETED and before timeout
    - Verify: raises error immediately on FAILED/DELETED
    - **Validates: Requirements 2.2, 2.3, 2.4**

- [ ] 3. Implement StepExecutor
  - [x] 3.1 Create `cicd-runner/src/execution/step_executor.py`
    - Implement `StepExecutor.__init__()` accepting a `NovaAct` instance and optional secrets_resolver callable
    - Implement `execute()` dispatch method that routes by `step_type` to the correct handler
    - Implement `_execute_navigation()` using `nova.act(instruction)`, with support for `enable_advanced_click_types`
    - Implement `_execute_validation()` using `nova.act_get()` with correct schema (STRING_SCHEMA, NUMBER_SCHEMA, BOOL_SCHEMA) and all comparison operators (exact, contains, not_equal, greater_then, less_then, equals, case-insensitive variants)
    - Implement `_execute_retrieve_value()` using `nova.act_get()` with correct schema
    - Implement `_execute_url()` using `nova.go_to_url()`
    - Implement `_execute_assertion()` comparing runtime variables without Nova Act calls, supporting all operators
    - Implement `_execute_secret()` resolving secret, calling `nova.act()`, then `nova.page.keyboard.type()`
    - Implement `_execute_download()` triggering download via `nova.act()` with CDP interception
    - Unknown step types fall back to navigation
    - All handlers return `StepResult`
    - Follow patterns from `worker/navigation_step.py`, `worker/validation_step.py`, etc.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_
  - [ ]* 3.2 Write unit tests for StepExecutor in `cicd-runner/tests/test_step_executor.py`
    - Test dispatch for each step type with mocked NovaAct
    - Test unknown step type falls back to navigation
    - Test all validation operators for string, number, bool types
    - Test assertion step does not call any Nova Act methods
    - Test StepResult construction for success and failure
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.8_
  - [ ]* 3.3 Write property test for validation comparison correctness
    - **Property 4: Validation comparison correctness**
    - Generate random validation_type, operator, expected_value, actual_value combinations
    - Verify comparison result matches operator semantics
    - **Validates: Requirements 4.2**
  - [ ]* 3.4 Write property test for assertion without Nova Act calls
    - **Property 5: Assertion comparison without Nova Act calls**
    - Generate random assertion configurations with runtime variables
    - Verify correct comparison result AND verify no Nova Act methods were called on the mock
    - **Validates: Requirements 4.5**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement variable resolution and WorkflowManager
  - [x] 5.1 Create `cicd-runner/src/execution/workflow_manager.py`
    - Implement `WorkflowManager.__init__()` accepting s3_bucket
    - Implement `ensure_workflow()` that checks/creates workflow definition via boto3 `nova-act` client
    - Follow patterns from `worker/nova_act_workflow.py`
    - _Requirements: 3.5_
  - [x] 5.2 Update variable resolution in engine to support runtime variables
    - Modify `_replace_variables()` to accept both initial variables and runtime variables dicts
    - Runtime variables take precedence over initial variables
    - Unknown placeholders left unchanged with warning log
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - [ ]* 5.3 Write property test for variable resolution correctness
    - **Property 7: Variable resolution correctness**
    - Generate random strings with `{{placeholder}}` patterns and random variable dicts
    - Verify: known placeholders are replaced, unknown placeholders are left unchanged
    - **Validates: Requirements 6.1, 6.4**

- [ ] 6. Extend ExecutionAPI with step status update
  - [x] 6.1 Add `update_step_status()` method to `cicd-runner/src/api/executions.py`
    - Method signature: `async def update_step_status(self, usecase_id, execution_id, step_id, status, error_message=None, actual_value=None)`
    - Call `PATCH /usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/status`
    - Payload: `{status, error_message, actual_value}` (omit None fields)
    - Use `asyncio.to_thread()` for the synchronous HTTP call
    - _Requirements: 5.5_
  - [ ]* 6.2 Write unit tests for update_step_status in `cicd-runner/tests/test_execution_api.py`
    - Test correct API path construction
    - Test payload includes all provided fields
    - Test payload omits None fields
    - _Requirements: 5.5_

- [ ] 7. Rewrite ExecutionEngine to use real Nova Act
  - [x] 7.1 Rewrite `cicd-runner/src/execution/engine.py`
    - Remove fictional `nova_act_sdk` import
    - Add imports for `NovaAct`, `Workflow` from `nova_act`
    - Add imports for `BrowserManager`, `StepExecutor`, `WorkflowManager`, `StepResult`
    - Keep `execute_all()` unchanged (async with asyncio.gather)
    - Modify `execute_usecase()` to wrap synchronous execution in `asyncio.to_thread()`
    - Implement `_execute_usecase_sync()` as the synchronous entry point
    - Implement `_execute_with_nova_act()` synchronously:
      - Validate environment variables (BEDROCK_EXECUTION_ROLE, and mode-specific vars)
      - Create BrowserManager and call `create_and_start()`
      - Determine GA vs Preview mode from `USE_NOVA_ACT_GA` env var
      - Create NovaAct context manager with ws_url, cdp_headers, starting_page, headless=True
      - If GA mode: create Workflow, ensure workflow definition, pass to NovaAct
      - If Preview mode: pass nova_act_api_key to NovaAct
      - Set custom HTTP headers if present in execution details
      - Execute steps sequentially via StepExecutor
      - Report step status via ExecutionAPI after each step
      - Accumulate runtime variables from retrieve_value steps
      - Stop on first step failure
      - Always call BrowserManager.cleanup() in finally block
    - Keep `_replace_variables()` (now `_resolve_variables()`) with runtime variable support
    - Sanitize all error messages before API calls
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.6, 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.4, 7.1, 7.3, 8.2, 8.3, 8.4, 9.1, 9.2, 9.3, 9.4, 9.5, 10.1, 10.2, 10.3, 10.4_
  - [ ]* 7.2 Write unit tests for rewritten ExecutionEngine in `cicd-runner/tests/test_execution_engine.py`
    - Mock BrowserManager, StepExecutor, ExecutionAPI, WorkflowManager
    - Test execute_usecase status lifecycle (running → completed on success, running → failed on failure)
    - Test step status reporting after each step
    - Test runtime variable accumulation across steps
    - Test stop-on-failure: when step K fails, steps K+1..N are not executed
    - Test browser cleanup always called (success, failure, exception cases)
    - Test environment variable validation (missing BEDROCK_EXECUTION_ROLE raises error)
    - Test GA mode vs Preview mode selection
    - Test error message sanitization in API calls
    - _Requirements: 1.1, 1.3, 2.6, 3.1, 3.2, 3.3, 5.1, 5.2, 5.4, 7.1, 8.2, 9.1, 9.3, 9.4_
  - [ ]* 7.3 Write property test for stop-on-failure behavior
    - **Property 10: Stop-on-failure behavior**
    - Generate random step lists (1-20 steps) with failure injected at random position K
    - Verify: steps 0..K are executed, steps K+1..N are not, step K is recorded as failed
    - **Validates: Requirements 9.1**

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Update artifact handling and cleanup
  - [x] 9.1 Update `cicd-runner/src/execution/artifacts.py` to work with synchronous Nova Act
    - Remove async from `capture_step_screenshot` and `capture_step_trace` (Nova Act is sync)
    - Update to use Nova Act's page object for screenshots if needed
    - Ensure logs directory is created per execution and passed to NovaAct
    - _Requirements: 10.1, 10.4_
  - [ ]* 9.2 Write property test for error message sanitization
    - **Property 11: Error message sanitization**
    - Generate random strings with embedded URLs containing query params, email addresses, and token/key/secret path segments
    - Verify: sanitized output does not contain the original sensitive values
    - Note: this tests the existing `sanitize_error_message` function which is already implemented but validates it in the integration context
    - **Validates: Requirements 9.4**

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The implementation follows the worker's proven patterns but adapts them for the CI/CD runner's HTTP API context
- Nova Act and BrowserClient must be mocked in all unit tests (they require real AWS infrastructure)
- Property tests use the `hypothesis` library with minimum 100 iterations per property
- The existing `execute_all()` async interface is preserved; only the internal execution becomes synchronous
