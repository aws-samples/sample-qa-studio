# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Fault Condition** - CI Runner Recordings Trigger Wrong Playback Path
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Use `fast-check` to generate executions with `trigger_type: "ci_runner"` and terminal statuses (`success`, `failed`, `error`, `stopped`), with `nova_session_id` as null or empty string
  - **Setup**: Install `fast-check` as a dev dependency in `frontend/` if not already present
  - **Test file**: `frontend/src/components/__tests__/RecordingPlayer.bugfix.test.tsx`
  - **Test 1 - Button visibility**: Render `ExecutionInformation` with generated CI runner executions (terminal status, no `nova_session_id`). Assert "View" button is visible. On unfixed code, button will be hidden because visibility is gated on `nova_session_id` — this confirms bug 1.2
  - **Test 2 - Player branch**: Render `RecordingPlayer` with mocked `getVideoPlayback` returning `playback_type: "video"` and a `download_url`. Assert a `<video>` element is rendered. On unfixed code, `RecordingPlayer` calls `listRecordingBatches` instead — this confirms bug 1.3
  - **Bug condition from design**: `isBugCondition(input)` where `input.execution.trigger_type == "ci_runner" AND (nova_session_id IS NULL OR "") AND status IN ["success","failed","error","stopped"]`
  - **Expected behavior from design**: Button visible for terminal CI runner executions; `RecordingPlayer` renders HTML5 `<video>` when `/video` returns `playback_type: "video"`
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct - it proves the bug exists)
  - Document counterexamples found (e.g., "View button not rendered for `{status: 'success', trigger_type: 'ci_runner', nova_session_id: null}`")
  - Mark task complete when tests are written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - rrweb Playback and Button Visibility Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **Test file**: `frontend/src/components/__tests__/RecordingPlayer.preservation.test.tsx`
  - **Setup**: Uses `fast-check` for property-based testing across the non-bug-condition input domain
  - **Observe on UNFIXED code first**:
    - Observe: `ExecutionInformation` with `{ status: "success", nova_session_id: "sess-123" }` renders "View" button
    - Observe: `ExecutionInformation` with `{ status: "executing" }` does NOT render "View" button
    - Observe: `ExecutionInformation` with `{ status: "pending" }` does NOT render "View" button
    - Observe: `RecordingPlayer` with mocked `listRecordingBatches` returning batches calls rrweb loading path
  - **Property test 1 - Button visible for Nova Act terminal executions**: For all executions with `nova_session_id` present AND terminal status (`success`, `failed`, `error`, `stopped`), the "View" button is rendered. Use `fc.record()` to generate execution objects with `nova_session_id` as non-empty string and status from terminal set.
  - **Property test 2 - Button hidden for non-terminal executions**: For all executions with status `executing` or `pending`, the "View" button is NOT rendered regardless of `trigger_type` or `nova_session_id`. Use `fc.oneof(fc.constant("executing"), fc.constant("pending"))` for status.
  - **Property test 3 - rrweb player path**: When `/video` endpoint returns `playback_type: "rrweb"`, the component calls `listRecordingBatches` and does NOT render a `<video>` element. Mock `getVideoPlayback` to return rrweb response.
  - **Property test 4 - 404 error handling**: When `/video` endpoint returns 404 error, the component displays an error alert.
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Fix for CI runner video playback and button visibility

  - [x] 3.1 Add `getVideoPlayback` API function and types to `recordingUtils.ts`
    - Add discriminated union types for video playback response:
      - `RrwebPlaybackResponse`: `{ playback_type: "rrweb", execution_id, trigger_type, batches, metadata }`
      - `VideoFilePlaybackResponse`: `{ playback_type: "video", execution_id, trigger_type, download_url, content_type, expires_in }`
      - `VideoPlaybackResponse = RrwebPlaybackResponse | VideoFilePlaybackResponse`
    - Add `getVideoPlayback(usecaseId, executionId)` function that calls `GET usecase/{usecaseId}/executions/${executionId}/video`
    - _Bug_Condition: isBugCondition(input) where trigger_type == "ci_runner" AND playerAttemptsRrwebLoad_
    - _Expected_Behavior: Call /video endpoint first to determine playback_type before loading anything_
    - _Preservation: Existing listRecordingBatches and getRecordingBatch functions remain unchanged_
    - _Requirements: 2.1, 2.3_

  - [x] 3.2 Branch `RecordingPlayer` by playback type
    - Add initial `getVideoPlayback()` call on mount before any loading
    - If `playback_type === "video"`: render HTML5 `<video>` element with `download_url` as source, native controls, responsive sizing within modal
    - If `playback_type === "rrweb"`: proceed with existing rrweb batch loading logic (unchanged)
    - Handle loading state while fetching playback type
    - Handle error state (404 from `/video` endpoint)
    - _Bug_Condition: isBugCondition(input) where trigger_type == "ci_runner" AND RecordingPlayer always calls listRecordingBatches_
    - _Expected_Behavior: RecordingPlayer calls getVideoPlayback first, branches to <video> for "video" type, rrweb for "rrweb" type_
    - _Preservation: rrweb batch loading, parallel page fetching, background loading, player state restoration all unchanged_
    - _Requirements: 2.1, 2.3, 3.1, 3.4_

  - [x] 3.3 Change button visibility in `ExecutionInformation.tsx`
    - Replace `execution.nova_session_id` check with terminal status check: `['success', 'failed', 'error', 'stopped'].includes(execution.status)`
    - Keep `nova_session_id` display in KeyValuePairs (informational only)
    - _Bug_Condition: isBugCondition(input) where nova_session_id IS NULL AND status is terminal_
    - _Expected_Behavior: Button visible for any terminal execution regardless of nova_session_id_
    - _Preservation: Button still hidden for executing/pending status_
    - _Requirements: 2.2, 3.3_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - CI Runner Recordings Play Correctly
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1: `cd frontend && npx vitest run src/components/__tests__/RecordingPlayer.bugfix.test.tsx`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - rrweb Playback and Button Visibility Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2: `cd frontend && npx vitest run src/components/__tests__/RecordingPlayer.preservation.test.tsx`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite: `cd frontend && npx vitest run`
  - Ensure all tests pass, ask the user if questions arise.
