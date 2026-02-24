# Implementation Plan: WP3 - Execution Engine & Output

## Overview

Implement the test execution engine using Nova Act SDK to run all use cases in parallel locally with a bundled Chromium browser. Include execution status updates via API, result aggregation, summary output formatting, and exit code logic.

## Tasks

- [x] 1. Set up execution engine infrastructure
  - Create `src/execution/` directory
  - Create `src/output/` directory
  - Add Nova Act SDK and async dependencies to requirements.txt
  - _Requirements: US1.1, US1.2_

- [x] 2. Implement ExecutionAPI class for async API operations
  - [x] 2.1 Create `src/api/executions.py` with ExecutionAPI class
    - Implement `get_execution()` method with async wrapper
    - Implement `update_status()` method with async wrapper
    - Implement `update_suite_status()` method with async wrapper
    - Use `asyncio.to_thread()` to wrap synchronous APIClient calls
    - _Requirements: US2.1, US2.2, US2.5_
  
  - [ ]* 2.2 Write unit tests for ExecutionAPI
    - Test get_execution with mocked API client
    - Test update_status with various status values
    - Test update_suite_status
    - Test error handling for API failures
    - _Requirements: US2.1, US2.2, US2.5_

- [x] 3. Implement ExecutionEngine core class
  - [x] 3.1 Create `src/execution/engine.py` with ExecutionEngine class
    - Implement `__init__()` with ExecutionAPI dependency
    - Implement `_replace_variables()` helper method
    - Add logging configuration
    - _Requirements: US1.1_
  
  - [x] 3.2 Implement `execute_all()` method for parallel execution
    - Create tasks for all executions
    - Use `asyncio.gather(*tasks, return_exceptions=True)`
    - Convert exceptions to error results
    - Return list of processed results
    - _Requirements: US1.1, US1.3, US1.4_
  
  - [ ]* 3.3 Write property test for parallel execution
    - **Property 1: Parallel Execution**
    - **Validates: Requirements US1.1**
  
  - [ ]* 3.4 Write property test for fault isolation
    - **Property 3: Fault Isolation**
    - **Validates: Requirements US1.3**
  
  - [ ]* 3.5 Write property test for result completeness
    - **Property 4: Result Completeness**
    - **Validates: Requirements US1.4**

- [x] 4. Implement Nova Act SDK integration
  - [x] 4.1 Implement `_execute_with_nova_act()` method
    - Initialize NovaActClient with region and model_id
    - Create browser session in headless mode
    - Navigate to starting_url
    - Execute steps sequentially
    - Handle step failures gracefully
    - Return success/failure result
    - _Requirements: US1.2, US1.3_
  
  - [x] 4.2 Implement `_execute_step()` method
    - Replace variables in step instruction
    - Execute step with Nova Act session
    - Handle Nova Act errors
    - Raise ExecutionError on failure
    - _Requirements: US1.2_
  
  - [ ]* 4.3 Write unit tests for Nova Act integration
    - Test _execute_with_nova_act with mocked Nova Act client
    - Test _execute_step with variable substitution
    - Test error handling for Nova Act failures
    - Test browser session lifecycle
    - _Requirements: US1.2, US1.3_
  
  - [ ]* 4.4 Write property test for session isolation
    - **Property 2: Session Isolation**
    - **Validates: Requirements US1.2**

- [x] 5. Implement `execute_usecase()` method with status updates
  - [x] 5.1 Implement execution lifecycle
    - Update status to "running" at start
    - Fetch execution details from API
    - Execute with Nova Act SDK
    - Calculate duration
    - Update status to "completed" or "failed"
    - Handle exceptions and update status
    - Return execution result
    - _Requirements: US1.5, US2.1, US2.2, US2.3, US2.4_
  
  - [ ]* 5.2 Write property test for status lifecycle
    - **Property 5: Status Lifecycle**
    - **Validates: Requirements US2.1, US2.2, US2.4**
  
  - [ ]* 5.3 Write property test for error message inclusion
    - **Property 6: Error Message Inclusion**
    - **Validates: Requirements US2.3**
  
  - [ ]* 5.4 Write unit tests for execute_usecase
    - Test successful execution flow
    - Test execution with Nova Act failure
    - Test execution with API error
    - Test duration calculation
    - Test error message formatting
    - _Requirements: US1.5, US2.1, US2.2, US2.3_

