# Cache Execution Strategy - How to Execute Cached Actions

## Critical Discovery: Nova Act Returns Multiple Steps

**IMPORTANT**: Each call to `nova.act()` can result in **multiple steps**. We need to cache each step individually.

Example from actual Nova Act response:
```json
{
  "steps": [
    {
      "request": {...},
      "response": {
        "program": [],
        "rawProgramBody": "think(\"...\");\nagentClick(\"<box>621,71,640,143</box>\");\n",
        "requestId": "..."
      }
    },
    {
      "request": {...},
      "response": {
        "program": [],
        "rawProgramBody": "think(\"...\");\nreturn();\n",
        "requestId": "..."
      }
    }
  ],
  "metadata": {
    "num_steps_executed": 2,
    ...
  }
}
```

**Key Insight**: The `rawProgramBody` contains the actual actions:
- `agentClick("<box>x1,y1,x2,y2</box>")` - Click action with bounding box
- `agentType("text")` - Type action
- `agentScroll(direction)` - Scroll action
- `think("...")` - Internal reasoning (not cached)
- `return()` - End of execution

## Key Discovery

Nova Act exposes a **Playwright `Page` object** via `nova.page`, which means we can use Playwright's API directly to execute cached actions without calling `nova.act()`.

From the Nova Act docs:
> `NovaAct` exposes a Playwright `Page` object directly under the `page` attribute. This can be used to retrieve current state of the browser, for example a screenshot or the DOM, or actuate it.

## Execution Methods by Action Type

### 1. Click Actions

**What Nova Act returns:**
```python
rawProgramBody: 'agentClick("<box>621,71,640,143</box>");'
```

**What we cache:**
```python
{
    "type": "click",
    "bbox": {"x1": 621, "y1": 71, "x2": 640, "y2": 143},
    "selector": None  # We'll try to extract this if possible
}
```

**How to execute:**
```python
def execute_cached_click(nova: NovaAct, cached_data: dict):
    """Execute cached click using Playwright"""
    bbox = cached_data['bbox']
    
    # Calculate center of bounding box
    center_x = (bbox['x1'] + bbox['x2']) / 2
    center_y = (bbox['y1'] + bbox['y2']) / 2
    
    # Use Playwright's mouse click at coordinates
    nova.page.mouse.click(center_x, center_y)
    
    # Alternative: If we have a selector (extracted post-execution)
    if cached_data.get('selector'):
        element = nova.page.locator(cached_data['selector'])
        element.click(timeout=5000)
```

**Reliability:** Bbox coordinates are what Nova Act uses, so they're the most reliable. Selector extraction is optional enhancement.

### 2. Type/Fill Actions

**What Nova Act returns:**
```python
rawProgramBody: 'agentType("admin");'
```

**What we cache:**
```python
{
    "type": "type",
    "text": "admin",  # We cache the text from the instruction
    "bbox": {"x1": 150, "y1": 300, "x2": 350, "y2": 330},  # Optional
    "selector": None  # Optional, extracted post-execution
}
```

**How to execute:**
```python
def execute_cached_type(nova: NovaAct, cached_data: dict, current_instruction: str):
    """Execute cached typing using Playwright"""
    
    # Extract current text from instruction (text may be dynamic)
    text_to_type = extract_text_from_instruction(current_instruction)
    
    # If we have a selector, use it
    if cached_data.get('selector'):
        element = nova.page.locator(cached_data['selector'])
        element.fill(text_to_type, timeout=5000)
    
    # Otherwise, click at bbox location first, then type
    elif cached_data.get('bbox'):
        bbox = cached_data['bbox']
        center_x = (bbox['x1'] + bbox['x2']) / 2
        center_y = (bbox['y1'] + bbox['y2']) / 2
        nova.page.mouse.click(center_x, center_y)
        nova.page.keyboard.type(text_to_type)
```

