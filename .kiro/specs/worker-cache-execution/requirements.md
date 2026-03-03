# Requirements Document

## Introduction

This feature implements cache execution in the worker to accelerate test execution by 40-60%. When a usecase has caching enabled and a navigation step has cached steps available, the worker will execute those cached steps directly using Playwright instead of calling Nova Act. This eliminates the LLM inference latency while maintaining test reliability through automatic fallback to Nova Act on cache failures.

The cache execution integrates with the existing step cache system (Packages 1-6) and leverages the cache_executor module to replay previously successful Nova Act actions.

## Glossary

- **Worker**: The ECS task that executes test usecases by orchestrating Nova Act and validating results
- **Nova_Act**: The AI agent that interprets natural language instructions and generates browser automation code
- **Cache_Executor**: The module that executes cached steps using Playwright API (from Package 2)
- **Navigation_Step**: A test step that performs browser interactions (clicks, typing, navigation)
- **Cached_Steps**: A JSON array of parsed Nova Act actions stored in the STEP record
- **Usecase_Config**: The USECASE record containing the enable_cache flag
- **Cache_Hit**: When cached steps are successfully executed without calling Nova Act
- **Cache_Miss**: When cached steps are unavailable or execution fails, requiring Nova Act fallback
- **Execution_Step**: The runtime representation of a step during test execution

## Requirements

### Requirement 1: Cache Availability Check

**User Story:** As a test execution system, I want to check if cached steps are available before executing a navigation step, so that I can decide whether to use cache or Nova Act

#### Acceptance Criteria

1. WHEN executing a navigation step, THE Worker SHALL check if enable_cache is True on the Usecase_Config
2. WHEN executing a navigation step, THE Worker SHALL check if cached_steps field exists on the Execution_Step
3. WHEN executing a navigation step, THE Worker SHALL check if cached_steps is not null and not empty
4. IF enable_cache is False, THEN THE Worker SHALL skip cache execution and call Nova_Act
5. IF cached_steps is null or empty, THEN THE Worker SHALL skip cache execution and call Nova_Act
6. IF both enable_cache is True AND cached_steps exists, THEN THE Worker SHALL attempt cache execution

### Requirement 2: Cache Execution

**User Story:** As a test execution system, I want to execute cached steps using Playwright, so that I can avoid Nova Act latency and speed up test execution

#### Acceptance Criteria

1. WHEN cache is available, THE Worker SHALL parse the cached_steps JSON string into a list of step dictionaries
2. WHEN cache is available, THE Worker SHALL call execute_cached_steps from the Cache_Executor module
3. WHEN cache is available, THE Worker SHALL pass the Nova_Act instance and parsed cached_steps to the executor
4. WHEN cache execution succeeds, THE Worker SHALL mark the step as successful
5. WHEN cache execution succeeds, THE Worker SHALL skip the Nova_Act call
6. THE Worker SHALL handle JSON parsing errors gracefully and fall back to Nova_Act

### Requirement 3: Cache Execution Fallback

**User Story:** As a test execution system, I want to automatically fall back to Nova Act when cache execution fails, so that tests remain reliable despite cache issues

#### Acceptance Criteria

1. IF cache execution raises a CacheExecutionError, THEN THE Worker SHALL catch the exception
2. IF cache execution raises a CacheExecutionError, THEN THE Worker SHALL log a warning with the error details
3. IF cache execution raises a CacheExecutionError, THEN THE Worker SHALL execute the step using Nova_Act
4. IF cache execution raises any other exception, THEN THE Worker SHALL catch the exception and fall back to Nova_Act
5. WHEN falling back to Nova_Act, THE Worker SHALL execute the step normally as if cache was not available
6. WHEN falling back to Nova_Act, THE Worker SHALL return the Nova_Act result to the caller

### Requirement 4: Cache Observability

**User Story:** As a developer, I want to see cache hit/miss metrics in logs, so that I can monitor cache effectiveness and debug issues

#### Acceptance Criteria

