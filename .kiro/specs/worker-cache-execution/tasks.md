# Implementation Plan: Worker Cache Execution

## Overview

This implementation integrates cached step execution into the worker's navigation_step.py module. The worker will check for cached steps before calling Nova Act, execute them using the cache_executor module, and automatically fall back to Nova Act on failures. This provides 40-60% execution speedup while maintaining test reliability.

## Tasks

- [ ] 1. Modify navigation_step.py to integrate cache execution
  - [x] 1.1 Add cache eligibility check logic
    - Add imports: json, time, SimpleNamespace, execute_cached_steps, CacheExecutionError
    - Check enable_cache flag using getattr(step, 'enable_cache', False)
    - Check cached_steps field using getattr(step, 'cached_steps', None)
    - Validate cached_steps is non-null and non-empty
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  
  - [x] 1.2 Implement cache execution path
    - Parse cached_steps JSON string to list using json.loads()
    - Call execute_cached_steps(nova, cached_steps)
    - Measure execution duration using time.time()
    - Create cache result object with metadata.act_id="cached"
    - Return cache result on success
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  
  - [x] 1.3 Implement cache failure handling
    - Catch CacheExecutionError and log warning with error details
    - Catch JSONDecodeError and log warning with parse error
    - Catch general Exception and log warning
    - Fall back to Nova Act execution on any exception
    - _Requirements: 2.6, 3.1, 3.2, 3.3, 3.4, 7.1, 7.6_
  
  - [x] 1.4 Add cache observability logging
    - Log INFO "Cache hit for step {sort} (executed in {duration_ms}ms)" on success
    - Log INFO "Cache miss for step {sort}: caching disabled" when enable_cache=False
    - Log INFO "Cache miss for step {sort}: no cached steps available" when cached_steps missing
    - Log WARNING with error details on cache execution failures
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  
  - [~] 1.5 Ensure fallback execution correctness
    - Preserve existing Nova Act instruction building logic
    - Maintain advanced click types integration (click_base_prompt)
    - Return Nova Act result unchanged on fallback
    - Ensure return signature remains (result, success, logs)
    - _Requirements: 3.5, 3.6, 5.4, 5.5, 6.1, 6.2, 6.3, 9.2, 9.3_

