# Bounding Box Cache Integration Strategy

## Executive Summary

This document defines the integration strategy for the bounding box cache system into the existing Nova Act QA Studio worker architecture. The goal is to minimize code changes while maximizing cache effectiveness.

## Current Architecture Analysis

### Worker Execution Flow
```
worker.py (main_batch)
  ├─ Initialize NovaAct context
  ├─ _execute_steps()
  │   └─ For each step:
  │       ├─ template_parser.parse_single_step()
  │       └─ Match step_type:
  │           ├─ 'secret' → execute_secret_step()
  │           ├─ 'validation' → execute_validation_step()
  │           ├─ 'retrieve_value' → execute_retrieve_value_step()
  │           ├─ 'assertion' → execute_assertion_step()
  │           ├─ 'url' → execute_url_step()
  │           ├─ 'download' → execute_download_step()
  │           └─ default → execute_navigation_step()
  └─ Update execution status
```

### Navigation Step Current Implementation
```python
# navigation_step.py
def execute_navigation_step(nova: NovaAct, step: ExecutionStep):
    instruction = step.instruction
    result = nova.act(instruction)  # Direct Nova Act call
    return result, success, logs
```

**Key Insight:** Navigation steps are the primary target for caching since they:
- Call `nova.act()` which is expensive (2-5 seconds)
- Have stable UI elements across runs
- Represent 70-80% of test execution time

## Integration Strategy

### 1. **Minimal Invasive Approach**

**Principle:** Integrate cache at the navigation step level only, avoiding changes to core worker logic.

**Why this works:**
- Navigation steps are isolated in `navigation_step.py`
- Other step types (validation, assertion, etc.) don't benefit from bbox caching
- Keeps cache logic contained and testable
- Easy to enable/disable via feature flag

### 2. **Cache Manager Initialization**

**Location:** `worker.py` in `main_batch()` function

```python
def main_batch():
    # ... existing initialization ...
    
    # Initialize cache manager (after db_client)
    cache_enabled = os.getenv('ENABLE_BBOX_CACHE', 'true').lower() == 'true'
    cache_manager = BoundingBoxCacheManager(
        usecase_id=usecase_id,
        db_client=db_client,
        enabled=cache_enabled
    )
    logger.info(f"Cache manager initialized: enabled={cache_enabled}")
    
    # ... rest of execution ...
    
    # Pass cache_manager to _execute_steps
    all_success = _execute_steps(
        nova, execution, execution_headers, template_parser,
        usecase_id, execution_id, s3_bucket_name, db_client, steps,
        cache_manager  # NEW PARAMETER
    )
```

### 3. **Navigation Step Integration**

**Modified `navigation_step.py`:**

