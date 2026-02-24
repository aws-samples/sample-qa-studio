# Shared Browser with Session-Based Execution - Implementation Plan

## Overview

This document outlines the implementation plan for migrating from per-execution browser creation to a shared browser architecture with session-based execution. This change is necessary because VPC attachment for browser creation takes too long, making per-execution browser creation impractical.

## Architecture Changes

### Current Architecture (Problem)
1. ECS task starts for each execution
2. Worker creates a new browser with VPC attachment (SLOW - ~30-60 seconds)
3. Worker runs execution
4. Worker deletes browser
5. Recordings saved directly to `{usecase_id}/{execution_id}/recording/`

### New Architecture (Solution)
1. **CDK Deployment**: Create browser once with VPC configuration → get `browser_id`
2. **Lambda Environment**: Pass `browser_id` to execute_usecase and start_wizard Lambdas
3. **ECS Task Start**: Lambda passes `browser_id` to ECS task as environment variable
4. **Worker Execution**: 
   - Worker reads `browser_id` from environment
   - Creates session (FAST - ~1-2 seconds) instead of browser
   - Runs execution using session
   - Copies recordings from temp location to final location
   - Stops session (browser persists for next execution)

## Key Concepts

### Browser vs Session
- **Browser**: Long-lived resource with VPC attachment, created at deployment time
- **Session**: Short-lived execution context within a browser, created per execution
- **Benefit**: Session creation is ~30x faster than browser creation

### Recording Strategy
- Browser is created with a generic S3 prefix: `recordings/temp/`
- Each session writes to: `recordings/temp/{browser_id}/{session_id}/`
- After execution, worker copies to: `{usecase_id}/{execution_id}/recording/`
- Temp recordings are cleaned up after successful copy

## Implementation Components

### 1. CDK Custom Resource for Browser Creation

**File**: `lib/browser-provisioner.ts` (new file)

Create a CDK Custom Resource that:
- Creates browser during stack deployment
- Configures VPC networking (subnets, security groups)
- Sets generic S3 recording location
- Returns `browser_id` as CloudFormation output
- Handles browser deletion on stack deletion
- Handles browser recreation on configuration changes

**Key Considerations**:
- Browser name: `nova-act-qa-studio-shared-browser`
- Recording prefix: `recordings/temp/`
- Idempotency: Use stack name or unique identifier in browser name
- Error handling: What if browser creation fails during deployment?

### 2. Worker Stack Updates

**File**: `lib/worker-stack.ts`

Changes needed:
1. Import and instantiate browser provisioner custom resource
2. Get `browser_id` from custom resource output
3. Add `BROWSER_ID` environment variable to `executeUsecaseLambda`
4. Add `BROWSER_ID` environment variable to `startWizardLambda`
5. Keep existing VPC environment variables for backward compatibility

**Environment Variables**:
```typescript
executeUsecaseLambda.addEnvironment('BROWSER_ID', browserProvisioner.browserId);
executeUsecaseLambda.addEnvironment('VPC_PRIVATE_SUBNET_IDS', vpcConfig.subnetIds);
executeUsecaseLambda.addEnvironment('BROWSER_SECURITY_GROUP_ID', vpcConfig.securityGroupId);
```

### 3. Execute Usecase Lambda Updates

**File**: `lambda/cmd/execute_usecase/main.go`

Changes needed:
1. Read `BROWSER_ID` from environment variables
2. Add `BROWSER_ID` to ECS task environment overrides
3. Keep existing VPC environment variable propagation

**Code Changes**:
```go
// Read browser_id
browserID := os.Getenv("BROWSER_ID")

// Add to environment overrides
if browserID != "" {
    environmentOverrides = append(environmentOverrides, &ecs.KeyValuePair{
        Name:  aws.String("BROWSER_ID"),
        Value: aws.String(browserID),
    })
}
```

### 4. Start Wizard Lambda Updates

**File**: `lambda/cmd/start_wizard_session/main.go`

Same changes as execute_usecase Lambda:
1. Read `BROWSER_ID` from environment
2. Pass to ECS task environment overrides

### 5. Browser Module Refactoring

**File**: `worker/browser.py`

Major refactoring needed:

**Current Functions**:
- `create_browser()` - Creates new browser (calls control plane API)
- `delete_browser()` - Deletes browser (calls control plane API)
- `start_browser()` - Creates session AND returns BrowserClient (confusing name!)

**Analysis**:
The current `start_browser()` function actually:
1. Creates a BrowserClient
2. Calls `browser_client.start()` to create a session
3. Returns the BrowserClient

This is confusing because it's not just "starting" a browser, it's creating a session.

