# Nova Act Bounding Box Cache - Performance Optimization Design

## Overview

Cache bounding boxes discovered by Nova Act during test execution to significantly reduce execution time on subsequent runs by reusing element locations instead of re-discovering them.

## Problem Statement

Currently, every `nova.act()` call requires Nova Act to:
1. Analyze the page screenshot
2. Identify UI elements
3. Calculate bounding boxes for interaction
4. Execute the action

This process is repeated identically for stable UI elements across multiple test runs, wasting time and resources.

**Goal:** Cache bounding boxes from successful `nova.act()` calls and reuse them in subsequent executions to reduce test execution time by 40-60%.

## Caching Strategy

### What Gets Cached

**YES - Cache these actions:**
1. **Click actions** - Button clicks, link clicks, checkbox toggles
   - Cache: selector + bounding box
   - Why: Element location is stable

2. **Scroll actions** - Page scrolling, element scrolling into view
   - Cache: scroll position (x, y)
   - Why: Scroll distance is predictable

3. **Navigation actions** - Going to specific elements
   - Cache: selector + bounding box
   - Why: UI structure is stable

**NO - Don't cache these:**
1. **Typing actions with dynamic data** - Forms with user input, search queries
   - Why: Data changes per execution (variables, timestamps, etc.)
   - Exception: Static text like "admin" username can be cached

2. **Data extraction** - `nova.act_get()` calls
   - Why: Always need fresh data from the page

### Typing Action Caching Rules

```python
def should_cache_typing(instruction, parsed_step):
    """Determine if typing action should be cached"""
    
    # Check if instruction contains variables
    if has_variables(instruction):
        return False  # Dynamic data, don't cache
    
    # Check if it's a static value
    if parsed_step.step_type == 'secret':
        return False  # Secrets never cached
    
    # Static typing (e.g., "type 'admin' in username field")
    return True

def execute_typing_with_cache(nova, cached_data, current_text):
    """Execute typing using cache, but with current text value"""
    element = nova.page.locator(cached_data['selector'])
    element.fill(current_text)  # Use current value, not cached text
    return True
```

