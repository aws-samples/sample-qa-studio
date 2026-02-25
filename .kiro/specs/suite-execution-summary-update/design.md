# Suite Execution Summary Update Bugfix Design

## Overview

When a test suite is executed via the CI/CD runner, three pieces of the status-propagation chain are broken:

1. `update_suite_execution_status` (PATCH endpoint) updates the suite execution record but never propagates results to the test suite summary record (`TEST_SUITES/SUITE#{suite_id}`).
2. `update_execution_status` (per-usecase PATCH endpoint) updates the usecase execution record but never touches suite execution counters (`completed_usecases`, `successful_usecases`, `failed_usecases`, `running_usecases`).
3. `last_execution_id` is never written to the test suite record — neither in the CI/CD path nor in the ECS worker path (`handle_task_state_change.update_test_suite_summary`).

The ECS worker path in `handle_task_state_change.py` already implements the correct counter-update and suite-completion logic (functions `update_suite_execution_counters`, `check_suite_completion`, `update_test_suite_summary`). The fix reuses these existing patterns in the CI/CD runner endpoints and also patches the ECS path to include `last_execution_id`.

## Glossary

- **Bug_Condition (C)**: A CI/CD runner calls `update_execution_status` with a terminal usecase status or calls `update_suite_execution_status` with a terminal suite status, and the execution belongs to a suite.
- **Property (P)**: Suite execution counters are atomically updated per-usecase completion; the test suite summary record is updated with `last_execution_status`, `last_execution_time`, `last_execution_id`, `last_successful_count`, `last_failed_count` when the suite reaches a terminal status.
- **Preservation**: All non-suite usecase status updates, non-terminal suite status updates, mouse/UI-triggered ECS worker path behavior, EventBridge event publishing, and response shapes must remain unchanged.
- **`update_execution_status`**: Lambda in `lambdas/endpoints/update_execution_status.py` — PATCH endpoint for per-usecase execution status updates.
- **`update_suite_execution_status`**: Lambda in `lambdas/endpoints/update_suite_execution_status.py` — PATCH endpoint for suite-level execution status updates.
- **`handle_task_state_change`**: Lambda in `lambdas/endpoints/handle_task_state_change.py` — EventBridge handler for ECS task state changes (reference implementation for suite tracking).
- **Suite Execution Record**: DynamoDB record with PK `SUITE_EXECUTION#{suite_id}`, SK `EXECUTION#{suite_execution_id}` — tracks counters and overall suite status.
- **Test Suite Summary Record**: DynamoDB record with PK `TEST_SUITES`, SK `SUITE#{suite_id}` — stores `last_execution_status`, `last_execution_time`, `last_execution_id`, counts.

## Bug Details

### Fault Condition

The bug manifests in two distinct scenarios within the CI/CD runner flow:

**Scenario A**: When `update_execution_status` is called with a terminal usecase status (`success` or `failed`) and the execution record has a `suite_execution_id`, the suite execution counters are never updated.

**Scenario B**: When `update_suite_execution_status` is called with a terminal suite status (`completed`, `partial`, or `failed`), the test suite summary record is never updated with execution results.

**Scenario C**: `last_execution_id` is never set on the test suite record in any path — neither CI/CD runner nor ECS worker.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type APIRequest
  OUTPUT: boolean

  // Scenario A: per-usecase terminal status with suite membership
  IF input.endpoint == "update_execution_status"
     AND input.body.status IN ['success', 'failed']
     AND executionRecord(input.usecase_id, input.execution_id).suite_execution_id IS NOT NULL
  THEN RETURN TRUE

  // Scenario B: suite-level terminal status
  IF input.endpoint == "update_suite_execution_status"
     AND input.body.status IN ['completed', 'partial', 'failed']
  THEN RETURN TRUE

  // Scenario C: ECS worker path completing a suite (last_execution_id missing)
  IF input.endpoint == "handle_task_state_change"
     AND execution.suite_execution_id IS NOT NULL
     AND suiteExecution.completed_usecases == suiteExecution.total_usecases
  THEN RETURN TRUE

  RETURN FALSE
