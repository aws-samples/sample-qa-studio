# Bounding Box Cache Implementation Plan

## Overview

Implement a caching system for Nova Act navigation steps to reduce test execution time by 40-60% by caching parsed actions from `nova.act()` calls and replaying them via direct Playwright interactions.

## Design Decisions

### 1. Cache Storage: STEP Record Extension

Store cache directly in STEP records (single-table design):

```python
{
  'pk': 'USECASE#{usecase_id}',
  'sk': 'STEP#{step_id}',
  'instruction': 'Click login button',
  'step_type': 'navigation',
  # ... existing fields ...
  'cached_steps': '[{"type":"click","bbox":{...}}]',  # NEW - JSON string
  'cache_last_updated': '2026-03-03T10:30:00Z'        # NEW - ISO timestamp
}
```

**Rationale**:
- Cache data belongs to the step (not a separate entity)
- Automatically copied to EXECUTION_STEP when execution is created
- Works for both cloud and local execution (CLI)
- Well within DynamoDB 400 KB item limit (~2-3 KB per cache)
- Aligns with single-table design principles

### 2. Cache Key Strategy: Instruction-Based

Cache key = instruction text (stored in STEP record)

**Benefits**:
- Stable across test runs
- Self-documenting
- Natural invalidation when instruction changes
- Simple implementation

**Validation**:
- Cache self-corrects on failure (falls back to Nova Act, updates cache)
- No success/fail counters needed (minimal approach)

### 3. Per-Usecase Toggle

Add `enable_cache` flag to USECASE metadata:

```python
{
  'pk': 'USECASE#{usecase_id}',
  'sk': 'METADATA',
  'title': '...',
  'enable_cache': True,  # NEW - default True (opt-out)
  # ... other fields ...
}
```

**Use cases**:
- Gradual rollout
- Disable for dynamic/flaky tests
- Debugging and A/B testing
- Cost control

### 4. Event-Driven Cache Building

Use EventBridge for decoupled, async cache building:

```
Worker completes test
    ↓
Emit: usecase.execution.completed
    ↓
EventBridge
    ↓
Cache Builder Lambda
    ↓
Update STEP records
```

**Event structure**:
```json
{
  "source": "qa-studio.worker",
  "detail-type": "usecase.execution.completed",
  "detail": {
    "usecase_id": "usecase-456",
    "execution_id": "exec-123",
    "execution_status": "success",
    "timestamp": "2026-03-03T10:55:00Z"
  }
}
```

**Benefits**:
- Lightweight event (~100 bytes)
- No execution slowdown
- Batch processing
- Retry logic via EventBridge
- Future extensibility (suite updates, analytics)

## Complete Agent Actions

From `browser.py` in Nova Act SDK:

### Actions to Cache (5 total)
1. `agentClick(box, click_type?, click_options?)` - Click center of bbox
2. `agentHover(box)` - Hover on center of bbox
3. `agentScroll(direction, box, value?)` - Scroll element (up/down/left/right)
4. `agentType(value, box, pressEnter?)` - Type text into element
5. `goToUrl(url)` - Navigate to URL

### Actions to Skip (6 total)
6. `think(value)` - Internal reasoning
7. `return(value?)` - End execution
8. `throw(value)` - Error
9. `wait(seconds)` - Pause
10. `waitForPageToSettle()` - Wait for page
11. `takeObservation()` - Snapshot

## Implementation Phases

### Phase 1: Cache Building (Event-Driven)

**1.1 Add fields to USECASE metadata**

Update DynamoDB schema:
```python
{
  'pk': 'USECASE#{usecase_id}',
  'sk': 'METADATA',
  'title': '...',
  'url': '...',
  'enable_cache': False,  # NEW - default False (opt-in)
  # ... existing fields
}
```

Update `create_usecase.py` endpoint:
```python
# Add to request body validation
enable_cache = body.get('enableCache', False)  # Default False

# Add to DynamoDB item
usecase_item = {
    'pk': f'USECASE#{usecase_id}',
    'sk': 'METADATA',
    'enable_cache': enable_cache,
    # ... existing fields
}
```

