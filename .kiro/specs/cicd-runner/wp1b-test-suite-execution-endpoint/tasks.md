# Implementation Plan: Test Suite Execution Endpoint

## Overview

This implementation plan breaks down the creation of the `POST /api/test-suites/{id}/execute` endpoint into discrete, incremental coding tasks. Each task builds on previous work and includes testing to validate functionality early. The endpoint creates suite execution records and execution records for all usecases in a suite with overrides applied, without spawning ECS tasks.

## Tasks

- [x] 1. Create utility modules for URL override and variable merge
  - Create `lambdas/utils/url_override.py` with `apply_base_url_override()` function
  - Create `lambdas/utils/variable_merge.py` with `merge_variables()`, `validate_variables_resolved()`, and `get_unresolved_variables()` functions
  - Implement URL parsing logic using urllib.parse
  - Implement variable merge with precedence: CLI > usecase > secrets
  - Implement regex-based template variable detection
  - _Requirements: US2.2, US2.3, US3.2, US3.3_

- [ ]* 1.1 Write unit tests for URL override utility
  - Test basic domain replacement
  - Test path preservation
  - Test query parameter preservation
  - Test fragment preservation
  - Test scheme change (http to https)
  - Test None base_url returns original
  - **Property 4: Base URL Transformation Preserves Path and Query**
  - **Validates: Requirements US2.2, US2.3**

- [ ]* 1.2 Write unit tests for variable merge utility
  - Test CLI variables override usecase variables
  - Test usecase variables override secrets
  - Test CLI variables override secrets
  - Test merge with empty dictionaries
  - Test all variables preserved
  - **Property 5: Variable Merge Precedence**
  - **Validates: Requirements US3.2**

- [ ]* 1.3 Write unit tests for variable validation
  - Test validation passes with all variables resolved
  - Test validation fails with missing variables
  - Test validation checks starting_url
  - Test validation checks steps
  - Test validation checks hooks
  - **Property 6: Unresolved Variables Rejection**
  - **Validates: Requirements US3.3, US3.5**

- [x] 2. Implement core Lambda function structure
  - Create `lambdas/endpoints/execute_test_suite.py`
  - Implement handler function with event parsing
  - Add authentication using `allow_m2m_token()` utility
  - Add OAuth scope validation for `api/suite.write` and `api/execution.write`
  - Parse path parameters (suite_id) and request body
  - Implement basic error response structure
  - _Requirements: US1.1, US1.2_

- [x] 3. Implement test suite and usecase fetching
  - Implement `get_test_suite()` function to query DynamoDB
  - Implement `get_suite_usecases()` function to query suite-usecase mappings
  - Implement `get_usecase_definition()` function
  - Implement `get_usecase_secrets()` function
  - Implement `get_usecase_variables()` function
  - Add error handling for suite not found (404)
  - Add error handling for usecase not found (500)
  - _Requirements: US1.1, US1.3_

- [x] 4. Implement suite execution record creation
  - Implement `create_suite_execution_record()` function
  - Create DynamoDB item with pk='SUITE#{suite_id}', sk='SUITE_EXECUTION#{suite_execution_id}'
  - Set status='pending', trigger_type='ci_runner'
  - Store overrides in record
  - Generate UUIDv7 for suite_execution_id
  - Use existing `get_current_timestamp()` utility
  - _Requirements: US1.2, US5.1, US5.3_

- [ ]* 4.1 Write property test for suite execution record creation
  - **Property 1: Suite Execution Record Creation**
  - **Validates: Requirements US1.2, US5.1**

- [x] 5. Implement execution record creation for usecases
  - Implement `create_execution_record_for_usecase()` function
  - Reuse logic from existing `execute_usecase` Lambda
  - Create execution record with trigger_type='ci_runner'
  - Add suite_execution_id and suite_id fields to execution record
  - Copy steps from usecase to execution
  - Copy hooks from usecase to execution
  - Copy headers from usecase to execution
  - Apply base URL override to starting_url
  - Merge variables and store as EXECUTION_VARIABLES
  - Apply region and model_id overrides
  - _Requirements: US1.3, US2.2, US2.4, US3.2, US3.4, US4.3, US5.4_