END FUNCTION
```

### Examples

- CI/CD runner calls `PATCH /api/usecases/{id}/executions/{execId}/status` with `{"status": "success"}` for an execution that has `suite_execution_id`. Expected: suite execution `completed_usecases` increments by 1, `successful_usecases` increments by 1, `running_usecases` decrements by 1. Actual: no counter changes, all remain at initial values.
- CI/CD runner calls `PATCH /api/test-suites/{suiteId}/executions/{execId}/status` with `{"status": "completed"}`. Expected: test suite record updated with `last_execution_status="completed"`, `last_execution_time`, `last_execution_id`, counts. Actual: only suite execution record status is updated, test suite summary untouched.
- ECS worker completes all usecases in a suite, `check_suite_completion` calls `update_test_suite_summary`. Expected: `last_execution_id` set on test suite record. Actual: `last_execution_id` is not included in the update expression.
- CI/CD runner calls `PATCH /api/usecases/{id}/executions/{execId}/status` with `{"status": "success"}` for an execution that has NO `suite_execution_id`. Expected: no suite counter updates (unchanged behavior). Actual: no suite counter updates (correct).


## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Non-suite usecase status updates (executions without `suite_execution_id`) must continue to update only the execution record, with no suite counter side-effects
- Non-terminal suite status updates (`running`) must continue to update only the suite execution record status
- EventBridge event publishing on usecase status changes must remain unchanged (same detail shape, same source/detail-type)
- Response shapes for both endpoints must remain identical (same JSON keys, same status codes)
- ECS worker path (`handle_task_state_change`) must continue to function independently — the existing `update_suite_execution_tracking` → `update_suite_execution_counters` → `check_suite_completion` chain must not be affected
- 404 responses for non-existent suite executions must remain unchanged
- `nova_session_id` handling in `update_execution_status` must remain unchanged

**Scope:**
All inputs that do NOT involve terminal status updates for suite-member executions should be completely unaffected by this fix. This includes:
- `update_execution_status` with `status=pending` or `status=running`
- `update_execution_status` for executions without `suite_execution_id`
- `update_suite_execution_status` with `status=running`
- All GET endpoints (read-only)
- All other PATCH/POST endpoints

## Hypothesized Root Cause

Based on code analysis, the root causes are confirmed (not hypothesized):

1. **`update_execution_status` missing suite counter logic**: The endpoint at `lambdas/endpoints/update_execution_status.py` performs a single `update_item` on the execution record and publishes an EventBridge event. It never reads `suite_execution_id` or `suite_id` from the execution record and never calls any suite counter update logic. The ECS worker path handles this in `handle_task_state_change.update_suite_execution_tracking`, but the CI/CD runner path bypasses that entirely since it calls the PATCH endpoint directly.

2. **`update_suite_execution_status` missing test suite summary propagation**: The endpoint at `lambdas/endpoints/update_suite_execution_status.py` updates the suite execution record's `status`, `completed_at`, and `duration_seconds` fields. It never reads the suite execution counters and never updates the test suite summary record (`TEST_SUITES/SUITE#{suite_id}`). The ECS worker path handles this in `handle_task_state_change.check_suite_completion` → `update_test_suite_summary`, but again the CI/CD runner path bypasses that.

3. **`update_test_suite_summary` missing `last_execution_id`**: The function in `handle_task_state_change.py` (line 641) builds an UpdateExpression that sets `last_execution_status`, `last_successful_count`, `last_failed_count`, and `last_execution_time` — but omits `last_execution_id`. The `suite_execution_id` is available in the caller (`check_suite_completion`) but is never passed down. The `get_suite_update_expression` helper in `test_suite_schema.py` already supports `last_execution_id` as a parameter, so the schema layer is ready.

## Correctness Properties

Property 1: Fault Condition — Suite Execution Counters Updated on Usecase Terminal Status

_For any_ usecase execution status update where the status is terminal (`success` or `failed`) and the execution record has a `suite_execution_id` and `suite_id`, the fixed `update_execution_status` endpoint SHALL atomically update the suite execution counters: incrementing `completed_usecases` and the appropriate success/failure counter, and decrementing `running_usecases`.

**Validates: Requirements 2.2**

Property 2: Fault Condition — Test Suite Summary Updated on Suite Terminal Status

_For any_ suite execution status update where the status is terminal (`completed`, `partial`, or `failed`), the fixed `update_suite_execution_status` endpoint SHALL read the suite execution counters and update the test suite summary record (`TEST_SUITES/SUITE#{suite_id}`) with `last_execution_status`, `last_execution_time`, `last_execution_id`, `last_successful_count`, and `last_failed_count`.

