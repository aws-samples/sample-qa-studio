# Requirements Document

## Introduction

This document defines the requirements for end-to-end integration testing of the step cache system. The cache system optimizes test execution by storing parsed navigation steps from Nova Act responses and replaying them directly via Playwright, reducing execution time by 5x or more. Integration testing validates the complete flow from cache building through cache execution, including performance benchmarks and failure scenarios.

## Glossary

- **Cache_System**: The complete step caching implementation including parser, executor, builder Lambda, and worker integration
- **Test_Suite**: The integration test suite that validates end-to-end cache functionality
- **Cache_Builder**: The Lambda function that parses Nova Act responses and stores cached steps in DynamoDB
- **Cache_Executor**: The worker component that executes cached steps via Playwright
- **Nova_Act**: The AI agent that generates browser automation steps
- **USECASE**: A DynamoDB record representing a test case with multiple steps
- **STEP**: A DynamoDB record representing a single test step within a usecase
- **EXECUTION_STEP**: A DynamoDB record representing a step execution instance
- **Cache_Hit**: When a step is executed using cached steps instead of Nova Act
- **Cache_Miss**: When a step is executed using Nova Act because no cache exists
- **Cache_Invalidation**: The process of removing cached steps when the instruction changes
- **Speedup_Ratio**: The ratio of Nova Act execution time to cached execution time
- **Performance_Benchmark**: A test that measures and validates cache performance improvements
- **Load_Test**: A test that validates cache system behavior under high volume

## Requirements

### Requirement 1: Cache Building Flow Validation

**User Story:** As a QA engineer, I want to verify that the cache building flow works correctly after successful test execution, so that cached steps are available for subsequent runs.

#### Acceptance Criteria

1. WHEN a usecase with `enable_cache=True` is created, THE Test_Suite SHALL verify the usecase record contains `enable_cache=True`
2. WHEN a navigation step is created for the usecase, THE Test_Suite SHALL verify the step record is created successfully
3. WHEN the usecase is executed for the first time, THE Test_Suite SHALL verify the execution completes successfully
4. WHEN the execution completes, THE Test_Suite SHALL verify the EventBridge event `usecase.execution.completed` is emitted
5. WHEN the Cache_Builder processes the event, THE Test_Suite SHALL verify the STEP record is updated with `cached_steps` field
6. WHEN the cache is built, THE Test_Suite SHALL verify the `cached_steps` field contains valid JSON with parsed actions
7. WHEN the cache is built, THE Test_Suite SHALL verify the `cache_last_updated` field contains a valid ISO timestamp

### Requirement 2: Cache Execution Flow Validation

**User Story:** As a QA engineer, I want to verify that cached steps are executed correctly on subsequent runs, so that tests run faster without calling Nova Act.

#### Acceptance Criteria

1. WHEN a usecase with cached steps is executed, THE Test_Suite SHALL verify the Cache_Executor is invoked
2. WHEN cached steps are executed, THE Test_Suite SHALL verify Nova Act is not called
3. WHEN cached steps are executed, THE Test_Suite SHALL verify the execution completes successfully
4. WHEN cached steps are executed, THE Test_Suite SHALL verify the EXECUTION_STEP record contains `act_id='cached'`
5. WHEN cached steps are executed, THE Test_Suite SHALL verify the execution logs indicate "Cache hit"

### Requirement 3: Performance Benchmark Validation

**User Story:** As a QA engineer, I want to measure cache performance improvements, so that I can verify the cache provides the expected speedup.

#### Acceptance Criteria

1. WHEN a navigation step is executed without cache, THE Test_Suite SHALL measure and record the execution time
2. WHEN the same navigation step is executed with cache, THE Test_Suite SHALL measure and record the execution time
3. WHEN comparing execution times, THE Test_Suite SHALL verify the cached execution is at least 5 times faster than the uncached execution
4. WHEN the performance benchmark completes, THE Test_Suite SHALL log the Speedup_Ratio for observability
5. IF the Speedup_Ratio is less than 5, THEN THE Test_Suite SHALL fail the benchmark test with a descriptive error message

### Requirement 4: Cache Invalidation Validation

**User Story:** As a QA engineer, I want to verify that cache is invalidated when step instructions change, so that stale cached steps are not executed.

#### Acceptance Criteria

