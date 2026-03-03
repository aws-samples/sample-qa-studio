# Step Cache Design - Complete Specification

## Overview

Implement a caching system for Nova Act navigation steps to reduce test execution time by 40-60% by caching parsed actions from `nova.act()` calls and replaying them via direct Playwright interactions.

**Key Insight**: Nova Act exposes a Playwright `Page` object via `nova.page`, allowing us to replay cached actions using Playwright's API directly without calling Nova Act.

## Table of Contents

1. [Critical Findings](#critical-findings)
2. [Design Decisions](#design-decisions)
3. [Nova Act Actions Reference](#nova-act-actions-reference)
4. [Implementation Plan](#implementation-plan)
5. [S3 File Lookup Strategy](#s3-file-lookup-strategy)
6. [Cache Execution Strategy](#cache-execution-strategy)
7. [Data Structures](#data-structures)
8. [API Changes](#api-changes)
9. [Testing Strategy](#testing-strategy)

---

## Critical Findings

### 1. Nova Act Returns Multiple Steps Per Call

**CRITICAL**: Each `nova.act()` call can return **multiple steps**, not just one action.

Example from actual response (`~/Downloads/act_019c9f2a-d303-7dc3-9fd1-c4793981fe63_Close_any_popups_on_the_page_calls.json`):
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

**Implication**: We must cache **all steps as a sequence**, not just one action.

### 2. Nova Act Uses Bounding Boxes

Nova Act actions use **bounding box coordinates**, not CSS selectors:

```python
agentClick("<box>621,71,640,143</box>")  # x1, y1, x2, y2
agentType("admin", "<box>300,400,500,450</box>")
agentScroll("down", "<box>0,0,1920,1080</box>")
```

**Bounding box format**: `<box>x1,y1,x2,y2</box>` where:
- `x1, y1` = top-left corner coordinates
- `x2, y2` = bottom-right corner coordinates

**Implication**: 
- Cache bbox coordinates (what Nova Act actually uses)
- Selector extraction is optional enhancement
- Bbox coordinates are the source of truth

### 3. Only Cache Navigation Actions

- `nova.act()` - Navigation actions (clicks, scrolls, typing) → **CACHE THIS**
- `nova.act_get()` - Data extraction → **DO NOT CACHE** (data may be stale)

### 4. Playwright API Access

From Nova Act docs:
> `NovaAct` exposes a Playwright `Page` object directly under the `page` attribute.

**Implication**: Execute cached actions using Playwright's API:
- `nova.page.mouse.click(x, y)` - Click at coordinates
- `nova.page.mouse.move(x, y)` - Hover at coordinates
- `nova.page.keyboard.type(text)` - Type text
- `nova.page.keyboard.press("Enter")` - Press Enter
- `nova.page.evaluate("window.scrollBy(...)")` - Scroll
- `nova.page.goto(url)` - Navigate to URL

---

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

**Size calculation**:
- 30 steps × 60 bytes = 1.8 KB
- Plus metadata = ~2.4 KB total
- **0.6% of 400 KB DynamoDB limit** ✅

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
  'enable_cache': False,  # NEW - default False (opt-in)
  # ... other fields ...
}
```

**Use cases**:
- Gradual rollout
- Disable for dynamic/flaky tests
- Debugging and A/B testing
- Cost control

**Default**: False (opt-in for safety during initial rollout)

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

---

## Nova Act Actions Reference

Complete list from `browser.py` in Nova Act SDK.

**Source**: https://github.com/aws/nova-act/blob/main/src/nova_act/tools/browser/interface/browser.py

### Actions to Cache (5 total)

These actions modify the browser state and should be cached:

#### 1. agentClick
```python
agentClick(box: str, click_type?: ClickType, click_options?: ClickOptions)
```
Clicks the center of the specified box.

**Example in rawProgramBody**:
```javascript
agentClick("<box>621,71,640,143</box>");
```

**Cached format**:
```python
{
    "type": "click",
    "bbox": {"x1": 621, "y1": 71, "x2": 640, "y2": 143}
}
```

**Execution**:
```python
x = (bbox['x1'] + bbox['x2']) / 2
y = (bbox['y1'] + bbox['y2']) / 2
nova.page.mouse.click(x, y)
```

#### 2. agentHover
```python
agentHover(box: str)
```
Hovers on the center of the specified box.

**Example in rawProgramBody**:
```javascript
agentHover("<box>100,200,150,250</box>");
```

**Cached format**:
```python
{
    "type": "hover",
    "bbox": {"x1": 100, "y1": 200, "x2": 150, "y2": 250}
}
```

**Execution**:
```python
x = (bbox['x1'] + bbox['x2']) / 2
y = (bbox['y1'] + bbox['y2']) / 2
nova.page.mouse.move(x, y)
```

#### 3. agentScroll
```python
agentScroll(direction: ScrollDirection, box: str, value?: float)
```
Scrolls the element in the specified box. Valid directions: up, down, left, right.

**Example in rawProgramBody**:
```javascript
agentScroll("down", "<box>0,0,1920,1080</box>");
agentScroll("up", "<box>100,100,500,500</box>", 200.0);
```

**Cached format**:
```python
{
    "type": "scroll",
    "direction": "down",
    "bbox": {"x1": 0, "y1": 0, "x2": 1920, "y2": 1080},
    "value": None  # or float
}
```

**Execution**:
```python
amount = cached_step.get('value', 800)  # Default viewport height
if direction == 'down':
    nova.page.evaluate(f"window.scrollBy(0, {amount})")
elif direction == 'up':
    nova.page.evaluate(f"window.scrollBy(0, -{amount})")
```

#### 4. agentType
```python
agentType(value: str, box: str, pressEnter: bool = False)
```
Types the specified value into the element at the center of the box.

**Example in rawProgramBody**:
```javascript
agentType("admin", "<box>300,400,500,450</box>");
agentType("search query", "<box>100,100,400,150</box>", true);
```

**Cached format**:
```python
{
    "type": "type",
    "text": "admin",
    "bbox": {"x1": 300, "y1": 400, "x2": 500, "y2": 450},
    "press_enter": False
}
```

**Execution**:
```python
# Click at bbox first to focus element
x = (bbox['x1'] + bbox['x2']) / 2
y = (bbox['y1'] + bbox['y2']) / 2
nova.page.mouse.click(x, y)

# Type text
nova.page.keyboard.type(cached_step['text'])

# Press Enter if needed
if cached_step.get('press_enter'):
    nova.page.keyboard.press("Enter")
```

#### 5. goToUrl
```python
goToUrl(url: str)
```
Navigates to the specified URL.

**Example in rawProgramBody**:
```javascript
goToUrl("https://example.com/login");
```

**Cached format**:
```python
{
    "type": "navigate",
    "url": "https://example.com/login"
}
```

**Execution**:
```python
nova.page.goto(cached_step['url'])
```

### Actions NOT to Cache (6 total)

These actions don't modify browser state or shouldn't be cached:

6. **think(value)** - Internal reasoning, no effect on environment
7. **return(value?)** - End execution marker
8. **throw(value)** - Task not possible error
9. **wait(seconds)** - Pause execution (timing-dependent)
10. **waitForPageToSettle()** - Wait for page ready (Playwright handles this)
11. **takeObservation()** - Take browser state snapshot (observation, not action)

**Skip these during parsing** - they don't affect browser state or are handled automatically.

---
## Implementation Plan

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
import os
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

def parse_nova_act_steps(act_response: dict) -> list[dict]:
    """Parse Nova Act response into cacheable steps"""
    cached_steps = []
    
    for step in act_response.get('steps', []):
        raw_body = step['response']['rawProgramBody']
        
        # Parse click: agentClick("<box>x1,y1,x2,y2</box>")
        click_match = re.search(r'agentClick\("&lt;box&gt;(\d+),(\d+),(\d+),(\d+)&lt;/box&gt;"\)', raw_body)
        if click_match:
            cached_steps.append({
                "type": "click",
                "bbox": {
                    "x1": int(click_match.group(1)),
                    "y1": int(click_match.group(2)),
                    "x2": int(click_match.group(3)),
                    "y2": int(click_match.group(4))
                }
            })
            continue
        
        # Parse hover: agentHover("<box>x1,y1,x2,y2</box>")
        hover_match = re.search(r'agentHover\("&lt;box&gt;(\d+),(\d+),(\d+),(\d+)&lt;/box&gt;"\)', raw_body)
        if hover_match:
            cached_steps.append({
                "type": "hover",
                "bbox": {
                    "x1": int(hover_match.group(1)),
                    "y1": int(hover_match.group(2)),
                    "x2": int(hover_match.group(3)),
                    "y2": int(hover_match.group(4))
                }
            })
            continue
        
        # Parse type: agentType("text", "<box>x1,y1,x2,y2</box>", pressEnter?)
        type_match = re.search(
            r'agentType\("([^"]+)",\s*"&lt;box&gt;(\d+),(\d+),(\d+),(\d+)&lt;/box&gt;"(?:,\s*(true|false))?\)',
            raw_body
        )
        if type_match:
            cached_steps.append({
                "type": "type",
                "text": type_match.group(1),
                "bbox": {
                    "x1": int(type_match.group(2)),
                    "y1": int(type_match.group(3)),
                    "x2": int(type_match.group(4)),
                    "y2": int(type_match.group(5))
                },
                "press_enter": type_match.group(6) == "true" if type_match.group(6) else False
            })
            continue
        
        # Parse scroll: agentScroll("direction", "<box>x1,y1,x2,y2</box>", value?)
        scroll_match = re.search(
            r'agentScroll\("(up|down|left|right)",\s*"&lt;box&gt;(\d+),(\d+),(\d+),(\d+)&lt;/box&gt;"(?:,\s*(\d+(?:\.\d+)?))?\)',
            raw_body
        )
        if scroll_match:
            cached_steps.append({
                "type": "scroll",
                "direction": scroll_match.group(1),
                "bbox": {
                    "x1": int(scroll_match.group(2)),
                    "y1": int(scroll_match.group(3)),
                    "x2": int(scroll_match.group(4)),
                    "y2": int(scroll_match.group(5))
                },
                "value": float(scroll_match.group(6)) if scroll_match.group(6) else None
            })
            continue
        
        # Parse goToUrl: goToUrl("https://...")
        url_match = re.search(r'goToUrl\("([^"]+)"\)', raw_body)
        if url_match:
            cached_steps.append({
                "type": "navigate",
                "url": url_match.group(1)
            })
            continue
    
    return cached_steps

def handler(event, context):
    detail = event['detail']
    usecase_id = detail['usecase_id']
    execution_id = detail['execution_id']
    execution_status = detail['execution_status']
    
    # Only process successful executions
    if execution_status != 'success':
        print(f"Skipping cache build for non-successful execution: {execution_status}")
        return
    
    # Check if cache enabled
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(os.environ['TABLE_NAME'])
    
    usecase = table.get_item(
        Key={'pk': f'USECASE#{usecase_id}', 'sk': 'METADATA'}
    )
    
    if not usecase.get('Item', {}).get('enable_cache', False):
        print(f"Cache disabled for usecase {usecase_id}")
        return
    
    # Get all act files
    bucket = os.environ['BUCKET_NAME']
    act_files = get_act_files_for_execution(bucket, execution_id)
    print(f"Found {len(act_files)} act files for execution {execution_id}")
    
    # Query execution steps
    execution_steps = table.query(
        KeyConditionExpression=Key('pk').eq(f'EXECUTION#{execution_id}') & 
                              Key('sk').begins_with('EXECUTION_STEP#')
    )
    
    # Process each navigation step
    s3 = boto3.client('s3')
    cached_count = 0
    
    with table.batch_writer() as batch:
        for step in execution_steps['Items']:
            if step.get('step_type') != 'navigation':
                continue
            
            act_id = step.get('act_id')
            if not act_id:
                continue
                
            s3_key = act_files.get(act_id)
            if not s3_key:
                print(f"No S3 file found for act_id {act_id}")
                continue
            
            try:
                # Fetch Nova Act response
                response = s3.get_object(Bucket=bucket, Key=s3_key)
                act_response = json.loads(response['Body'].read())
                
                # Parse cached steps
                cached_steps = parse_nova_act_steps(act_response)
                
                if not cached_steps:
                    print(f"No cacheable steps found for step {step.get('step_id')}")
                    continue
                
                # Update STEP record
                batch.put_item(Item={
                    'pk': f'USECASE#{usecase_id}',
                    'sk': f'STEP#{step.get("step_id")}',
                    'cached_steps': json.dumps(cached_steps),
                    'cache_last_updated': detail['timestamp']
                })
                
                cached_count += 1
                print(f"Cached {len(cached_steps)} steps for step {step.get('step_id')}")
                
            except Exception as e:
                print(f"Failed to cache step {step.get('step_id')}: {e}")
                continue
    
    print(f"Successfully cached {cached_count} steps for usecase {usecase_id}")
    return {'cached_count': cached_count}
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

In `worker/worker.py` after test completion:
```python
import boto3

def emit_execution_completed_event(usecase_id: str, execution_id: str, status: str):
    """Emit EventBridge event after test completion"""
    eventbridge = boto3.client('events')
    
    eventbridge.put_events(
        Entries=[{
            'Source': 'qa-studio.worker',
            'DetailType': 'usecase.execution.completed',
            'Detail': json.dumps({
                'usecase_id': usecase_id,
                'execution_id': execution_id,
                'execution_status': status,  # 'success' or 'failed'
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })
        }]
    )

# Call after test completes
emit_execution_completed_event(usecase_id, execution_id, final_status)
```

**1.5 Create parser module**
- Already included in Cache Builder Lambda above
- `parse_nova_act_steps(response: dict) -> list[dict]`
- Regex patterns for all 5 cacheable actions
- Handle HTML entities (`&lt;`, `&gt;`)
- Unit tests for all action types

### Phase 2: Cache Execution

**2.1 Update execute_usecase endpoint**

In `lambdas/endpoints/execute_usecase.py`:
```python
# When copying steps to execution_steps, include cache fields
for field in ['cached_steps', 'cache_last_updated']:
    if field in step:
        execution_step[field] = step[field]
```

**2.2 Update Worker execution logic**

In `worker/navigation_step.py`:
```python
def execute_navigation_step(nova: NovaAct, step: dict, usecase_config: dict):
    """Execute navigation step with optional caching"""
    
    # Check if cache enabled and available
    if usecase_config.get('enable_cache') and step.get('cached_steps'):
        try:
            cached_steps = json.loads(step['cached_steps'])
            execute_cached_steps(nova, cached_steps)
            return {'success': True, 'used_cache': True}
        except Exception as e:
            logger.warning(f"Cache execution failed: {e}, falling back to Nova Act")
    
    # Fall back to Nova Act
    result = nova.act(step['instruction'])
    return {'success': True, 'used_cache': False, 'result': result}
```

**2.3 Create cache executor module**

Create `worker/cache_executor.py`:
```python
"""Execute cached Nova Act steps using Playwright API"""
import time
from typing import List, Dict

def execute_cached_steps(nova, cached_steps: List[Dict]):
    """Execute all cached steps in sequence"""
    for step in cached_steps:
        execute_cached_step(nova, step)
        time.sleep(0.1)  # Small delay between actions

def execute_cached_step(nova, step: Dict):
    """Execute a single cached step"""
    action_type = step['type']
    
    if action_type == 'click':
        bbox = step['bbox']
        x = (bbox['x1'] + bbox['x2']) / 2
        y = (bbox['y1'] + bbox['y2']) / 2
        nova.page.mouse.click(x, y)
        
    elif action_type == 'hover':
        bbox = step['bbox']
        x = (bbox['x1'] + bbox['x2']) / 2
        y = (bbox['y1'] + bbox['y2']) / 2
        nova.page.mouse.move(x, y)
        
    elif action_type == 'type':
        # Click at bbox first to focus element
        bbox = step['bbox']
        x = (bbox['x1'] + bbox['x2']) / 2
        y = (bbox['y1'] + bbox['y2']) / 2
        nova.page.mouse.click(x, y)
        
        # Type text
        nova.page.keyboard.type(step['text'])
        
        # Press Enter if needed
        if step.get('press_enter'):
            nova.page.keyboard.press("Enter")
        
    elif action_type == 'scroll':
        direction = step['direction']
        amount = step.get('value', 800)  # Default viewport height
        
        if direction == 'down':
            nova.page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == 'up':
            nova.page.evaluate(f"window.scrollBy(0, -{amount})")
        elif direction == 'left':
            nova.page.evaluate(f"window.scrollBy(-{amount}, 0)")
        elif direction == 'right':
            nova.page.evaluate(f"window.scrollBy({amount}, 0)")
        
    elif action_type == 'navigate':
        nova.page.goto(step['url'])
```

**2.4 Update list_steps endpoint**

Update `list_steps.py` to return cache data:
```python
def handler(event, context):
    # ... existing code to fetch steps ...
    
    # Add cache data to response
    steps_response = []
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
        steps_response.append(step_response)
    
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

---
## S3 File Lookup Strategy

### Current Architecture

**Worker stores `act_id` in EXECUTION_STEP**:
```python
# worker/dynamodb_client.py:248-277
def update_execution_step_status(execution_id, step_id, act_id, status, logs, actual_value):
    table.update_item(
        Key={'pk': f'EXECUTION#{execution_id}', 'sk': f'EXECUTION_STEP#{step_id}'},
        UpdateExpression="SET act_id = :act_id, #status = :status, ...",
        ExpressionAttributeValues={':act_id': act_id, ...}
    )
```

**Nova Act saves recordings to S3**:
```python
# worker/browser.py:70
browser_config = {
    'recording': {
        'enabled': True,
        's3Location': {
            'bucket': artefact_bucket,
            'prefix': artefact_prefix  # e.g., "executions/{execution_id}/"
        }
    }
}
```

### S3 File Structure

Nova Act automatically saves action traces to:
```
s3://{bucket}/{artefact_prefix}/act_{act_id}_{instruction}_calls.json
```

Example:
```
s3://qa-studio-artifacts/executions/exec-123/act_019c9f2a-d303-7dc3-9fd1-c4793981fe63_Close_any_popups_on_the_page_calls.json
```

**Note**: The instruction part may be truncated, so we cannot rely on exact filename matching.

### Recommended Approach: List S3 Objects

Use prefix listing and match by `act_id` only:

```python
def get_act_files_for_execution(bucket: str, execution_id: str) -> dict[str, str]:
    """
    List all Nova Act trace files for an execution.
    Returns: {act_id: s3_key}
    """
    s3 = boto3.client('s3')
    
    # List all act_*.json files for this execution
    response = s3.list_objects_v2(
        Bucket=bucket,
        Prefix=f"executions/{execution_id}/act_"
    )
    
    # Build map: act_id -> s3_key
    act_files = {}
    for obj in response.get('Contents', []):
        key = obj['Key']
        # Extract act_id from filename: act_{act_id}_*.json
        match = re.search(r'act_([^_]+)_.*\.json$', key)
        if match:
            act_files[match.group(1)] = key
    
    return act_files

# Then lookup by act_id
for step in execution_steps:
    act_id = step.get('act_id')
    s3_key = act_files.get(act_id)
    if not s3_key:
        continue
    # Fetch and parse...
```

**Benefits**:
- No dependency on instruction sanitization
- Handles truncated instructions
- Simple and reliable

---

## Cache Execution Strategy

### Execution Flow

```python
def execute_navigation_step(nova: NovaAct, step: dict, usecase_config: dict):
    """Execute navigation step with optional caching"""
    
    # 1. Check if cache enabled and available
    if usecase_config.get('enable_cache') and step.get('cached_steps'):
        try:
            # 2. Parse cached steps
            cached_steps = json.loads(step['cached_steps'])
            
            # 3. Execute all cached steps in sequence
            execute_cached_steps(nova, cached_steps)
            
            # 4. Success - return early
            return {'success': True, 'used_cache': True}
            
        except Exception as e:
            # 5. Cache failed - log and fall through to Nova Act
            logger.warning(f"Cache execution failed: {e}, falling back to Nova Act")
    
    # 6. Fall back to Nova Act (cache miss or failure)
    result = nova.act(step['instruction'])
    return {'success': True, 'used_cache': False, 'result': result}
```

### Execution Methods by Action Type

```python
def execute_cached_step(nova, step: Dict):
    """Execute a single cached step using Playwright API"""
    action_type = step['type']
    
    if action_type == 'click':
        # Calculate center of bounding box
        bbox = step['bbox']
        x = (bbox['x1'] + bbox['x2']) / 2
        y = (bbox['y1'] + bbox['y2']) / 2
        
        # Use Playwright's mouse click at coordinates
        nova.page.mouse.click(x, y)
        
    elif action_type == 'hover':
        # Calculate center and move mouse
        bbox = step['bbox']
        x = (bbox['x1'] + bbox['x2']) / 2
        y = (bbox['y1'] + bbox['y2']) / 2
        nova.page.mouse.move(x, y)
        
    elif action_type == 'type':
        # Click at bbox first to focus element
        bbox = step['bbox']
        x = (bbox['x1'] + bbox['x2']) / 2
        y = (bbox['y1'] + bbox['y2']) / 2
        nova.page.mouse.click(x, y)
        
        # Type text
        nova.page.keyboard.type(step['text'])
        
        # Press Enter if needed
        if step.get('press_enter'):
            nova.page.keyboard.press("Enter")
        
    elif action_type == 'scroll':
        # Scroll in specified direction
        direction = step['direction']
        amount = step.get('value', 800)  # Default viewport height
        
        if direction == 'down':
            nova.page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == 'up':
            nova.page.evaluate(f"window.scrollBy(0, -{amount})")
        elif direction == 'left':
            nova.page.evaluate(f"window.scrollBy(-{amount}, 0)")
        elif direction == 'right':
            nova.page.evaluate(f"window.scrollBy({amount}, 0)")
        
    elif action_type == 'navigate':
        # Navigate to URL
        nova.page.goto(step['url'])
```

### Error Handling

```python
def execute_cached_steps(nova, cached_steps: List[Dict]):
    """Execute all cached steps in sequence with error handling"""
    for i, step in enumerate(cached_steps):
        try:
            execute_cached_step(nova, step)
            time.sleep(0.1)  # Small delay between actions
        except Exception as e:
            # Log error and re-raise to trigger fallback
            logger.error(f"Failed to execute cached step {i}: {step['type']} - {e}")
            raise
```

---

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

---

## API Changes

### GET /usecases/{usecase_id}
**Response changes** (add):
```json
{
  "enableCache": false
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
  "enableCache": false
}
```

### PATCH /usecases/{usecase_id}
**Request changes** (add optional):
```json
{
  "enableCache": true
}
```

---

## Testing Strategy

### Unit Tests

**Parser tests** (`test_parse_nova_act_steps.py`):
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

def test_parse_type_action():
    # Test with and without pressEnter
    pass

def test_parse_multiple_steps():
    # Test response with multiple actions
    pass
```

**Executor tests** (`test_cache_executor.py`):
```python
@mock.patch('nova.page.mouse.click')
def test_execute_cached_click(mock_click):
    step = {'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}
    execute_cached_step(mock_nova, step)
    mock_click.assert_called_once_with(200, 300)  # Center point

@mock.patch('nova.page.keyboard.type')
def test_execute_cached_type(mock_type):
    step = {'type': 'type', 'text': 'admin', 'bbox': {...}, 'press_enter': False}
    execute_cached_step(mock_nova, step)
    mock_type.assert_called_once_with('admin')
```

**Cache Builder Lambda tests** (`test_build_step_cache.py`):
```python
@mock_s3
@mock_dynamodb
def test_cache_builder_success():
    # Setup mock S3 with act files
    # Setup mock DynamoDB with execution steps
    # Invoke handler
    # Verify cache created in STEP records
    pass

def test_cache_builder_skips_non_success():
    event = {'detail': {'execution_status': 'failed'}}
    result = handler(event, None)
    # Verify no cache created
    pass
```

### Integration Tests

```python
def test_cache_hit_faster_than_nova_act():
    # 1. Execute with Nova Act (first run)
    start = time.time()
    execute_navigation_step(nova, step, {'enable_cache': False})
    nova_act_time = time.time() - start
    
    # 2. Build cache (simulate)
    # 3. Execute with cache (second run)
    start = time.time()
    execute_navigation_step(nova, step_with_cache, {'enable_cache': True})
    cache_time = time.time() - start
    
    # 4. Assert cache is significantly faster
    assert cache_time < nova_act_time / 5  # At least 5x faster
    assert cache_time < 0.5  # Less than 500ms
```

### E2E Tests with qa-studio

```bash
# Create test usecase with caching enabled
qa-studio create-test --title "Cache Test" --url "https://example.com" --enable-cache

# Add navigation steps
qa-studio add-step --instruction "Click login button"
qa-studio add-step --instruction "Type username"

# Execute first time (cache miss)
qa-studio run --local

# Execute second time (cache hit)
qa-studio run --local

# Verify cache was used (check logs)
```

---

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

---

## Infrastructure Changes

### EventBridge
- Create event bus (or use default)
- Add rule: `detail-type = "usecase.execution.completed"`
- Target: Cache Builder Lambda

### Lambda
- New: `build_step_cache.py`
- Permissions: DynamoDB read/write, S3 read, EventBridge consume

### DynamoDB
- No new tables (single-table design)
- No new GSIs
- Just add optional fields to existing records

---

## Rollout Plan

1. **Phase 1**: Deploy cache building (no execution changes)
   - Monitor cache creation
   - Verify data quality
   - No user impact

2. **Phase 2**: Enable cache execution for opt-in usecases
   - Add UI toggle
   - Users can enable per usecase
   - Monitor performance gains

3. **Phase 3**: Evaluate default setting
   - If successful, consider changing default to True
   - Existing usecases stay as-is
   - New usecases get cache by default

---

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

---

## Future Enhancements

**Not in this PR**:
- Cache success/fail counters (add if needed)
- Cache TTL (cache lives with step for now)
- Cache compression (not needed, size is small)
- Selector extraction (bbox is sufficient)
- Cross-usecase cache sharing (instruction-based only for now)

---

## References

- Nova Act SDK: https://github.com/aws/nova-act
- Browser interface: https://github.com/aws/nova-act/blob/main/src/nova_act/tools/browser/interface/browser.py
- Example response: `~/Downloads/act_019c9f2a-d303-7dc3-9fd1-c4793981fe63_Close_any_popups_on_the_page_calls.json`
- DynamoDB single-table design: `.kiro/steering/01_dynamodb.md`
- API design guidelines: `.kiro/steering/02_api-design.md`
- Coding standards: `.kiro/steering/05_coding.md`
