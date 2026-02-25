# Bugfix Requirements Document

## Introduction

The frontend's `RecordingPlayer` component unconditionally assumes all execution recordings are in rrweb format. CI runner executions (`trigger_type=ci_runner`) produce `.webm` video files stored as artifacts, not rrweb event batches. When a user tries to view a recording for a CI runner execution, the player fails because no rrweb batches exist. Additionally, the "View Recording" button is gated on `execution.nova_session_id`, which CI runner executions may not have, hiding the button entirely even when a video recording is available.

A new backend endpoint `GET /api/usecase/{id}/executions/{executionId}/video` has been implemented that returns a `playback_type` discriminator (`"rrweb"` or `"video"`) along with the appropriate playback data. The frontend needs to call this endpoint first, then branch to the correct player.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user clicks "View Recording" on a CI runner execution THEN the system calls `listRecordingBatches()` (the `/events` endpoint) which returns no batches, and the player displays "No recording batches found" error

1.2 WHEN an execution has `trigger_type=ci_runner` and no `nova_session_id` THEN the system hides the "View Recording" button entirely, even though a `.webm` video recording exists

1.3 WHEN the `RecordingPlayer` component mounts THEN the system always attempts to load rrweb event batches regardless of the execution's recording type

### Expected Behavior (Correct)

2.1 WHEN a user clicks "View Recording" on a CI runner execution THEN the system SHALL call `GET /api/usecase/{id}/executions/{executionId}/video`, receive `playback_type: "video"`, and render a native HTML5 `<video>` player using the returned `download_url`

2.2 WHEN an execution has a completed/terminal status (`success`, `failed`, `error`, `stopped`) THEN the system SHALL show the "View Recording" button regardless of whether `nova_session_id` exists

2.3 WHEN the `RecordingPlayer` component mounts THEN the system SHALL first call the `/video` endpoint to determine `playback_type`, then branch to either the rrweb player (for `playback_type: "rrweb"`) or the native video player (for `playback_type: "video"`)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user clicks "View Recording" on a Nova Act execution (rrweb recording) THEN the system SHALL CONTINUE TO render the rrweb player with full batch loading, background loading, and playback controls as before

3.2 WHEN the `/video` endpoint returns a 404 (no recording available) THEN the system SHALL CONTINUE TO display an appropriate error message to the user

3.3 WHEN an execution is in `executing` or `pending` status THEN the system SHALL CONTINUE TO not show the "View Recording" button (recording is not yet complete)

3.4 WHEN the rrweb player loads batches with multiple pages THEN the system SHALL CONTINUE TO load them with parallel fetching and background loading as currently implemented
