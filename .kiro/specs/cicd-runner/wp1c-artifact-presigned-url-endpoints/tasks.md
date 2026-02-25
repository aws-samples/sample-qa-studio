# Implementation Plan: Artifact Presigned URL Endpoints

## Overview

Implement two API endpoints that generate presigned S3 URLs for artifact uploads. The CI/CD runner will use these URLs to upload artifacts (videos, traces, logs, screenshots) directly to S3, bypassing API Gateway payload limits.

## Tasks

- [x] 1. Set up Lambda functions and shared utilities
  - Create Lambda function files for both endpoints
  - Implement shared utility functions for S3 key generation and validation
  - _Requirements: US1.1, US2.1_

- [ ] 2. Implement execution-level artifact endpoint
  - [x] 2.1 Implement generate_execution_artifact_url Lambda handler
    - Parse and validate request (usecase_id, execution_id, type, filename, content_type)
    - Validate execution exists in DynamoDB
    - Validate artifact type is "recording" or "logs"
    - Generate artifact_id using UUIDv7
    - Generate S3 key using format: artifacts/{usecase_id}/executions/{execution_id}/{filename}
    - Create artifact record in DynamoDB with status="pending"
    - Generate presigned S3 URL with 1-hour expiration
    - Return response with artifact_id, upload_url, expires_in, s3_key
    - _Requirements: US1.1, US1.2, US1.3, US1.4, US1.5_
  
  - [ ]* 2.2 Write property test for artifact type validation
    - **Property 1: Artifact Type Validation**
    - **Validates: Requirements US1.2**
  
  - [ ]* 2.3 Write property test for presigned URL generation
    - **Property 2: Presigned URL Generation**
    - **Validates: Requirements US1.3**
  
  - [ ]* 2.4 Write property test for response structure
    - **Property 3: Response Structure Completeness**
    - **Validates: Requirements US1.4**
  
  - [ ]* 2.5 Write property test for artifact record creation
    - **Property 4: Execution-Level Artifact Record Creation**
    - **Validates: Requirements US1.5**
  
  - [x]* 2.6 Write unit tests for execution artifact endpoint
    - Test successful URL generation for recording
    - Test successful URL generation for logs
    - Test invalid artifact type returns 400
    - Test execution not found returns 404
    - Test missing required fields returns 400
    - Test insufficient permissions returns 403
    - _Requirements: US1.1, US1.2, US1.3, US1.4, US1.5_

- [ ] 3. Implement step-level artifact endpoint
  - [x] 3.1 Implement generate_step_artifact_url Lambda handler
    - Parse and validate request (usecase_id, execution_id, step_id, filename, content_type)
    - Validate execution exists in DynamoDB
    - Validate step exists in DynamoDB
    - Generate artifact_id using UUIDv7
    - Generate S3 key using format: artifacts/{usecase_id}/executions/{execution_id}/steps/{step_id}/{filename}
    - Create artifact record in DynamoDB with status="pending" and step_id field
    - Generate presigned S3 URL with 1-hour expiration
    - Return response with artifact_id, upload_url, expires_in, s3_key
    - _Requirements: US2.1, US2.2, US2.3, US2.4, US2.5_
  
  - [ ]* 3.2 Write property test for step artifact record creation
    - **Property 5: Step-Level Artifact Record Creation**
    - **Validates: Requirements US2.5**
  
  - [ ]* 3.3 Write property test for artifact record structure
    - **Property 6: Artifact Record Structure Invariant**
    - **Validates: Requirements US3.1, US3.3, US3.4**
  
  - [x]* 3.4 Write unit tests for step artifact endpoint
    - Test successful URL generation for screenshot
    - Test successful URL generation for trace
    - Test step not found returns 404
    - Test artifact record includes step_id
    - Test S3 key includes step_id in path
    - _Requirements: US2.1, US2.2, US2.3, US2.4, US2.5_

