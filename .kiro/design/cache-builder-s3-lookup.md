# Cache Builder Lambda - S3 File Lookup Strategy

## Current Architecture

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

## S3 File Structure

Nova Act automatically saves action traces to:
```
s3://{bucket}/{artefact_prefix}/act_{act_id}_{instruction}_calls.json
```

Example:
```
s3://qa-studio-artifacts/executions/exec-123/act_019c9f2a-d303-7dc3-9fd1-c4793981fe63_Close_any_popups_on_the_page_calls.json
```

## Cache Builder Lambda Strategy

**Step 1: Query EXECUTION_STEP records**
```python
execution_steps = dynamodb.query(
    KeyConditionExpression=Key('pk').eq(f'EXECUTION#{execution_id}') & 
                          Key('sk').begins_with('EXECUTION_STEP#')
)
```

**Step 2: For each step, construct S3 key**
```python
for step in execution_steps:
    act_id = step.get('act_id')  # Already stored by worker
    instruction = step.get('instruction')
    
    # Construct S3 key (same pattern as Nova Act)
    s3_key = f"executions/{execution_id}/act_{act_id}_{sanitize(instruction)}_calls.json"
    
    # Fetch from S3
    response = s3.get_object(Bucket=bucket, Key=s3_key)
    act_response = json.loads(response['Body'].read())
    
    # Parse and cache
    cached_steps = parse_nova_act_steps(act_response)
    update_step_cache(step['step_id'], cached_steps)
```

**Step 3: Handle missing files gracefully**
```python
try:
    response = s3.get_object(Bucket=bucket, Key=s3_key)
except s3.exceptions.NoSuchKey:
    logger.warning(f"Nova Act trace not found for step {step_id}, skipping cache")
    continue  # Skip this step, don't fail entire batch
```

## Alternative: List S3 Objects

If exact filename matching is unreliable (instruction sanitization differs), use prefix listing:

```python
# List all act_*.json files for this execution
objects = s3.list_objects_v2(
    Bucket=bucket,
    Prefix=f"executions/{execution_id}/act_"
)

# Build map: act_id -> s3_key
act_files = {}
for obj in objects.get('Contents', []):
    key = obj['Key']
    # Extract act_id from filename: act_{act_id}_*.json
    match = re.search(r'act_([^_]+)_.*\.json$', key)
    if match:
        act_files[match.group(1)] = key

# Then lookup by act_id
for step in execution_steps:
    act_id = step.get('act_id')
    s3_key = act_files.get(act_id)
    if not s3_key:
        continue
    # Fetch and parse...
```

## Recommendation

**Use direct S3 key construction** (first approach):
- Simpler and faster (no list operation)
- Worker already stores `act_id`
- Instruction sanitization should match Nova Act's
- Gracefully skip missing files

**Fallback to list approach** only if filename matching proves unreliable in practice.

## Implementation Notes

**Instruction sanitization** (match Nova Act's behavior):
```python
def sanitize_instruction(instruction: str) -> str:
    """Sanitize instruction for S3 filename (match Nova Act)"""
    # Replace spaces and special chars with underscores
    sanitized = re.sub(r'[^\w\s-]', '', instruction)
    sanitized = re.sub(r'[-\s]+', '_', sanitized)
    return sanitized[:100]  # Limit length
```

**Batch processing**:
```python
# Process all steps in one Lambda invocation
for step in execution_steps:
    if step.get('step_type') != 'navigation':
        continue  # Skip validation steps
    
    try:
        # Fetch, parse, cache
        process_step_cache(step, execution_id, bucket)
    except Exception as e:
        logger.error(f"Failed to cache step {step['step_id']}: {e}")
        continue  # Don't fail entire batch
```

## Testing

**Unit test**: Mock S3 responses
```python
@mock_s3
def test_cache_builder():
    # Setup mock S3 with act_*.json files
    s3.put_object(
        Bucket='test-bucket',
        Key='executions/exec-123/act_abc123_Click_login_calls.json',
        Body=json.dumps(mock_nova_act_response)
    )
    
    # Invoke Lambda
    result = handler(mock_event)
    
    # Verify cache created
    assert step_has_cache('step-001')
```

**Integration test**: Use real S3 and DynamoDB
```python
def test_cache_builder_integration():
    # Create execution with steps
    # Upload real Nova Act response to S3
    # Emit event
    # Verify cache built in STEP records
```
