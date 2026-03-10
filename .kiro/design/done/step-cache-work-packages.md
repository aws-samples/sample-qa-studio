# Step Cache Implementation - Work Packages

## Overview

This document breaks down the step cache implementation into logical, independent work packages that can be developed and tested separately.

---

## Package 1: Core Parser Module

**Goal**: Parse Nova Act responses into cacheable step format

**Deliverables**:
- `worker/cache_parser.py` with `parse_nova_act_steps()` function
- Regex patterns for all 5 cacheable actions (click, hover, scroll, type, navigate)
- Unit tests with 70%+ coverage

**Dependencies**: None

**Estimated Effort**: 1-2 days

**Files to Create**:
```
worker/cache_parser.py
worker/tests/test_cache_parser.py
```

**Acceptance Criteria**:
- [ ] Parses `agentClick` with bbox coordinates
- [ ] Parses `agentHover` with bbox coordinates
- [ ] Parses `agentScroll` with direction, bbox, and optional value
- [ ] Parses `agentType` with text, bbox, and press_enter flag
- [ ] Parses `goToUrl` with URL
- [ ] Skips `think`, `return`, `throw`, `wait*`, `takeObservation`
- [ ] Handles HTML entities (`&lt;`, `&gt;`)
- [ ] Returns list of structured dicts
- [ ] Unit tests cover all action types
- [ ] Unit tests cover edge cases (missing fields, malformed input)

**Example Test**:
```python
def test_parse_click_action():
    response = {
        'steps': [{
            'response': {
                'rawProgramBody': 'agentClick("<box>100,200,300,400</box>");'
            }
        }]
    }
    result = parse_nova_act_steps(response)
    assert result == [{
        'type': 'click',
        'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}
    }]
```

---

## Package 2: Core Executor Module

**Goal**: Execute cached steps using Playwright API

**Deliverables**:
- `worker/cache_executor.py` with `execute_cached_steps()` function
- Playwright API calls for all 5 action types
- Unit tests with mocked Playwright

**Dependencies**: None (can develop in parallel with Package 1)

**Estimated Effort**: 1-2 days

**Files to Create**:
```
worker/cache_executor.py
worker/tests/test_cache_executor.py
```

**Acceptance Criteria**:
- [ ] Executes `click` action via `nova.page.mouse.click(x, y)`
- [ ] Executes `hover` action via `nova.page.mouse.move(x, y)`
- [ ] Executes `type` action via `nova.page.keyboard.type()` + optional Enter
- [ ] Executes `scroll` action via `nova.page.evaluate()`
- [ ] Executes `navigate` action via `nova.page.goto()`
- [ ] Calculates center point from bbox coordinates
- [ ] Adds small delays between actions (100ms)
- [ ] Handles errors gracefully (raises exception for fallback)
- [ ] Unit tests mock Playwright API
- [ ] Unit tests verify correct API calls

**Example Test**:
```python
@mock.patch('nova.page.mouse.click')
def test_execute_click(mock_click):
    step = {'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}
    execute_cached_step(mock_nova, step)
    mock_click.assert_called_once_with(200, 300)  # Center point
```

---

## Package 3: DynamoDB Schema Updates

**Goal**: Add cache fields to STEP records

**Deliverables**:
- Updated `create_step.py` to accept optional cache fields
- Updated `update_step.py` to allow cache field updates
- Updated `list_steps.py` to return cache fields (camelCase)
- Updated `execute_usecase.py` to copy cache fields to EXECUTION_STEP

**Dependencies**: None

**Estimated Effort**: 1 day

**Files to Modify**:
```
lambdas/endpoints/create_step.py
lambdas/endpoints/update_step.py
lambdas/endpoints/list_steps.py
lambdas/endpoints/execute_usecase.py
```

**Acceptance Criteria**:
- [ ] STEP records can store `cached_steps` (string, JSON)
- [ ] STEP records can store `cache_last_updated` (string, ISO timestamp)
- [ ] Fields are optional (no migration needed)
- [ ] `list_steps` returns `cachedSteps` and `cacheLastUpdated` (camelCase)
- [ ] `execute_usecase` copies cache fields to EXECUTION_STEP
- [ ] Unit tests verify field handling
- [ ] No breaking changes to existing API

