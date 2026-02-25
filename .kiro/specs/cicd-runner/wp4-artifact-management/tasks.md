# Implementation Plan: Artifact Management

## Overview

Implement artifact capture (videos, traces, logs, screenshots) during test execution and upload them to S3 using presigned URLs. This includes creating the ArtifactCapture and ArtifactUploader classes, integrating them with the ExecutionEngine, and ensuring fault-tolerant uploads with retry logic.

## Tasks

- [x] 1. Create artifact capture module
  - [x] 1.1 Implement ArtifactCapture class
    - Create `src/execution/artifacts.py`
    - Implement `__init__()` with execution_id and temp_dir
    - Implement `setup_recording()` to return recording path
    - Implement `setup_logs()` to configure file logging
    - Implement `capture_step_screenshot()` with error handling
    - Implement `capture_step_trace()` with error handling
    - Implement `get_execution_artifacts()` to return artifact dict
    - Implement `get_step_artifacts()` to return step artifact dict
    - Implement `cleanup()` to remove temporary directory
    - _Requirements: US1.1, US1.2, US1.4, US2.1, US2.2, US2.3, US3.1, US3.2, US3.3, US3.4_
  
  - [ ]* 1.2 Write property test for artifact file format validation
    - **Property 2: Artifact File Format Validation**
    - **Validates: Requirements US1.2, US2.3, US3.3, US3.4**
  
  - [ ]* 1.3 Write unit tests for ArtifactCapture
    - Test setup_recording() creates correct path
    - Test setup_logs() creates file handler
    - Test capture_step_screenshot() success and failure cases
    - Test capture_step_trace() success and failure cases
    - Test get_execution_artifacts() returns only existing files
    - Test get_step_artifacts() returns correct artifacts
    - Test cleanup() removes temporary directory
    - _Requirements: US1.1, US1.2, US2.1, US2.3, US3.1, US3.2, US3.3, US3.4_

- [x] 2. Create artifact uploader module
  - [x] 2.1 Implement ArtifactUploader class
    - Create `src/execution/artifact_uploader.py`
    - Add `tenacity` to requirements.txt
    - Implement `__init__()` with api_client
    - Implement `upload_execution_artifacts()` with error handling
    - Implement `upload_step_artifacts()` with error handling
    - Implement `_upload_execution_artifact()` with retry decorator
    - Implement `_upload_step_artifact()` with retry decorator
    - Implement `_get_content_type()` static method
    - Configure retry: 3 attempts, exponential backoff (2s, 4s, 8s)
    - _Requirements: US4.1, US4.2, US4.3, US4.4, US4.5_
  
  - [ ]* 2.2 Write property test for upload retry behavior
    - **Property 8: Upload Retry with Exponential Backoff**
    - **Validates: Requirements US4.3**
  
  - [ ]* 2.3 Write property test for presigned URL requests
    - **Property 6: Presigned URL Request for Uploads**
    - **Validates: Requirements US4.1**
  
  - [ ]* 2.4 Write unit tests for ArtifactUploader
    - Test upload_execution_artifacts() with all artifact types
    - Test upload_step_artifacts() with screenshot and trace
    - Test _upload_execution_artifact() makes correct API call
    - Test _upload_step_artifact() makes correct API call
    - Test _get_content_type() for all file extensions
    - Test retry logic with mocked failures (1, 2, 3+ failures)
    - Test upload continues after individual artifact failure
    - _Requirements: US4.1, US4.2, US4.3, US4.4, US4.5_

