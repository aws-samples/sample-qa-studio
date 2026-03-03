# CRITICAL FINDINGS - Bounding Box Cache Implementation

## Key Discoveries

### 1. Nova Act Returns Multiple Steps Per Call

**CRITICAL**: Each `nova.act()` call can return **multiple steps**, not just one action.

Example from actual response:
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

### 2. Nova Act Uses Bounding Boxes, Not Selectors

Nova Act actions use **bounding box coordinates**, not CSS selectors:

```python
agentClick("<box>621,71,640,143</box>")  # x1, y1, x2, y2
agentType("admin")
agentScroll("down")
```

**Implication**: 
- We should cache bbox coordinates (what Nova Act actually uses)
- Selector extraction is optional enhancement, not required
- Bbox coordinates are the source of truth

### 3. Only Cache `nova.act()`, NOT `nova.act_get()`

- `nova.act()` - Navigation actions (clicks, scrolls, typing) → **CACHE THIS**
- `nova.act_get()` - Data extraction → **DO NOT CACHE** (data may be stale)

### 4. Nova Act Exposes Playwright Page Object

From Nova Act docs:
> `NovaAct` exposes a Playwright `Page` object directly under the `page` attribute.

**Implication**: We can use Playwright's API directly to execute cached actions:
- `nova.page.mouse.click(x, y)` - Click at coordinates
- `nova.page.keyboard.type(text)` - Type text
- `nova.page.evaluate("window.scrollBy(0, 800)")` - Scroll

## Revised Cache Strategy

### What We Cache

```python
{
  "cache_key": "hash(url_pattern + instruction + page_structure)",
  "steps": [
    {
      "type": "click",
      "bbox": {"x1": 621, "y1": 71, "x2": 640, "y2": 143}
    },
    {
      "type": "type",
      "text": "admin"
    }
  ],
  "metadata": {
    "timestamp": "...",
    "success_count": 10,
    "fail_count": 0
  }
}
```

### How We Execute Cache

```python
def execute_cached_steps(nova: NovaAct, cached_steps: list[dict]):
    """Execute all cached steps in sequence"""
    for step in cached_steps:
        if step['type'] == 'click':
            bbox = step['bbox']
            x = (bbox['x1'] + bbox['x2']) / 2
            y = (bbox['y1'] + bbox['y2']) / 2
            nova.page.mouse.click(x, y)
            
        elif step['type'] == 'type':
            nova.page.keyboard.type(step['text'])
            
        elif step['type'] == 'scroll':
            direction = step['direction']
            amount = 800  # viewport height
            if direction == 'down':
                nova.page.evaluate(f"window.scrollBy(0, {amount})")
            else:
                nova.page.evaluate(f"window.scrollBy(0, -{amount})")
```

### How We Extract Cache Data

```python
def parse_nova_act_response(result: dict) -> list[dict]:
    """Parse Nova Act response into cacheable steps"""
    import re
    
    cached_steps = []
    
    for step in result.get('steps', []):
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
        
        # Parse type: agentType("text")
        type_match = re.search(r'agentType\("([^"]+)"\)', raw_body)
        if type_match:
            cached_steps.append({
                "type": "type",
                "text": type_match.group(1)
            })
        
        # Parse scroll: agentScroll("up|down")
        scroll_match = re.search(r'agentScroll\("(up|down)"\)', raw_body)
        if scroll_match:
            cached_steps.append({
                "type": "scroll",
                "direction": scroll_match.group(1)
            })
    
    return cached_steps
```

## Implementation Changes Required

### 1. Update Integration Strategy Document
- Change from "cache single action" to "cache sequence of steps"
- Update cache data structure to store list of steps
- Update execution logic to replay all steps

### 2. Update Cache Manager
- Store list of steps instead of single action
- Parse `rawProgramBody` from Nova Act response
- Handle multiple steps per cache entry

### 3. Update Navigation Step Handler
- Parse Nova Act response to extract all steps
- Execute all cached steps in sequence
- Fallback to Nova Act if any step fails

## Performance Impact

**Expected speedup per cached instruction:**
- Nova Act: 2-5 seconds per call
- Cached execution: 100-300ms per step
- **Total speedup**: 10-20x for single-step actions, 20-50x for multi-step actions

**Example:**
- Instruction: "Close any popups"
- Nova Act: 2 steps × 3 seconds = 6 seconds
- Cached: 2 steps × 200ms = 400ms
- **Speedup**: 15x faster

## Complete List of Agent Actions

From `browser.py` in Nova Act SDK:

### Actions to Cache (5 total)
1. **agentClick(box, click_type?, click_options?)** - Click center of bbox
2. **agentHover(box)** - Hover on center of bbox  
3. **agentScroll(direction, box, value?)** - Scroll element (up/down/left/right)
4. **agentType(value, box, pressEnter?)** - Type text into element
5. **goToUrl(url)** - Navigate to URL

### Actions NOT to Cache (6 total)
6. **think(value)** - Internal reasoning, no effect on environment
7. **return(value?)** - End execution
8. **throw(value)** - Task not possible error
9. **wait(seconds)** - Pause execution
10. **waitForPageToSettle()** - Wait for page ready
11. **takeObservation()** - Take browser state snapshot

**Source**: https://github.com/aws/nova-act/blob/main/src/nova_act/tools/browser/interface/browser.py

## Final Design Decisions

### Cache Storage
- Store in STEP records (not separate table)
- Fields: `cached_steps` (JSON string), `cache_last_updated` (ISO timestamp)
- Minimal approach: no success/fail counters

### Cache Key
- Instruction-based (stored in STEP record)
- Self-correcting on failure

### Per-Usecase Toggle
- Add `enable_cache` boolean to USECASE metadata
- Default: True (opt-out)

### Event-Driven Building
- Worker emits: `usecase.execution.completed` event
- Cache Builder Lambda consumes event
- Fetches data from DynamoDB/S3
- Updates STEP records in batch

## Next Steps

1. ✅ Update cache-execution-strategy.md with new findings
2. ✅ Identify complete list of agent actions
3. ✅ Create comprehensive implementation plan
4. ⬜ Implement Phase 1: Cache Building
5. ⬜ Implement Phase 2: Cache Execution
6. ⬜ Implement Phase 3: Testing & Validation
