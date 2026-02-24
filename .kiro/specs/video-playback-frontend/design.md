# Video Playback Frontend Bugfix Design

## Overview

The `RecordingPlayer` component unconditionally assumes all recordings are rrweb format, and the "View Recording" button is gated on `nova_session_id`. This causes two failures for CI runner executions: (1) the button is hidden because CI runner executions lack `nova_session_id`, and (2) if somehow reached, the player fails because no rrweb batches exist for `.webm` video recordings.

The fix introduces a playback-type detection step using the existing `GET /api/usecase/{id}/executions/{executionId}/video` endpoint, branches the `RecordingPlayer` between rrweb and HTML5 `<video>` players, and changes the button visibility to check terminal execution status instead of `nova_session_id`.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — when a CI runner execution's recording is requested, the frontend either hides the button (no `nova_session_id`) or attempts rrweb playback on a `.webm` file
- **Property (P)**: The desired behavior — the frontend calls the `/video` endpoint, detects `playback_type`, and renders the correct player (rrweb or HTML5 video)
- **Preservation**: Existing rrweb playback (batch loading, background loading, player controls) and non-recording UI behavior must remain unchanged
- **RecordingPlayer**: The component in `frontend/src/components/RecordingPlayer.tsx` that renders execution recordings
- **ExecutionInformation**: The component in `frontend/src/components/execution/ExecutionInformation.tsx` that displays execution metadata and the "View Recording" button
- **playback_type**: Discriminator field returned by the `/video` endpoint — either `"rrweb"` or `"video"`
- **Terminal status**: Execution statuses indicating completion: `success`, `failed`, `error`, `stopped`

## Bug Details

### Fault Condition

The bug manifests in two places:

1. **Button visibility**: `ExecutionInformation.tsx` conditionally renders the "View Recording" button only when `execution.nova_session_id` is truthy. CI runner executions may not have this field, so the button is hidden even when a `.webm` recording exists.

2. **Player assumption**: `RecordingPlayer.tsx` always calls `listRecordingBatches()` (the `/events` endpoint) on mount. For CI runner executions, this returns no batches, causing a "No recording batches found" error.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type { execution: ExecutionRecord, action: "view_recording" | "render_player" }
  OUTPUT: boolean

  IF input.action == "view_recording" THEN
    RETURN input.execution.trigger_type == "ci_runner"
           AND (input.execution.nova_session_id IS NULL OR input.execution.nova_session_id == "")
           AND input.execution.status IN ["success", "failed", "error", "stopped"]
  END IF

  IF input.action == "render_player" THEN
    RETURN input.execution.trigger_type == "ci_runner"
           AND playerAttemptsRrwebLoad(input.execution)
  END IF
