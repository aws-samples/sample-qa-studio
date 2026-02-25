# Work Package 1a: Execution Record & Trigger Type

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP1a - Execution Record & Trigger Type
- **Estimated Duration**: 3 days
- **Dependencies**: None
- **Status**: Not Started

---

## Overview

Modify the execution record data model and `execute_usecase` Lambda to support a new `trigger_type` field that distinguishes between manual, scheduled, and CI/CD runner executions. When trigger_type is "ci_runner", skip ECS task creation.

---

## User Stories

### US1: As a platform backend, I need to track the source of test executions
**Acceptance Criteria**:
- Execution records include a `trigger_type` field
- Valid values are: "manual", "scheduled", "ci_runner"
- Default value is "manual" for backward compatibility
- Field is stored in DynamoDB execution records

### US2: As a CI/CD runner, I need to create execution records without spawning ECS tasks
**Acceptance Criteria**:
- `execute_usecase` Lambda accepts `trigger_type` parameter in request body
- When `trigger_type="ci_runner"`, execution record is created but no ECS task is spawned
- When `trigger_type="manual"` or `trigger_type="scheduled"`, existing ECS task creation logic runs
- Execution record includes all necessary data (steps, hooks, variables, headers) regardless of trigger type

### US3: As a developer, I need to query executions by trigger type
**Acceptance Criteria**:
- Execution records can be filtered by trigger_type
- UI can display execution source badge based on trigger_type
- API returns trigger_type in execution record responses

### US4: As a CI/CD runner, I need to update individual step status during execution
**Acceptance Criteria**:
- API endpoint accepts step status updates
- Step status can be: "pending", "running", "completed", "failed", "skipped"
- Step execution time is tracked (started_at, completed_at)
- Error messages can be stored for failed steps
- Updates are validated (step must exist, execution must exist)

---

## Technical Requirements

### Data Model Changes

**Execution Record (DynamoDB)**:
```python
{
    "PK": "USECASE#{usecase_id}",
    "SK": "EXECUTION#{execution_id}",
    "trigger_type": "manual" | "scheduled" | "ci_runner",  # NEW FIELD
    "status": "pending" | "running" | "completed" | "failed",
    "created_at": "ISO8601 timestamp",
    "started_at": "ISO8601 timestamp",
    "completed_at": "ISO8601 timestamp",
    "starting_url": "string",
    "region": "string",
    "model_id": "string",
    # ... existing fields
}
```

### Lambda Modifications

**`execute_usecase` Lambda**:
- Accept `trigger_type` in request body (optional, defaults to "manual")
- Validate trigger_type is one of: "manual", "scheduled", "ci_runner"
- Store trigger_type in execution record
- Add conditional logic: if trigger_type == "ci_runner", skip ECS task creation
- Preserve all existing functionality for "manual" and "scheduled" triggers

### API Changes

**Existing Endpoint**: `POST /usecase/{id}/execute`

**Modified Request Body**:
```json
{
  "trigger_type": "manual" | "scheduled" | "ci_runner",  // Optional, defaults to "manual"
  "region": "string",  // Optional
  "model_id": "string"  // Optional
}
```

**Response** (unchanged):
```json
{
  "execution_id": "uuid",
  "status": "pending",
  "created_at": "ISO8601 timestamp"
}
```

### New API Endpoint: Update Step Status

**Endpoint**: `PATCH /usecase/{id}/executions/{executionId}/steps/{stepId}/status`

**Request Body**:
```json
{
  "status": "pending" | "running" | "completed" | "failed" | "skipped",
  "started_at": "ISO8601 timestamp",  // Optional, set when status changes to "running"
  "completed_at": "ISO8601 timestamp",  // Optional, set when status changes to "completed" or "failed"
  "error_message": "string"  // Optional, only for "failed" status
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
- `400`: Invalid status value or missing required fields
- `404`: Execution or step not found
- `403`: Insufficient permissions (missing `api/execution.write` scope)
- `500`: Internal server error

---

## Implementation Details

### DynamoDB Schema Update
- Add `trigger_type` attribute to execution records
- No GSI/LSI changes required (can query by PK/SK)
- Existing records without trigger_type should default to "manual"

### Lambda Logic Flow
```python
def execute_usecase(event, context):
    # Parse request
    trigger_type = body.get('trigger_type', 'manual')
    
    # Validate trigger_type
    if trigger_type not in ['manual', 'scheduled', 'ci_runner']:
        return error_response(400, 'Invalid trigger_type')
    
    # Create execution record (existing logic)
    execution_record = create_execution_record(
        usecase_id=usecase_id,
        trigger_type=trigger_type,
        # ... other fields
    )
    
    # Conditional ECS task creation
    if trigger_type != 'ci_runner':
        spawn_ecs_task(execution_id)
    
    return success_response(execution_record)