1. WHEN a STEP instruction is updated, THE Test_Suite SHALL verify the `cached_steps` field is cleared
2. WHEN a STEP instruction is updated, THE Test_Suite SHALL verify the `cache_last_updated` field is cleared
3. WHEN a step with cleared cache is executed, THE Test_Suite SHALL verify Nova Act is called
4. WHEN the execution completes, THE Test_Suite SHALL verify new cached steps are built
5. WHEN the step is executed again, THE Test_Suite SHALL verify the new cached steps are used

### Requirement 5: Cache Disable Flow Validation

**User Story:** As a QA engineer, I want to verify that disabling cache falls back to Nova Act, so that users can opt out of caching when needed.

#### Acceptance Criteria

1. WHEN a usecase with `enable_cache=False` is created, THE Test_Suite SHALL verify the usecase record contains `enable_cache=False`
2. WHEN a navigation step is executed with cache disabled, THE Test_Suite SHALL verify Nova Act is called
3. WHEN a navigation step is executed with cache disabled, THE Test_Suite SHALL verify no cached steps are built
4. WHEN a usecase with existing cached steps has `enable_cache` set to False, THE Test_Suite SHALL verify Nova Act is called instead of using cache
5. WHEN cache is disabled, THE Test_Suite SHALL verify the execution logs indicate "Cache miss: caching disabled"

### Requirement 6: Cache Execution Failure Fallback Validation

**User Story:** As a QA engineer, I want to verify that cache execution failures fall back to Nova Act, so that tests remain reliable even when cache execution fails.

#### Acceptance Criteria

1. WHEN cached step execution fails, THE Test_Suite SHALL verify the Cache_Executor raises an exception
2. WHEN the Cache_Executor raises an exception, THE Test_Suite SHALL verify Nova Act is called as fallback
3. WHEN Nova Act fallback succeeds, THE Test_Suite SHALL verify the execution completes successfully
4. WHEN fallback occurs, THE Test_Suite SHALL verify the execution logs contain "Cache execution failed" warning
5. WHEN fallback occurs, THE Test_Suite SHALL verify the EXECUTION_STEP record contains the Nova Act `act_id` (not "cached")

### Requirement 7: Multiple Step Cache Flow Validation

**User Story:** As a QA engineer, I want to verify that usecases with multiple navigation steps cache and execute correctly, so that complex test flows benefit from caching.

#### Acceptance Criteria

1. WHEN a usecase with multiple navigation steps is executed, THE Test_Suite SHALL verify all navigation steps are cached
2. WHEN the usecase is executed again, THE Test_Suite SHALL verify all navigation steps use cache
3. WHEN the usecase is executed again, THE Test_Suite SHALL verify the total execution time is at least 5 times faster
4. WHEN one step's instruction is updated, THE Test_Suite SHALL verify only that step's cache is invalidated
5. WHEN the usecase is executed after partial invalidation, THE Test_Suite SHALL verify unchanged steps use cache and the updated step calls Nova Act

### Requirement 8: Mixed Step Type Flow Validation

**User Story:** As a QA engineer, I want to verify that usecases with mixed step types (navigation and assertion) handle caching correctly, so that only navigation steps are cached.

#### Acceptance Criteria

1. WHEN a usecase contains navigation and assertion steps, THE Test_Suite SHALL verify only navigation steps are cached
2. WHEN the usecase is executed, THE Test_Suite SHALL verify navigation steps use cache
3. WHEN the usecase is executed, THE Test_Suite SHALL verify assertion steps call Nova Act
4. WHEN the usecase is executed, THE Test_Suite SHALL verify the execution completes successfully with mixed step types

### Requirement 9: Load Test Validation

**User Story:** As a QA engineer, I want to verify that the cache system handles high volume, so that the system remains stable under production load.

#### Acceptance Criteria

1. WHEN 10 usecases are executed concurrently, THE Test_Suite SHALL verify all executions complete successfully
2. WHEN concurrent executions complete, THE Test_Suite SHALL verify all navigation steps are cached
3. WHEN the 10 usecases are executed concurrently again, THE Test_Suite SHALL verify all use cache
4. WHEN concurrent cache executions complete, THE Test_Suite SHALL verify no cache execution failures occurred
5. WHEN the load test completes, THE Test_Suite SHALL verify the average Speedup_Ratio is at least 5

### Requirement 10: Cache Age Indicator Validation