END FUNCTION
```

### Examples

- CI runner execution with `trigger_type=ci_runner`, no `nova_session_id`, status `success` → button hidden, user cannot view existing `.webm` recording
- CI runner execution with `trigger_type=ci_runner`, no `nova_session_id`, status `failed` → button hidden, `.webm` recording exists but inaccessible
- CI runner execution somehow reaches RecordingPlayer → `listRecordingBatches()` returns empty, player shows "No recording batches found"
- Nova Act execution with `trigger_type=OnDemand`, `nova_session_id` present → button visible, rrweb player works correctly (not affected by bug)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- rrweb playback for Nova Act executions (`OnDemand`, `Scheduled`, `OnDemandHeadless`) must continue to work with full batch loading, parallel page fetching, background loading, and player state restoration
- The rrweb player's progress indicators, error handling, and dynamic import of `rrweb-player` must remain unchanged
- Mouse clicks, navigation, and all non-recording UI interactions must remain unchanged
- Execution polling (10s interval for `executing`/`pending` status) must remain unchanged
- The recording modal's open/close behavior in `ExecutionDetailRefactored.tsx` must remain unchanged

**Scope:**
All inputs that do NOT involve CI runner execution recordings should be completely unaffected by this fix. This includes:
- rrweb playback for worker-path executions
- All non-recording UI elements (execution info, steps, variables, timeline, live view)
- Error handling for 404 responses (no recording available)
- Executions in non-terminal status (`executing`, `pending`) — button should remain hidden

## Hypothesized Root Cause

Based on the bug description, the root causes are:

1. **Incorrect button visibility gate**: `ExecutionInformation.tsx` line ~80 checks `execution.nova_session_id` to show the "View Recording" button. This is a Nova Act-specific field that CI runner executions don't have. The gate should check terminal execution status instead, since any completed execution _might_ have a recording regardless of trigger type.

2. **Missing playback type detection**: `RecordingPlayer.tsx` has no awareness of the `/video` endpoint or the `playback_type` discriminator. It unconditionally calls `listRecordingBatches()` which only works for rrweb recordings.

3. **No video player path**: `RecordingPlayer.tsx` has no HTML5 `<video>` rendering branch. Even if the playback type were detected, there's no code to render a `.webm` video.

4. **Missing API integration**: `frontend/src/utils/api.ts` and `frontend/src/utils/recordingUtils.ts` have no function to call the `GET /video` endpoint.

## Correctness Properties

Property 1: Fault Condition — CI Runner Recordings Play as HTML5 Video

_For any_ execution where `trigger_type` is `"ci_runner"` and the `/video` endpoint returns `playback_type: "video"` with a `download_url`, the `RecordingPlayer` SHALL render a native HTML5 `<video>` element with the `download_url` as its source, instead of attempting rrweb batch loading.

**Validates: Requirements 2.1, 2.3**

Property 2: Fault Condition — Button Visible for Terminal CI Runner Executions

_For any_ execution with a terminal status (`success`, `failed`, `error`, `stopped`), the "View Recording" button SHALL be visible regardless of whether `nova_session_id` exists.

**Validates: Requirements 2.2**

Property 3: Preservation — rrweb Playback Unchanged

_For any_ execution where the `/video` endpoint returns `playback_type: "rrweb"`, the `RecordingPlayer` SHALL continue to load rrweb batches with parallel page fetching, background loading, and player state restoration exactly as before.

**Validates: Requirements 3.1, 3.4**

Property 4: Preservation — Non-Terminal Executions Hide Button

_For any_ execution with a non-terminal status (`executing`, `pending`), the "View Recording" button SHALL NOT be visible, preserving the existing behavior that recordings are only viewable after completion.

**Validates: Requirements 3.3**

Property 5: Preservation — 404 Error Handling

_For any_ execution where the `/video` endpoint returns 404, the `RecordingPlayer` SHALL display an appropriate error message, preserving the existing error UX.

**Validates: Requirements 3.2**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `frontend/src/utils/recordingUtils.ts`

**Function**: New `getVideoPlayback` function

**Specific Changes**:
1. **Add playback type interfaces**: Define `VideoPlaybackResponse` as a discriminated union type:
   - `RrwebPlaybackResponse`: `{ playback_type: "rrweb", execution_id: string, trigger_type: string, batches: string[], metadata: RecordingMetadata }`
   - `VideoPlaybackResponse`: `{ playback_type: "video", execution_id: string, trigger_type: string, download_url: string, content_type: string, expires_in: number }`
2. **Add `getVideoPlayback` function**: Calls `GET usecase/{usecaseId}/executions/{executionId}/video` and returns the typed response

---

**File**: `frontend/src/components/RecordingPlayer.tsx`

**Function**: `RecordingPlayer` component

**Specific Changes**:
3. **Add playback type detection on mount**: Before loading anything, call `getVideoPlayback()` to determine `playback_type`
4. **Branch rendering**: If `playback_type === "video"`, render a native HTML5 `<video>` element with `download_url` as source, controls enabled, and appropriate styling. If `playback_type === "rrweb"`, proceed with existing rrweb batch loading logic unchanged.
5. **Video player UI**: The HTML5 video player should include native controls, be responsive within the modal, and handle loading/error states

---

**File**: `frontend/src/components/execution/ExecutionInformation.tsx`

**Function**: `ExecutionInformation` component

**Specific Changes**:
6. **Change button visibility condition**: Replace `execution.nova_session_id` check with a terminal status check: `['success', 'failed', 'error', 'stopped'].includes(execution.status)`. This makes the button visible for any completed execution regardless of trigger type.
7. **Keep NovaAct Session ID display**: The `nova_session_id` key-value pair should still display when available (it's informational), but it should no longer gate the recording button.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write component tests using `@testing-library/react` and `vitest` that render `ExecutionInformation` and `RecordingPlayer` with CI runner execution data. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:
1. **Button Hidden for CI Runner**: Render `ExecutionInformation` with `{ status: "success", trigger_type: "ci_runner", nova_session_id: null }` — assert button is hidden (will confirm bug on unfixed code)
2. **Player Fails for CI Runner**: Render `RecordingPlayer` with mocked `/video` endpoint returning `playback_type: "video"` — assert rrweb loading is attempted instead (will fail on unfixed code)
3. **Button Hidden for CI Runner Failed**: Render `ExecutionInformation` with `{ status: "failed", trigger_type: "ci_runner" }` — assert button is hidden (will confirm bug on unfixed code)

**Expected Counterexamples**:
- "View Recording" button not rendered when `nova_session_id` is absent despite terminal status
- `listRecordingBatches` called instead of `getVideoPlayback` for CI runner executions

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL execution WHERE isBugCondition(execution) DO
  result_button := renderExecutionInformation(execution)
  ASSERT "View Recording" button IS visible

  result_player := renderRecordingPlayer(execution)
  ASSERT getVideoPlayback() IS called
  ASSERT HTML5 <video> element IS rendered with download_url
  ASSERT listRecordingBatches() IS NOT called
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL execution WHERE NOT isBugCondition(execution) DO
  ASSERT renderExecutionInformation_original(execution) = renderExecutionInformation_fixed(execution)
  ASSERT renderRecordingPlayer_original(execution) = renderRecordingPlayer_fixed(execution)
END FOR
```