```python
def execute_navigation_step(nova: NovaAct, step: ExecutionStep, cache_manager=None):
    """Execute navigation step with optional caching"""
    logger.info(f"Executing navigation step {step.sort}: {step.instruction}")
    
    # Build instruction
    instruction = step.instruction
    if hasattr(step, 'enable_advanced_click_types') and step.enable_advanced_click_types:
        instruction = f"{click_base_prompt}\n\n{step.instruction}"
    
    result = None
    success = True
    logs = ""
    cache_used = False
    
    try:
        # Try cache if available
        if cache_manager and cache_manager.enabled:
            cache_key = cache_manager.generate_key(
                url=nova.page.url,
                instruction=instruction,
                page_content=nova.page.content()
            )
            
            cached_data = cache_manager.get(cache_key)
            
            if cached_data:
                try:
                    # Execute with cache
                    _execute_with_cache(nova, cached_data, step)
                    cache_manager.record_hit(cache_key)
                    cache_used = True
                    logs = f"Cache hit (key: {cache_key[:8]}...)"
                    logger.info(f"Step {step.sort}: Cache hit")
                    
                    # Create minimal result object for cache hits
                    from types import SimpleNamespace
                    result = SimpleNamespace()
                    result.metadata = SimpleNamespace()
                    result.metadata.act_id = f"cached-{cache_key[:8]}"
                    result.metadata.num_steps_executed = 0
                    
                except Exception as cache_error:
                    logger.warning(f"Cache execution failed: {cache_error}, retrying with Nova Act")
                    cache_manager.record_miss(cache_key)
                    cache_used = False
        
        # Normal Nova Act execution (if cache not used or failed)
        if not cache_used:
            result = nova.act(instruction)
            
            # Store in cache if successful
            if cache_manager and cache_manager.enabled and result.metadata.num_steps_executed > 0:
                cache_data = _extract_cache_data(nova, result, instruction)
                if cache_data:
                    cache_manager.store(cache_key, cache_data)
                    logger.info(f"Step {step.sort}: Cached for future use")
                    
    except Exception as e:
        logger.error(f"Error executing navigation step {step.sort}: {str(e)}")
        success = False
        logs = str(e)
        # Create minimal result object
        from types import SimpleNamespace
        result = SimpleNamespace()
        result.metadata = SimpleNamespace()
        result.metadata.act_id = getattr(getattr(e, 'metadata', None), 'act_id', 'error')
    
    status = "success" if success else "error"
    logger.info(f"Navigation step {step.sort} completed: {status} (cache_used={cache_used})")
    
    return result, success, logs


def _execute_with_cache(nova: NovaAct, cached_data: dict, step: ExecutionStep):
    """Execute action using cached selector/bbox"""
    action_type = cached_data['type']
    
    if action_type == 'click':
        selector = cached_data['selector']
        element = nova.page.locator(selector)
        element.click(timeout=5000)
        
    elif action_type == 'scroll':
        x = cached_data['x']
        y = cached_data['y']
        nova.page.evaluate(f"window.scrollTo({x}, {y})")
        
    elif action_type == 'type':
        selector = cached_data['selector']
        element = nova.page.locator(selector)
        
        # Extract text from current instruction (variables already resolved)
        text_to_type = _extract_text_from_instruction(step.instruction)
        element.fill(text_to_type, timeout=5000)


def _extract_text_from_instruction(instruction: str) -> str:
    """Extract text value from typing instruction"""
    import re
    # Match quoted text: "Type 'admin' in username"
    match = re.search(r"['\"]([^'\"]+)['\"]", instruction)
    if match:
        return match.group(1)
    
    # Match unquoted text after type/enter keywords
    words = instruction.lower().split()
    for keyword in ['type', 'enter', 'input']:
        if keyword in words:
            idx = words.index(keyword)
            if idx + 1 < len(words):
                return words[idx + 1]
    
    return ""


def _extract_cache_data(nova: NovaAct, act_result, instruction: str) -> dict:
    """Extract cacheable data from Nova Act execution"""
    
    # Detect action type from instruction
    action_type = _detect_action_type(instruction)
    
    if action_type == 'scroll':
        scroll_pos = nova.page.evaluate("({x: window.scrollX, y: window.scrollY})")
        return {
            "type": "scroll",
            "x": scroll_pos['x'],
            "y": scroll_pos['y'],
            "viewport_height": nova.page.viewport_size['height']
        }
    
    elif action_type in ['click', 'type']:
        # Get the last interacted element
        element_info = nova.page.evaluate("""
            () => {
                const el = document.activeElement;
                if (!el || el === document.body) return null;
                
                // Generate selector
                let selector = '';
                if (el.id) {
                    selector = `#${el.id}`;
                } else if (el.className) {
                    const classes = el.className.split(' ').filter(c => c.length > 0);
                    if (classes.length > 0) {
                        selector = `.${classes[0]}`;
                    }
                } else {
                    selector = el.tagName.toLowerCase();
                }
                
                const rect = el.getBoundingClientRect();
                return {
                    selector: selector,
                    bbox: {
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    }
                };
            }
        """)
        
        if element_info:
            return {
                "type": action_type,
                "selector": element_info['selector'],
                "bbox": element_info['bbox']
            }
    
    return None


def _detect_action_type(instruction: str) -> str:
    """Detect action type from instruction text"""
    instruction_lower = instruction.lower()
    
    if any(keyword in instruction_lower for keyword in ['scroll', 'page down', 'page up']):
        return 'scroll'
    elif any(keyword in instruction_lower for keyword in ['type', 'enter', 'input', 'fill']):
        return 'type'
    else:
        return 'click'  # Default
```

### 4. **Cache Manager Implementation**

**New file: `worker/bbox_cache_manager.py`**

```python
import hashlib
import logging
from typing import Optional, Dict
from urllib.parse import urlparse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class BoundingBoxCacheManager:
    """Manages bounding box cache for Nova Act actions"""
    
    def __init__(self, usecase_id: str, db_client, enabled: bool = True):
        self.usecase_id = usecase_id
        self.db_client = db_client
        self.enabled = enabled
        self.stats = {"hits": 0, "misses": 0}
        
        # Check usecase-level cache settings
        if enabled:
            usecase = db_client.get_usecase(usecase_id)
            self.enabled = usecase.get('cache_enabled', True)
            self.cache_invalidated_at = usecase.get('cache_invalidated_at')
        
        logger.info(f"BoundingBoxCacheManager: enabled={self.enabled}, usecase={usecase_id}")
    
    def generate_key(self, url: str, instruction: str, page_content: str) -> str:
        """Generate cache key from URL, instruction, and page structure"""
        url_pattern = self._normalize_url(url)
        instruction_hash = hashlib.sha256(instruction.encode()).hexdigest()
        structure_hash = self._hash_dom_structure(page_content)
        
        cache_key = hashlib.sha256(
            f"{url_pattern}:{instruction_hash}:{structure_hash}".encode()
        ).hexdigest()
        
        return cache_key
    
    def get(self, cache_key: str) -> Optional[Dict]:
        """Retrieve cached data"""
        if not self.enabled:
            return None
        
        try:
            cache_entry = self.db_client.get_bbox_cache(self.usecase_id, cache_key)
            
            # Check if cache is invalidated
            if cache_entry and self.cache_invalidated_at:
                if cache_entry.get('created_at', '') < self.cache_invalidated_at:
                    logger.info(f"Cache entry outdated, invalidating")
                    self.db_client.delete_bbox_cache(self.usecase_id, cache_key)
                    return None
            
            return cache_entry
        except Exception as e:
            logger.warning(f"Failed to retrieve cache: {e}")
            return None
    
    def store(self, cache_key: str, cache_data: Dict):
        """Store data in cache"""
        if not self.enabled:
            return
        
        try:
            self.db_client.store_bbox_cache(self.usecase_id, cache_key, cache_data)
        except Exception as e:
            logger.warning(f"Failed to store cache: {e}")
    
    def record_hit(self, cache_key: str):
        """Record cache hit"""
        self.stats["hits"] += 1
        try:
            self.db_client.increment_cache_hit(self.usecase_id, cache_key)
        except Exception as e:
            logger.warning(f"Failed to record cache hit: {e}")
    
    def record_miss(self, cache_key: str):
        """Record cache miss"""
        self.stats["misses"] += 1
        try:
            self.db_client.increment_cache_miss(self.usecase_id, cache_key)
            
            # Check success rate and invalidate if too low
            cache_entry = self.db_client.get_bbox_cache(self.usecase_id, cache_key)
            if cache_entry:
                hit_count = cache_entry.get('hit_count', 0)
                miss_count = cache_entry.get('miss_count', 0)
                total = hit_count + miss_count
                
                if total > 5:  # Only check after 5+ attempts
                    success_rate = hit_count / total
                    if success_rate < 0.7:
                        logger.warning(f"Cache entry has low success rate ({success_rate:.2f}), invalidating")
                        self.db_client.delete_bbox_cache(self.usecase_id, cache_key)
        except Exception as e:
            logger.warning(f"Failed to record cache miss: {e}")
    
    def _normalize_url(self, url: str) -> str:
        """Remove query params and fragments from URL"""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    
    def _hash_dom_structure(self, html_content: str) -> str:
        """Hash DOM structure (tags only, not content)"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            structure = self._get_structure(soup)
            return hashlib.md5(structure.encode()).hexdigest()
        except Exception as e:
            logger.warning(f"Failed to hash DOM structure: {e}")
            return hashlib.md5(html_content[:1000].encode()).hexdigest()
    
    def _get_structure(self, element, depth=0, max_depth=5) -> str:
        """Extract structural representation of DOM"""
        if depth > max_depth:
            return ""
        
        if element.name is None:
            return ""
        
        structure = f"<{element.name}>"
        
        for child in element.children:
            if hasattr(child, 'name'):
                structure += self._get_structure(child, depth + 1, max_depth)
        
        return structure