1. WHEN cache execution succeeds, THE Worker SHALL log an info message containing "Cache hit" and the step identifier
2. WHEN cache is unavailable, THE Worker SHALL log an info message containing "Cache miss" and the reason
3. WHEN cache execution fails, THE Worker SHALL log a warning message containing "Cache execution failed" and the error details
4. WHEN falling back to Nova_Act, THE Worker SHALL log an info message containing "Falling back to Nova Act"
5. THE Worker SHALL include the step sort number in all cache-related log messages
6. THE Worker SHALL include timing information showing cache execution duration

### Requirement 5: Result Compatibility

**User Story:** As a test execution system, I want cache execution results to be compatible with Nova Act results, so that downstream validation logic works correctly

#### Acceptance Criteria

1. WHEN cache execution succeeds, THE Worker SHALL return a result object with success=True
2. WHEN cache execution succeeds, THE Worker SHALL return a result object with logs=""
3. WHEN cache execution succeeds, THE Worker SHALL return a result object with a metadata attribute containing act_id="cached"
4. WHEN Nova_Act is called (cache miss or fallback), THE Worker SHALL return the actual Nova_Act result object
5. THE Worker SHALL ensure the return signature matches the existing execute_navigation_step function
6. THE Worker SHALL maintain backward compatibility with existing callers

### Requirement 6: Advanced Click Types Support

**User Story:** As a test execution system, I want cache execution to respect the enable_advanced_click_types flag, so that cached steps work correctly with advanced click features

#### Acceptance Criteria

1. WHEN enable_advanced_click_types is True on the Execution_Step, THE Worker SHALL include the click_base_prompt in the instruction
2. WHEN enable_advanced_click_types is True AND cache is used, THE Worker SHALL still execute cached steps normally
3. WHEN enable_advanced_click_types is True AND cache fails, THE Worker SHALL fall back to Nova_Act with the enhanced instruction
4. THE Worker SHALL maintain the existing advanced click types behavior for non-cached execution

### Requirement 7: Error Handling

**User Story:** As a test execution system, I want robust error handling for cache execution, so that unexpected failures don't break test execution

#### Acceptance Criteria

1. IF cached_steps JSON parsing fails, THEN THE Worker SHALL log the error and fall back to Nova_Act
2. IF Cache_Executor module is not available, THEN THE Worker SHALL log the error and fall back to Nova_Act
3. IF Nova_Act instance is invalid, THEN THE Worker SHALL raise an exception (existing behavior)
4. IF Execution_Step is invalid, THEN THE Worker SHALL raise an exception (existing behavior)
5. THE Worker SHALL never silently ignore errors without logging
6. THE Worker SHALL ensure all exceptions are properly caught and handled

### Requirement 8: Performance Requirements

**User Story:** As a test execution system, I want cache execution to be significantly faster than Nova Act, so that the cache provides measurable value

#### Acceptance Criteria

1. WHEN cache execution succeeds, THE Worker SHALL complete the step in less than 500ms
2. WHEN cache execution succeeds, THE Worker SHALL be at least 5x faster than Nova Act execution
3. THE Worker SHALL add minimal overhead (<10ms) for cache availability checks
4. THE Worker SHALL not introduce additional delays beyond the Cache_Executor's configured action delays
5. FOR ALL cached steps, the total execution time SHALL be less than 10% of the equivalent Nova Act execution time

### Requirement 9: Integration with Existing Flow

**User Story:** As a developer, I want cache execution to integrate seamlessly with the existing navigation_step.py flow, so that minimal code changes are required

#### Acceptance Criteria

1. THE Worker SHALL modify only the execute_navigation_step function in navigation_step.py
2. THE Worker SHALL maintain the existing function signature: execute_navigation_step(nova, step)
3. THE Worker SHALL maintain the existing return signature: (result, success, logs)
4. THE Worker SHALL not modify the ExecutionStep dataclass
5. THE Worker SHALL not modify the Nova_Act integration
6. THE Worker SHALL preserve all existing error handling behavior for non-cached execution
