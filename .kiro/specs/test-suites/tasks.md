# Implementation Plan: Test Suites

## Overview

This implementation plan breaks down the Test Suites feature into discrete coding tasks. The feature will be implemented in phases: backend foundation, execution engine, frontend implementation, scheduling, and polish.

## Tasks

- [x] 1. Backend Foundation - Data Model and CRUD Operations
  - [x] 1.1 Create DynamoDB schema utilities for test suites
    - Add schema definitions for TEST_SUITES, SUITE#{suite_id}, SUITE_EXECUTION#{suite_id}, and SUITE_EXEC#{execution_id} entities
    - Create helper functions for partition key and sort key generation
    - _Requirements: 1.1, 10.1, 10.2, 10.4_
  
  - [x] 1.2 Implement create_test_suite.py Lambda function
    - Validate user has write access to specified scope
    - Generate UUID for suite
    - Create suite item in DynamoDB with all required fields
    - Return created suite object
    - _Requirements: 1.1, 5.1_
  
  - [ ]* 1.3 Write property test for suite creation
    - **Property 1: Suite CRUD Round Trip**
    - **Validates: Requirements 1.1, 1.3**
  
  - [x] 1.4 Implement list_test_suites.py Lambda function
    - Query pk = 'TEST_SUITES'
    - Filter by user's accessible scopes (application-level)
    - Support tag and scope query parameters
    - Return array of suite objects
    - _Requirements: 1.2, 7.2_
  
  - [ ]* 1.5 Write property test for scope-based filtering
    - **Property 4: Scope-Based Suite Filtering**
    - **Validates: Requirements 1.2**
  
  - [x] 1.6 Implement get_test_suite.py Lambda function
    - Get suite by ID from DynamoDB
    - Validate user has read access to suite scope
    - Return suite object with all metadata
    - _Requirements: 1.3, 5.2_
  
  - [x] 1.7 Implement update_test_suite.py Lambda function
    - Validate user has write access to suite scope
    - Update suite metadata (name, description, tags)
    - Update updated_at timestamp
    - Return updated suite object
    - _Requirements: 1.4_
  
  - [ ]* 1.8 Write property test for suite updates
    - **Property 2: Suite Update Persistence**
    - **Validates: Requirements 1.4**
  
  - [x] 1.9 Implement delete_test_suite.py Lambda function
    - Validate user has write access to suite scope
    - Delete suite item from DynamoDB
    - Query and delete all suite-usecase mappings
    - Disable EventBridge schedule if exists
    - Return 204 No Content
    - _Requirements: 1.5, 6.5_
  
  - [ ]* 1.10 Write property test for suite deletion cascade
    - **Property 3: Suite Deletion Cascade**
    - **Validates: Requirements 1.5, 6.5**

- [x] 2. Backend - Use Case Association Management
  - [x] 2.1 Implement add_usecases_to_suite.py Lambda function
    - Validate user has write access to suite scope
    - For each use case: validate read access, get metadata, create mapping
    - Update total_usecases count on suite
    - Return count of added use cases
    - _Requirements: 2.1, 5.4, 10.2_
  
  - [ ]* 2.2 Write property test for use case mapping creation
    - **Property 5: Use Case Mapping Creation**
    - **Validates: Requirements 2.1, 10.2**
  
  - [ ]* 2.3 Write property test for mapping idempotency
    - **Property 6: Use Case Mapping Idempotency**
    - **Validates: Requirements 2.2**
  
  - [x] 2.4 Implement list_suite_usecases.py Lambda function
    - Validate user has read access to suite scope
    - Query pk = 'SUITE#{suite_id}', sk begins_with 'USECASE#'
    - Return array of use case objects with metadata
    - _Requirements: 2.3_
  
  - [x] 2.5 Implement remove_usecase_from_suite.py Lambda function
    - Validate user has write access to suite scope
    - Delete mapping item from DynamoDB
    - Decrement total_usecases count on suite
    - Return 204 No Content
    - _Requirements: 2.4_
  
  - [ ]* 2.6 Write property test for use case removal
    - **Property 7: Use Case Mapping Removal**
    - **Validates: Requirements 2.4**
  
  - [ ]* 2.7 Write property test for many-to-many deletion
    - **Property 8: Many-to-Many Use Case Deletion**
    - **Validates: Requirements 2.5, 10.1, 10.5**