**Validates: Requirements 2.1, 2.3**

Property 3: Fault Condition — `last_execution_id` Set in ECS Worker Path

_For any_ suite execution that completes via the ECS worker path, the fixed `update_test_suite_summary` function SHALL include `last_execution_id` in the test suite summary update.

**Validates: Requirements 2.3**

Property 4: Preservation — Non-Suite Usecase Updates Unchanged

_For any_ usecase execution status update where the execution record does NOT have a `suite_execution_id`, the fixed `update_execution_status` endpoint SHALL produce exactly the same DynamoDB operations and response as the original code — no suite counter updates attempted.

**Validates: Requirements 3.1**

Property 5: Preservation — Non-Terminal Suite Updates Unchanged

_For any_ suite execution status update where the status is non-terminal (`running`), the fixed `update_suite_execution_status` endpoint SHALL produce exactly the same behavior as the original code — only the suite execution record status is updated, no test suite summary propagation.

**Validates: Requirements 3.2**

Property 6: Preservation — Response Shapes Unchanged

_For any_ valid request to either endpoint, the response body shape and status codes SHALL remain identical to the original code.

**Validates: Requirements 3.1, 3.2, 3.3**

## Fix Implementation

### Changes Required

**File 1**: `lambdas/endpoints/update_execution_status.py`

**Function**: `handler`

**Specific Changes**:
1. **Read suite context from execution record**: After the existing `get_item` call that checks if the execution exists, extract `suite_execution_id` and `suite_id` from the returned item.
2. **Add suite counter update for terminal statuses**: After the existing `update_item` call on the execution record, if `status` is terminal (`success` or `failed`) AND `suite_execution_id` is present, perform an atomic counter update on the suite execution record using `ADD` expressions (same pattern as `handle_task_state_change.update_suite_execution_counters`):
   - `success` → `ADD completed_usecases :inc, successful_usecases :inc, running_usecases :dec`
   - `failed` → `ADD completed_usecases :inc, failed_usecases :inc, running_usecases :dec`
3. **Import `test_suite_schema` helpers**: Import `get_suite_execution_pk` and `get_execution_sk` for building the correct DynamoDB keys.
4. **Error handling**: Wrap the suite counter update in a try/except — log errors but don't fail the main request (same pattern as EventBridge publishing).

---

**File 2**: `lambdas/endpoints/update_suite_execution_status.py`

**Function**: `handler`

**Specific Changes**:
1. **Read suite execution counters on terminal status**: When `status` is terminal (`completed`, `partial`, `failed`), after the existing `get_item` call, extract `successful_usecases`, `failed_usecases`, and `suite_id` from the suite execution record item (already fetched, no extra DynamoDB call needed).
2. **Update test suite summary record**: After updating the suite execution record, perform an `update_item` on the test suite summary record (`PK=TEST_SUITES`, `SK=SUITE#{suite_id}`) setting `last_execution_status`, `last_execution_time`, `last_execution_id`, `last_successful_count`, `last_failed_count`.
3. **Extract `suite_id` from the suite execution record**: The `suite_id` is already stored on the suite execution record (set during `create_suite_execution_record`). Alternatively, it's available from the path parameter.
4. **Error handling**: Wrap the summary update in a try/except — log errors but don't fail the main request.

---

**File 3**: `lambdas/endpoints/handle_task_state_change.py`

**Function**: `update_test_suite_summary`

**Specific Changes**:
1. **Add `suite_execution_id` parameter**: Add a new parameter to accept the suite execution ID.
2. **Include `last_execution_id` in update expression**: Add `last_execution_id = :exec_id` to the UpdateExpression and `:exec_id` to ExpressionAttributeValues.

**Function**: `check_suite_completion`

**Specific Changes**:
1. **Pass `suite_execution_id` to `update_test_suite_summary`**: Update the call to include the suite execution ID that's already available in scope.

### DRY Consideration

The suite counter update logic in `update_execution_status.py` will mirror `handle_task_state_change.update_suite_execution_counters`. However, extracting a shared module would couple the API endpoint Lambda to the EventBridge handler Lambda. Since these are separate Lambda deployment packages, the duplication is acceptable — the logic is a single atomic DynamoDB `ADD` expression (3 lines). If this pattern grows, consider extracting to a shared `suite_tracking_utils.py` module.