- [ ] 2. Write unit tests for cache execution
  - [~] 2.1 Write test for successful cache execution
    - Mock execute_cached_steps to return successfully
    - Verify cache result structure (metadata.act_id="cached", logs="")
    - Verify Nova Act not called on cache hit
    - Verify return signature is (result, True, "")
    - _Requirements: 2.4, 2.5, 5.1, 5.2, 5.3_
  
  - [~] 2.2 Write tests for cache miss scenarios
    - Test enable_cache=False triggers Nova Act
    - Test cached_steps=None triggers Nova Act
    - Test cached_steps="" triggers Nova Act
    - Verify correct log messages for each scenario
    - _Requirements: 1.4, 1.5, 4.2_
  
  - [~] 2.3 Write tests for cache failure scenarios
    - Test JSONDecodeError handling and fallback
    - Test CacheExecutionError handling and fallback
    - Test unexpected exception handling and fallback
    - Verify warning logs contain error details
    - _Requirements: 2.6, 3.1, 3.2, 3.3, 3.4, 7.1_
  
  - [~] 2.4 Write tests for logging verification
    - Test cache hit log contains "Cache hit", step sort, and duration
    - Test cache miss logs contain "Cache miss" and reason
    - Test cache failure logs contain "Cache execution failed" and error
    - Use caplog fixture to verify log messages
    - _Requirements: 4.1, 4.2, 4.3, 4.5_
  
  - [~] 2.5 Write test for advanced click types integration
    - Test cache execution with enable_advanced_click_types=True
    - Test fallback includes click_base_prompt in instruction
    - Verify cache execution ignores advanced click types flag
    - _Requirements: 6.1, 6.2, 6.3_
  
  - [~] 2.6 Write test for result compatibility
    - Verify cache result has metadata.act_id attribute
    - Verify cache result has logs attribute
    - Verify Nova Act result returned unchanged on fallback
    - Test return signature consistency across all paths
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [~] 3. Checkpoint - Ensure all unit tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ]* 4. Write property-based tests for universal properties
  - [ ]* 4.1 Write property test for cache eligibility decision
    - **Property 1: Cache Eligibility Decision**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**
    - Generate random enable_cache (bool) and cached_steps (None, "", "[]", valid JSON)
    - Verify cache attempted iff enable_cache=True AND cached_steps non-empty
    - Use hypothesis with 100 iterations
  
  - [ ]* 4.2 Write property test for cache execution integration
    - **Property 2: Cache Execution Integration**
    - **Validates: Requirements 2.1, 2.2, 2.3**
    - Generate random valid cached_steps JSON
    - Verify execute_cached_steps called with correct arguments
    - Mock execute_cached_steps to verify integration
  
  - [ ]* 4.3 Write property test for cache success result structure
    - **Property 3: Cache Success Result Structure**
    - **Validates: Requirements 2.4, 5.1, 5.2, 5.3, 5.5**
    - Generate random valid cached_steps
    - Verify result tuple is (result, True, "")
    - Verify result.metadata.act_id == "cached"
    - Verify result.logs == ""
  
  - [ ]* 4.4 Write property test for cache success skips Nova Act
    - **Property 4: Cache Success Skips Nova Act**
    - **Validates: Requirements 2.5**
    - Generate random valid cached_steps
    - Mock Nova Act and execute_cached_steps
    - Verify nova.act() not called when cache succeeds
  
  - [ ]* 4.5 Write property test for JSON parsing error handling
    - **Property 5: JSON Parsing Error Handling**
    - **Validates: Requirements 2.6, 7.1**
    - Generate random invalid JSON strings
    - Verify JSONDecodeError caught and logged
    - Verify fallback to Nova Act occurs
  
  - [ ]* 4.6 Write property test for CacheExecutionError handling
    - **Property 6: CacheExecutionError Handling**
    - **Validates: Requirements 3.1, 3.2, 3.3**
    - Mock execute_cached_steps to raise CacheExecutionError
    - Verify exception caught and warning logged with error details
    - Verify fallback to Nova Act occurs
  
  - [ ]* 4.7 Write property test for general exception handling
    - **Property 7: General Exception Handling**
    - **Validates: Requirements 3.4, 7.6**
    - Mock execute_cached_steps to raise random exceptions
    - Verify all exceptions caught and logged
    - Verify fallback to Nova Act occurs
  
  - [ ]* 4.8 Write property test for fallback execution correctness
    - **Property 8: Fallback Execution Correctness**
    - **Validates: Requirements 3.5, 3.6, 5.4**
    - Generate random cache failures
    - Verify Nova Act called with correct instruction
    - Verify Nova Act result returned unchanged
    - Verify advanced click types preserved in fallback
  
  - [ ]* 4.9 Write property test for cache hit logging
    - **Property 9: Cache Hit Logging**
    - **Validates: Requirements 4.1, 4.5, 4.6**
    - Generate random successful cache executions
    - Verify log contains "Cache hit", step sort, and duration
    - Use caplog fixture to verify log level is INFO
  
  - [ ]* 4.10 Write property test for cache miss logging
    - **Property 10: Cache Miss Logging**
    - **Validates: Requirements 4.2, 4.5**
    - Generate random cache miss scenarios (disabled or no data)
    - Verify log contains "Cache miss", step sort, and reason
    - Verify log level is INFO
  
  - [ ]* 4.11 Write property test for cache failure logging
    - **Property 11: Cache Failure Logging**
    - **Validates: Requirements 4.3, 4.5, 7.5**
    - Generate random cache execution failures
    - Verify log contains failure message, step sort, and error details
    - Verify log level is WARNING
  
  - [ ]* 4.12 Write property test for advanced click types integration
    - **Property 12: Advanced Click Types Integration**
    - **Validates: Requirements 6.1, 6.2, 6.3**
    - Generate random steps with enable_advanced_click_types=True
    - Verify cache execution works normally
    - Verify fallback includes click_base_prompt
  
  - [ ]* 4.13 Write property test for return signature consistency
    - **Property 13: Return Signature Consistency**
    - **Validates: Requirements 5.5**
    - Generate random execution paths (hit, miss, failure)
    - Verify return is always (result, bool, str)
    - Verify result always has metadata.act_id attribute

- [ ] 5. Update documentation
  - [~] 5.1 Update worker README with cache execution behavior
    - Document cache eligibility criteria
    - Document fallback behavior
    - Document cache result structure
    - Document environment variables (CACHE_ACTION_DELAY_MS)
    - _Requirements: All_
  
  - [~] 5.2 Add inline code comments for cache logic
    - Comment cache eligibility check logic
    - Comment cache execution path
    - Comment fallback handling
    - Comment result object creation
    - _Requirements: 9.1, 9.2, 9.3_

- [~] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use hypothesis library with 100 iterations minimum
- Target: 70% unit test coverage minimum
- Cache execution provides 40-60% speedup over Nova Act
- Automatic fallback ensures zero test reliability impact
