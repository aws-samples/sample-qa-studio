# Work Package 1a: Execution Record & Trigger Type - Design Document

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP1a - Execution Record & Trigger Type
- **Version**: 1.0
- **Status**: Design Phase
- **Dependencies**: None

---

## Design Overview

This workpackage adds a `trigger_type` field to execution records to distinguish between manual UI executions, scheduled executions, and CI/CD runner executions. When `trigger_type="ci_runner"`, the execution record is created but no ECS task is spawned, allowing the CI/CD runner to execute tests locally.

### Key Design Principles
1. **Backward Compatibility**: Existing executions default to "manual" trigger type
2. **Minimal Changes**: Leverage existing execution flow, only add conditional ECS task creation
3. **Query Efficiency**: No new GSI/LSI required, trigger_type is a simple attribute
4. **Clear Separation**: CI/CD runner executions are clearly identifiable in the system

---

## Current System Analysis

### Existing Execution Flow

**File**: `lambdas/endpoints/execute_usecase.py`

**Current Trigger Types**:
- `OnDemand` - Queues execution to SQS for worker processing
- `Scheduled` - Directly spawns ECS task (used by EventBridge Scheduler)
- `OnDemandHeadless` - Directly spawns ECS task (used by UI for immediate execution)

**Current Execution Record Structure**:
```python
{
    'pk': 'USECASE_EXECUTION#{usecase_id}',
    'sk': 'EXECUTION#{execution_id}',
    'starting_url': 'string',
    'status': 'pending',
    'created_at': 'ISO8601 timestamp',
    'trigger_type': 'OnDemand | Scheduled | OnDemandHeadless',  # Existing field!
    'executing_region': 'string',
    'model_id': 'string',
    'suite_execution_id': 'string',  # Optional
    'suite_id': 'string'  # Optional
}
```

**Key Finding**: The `trigger_type` field already exists! It's currently used to determine execution method (SQS queue vs direct ECS task).

---

## Design Decision: Extend Existing trigger_type

### Option 1: Add New Field (Original Plan)
Add a separate `execution_source` field to track manual/scheduled/ci_runner.

**Pros**:
- Clear separation of concerns
- Doesn't affect existing trigger logic

**Cons**:
- Redundant with existing trigger_type
- More fields to maintain
- Confusing to have both trigger_type and execution_source

### Option 2: Extend Existing trigger_type (SELECTED)
Add `ci_runner` as a new value for the existing `trigger_type` field.

**Pros**:
- Reuses existing field and logic
- Simpler data model
- Consistent with current architecture
- Less code changes

**Cons**:
- Need to ensure backward compatibility
- Need to update any code that validates trigger_type values

**Decision**: Extend existing `trigger_type` field with new value `ci_runner`.

---

## Detailed Design

### 1. DynamoDB Schema Changes

**Execution Record** (no schema change, just new enum value):
```python
{
    'pk': 'USECASE_EXECUTION#{usecase_id}',
    'sk': 'EXECUTION#{execution_id}',
    'trigger_type': 'OnDemand | Scheduled | OnDemandHeadless | ci_runner',  # NEW VALUE
    # ... other fields unchanged
}
```

**Migration**: No migration needed. Existing records remain valid.

### 2. Lambda Function Changes

**File**: `lambdas/endpoints/execute_usecase.py`

**Current Logic**:
```python
if trigger_type == 'OnDemand':
    # Send to SQS queue
    sqs.send_message(...)
elif trigger_type in ['Scheduled', 'OnDemandHeadless']:
    # Start ECS task directly
    ecs.run_task(...)
else:
    return error(400, 'Invalid trigger type')
```

**New Logic**:
```python
if trigger_type == 'OnDemand':
    # Send to SQS queue
    sqs.send_message(...)
elif trigger_type in ['Scheduled', 'OnDemandHeadless']:
    # Start ECS task directly
    ecs.run_task(...)
elif trigger_type == 'ci_runner':
    # Create execution record only, no ECS task
    # Return success immediately
    return create_response(200, {
        'status': 'execution created',
        'usecaseId': usecase_id,
        'executionId': execution_id
    })
else:
    return error(400, 'Invalid trigger type')
```

### 3. API Changes

**Endpoint**: `POST /usecase/{id}/execute`

**Query Parameters** (existing):
- `trigger-type`: `OnDemand` | `Scheduled` | `OnDemandHeadless` | `ci_runner` (NEW)
- `suite-execution-id`: Optional, for suite executions
- `suite-id`: Optional, for suite executions

**Request Body**: None (existing behavior)

**Response for ci_runner**:
```json
{
    "status": "execution created",
    "usecaseId": "uuid",
    "executionId": "uuid"
}
```

**Response for other trigger types**: Unchanged

### 4. New API Endpoint: Update Step Status

**Endpoint**: `PATCH /usecase/{id}/executions/{executionId}/steps/{stepId}/status`

**Purpose**: Allow CI/CD runner to update individual step status during execution