**New Functions** (cleaner separation of concerns):
- `create_browser()` - ONLY used by CDK custom resource for browser provisioning
- `delete_browser()` - ONLY used by CDK custom resource for browser cleanup
- `start_session()` - NEW: Creates session, returns (browser_client, session_id)
- `stop_session()` - NEW: Stops session using browser_client

**Simplified API**:
```python
def start_session(browser_id: str, session_name: str, region: str) -> tuple[BrowserClient, str]:
    """
    Create a new session in an existing browser.
    
    Args:
        browser_id: ID of existing browser
        session_name: Name for the session (use execution_id)
        region: AWS region
        
    Returns:
        (browser_client, session_id): Tuple of BrowserClient and session ID
    """
    browser_client = BrowserClient(region)
    session_id = browser_client.start(
        identifier=browser_id,
        name=session_name
    )
    return browser_client, session_id

def stop_session(browser_client: BrowserClient):
    """
    Stop a session without deleting the browser.
    
    Args:
        browser_client: BrowserClient instance to stop
    """
    browser_client.stop()
```

**Key Changes**:
- Remove `start_browser()` - it's confusing and does too much
- `start_session()` replaces it with clearer naming
- `stop_session()` is simple - just calls browser_client.stop()
- `create_browser()` and `delete_browser()` only used by CDK provisioning

**Migration Path**:
- Worker code changes from: `browser = start_browser(browser_id, execution_id, region)`
- To: `browser_client, session_id = start_session(browser_id, execution_id, region)`

### 6. Worker Module Updates

**File**: `worker/worker.py`

Changes needed in `main_batch()`:

**Current Code**:
```python
browser_id = create_browser(...)
browser = start_browser(browser_id, execution_id, region)
# ... execution ...
delete_browser(browser_id, region)
```

**New Code**:
```python
# Read browser_id from environment
browser_id = os.getenv('BROWSER_ID')

if not browser_id:
    logger.error("BROWSER_ID environment variable is required")
    return False

# Create session (replaces create_browser + start_browser)
browser_client, session_id = start_session(browser_id, execution_id, region)

# Get WebSocket URL and headers for NovaAct
ws_url, headers = browser_client.generate_ws_headers()
live_view_url = browser_client.generate_live_view_url()

# Store session_id in DynamoDB
db_client.update_execution_browser_session(usecase_id, execution_id, session_id)

# ... execution with NovaAct using ws_url and headers ...

# Copy recordings from temp to final location
copy_recordings_to_execution_location(
    s3_bucket_name,
    f"recordings/temp/{browser_id}/{session_id}/",
    f"{usecase_id}/{execution_id}/recording/"
)

# Stop session (don't delete browser)
stop_session(browser_client)
```

**New Function Needed**:
```python
def copy_recordings_to_execution_location(bucket: str, source_prefix: str, target_prefix: str):
    """
    Copy recordings from temp location to execution-specific location.
    
    Args:
        bucket: S3 bucket name
        source_prefix: Source prefix (temp location)
        target_prefix: Target prefix (execution location)
    """
    s3_client = boto3.client('s3')
    
    # List objects in source
    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=source_prefix)
    
    for page in pages:
        if 'Contents' not in page:
            continue
            
        for obj in page['Contents']:
            source_key = obj['Key']
            # Calculate target key
            relative_key = source_key[len(source_prefix):]
            target_key = target_prefix + relative_key
            
            # Copy object
            copy_source = {'Bucket': bucket, 'Key': source_key}
            s3_client.copy_object(
                CopySource=copy_source,
                Bucket=bucket,
                Key=target_key
            )
            
            # Delete source after successful copy
            s3_client.delete_object(Bucket=bucket, Key=source_key)
    
    logger.info(f"Copied recordings from {source_prefix} to {target_prefix}")
```

### 7. Wizard Worker Updates

**File**: `worker/wizard_worker.py`

Similar changes to worker.py:

