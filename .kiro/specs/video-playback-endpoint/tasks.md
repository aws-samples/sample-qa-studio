# Implementation Plan: Video Playback Endpoint

## Overview

Implement a single GET endpoint (`/api/usecase/{id}/executions/{executionId}/video`) that returns video playback data for a given execution. The endpoint reads the execution record's `trigger_type` to determine the recording type and returns either rrweb batch metadata (worker path) or a presigned S3 download URL (cicd-runner path). The implementation follows existing endpoint patterns (`generate_execution_artifact_url.py`, `list_recording_batches.py`) and reuses shared utilities from `utils.py`.

## Tasks

- [x] 1. Implement the get_video_playback Lambda handler
  - [x] 1.1 Create `lambdas/endpoints/get_video_playback.py` with handler function
    - Validate `api/executions.read` scope using `require_scopes`
    - Parse `id` and `executionId` from `pathParameters`
    - Return 400 if path parameters are missing
    - Retrieve execution record from DynamoDB (`pk=USECASE_EXECUTION#{id}`, `sk=EXECUTION#{executionId}`)
    - Return 404 if execution record not found
    - Read `trigger_type` from execution record and classify playback type
    - Return 400 for unrecognized `trigger_type`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.1, 7.1, 7.3_

  - [x] 1.2 Implement `classify_playback_type(trigger_type)` helper
    - Map `OnDemand`, `Scheduled`, `OnDemandHeadless` → `"rrweb"`
    - Map `ci_runner` → `"video"`
    - Raise `ValueError` for unknown trigger types
    - _Requirements: 1.2, 1.3, 7.3_

  - [x] 1.3 Implement `get_rrweb_playback_data(s3_client, bucket, usecase_id, execution_id)` helper
    - List S3 objects at `{usecase_id}/{execution_id}/recording/` with delimiter to find session folder
    - Load `metadata.json` from the session folder
    - List batch files (`batch_*.ndjson.gz`) and extract sorted batch IDs
    - Return `(batches, metadata)` or raise if no recording folder found
    - Reuse the same S3 listing pattern from `list_recording_batches.py`
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 1.4 Implement `get_video_playback_data(dynamodb, table_name, bucket, execution_id)` helper
    - Query DynamoDB for artifact records (`pk=EXECUTION#{execution_id}`, `sk begins_with ARTIFACT#`)
    - Filter for `type=recording` and `upload_status=uploaded`
    - Generate presigned S3 GET URL (3600s expiration) for the recording file
    - Return `(download_url, content_type, expires_in)` or raise if no artifact found
    - _Requirements: 3.1, 3.2, 3.4_

  - [x] 1.5 Wire handler response assembly
    - Build rrweb response: `{playback_type, execution_id, trigger_type, batches, metadata}`
    - Build video response: `{playback_type, execution_id, trigger_type, download_url, content_type, expires_in}`
    - Wrap all DynamoDB/S3 errors in try/except, return 500 with generic message, log full error
    - _Requirements: 2.3, 3.3, 5.1, 5.2, 5.3, 7.2_

- [x] 2. Checkpoint - Verify handler logic
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Write unit tests for get_video_playback
  - [x] 3.1 Create `lambdas/endpoints/test_get_video_playback.py` with unit tests
    - Test happy path: rrweb playback (trigger_type=OnDemand) with mocked S3 returning batches and metadata
    - Test happy path: rrweb playback (trigger_type=Scheduled)
    - Test happy path: rrweb playback (trigger_type=OnDemandHeadless)
    - Test happy path: video playback (trigger_type=ci_runner) with mocked DynamoDB artifact query and S3 presigned URL
    - Test 404: execution not found
    - Test 404: rrweb path but no recording folder in S3
    - Test 404: video path but no artifact with upload_status=uploaded
    - Test 400: missing path parameters
    - Test 400: unrecognized trigger_type
    - Test 500: DynamoDB ClientError
    - Test 500: S3 ClientError
    - Test 403: missing `api/executions.read` scope
    - Follow mocking pattern from `test_generate_execution_artifact_url.py` (patch `get_dynamodb_client` and `get_s3_client`)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 5.1, 5.2, 5.3, 7.1, 7.2, 7.3_

  - [ ]* 3.2 Write property test: trigger type classification is total and correct
    - **Property 1: Trigger type classification is total and correct**
    - Generate random strings with `hypothesis`. For known trigger types assert correct classification, for unknown strings assert `ValueError`.
    - **Validates: Requirements 1.2, 1.3, 7.3**

  - [ ]* 3.3 Write property test: successful response envelope contains required fields
    - **Property 2: Successful response envelope contains required fields**
    - Generate valid execution records and mock S3/DynamoDB. Assert response body always contains `playback_type`, `execution_id`, `trigger_type`, plus type-specific fields.
    - **Validates: Requirements 2.3, 3.3, 5.1, 5.2, 5.3**

  - [ ]* 3.4 Write property test: S3 recording path construction
    - **Property 3: S3 recording path construction**
    - Generate random `usecase_id` and `execution_id` strings. Assert constructed prefix is exactly `"{usecase_id}/{execution_id}/recording/"`.
    - **Validates: Requirements 2.1**

  - [ ]* 3.5 Write property test: requests without required scope are rejected
    - **Property 4: Requests without required scope are rejected**
    - Generate random events without `api/executions.read` scope. Assert 403 response.
    - **Validates: Requirements 4.1, 4.2**

  - [ ]* 3.6 Write property test: internal errors produce HTTP 500 with generic message
    - **Property 5: Internal errors produce HTTP 500 with generic message**
    - Generate random `ClientError` exceptions. Assert 500 response with generic error message (no internal details leaked).
    - **Validates: Requirements 7.2**

- [x] 4. Checkpoint - Verify all unit and property tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Register Lambda in CDK stacks
  - [x] 5.1 Add `getVideoPlaybackLambda` property and definition to `lib/lambda-stack.ts`
    - Declare `public readonly getVideoPlaybackLambda: Function`
    - Create Lambda with `createPythonLambda({ path: 'get_video_playback', environment: { TABLE_NAME, BUCKET_NAME } })`
    - Grant `tableReadPolicy` (DynamoDB read for execution + artifact records)
    - Grant `artefactsBucket.grantRead()` (S3 read for rrweb batches + presigned GET URLs)
    - _Requirements: 6.2, 6.3_

  - [x] 5.2 Add GET route to `lib/api-stack.ts`
    - Add `video` resource under existing `execution` resource: `const executionVideo = this.addResource(execution, 'video')`
    - Register GET method: `this.addMethod(executionVideo, HttpMethod.GET, l.getVideoPlaybackLambda)`
    - Cognito authorizer is attached automatically via `addMethod`
    - _Requirements: 6.1, 6.2_

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The Lambda reuses existing patterns from `list_recording_batches.py` (rrweb S3 listing) and `generate_execution_artifact_url.py` (DynamoDB artifact queries, presigned URLs)
- No new DynamoDB record types, GSIs, or S3 key patterns are introduced
- The `api/executions.read` scope already exists in the CDK stack
