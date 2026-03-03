# Implementation Plan: Cache Builder Lambda

## Overview

This plan implements an event-driven AWS Lambda function that automatically builds step caches from Nova Act responses after successful test executions. The Lambda processes EventBridge events, fetches Nova Act response files from S3, parses them using the existing cache_parser module, and updates STEP records in DynamoDB with cached actions. This enables 40-60% faster test execution by replaying cached steps via Playwright instead of calling Nova Act.

## Tasks

- [ ] 1. Create Lambda handler and core infrastructure
  - [x] 1.1 Create build_cache.py Lambda handler with event processing
    - Implement lambda_handler function that extracts usecase_id, execution_id, execution_status, and timestamp from EventBridge event
    - Add fire-and-forget error handling with top-level try-except that always returns 200
    - Set up logging configuration with INFO level
    - Add environment variable reading for DYNAMODB_TABLE_NAME and S3_BUCKET
    - _Requirements: 1.1, 1.3, 1.5, 12.5, 12.6_

  - [x] 1.2 Implement cache eligibility verification
    - Create check_cache_eligibility function that queries USECASE record (pk: USECASES, sk: USECASE#{usecase_id})
    - Check enable_cache field and return boolean
    - Add logging for skip decisions (non-success status, cache disabled, missing usecase)
    - Handle missing USECASE records gracefully
    - _Requirements: 1.4, 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 1.3 Write property test for event field extraction
    - **Property 1: Event Field Extraction**
    - **Validates: Requirements 1.3**
    - Generate random valid EventBridge events with detail fields
    - Verify Lambda successfully extracts usecase_id, execution_id, execution_status, timestamp
    - Tag: Feature: cache-builder-lambda, Property 1: Event field extraction

  - [ ]* 1.4 Write property test for fire-and-forget error handling
    - **Property 2: Fire-and-Forget Error Handling**
    - **Validates: Requirements 1.5, 9.3, 9.4**
    - Generate random error conditions (S3, DynamoDB, parsing errors)
    - Verify Lambda never raises exceptions and always returns 200
    - Tag: Feature: cache-builder-lambda, Property 2: Fire-and-forget error handling

- [ ] 2. Implement S3 act file discovery and mapping
  - [x] 2.1 Create discover_act_files function
    - Implement S3 list_objects_v2 with prefix executions/{execution_id}/act_
    - Parse act_id from S3 keys using regex pattern act_(.+)\.json
    - Build and return dictionary mapping {act_id: s3_key}
    - Handle empty results and S3 access errors gracefully with logging
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 2.2 Write property test for S3 act file mapping
    - **Property 3: S3 Act File Mapping**
    - **Validates: Requirements 3.2, 3.3**
    - Generate random S3 object lists with keys matching pattern
    - Verify correct act_id extraction and mapping dictionary construction
    - Tag: Feature: cache-builder-lambda, Property 3: S3 act file mapping

- [ ] 3. Implement execution step retrieval and filtering
  - [x] 3.1 Create get_execution_steps function
    - Implement DynamoDB query with pk: EXECUTION#{execution_id}, sk begins_with: EXECUTION_STEP#
    - Return list of EXECUTION_STEP records
    - Handle DynamoDB errors gracefully with logging
    - _Requirements: 4.1_

  - [x] 3.2 Create filter_navigation_steps function
    - Filter steps where step_type equals "navigation"
    - Skip steps with missing or null act_id
    - Skip steps where act_id not in act_mapping
    - Log count of navigation steps found and steps with matching act files
    - _Requirements: 4.2, 4.3, 4.4, 4.5_

  - [ ]* 3.3 Write property test for navigation step filtering
    - **Property 4: Navigation Step Filtering**
    - **Validates: Requirements 4.2, 4.4**
    - Generate random lists of EXECUTION_STEP records with mixed step_types
    - Verify only navigation steps with act_id in mapping are returned
    - Tag: Feature: cache-builder-lambda, Property 4: Navigation step filtering

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement Nova Act response parsing and cache storage
  - [x] 5.1 Create fetch_and_parse_act_response function
    - Implement S3 get_object to fetch Nova Act response JSON
    - Call parse_nova_act_steps from worker.cache_parser module
    - Return parsed cached steps or None if parsing fails
    - Handle S3 fetch errors and parsing exceptions gracefully with logging
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 12.1_

  - [x] 5.2 Create update_step_caches function with batch_writer
    - Use DynamoDB batch_writer for efficient batch updates
    - Update STEP records (pk: USECASE#{usecase_id}, sk: STEP#{step_id})
    - Store cached_steps as JSON string and cache_last_updated timestamp
    - Track successful and failed updates, return tuple (successful, failed)
    - Handle DynamoDB update errors gracefully by logging and continuing
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.2, 7.4_

  - [ ]* 5.3 Write property test for parsing error resilience
    - **Property 5: Parsing Error Resilience**
    - **Validates: Requirements 5.4**
    - Generate Nova Act responses that cause parse_nova_act_steps to raise exceptions
    - Verify Lambda catches exception, logs it, and continues processing
    - Tag: Feature: cache-builder-lambda, Property 5: Parsing error resilience

  - [ ]* 5.4 Write property test for S3 fetch error resilience
    - **Property 6: S3 Fetch Error Resilience**
    - **Validates: Requirements 5.5**
    - Mock S3 get_object to raise exceptions
    - Verify Lambda catches exception, logs it, and continues processing
    - Tag: Feature: cache-builder-lambda, Property 6: S3 fetch error resilience

  - [ ]* 5.5 Write property test for cache serialization round-trip
    - **Property 7: Cache Serialization Round-Trip**
    - **Validates: Requirements 6.2**
    - Generate random parsed cached steps lists
    - Verify JSON serialization and deserialization preserves structure
    - Tag: Feature: cache-builder-lambda, Property 7: Cache serialization round-trip

- [ ] 6. Implement step ID resolution and error resilience
  - [x] 6.1 Add step_id extraction and validation
    - Extract step_id field from EXECUTION_STEP records
    - Log error and skip step if step_id field is missing
    - Construct STEP record key as pk: USECASE#{usecase_id}, sk: STEP#{step_id}
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 6.2 Integrate all components in lambda_handler
    - Wire together eligibility check, S3 discovery, step retrieval, filtering, parsing, and cache updates
    - Implement step-level error isolation (individual failures don't stop processing)
    - Track and log statistics (steps_processed, successful_updates, failed_updates)
    - Return success response with statistics in body
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.7, 9.2, 9.5_

  - [ ]* 6.3 Write property test for DynamoDB update error resilience
    - **Property 8: DynamoDB Update Error Resilience**
    - **Validates: Requirements 6.5**
    - Mock batch_writer to fail for specific steps
    - Verify Lambda logs error and continues processing remaining steps
    - Tag: Feature: cache-builder-lambda, Property 8: DynamoDB update error resilience

  - [ ]* 6.4 Write property test for STEP record identification
    - **Property 9: STEP Record Identification**
    - **Validates: Requirements 7.2, 7.4**
    - Generate EXECUTION_STEP records with step_id fields
    - Verify correct STEP record key construction using step_id (not execution_step_id)
    - Tag: Feature: cache-builder-lambda, Property 9: STEP record identification

  - [ ]* 6.5 Write property test for missing STEP record resilience
    - **Property 10: Missing STEP Record Resilience**
    - **Validates: Requirements 7.5**
    - Mock STEP records that no longer exist
    - Verify Lambda handles update failure gracefully and continues
    - Tag: Feature: cache-builder-lambda, Property 10: Missing STEP record resilience

  - [ ]* 6.6 Write property test for individual step failure isolation
    - **Property 11: Individual Step Failure Isolation**
    - **Validates: Requirements 9.2**
    - Generate executions with multiple steps where one fails
    - Verify Lambda continues processing all remaining steps
    - Tag: Feature: cache-builder-lambda, Property 11: Individual step failure isolation

  - [ ]* 6.7 Write property test for update statistics tracking
    - **Property 12: Update Statistics Tracking**
    - **Validates: Requirements 9.5**
    - Generate batches of step updates with mixed success/failure
    - Verify accurate tracking and logging of successful vs failed updates
    - Tag: Feature: cache-builder-lambda, Property 12: Update statistics tracking

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Write unit tests for specific scenarios
  - [x] 8.1 Write unit test for successful cache building
    - Mock boto3 S3 and DynamoDB clients
    - Test complete flow with valid inputs and successful cache building
    - Verify all functions called correctly and cache stored
    - _Requirements: 11.2_

  - [x] 8.2 Write unit test for skipping non-success executions
    - Test Lambda skips processing when execution_status != "success"
    - Verify appropriate logging and early return
    - _Requirements: 11.3_

  - [x] 8.3 Write unit test for skipping when cache disabled
    - Test Lambda skips processing when enable_cache is false
    - Verify appropriate logging and early return
    - _Requirements: 11.4_

  - [x] 8.4 Write unit test for missing USECASE record
    - Test Lambda handles missing USECASE record gracefully
    - Verify error logging and return without raising exception
    - _Requirements: 11.5_

  - [x] 8.5 Write unit test for empty S3 act file list
    - Test Lambda handles empty S3 results gracefully
    - Verify warning logging and return without raising exception
    - _Requirements: 11.6_

  - [x] 8.6 Write unit test for parsing failures
    - Mock parse_nova_act_steps to return None
    - Verify Lambda logs warning and skips step
    - _Requirements: 11.7_

  - [x] 8.7 Write unit test for S3 fetch errors
    - Mock S3 get_object to raise exception
    - Verify Lambda logs error and continues processing
    - _Requirements: 11.8_

  - [x] 8.8 Write unit test for DynamoDB update errors
    - Mock DynamoDB batch_writer to raise exception
    - Verify Lambda logs error and continues processing
    - _Requirements: 11.9_

  - [x] 8.9 Write unit test for batch_writer usage
    - Verify Lambda uses DynamoDB batch_writer for efficient updates
    - Check batch_writer context manager usage
    - _Requirements: 11.10_

  - [x] 8.10 Verify test coverage meets 70% minimum
    - Run pytest with coverage report
    - Ensure minimum 70% code coverage achieved
    - _Requirements: 11.11_

- [ ] 9. Add CDK infrastructure configuration
  - [x] 9.1 Add Lambda function definition to worker-stack.ts
    - Create Lambda using createPythonLambda with path 'build_cache'
    - Set timeout to 60 seconds and memory to 512 MB
    - Add environment variables for DYNAMODB_TABLE_NAME and S3_BUCKET
    - _Requirements: 10.1, 10.6, 10.7_

  - [x] 9.2 Grant Lambda IAM permissions
    - Grant S3 read access to artefactsBucket
    - Grant DynamoDB read/write access using tableReadPolicy and tableWritePolicy
    - _Requirements: 10.2, 10.3_

  - [x] 9.3 Create EventBridge rule for cache builder
    - Define EventBridge rule matching source 'qa-studio.worker' and detail-type 'usecase.execution.completed'
    - Add Lambda as target for the rule
    - _Requirements: 10.4, 10.5, 12.2_

- [x] 10. Final checkpoint - Ensure all tests pass and integration works
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using hypothesis library (minimum 100 iterations)
- Unit tests validate specific examples and edge cases
- Lambda follows fire-and-forget pattern where all errors are caught and logged
- Target: 70% minimum unit test coverage
- Integration with existing cache_parser module from worker/cache_parser.py
- CDK infrastructure added to web-app/lib/worker-stack.ts