**Typing cache stores:**
- Element selector (WHERE to type)
- Bounding box (element location)
- NOT the actual text (that's dynamic)

**Example:**
```python
# Instruction: "Type {{username}} in the login field"
# Cache stores: selector="#username-input", bbox={...}
# At runtime: Uses current value of {{username}} variable
# Benefit: Skips Nova Act finding the field, just types directly
```

## How Caching Works

### Cache Lifecycle

**1. First Execution (Cache Miss)**
```
User runs test
  → nova.act("Click login button")
  → Nova Act analyzes page (slow)
  → Finds button, gets selector + bbox
  → Clicks button
  → Extract: {type: "click", selector: "#login-btn", bbox: {...}}
  → Store in DynamoDB with cache_key
```

**2. Second Execution (Cache Hit)**
```
User runs test again
  → Check cache with cache_key
  → Found: {type: "click", selector: "#login-btn", bbox: {...}}
  → Skip Nova Act, use Playwright directly
  → element = page.locator("#login-btn")
  → element.click()
  → Done in <100ms vs 2-5 seconds
```

**3. Cache Miss (Page Changed)**
```
User runs test after UI update
  → Check cache with cache_key
  → Page structure hash changed → cache_key different
  → Cache miss
  → Execute with nova.act() (normal flow)
  → Store new cache entry
```

**4. Cache Failure (Stale Cache)**
```
User runs test
  → Check cache, found entry
  → Try: page.locator("#login-btn").click()
  → Error: Element not found
  → AUTO-RETRY: nova.act("Click login button")
  → Success
  → Update cache with new selector
```

### Performance Comparison

**Without Cache:**
```
Step 1: nova.act("Click login")     → 3.2s
Step 2: nova.act("Type username")   → 2.8s  
Step 3: nova.act("Type password")   → 2.5s
Step 4: nova.act("Click submit")    → 3.1s
Total: 11.6 seconds
```

**With Cache (after first run):**
```
Step 1: Cached click                → 0.2s
Step 2: Cached type (find field)    → 0.3s
Step 3: Cached type (find field)    → 0.3s
Step 4: Cached click                → 0.2s
Total: 1.0 seconds (91% faster!)
```

### Cache Key Generation

```python
def generate_cache_key(url, instruction, page_content):
    # Normalize URL (remove dynamic parts)
    url_pattern = normalize_url(url)
    # "https://app.example.com/dashboard?user=123" 
    # → "https://app.example.com/dashboard"
    
    # Hash page structure (not content)
    structure = extract_dom_structure(page_content)
    # "<div><header><nav>...</nav></header><main>...</main></div>"
    structure_hash = md5(structure)
    
    # Normalize instruction (remove variable values)
    normalized_instruction = normalize_instruction(instruction)
    # "Type 'john@example.com' in email field"
    # → "Type in email field"
    
    cache_key = sha256(f"{url_pattern}:{normalized_instruction}:{structure_hash}")
    return cache_key
```

This ensures:
- Same action on same page structure = cache hit
- Different URL query params = still cache hit
- Page structure changed = cache miss (rebuild)
- Different variable values = still cache hit (only selector cached)

## Technical Design

### Cache Key Structure

```python
cache_key = hash(
    url_pattern,      # Normalized URL (remove query params, fragments)
    instruction_hash, # SHA256 of instruction text (detects step changes)
    page_structure    # Hash of DOM structure
)
```

**Instruction hash ensures:**
- If step instruction changes → new cache_key → cache miss → rebuild
- Example: "Click login" → "Click the login button" = different hash = rebuild cache

### Cache Storage

**DynamoDB Table: `BoundingBoxCache`**
```
PK: USECASE#<usecase_id>
SK: CACHE#<cache_key>
Attributes:
- action_type: str (click|scroll|type)
- selector: str (CSS/XPath selector) [for click/type]
- bbox: {x, y, width, height} [for click/type]
- scroll_position: {x, y, viewport_height} [for scroll]
- instruction: str (original instruction text)
- instruction_hash: str (SHA256 of instruction)
- url_pattern: str
- page_structure_hash: str
- created_at: timestamp
- last_used_at: timestamp
- hit_count: int
- miss_count: int
- success_rate: float
TTL: 30 days
```

**Usecase Table Update:**
Add cache configuration to existing usecase records:
```
PK: USECASE#<usecase_id>
SK: METADATA
Attributes:
  ... existing fields ...
  cache_enabled: bool (default: true)
  cache_invalidated_at: timestamp (set when steps change)
```

### Worker Integration

**Modified `worker.py` execution flow with auto-retry:**

```python
# In navigation_step.py
def execute_navigation_step(nova, parsed_step, cache_manager):
    cache_key = cache_manager.generate_key(
        nova.page.url,
        parsed_step.instruction,
        nova.page.content()
    )
    
    cached_data = cache_manager.get(cache_key)
    
    if cached_data:
        try:
            # Try cached execution first
            success = _execute_with_cache(nova, cached_data)
            if success:
                cache_manager.record_hit(cache_key)
                return result, True, "Cache hit"
        except Exception as e:
            logger.warning(f"Cache execution failed: {e}, retrying without cache")
            cache_manager.record_miss(cache_key)
            # AUTO-RETRY: Fall through to normal execution
    
    # Normal Nova Act execution (first run or cache retry)
    result = nova.act(parsed_step.instruction)
    
    # Extract and cache data from successful result
    if result.metadata.num_steps_executed > 0:
        cache_data = _extract_cache_data(nova, result)
        if cache_data:
            cache_manager.store(cache_key, cache_data)
    
    return result, True, "Executed"

def _execute_with_cache(nova, cached_data, parsed_step=None):
    """Execute action using cached data"""
    if cached_data['type'] == 'click':
        # Use Playwright directly with cached selector/bbox
        element = nova.page.locator(cached_data['selector'])
        element.click()
        
    elif cached_data['type'] == 'scroll':
        # Execute cached scroll action
        nova.page.evaluate(f"window.scrollTo({cached_data['x']}, {cached_data['y']})")
        
    elif cached_data['type'] == 'type':
        # Use cached selector, but current text value
        element = nova.page.locator(cached_data['selector'])
        
        # Get current text from parsed_step (with variables resolved)
        current_text = _extract_text_from_instruction(parsed_step.instruction)
        element.fill(current_text)
    
    return True

def _extract_text_from_instruction(instruction):
    """Extract the text to type from instruction"""
    # Parse instruction like "Type 'admin' in username"
    # or "Enter {{password}} in password field"
    # Return the actual text value (variables already resolved by template_parser)
    
    # Simple regex to extract quoted text or variable values
    import re
    match = re.search(r"['\"]([^'\"]+)['\"]", instruction)
    if match:
        return match.group(1)
    
    # If no quotes, extract first word after "type" or "enter"
    words = instruction.lower().split()
    if 'type' in words:
        idx = words.index('type')
        return words[idx + 1] if idx + 1 < len(words) else ""
    
    return ""
```

### Cache Data Extraction

Extract action type, selectors, and scroll positions from Nova Act execution:

```python
def _extract_cache_data(nova, act_result):
    """
    Extract cacheable data from Nova Act execution.
    Supports: clicks, scrolls, typing
    """
    # Get current page state
    current_url = nova.page.url
    
    # Detect action type from Nova Act traces or page changes
    action_type = _detect_action_type(act_result)
    
    if action_type == 'scroll':
        # Cache scroll position
        scroll_pos = nova.page.evaluate("({x: window.scrollX, y: window.scrollY})")
        return {
            "type": "scroll",
            "x": scroll_pos['x'],
            "y": scroll_pos['y'],
            "viewport_height": nova.page.viewport_size['height']
        }
    
    elif action_type in ['click', 'type']:
        # Find the element that was interacted with
        # Use Playwright's accessibility tree or last focused element
        element = nova.page.evaluate("""
            () => {
                const el = document.activeElement;
                return el ? {
                    selector: el.id ? `#${el.id}` : el.className ? `.${el.className.split(' ')[0]}` : el.tagName,
                    bbox: el.getBoundingClientRect()
                } : null;
            }
        """)
        
        if element:
            return {
                "type": action_type,
                "selector": element['selector'],
                "bbox": {
                    "x": element['bbox']['x'],
                    "y": element['bbox']['y'],
                    "width": element['bbox']['width'],
                    "height": element['bbox']['height']
                }
            }
    
    return None

def _detect_action_type(act_result):
    """Detect action type from Nova Act result"""
    # Check if scroll happened by comparing viewport position
    # Or parse Nova Act's internal logs/traces
    # Simplified: return based on instruction keywords
    return "click"  # Default
```

### Cache Manager Class

```python
class BoundingBoxCacheManager:
    def __init__(self, usecase_id, db_client, enabled=True):
        self.usecase_id = usecase_id
        self.db_client = db_client
        self.stats = {"hits": 0, "misses": 0}
        
        # Check if cache is enabled for this usecase
        usecase = db_client.get_usecase(usecase_id)
        self.enabled = enabled and usecase.get('cache_enabled', True)
        self.cache_invalidated_at = usecase.get('cache_invalidated_at')
        
        logger.info(f"Cache manager initialized: enabled={self.enabled}, usecase={usecase_id}")
    
    def generate_key(self, url, instruction, page_content):
        url_pattern = self._normalize_url(url)
        instruction_hash = hashlib.sha256(instruction.encode()).hexdigest()
        structure_hash = self._hash_dom_structure(page_content)
        
        cache_key = hashlib.sha256(
            f"{url_pattern}:{instruction_hash}:{structure_hash}".encode()
        ).hexdigest()
        
        return cache_key
    
    def get(self, cache_key):
        if not self.enabled:
            return None
        
        cache_entry = self.db_client.get_bbox_cache(self.usecase_id, cache_key)
        
        # Invalidate if cache is older than usecase invalidation timestamp
        if cache_entry and self.cache_invalidated_at:
            if cache_entry['created_at'] < self.cache_invalidated_at:
                logger.info(f"Cache entry outdated (step changed), invalidating")
                self.db_client.delete_bbox_cache(self.usecase_id, cache_key)
                return None
        
        return cache_entry
    
    def store(self, cache_key, cache_data):
        if not self.enabled:
            return
        self.db_client.store_bbox_cache(
            self.usecase_id, 
            cache_key, 
            cache_data
        )
    
    def record_hit(self, cache_key):
        """Increment hit count and update success rate"""
        self.stats["hits"] += 1
        self.db_client.increment_cache_hit(self.usecase_id, cache_key)
    
    def record_miss(self, cache_key):
        """Increment miss count and update success rate"""
        self.stats["misses"] += 1
        self.db_client.increment_cache_miss(self.usecase_id, cache_key)
        
        # Auto-invalidate if success rate drops too low
        cache_entry = self.db_client.get_bbox_cache(self.usecase_id, cache_key)
        if cache_entry:
            success_rate = cache_entry['hit_count'] / (cache_entry['hit_count'] + cache_entry['miss_count'])
            if success_rate < 0.7:
                logger.warning(f"Cache entry {cache_key} has low success rate {success_rate:.2f}, invalidating")
                self.db_client.delete_bbox_cache(self.usecase_id, cache_key)
    
    def _normalize_url(self, url):
        # Remove query params and fragments
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    
    def _hash_dom_structure(self, html_content):
        # Extract structural elements only (tags, not content)
        soup = BeautifulSoup(html_content, 'html.parser')
        structure = self._get_structure(soup)
        return hashlib.md5(structure.encode()).hexdigest()
```

### Cache Invalidation

**Automatic invalidation when:**
1. Instruction text changes (different instruction_hash in cache_key)
2. Page structure hash changes (DOM modified)
3. Cache entry older than 30 days (TTL)
4. Cache entry older than usecase's `cache_invalidated_at` timestamp
5. Success rate drops below 70%

**Manual invalidation options:**

**Option 1: Per-usecase flag (Recommended)**
```python
# When any step is updated via API
def update_step(usecase_id, step_id, new_instruction):
    # Update the step
    db_client.update_step(usecase_id, step_id, new_instruction)
    
    # Set invalidation timestamp on usecase
    db_client.update_usecase(usecase_id, {
        'cache_invalidated_at': datetime.now().isoformat()
    })
    
    # Next execution will ignore all cache entries older than this timestamp
```

**Option 2: Explicit cache clear**
```python
# New Lambda endpoint
POST /usecases/{usecase_id}/cache/invalidate
{
  "reason": "steps_changed"
}

# Deletes all cache entries for this usecase
```

**Option 3: Toggle cache on/off**
```python
# New Lambda endpoint
PATCH /usecases/{usecase_id}
{
  "cache_enabled": false
}

# Disables cache for this usecase without deleting entries
```

## Implementation Plan

### Phase 1: Infrastructure (Week 1)
- Create DynamoDB cache table
- Add `cache_enabled` and `cache_invalidated_at` to usecase table
- Implement cache manager class
- Add global enable/disable flag

### Phase 2: Integration (Week 2)
- Modify navigation_step.py with cache logic
- Add instruction hash to cache key generation
- Integrate with worker.py
- Add cache data extraction logic

### Phase 3: API & Invalidation (Week 3)
- Create cache toggle endpoint (PATCH /usecases/{id})
- Create cache clear endpoint (POST /usecases/{id}/cache/clear)
- Create cache stats endpoint (GET /usecases/{id}/cache/stats)
- Auto-set `cache_invalidated_at` when steps are updated
- Test invalidation scenarios

### Phase 4: Frontend & Testing (Week 4)
- Add cache toggle to usecase settings UI
- Add cache stats display
- Add "Clear Cache" button
- Performance testing and validation
- Documentation

## Performance Impact

**Expected improvements:**
- 40-60% reduction in execution time for repeated tests
- 50% reduction in Nova Act API calls
- Lower costs due to fewer model invocations

**Measurements:**
- Cache hit rate
- Average execution time (with/without cache)
- Cost savings per execution

## Configuration

**Environment variables:**
```bash
ENABLE_BBOX_CACHE=true              # Global enable/disable
BBOX_CACHE_TTL_DAYS=30
BBOX_CACHE_MIN_SUCCESS_RATE=0.7
```

**Per-usecase configuration (in DynamoDB):**
```json
{
  "usecase_id": "123",
  "cache_enabled": true,              // Toggle cache for this usecase
  "cache_invalidated_at": "2026-02-28T14:00:00Z"  // Auto-set when steps change
}
```

**Frontend UI:**
```
Usecase Settings Page:
  ┌─────────────────────────────────┐
  │ Performance                     │
  │                                 │
  │ ☑ Enable bounding box cache    │
  │   Speed up test execution by    │
  │   caching element locations     │
  │                                 │
  │ [Clear Cache]                   │
  │                                 │
  │ Cache Stats:                    │
  │ • Hit rate: 78%                 │
  │ • Avg speedup: 3.2x             │
  │ • Last invalidated: 2 days ago  │
  └─────────────────────────────────┘
```

**API Endpoints:**
```
# Toggle cache
PATCH /usecases/{usecase_id}
{
  "cache_enabled": true|false
}

# Clear cache
POST /usecases/{usecase_id}/cache/clear

# Get cache stats
GET /usecases/{usecase_id}/cache/stats
Response:
{
  "enabled": true,
  "hit_rate": 0.78,
  "total_entries": 45,
  "last_invalidated_at": "2026-02-26T10:30:00Z"
}
```

## Risks & Mitigations

**Risk:** Cache returns stale bounding boxes for dynamic UIs
**Mitigation:** Page structure hash validation, fallback to normal execution

**Risk:** Cache overhead slows down first execution
**Mitigation:** Async cache storage, minimal extraction logic

**Risk:** Cache storage costs increase
**Mitigation:** 30-day TTL, cleanup of low-success entries

## Future Enhancements

1. **Smart cache warming** - Pre-populate cache from previous executions
2. **Cross-usecase sharing** - Share cache for identical steps
3. **ML-based invalidation** - Predict when cache will fail
4. **Partial cache** - Cache element discovery but re-validate position

## Success Metrics

- 50% cache hit rate within 1 month
- 40% average execution time reduction
- 30% cost reduction for repeated tests
- <5% cache-related failures
