# Work Package 1c: Artifact Presigned URL Endpoints

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP1c - Artifact Presigned URL Endpoints
- **Estimated Duration**: 2 days
- **Dependencies**: WP1a (Execution Record & Trigger Type)
- **Status**: Not Started

---

## Overview

Create API endpoints that generate presigned S3 URLs for artifact uploads. The CI/CD runner will use these URLs to upload artifacts (videos, traces, logs, screenshots) directly to S3, bypassing API Gateway payload limits.

---

## User Stories

### US1: As a CI/CD runner, I need to upload execution-level artifacts (recording, logs)
**Acceptance Criteria**:
- Single endpoint for execution-level artifacts with type parameter
- Endpoint accepts artifact type: "recording" or "logs"
- Endpoint generates presigned S3 URL with appropriate expiration
- Endpoint returns upload URL and artifact_id
- Artifact metadata is stored in DynamoDB

### US2: As a CI/CD runner, I need to upload step-level artifacts (screenshots, traces)
**Acceptance Criteria**:
- Separate endpoint for step-level artifacts
- Endpoint accepts step_id in path
- Endpoint generates presigned S3 URL for step artifact
- Endpoint returns upload URL and artifact_id
- Artifact metadata is stored in DynamoDB

### US3: As a platform, I need to track artifact metadata
**Acceptance Criteria**:
- Artifact records include: artifact_id, execution_id, type, filename, s3_key, upload_status
- Artifact records are queryable by execution_id
- Artifact records include created_at timestamp
- Artifact records support both execution-level and step-level artifacts

---

## Technical Requirements

### New Data Model

**Artifact Record (DynamoDB)**:
```python
{
    "PK": "EXECUTION#{execution_id}",
    "SK": "ARTIFACT#{artifact_id}",
    "artifact_id": "uuid",
    "execution_id": "uuid",
    "step_id": "uuid",  # Optional, only for step-level artifacts
    "type": "recording" | "logs" | "screenshot" | "trace",
    "filename": "string",
    "content_type": "string",
    "s3_bucket": "string",
    "s3_key": "string",
    "upload_status": "pending" | "completed" | "failed",
    "created_at": "ISO8601 timestamp",
    "uploaded_at": "ISO8601 timestamp",  # Set when upload confirmed
    "size_bytes": "number"  # Optional, set after upload
}
```

### S3 Key Structure

**Execution-level artifacts**:
```
artifacts/{usecase_id}/executions/{execution_id}/recording.webm
artifacts/{usecase_id}/executions/{execution_id}/logs.txt
```

**Step-level artifacts**:
```
artifacts/{usecase_id}/executions/{execution_id}/steps/{step_id}/screenshot.png
artifacts/{usecase_id}/executions/{execution_id}/steps/{step_id}/trace.json
```

### New API Endpoints

#### Endpoint 1: Execution-Level Artifacts

**Endpoint**: `POST /usecase/{id}/executions/{executionId}/artifacts`

**Request Body**:
```json
{
  "type": "recording" | "logs",
  "filename": "recording.webm",
  "content_type": "video/webm"
}
```

**Response**:
```json
{
  "artifact_id": "uuid",
  "upload_url": "https://s3.amazonaws.com/bucket/key?X-Amz-Algorithm=...",
  "expires_in": 3600,
  "s3_key": "artifacts/{usecase_id}/executions/{execution_id}/recording.webm"
}
```

#### Endpoint 2: Step-Level Artifacts

**Endpoint**: `POST /usecase/{id}/executions/{executionId}/steps/{stepId}/artifacts`

**Request Body**:
```json
{
  "filename": "screenshot.png",
  "content_type": "image/png"
}
```

**Response**:
```json
{
  "artifact_id": "uuid",
  "upload_url": "https://s3.amazonaws.com/bucket/key?X-Amz-Algorithm=...",
  "expires_in": 3600,
  "s3_key": "artifacts/{usecase_id}/executions/{execution_id}/steps/{step_id}/screenshot.png"
}
```

**Error Responses**:
- `400`: Invalid request (missing fields, invalid type)
- `404`: Execution or step not found
- `403`: Insufficient permissions
- `500`: Internal server error

---

## Implementation Details

### Lambda Function: `generate_artifact_presigned_url`

**For Execution-Level Artifacts**:
```python
import boto3
from datetime import datetime, timedelta
import uuid

def generate_execution_artifact_url(event, context):
    # 1. Parse request
    usecase_id = event['pathParameters']['id']
    execution_id = event['pathParameters']['executionId']
    body = json.loads(event['body'])
    
    artifact_type = body['type']  # "recording" or "logs"
    filename = body['filename']
    content_type = body['content_type']
    
    # 2. Validate execution exists
    execution = get_execution(usecase_id, execution_id)
    if not execution:
        return error_response(404, 'Execution not found')
    
    # 3. Validate artifact type
    if artifact_type not in ['recording', 'logs']:
        return error_response(400, 'Invalid artifact type')
    
    # 4. Generate S3 key
    artifact_id = str(uuid.uuid4())
    s3_key = f"artifacts/{usecase_id}/executions/{execution_id}/{filename}"
    
    # 5. Create artifact record in DynamoDB
    artifact_record = {
        'PK': f"EXECUTION#{execution_id}",
        'SK': f"ARTIFACT#{artifact_id}",
        'artifact_id': artifact_id,
        'execution_id': execution_id,
        'type': artifact_type,
        'filename': filename,
        'content_type': content_type,
        's3_bucket': ARTIFACTS_BUCKET,
        's3_key': s3_key,
        'upload_status': 'pending',
        'created_at': datetime.utcnow().isoformat()
    }
    save_artifact_record(artifact_record)
    
    # 6. Generate presigned URL
    s3_client = boto3.client('s3')
    presigned_url = s3_client.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': ARTIFACTS_BUCKET,
            'Key': s3_key,
            'ContentType': content_type
        },
        ExpiresIn=3600  # 1 hour
    )
    
    # 7. Return response
    return success_response({
        'artifact_id': artifact_id,
        'upload_url': presigned_url,
        'expires_in': 3600,
        's3_key': s3_key
    })
```