- [x] 3. Backend - Scope Validation Utilities
  - [x] 3.1 Add validate_scope_access function to utils.py
    - Implement scope validation logic (wildcard, specific permission, write implies read/execute)
    - Raise PermissionError if user lacks required permission
    - Support suite:* and usecase:* scope patterns
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  
  - [ ]* 3.2 Write property tests for authorization enforcement
    - **Property 15: Authorization Enforcement**
    - **Property 16: Cross-Resource Authorization**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

- [x] 4. Infrastructure - API Gateway and Lambda Configuration
  - [x] 4.1 Add test suite API routes to lib/api-stack.ts
    - Add /test-suites routes (GET, POST)
    - Add /test-suites/{suite_id} routes (GET, PUT, DELETE)
    - Add /test-suites/{suite_id}/usecases routes (GET, POST)
    - Add /test-suites/{suite_id}/usecases/{usecase_id} route (DELETE)
    - Wire routes to Lambda functions
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.3, 2.4_
  
  - [x] 4.2 Add Lambda function definitions to lib/lambda-stack.ts
    - Create Lambda functions for all suite management operations
    - Grant DynamoDB read/write permissions
    - Set environment variables (TABLE_NAME)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.3, 2.4_

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Backend - Suite Execution Engine
  - [x] 6.1 Implement execute_test_suite.py Lambda function
    - Validate user has execute access to suite scope
    - Create suite execution record with status='running'
    - Query all use cases in suite
    - Invoke execute_usecase Lambda for each use case in parallel
    - Create execution result records with status='pending'
    - Store task ARNs and usecase_execution_ids
    - Return suite execution ID and metadata
    - _Requirements: 3.1, 3.2, 5.3_
  
  - [ ]* 6.2 Write property test for parallel execution initialization
    - **Property 9: Parallel Execution Initialization**
    - **Validates: Requirements 3.1, 3.2**
  
  - [x] 6.3 Implement list_suite_executions.py Lambda function
    - Validate user has read access to suite scope
    - Query pk = 'SUITE_EXECUTION#{suite_id}', sk begins_with 'EXECUTION#'
    - Support pagination (limit parameter)
    - Support status filtering
    - Return array of execution objects sorted by started_at descending
    - _Requirements: 9.1, 9.2, 9.3_
  
  - [ ]* 6.4 Write property tests for execution listing
    - **Property 25: Execution List Sort Order**
    - **Property 26: Execution List Pagination**
    - **Property 27: Execution List Filtering**
    - **Validates: Requirements 9.1, 9.2, 9.3**
  
  - [x] 6.5 Implement get_suite_execution.py Lambda function
    - Validate user has read access to suite scope
    - Get suite execution metadata
    - Query all execution results (pk = 'SUITE_EXEC#{execution_id}')
    - Return execution object with results array
    - _Requirements: 4.3, 9.4, 9.5_
  
  - [ ]* 6.6 Write property test for execution detail completeness
    - **Property 14: Execution Status Query Completeness**
    - **Property 28: Execution Detail Completeness**
    - **Validates: Requirements 4.3, 9.4, 9.5**
  
  - [x] 6.7 Implement stop_suite_execution.py Lambda function
    - Validate user has execute access to suite scope
    - Query all execution results with status='running'
    - For each running result: stop ECS task, update status to 'failed'
    - Update suite execution status
    - Return count of stopped tasks
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  
  - [ ]* 6.8 Write property tests for stop execution
    - **Property 22: Stop Execution Completeness**
    - **Property 23: Stop Execution Status Update**
    - **Property 24: Stop Execution Authorization**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 7. Backend - Event Handler Integration
  - [x] 7.1 Modify handle_task_state_change.py for suite execution tracking
    - Add query_suite_execution_results function to find suite executions containing a use case execution
    - Add update_suite_execution_result function to update individual result status
    - Add update_suite_execution_counters function to increment/decrement counters atomically
    - Add check_suite_completion function to determine final suite status
    - Integrate suite execution updates into existing event handler
    - _Requirements: 3.3, 3.4, 3.5, 4.1, 4.2, 4.4, 4.5, 7.1, 7.4, 10.3_
  
  - [x] 7.2 Handle stopped use case executions in suite tracking
    - Update worker/dynamodb_client.py update_suite_execution_counters to handle 'stopped' status
    - Treat 'stopped' status as 'failed' for suite execution counter purposes
    - Update handle_task_state_change.py to handle 'stopped' status
    - Ensure suite execution completes when all use cases are done (including stopped ones)
    - _Requirements: 8.6_
  
  - [ ]* 7.3 Write property tests for execution tracking
    - **Property 10: Independent Result Updates**
    - **Property 11: Failure Isolation**
    - **Property 12: Suite Status Determination**
    - **Property 13: Execution Counter Accuracy**
    - **Property 19: Execution Metrics Denormalization**
    - **Validates: Requirements 3.3, 3.4, 3.5, 4.1, 4.2, 4.4, 4.5, 7.1, 7.4, 10.3**