- [x] 6. Checkpoint - Ensure execution engine tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement SummaryFormatter class
  - [x] 7.1 Create `src/output/summary.py` with SummaryFormatter class
    - Implement `format_table()` static method
    - Build ASCII table with box drawing characters
    - Include suite name and execution ID in header
    - Include start/end times and duration
    - List all use cases with status and duration
    - Calculate and display statistics (total, passed, failed, success %)
    - _Requirements: US3.1, US3.2, US3.5_
  
  - [x] 7.2 Implement `_format_duration()` helper method
    - Format seconds as "Xs"
    - Format minutes as "Xm Ys"
    - Format hours as "Xh Ym"
    - _Requirements: US3.1_
  
  - [ ]* 7.3 Write property test for summary completeness
    - **Property 8: Summary Completeness**
    - **Validates: Requirements US3.1, US3.5**
  
  - [ ]* 7.4 Write property test for statistics calculation
    - **Property 9: Statistics Calculation**
    - **Validates: Requirements US3.2**
  
  - [ ]* 7.5 Write unit tests for SummaryFormatter
    - Test format_table with various result sets
    - Test format_table with all passed
    - Test format_table with all failed
    - Test format_table with mixed results
    - Test _format_duration for seconds, minutes, hours
    - Test table structure and formatting
    - _Requirements: US3.1, US3.2, US3.5_

- [-] 8. Implement exit code logic
  - [x] 8.1 Add `determine_exit_code()` function to `src/main.py`
    - Return 0 if all results have status="completed"
    - Return 1 if any result has status="failed"
    - Return 2 if results list is empty
    - _Requirements: US4.1, US4.2, US4.3_
  
  - [ ]* 8.2 Write property test for exit code success
    - **Property 10: Exit Code for Success**
    - **Validates: Requirements US4.1**
  
  - [ ]* 8.3 Write property test for exit code failure
    - **Property 11: Exit Code for Failure**
    - **Validates: Requirements US4.2**
  
  - [ ]* 8.4 Write property test for exit code error
    - **Property 12: Exit Code for Error**
    - **Validates: Requirements US4.3**
  
  - [ ]* 8.5 Write unit tests for exit code logic
    - Test exit code 0 with all passed
    - Test exit code 1 with some failed
    - Test exit code 2 with empty results
    - _Requirements: US4.1, US4.2, US4.3_

- [x] 9. Integrate execution engine into main runner
  - [x] 9.1 Update `src/main.py` to use ExecutionEngine
    - Import ExecutionEngine and SummaryFormatter
    - After execute_suite API call, extract execution_ids
    - Initialize ExecutionEngine with ExecutionAPI
    - Call `execute_all()` with execution_ids
    - Update suite execution status based on results
    - Format and print summary table to stdout
    - Determine and return exit code
    - _Requirements: US1.1, US2.5, US3.3, US4.4_
  
  - [x] 9.2 Add verbose logging support
    - Check for --verbose CLI flag
    - Set log level to DEBUG if verbose
    - Ensure detailed logs shown in verbose mode
    - _Requirements: US3.4_
  
  - [ ]* 9.3 Write integration test for full execution flow
    - Test end-to-end execution with mocked API and Nova Act
    - Verify status updates sent
    - Verify summary printed
    - Verify exit code correct
    - _Requirements: US1.1, US2.1, US2.2, US2.5, US3.3, US4.1_

- [x] 10. Add error handling and logging
  - [x] 10.1 Add ExecutionError to `src/utils/errors.py`
    - Define ExecutionError exception class
    - Add descriptive error messages
    - _Requirements: US1.3_
  
  - [x] 10.2 Implement error sanitization
    - Add function to sanitize error messages
    - Remove sensitive data (URLs with params, emails)
    - Apply to all error messages before logging
    - _Requirements: US2.3_
  
  - [ ]* 10.3 Write unit tests for error handling
    - Test ExecutionError creation
    - Test error message sanitization
    - Test error logging
    - _Requirements: US1.3, US2.3_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional property-based and unit tests
- Each property test should run minimum 100 iterations
- Property tests should be tagged with feature name and property number
- Integration tests should use mocked external dependencies (API, Nova Act)
- Verbose mode is controlled by existing --verbose CLI flag from WP2
- Exit code should be set after summary is printed to stdout