```

### 5. **DynamoDB Client Extensions**

**Add to `dynamodb_client.py`:**

```python
def get_bbox_cache(self, usecase_id: str, cache_key: str) -> Optional[Dict]:
    """Retrieve bbox cache entry"""
    try:
        response = self.table.get_item(
            Key={
                'PK': f'USECASE#{usecase_id}',
                'SK': f'CACHE#{cache_key}'
            }
        )
        return response.get('Item')
    except Exception as e:
        logger.error(f"Failed to get bbox cache: {e}")
        return None

def store_bbox_cache(self, usecase_id: str, cache_key: str, cache_data: Dict):
    """Store bbox cache entry"""
    import time
    from datetime import datetime, timedelta
    
    ttl_days = int(os.getenv('BBOX_CACHE_TTL_DAYS', '30'))
    ttl_timestamp = int((datetime.now() + timedelta(days=ttl_days)).timestamp())
    
    item = {
        'PK': f'USECASE#{usecase_id}',
        'SK': f'CACHE#{cache_key}',
        'action_type': cache_data['type'],
        'cache_data': cache_data,
        'created_at': datetime.now().isoformat(),
        'last_used_at': datetime.now().isoformat(),
        'hit_count': 0,
        'miss_count': 0,
        'TTL': ttl_timestamp
    }
    
    self.table.put_item(Item=item)

