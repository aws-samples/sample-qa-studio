# Implementation Plan: Worker Event Emission

## Overview

This implementation adds EventBridge event emission to the worker process after test execution completes. The worker will emit a `usecase.execution.completed` event to EventBridge, which triggers downstream cache building processes. The implementation follows a fire-and-forget pattern where event emission failures do not affect test execution outcomes.

## Tasks

- [x] 1. Create event emission module
  - [x] 1.1 Create `web-app/worker/event_emitter.py` module
    - Implement `emit_execution_completed_event` function with signature: `(usecase_id: str, execution_id: str, execution_status: str, region_name: str = None) -> None`
    - Initialize EventBridge client using `boto3.client('events', region_name=region_name)`
    - Create event detail with usecase_id, execution_id, execution_status, and ISO 8601 UTC timestamp
    - Call `put_events` with Source="qa-studio.worker", DetailType="usecase.execution.completed"
    - Implement fire-and-forget error handling (catch all exceptions, log, never raise)
    - Add INFO logging on success: "Emitted execution completed event: {usecase_id}/{execution_id} -> {execution_status}"
    - Add ERROR logging on client init failure: "Failed to initialize EventBridge client: {error}"
    - Add ERROR logging on emission failure: "Failed to emit execution completed event: {error}"
    - Add DEBUG logging for full event detail JSON
    - _Requirements: 1.1, 1.2, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 3.2, 3.3, 4.1, 4.2, 5.1, 5.2, 5.3, 5.4_

  - [x]* 1.2 Write unit tests for event_emitter.py
    - Create `web-app/worker/test_event_emitter.py`
    - Test successful event emission with status="success"
    - Test successful event emission with status="failed"
    - Test EventBridge client initialization failure
    - Test `put_events` raises `ClientError`
    - Test `put_events` raises generic `Exception`
    - Verify event structure (Source, DetailType, Detail fields)
    - Verify timestamp format matches ISO 8601 with UTC timezone
    - Verify logging at INFO level on success
    - Verify logging at ERROR level on failures
    - Verify function never raises exceptions
    - Use `unittest.mock.patch` on `boto3.client` to mock EventBridge client
    - Achieve at least 70% code coverage
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [ ]* 1.3 Write property test for event structure completeness
    - **Property 2: Event structure completeness**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.7**
    - Generate random usecase_id, execution_id, and execution_status using hypothesis
    - Mock EventBridge client to capture the event
    - Call `emit_execution_completed_event`
    - Assert event has correct Source, DetailType, and all Detail fields are present and non-empty
    - Run minimum 100 iterations

  - [ ]* 1.4 Write property test for timestamp format correctness
    - **Property 3: Timestamp format correctness**
    - **Validates: Requirements 2.6**
    - Generate random usecase_id, execution_id, and execution_status using hypothesis
    - Mock EventBridge client to capture the event
    - Call `emit_execution_completed_event`
    - Parse timestamp from Detail and assert it matches ISO 8601 format with UTC timezone (YYYY-MM-DDTHH:MM:SS.ffffffZ)
    - Verify timestamp is parseable by `datetime.fromisoformat()`
    - Run minimum 100 iterations

  - [ ]* 1.5 Write property test for fire-and-forget error handling
    - **Property 5: Fire-and-forget error handling**
    - **Validates: Requirements 1.5, 3.1, 3.2, 3.3**
    - Generate random usecase_id, execution_id, and execution_status using hypothesis
    - Mock EventBridge client to raise random exceptions (ClientError, Exception, etc.)
    - Call `emit_execution_completed_event`
    - Assert function returns without raising exception
    - Run minimum 100 iterations

