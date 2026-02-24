# Requirements Document

## Introduction

A dedicated video playback endpoint that serves execution recording data to the frontend. The system must distinguish between two recording types based on how the execution was triggered:

1. **Worker path** (Bedrock Agent Core remote browser): Recordings are stored as rrweb-format `.ndjson.gz` batch files with metadata at `{usecase_id}/{execution_id}/recording/{session_folder_id}/`. These are replayed in the browser using an rrweb player.
2. **CICD-runner path** (local chromium via Nova Act): Recordings are stored as `.webm` video files uploaded as execution artifacts to `{usecase_id}/{execution_id}/recording.webm`. These are played back as native video.

The endpoint reads the execution record's `trigger_type` field to determine which path was used, then returns the appropriate playback data and metadata so the frontend knows how to render the recording.

## Glossary

- **Video_Playback_Endpoint**: The new GET endpoint that returns video playback information for a given execution
- **Execution_Record**: DynamoDB record with pk=`USECASE_EXECUTION#{usecase_id}`, sk=`EXECUTION#{execution_id}` containing execution metadata including `trigger_type`
- **trigger_type**: Field on the execution record indicating how the execution was triggered. Values: `OnDemand`, `Scheduled`, `OnDemandHeadless` (worker path), `ci_runner` (cicd-runner path)
- **Worker_Recording**: rrweb-format recording produced by Bedrock Agent Core remote browser, stored as `.ndjson.gz` batch files in S3
- **Runner_Recording**: `.webm` video file produced by local chromium via Nova Act, uploaded as an execution artifact to S3
- **Playback_Type**: Discriminator returned by the endpoint: `rrweb` for worker recordings, `video` for runner recordings
- **Artifact_Record**: DynamoDB record with pk=`EXECUTION#{execution_id}`, sk=`ARTIFACT#{artifact_id}` tracking uploaded artifact files

## Requirements

### Requirement 1: Determine Recording Type from Execution

**User Story:** As a frontend developer, I want the endpoint to determine the recording type from the execution record, so that I can render the correct player component.

#### Acceptance Criteria

1. WHEN a GET request is received with a valid usecase ID and execution ID, THE Video_Playback_Endpoint SHALL retrieve the Execution_Record from DynamoDB
2. WHEN the Execution_Record has a trigger_type of `OnDemand`, `Scheduled`, or `OnDemandHeadless`, THE Video_Playback_Endpoint SHALL classify the Playback_Type as `rrweb`
3. WHEN the Execution_Record has a trigger_type of `ci_runner`, THE Video_Playback_Endpoint SHALL classify the Playback_Type as `video`
4. IF the Execution_Record does not exist for the given usecase ID and execution ID, THEN THE Video_Playback_Endpoint SHALL return HTTP 404 with an error message

### Requirement 2: Return Worker Recording Playback Data (rrweb)

**User Story:** As a frontend developer, I want to receive rrweb recording metadata for worker-path executions, so that I can initialize the rrweb player with the correct batch list.

#### Acceptance Criteria

1. WHEN the Playback_Type is `rrweb`, THE Video_Playback_Endpoint SHALL locate the recording folder in S3 at `{usecase_id}/{execution_id}/recording/`
2. WHEN the Playback_Type is `rrweb` and a recording folder exists, THE Video_Playback_Endpoint SHALL return the list of batch IDs and the recording metadata from `metadata.json`
3. WHEN the Playback_Type is `rrweb` and the response is returned, THE Video_Playback_Endpoint SHALL include `playback_type: "rrweb"` in the response body
4. IF the Playback_Type is `rrweb` and no recording folder is found in S3, THEN THE Video_Playback_Endpoint SHALL return HTTP 404 with an error message indicating no recording is available

### Requirement 3: Return Runner Recording Playback Data (video)

**User Story:** As a frontend developer, I want to receive a presigned download URL for runner-path executions, so that I can play the `.webm` video in a native video player.

#### Acceptance Criteria

1. WHEN the Playback_Type is `video`, THE Video_Playback_Endpoint SHALL query the Artifact_Records for the execution to find artifacts with type `recording`
2. WHEN the Playback_Type is `video` and a recording artifact exists with upload_status `uploaded`, THE Video_Playback_Endpoint SHALL generate a presigned S3 GET URL for the recording file
3. WHEN the Playback_Type is `video` and the response is returned, THE Video_Playback_Endpoint SHALL include `playback_type: "video"`, the presigned download URL, the content type, and the URL expiration time in seconds
4. IF the Playback_Type is `video` and no recording artifact with upload_status `uploaded` is found, THEN THE Video_Playback_Endpoint SHALL return HTTP 404 with an error message indicating no recording is available

### Requirement 4: Authorization and Scope Validation

**User Story:** As a system administrator, I want the endpoint to enforce proper authorization, so that only authenticated users with the correct scope can access recording data.

#### Acceptance Criteria

1. THE Video_Playback_Endpoint SHALL validate the request against the `api/executions.read` OAuth scope
2. IF the request lacks a valid token or the required scope, THEN THE Video_Playback_Endpoint SHALL return HTTP 403 with an error message

### Requirement 5: Consistent Response Envelope

**User Story:** As a frontend developer, I want a consistent response structure regardless of recording type, so that I can implement a clean branching logic in the UI.

#### Acceptance Criteria

1. THE Video_Playback_Endpoint SHALL return a JSON response containing `playback_type` (either `rrweb` or `video`), `execution_id`, and `trigger_type` for all successful responses
2. WHEN the Playback_Type is `rrweb`, THE Video_Playback_Endpoint SHALL include `batches` (list of batch IDs) and `metadata` (recording metadata object) in the response
3. WHEN the Playback_Type is `video`, THE Video_Playback_Endpoint SHALL include `download_url` (presigned S3 GET URL), `content_type` (MIME type of the video), and `expires_in` (URL expiration in seconds) in the response

### Requirement 6: API Route Definition

**User Story:** As a backend developer, I want the endpoint registered as a new independent route, so that it does not conflict with existing artifact endpoints.

#### Acceptance Criteria

1. THE Video_Playback_Endpoint SHALL be accessible via `GET /api/usecase/{id}/executions/{executionId}/video`
2. THE Video_Playback_Endpoint SHALL be registered as an independent Lambda function in the CDK stack with the Cognito authorizer attached
3. THE Video_Playback_Endpoint SHALL have the `BUCKET_NAME` environment variable configured to access the S3 artifacts bucket

### Requirement 7: Error Handling

**User Story:** As a frontend developer, I want clear error responses, so that I can display meaningful messages to the user.

#### Acceptance Criteria

1. IF a required path parameter (usecase ID or execution ID) is missing, THEN THE Video_Playback_Endpoint SHALL return HTTP 400 with a descriptive error message
2. IF an internal error occurs while accessing DynamoDB or S3, THEN THE Video_Playback_Endpoint SHALL return HTTP 500 with a generic error message and log the detailed error server-side
3. IF the execution exists but has a trigger_type that is not recognized, THEN THE Video_Playback_Endpoint SHALL return HTTP 400 with an error message indicating an unsupported trigger type