**Request Body**:
```json
{
    "status": "pending" | "running" | "completed" | "failed" | "skipped",
    "started_at": "ISO8601 timestamp",  // Optional
    "completed_at": "ISO8601 timestamp",  // Optional
    "error_message": "string"  // Optional, for failed steps
}
```

**Response**:
```json
{
    "success": true,
    "step_id": "uuid",
    "status": "completed"
}
```

**Error Responses**:
- `400`: Invalid status value
- `404`: Execution or step not found
- `403`: Insufficient permissions
- `500`: Internal server error

**OAuth Scopes**: `api/execution.write`

### 5. Execution Flow for ci_runner

```
1. API Gateway receives POST /usecase/{id}/execute?trigger-type=ci_runner
2. Lambda validates authentication (OAuth M2M token)
3. Lambda loads usecase definition
4. Lambda creates execution record with trigger_type='ci_runner'
5. Lambda copies steps, hooks, variables, headers to execution
6. Lambda publishes 'pending' status event to EventBridge
7. Lambda returns success response (no ECS task created)
8. CI/CD runner receives execution_id
9. CI/CD runner executes test locally with Nova Act SDK
10. CI/CD runner updates execution status via API
```

### 5. Code Changes Required

**File**: `lambdas/endpoints/execute_usecase.py`

**Changes**:
1. Add `ci_runner` to valid trigger types
2. Add conditional logic to skip ECS task creation for `ci_runner`
3. Return appropriate response for `ci_runner` trigger
4. Update docstring to document new trigger type

**Pseudocode**:
```python
def handler(event, context):
    # ... existing authentication and validation ...
    
    trigger_type = query_params.get('trigger-type', 'OnDemand')
    
    # Validate trigger type
    valid_trigger_types = ['OnDemand', 'Scheduled', 'OnDemandHeadless', 'ci_runner']
    if trigger_type not in valid_trigger_types:
        return create_response(400, {'error': f'Invalid trigger type: {trigger_type}'})
    
    # ... existing execution record creation ...
    
    # Create execution record (same for all trigger types)
    execution_item = {
        'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
        'sk': {'S': f'EXECUTION#{execution_id}'},
        'trigger_type': {'S': trigger_type},  # Store the trigger type
        # ... other fields ...
    }
    dynamodb.put_item(TableName=table_name, Item=execution_item)
    
    # Copy steps, hooks, variables, headers (same for all trigger types)
    # ... existing copy logic ...
    
    # Handle different trigger types
    if trigger_type == 'OnDemand':
        # Send to SQS queue
        sqs.send_message(...)
        return create_response(200, {
            'status': 'usecase queued',
            'usecaseId': usecase_id
        })
    
    elif trigger_type in ['Scheduled', 'OnDemandHeadless']:
        # Start ECS task
        task_result = ecs.run_task(...)
        # ... existing ECS task handling ...
        return create_response(200, {
            'status': 'task started',
            'usecaseId': usecase_id,
            'executionId': execution_id,
            'taskArn': task_arn,
            'taskId': task_id,
            'cloudWatchLogsUrl': cloudwatch_url
        })
    
    elif trigger_type == 'ci_runner':
        # No ECS task creation, just return execution ID
        print(f'CI/CD runner execution created: {execution_id}')
        return create_response(200, {
            'status': 'execution created',
            'usecaseId': usecase_id,
            'executionId': execution_id
        })
    
    else:
        # Should never reach here due to validation above
        return create_response(400, {'error': f'Invalid trigger type: {trigger_type}'})
```

### 6. UI Changes (Optional for WP1a)

**Display trigger type in execution list**:
- Show badge/icon for different trigger types
- Filter executions by trigger type
- Color coding: manual (blue), scheduled (green), ci_runner (purple)

**Note**: UI changes are optional for WP1a and can be deferred to a later workpackage.

---

## Security Considerations

### Authentication
- CI/CD runner uses OAuth M2M tokens (client credentials flow)
- Existing `allow_m2m_token()` function already supports M2M authentication
- No changes needed to authentication logic

### Authorization
- OAuth scopes required: `api/execution.write`
- Existing scope validation applies to ci_runner trigger
- No new scopes needed for WP1a

### Validation
- Validate trigger_type is one of allowed values
- Prevent unauthorized trigger type usage (if needed in future)

---

## Testing Strategy

### Unit Tests

**File**: `lambdas/endpoints/test_execute_usecase.py` (new tests)

**Test Cases**:
1. `test_execute_usecase_with_ci_runner_trigger`
   - Verify execution record created
   - Verify no ECS task spawned
   - Verify correct response returned

2. `test_ci_runner_trigger_copies_steps_hooks_variables`
   - Verify all data copied to execution
   - Verify same behavior as other trigger types

3. `test_ci_runner_trigger_with_suite_execution_id`
   - Verify suite_execution_id stored correctly
   - Verify suite_id stored correctly

4. `test_invalid_trigger_type_returns_400`
   - Verify validation works
   - Verify error message is clear