- [ ]* 5.1 Write property test for complete execution record creation
  - **Property 2: Complete Execution Record Creation**
  - **Validates: Requirements US1.3, US1.4**

- [ ]* 5.2 Write property test for no ECS task spawning
  - **Property 3: No ECS Task Spawning**
  - **Validates: Requirements US1.5**

- [ ]* 5.3 Write property test for override application
  - **Property 7: Override Application to All Executions**
  - **Validates: Requirements US4.3, US4.4**

- [ ]* 5.4 Write property test for bidirectional linking
  - **Property 8: Bidirectional Suite-Execution Linking**
  - **Validates: Requirements US5.2, US5.4**

- [x] 6. Implement main execution flow orchestration
  - Implement main handler logic to orchestrate all steps
  - Fetch test suite definition
  - Fetch all usecase mappings
  - Create suite execution record
  - Loop through all usecases:
    - Fetch usecase definition, secrets, variables
    - Apply base URL override
    - Merge variables with precedence
    - Validate all variables resolved
    - Create execution record
  - Update suite execution record with all execution IDs
  - Return response with suite_execution_id and execution_ids
  - _Requirements: US1.1, US1.2, US1.3, US1.4_

- [x] 7. Implement error handling and validation
  - Add validation for trigger_type='ci_runner' (required)
  - Add validation for base_url format (if provided)
  - Add validation for variables dictionary (if provided)
  - Add validation for region format (if provided)
  - Implement error handling for missing variables (400)
  - Implement error handling for invalid base_url (400)
  - Implement error handling for suite not found (404)
  - Implement error handling for DynamoDB errors (500)
  - Ensure no execution records created if validation fails (fail fast)
  - _Requirements: US3.3, US3.5_

- [ ]* 7.1 Write unit tests for error handling
  - Test suite not found returns 404
  - Test missing variables returns 400
  - Test invalid base_url returns 400
  - Test insufficient permissions returns 403
  - Test usecase not found returns 500

- [x] 8. Add monitoring and observability
  - Add structured logging using JSON format
  - Log suite execution started event
  - Log each usecase execution created
  - Log overrides applied
  - Add CloudWatch custom metrics for suite executions created
  - Add CloudWatch custom metrics for execution creation duration
  - Publish EventBridge event for suite execution created
  - _Requirements: US1.2_

- [x] 9. Checkpoint - Ensure all tests pass
  - Run all unit tests and verify ≥70% coverage
  - Run property tests with minimum 100 iterations each
  - Fix any failing tests
  - Verify no regressions in existing functionality
  - Ask the user if questions arise

- [x] 10. Configure API Gateway endpoint
  - Add route `POST /test-suites/{id}/execute` in CDK stack
  - Configure Cognito authorizer
  - Configure Lambda integration
  - Add request validation
  - Add CORS configuration
  - Deploy to development environment
  - _Requirements: US1.1_

- [ ]* 10.1 Write integration tests for API endpoint
  - Test execute suite with no overrides
  - Test execute suite with base_url override
  - Test execute suite with variable overrides
  - Test execute suite with region/model overrides
  - Test execute suite with all overrides combined
  - Test suite not found returns 404
  - Test missing variables returns 400
  - Test insufficient scopes returns 403

- [x] 11. Update API documentation
  - Add endpoint specification to docs/API.md
  - Document request body schema
  - Document response format
  - Document error responses
  - Add example cURL and Python usage
  - Document OAuth scopes required
  - _Requirements: US1.1_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Run all unit tests
  - Run all property tests
  - Run all integration tests
  - Verify API documentation is complete
  - Verify CloudWatch logs are structured correctly
  - Ask the user if questions arise

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties with minimum 100 iterations
- Unit tests validate specific examples and edge cases
- Integration tests validate end-to-end flows
- Checkpoints ensure incremental validation
- The implementation reuses existing patterns from `execute_usecase` Lambda
- No new DynamoDB indexes required (uses existing query patterns)
- OAuth scope validation follows existing security patterns

