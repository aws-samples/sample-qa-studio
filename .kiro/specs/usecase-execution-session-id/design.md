# Usecase Execution Session ID Bugfix Design

## Overview

The cicd-runner's `ExecutionEngine._run_steps_with_nova` opens a NovaAct context but never calls `nova.get_session_id()` to capture the Nova Act session ID, and `ExecutionAPI` has no method to persist it. This causes the `nova_session_id` field to be missing from execution records in DynamoDB, which breaks the S3 URL generation endpoint (`generate_s3_url.py`) — it cannot construct the S3 key prefix for trace HTML files without the session ID.

The fix is two-fold:
1. Extend the existing PATCH `/api/usecases/{id}/executions/{executionId}/status` endpoint to accept an optional `nova_session_id` field.
2. Add an `update_session_id` method to `ExecutionAPI` and call it from `_run_steps_with_nova` after opening the NovaAct context.

This mirrors the worker path (`wizard_worker.py`) which calls `nova.get_session_id()` and persists it via `db_client.update_execution_session_id()`.

## Glossary

- **Bug_Condition (C)**: An execution runs through the cicd-runner path (`ExecutionEngine._run_steps_with_nova`) — the `nova_session_id` is never captured or persisted.
- **Property (P)**: After the NovaAct context opens, `nova.get_session_id()` is called and the result is persisted to the execution record via the API.
- **Preservation**: The worker path's session ID capture, existing step execution, status updates, artifact uploads, and all non-session-ID behavior must remain unchanged.
- **`_run_steps_with_nova`**: The method in `cicd-runner/src/execution/engine.py` that opens the NovaAct context and executes steps sequentially.
- **`ExecutionAPI`**: The API client class in `cicd-runner/src/api/executions.py` that wraps HTTP calls to the backend.
- **`nova_session_id`**: The DynamoDB attribute on the `EXECUTION#{id}` record that stores the Nova Act session identifier, used by `generate_s3_url.py` to construct S3 key prefixes for trace files.

## Bug Details

### Fault Condition

The bug manifests when a usecase execution runs through the cicd-runner path. The `_run_steps_with_nova` method opens a `NovaAct` context but never calls `nova.get_session_id()`, and `ExecutionAPI` has no method to persist the session ID to the backend. The DynamoDB execution record's `nova_session_id` attribute remains empty.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ExecutionContext
  OUTPUT: boolean

  RETURN input.executionPath == "cicd-runner"
         AND input.novaActContextOpened == true
         AND input.executionRecord.nova_session_id IS EMPTY