5. `test_backward_compatibility_default_trigger_type`
   - Verify default is 'OnDemand' when not specified
   - Verify existing behavior unchanged

### Integration Tests

**Test Scenarios**:
1. Create execution with ci_runner trigger via API
2. Verify execution record exists in DynamoDB
3. Verify no ECS task was created (check ECS API)
4. Verify EventBridge event published
5. Query execution by ID and verify trigger_type field

### Manual Testing

**Steps**:
1. Deploy updated Lambda
2. Call API with `?trigger-type=ci_runner`
3. Check DynamoDB for execution record
4. Check ECS console - no task should be running
5. Check CloudWatch Logs for Lambda execution
6. Verify response contains execution_id

---

## Rollout Plan

### Phase 1: Deploy Lambda Changes
1. Update `execute_usecase` Lambda function
2. Deploy to development environment
3. Run integration tests
4. Verify no regressions for existing trigger types

### Phase 2: Validation
1. Test ci_runner trigger in development
2. Verify execution records created correctly
3. Verify no ECS tasks spawned
4. Monitor CloudWatch Logs for errors

### Phase 3: Production Deployment
1. Deploy to production
2. Monitor for errors
3. Verify existing executions continue to work
4. Enable ci_runner trigger for CI/CD runner (WP2)

---

## Monitoring & Observability

### CloudWatch Metrics
- Count of executions by trigger_type
- Success/failure rate by trigger_type
- Execution creation latency

### CloudWatch Logs
- Log trigger_type for each execution
- Log when ci_runner execution is created
- Log when ECS task is skipped

### EventBridge Events
- Existing execution status events include trigger_type
- No changes needed to event structure

---

## Backward Compatibility

### Existing Executions
- Existing execution records without explicit trigger_type will default to 'OnDemand'
- No migration needed
- Existing queries continue to work

### Existing Code
- All existing trigger types continue to work
- No breaking changes to API
- Response format unchanged for existing trigger types

### Existing UI
- UI can display trigger_type if present
- UI defaults to showing "manual" if trigger_type is missing
- No UI changes required for WP1a

---

## Performance Considerations

### Execution Creation
- ci_runner trigger is faster than other triggers (no ECS task creation)
- Reduces AWS costs (no ECS task for CI/CD executions)
- Reduces execution latency (no ECS task startup time)

### DynamoDB
- No additional queries needed
- No new indexes required
- Same query patterns as existing executions

---

## Error Handling

### Invalid Trigger Type
```python
if trigger_type not in valid_trigger_types:
    return create_response(400, {
        'error': f'Invalid trigger type: {trigger_type}. Valid values: {", ".join(valid_trigger_types)}'
    })
```

### Execution Record Creation Failure
- Same error handling as existing trigger types
- Log error to CloudWatch
- Return 500 error to client

### EventBridge Event Failure
- Log warning but don't fail execution
- Existing behavior (non-blocking)

---

## Dependencies

### Internal Dependencies
- None (WP1a is independent)

### External Dependencies
- DynamoDB table (existing)
- EventBridge (existing)
- CloudWatch Logs (existing)

### Downstream Dependencies
- WP1b (Test Suite Execution Endpoint) will use ci_runner trigger
- WP2 (Runner Core) will call this endpoint with ci_runner trigger

---

## Success Criteria

- [ ] Lambda function accepts `ci_runner` trigger type
- [ ] Execution record created with trigger_type='ci_runner'
- [ ] No ECS task spawned for ci_runner trigger
- [ ] All existing trigger types continue to work
- [ ] Unit tests pass (≥70% coverage)
- [ ] Integration tests pass
- [ ] No performance regression
- [ ] Backward compatible with existing executions
- [ ] Documentation updated

---

## Open Questions

1. **Should we add rate limiting for ci_runner executions?**
   - Decision: Defer to WP1b (suite execution endpoint)
   - Rationale: Rate limiting should be at suite level, not individual execution

2. **Should we validate OAuth client has specific scopes for ci_runner?**
   - Decision: No, use existing `api/execution.write` scope
   - Rationale: Keep authorization simple for WP1a

3. **Should we add a separate status for ci_runner executions?**
   - Decision: No, use existing status values (pending, running, completed, failed)
   - Rationale: Status lifecycle is the same regardless of trigger type

---

## Future Enhancements (Out of Scope)

- UI filtering by trigger_type
- Analytics dashboard showing execution breakdown by trigger type
- Separate rate limits for different trigger types
- Webhook notifications for ci_runner executions
- Audit logging for ci_runner executions

---

## References

- [CI/CD Runner Design Document](../../design/qa-studio-ci-runner.md)
- [WP1a Requirements](./requirements.md)
- [Existing execute_usecase Lambda](../../../lambdas/endpoints/execute_usecase.py)
- [DynamoDB Steering Rules](../../../.kiro/steering/01_dynamodb.md)
- [API Design Steering Rules](../../../.kiro/steering/02_api-design.md)
