# Bounding Box Cache - Design Complete ✅

## Summary

We've designed a complete caching system for Nova Act navigation steps to reduce test execution time by 40-60%.

## Key Design Decisions

### 1. Cache Storage
- **Location**: STEP records (single-table design)
- **Fields**: `cached_steps` (JSON string), `cache_last_updated` (ISO timestamp)
- **Size**: ~2-3 KB per cache (well within 400 KB DynamoDB limit)

### 2. Cache Key
- **Strategy**: Instruction-based (stored in STEP record)
- **Benefits**: Stable, self-documenting, natural invalidation

### 3. Per-Usecase Toggle
- **Field**: `enable_cache` boolean in USECASE metadata
- **Default**: False (opt-in for safety)
- **UI**: Cloudscape Toggle component in create/update forms

### 4. Event-Driven Building
- **Pattern**: EventBridge with `usecase.execution.completed` event
- **Benefits**: Decoupled, async, batch processing, future-proof
- **S3 Lookup**: List objects by prefix, match by `act_id` (safe for truncated instructions)

### 5. Complete Action List
- **Cache**: agentClick, agentHover, agentScroll, agentType, goToUrl (5 actions)
- **Skip**: think, return, throw, wait, waitForPageToSettle, takeObservation (6 actions)

## Documents Created

1. ✅ `bbox-cache-implementation-plan.md` - Complete implementation plan with 3 phases
2. ✅ `nova-act-actions-reference.md` - Complete list of all Nova Act actions
3. ✅ `cache-builder-s3-lookup.md` - S3 file lookup strategy
4. ✅ `cache-execution-strategy.md` - How to execute cached steps
5. ✅ `CRITICAL-FINDINGS.md` - Key discoveries (multi-step responses, bbox format)

## Implementation Phases

### Phase 1: Cache Building (Event-Driven)
- Add `enable_cache` to USECASE metadata
- Add `cached_steps`, `cache_last_updated` to STEP records
- Create Cache Builder Lambda (EventBridge trigger)
- Update Worker to emit `usecase.execution.completed` event
- Create parser module for Nova Act responses
- Update create/update usecase endpoints
- Add UI toggles in CreateUsecase and UsecaseSettings

### Phase 2: Cache Execution
- Update execute_usecase endpoint to copy cache to EXECUTION_STEP
- Update Worker to check and execute cached steps
- Create cache executor module (Playwright API)
- Update list_steps endpoint to return cache data
- Add cache status indicators in UI

### Phase 3: Testing & Validation
- Unit tests (70% coverage target)
- Integration tests
- E2E tests with qa-studio

## API Changes

### Endpoints Modified
- `POST /usecases` - Accept `enableCache` (default: false)
- `PATCH /usecases/{id}` - Accept `enableCache`
- `GET /usecases/{id}` - Return `enableCache`
- `GET /steps/{usecase_id}` - Return `cachedSteps`, `cacheLastUpdated`

### New Lambda
- `build_step_cache.py` - EventBridge consumer

### Infrastructure
- EventBridge rule: `usecase.execution.completed` → Cache Builder Lambda
- No new DynamoDB tables (single-table design)
- No new GSIs

## Compliance Checklist

- ✅ Single-table design (01_dynamodb.md)
- ✅ API-first with camelCase JSON (02_api-design.md)
- ✅ OAuth scopes validation needed (03_security.md)
- ✅ Cloudscape components (04_frontend.md)
- ✅ Well-tested code plan (05_coding.md)
- ✅ CDK deployment (06_deployment.md)
- ✅ Read all steering docs (07_learning.md)

## Performance Target

- **Current**: 2-5 seconds per Nova Act call
- **Cached**: 100-300ms per step
- **Speedup**: 10-50x per cached instruction
- **Overall**: 40-60% reduction in total test execution time

## Rollout Strategy

1. Deploy Phase 1 (cache building only) - no user impact
2. Enable Phase 2 for opt-in usecases - gradual rollout
3. Monitor performance and reliability
4. Iterate based on feedback

## Next Steps

**Ready for implementation when you are!** All design decisions documented and approved.

## Questions Resolved

1. ✅ Complete list of Nova Act actions - Found in browser.py
2. ✅ Cache storage location - STEP records (single-table)
3. ✅ Cache key strategy - Instruction-based
4. ✅ Event-driven vs inline - EventBridge pattern
5. ✅ S3 file lookup - List by prefix, match by act_id
6. ✅ Per-usecase toggle - enable_cache field
7. ✅ Success/fail counters - Not needed (minimal approach)
8. ✅ Default value - False (opt-in)
9. ✅ UI component - Cloudscape Toggle
10. ✅ Both create and update forms - Yes, both updated