- [x] 3. Checkpoint - Ensure artifact modules tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Integrate artifact capture with execution engine
  - [x] 4.1 Modify ExecutionEngine.execute_usecase()
    - Import ArtifactCapture and ArtifactUploader
    - Create ArtifactCapture instance with execution_id
    - Call setup_recording() and setup_logs()
    - Create ArtifactUploader instance with api_client
    - Add try/finally block for cleanup
    - Upload execution artifacts after test completes
    - Call cleanup() in finally block
    - _Requirements: US1.1, US1.4, US2.1_
  
  - [x] 4.2 Modify ExecutionEngine._execute_with_nova_act()
    - Add artifact_capture parameter
    - Enable recording in NovaActClient (recording=True)
    - Enable tracing in NovaActClient (tracing=True)
    - Pass artifact_capture to _execute_step()
    - _Requirements: US1.1, US1.2, US3.1, US3.2_
  
  - [x] 4.3 Modify ExecutionEngine._execute_step()
    - Add artifact_capture, artifact_uploader, usecase_id, execution_id parameters
    - After step execution, capture screenshot
    - After step execution, capture trace
    - Get step artifacts from artifact_capture
    - Upload step artifacts immediately via artifact_uploader
    - Ensure errors don't fail the step
    - _Requirements: US3.1, US3.2, US3.3, US3.4, US4.2, US4.4_
  
  - [ ]* 4.4 Write property test for recording capture
    - **Property 1: Recording Capture for All Executions**
    - **Validates: Requirements US1.1, US1.4**
  
  - [ ]* 4.5 Write property test for step artifact completeness
    - **Property 5: Step Artifact Completeness**
    - **Validates: Requirements US3.1, US3.2**
  
  - [ ]* 4.6 Write property test for test continuation on upload failure
    - **Property 9: Test Continuation on Upload Failure**
    - **Validates: Requirements US4.4**
  
  - [ ]* 4.7 Write unit tests for execution engine integration
    - Test execute_usecase() sets up artifact capture
    - Test execute_usecase() uploads execution artifacts
    - Test execute_usecase() cleans up artifacts in finally block
    - Test _execute_step() captures step artifacts
    - Test _execute_step() uploads step artifacts immediately
    - Test artifact capture failures don't fail test
    - Test artifact upload failures don't fail test
    - _Requirements: US1.1, US1.4, US2.1, US3.1, US3.2, US4.4_

- [x] 5. Checkpoint - Ensure integration tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Add remaining property tests
  - [ ]* 6.1 Write property test for log file structure
    - **Property 3: Log File Structure**
    - **Validates: Requirements US2.1, US2.2**
  
  - [ ]* 6.2 Write property test for Nova Act SDK logging
    - **Property 4: Nova Act SDK Logging**
    - **Validates: Requirements US2.4**
  
  - [ ]* 6.3 Write property test for S3 upload via presigned URL
    - **Property 7: S3 Upload via Presigned URL**
    - **Validates: Requirements US4.2**
  
  - [ ]* 6.4 Write property test for artifact association correctness
    - **Property 10: Artifact Association Correctness**
    - **Validates: Requirements US4.5**
  
  - [ ]* 6.5 Write property test for temporary file cleanup
    - **Property 11: Temporary File Cleanup**
    - **Validates: Implicit cleanup requirement**

- [ ] 7. Integration testing and validation
  - [ ]* 7.1 Write integration test for end-to-end artifact flow
    - Execute real test with Nova Act SDK
    - Verify recording file created
    - Verify log file created with correct format
    - Verify screenshots captured for each step
    - Verify traces captured for each step
    - Verify all artifacts uploaded to S3
    - Verify temporary files cleaned up
    - _Requirements: US1.1, US1.2, US2.1, US2.2, US2.3, US3.1, US3.2, US3.3, US3.4, US4.2_
  
  - [ ]* 7.2 Write integration test for artifact upload with real API
    - Request presigned URL from real API endpoint
    - Upload artifact to S3 using presigned URL
    - Verify artifact exists in S3
    - Verify artifact metadata in DynamoDB
    - _Requirements: US4.1, US4.2, US4.5_
  
  - [ ]* 7.3 Write integration test for failure scenarios
    - Test with failing test (verify recording still captured)
    - Test with screenshot capture failure (verify test continues)
    - Test with upload failure (verify test continues)
    - Test with API error (verify retry logic)
    - _Requirements: US1.4, US4.3, US4.4_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (100+ iterations each)
- Unit tests validate specific examples and edge cases
- Integration tests validate end-to-end flows with real dependencies
- Artifact failures should never fail tests - fault tolerance is critical
- Retry logic uses exponential backoff: 2s, 4s, 8s (max 3 attempts)
- Temporary files must always be cleaned up (use finally blocks)