**Changes in `main()`**:
1. Read `BROWSER_ID` from environment instead of creating browser
2. Create session instead of browser
3. Store session_id in DynamoDB
4. On restart command: stop old session, create new session (don't recreate browser)
5. On terminate: stop session, copy recordings, cleanup
6. Remove browser deletion logic

**Key Differences from Batch Mode**:
- Wizard maintains session for longer duration
- Restart command creates new session in same browser
- Need to handle session timeout/expiration

### 8. DynamoDB Schema Updates

**File**: `worker/dynamodb_client.py`

New method needed:
```python
def update_execution_browser_session(self, usecase_id: str, execution_id: str, session_id: str):
    """
    Store browser session_id associated with execution.
    
    Args:
        usecase_id: Use case ID
        execution_id: Execution ID
        session_id: Browser session ID
    """
    pass
```

This allows tracking which session belongs to which execution for debugging and monitoring.

### 9. Error Handling & Edge Cases

**Browser Unavailable**:
- What if browser_id doesn't exist (deleted manually)?
- Fallback: Create new browser? Fail gracefully?
- Solution: Add browser health check before session creation

**Session Creation Failure**:
- Retry logic with exponential backoff
- Max retries: 3
- Log detailed error information
- Update execution status to failed

**Recording Copy Failure**:
- Retry S3 copy operations
- Don't delete source until copy confirmed
- Keep temp recordings for manual recovery
- Alert/log for investigation

**Concurrent Executions**:
- Can same browser handle multiple concurrent sessions?
- If yes: No additional logic needed
- If no: Need session queue or browser pool

**Browser State Accumulation**:
- Sessions should be isolated, but browser might accumulate state
- Consider: Periodic browser recreation (e.g., daily)
- Monitor: Browser memory/performance metrics

### 10. Backward Compatibility

**PUBLIC Mode Support**:
- If `BROWSER_ID` is not set, fall back to old behavior
- Create browser per execution (PUBLIC mode)
- No recording copy needed

**Migration Strategy**:
- Deploy new code with backward compatibility
- Test with VPC configuration
- Gradually migrate all environments
- Remove old code path after validation

## Implementation Phases

### Phase 1: CDK Browser Provisioning
1. Create browser provisioner custom resource
2. Update worker-stack to create browser at deployment
3. Pass browser_id to Lambdas
4. Test browser creation/deletion during stack operations

### Phase 2: Lambda Updates
1. Update execute_usecase Lambda to read and pass BROWSER_ID
2. Update start_wizard Lambda to read and pass BROWSER_ID
3. Test Lambda environment variable propagation

### Phase 3: Browser Module Refactoring
1. Implement start_session() function
2. Implement stop_session() function
3. Update start_browser() to work with sessions
4. Add comprehensive error handling
5. Unit test new functions

### Phase 4: Worker Updates
1. Update worker.py to use browser_id and sessions
2. Implement recording copy logic
3. Update error handling
4. Test batch execution flow

### Phase 5: Wizard Worker Updates
1. Update wizard_worker.py to use browser_id and sessions
2. Update restart logic
3. Update terminate logic
4. Test wizard execution flow

### Phase 6: Testing & Validation
1. Test browser creation during deployment
2. Test session creation and execution
3. Test recording copy functionality
4. Test error scenarios
5. Test concurrent executions
6. Performance testing (compare old vs new)

### Phase 7: Monitoring & Cleanup
1. Add CloudWatch metrics for session operations
2. Add logging for debugging
3. Document operational procedures
4. Remove old code paths
5. Update documentation

## Open Questions

1. **Browser Lifecycle Management**:
   - How often should we recreate the browser?
   - Should we have a separate process to monitor browser health?
   - What triggers browser recreation?

2. **Multi-Region Support**:
   - Do we need browsers in multiple regions?
   - How do we handle region-specific browser_ids?

3. **Browser Pool**:
   - Should we create multiple browsers for better concurrency?
   - How many browsers per stack?
   - Load balancing strategy?

4. **Cost Optimization**:
   - Browser runs 24/7 vs on-demand
   - Cost comparison: always-on browser vs per-execution creation
   - Should browser be stopped during idle periods?

5. **Disaster Recovery**:
   - What if browser becomes unhealthy?
   - Automatic recreation vs manual intervention?
   - How to handle browser recreation without downtime?

6. **Session Limits**:
   - Is there a limit to concurrent sessions per browser?
   - Is there a limit to total sessions per browser?
   - Do we need session cleanup/garbage collection?

## Success Criteria

1. **Performance**: Session creation < 5 seconds (vs 30-60 seconds for browser creation)
2. **Reliability**: 99.9% session creation success rate
3. **Recording Integrity**: 100% of recordings successfully copied to final location
4. **Backward Compatibility**: PUBLIC mode still works without BROWSER_ID
5. **Error Handling**: All error scenarios handled gracefully with clear logging
6. **Monitoring**: CloudWatch metrics for session operations and failures

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Browser becomes unhealthy | High - all executions fail | Health checks, automatic recreation |
| Recording copy fails | Medium - data loss | Retry logic, keep temp recordings |
| Session limit reached | Medium - executions blocked | Monitor session count, cleanup old sessions |
| Browser state accumulation | Low - performance degradation | Periodic browser recreation |
| Concurrent session conflicts | Low - execution failures | Test concurrent execution limits |

## Next Steps

1. Review this implementation plan
2. Clarify open questions
3. Create detailed task list
4. Begin Phase 1 implementation
5. Iterate based on testing results