**For Step-Level Artifacts**:
```python
def generate_step_artifact_url(event, context):
    # Similar to above, but includes step_id
    usecase_id = event['pathParameters']['id']
    execution_id = event['pathParameters']['executionId']
    step_id = event['pathParameters']['stepId']
    body = json.loads(event['body'])
    
    filename = body['filename']
    content_type = body['content_type']
    
    # Validate execution and step exist
    execution = get_execution(usecase_id, execution_id)
    if not execution:
        return error_response(404, 'Execution not found')
    
    step = get_execution_step(execution_id, step_id)
    if not step:
        return error_response(404, 'Step not found')
    
    # Generate S3 key with step_id
    artifact_id = str(uuid.uuid4())
    s3_key = f"artifacts/{usecase_id}/executions/{execution_id}/steps/{step_id}/{filename}"
    
    # Create artifact record with step_id
    artifact_record = {
        'PK': f"EXECUTION#{execution_id}",
        'SK': f"ARTIFACT#{artifact_id}",
        'artifact_id': artifact_id,
        'execution_id': execution_id,
        'step_id': step_id,  # Include step_id
        'filename': filename,
        'content_type': content_type,
        's3_bucket': ARTIFACTS_BUCKET,
        's3_key': s3_key,
        'upload_status': 'pending',
        'created_at': datetime.utcnow().isoformat()
    }
    save_artifact_record(artifact_record)
    
    # Generate presigned URL
    s3_client = boto3.client('s3')
    presigned_url = s3_client.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': ARTIFACTS_BUCKET,
            'Key': s3_key,
            'ContentType': content_type
        },
        ExpiresIn=3600
    )
    
    return success_response({
        'artifact_id': artifact_id,
        'upload_url': presigned_url,
        'expires_in': 3600,
        's3_key': s3_key
    })
```

### S3 Bucket Configuration

**Bucket Name**: `{stack-name}-artifacts` (existing bucket)

**CORS Configuration**:
```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["PUT", "POST"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": ["ETag"]
  }
]
```

**Lifecycle Policy**:
- Transition to Glacier after 90 days
- Delete after 365 days (configurable)

---

## API Gateway Configuration

**Endpoint 1**:
- **Path**: `/usecase/{id}/executions/{executionId}/artifacts`
- **Method**: `POST`
- **Authorizer**: Cognito User Pool Authorizer
- **Required Scopes**: `api/execution.write`
- **Lambda**: `generate_artifact_presigned_url`

**Endpoint 2**:
- **Path**: `/usecase/{id}/executions/{executionId}/steps/{stepId}/artifacts`
- **Method**: `POST`
- **Authorizer**: Cognito User Pool Authorizer
- **Required Scopes**: `api/execution.write`
- **Lambda**: `generate_step_artifact_presigned_url`

---

## Testing Requirements

### Unit Tests
- Test presigned URL generation for execution-level artifacts
- Test presigned URL generation for step-level artifacts
- Test artifact record creation in DynamoDB
- Test S3 key generation logic
- Test validation (execution exists, step exists)
- Test error handling (invalid type, missing fields)

### Integration Tests
- Generate presigned URL for recording artifact
- Upload file to presigned URL
- Verify file exists in S3
- Verify artifact record in DynamoDB
- Generate presigned URL for step screenshot
- Upload screenshot to presigned URL
- Verify screenshot in S3

### Security Tests
- Test presigned URL expiration (after 1 hour)
- Test presigned URL cannot be used for GET (only PUT)
- Test OAuth scope validation

---

## Security Considerations

- Presigned URLs expire after 1 hour
- URLs are single-use (PUT only, not GET)
- OAuth scopes validated: `api/execution.write`
- S3 bucket has encryption at rest enabled
- Artifact records track upload status
- No public read access to artifacts (presigned URLs required)

---

## DynamoDB Query Patterns

**Query all artifacts for an execution**:
```python
PK = "EXECUTION#{execution_id}"
SK begins_with "ARTIFACT#"
```

**Query step-level artifacts**:
```python
PK = "EXECUTION#{execution_id}"
SK begins_with "ARTIFACT#"
Filter: step_id = {step_id}
```

---

## Future Enhancements (Out of Scope)

- Webhook notification when upload completes
- Automatic artifact size validation
- Virus scanning for uploaded files
- Artifact compression
- CDN distribution for artifact downloads

---

## Success Criteria

- [ ] Execution-level artifact endpoint created
- [ ] Step-level artifact endpoint created
- [ ] Presigned URLs generated successfully
- [ ] Artifact records stored in DynamoDB
- [ ] S3 uploads work via presigned URLs
- [ ] Unit test coverage ≥ 70%
- [ ] Integration tests pass
- [ ] API documentation updated
- [ ] S3 bucket CORS configured correctly