def increment_cache_hit(self, usecase_id: str, cache_key: str):
    """Increment cache hit counter"""
    from datetime import datetime
    
    self.table.update_item(
        Key={
            'PK': f'USECASE#{usecase_id}',
            'SK': f'CACHE#{cache_key}'
        },
        UpdateExpression='ADD hit_count :inc SET last_used_at = :now',
        ExpressionAttributeValues={
            ':inc': 1,
            ':now': datetime.now().isoformat()
        }
    )

def increment_cache_miss(self, usecase_id: str, cache_key: str):
    """Increment cache miss counter"""
    self.table.update_item(
        Key={
            'PK': f'USECASE#{usecase_id}',
            'SK': f'CACHE#{cache_key}'
        },
        UpdateExpression='ADD miss_count :inc',
        ExpressionAttributeValues={':inc': 1}
    )

def delete_bbox_cache(self, usecase_id: str, cache_key: str):
    """Delete bbox cache entry"""
    self.table.delete_item(
        Key={
            'PK': f'USECASE#{usecase_id}',
            'SK': f'CACHE#{cache_key}'
        }
    )
```

## Key Design Decisions

### 1. **Cache Scope: Navigation Steps Only**
- **Rationale:** Other step types (validation, assertion) don't interact with Nova Act in a cacheable way
- **Benefit:** Simpler implementation, easier to test

### 2. **Cache Key Components**
- **URL pattern** (normalized): Handles same page across different query params
- **Instruction hash**: Detects when step changes
- **Page structure hash**: Detects when UI changes

### 3. **Graceful Degradation**
- Cache failures fall back to normal Nova Act execution
- No test failures due to cache issues
- Auto-retry mechanism built-in

### 4. **Feature Flag Control**
- Environment variable: `ENABLE_BBOX_CACHE=true/false`
- Per-usecase toggle in DynamoDB
- Easy to disable if issues arise

### 5. **Minimal Code Changes**
- Only 3 files modified: `worker.py`, `navigation_step.py`, `dynamodb_client.py`
- 2 files added: `bbox_cache_manager.py`, cache table schema
- No changes to core worker logic or other step types

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
1. Create `bbox_cache_manager.py`
2. Add DynamoDB methods to `dynamodb_client.py`
3. Add cache table to CDK stack
4. Unit tests for cache manager

### Phase 2: Navigation Step Integration (Week 2)
1. Modify `navigation_step.py` with cache logic
2. Modify `worker.py` to initialize cache manager
3. Integration tests with mock cache

### Phase 3: Testing & Validation (Week 3)
1. End-to-end tests with real Nova Act
2. Performance benchmarking
3. Cache hit rate analysis
4. Edge case testing (stale cache, failures, etc.)

### Phase 4: Deployment & Monitoring (Week 4)
1. Deploy to staging environment
2. Monitor cache metrics
3. Tune cache parameters (TTL, success rate threshold)
4. Production rollout with feature flag

## Success Criteria

- ✅ 40%+ cache hit rate after 1 week
- ✅ 30%+ execution time reduction on cached runs
- ✅ <1% cache-related test failures
- ✅ Zero impact on non-cached executions
- ✅ Easy to enable/disable via feature flag

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Stale cache causes failures | Auto-retry with Nova Act, success rate monitoring |
| Cache overhead slows first run | Async cache storage, minimal extraction logic |
| Storage costs increase | 30-day TTL, auto-cleanup of low-success entries |
| Complex debugging | Detailed logging, cache hit/miss tracking |

## Open Questions for Discussion

1. **Cache Extraction Strategy**: How do we reliably extract the selector from Nova Act's execution? Should we:
   - Use `document.activeElement` (current approach)
   - Parse Nova Act's internal logs/traces
   - Use Playwright's accessibility tree
   - Combination of methods?

2. **Typing Action Caching**: Should we cache typing actions at all, or only clicks/scrolls?
   - Pro: Faster field location
   - Con: More complex text extraction logic

3. **Cache Warming**: Should we pre-populate cache from previous executions?
   - Pro: Immediate performance gains
   - Con: More complex implementation

4. **Cross-Usecase Sharing**: Should identical steps across different usecases share cache?
   - Pro: Better cache hit rates
   - Con: More complex cache key generation

## Next Steps

1. **Review this strategy** with the team
2. **Answer open questions** above
3. **Create detailed implementation tickets** for Phase 1
4. **Set up monitoring/metrics** for cache performance
5. **Begin Phase 1 implementation**
