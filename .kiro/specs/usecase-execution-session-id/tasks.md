# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Fault Condition** - Nova Session ID Never Captured in CICD Runner Path
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to the concrete failing case: `_run_steps_with_nova` opens a NovaAct context but never calls `nova.get_session_id()` and never persists the session ID via the API
  - Create test file `qa-studio-ci-runner/tests/test_engine_session_id.py`
  - Mock `NovaAct` context manager so that `nova.get_session_id()` returns a known session ID string (e.g. `"session-abc-123"`)
  - Mock `ExecutionAPI` (specifically `update_status`, `update_step_status`, and assert that a session-ID-persisting call is made)
  - Mock `StepExecutor` to return successful `StepResult` for each step
  - Mock `ArtifactCapture` and `ArtifactUploader` as no-ops
  - Call `_run_steps_with_nova` with a minimal single-step execution
  - Assert: `nova.get_session_id()` was called after the NovaAct context opened
  - Assert: the session ID was persisted via an API call (e.g. `execution_api.update_session_id` or equivalent)
  - Run test on UNFIXED code — expect FAILURE (confirms bug: `get_session_id` is never called, no persist method exists)
  - Document counterexamples: `get_session_id()` not called; `ExecutionAPI` has no `update_session_id` method
  - _Requirements: 1.1, 1.2, 2.1, 2.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Existing Step Execution and Status Update Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Create test file `lambdas/endpoints/test_update_execution_status.py` for Lambda endpoint preservation
  - Create test section in `qa-studio-ci-runner/tests/test_engine_session_id.py` for engine preservation
  - **Lambda endpoint preservation (observation-first)**:
    - Observe on UNFIXED code: PATCH with `{"status": "running"}` sets `status`, `started_at`, `updated_at` in DynamoDB — no `nova_session_id` attribute touched
    - Observe on UNFIXED code: PATCH with `{"status": "failed", "error_message": "err"}` sets `status`, `completed_at`, `updated_at`, `error_message`
    - Write property-based test: for all valid status values and optional error_message combinations (without `nova_session_id`), the endpoint produces the same DynamoDB update expression fields as before
    - Verify tests PASS on UNFIXED code
  - **Engine step execution preservation (observation-first)**:
    - Observe on UNFIXED code: `_run_steps_with_nova` executes all steps sequentially, calls `update_step_status` per step, captures artifacts, stops on first failure
    - Write property-based test: for any list of steps (1–5 steps, mix of success/failure), the engine calls `update_step_status` for each step up to and including the first failure, and returns `{"success": False}` on failure or `{"success": True}` when all pass
    - Verify tests PASS on UNFIXED code
  - **Session ID failure resilience preservation**:
    - Observe on UNFIXED code: step execution completes regardless of any session-ID-related state (trivially true since no session ID code exists yet)
    - Write test: when `nova.get_session_id()` raises an exception, step execution still completes and returns results (this test will be meaningful after the fix, but should also pass on unfixed code if guarded properly)
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Fix: Capture and persist Nova session ID in qa-studio-ci-runner path

  - [x] 3.1 Extend PATCH endpoint to accept optional `nova_session_id`
    - In `lambdas/endpoints/update_execution_status.py`:
    - Parse `nova_session_id` from request body: `nova_session_id = body.get('nova_session_id')`
    - If `nova_session_id` is provided and non-empty, append `nova_session_id = :nova_session_id` to the DynamoDB `UpdateExpression`
    - Add `:nova_session_id` to `ExpressionAttributeValues` as `{'S': nova_session_id}`
    - Existing callers that omit `nova_session_id` are completely unaffected (field is optional)
    - Write unit tests in `lambdas/endpoints/test_update_execution_status.py`:
      - Test PATCH with `nova_session_id` persists it to DynamoDB
      - Test PATCH without `nova_session_id` does NOT add it to the update expression (backward compatible)
      - Test PATCH with empty string `nova_session_id` does NOT add it to the update expression
    - _Bug_Condition: isBugCondition(input) where input.executionPath == "qa-studio-ci-runner" AND nova_session_id IS EMPTY_
    - _Expected_Behavior: PATCH endpoint accepts and persists optional nova_session_id to DynamoDB record_
    - _Preservation: Existing status/error_message/timestamp handling unchanged when nova_session_id not provided_
    - _Requirements: 2.2, 3.3_

  - [x] 3.2 Add `update_session_id` method to `ExecutionAPI`
    - In `qa-studio-ci-runner/src/api/executions.py`:
    - Add async method `update_session_id(self, usecase_id: str, execution_id: str, session_id: str) -> Dict[str, Any]`
    - Method calls PATCH `/usecase/{usecase_id}/executions/{execution_id}/status` with `{"status": "running", "nova_session_id": session_id}`
    - Re-sending `status: "running"` is safe and idempotent (execution is already running at this point)
    - Write unit tests in `qa-studio-ci-runner/tests/test_execution_api.py`:
      - Test `update_session_id` calls `client.patch` with correct URL and payload
      - Test `update_session_id` propagates API errors
    - _Bug_Condition: ExecutionAPI has no method to persist session ID_
    - _Expected_Behavior: New update_session_id method calls PATCH endpoint with nova_session_id in payload_
    - _Preservation: Existing update_status, update_step_status, update_suite_status methods unchanged_
    - _Requirements: 2.2_

  - [x] 3.3 Call `nova.get_session_id()` and persist in `_run_steps_with_nova`
    - In `qa-studio-ci-runner/src/execution/engine.py`, inside `_run_steps_with_nova`:
    - Immediately after `with NovaAct(**nova_kwargs) as nova:` and before the header/step logic, add:
      ```python
      # Capture Nova Act session ID (non-fatal)
      try:
          session_id = nova.get_session_id()
          if session_id:
              self._run_async(
                  self.execution_api.update_session_id(
                      usecase_id=usecase_id,
                      execution_id=execution_id,
                      session_id=session_id,
                  )
              )
              logger.info(f"Captured Nova Act session ID: {session_id}")
          else:
              logger.warning("nova.get_session_id() returned None")
      except Exception as e:
          logger.warning(f"Failed to capture Nova Act session ID: {sanitize_error_message(str(e))}")
      ```
    - Session ID capture failure MUST NOT interrupt step execution (requirement 3.4)
    - Write unit tests in `qa-studio-ci-runner/tests/test_engine_session_id.py`:
      - Test `get_session_id()` called and result persisted via `update_session_id`
      - Test `get_session_id()` returning `None` logs warning, steps still execute
      - Test `get_session_id()` raising exception logs warning, steps still execute
    - _Bug_Condition: _run_steps_with_nova never calls nova.get_session_id()_
    - _Expected_Behavior: get_session_id() called after NovaAct context opens, result persisted via API_
    - _Preservation: All step execution, status reporting, artifact capture unchanged_
    - _Requirements: 2.1, 2.2, 3.2, 3.4_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Nova Session ID Captured and Persisted
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior (get_session_id called, session ID persisted)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - Existing Behavior Unchanged After Fix
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run all preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm: Lambda endpoint status-only updates unchanged
    - Confirm: Engine step execution behavior unchanged
    - Confirm: Session ID failure does not interrupt execution

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite: `cd qa-studio-ci-runner && python -m pytest tests/ -v`
  - Run Lambda endpoint tests: `cd lambdas/endpoints && python -m pytest test_update_execution_status.py -v`
  - Ensure all tests pass, ask the user if questions arise