- [x] 2. Integrate event emission into worker.py
  - [x] 2.1 Add import statement for event_emitter
    - Add `from event_emitter import emit_execution_completed_event` at top of `web-app/worker/worker.py`
    - _Requirements: 1.4_

  - [x] 2.2 Add event emission after successful execution
    - In `main_batch()` function after line ~237 (after `db_client.update_suite_execution_counters(execution_id, usecase_id, "success")`)
    - Add call: `emit_execution_completed_event(usecase_id, execution_id, "success", region_name)`
    - Place before the `logger.info(f"Execution {execution_id} completed successfully")` line
    - _Requirements: 1.1, 1.3, 1.4_

  - [x] 2.3 Add event emission after failed execution (main failure path)
    - In `main_batch()` function after line ~232 (after `db_client.update_suite_execution_counters(execution_id, usecase_id, "failed")`)
    - Add call: `emit_execution_completed_event(usecase_id, execution_id, "failed", region_name)`
    - Place before the `return False` statement
    - _Requirements: 1.2, 1.3, 1.4_

  - [x] 2.4 Add event emission after failed execution (Nova Act exception path)
    - In `main_batch()` function in the Nova Act exception handler after line ~217 (after `db_client.update_suite_execution_counters(execution_id, usecase_id, "failed")`)
    - Add call: `emit_execution_completed_event(usecase_id, execution_id, "failed", region_name)`
    - Place inside the try block before the except clause
    - _Requirements: 1.2, 1.3, 1.4_

  - [ ]* 2.5 Write property test for event emission after status update
    - **Property 4: Event emission after status update**
    - **Validates: Requirements 1.3, 3.4**
    - Mock both `db_client.update_execution_status` and `emit_execution_completed_event`
    - Execute worker flow (or simulate it)
    - Assert `emit_execution_completed_event` is called after `update_execution_status` completes
    - Verify call order using mock call history
    - Run minimum 100 iterations with hypothesis

  - [ ]* 2.6 Write property test for worker status independence
    - **Property 6: Worker status independence**
    - **Validates: Requirements 3.5**
    - Generate random execution scenarios (success/failure) using hypothesis
    - Mock `emit_execution_completed_event` to raise exceptions
    - Execute worker flow
    - Assert worker return value (True/False) is the same regardless of event emission outcome
    - Run minimum 100 iterations

- [x] 3. Checkpoint - Ensure all tests pass
  - Run all unit tests: `pytest web-app/worker/test_event_emitter.py -v`
  - Run all property tests with coverage
  - Verify no regressions in existing worker tests
  - Ensure all tests pass, ask the user if questions arise

- [x] 4. Update IAM permissions (if needed)
  - [x] 4.1 Verify worker IAM role has EventBridge permissions
    - Check CDK stack for worker Lambda/ECS task role
    - Verify role has `events:PutEvents` permission
    - If missing, add permission to CDK stack with resource constraint to specific event bus (or default bus)
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 4.2 Write integration test for IAM permissions
    - Create test that verifies worker can emit events to EventBridge
    - Use real AWS credentials in test environment (not mocked)
    - Assert event emission succeeds without permission errors
    - This test may need to run in CI/CD environment with proper AWS credentials

- [x] 5. Update documentation
  - [x] 5.1 Update worker module documentation
    - Document the new event emission behavior in worker.py docstring or README
    - Explain the fire-and-forget pattern and error handling
    - Document the event structure and fields
    - Add example of emitted event JSON
    - _Requirements: All (documentation for developers)_

  - [x] 5.2 Update architecture documentation
    - Document the event flow from worker to EventBridge to Cache Builder
    - Add sequence diagram if not already present in design doc
    - Explain the relationship between worker events and DynamoDB client events
    - _Requirements: All (documentation for developers and QA engineers)_

- [x] 6. Final checkpoint - Ensure all tests pass
  - Run full test suite: `pytest web-app/worker/ -v --cov=web-app/worker/event_emitter`
  - Verify code coverage is at least 70% for event_emitter.py
  - Run any existing integration tests
  - Ensure all tests pass, ask the user if questions arise

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The implementation uses Python with boto3 for AWS SDK
- Property tests use hypothesis library with minimum 100 iterations
- Fire-and-forget pattern ensures event emission never blocks or fails test execution
- Event emission is independent of existing DynamoDB client event emission
- No DynamoDB schema changes required
- IAM permissions may already exist; verify before adding