**Example**:
```python
# In create_step.py
step = {
    'pk': f'USECASE#{usecase_id}',
    'sk': f'STEP#{step_id}',
    'instruction': instruction,
    'step_type': step_type,
    'cached_steps': body.get('cachedSteps'),  # NEW - optional
    'cache_last_updated': body.get('cacheLastUpdated'),  # NEW - optional
    # ... existing fields
}
```

---

## Package 4: USECASE Metadata Updates

**Goal**: Add `enable_cache` flag to USECASE records

**Deliverables**:
- Updated `create_usecase.py` to accept `enableCache` field
- Updated `update_usecase.py` to allow `enableCache` updates
- Updated `get_usecase.py` to return `enableCache` field
- Frontend toggle in CreateUsecase and UsecaseSettings components

**Dependencies**: None

**Estimated Effort**: 1 day

**Files to Modify**:
```
lambdas/endpoints/create_usecase.py
lambdas/endpoints/update_usecase.py
lambdas/endpoints/get_usecase.py
frontend/src/components/CreateUsecase.tsx
frontend/src/components/UsecaseSettings.tsx (or UpdateUsecase.tsx)
```

**Acceptance Criteria**:
- [ ] USECASE records can store `enable_cache` (boolean, default False)
- [ ] `create_usecase` accepts `enableCache` in request body
- [ ] `update_usecase` accepts `enableCache` in request body
- [ ] `get_usecase` returns `enableCache` in response
- [ ] Frontend shows Cloudscape Toggle component
- [ ] Toggle appears in both create and update forms
- [ ] Default value is False (opt-in)
- [ ] Unit tests verify field handling
- [ ] E2E tests verify UI toggle works

**Example Frontend**:
```tsx
<FormField
  label="Step caching"
  description="Cache navigation steps to reduce execution time by 40-60%"
>
  <Toggle
    checked={enableCache}
    onChange={({ detail }) => setEnableCache(detail.checked)}
  >
    Enable caching
  </Toggle>
</FormField>
```

---

## Package 5: Cache Builder Lambda

**Goal**: Build cache from Nova Act responses after test execution

**Deliverables**:
- New Lambda: `lambdas/endpoints/build_step_cache.py`
- EventBridge rule configuration in CDK
- S3 file lookup logic (list by prefix, match by act_id)
- Integration with parser module (Package 1)

**Dependencies**: Package 1 (parser module)

**Estimated Effort**: 2-3 days

**Files to Create**:
```
lambdas/endpoints/build_step_cache.py
lambdas/endpoints/test_build_step_cache.py
```

**Files to Modify**:
```
cdk/lib/qa-studio-stack.ts (add EventBridge rule)
```

**Acceptance Criteria**:
- [ ] Lambda triggered by `usecase.execution.completed` event
- [ ] Only processes successful executions (`execution_status == 'success'`)
- [ ] Checks `enable_cache` flag on USECASE
- [ ] Lists S3 objects by prefix: `executions/{execution_id}/act_`
- [ ] Builds map: `{act_id: s3_key}`
- [ ] Queries EXECUTION_STEP records
- [ ] For each navigation step:
  - [ ] Fetches Nova Act response from S3
  - [ ] Parses cached steps using parser module
  - [ ] Updates STEP record with cache
- [ ] Uses DynamoDB batch_writer for efficiency
- [ ] Handles errors gracefully (logs, continues)
- [ ] Unit tests with mocked S3 and DynamoDB
- [ ] Integration tests with real AWS services

**Example**:
```python
def handler(event, context):
    detail = event['detail']
    
    if detail['execution_status'] != 'success':
        return
    
    usecase = get_usecase(detail['usecase_id'])
    if not usecase.get('enable_cache'):
        return
    
    act_files = get_act_files_for_execution(bucket, detail['execution_id'])
    execution_steps = query_execution_steps(detail['execution_id'])
    
    with table.batch_writer() as batch:
        for step in execution_steps:
            if step['step_type'] != 'navigation':
                continue
            
            s3_key = act_files.get(step['act_id'])
            if not s3_key:
                continue
            
            act_response = fetch_from_s3(bucket, s3_key)
            cached_steps = parse_nova_act_steps(act_response)
            
            batch.put_item(Item={
                'pk': f'USECASE#{usecase_id}',
                'sk': f'STEP#{step["step_id"]}',
                'cached_steps': json.dumps(cached_steps),
                'cache_last_updated': detail['timestamp']
            })
```

---

## Package 6: Worker Event Emission

**Goal**: Emit EventBridge event after test execution