**Text extraction from instruction:**
```python
def extract_text_from_instruction(instruction: str) -> str:
    """Extract text to type from instruction"""
    import re
    
    # Match quoted text: "Type 'admin' in username"
    match = re.search(r"['\"]([^'\"]+)['\"]", instruction)
    if match:
        return match.group(1)
    
    # Match text after keywords
    instruction_lower = instruction.lower()
    for keyword in ['type', 'enter', 'input', 'fill']:
        if keyword in instruction_lower:
            # Extract word after keyword
            words = instruction.split()
            keyword_idx = [i for i, w in enumerate(words) if w.lower() == keyword]
            if keyword_idx and keyword_idx[0] + 1 < len(words):
                return words[keyword_idx[0] + 1]
    
    return ""
```

### 3. Scroll Actions

**What Nova Act returns:**
```python
rawProgramBody: 'agentScroll("down");'
# or
rawProgramBody: 'agentScroll("up");'
```

**What we cache:**
```python
{
    "type": "scroll",
    "direction": "down",  # or "up"
    "scroll_amount": 800  # pixels (estimated from viewport)
}
```

**How to execute:**
```python
def execute_cached_scroll(nova: NovaAct, cached_data: dict):
    """Execute cached scroll using Playwright"""
    direction = cached_data['direction']
    amount = cached_data.get('scroll_amount', 800)  # Default to viewport height
    
    if direction == 'down':
        nova.page.evaluate(f"window.scrollBy(0, {amount})")
    elif direction == 'up':
        nova.page.evaluate(f"window.scrollBy(0, -{amount})")
```

## Cache Data Extraction Strategy

### How Nova Act Returns Data

Nova Act returns a response with multiple steps in `rawProgramBody` format:

```python
result = nova.act("Close any popups")
# result contains:
# {
#   "steps": [
#     {
#       "response": {
#         "rawProgramBody": "think(\"...\");\nagentClick(\"<box>621,71,640,143</box>\");\n"
#       }
#     },
#     {
#       "response": {
#         "rawProgramBody": "think(\"...\");\nreturn();\n"
#       }
#     }
#   ]
# }
```

### Parsing Strategy

**Parse `rawProgramBody` to extract actions:**

```python
import re

def parse_nova_act_steps(result: dict) -> list[dict]:
    """Parse Nova Act result into cacheable steps"""
    cached_steps = []
    
    for step in result.get('steps', []):
        raw_body = step['response']['rawProgramBody']
        
        # Parse click actions
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
        
        # Parse type actions
        type_match = re.search(r'agentType\("([^"]+)"\)', raw_body)
        if type_match:
            cached_steps.append({
                "type": "type",
                "text": type_match.group(1)
            })
        
        # Parse scroll actions
        scroll_match = re.search(r'agentScroll\("(up|down)"\)', raw_body)
        if scroll_match:
            cached_steps.append({
                "type": "scroll",
                "direction": scroll_match.group(1)
            })
    
    return cached_steps
```

## Implementation in `navigation_step.py`