Update `update_usecase.py` endpoint:
```python
# Add to allowed update fields
if 'enableCache' in body:
    update_expression_parts.append('enable_cache = :enable_cache')
    expression_values[':enable_cache'] = body['enableCache']
```

Update `get_usecase.py` endpoint response:
```python
# Add to response (convert to camelCase)
return {
    'usecaseId': usecase['id'],
    'title': usecase['title'],
    'enableCache': usecase.get('enable_cache', False),  # NEW - default False
    # ... existing fields
}
```

Update frontend `CreateUsecase.tsx`:
```tsx
import { Toggle } from '@cloudscape-design/components';

// Add to form state
const [enableCache, setEnableCache] = useState(false);  // Default False

// Add toggle to form
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

// Add to API request
const response = await api.createUsecase({
  title,
  url,
  enableCache,  // NEW
  // ... existing fields
});
```

Update frontend `UsecaseSettings.tsx` (or `UpdateUsecase.tsx`):
```tsx
import { Toggle } from '@cloudscape-design/components';

// Add to form state (load from existing usecase)
const [enableCache, setEnableCache] = useState(usecase?.enableCache ?? false);

// Add toggle to settings form
<FormField
  label="Step caching"
  description="Cache navigation steps to speed up test execution by 40-60%"
>
  <Toggle
    checked={enableCache}
    onChange={({ detail }) => setEnableCache(detail.checked)}
  >
    Enable step caching
  </Toggle>
</FormField>

// Add to update API request
const response = await api.updateUsecase(usecaseId, {
  enableCache,  // NEW
  // ... existing fields
});
```

**1.2 Add fields to STEP records**
- Add `cached_steps` string field (JSON)
- Add `cache_last_updated` string field (ISO timestamp)
- No schema migration needed (optional fields)

**1.3 Create Cache Builder Lambda**

Create `lambdas/endpoints/build_step_cache.py`:
```python
"""
Lambda function to build step cache from Nova Act responses.
Triggered by EventBridge: usecase.execution.completed
"""
import json
import boto3
import re
from boto3.dynamodb.conditions import Key

def get_act_files_for_execution(bucket: str, execution_id: str) -> dict[str, str]:
    """
    List all Nova Act trace files for an execution.
    Returns: {act_id: s3_key}
    """
    s3 = boto3.client('s3')
    
    response = s3.list_objects_v2(
        Bucket=bucket,
        Prefix=f"executions/{execution_id}/act_"
    )
    
    act_files = {}
    for obj in response.get('Contents', []):
        key = obj['Key']
        # Extract act_id from: act_{act_id}_*.json
        match = re.search(r'act_([^_]+)_.*\.json$', key)
        if match:
            act_files[match.group(1)] = key
    
    return act_files

def handler(event, context):
    detail = event['detail']
    usecase_id = detail['usecase_id']
    execution_id = detail['execution_id']
    execution_status = detail['execution_status']
    
    # Only process successful executions
    if execution_status != 'success':
        return
    
    # Check if cache enabled
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(os.environ['TABLE_NAME'])
    
    usecase = table.get_item(
        Key={'pk': f'USECASE#{usecase_id}', 'sk': 'METADATA'}
    )
    
    if not usecase.get('Item', {}).get('enable_cache', False):
        return
    
    # Get all act files
    bucket = os.environ['BUCKET_NAME']
    act_files = get_act_files_for_execution(bucket, execution_id)
    
    # Query execution steps
    execution_steps = table.query(
        KeyConditionExpression=Key('pk').eq(f'EXECUTION#{execution_id}') & 
                              Key('sk').begins_with('EXECUTION_STEP#')
    )
    
    # Process each navigation step
    s3 = boto3.client('s3')
    with table.batch_writer() as batch:
        for step in execution_steps['Items']:
            if step.get('step_type') != 'navigation':
                continue
            
            act_id = step.get('act_id')
            s3_key = act_files.get(act_id)
            
            if not s3_key:
                continue
            
            try:
                # Fetch Nova Act response
                response = s3.get_object(Bucket=bucket, Key=s3_key)
                act_response = json.loads(response['Body'].read())
                
                # Parse cached steps
                cached_steps = parse_nova_act_steps(act_response)
                
                # Update STEP record
                batch.put_item(Item={
                    'pk': f'USECASE#{usecase_id}',
                    'sk': f'STEP#{step["step_id"]}',
                    'cached_steps': json.dumps(cached_steps),
                    'cache_last_updated': detail['timestamp']
                })
            except Exception as e:
                print(f"Failed to cache step {step['step_id']}: {e}")
                continue
```