- [ ] 4. Implement shared validation and utility functions
  - [x] 4.1 Implement validation functions
    - Create validate_execution_exists() function
    - Create validate_step_exists() function
    - Create validate_artifact_type() function
    - Create sanitize_filename() function
    - Create validate_content_type() function
    - _Requirements: US1.2, US2.2_
  
  - [x] 4.2 Implement S3 key generation functions
    - Create generate_s3_key_for_execution_artifact() function
    - Create generate_s3_key_for_step_artifact() function
    - _Requirements: US1.3, US2.3_
  
  - [x] 4.3 Implement artifact record creation function
    - Create create_artifact_record() function
    - Support both execution-level and step-level artifacts
    - _Requirements: US1.5, US2.5, US3.1, US3.2, US3.3, US3.4_
  
  - [x] 4.4 Implement presigned URL generation function
    - Create generate_presigned_upload_url() function
    - Set expiration to 3600 seconds (1 hour)
    - Enforce content_type parameter
    - Restrict to PUT operation only
    - _Requirements: US1.3, US2.3_
  
  - [ ]* 4.5 Write property test for artifact queryability
    - **Property 7: Artifact Queryability**
    - **Validates: Requirements US3.2**
  
  - [ ]* 4.6 Write property test for S3 key format
    - **Property 8: S3 Key Format Consistency**
    - **Validates: Requirements US1.3, US2.3**
  
  - [ ]* 4.7 Write unit tests for utility functions
    - Test S3 key generation for execution artifacts
    - Test S3 key generation for step artifacts
    - Test filename sanitization
    - Test content type validation
    - Test artifact type validation

- [x] 5. Configure API Gateway endpoints
  - [x] 5.1 Add execution artifact endpoint to API Gateway
    - Path: POST /usecase/{id}/executions/{executionId}/artifacts
    - Attach Cognito authorizer
    - Configure required scope: api/execution.write
    - Link to generate_execution_artifact_url Lambda
    - _Requirements: US1.1_
  
  - [x] 5.2 Add step artifact endpoint to API Gateway
    - Path: POST /usecase/{id}/executions/{executionId}/steps/{stepId}/artifacts
    - Attach Cognito authorizer
    - Configure required scope: api/execution.write
    - Link to generate_step_artifact_url Lambda
    - _Requirements: US2.1_

- [x] 6. Configure S3 bucket for artifact uploads
  - [x] 6.1 Update S3 bucket CORS configuration
    - Allow PUT and POST methods
    - Allow all origins (for CI/CD runners)
    - Expose ETag header
    - _Requirements: US1.3, US2.3_
  
  - [x] 6.2 Verify Lambda execution role permissions
    - Ensure role has s3:PutObject permission
    - Ensure role has dynamodb:GetItem permission
    - Ensure role has dynamodb:PutItem permission
    - _Requirements: US1.5, US2.5_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Add CloudWatch monitoring and logging
  - [ ] 8.1 Implement structured logging
    - Log artifact URL generation events
    - Log user identity and artifact metadata
    - Never log presigned URLs (security)
    - _Requirements: US1.3, US2.3_
  
  - [ ] 8.2 Implement CloudWatch metrics
    - Publish ArtifactUrlGenerated metric (by type and level)
    - Publish UrlGenerationDuration metric
    - Publish error metrics by type
    - _Requirements: US1.3, US2.3_

- [ ]* 9. Write integration tests
  - [ ]* 9.1 Test execution artifact upload flow
    - Create execution record
    - Generate presigned URL for recording
    - Upload file to presigned URL
    - Verify file exists in S3
    - Verify artifact record in DynamoDB
    - _Requirements: US1.1, US1.2, US1.3, US1.4, US1.5_
  
  - [ ]* 9.2 Test step artifact upload flow
    - Create execution and step records
    - Generate presigned URL for screenshot
    - Upload file to presigned URL
    - Verify file exists in S3
    - Verify artifact record includes step_id
    - _Requirements: US2.1, US2.2, US2.3, US2.4, US2.5_
  
  - [ ]* 9.3 Test presigned URL expiration
    - Generate presigned URL
    - Verify URL expires after 1 hour
    - _Requirements: US1.3, US2.3_
  
  - [ ]* 9.4 Test error scenarios
    - Test execution not found
    - Test step not found
    - Test invalid artifact type
    - Test missing required fields
    - _Requirements: US1.2, US2.2_

- [ ] 10. Update API documentation
  - [x] 10.1 Add execution artifact endpoint documentation
    - Document request/response format
    - Document error responses
    - Add cURL and Python examples
    - _Requirements: US1.1, US1.2, US1.3, US1.4_
  
  - [x] 10.2 Add step artifact endpoint documentation
    - Document request/response format
    - Document error responses
    - Add cURL and Python examples
    - _Requirements: US2.1, US2.2, US2.3, US2.4_
  
  - [x] 10.3 Update API.md with new endpoints
    - Add to CI/CD Integration section
    - Document artifact upload workflow
    - Include example usage in CI/CD pipeline
    - _Requirements: US1.1, US2.1_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- Integration tests validate end-to-end artifact upload flow
- Lambda functions use existing utility patterns from utils.py
- S3 presigned URLs expire after 1 hour for security
- Artifact records track upload status (pending initially)
- Both endpoints support M2M tokens for CI/CD runners