END FUNCTION
```

### Examples

- Execution `019c76ba-728d-fa40-f224-eae7164fd2b4` ran via cicd-runner. The NovaAct context opened successfully, steps executed, but `nova_session_id` was never written. The S3 URL endpoint returned: `"No Nova Act session ID found for execution: 019c76ba-728d-fa40-f224-eae7164fd2b4"`.
- A worker-path execution for the same usecase correctly has `nova_session_id` populated and S3 URL generation works.
- A cicd-runner execution that fails before opening the NovaAct context would not have a session ID either, but that is expected (no NovaAct session was created).

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Worker path (`wizard_worker.py`) must continue to capture and persist `nova_session_id` via `db_client.update_execution_session_id()`.
- All existing step execution, step status reporting, artifact capture/upload in `_run_steps_with_nova` must remain identical.
- The existing PATCH `/api/usecases/{id}/executions/{executionId}/status` endpoint must continue to handle `status`, `error_message`, timestamps exactly as before when `nova_session_id` is not provided.
- `nova.get_session_id()` failure or returning `None` must not interrupt step execution (non-fatal).

**Scope:**
All inputs that do NOT involve the cicd-runner's NovaAct session ID capture should be completely unaffected by this fix. This includes:
- Worker-path executions
- Step execution logic
- Artifact upload logic
- Status update calls without `nova_session_id`
- Frontend rendering (no frontend changes needed — it already reads `nova_session_id` from the record)

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is straightforward:

1. **Missing `nova.get_session_id()` call**: In `_run_steps_with_nova` (engine.py line ~290), after `with NovaAct(**nova_kwargs) as nova:`, there is no call to `nova.get_session_id()`. The worker path has this call at line 247 and 472 of `wizard_worker.py`.

2. **Missing API method**: `ExecutionAPI` (executions.py) has `update_status` and `update_step_status` but no method to persist the session ID. The cicd-runner communicates with the backend exclusively via HTTP API (it has no direct DynamoDB access), so a new API method is needed.

3. **Backend endpoint doesn't accept `nova_session_id`**: The existing PATCH `update_execution_status.py` endpoint only handles `status` and `error_message` fields. It needs to also accept and persist `nova_session_id`.

## Correctness Properties

Property 1: Fault Condition - Session ID Captured and Persisted via CICD Runner

_For any_ execution that runs through the cicd-runner path where the NovaAct context opens successfully and `nova.get_session_id()` returns a non-empty string, the fixed `_run_steps_with_nova` SHALL call `nova.get_session_id()` and persist the result to the execution record via the API, such that the DynamoDB record's `nova_session_id` attribute is populated.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Existing Behavior Unchanged

_For any_ execution where the bug condition does NOT hold (worker-path executions, status updates without `nova_session_id`, step execution logic), the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing step execution, status reporting, artifact handling, and worker-path session ID capture.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `lambdas/endpoints/update_execution_status.py`

**Changes**:
1. **Accept optional `nova_session_id` in request body**: Parse `nova_session_id` from the body alongside `status` and `error_message`.
2. **Conditionally add to DynamoDB update expression**: If `nova_session_id` is provided and non-empty, add `SET nova_session_id = :nova_session_id` to the update expression.
3. **No new endpoint needed**: Extending the existing PATCH endpoint keeps the API surface minimal and follows the established pattern. The `nova_session_id` is optional — existing callers are unaffected.

**File**: `cicd-runner/src/api/executions.py`

**Changes**:
1. **Add `update_session_id` method**: New async method that calls PATCH `/usecase/{usecase_id}/executions/{execution_id}/status` with `{"status": "running", "nova_session_id": session_id}`. Alternatively, a dedicated thin method that only sends `nova_session_id` alongside the current status. Since the execution is already in `running` state at this point, re-sending `status: "running"` is safe and idempotent.

**File**: `cicd-runner/src/execution/engine.py`

**Changes**:
1. **Call `nova.get_session_id()` after NovaAct context opens**: Inside `_run_steps_with_nova`, immediately after `with NovaAct(**nova_kwargs) as nova:` and before step execution, call `nova.get_session_id()`.
2. **Persist session ID via API**: Call `self._run_async(self.execution_api.update_session_id(...))` with the captured session ID.
3. **Wrap in try/except**: Session ID capture failure must be non-fatal (requirement 3.4). Log a warning and continue.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis.

**Test Plan**: Write tests that mock the NovaAct context and verify whether `nova.get_session_id()` is called and whether the session ID is persisted via the API. Run on unfixed code to observe failures.

**Test Cases**:
1. **Engine Session ID Capture Test**: Mock `NovaAct` and verify `get_session_id()` is called after context opens (will fail on unfixed code — no such call exists).
2. **ExecutionAPI Session ID Method Test**: Verify `ExecutionAPI` has an `update_session_id` method (will fail on unfixed code — method doesn't exist).
3. **Endpoint Session ID Acceptance Test**: Send a PATCH request with `nova_session_id` in the body and verify it's persisted to DynamoDB (will fail on unfixed code — field is ignored).

**Expected Counterexamples**:
- `nova.get_session_id()` is never called in `_run_steps_with_nova`
- `ExecutionAPI` has no `update_session_id` method
- PATCH endpoint ignores `nova_session_id` field in request body

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := _run_steps_with_nova_fixed(input)
  ASSERT nova.get_session_id() was called
  ASSERT execution_api.update_session_id() was called with correct session_id
  ASSERT DynamoDB record has nova_session_id populated
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT update_execution_status_original(input) = update_execution_status_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for status-only updates (no `nova_session_id`), then write property-based tests capturing that behavior.

**Test Cases**:
1. **Status Update Preservation**: Verify PATCH calls with only `status` and `error_message` (no `nova_session_id`) produce identical DynamoDB updates before and after the fix.
2. **Step Execution Preservation**: Verify step execution, status reporting, and artifact capture in `_run_steps_with_nova` are unchanged.
3. **Worker Path Preservation**: Verify `wizard_worker.py` session ID capture is unaffected.
4. **Session ID Failure Resilience**: Verify that if `nova.get_session_id()` raises an exception or returns `None`, step execution continues uninterrupted.

### Unit Tests

- Test `update_execution_status.py` Lambda: PATCH with `nova_session_id` persists it to DynamoDB
- Test `update_execution_status.py` Lambda: PATCH without `nova_session_id` behaves identically to before
- Test `ExecutionAPI.update_session_id`: Calls correct endpoint with correct payload
- Test `_run_steps_with_nova`: Calls `nova.get_session_id()` and `execution_api.update_session_id()`
- Test `_run_steps_with_nova`: Session ID capture failure is non-fatal
- Test `_run_steps_with_nova`: `nova.get_session_id()` returning `None` is handled gracefully

### Property-Based Tests

- Generate random execution contexts (with/without `nova_session_id` in PATCH body) and verify the endpoint correctly persists or ignores the field
- Generate random step lists and verify step execution behavior is identical with and without the session ID capture code

### Integration Tests

- End-to-end: cicd-runner executes a usecase, session ID is captured, DynamoDB record has `nova_session_id`, and `generate_s3_url.py` returns a valid signed URL
- End-to-end: worker path execution still captures session ID correctly