Add EventBridge rule in CDK:
```typescript
// In cdk/lib/qa-studio-stack.ts
const cacheBuilderRule = new events.Rule(this, 'CacheBuilderRule', {
  eventPattern: {
    source: ['qa-studio.worker'],
    detailType: ['usecase.execution.completed']
  }
});

cacheBuilderRule.addTarget(new targets.LambdaFunction(cacheBuilderLambda));
```

**1.4 Update Worker to emit event**
- After test completion, emit `usecase.execution.completed` event
- Include: usecase_id, execution_id, execution_status, timestamp
- Always emit (no conditional logic)

**1.5 Create parser module**
- `parse_nova_act_steps(response: dict) -> list[dict]`
- Regex patterns for all 5 cacheable actions
- Handle HTML entities (`&lt;`, `&gt;`)
- Unit tests for all action types

### Phase 2: Cache Execution

**2.1 Update execute_usecase endpoint**
- Copy `cached_steps` and `cache_last_updated` to EXECUTION_STEP
- Include in existing step copy logic

**2.2 Update Worker execution logic**
- Check if `cached_steps` exists and `enable_cache == True`
- If yes: execute_cached_steps()
- If fails or no cache: fall back to nova.act()
- If nova.act() succeeds: emit event to rebuild cache

**2.3 Create cache executor module**
- `execute_cached_steps(nova: NovaAct, cached_steps: list[dict])`
- Use Playwright API directly:
  - `agentClick` → `nova.page.mouse.click(x, y)`
  - `agentHover` → `nova.page.mouse.move(x, y)`
  - `agentType` → `nova.page.keyboard.type(text)` + optional Enter
  - `agentScroll` → `nova.page.evaluate("window.scrollBy(...)")`
  - `goToUrl` → `nova.page.goto(url)`
- Calculate center point from bbox: `(x1+x2)/2, (y1+y2)/2`
- Add small delays between actions (100-200ms)

**2.4 Update list_steps endpoint**

Update `list_steps.py` to return cache data:
```python
def handler(event, context):
    # ... existing code to fetch steps ...
    
    # Add cache data to response
    for step in steps:
        # Convert snake_case to camelCase for API
        step_response = {
            'stepId': step['id'],
            'instruction': step['instruction'],
            'stepType': step['step_type'],
            'cachedSteps': json.loads(step['cached_steps']) if step.get('cached_steps') else None,  # NEW
            'cacheLastUpdated': step.get('cache_last_updated'),  # NEW
            # ... existing fields
        }
    
    return create_response(200, {'steps': steps_response})
```

Update frontend `StepsList.tsx` to show cache status:
```tsx
// Add cache indicator to step row
<Box variant="span">
  {step.instruction}
  {step.cachedSteps && (
    <Badge color="green">
      <Icon name="check" /> Cached
    </Badge>
  )}
</Box>
```

Update frontend `ExecutionSteps.tsx` to show cache usage:
```tsx
// Show if step used cache during execution
<Box variant="small" color="text-body-secondary">
  {step.usedCache ? 'Executed from cache' : 'Executed with Nova Act'}
</Box>
```

### Phase 3: Testing & Validation

**3.1 Unit tests**
- Parser: test all 5 action types
- Executor: test all 5 action types (mock Playwright)
- Cache Builder Lambda: test event handling
- Target: 70% coverage

**3.2 Integration tests**
- Create test usecase with navigation steps
- Execute test (cache miss)
- Verify cache built in STEP records
- Execute again (cache hit)
- Verify faster execution
- Disable cache, verify falls back to Nova Act