**User Story:** As a QA engineer, I want to verify that cache age is tracked correctly, so that users can see when cached steps were last updated.

#### Acceptance Criteria

1. WHEN cached steps are built, THE Test_Suite SHALL verify the `cache_last_updated` timestamp is within 5 seconds of the current time
2. WHEN cached steps are retrieved, THE Test_Suite SHALL verify the `cache_last_updated` field is returned in the API response
3. WHEN cached steps are older than 1 day, THE Test_Suite SHALL verify the cache age is calculated correctly
4. WHEN the cache is invalidated, THE Test_Suite SHALL verify the `cache_last_updated` field is cleared

### Requirement 11: EventBridge Event Validation

**User Story:** As a QA engineer, I want to verify that EventBridge events are emitted correctly, so that the Cache_Builder is triggered reliably.

#### Acceptance Criteria

1. WHEN a usecase execution completes successfully, THE Test_Suite SHALL verify the `usecase.execution.completed` event is emitted
2. WHEN the event is emitted, THE Test_Suite SHALL verify it contains `usecase_id`, `execution_id`, `execution_status`, and `timestamp` fields
3. WHEN the event is emitted, THE Test_Suite SHALL verify the `execution_status` field is "success"
4. WHEN the event is emitted, THE Test_Suite SHALL verify the `source` field is "qa-studio.worker"
5. WHEN the event is emitted, THE Test_Suite SHALL verify the `detail-type` field is "usecase.execution.completed"

### Requirement 12: S3 Act File Discovery Validation

**User Story:** As a QA engineer, I want to verify that the Cache_Builder discovers Nova Act response files correctly, so that cached steps are built from the correct data.

#### Acceptance Criteria

1. WHEN the Cache_Builder processes an execution, THE Test_Suite SHALL verify it lists S3 objects with the correct prefix
2. WHEN S3 objects are listed, THE Test_Suite SHALL verify the Cache_Builder builds a mapping of `act_id` to S3 key
3. WHEN the mapping is built, THE Test_Suite SHALL verify all navigation step `act_id` values are present in the mapping
4. WHEN an `act_id` is not found in S3, THE Test_Suite SHALL verify the Cache_Builder skips that step with a warning log

### Requirement 13: Cache Parser Integration Validation

**User Story:** As a QA engineer, I want to verify that the cache parser correctly extracts actions from Nova Act responses, so that cached steps are accurate.

#### Acceptance Criteria

1. WHEN the Cache_Builder fetches a Nova Act response from S3, THE Test_Suite SHALL verify the parser is invoked
2. WHEN the parser processes the response, THE Test_Suite SHALL verify it extracts all cacheable actions (click, hover, scroll, type, navigate)
3. WHEN the parser processes the response, THE Test_Suite SHALL verify it skips non-cacheable actions (think, return, throw, wait)
4. WHEN the parser completes, THE Test_Suite SHALL verify the cached steps are stored as valid JSON in the STEP record

### Requirement 14: Error Handling Validation

**User Story:** As a QA engineer, I want to verify that the cache system handles errors gracefully, so that failures don't break the test execution flow.

#### Acceptance Criteria

1. IF the Cache_Builder fails to fetch an S3 file, THEN THE Test_Suite SHALL verify the Cache_Builder logs an error and continues processing other steps
2. IF the cache parser fails to parse a Nova Act response, THEN THE Test_Suite SHALL verify the Cache_Builder logs an error and skips that step
3. IF the Cache_Executor fails to execute a cached step, THEN THE Test_Suite SHALL verify the worker falls back to Nova Act
4. IF DynamoDB update fails during cache building, THEN THE Test_Suite SHALL verify the Cache_Builder logs an error and continues
5. IF EventBridge event emission fails, THEN THE Test_Suite SHALL verify the worker logs an error but completes the execution

### Requirement 15: Test Isolation Validation

**User Story:** As a QA engineer, I want to verify that integration tests are properly isolated, so that test failures don't affect other tests.

#### Acceptance Criteria

1. THE Test_Suite SHALL create unique usecase IDs for each test
2. THE Test_Suite SHALL clean up created usecases after each test completes
3. THE Test_Suite SHALL clean up created steps after each test completes
4. THE Test_Suite SHALL clean up S3 files after each test completes
5. IF a test fails, THEN THE Test_Suite SHALL still perform cleanup to prevent test pollution