Similarly, the test suite summary update in `update_suite_execution_status.py` mirrors `handle_task_state_change.update_test_suite_summary`. The same deployment-boundary argument applies. The `test_suite_schema.py` helpers (`get_suite_execution_pk`, `get_execution_sk`) are already shared and should be reused.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm the root cause analysis.

**Test Plan**: Write tests that call the unfixed endpoints with terminal statuses for suite-member executions and assert that suite counters and test suite summary are updated. These tests will fail on unfixed code, confirming the bug.

**Test Cases**:
1. **Counter Update Missing Test**: Call `update_execution_status` with `status=success` for an execution with `suite_execution_id`. Assert `update_item` is called on the suite execution record with `ADD` counters. (Will fail on unfixed code — no such call exists.)
2. **Summary Propagation Missing Test**: Call `update_suite_execution_status` with `status=completed`. Assert `update_item` is called on `TEST_SUITES/SUITE#{suite_id}` with `last_execution_status`, `last_execution_id`, counts. (Will fail on unfixed code — no such call exists.)
3. **`last_execution_id` Missing Test**: Call `update_test_suite_summary` and assert the UpdateExpression includes `last_execution_id`. (Will fail on unfixed code — field is omitted.)

**Expected Counterexamples**:
- `update_execution_status`: DynamoDB `update_item` is called exactly once (only on execution record), never on suite execution record
- `update_suite_execution_status`: DynamoDB `update_item` is called exactly once (only on suite execution record), never on test suite summary record
- `update_test_suite_summary`: UpdateExpression does not contain `last_execution_id`

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed functions produce the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedEndpoint(input)
  ASSERT expectedBehavior(result)
END FOR
```

Specifically:
- For `update_execution_status` with terminal status + suite membership: assert atomic counter update on suite execution record
- For `update_suite_execution_status` with terminal status: assert test suite summary record updated with all five fields
- For `update_test_suite_summary`: assert `last_execution_id` in UpdateExpression

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed functions produce the same result as the original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalFunction(input) = fixedFunction(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: The existing preservation tests in `test_update_execution_status.py` (classes `TestStatusUpdatePreservation`, `TestEventBridgePreservation`) already cover the non-suite path. New preservation tests should verify that non-suite executions trigger zero additional DynamoDB calls.

**Test Cases**:
1. **Non-Suite Execution Preservation**: For any execution without `suite_execution_id`, verify `update_item` is called exactly once (only on execution record) — same as before the fix.
2. **Non-Terminal Suite Status Preservation**: For `update_suite_execution_status` with `status=running`, verify `update_item` is called exactly once (only on suite execution record) — no test suite summary update.
3. **Response Shape Preservation**: For both endpoints, verify response body keys and status codes are identical to pre-fix behavior.
4. **EventBridge Preservation**: For `update_execution_status`, verify EventBridge event detail shape is unchanged regardless of suite membership.

### Unit Tests

- `test_update_execution_status.py`: Add tests for suite counter updates on terminal status with suite membership
- `test_update_execution_status.py`: Add tests verifying no suite counter updates for non-suite executions
- `test_update_execution_status.py`: Add tests verifying no suite counter updates for non-terminal statuses
- `test_update_suite_execution_status.py` (new file): Tests for test suite summary propagation on terminal status
- `test_update_suite_execution_status.py`: Tests for no summary propagation on non-terminal status
- `test_update_suite_execution_status.py`: Tests for 404 handling unchanged
- `test_handle_task_state_change.py`: Tests for `last_execution_id` inclusion in `update_test_suite_summary`

### Property-Based Tests

- Generate random terminal statuses (`success`/`failed`) with random suite_execution_id presence/absence and verify counter update behavior is correct across all combinations
- Generate random suite terminal statuses (`completed`/`partial`/`failed`) with random counter values and verify test suite summary is always updated with correct fields
- Generate random non-terminal statuses and verify zero additional DynamoDB calls (preservation)

### Integration Tests

- Full CI/CD runner flow: create suite execution → update individual usecase statuses → update suite execution status → verify test suite summary record has correct `last_execution_status`, `last_execution_time`, `last_execution_id`, counts
- Mixed success/failure flow: some usecases succeed, some fail → verify counters are correct and final suite status is `partial`
- ECS worker path: verify `last_execution_id` is now set on test suite record after suite completion