**Testing Approach**: Property-based testing with `fast-check` is recommended for preservation checking because:
- It generates many execution configurations automatically across the input domain
- It catches edge cases in status/trigger_type combinations that manual tests might miss
- It provides strong guarantees that rrweb playback behavior is unchanged

**Test Plan**: Observe behavior on UNFIXED code first for rrweb executions, then write property-based tests capturing that behavior.

**Test Cases**:
1. **rrweb Playback Preservation**: Verify that for any execution where `/video` returns `playback_type: "rrweb"`, the component calls `listRecordingBatches` and renders the rrweb player
2. **Button Visibility Preservation for Nova Act**: Verify that for any execution with `nova_session_id` and terminal status, the button remains visible (existing behavior preserved)
3. **Non-Terminal Status Preservation**: Verify that for any execution with `executing` or `pending` status, the button remains hidden regardless of trigger type
4. **Error Handling Preservation**: Verify that 404 from `/video` endpoint displays error message

### Unit Tests

- Test `getVideoPlayback` API function returns correct typed response for both `rrweb` and `video` playback types
- Test `RecordingPlayer` renders HTML5 `<video>` when `playback_type === "video"`
- Test `RecordingPlayer` renders rrweb player when `playback_type === "rrweb"` (delegates to existing batch loading)
- Test `RecordingPlayer` shows error when `/video` endpoint returns 404
- Test `RecordingPlayer` shows loading state while fetching playback type
- Test `ExecutionInformation` shows button for terminal status regardless of `nova_session_id`
- Test `ExecutionInformation` hides button for non-terminal status
- Test `ExecutionInformation` hides button for `executing` and `pending` status even with `nova_session_id`

### Property-Based Tests

- Generate random execution objects with varying `status`, `trigger_type`, and `nova_session_id` values — verify button visibility follows terminal status rule, not `nova_session_id` rule
- Generate random `/video` responses with `playback_type` discriminator — verify correct player branch is taken
- Generate random rrweb batch configurations — verify existing parallel loading and background loading behavior is preserved

### Integration Tests

- Full flow: render `ExecutionDetailRefactored` with CI runner execution → click "View Recording" → verify video player renders in modal
- Full flow: render `ExecutionDetailRefactored` with Nova Act execution → click "View Recording" → verify rrweb player renders in modal
- Verify modal open/close behavior works for both player types