**Deliverables**:
- Updated `worker/worker.py` to emit `usecase.execution.completed` event
- Event includes: usecase_id, execution_id, execution_status, timestamp

**Dependencies**: None

**Estimated Effort**: 0.5 days

**Files to Modify**:
```
worker/worker.py
```

**Acceptance Criteria**:
- [ ] Event emitted after test execution completes
- [ ] Event includes all required fields
- [ ] Event emitted for both success and failure
- [ ] Event uses correct source: `qa-studio.worker`
- [ ] Event uses correct detail-type: `usecase.execution.completed`
- [ ] No impact on test execution (fire-and-forget)
- [ ] Unit tests verify event emission

**Example**:
```python
def emit_execution_completed_event(usecase_id, execution_id, status):
    eventbridge = boto3.client('events')
    
    eventbridge.put_events(
        Entries=[{
            'Source': 'qa-studio.worker',
            'DetailType': 'usecase.execution.completed',
            'Detail': json.dumps({
                'usecase_id': usecase_id,
                'execution_id': execution_id,
                'execution_status': status,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })
        }]
    )

# Call after test completes
emit_execution_completed_event(usecase_id, execution_id, final_status)
```

---

## Package 7: Worker Cache Execution

**Goal**: Execute cached steps in worker instead of calling Nova Act

**Deliverables**:
- Updated `worker/navigation_step.py` to check for cached steps
- Integration with executor module (Package 2)
- Fallback to Nova Act on cache failure

**Dependencies**: Package 2 (executor module), Package 3 (DynamoDB schema)

**Estimated Effort**: 1-2 days

**Files to Modify**:
```
worker/navigation_step.py
```

**Acceptance Criteria**:
- [ ] Checks if `enable_cache == True` on usecase config
- [ ] Checks if `cached_steps` exists on step
- [ ] If both true, executes cached steps using executor module
- [ ] If cache execution succeeds, skips Nova Act call
- [ ] If cache execution fails, falls back to Nova Act
- [ ] Logs cache hit/miss for observability
- [ ] Unit tests with mocked executor
- [ ] Integration tests with real Nova Act

**Example**:
```python
def execute_navigation_step(nova, step, usecase_config):
    # Check cache
    if usecase_config.get('enable_cache') and step.get('cached_steps'):
        try:
            cached_steps = json.loads(step['cached_steps'])
            execute_cached_steps(nova, cached_steps)
            logger.info(f"Cache hit for step {step['step_id']}")
            return {'success': True, 'used_cache': True}
        except Exception as e:
            logger.warning(f"Cache execution failed: {e}, falling back to Nova Act")
    
    # Fallback to Nova Act
    result = nova.act(step['instruction'])
    return {'success': True, 'used_cache': False, 'result': result}
```

---

## Package 8: Frontend Cache Indicators

**Goal**: Show cache status in UI

**Deliverables**:
- Cache badge in StepsList component
- Cache usage indicator in ExecutionSteps component

**Dependencies**: Package 3 (DynamoDB schema)

**Estimated Effort**: 0.5 days

**Files to Modify**:
```
frontend/src/components/StepsList.tsx
frontend/src/components/ExecutionSteps.tsx
```

**Acceptance Criteria**:
- [ ] StepsList shows green "Cached" badge if `cachedSteps` exists
- [ ] Badge shows cache age (e.g., "Cached 2 days ago")
- [ ] ExecutionSteps shows if step used cache during execution
- [ ] UI updates when cache is built
- [ ] Responsive design (mobile-friendly)

**Example**:
```tsx
// StepsList.tsx
{step.cachedSteps && (
  <Badge color="green">
    <Icon name="check" /> Cached
  </Badge>
)}

// ExecutionSteps.tsx
<Box variant="small" color="text-body-secondary">
  {step.usedCache ? 'Executed from cache (200ms)' : 'Executed with Nova Act (3.2s)'}
</Box>
```

---

## Package 9: Integration Testing

**Goal**: End-to-end testing of cache system

**Deliverables**:
- Integration tests for cache building flow
- Integration tests for cache execution flow
- Performance benchmarks

**Dependencies**: All previous packages

**Estimated Effort**: 2-3 days

**Files to Create**:
```
worker/tests/integration/test_cache_flow.py
```