```

### Step Status Update Lambda

**New Lambda**: `update_execution_step_status`

```python
def update_execution_step_status(event, context):
    """
    Update the status of an individual execution step.
    Used by CI/CD runner to report step progress.
    """
    # Parse request
    usecase_id = event['pathParameters']['id']
    execution_id = event['pathParameters']['executionId']
    step_id = event['pathParameters']['stepId']
    body = json.loads(event['body'])
    
    status = body.get('status')
    started_at = body.get('started_at')
    completed_at = body.get('completed_at')
    error_message = body.get('error_message')
    
    # Validate status
    valid_statuses = ['pending', 'running', 'completed', 'failed', 'skipped']
    if status not in valid_statuses:
        return error_response(400, f'Invalid status. Must be one of: {", ".join(valid_statuses)}')
    
    # Verify execution exists
    execution = get_execution(usecase_id, execution_id)
    if not execution:
        return error_response(404, 'Execution not found')
    
    # Verify step exists
    step = get_execution_step(execution_id, step_id)
    if not step:
        return error_response(404, 'Step not found')
    
    # Build update expression
    update_expression = 'SET #status = :status'
    expression_attribute_names = {'#status': 'status'}
    expression_attribute_values = {':status': {'S': status}}
    
    if started_at:
        update_expression += ', started_at = :started_at'
        expression_attribute_values[':started_at'] = {'S': started_at}
    
    if completed_at:
        update_expression += ', completed_at = :completed_at'
        expression_attribute_values[':completed_at'] = {'S': completed_at}
    
    if error_message:
        update_expression += ', error_message = :error_message'
        expression_attribute_values[':error_message'] = {'S': error_message}
    
    # Update step status in DynamoDB
    dynamodb.update_item(
        TableName=get_table_name(),
        Key={
            'pk': {'S': f'EXECUTION#{execution_id}'},
            'sk': {'S': f'EXECUTION_STEP#{step_id}'}
        },
        UpdateExpression=update_expression,
        ExpressionAttributeNames=expression_attribute_names,
        ExpressionAttributeValues=expression_attribute_values
    )
    
    print(f'Updated step {step_id} status to {status}')
    
    return success_response({
        'success': True,
        'step_id': step_id,
        'status': status
    })
```

### Backward Compatibility
- Existing API calls without `trigger_type` default to "manual"
- Existing execution records without `trigger_type` are treated as "manual"
- No breaking changes to existing functionality

---

## Testing Requirements

### Unit Tests
- Test execution record creation with each trigger_type value
- Test default trigger_type is "manual" when not specified
- Test invalid trigger_type returns 400 error
- Test ECS task is NOT created when trigger_type="ci_runner"
- Test ECS task IS created when trigger_type="manual" or "scheduled"
- Test step status update with valid status values
- Test step status update with invalid status returns 400
- Test step status update for non-existent step returns 404
- Test step status update stores started_at and completed_at
- Test step status update stores error_message for failed steps

### Integration Tests
- Create execution via API with trigger_type="ci_runner"
- Verify execution record exists in DynamoDB
- Verify no ECS task was created
- Create execution via API with trigger_type="manual"
- Verify ECS task was created
- Update step status via API
- Verify step status updated in DynamoDB
- Update multiple steps in sequence
- Verify all step statuses updated correctly

---

## Security Considerations

- No new scopes required (uses existing `api/execution.write`)
- Validate trigger_type to prevent injection attacks
- Ensure CI/CD runner cannot bypass authorization
- Step status updates require `api/execution.write` scope
- Validate step_id and execution_id to prevent unauthorized updates
- Sanitize error_message to prevent XSS attacks

---

## Rollout Plan

1. Deploy DynamoDB schema changes (backward compatible)
2. Deploy updated `execute_usecase` Lambda
3. Test with manual trigger (existing behavior)
4. Test with ci_runner trigger (new behavior)
5. Monitor CloudWatch logs for errors

---

## Success Criteria

- [ ] Execution records include trigger_type field
- [ ] execute_usecase Lambda skips ECS task creation for ci_runner trigger
- [ ] Existing manual/scheduled executions continue to work
- [ ] Step status update endpoint created and functional
- [ ] Step status updates validated and stored correctly
- [ ] Unit test coverage ≥ 70%
- [ ] Integration tests pass
- [ ] No breaking changes to existing API contracts