**3.3 E2E tests with qa-studio**
- Test cache building flow
- Test cache execution flow
- Test cache invalidation (update instruction)
- Test enable_cache toggle

## Data Structures

### Cached Step Format

```python
[
  {
    "type": "click",
    "bbox": {"x1": 621, "y1": 71, "x2": 640, "y2": 143}
  },
  {
    "type": "hover",
    "bbox": {"x1": 100, "y1": 200, "x2": 150, "y2": 250}
  },
  {
    "type": "type",
    "text": "admin",
    "bbox": {"x1": 300, "y1": 400, "x2": 500, "y2": 450},
    "press_enter": False
  },
  {
    "type": "scroll",
    "direction": "down",
    "bbox": {"x1": 0, "y1": 0, "x2": 1920, "y2": 1080},
    "value": None
  },
  {
    "type": "navigate",
    "url": "https://example.com/login"
  }
]
```

### Nova Act Response Format

```json
{
  "steps": [
    {
      "response": {
        "rawProgramBody": "think(\"...\");\nagentClick(\"<box>621,71,640,143</box>\");\n"
      }
    },
    {
      "response": {
        "rawProgramBody": "think(\"...\");\nreturn();\n"
      }
    }
  ],
  "metadata": {
    "num_steps_executed": 2
  }
}
```

## Performance Impact

**Expected speedup per cached instruction**:
- Nova Act: 2-5 seconds per call
- Cached execution: 100-300ms per step
- **Total speedup**: 10-20x for single-step actions, 20-50x for multi-step actions

**Example**:
- Instruction: "Close any popups"
- Nova Act: 2 steps × 3 seconds = 6 seconds
- Cached: 2 steps × 200ms = 400ms
- **Speedup**: 15x faster

**Target**: 40-60% reduction in total test execution time

## API Changes

### GET /usecases/{usecase_id}
**Response changes** (add):
```json
{
  "enableCache": true
}
```

### GET /steps/{usecase_id}
**Response changes** (add):
```json
{
  "steps": [
    {
      "stepId": "...",
      "instruction": "...",
      "cachedSteps": [...],  // NEW - null if no cache
      "cacheLastUpdated": "..."  // NEW - null if no cache
    }
  ]
}
```

### POST /usecases
**Request changes** (add optional):
```json
{
  "enableCache": true
}
```

### PATCH /usecases/{usecase_id}
**Request changes** (add optional):
```json
{
  "enableCache": false
}
```

## Infrastructure Changes

### EventBridge
- Create event bus (or use default)
- Add rule: `detail-type = "usecase.execution.completed"`
- Target: Cache Builder Lambda

### Lambda
- New: `cache_builder.py`
- Permissions: DynamoDB read/write, S3 read, EventBridge consume

### DynamoDB
- No new tables (single-table design)
- No new GSIs
- Just add optional fields to existing records

## Rollout Plan

1. **Phase 1**: Deploy cache building (no execution changes)
   - Monitor cache creation
   - Verify data quality
   - No user impact

2. **Phase 2**: Enable cache execution for opt-in usecases
   - Add UI toggle
   - Users can enable per usecase
   - Monitor performance gains

3. **Phase 3**: Default to enabled for all new usecases
   - Existing usecases stay as-is
   - New usecases get cache by default

## Monitoring & Observability

**Metrics to track**:
- Cache hit rate per usecase
- Cache execution time vs Nova Act time
- Cache build success rate
- Cache invalidation frequency

**Logs to add**:
- Cache hit/miss per step
- Cache execution failures
- Cache build events
- Parser errors

## Future Enhancements

**Not in this PR**:
- Cache success/fail counters (add if needed)
- Cache TTL (cache lives with step for now)
- Cache compression (not needed, size is small)
- Selector extraction (bbox is sufficient)
- Cross-usecase cache sharing (instruction-based only for now)

## References

- Nova Act SDK: https://github.com/aws/nova-act
- Browser interface: https://github.com/aws/nova-act/blob/main/src/nova_act/tools/browser/interface/browser.py
- Example response: `~/Downloads/act_019c9f2a-d303-7dc3-9fd1-c4793981fe63_Close_any_popups_on_the_page_calls.json`