- [x] 8. Infrastructure - Execution API Routes and Permissions
  - [x] 8.1 Add execution API routes to lib/api-stack.ts
    - Add /test-suites/{suite_id}/execute route (POST)
    - Add /test-suites/{suite_id}/executions routes (GET)
    - Add /test-suites/{suite_id}/executions/{execution_id} route (GET)
    - Add /test-suites/{suite_id}/executions/{execution_id}/stop route (POST)
    - Wire routes to Lambda functions
    - _Requirements: 3.1, 4.3, 8.1, 9.1, 9.4_
  
  - [x] 8.2 Add execution Lambda definitions to lib/lambda-stack.ts
    - Create Lambda functions for execution operations
    - Grant DynamoDB read/write permissions
    - Grant execute_usecase Lambda invocation permission to execute_suite Lambda
    - Grant ECS StopTask permission to stop_suite_execution Lambda
    - Set environment variables (TABLE_NAME, EXECUTE_USECASE_LAMBDA_ARN, CLUSTER_ARN)
    - _Requirements: 3.1, 4.3, 8.1, 9.1, 9.4_

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Backend - Suite Scheduling
  - [x] 10.1 Implement update_suite_schedule.py Lambda function
    - Validate user has write access to suite scope
    - Update schedule fields on suite entity
    - If schedule_enabled=true: create/update EventBridge rule with cron expression
    - If schedule_enabled=false: disable EventBridge rule
    - Return updated suite object
    - _Requirements: 6.1, 6.4_
  
  - [ ]* 10.2 Write property tests for schedule configuration
    - **Property 17: Schedule Configuration Persistence**
    - **Validates: Requirements 6.1, 6.4**
  
  - [ ]* 10.3 Write property test for scheduled execution metadata
    - **Property 18: Scheduled Execution Metadata**
    - **Validates: Requirements 6.3**

- [ ] 11. Infrastructure - Scheduling Configuration
  - [x] 11.1 Add schedule API route to lib/api-stack.ts
    - Add /test-suites/{suite_id}/schedule route (PUT)
    - Wire route to update_suite_schedule Lambda
    - _Requirements: 6.1, 6.4_
  
  - [x] 11.2 Add schedule Lambda definition to lib/lambda-stack.ts
    - Create update_suite_schedule Lambda function
    - Grant DynamoDB read/write permissions
    - Grant EventBridge permissions (PutRule, PutTargets, EnableRule, DisableRule)
    - Set environment variables (TABLE_NAME, EVENTBRIDGE_RULE_PREFIX, EXECUTE_SUITE_LAMBDA_ARN)
    - _Requirements: 6.1, 6.4_
  
  - [x] 11.3 Configure EventBridge to invoke execute_suite Lambda
    - Grant EventBridge permission to invoke execute_suite Lambda
    - Configure rule naming convention: {baseName}-suite-{suite_id}
    - _Requirements: 6.1, 6.2_