**Acceptance Criteria**:
- [ ] Test: Create usecase with `enable_cache=True`
- [ ] Test: Execute test (cache miss)
- [ ] Test: Verify cache built in STEP records
- [ ] Test: Execute again (cache hit)
- [ ] Test: Verify faster execution (>5x speedup)
- [ ] Test: Update instruction, verify cache invalidated
- [ ] Test: Disable cache, verify falls back to Nova Act
- [ ] Test: Cache execution failure, verify fallback works
- [ ] Performance benchmark: measure speedup
- [ ] Load test: verify cache handles high volume

**Example**:
```python
def test_cache_flow_end_to_end():
    # 1. Create usecase with cache enabled
    usecase = create_usecase(enable_cache=True)
    step = create_step(usecase_id, instruction="Click login button")
    
    # 2. Execute test (cache miss)
    start = time.time()
    execute_usecase(usecase_id)
    first_execution_time = time.time() - start
    
    # 3. Wait for cache to build
    time.sleep(5)
    
    # 4. Verify cache exists
    step = get_step(usecase_id, step_id)
    assert step['cached_steps'] is not None
    
    # 5. Execute again (cache hit)
    start = time.time()
    execute_usecase(usecase_id)
    second_execution_time = time.time() - start
    
    # 6. Verify speedup
    assert second_execution_time < first_execution_time / 5  # At least 5x faster
```

---

## Package 10: Documentation & Rollout

**Goal**: Document feature and plan rollout

**Deliverables**:
- Updated user guide with cache feature
- Updated API documentation
- Rollout plan and monitoring strategy

**Dependencies**: All previous packages

**Estimated Effort**: 1 day

**Files to Modify**:
```
docs/user-guide.md
docs/api-reference.md
docs/architecture.md
README.md
```

**Acceptance Criteria**:
- [ ] User guide explains cache feature
- [ ] User guide shows how to enable/disable cache
- [ ] API docs updated with new fields
- [ ] Architecture docs updated with cache flow
- [ ] README mentions cache feature
- [ ] Rollout plan documented
- [ ] Monitoring strategy documented
- [ ] Performance metrics defined

---

## Dependency Graph

```
Package 1 (Parser) ──────────────┐
                                 ├──> Package 5 (Cache Builder)
Package 3 (DynamoDB Schema) ─────┤
                                 │
Package 2 (Executor) ────────────┼──> Package 7 (Worker Execution)
                                 │
Package 4 (USECASE Metadata) ────┘

Package 6 (Event Emission) ──────────> Package 5 (Cache Builder)

Package 8 (Frontend) ────────────────> Package 3 (DynamoDB Schema)

All Packages ────────────────────────> Package 9 (Integration Tests)
                                     └> Package 10 (Documentation)
```

## Recommended Implementation Order

### Phase 1: Foundation (Parallel)
1. **Package 1** (Parser) - Can start immediately
2. **Package 2** (Executor) - Can start immediately
3. **Package 3** (DynamoDB Schema) - Can start immediately
4. **Package 4** (USECASE Metadata) - Can start immediately

### Phase 2: Integration (Sequential)
5. **Package 6** (Event Emission) - After Phase 1
6. **Package 5** (Cache Builder) - After Packages 1, 3, 6
7. **Package 7** (Worker Execution) - After Packages 2, 3

### Phase 3: Polish (Parallel)
8. **Package 8** (Frontend) - After Package 3
9. **Package 9** (Integration Tests) - After all core packages
10. **Package 10** (Documentation) - After all packages

## Estimated Total Effort

- **Phase 1**: 4-6 days (parallel development)
- **Phase 2**: 4-6 days (sequential development)
- **Phase 3**: 3-4 days (parallel development)

**Total**: 11-16 days (2-3 weeks)

## Risk Mitigation

**Risk**: Parser regex patterns don't match all Nova Act output formats
- **Mitigation**: Test with real Nova Act responses early
- **Fallback**: Add logging for unparsed actions, iterate on patterns

**Risk**: Cache execution fails due to page changes
- **Mitigation**: Implement robust error handling and fallback
- **Monitoring**: Track cache hit/miss rates

**Risk**: EventBridge event delivery delays
- **Mitigation**: Cache building is async, delays are acceptable
- **Monitoring**: Track event processing time

**Risk**: Performance gains less than expected
- **Mitigation**: Benchmark early, optimize if needed
- **Acceptance**: Even 2-3x speedup is valuable

## Success Metrics

- [ ] Cache hit rate > 70% after 1 week
- [ ] Average speedup > 5x for cached steps
- [ ] Cache execution failure rate < 5%
- [ ] No increase in test flakiness
- [ ] User adoption > 50% within 1 month