```python
def execute_navigation_step(nova: NovaAct, step: ExecutionStep, cache_manager=None):
    """Execute navigation step with caching"""
    
    instruction = step.instruction
    cache_used = False
    cached_steps = []
    
    # Try cache first
    if cache_manager and cache_manager.enabled:
        cache_key = cache_manager.generate_key(
            url=nova.page.url,
            instruction=instruction,
            page_content_hash=hash(nova.page.content())
        )
        
        cached_steps = cache_manager.get(cache_key)
        
        if cached_steps:
            try:
                # Execute all cached steps using Playwright
                for cached_step in cached_steps:
                    execute_cached_step(nova, cached_step)
                
                cache_manager.record_hit(cache_key)
                cache_used = True
                
            except Exception as e:
                logger.warning(f"Cache execution failed: {e}, retrying with Nova Act")
                cache_manager.record_miss(cache_key)
    
    # Normal Nova Act execution if cache not used
    if not cache_used:
        result = nova.act(instruction)
        
        # Extract and cache steps
        if cache_manager and cache_manager.enabled:
            cached_steps = parse_nova_act_steps(result)
            if cached_steps:
                cache_manager.store(cache_key, cached_steps)
    
    return result, success, logs


def execute_cached_step(nova: NovaAct, cached_step: dict):
    """Execute a single cached step using Playwright"""
    action_type = cached_step['type']
    
    if action_type == 'click':
        bbox = cached_step['bbox']
        center_x = (bbox['x1'] + bbox['x2']) / 2
        center_y = (bbox['y1'] + bbox['y2']) / 2
        nova.page.mouse.click(center_x, center_y)
        
    elif action_type == 'type':
        # Text is already in cached_step from Nova Act response
        text = cached_step['text']
        nova.page.keyboard.type(text)
        
    elif action_type == 'scroll':
        direction = cached_step['direction']
        amount = cached_step.get('scroll_amount', 800)
        if direction == 'down':
            nova.page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == 'up':
            nova.page.evaluate(f"window.scrollBy(0, -{amount})")


def parse_nova_act_steps(result: dict) -> list[dict]:
    """Parse Nova Act result into cacheable steps"""
    import re
    
    cached_steps = []
    
    for step in result.get('steps', []):
        raw_body = step['response']['rawProgramBody']
        
        # Parse click actions
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
        
        # Parse type actions
        type_match = re.search(r'agentType\("([^"]+)"\)', raw_body)
        if type_match:
            cached_steps.append({
                "type": "type",
                "text": type_match.group(1)
            })
        
        # Parse scroll actions
        scroll_match = re.search(r'agentScroll\("(up|down)"\)', raw_body)
        if scroll_match:
            cached_steps.append({
                "type": "scroll",
                "direction": scroll_match.group(1),
                "scroll_amount": 800  # Default viewport height
            })
    
    return cached_steps
```

## Testing Strategy

### Unit Tests
```python
def test_execute_cached_click():
    # Mock nova.page.locator
    # Verify click() called with correct selector
    pass

def test_execute_cached_type():
    # Mock nova.page.locator
    # Verify fill() called with correct text
    pass

def test_extract_text_from_instruction():
    assert extract_text_from_instruction("Type 'admin' in username") == "admin"
    assert extract_text_from_instruction("Enter password123") == "password123"
```

### Integration Tests
```python
def test_cache_hit_faster_than_nova_act():
    # Execute with Nova Act (first run)
    # Execute with cache (second run)
    # Assert cache execution < 500ms
    # Assert Nova Act execution > 2000ms
    pass
```

## Performance Expectations

| Action Type | Nova Act | Cached | Speedup |
|-------------|----------|--------|---------|
| Click       | 2-5s     | 100-300ms | 10-20x |
| Type        | 2-4s     | 200-400ms | 8-15x |
| Scroll      | 1-3s     | 50-100ms | 15-30x |

## Open Questions

1. **Should we cache `nova.act_get()` calls?**
   - **Answer**: NO - only cache `nova.act()` calls (navigation actions)
   - `act_get()` is for data extraction, not navigation
   - Caching data extraction could return stale data

2. **How to handle dynamic text in type actions?**
   - Nova Act returns the actual text typed in `agentType("text")`
   - We cache this text directly from the response
   - For dynamic values (e.g., timestamps), cache may not help

3. **Cache key generation:**
   - Should include: URL pattern, instruction hash, page structure hash
   - Page structure hash: hash of DOM structure (not content)
   - This ensures cache is invalidated when page layout changes

4. **Scroll amount estimation:**
   - Nova Act doesn't return exact scroll amount
   - We estimate based on viewport height (800px default)
   - May need adjustment based on actual page behavior

5. **Multiple steps per instruction:**
   - Each `nova.act()` call can return multiple steps
   - We cache ALL steps as a sequence
   - Execute them in order during cache replay

6. **Cache validation:**
   - Should we validate element exists before using cache?
   - Pro: Prevents errors
   - Con: Adds latency (defeats purpose)
   - **Recommendation**: No validation, rely on try/catch and fallback

7. **Cross-usecase cache sharing:**
   - Should different usecases share cache?
   - Pro: More cache hits
   - Con: Different usecases may have different page states
   - **Recommendation**: Share cache, but include usecase_id in key for isolation option

## Next Steps

1. Implement `execute_cached_action()` with all three action types
2. Implement `extract_cache_data_after_act()` using activeElement
3. Add error handling and fallback to Nova Act
4. Write unit tests for extraction and execution
5. Run integration tests to measure performance gains