- [x] 12. Frontend - API Integration Layer
  - [x] 12.1 Add test suite API methods to frontend/src/utils/api.ts
    - Add testSuites.create, list, get, update, delete methods
    - Add testSuites.addUsecases, listUsecases, removeUsecase methods
    - Add testSuites.updateSchedule method
    - Add testSuites.execute, listExecutions, getExecution, stopExecution methods
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.3, 2.4, 3.1, 4.3, 6.1, 8.1, 9.1, 9.4_
  
  - [x] 12.2 Add TypeScript interfaces to frontend/src/types/
    - Add TestSuite, SuiteExecution, SuiteExecutionResult interfaces
    - Add CreateTestSuiteRequest, UpdateTestSuiteRequest, ScheduleConfig interfaces
    - _Requirements: 1.1, 3.1, 4.3_

- [x] 13. Frontend - Test Suite List View
  - [x] 13.1 Create TestSuites.tsx component
    - Display table with columns: Name, Description, Total Tests, Last Run, Success Rate, Status, Schedule, Actions
    - Add filter by tags and scope
    - Add search by name
    - Add "Create Test Suite" button
    - Add actions dropdown: Execute, Edit, Delete
    - _Requirements: 1.2, 7.2, 7.5_
  
  - [x] 13.2 Create CreateTestSuite.tsx modal component
    - Add form fields: Name, Description, Scope, Tags
    - Add validation: Name 3-100 chars, valid scope format
    - Integrate with create_test_suite API
    - _Requirements: 1.1_
  
  - [x] 13.3 Update App.tsx navigation
    - Add "Test Suites" link in Testing section
    - Add route for /test-suites
    - _Requirements: 1.2_

- [x] 14. Frontend - Test Suite Detail View
  - [x] 14.1 Create TestSuiteDetail.tsx component
    - Display suite header with name, description, scope, tags
    - Add actions bar: Execute Suite, Add Use Cases, Configure Schedule buttons
    - Display use cases table with columns: Name, Scope, Status, Actions
    - Display recent executions table (last 10)
    - Add edit and delete buttons
    - _Requirements: 1.3, 2.3, 7.3_
  
  - [x] 14.2 Create AddUsecasesToSuite.tsx modal component
    - Display multi-select table of available use cases
    - Add filter by name, tags, scope
    - Disable use cases already in suite
    - Add "Add Selected" button
    - _Requirements: 2.1_
  
  - [x] 14.3 Create ConfigureSchedule.tsx modal component
    - Add form fields: Enable Schedule toggle, Schedule Expression, Timezone
    - Add cron expression presets and validation
    - Add next run preview
    - Integrate with update_suite_schedule API
    - _Requirements: 6.1_

- [ ] 15. Frontend - Suite Execution View
  - [x] 15.1 Create SuiteExecutionDetail.tsx component
    - Display execution header with suite name, execution ID, started time, duration, status
    - Add progress bar showing completed/total tests
    - Display summary cards: Total Tests, Completed, Successful, Failed, Running
    - Display results table with columns: Use Case Name, Status, Started, Duration, Actions
    - Add "Stop Execution" button (if running)
    - Add "Re-run Suite" button (if completed)
    - _Requirements: 4.3, 9.4_
  
  - [x] 15.2 Implement real-time polling for execution status
    - Poll GET /test-suites/{suite_id}/executions/{execution_id} every 5 seconds when status is 'running'
    - Update UI with live progress
    - Stop polling when execution completes
    - _Requirements: 4.3_

- [x] 16. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 17. Integration Testing and Polish
  - [ ]* 17.1 Write integration tests for complete suite execution flow
    - Test creating suite, adding use cases, executing, monitoring status
    - Test scheduled execution flow
    - Test stop execution flow
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5_
  
  - [ ]* 17.2 Write integration tests for authorization flows
    - Test operations with various user scope combinations
    - Verify only authorized operations succeed
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  
  - [x] 17.3 Add error handling and user feedback
    - Add loading states and skeletons to all components
    - Add error messages for failed operations
    - Add success notifications for completed operations
    - _Requirements: All_
  
  - [x] 17.4 Add metrics and monitoring
    - Add CloudWatch metrics for suite executions
    - Add logging for all Lambda functions
    - Add error tracking
    - _Requirements: All_

- [x] 18. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- Backend uses Python for Lambda functions
- Frontend uses TypeScript/React
- Infrastructure uses AWS CDK (TypeScript)
