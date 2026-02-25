# Work Package 1c: Artifact Presigned URL Endpoints - Design Document

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP1c - Artifact Presigned URL Endpoints
- **Version**: 1.0
- **Status**: Design Phase
- **Dependencies**: WP1a (Execution Record & Trigger Type)

---

## Design Overview

This workpackage implements two API endpoints that generate presigned S3 URLs for artifact uploads. The CI/CD runner will use these URLs to upload artifacts (videos, traces, logs, screenshots) directly to S3, bypassing API Gateway payload limits (6MB for REST APIs, 10MB for HTTP APIs).

### Key Design Principles
1. **Direct S3 Upload**: Generate presigned URLs for direct client-to-S3 uploads
2. **Metadata Tracking**: Store artifact metadata in DynamoDB before upload
3. **Security**: Presigned URLs expire after 1 hour, single-use (PUT only)
4. **Separation**: Execution-level artifacts (recording, logs) vs step-level artifacts (screenshots, traces)
5. **Query Efficiency**: Use existing DynamoDB patterns, no new GSI/LSI required

---

## Architecture

### High-Level Flow

```
CI/CD Runner
    ↓
POST /usecase/{id}/executions/{executionId}/artifacts
    ↓
Lambda: generate_execution_artifact_url
    ↓
1. Validate execution exists
2. Validate artifact type (recording or logs)
3. Generate artifact_id (UUIDv7)
4. Generate S3 key
5. Create artifact record in DynamoDB (status=pending)
6. Generate presigned URL (PUT, 1 hour expiration)
7. Return presigned URL + artifact_id
    ↓
CI/CD Runner uploads file to presigned URL
    ↓
File stored in S3
```

### Component Interaction

```
┌─────────────────┐
│   CI/CD Runner  │
└────────┬────────┘
         │ POST /usecase/{id}/executions/{executionId}/artifacts
         │ { type: "recording", filename: "recording.webm", content_type: "video/webm" }
         ↓
┌─────────────────────────────────────────────────┐
│         API Gateway + Lambda Authorizer         │
│         (Cognito OAuth validation)              │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│    Lambda: generate_execution_artifact_url      │
│                                                  │
│  1. Get: USECASE_EXECUTION#{usecase_id} /      │
│          EXECUTION#{execution_id}               │
│  2. Validate artifact type                      │
│  3. Generate artifact_id (UUIDv7)              │
│  4. Generate S3 key                             │
│  5. Put: EXECUTION#{execution_id} /            │
│          ARTIFACT#{artifact_id}                 │
│  6. Generate presigned URL (S3 PutObject)      │
│  7. Return URL + artifact_id                    │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│              DynamoDB Table                      │
│                                                  │
│  - Artifact record (status=pending)             │
└─────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│   CI/CD Runner uploads to presigned URL         │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│              S3 Bucket                           │
│                                                  │
│  - Artifact file stored                         │
└─────────────────────────────────────────────────┘
```

---

## Components and Interfaces

### 1. Lambda Function: generate_execution_artifact_url

**Purpose**: Generate presigned S3 URL for execution-level artifacts (recording, logs)

**Handler Signature**:
```python
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]
```

**Input** (API Gateway event):
```python
{
    'pathParameters': {
        'id': 'usecase-uuid',
        'executionId': 'execution-uuid'
    },
    'body': json.dumps({
        'type': 'recording',  # or 'logs'
        'filename': 'recording.webm',
        'content_type': 'video/webm'
    })
}
```

**Output**:
```python
{
    'statusCode': 200,
    'body': json.dumps({
        'artifact_id': 'uuid',
        'upload_url': 'https://s3.amazonaws.com/bucket/key?X-Amz-Algorithm=...',
        'expires_in': 3600,
        's3_key': 'artifacts/{usecase_id}/executions/{execution_id}/recording.webm'
    })
}
```

**Core Functions**:

```python
def validate_execution_exists(usecase_id: str, execution_id: str) -> Dict[str, Any]:
    """
    Verify execution record exists in DynamoDB.
    
    Query: pk='USECASE_EXECUTION#{usecase_id}', sk='EXECUTION#{execution_id}'
    
    Returns:
        Execution record
    
    Raises:
        ValueError: If execution not found
    """

def validate_artifact_type(artifact_type: str, allowed_types: List[str]) -> None:
    """
    Validate artifact type is in allowed list.
    
    Args:
        artifact_type: Type from request body
        allowed_types: List of valid types for this endpoint
    
    Raises:
        ValueError: If type not in allowed list
    """

def generate_s3_key_for_execution_artifact(
    usecase_id: str,
    execution_id: str,
    filename: str
) -> str:
    """
    Generate S3 key for execution-level artifact.
    
    Format: artifacts/{usecase_id}/executions/{execution_id}/{filename}
    
    Args:
        usecase_id: Usecase UUID
        execution_id: Execution UUID
        filename: Original filename from request
    
    Returns:
        S3 key string
    """

def create_artifact_record(
    artifact_id: str,
    execution_id: str,
    artifact_type: str,
    filename: str,
    content_type: str,
    s3_bucket: str,
    s3_key: str,
    created_at: str,
    step_id: Optional[str] = None
) -> None:
    """
    Create artifact metadata record in DynamoDB.
    
    Put: pk='EXECUTION#{execution_id}', sk='ARTIFACT#{artifact_id}'
    
    Args:
        artifact_id: Generated UUIDv7
        execution_id: Parent execution UUID
        artifact_type: Type of artifact (recording, logs, screenshot, trace)
        filename: Original filename
        content_type: MIME type
        s3_bucket: S3 bucket name
        s3_key: S3 object key
        created_at: ISO8601 timestamp
        step_id: Optional step UUID for step-level artifacts
    """

def generate_presigned_upload_url(
    s3_bucket: str,
    s3_key: str,
    content_type: str,
    expires_in: int = 3600
) -> str:
    """
    Generate presigned URL for S3 PutObject operation.
    
    Args:
        s3_bucket: S3 bucket name
        s3_key: S3 object key
        content_type: MIME type (enforced in presigned URL)
        expires_in: Expiration time in seconds (default 1 hour)
    
    Returns:
        Presigned URL string
    """
```

### 2. Lambda Function: generate_step_artifact_url

**Purpose**: Generate presigned S3 URL for step-level artifacts (screenshot, trace)

**Handler Signature**:
```python
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]
```

**Input** (API Gateway event):
```python
{
    'pathParameters': {
        'id': 'usecase-uuid',
        'executionId': 'execution-uuid',
        'stepId': 'step-uuid'
    },
    'body': json.dumps({
        'filename': 'screenshot.png',
        'content_type': 'image/png'
    })
}
```

**Output**:
```python
{
    'statusCode': 200,
    'body': json.dumps({
        'artifact_id': 'uuid',
        'upload_url': 'https://s3.amazonaws.com/bucket/key?X-Amz-Algorithm=...',
        'expires_in': 3600,
        's3_key': 'artifacts/{usecase_id}/executions/{execution_id}/steps/{step_id}/screenshot.png'
    })
}
```

**Core Functions**:

```python
def validate_step_exists(execution_id: str, step_id: str) -> Dict[str, Any]:
    """
    Verify execution step record exists in DynamoDB.
    
    Query: pk='EXECUTION#{execution_id}', sk='EXECUTION_STEP#{step_id}'
    
    Returns:
        Execution step record
    
    Raises:
        ValueError: If step not found
    """

def generate_s3_key_for_step_artifact(
    usecase_id: str,
    execution_id: str,
    step_id: str,
    filename: str
) -> str:
    """
    Generate S3 key for step-level artifact.
    
    Format: artifacts/{usecase_id}/executions/{execution_id}/steps/{step_id}/{filename}
    
    Args:
        usecase_id: Usecase UUID
        execution_id: Execution UUID
        step_id: Step UUID
        filename: Original filename from request
    
    Returns:
        S3 key string
    """
```

### 3. API Gateway Configuration

**Endpoint 1: Execution-Level Artifacts**

**Path**: `/usecase/{id}/executions/{executionId}/artifacts`

**Method**: `POST`

**Authorizer**: Cognito User Pool Authorizer

**Required Scopes**: `api/execution.write`

**Request Validation**:
- Path parameters `id` and `executionId` are required
- Request body must be valid JSON
- `type` field is required and must be "recording" or "logs"
- `filename` field is required
- `content_type` field is required

**Response Models**:
- 200: Success response with presigned URL
- 400: Bad request (invalid type, missing fields)
- 403: Forbidden (insufficient scopes)
- 404: Execution not found
- 500: Internal server error

**Endpoint 2: Step-Level Artifacts**

**Path**: `/usecase/{id}/executions/{executionId}/steps/{stepId}/artifacts`

**Method**: `POST`

**Authorizer**: Cognito User Pool Authorizer

**Required Scopes**: `api/execution.write`

**Request Validation**:
- Path parameters `id`, `executionId`, and `stepId` are required
- Request body must be valid JSON
- `filename` field is required
- `content_type` field is required

**Response Models**:
- 200: Success response with presigned URL
- 400: Bad request (missing fields)
- 403: Forbidden (insufficient scopes)
- 404: Execution or step not found
- 500: Internal server error

### 4. S3 Bucket Configuration

**Bucket Name**: Retrieved from environment variable `BUCKET_NAME` (existing bucket)

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

**Encryption**: Server-side encryption enabled (AES-256 or KMS)

**Lifecycle Policy** (optional, for future):
- Transition to Glacier after 90 days
- Delete after 365 days

**Bucket Policy**: Lambda execution role must have `s3:PutObject` permission

---

## Data Models

### Artifact Record

**DynamoDB Item**:
```python
{
    'pk': 'EXECUTION#{execution_id}',
    'sk': 'ARTIFACT#{artifact_id}',
    'artifact_id': 'uuid',  # UUIDv7
    'execution_id': 'uuid',
    'step_id': 'uuid',  # Optional, only for step-level artifacts
    'type': 'recording',  # recording | logs | screenshot | trace
    'filename': 'recording.webm',
    'content_type': 'video/webm',
    's3_bucket': 'bucket-name',
    's3_key': 'artifacts/{usecase_id}/executions/{execution_id}/recording.webm',
    'upload_status': 'pending',  # pending | completed | failed
    'created_at': 'ISO8601 timestamp',
    'uploaded_at': 'ISO8601 timestamp',  # Optional, set when upload confirmed
    'size_bytes': 12345  # Optional, set after upload
}
```

**Query Patterns**:

```python
# Get all artifacts for an execution
pk = 'EXECUTION#{execution_id}'
sk begins_with 'ARTIFACT#'

# Get specific artifact
pk = 'EXECUTION#{execution_id}'
sk = 'ARTIFACT#{artifact_id}'

# Filter step-level artifacts (application-level filter)
pk = 'EXECUTION#{execution_id}'
sk begins_with 'ARTIFACT#'
Filter: step_id = {step_id}
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

**Rationale**:
- Hierarchical structure for easy querying and cleanup
- Usecase ID at top level for organizational purposes
- Execution ID groups all artifacts for a single execution
- Step ID groups artifacts for a specific step
- Filename preserves original name for debugging

---

## Error Handling

### Error Response Format

All error responses follow this structure:
```json
{
    "error": "Error type",
    "message": "Detailed error description"
}
```

### Error Scenarios

#### 1. Execution Not Found (404)
```python
try:
    execution = validate_execution_exists(usecase_id, execution_id)
except ValueError:
    return create_response(404, {
        'error': 'Execution not found',
        'message': f'No execution found with ID: {execution_id}'
    })
```

#### 2. Step Not Found (404)
```python
try:
    step = validate_step_exists(execution_id, step_id)
except ValueError:
    return create_response(404, {
        'error': 'Step not found',
        'message': f'No step found with ID: {step_id}'
    })
```

#### 3. Invalid Artifact Type (400)
```python
if artifact_type not in ['recording', 'logs']:
    return create_response(400, {
        'error': 'Invalid artifact type',
        'message': f'Artifact type must be "recording" or "logs", got: {artifact_type}'
    })
```

#### 4. Missing Required Fields (400)
```python
if not filename or not content_type:
    return create_response(400, {
        'error': 'Missing required fields',
        'message': 'filename and content_type are required'
    })
```

#### 5. Insufficient Permissions (403)
```python
# Handled by require_scopes utility
user_identity, error_response = require_scopes(event, ['api/execution.write'])
if error_response:
    return error_response
```

#### 6. S3 Error (500)
```python
except ClientError as e:
    print(f'S3 error: {str(e)}')
    return create_response(500, {
        'error': 'Failed to generate presigned URL',
        'message': 'Internal server error'
    })
```

#### 7. DynamoDB Error (500)
```python
except ClientError as e:
    print(f'DynamoDB error: {str(e)}')
    return create_response(500, {
        'error': 'Failed to create artifact record',
        'message': 'Internal server error'
    })
```

### Error Handling Strategy

1. **Validate Early**: Check execution/step exists before generating URLs
2. **Fail Fast**: Return errors immediately, don't create partial state
3. **Clear Messages**: Provide actionable error messages
4. **Logging**: Log all errors to CloudWatch for debugging
5. **Security**: Don't expose internal details in error messages

---

## Testing Strategy

### Unit Tests

**File**: `lambdas/endpoints/test_generate_execution_artifact_url.py` (new file)

**Test Coverage Target**: ≥70%

**Test Classes**:

```python
class TestGenerateExecutionArtifactUrl:
    """Test execution-level artifact URL generation"""
    
    def test_generate_url_for_recording(self):
        """Verify presigned URL generated for recording artifact"""
    
    def test_generate_url_for_logs(self):
        """Verify presigned URL generated for logs artifact"""
    
    def test_artifact_record_created_with_pending_status(self):
        """Verify artifact record created in DynamoDB with status=pending"""
    
    def test_s3_key_format_correct(self):
        """Verify S3 key follows expected format"""
    
    def test_presigned_url_expires_in_one_hour(self):
        """Verify presigned URL has 1 hour expiration"""
    
    def test_content_type_enforced_in_presigned_url(self):
        """Verify content_type parameter included in presigned URL"""

class TestGenerateStepArtifactUrl:
    """Test step-level artifact URL generation"""
    
    def test_generate_url_for_screenshot(self):
        """Verify presigned URL generated for screenshot"""
    
    def test_generate_url_for_trace(self):
        """Verify presigned URL generated for trace"""
    
    def test_artifact_record_includes_step_id(self):
        """Verify artifact record includes step_id field"""
    
    def test_s3_key_includes_step_id(self):
        """Verify S3 key includes step_id in path"""

class TestValidation:
    """Test input validation"""
    
    def test_execution_not_found_returns_404(self):
        """Verify 404 when execution doesn't exist"""
    
    def test_step_not_found_returns_404(self):
        """Verify 404 when step doesn't exist"""
    
    def test_invalid_artifact_type_returns_400(self):
        """Verify 400 when artifact type is invalid"""
    
    def test_missing_filename_returns_400(self):
        """Verify 400 when filename is missing"""
    
    def test_missing_content_type_returns_400(self):
        """Verify 400 when content_type is missing"""
    
    def test_insufficient_permissions_returns_403(self):
        """Verify 403 when api/execution.write scope missing"""

class TestS3KeyGeneration:
    """Test S3 key generation logic"""
    
    def test_execution_artifact_key_format(self):
        """Verify execution artifact key format"""
    
    def test_step_artifact_key_format(self):
        """Verify step artifact key format"""
    
    def test_filename_preserved_in_key(self):
        """Verify original filename preserved in S3 key"""
    
    def test_special_characters_in_filename(self):
        """Verify special characters handled correctly"""
```

**File**: `lambdas/endpoints/test_generate_step_artifact_url.py` (new file)

```python
class TestGenerateStepArtifactUrl:
    """Test step-level artifact URL generation endpoint"""
    
    def test_generate_url_success(self):
        """Test successful URL generation"""
    
    def test_step_validation(self):
        """Test step existence validation"""
    
    def test_artifact_record_creation(self):
        """Test artifact record created with step_id"""
```

### Integration Tests

**Test Scenarios**:

1. **Generate URL and upload recording**
   - Create execution record
   - Call execution artifact endpoint with type="recording"
   - Verify presigned URL returned
   - Upload file to presigned URL using HTTP PUT
   - Verify file exists in S3
   - Verify artifact record in DynamoDB

2. **Generate URL and upload logs**
   - Create execution record
   - Call execution artifact endpoint with type="logs"
   - Upload text file to presigned URL
   - Verify file in S3

3. **Generate URL and upload screenshot**
   - Create execution and step records
   - Call step artifact endpoint
   - Upload image file to presigned URL
   - Verify file in S3
   - Verify artifact record includes step_id

4. **Generate URL and upload trace**
   - Create execution and step records
   - Call step artifact endpoint
   - Upload JSON file to presigned URL
   - Verify file in S3

5. **Presigned URL expiration**
   - Generate presigned URL
   - Wait 1 hour + 1 minute
   - Attempt upload
   - Verify upload fails with 403 Forbidden

6. **Invalid artifact type**
   - Call endpoint with type="invalid"
   - Verify 400 error returned

7. **Execution not found**
   - Call endpoint with non-existent execution ID
   - Verify 404 error returned

8. **Step not found**
   - Call step endpoint with non-existent step ID
   - Verify 404 error returned

### Manual Testing Checklist

- [ ] Deploy Lambda functions
- [ ] Create execution record via execute_usecase endpoint
- [ ] Call execution artifact endpoint with Postman/curl
- [ ] Verify presigned URL returned
- [ ] Upload file to presigned URL using curl
- [ ] Verify file in S3 console
- [ ] Verify artifact record in DynamoDB
- [ ] Test step artifact endpoint
- [ ] Test error cases (invalid type, missing execution)
- [ ] Verify OAuth scope validation works
- [ ] Test CORS headers on S3 bucket

---

## Correctness Properties

A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

### Property 1: Artifact Type Validation

*For any* request to the execution artifact endpoint, if the artifact type is "recording" or "logs", the request should be accepted and return a 200 response; if the artifact type is any other value, the request should be rejected with a 400 error.

**Validates: Requirements US1.2**

### Property 2: Presigned URL Generation

*For any* valid artifact request (execution-level or step-level), the endpoint should return a presigned S3 URL that expires in exactly 3600 seconds (1 hour) and includes the content_type parameter to enforce upload constraints.

**Validates: Requirements US1.3, US2.3**

### Property 3: Response Structure Completeness

*For any* successful artifact URL generation request, the response should contain exactly three required fields: artifact_id (a valid UUIDv7), upload_url (a valid HTTPS URL), and s3_key (a string matching the expected S3 key format).

**Validates: Requirements US1.4, US2.4**

### Property 4: Execution-Level Artifact Record Creation

*For any* successful execution artifact request, an artifact record should be created in DynamoDB with pk=EXECUTION#{execution_id}, sk=ARTIFACT#{artifact_id}, upload_status="pending", and without a step_id field.

**Validates: Requirements US1.5**

### Property 5: Step-Level Artifact Record Creation

*For any* successful step artifact request, an artifact record should be created in DynamoDB with pk=EXECUTION#{execution_id}, sk=ARTIFACT#{artifact_id}, upload_status="pending", and with a step_id field populated with the step UUID.

**Validates: Requirements US2.5**

### Property 6: Artifact Record Structure Invariant

*For any* artifact record created in DynamoDB, it must contain all required fields: artifact_id, execution_id, type, filename, content_type, s3_bucket, s3_key, upload_status, and created_at (in ISO8601 format); additionally, step-level artifacts must have a step_id field while execution-level artifacts must not.

**Validates: Requirements US3.1, US3.3, US3.4**

### Property 7: Artifact Queryability

*For any* execution with N artifacts, querying DynamoDB with pk=EXECUTION#{execution_id} and sk begins_with "ARTIFACT#" should return exactly N artifact records, each with a unique artifact_id.

**Validates: Requirements US3.2**

### Property 8: S3 Key Format Consistency

*For any* execution-level artifact, the S3 key should match the format "artifacts/{usecase_id}/executions/{execution_id}/{filename}"; for any step-level artifact, the S3 key should match the format "artifacts/{usecase_id}/executions/{execution_id}/steps/{step_id}/{filename}".

**Validates: Requirements US1.3, US2.3** (implicit in S3 key structure)

### Property 9: Presigned URL Single-Use Constraint

*For any* generated presigned URL, it should only allow PUT operations (not GET or DELETE), ensuring that the URL can only be used to upload a file, not to download or delete existing files.

**Validates: Security requirements** (implicit in presigned URL generation)

---

## Security Considerations

### Authentication & Authorization

**OAuth Scopes Required**:
- `api/execution.write` - Required to generate artifact upload URLs

**Scope Validation**:
```python
# Lambda function must validate scopes using existing require_scopes utility
user_identity, error_response = require_scopes(event, ['api/execution.write'])
if error_response:
    return error_response
```

**M2M Token Support**:
- Endpoints must support both user tokens and M2M tokens (OAuth client credentials)
- CI/CD runners will use M2M tokens exclusively
- Use existing `require_scopes()` function which supports both token types

### Input Validation

**Execution/Step ID Validation**:
- Validate IDs are valid UUID format
- Verify execution/step exists before generating URL
- Return 404 if not found

**Artifact Type Validation**:
```python
ALLOWED_EXECUTION_TYPES = ['recording', 'logs']

if artifact_type not in ALLOWED_EXECUTION_TYPES:
    return create_response(400, {
        'error': 'Invalid artifact type',
        'message': f'Artifact type must be one of: {", ".join(ALLOWED_EXECUTION_TYPES)}'
    })
```

**Filename Validation**:
- Validate filename is not empty
- Sanitize filename to prevent path traversal attacks
- Remove or replace special characters that could cause issues
- Maximum length: 255 characters

```python
def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent security issues.
    
    - Remove path separators (/, \)
    - Remove null bytes
    - Limit length to 255 characters
    - Preserve file extension
    """
    # Remove path separators and null bytes
    sanitized = filename.replace('/', '_').replace('\\', '_').replace('\0', '')
    
    # Limit length
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:255-len(ext)] + ext
    
    return sanitized
```

**Content-Type Validation**:
- Validate content_type is not empty
- Validate content_type follows MIME type format (type/subtype)
- Allowlist common content types for security:
  - Video: video/webm, video/mp4
  - Images: image/png, image/jpeg
  - Text: text/plain, application/json
  - Traces: application/json

```python
ALLOWED_CONTENT_TYPES = {
    'recording': ['video/webm', 'video/mp4'],
    'logs': ['text/plain'],
    'screenshot': ['image/png', 'image/jpeg'],
    'trace': ['application/json']
}

def validate_content_type(artifact_type: str, content_type: str) -> None:
    """Validate content type is allowed for artifact type."""
    allowed = ALLOWED_CONTENT_TYPES.get(artifact_type, [])
    if content_type not in allowed:
        raise ValueError(f'Content type {content_type} not allowed for {artifact_type}')
```

### Presigned URL Security

**Expiration**:
- URLs expire after 1 hour (3600 seconds)
- Cannot be extended or refreshed
- Client must request new URL if expired

**Operation Restriction**:
- URLs only allow PUT operation
- Cannot be used for GET (download) or DELETE
- Enforced by S3 presigned URL parameters

**Content-Type Enforcement**:
- Content-Type parameter included in presigned URL
- S3 will reject uploads with different content type
- Prevents uploading malicious file types

```python
presigned_url = s3_client.generate_presigned_url(
    'put_object',
    Params={
        'Bucket': bucket_name,
        'Key': s3_key,
        'ContentType': content_type  # Enforced by S3
    },
    ExpiresIn=3600
)
```

### S3 Bucket Security

**Encryption**:
- Server-side encryption enabled (AES-256 or KMS)
- All artifacts encrypted at rest

**Access Control**:
- No public read access
- Lambda execution role has PutObject permission only
- Presigned URLs required for all uploads
- Separate presigned URLs required for downloads (future)

**CORS Configuration**:
- Allow PUT and POST methods only
- Allow all origins (artifacts uploaded from CI/CD runners)
- Expose ETag header for upload verification

### Data Access Control

**Execution Access**:
- Verify user has access to the execution (scope-based)
- Artifact records inherit access control from parent execution
- Only users with `api/execution.write` scope can generate upload URLs

**Artifact Isolation**:
- S3 keys include usecase_id and execution_id
- Prevents cross-execution artifact access
- Each execution's artifacts are isolated

### Logging and Monitoring

**Sensitive Data**:
- Never log presigned URLs (contain temporary credentials)
- Log only artifact_id, execution_id, and artifact type
- Redact S3 keys in logs if they contain sensitive information

**Audit Trail**:
- Log all artifact URL generation requests
- Include user identity (email or client_id)
- Log artifact type and filename
- Log success/failure status

```python
print(json.dumps({
    'event': 'artifact_url_generated',
    'artifact_id': artifact_id,
    'execution_id': execution_id,
    'artifact_type': artifact_type,
    'filename': filename,
    'user_identity': user_identity['identity'],
    'timestamp': get_current_timestamp()
}))
```

---

## Performance Considerations

### Latency

**Expected Latency**:
- Execution validation: ~50ms (DynamoDB GetItem)
- Artifact record creation: ~50ms (DynamoDB PutItem)
- Presigned URL generation: ~10ms (local computation)
- Total: ~110ms per request

**Optimization Opportunities**:
- Cache execution validation results (if multiple artifacts uploaded)
- Batch artifact record creation (if multiple artifacts requested)

### Throughput

**DynamoDB Operations**:
- 1 read per request (execution validation)
- 1 write per request (artifact record creation)
- Total: 2 operations per request

**S3 Operations**:
- 0 S3 API calls (presigned URL generation is local)
- Actual uploads happen client-to-S3 (not through Lambda)

**Provisioned Capacity**:
- Use on-demand billing mode (existing configuration)
- No throttling expected for typical usage patterns

### Lambda Configuration

**Memory**: 256 MB (sufficient for URL generation)

**Timeout**: 30 seconds (more than enough for validation + URL generation)

**Concurrency**: No reserved concurrency needed (lightweight operation)

### S3 Upload Performance

**Direct Upload Benefits**:
- Bypasses API Gateway payload limits (6MB REST, 10MB HTTP)
- Bypasses Lambda payload limits (6MB synchronous)
- Supports large files (videos can be GBs)
- Parallel uploads from CI/CD runner

**Upload Speed**:
- Depends on client network bandwidth
- S3 supports multipart uploads for large files (client responsibility)
- No Lambda involvement in actual upload

---

## Monitoring & Observability

### CloudWatch Metrics

**Custom Metrics**:
```python
cloudwatch = boto3.client('cloudwatch')

cloudwatch.put_metric_data(
    Namespace='NovaActQA/Artifacts',
    MetricData=[
        {
            'MetricName': 'ArtifactUrlGenerated',
            'Value': 1,
            'Unit': 'Count',
            'Dimensions': [
                {'Name': 'ArtifactType', 'Value': artifact_type},
                {'Name': 'Level', 'Value': 'execution'}  # or 'step'
            ]
        },
        {
            'MetricName': 'UrlGenerationDuration',
            'Value': duration_ms,
            'Unit': 'Milliseconds'
        }
    ]
)
```

**Metrics to Track**:
- Artifact URLs generated (count, by type)
- URL generation duration (milliseconds)
- Errors by type (count)
- Execution-level vs step-level artifacts (count)

### CloudWatch Logs

**Structured Logging**:
```python
def log_artifact_event(event_type: str, data: Dict[str, Any]) -> None:
    """Log structured artifact event."""
    log_entry = {
        'timestamp': get_current_timestamp(),
        'event_type': event_type,
        'data': data
    }
    print(json.dumps(log_entry))

# Usage
log_artifact_event('artifact_url_generated', {
    'artifact_id': artifact_id,
    'execution_id': execution_id,
    'artifact_type': artifact_type,
    'filename': filename,
    's3_key': s3_key,
    'user_identity': user_identity['identity']
})
```

**Log Levels**:
- INFO: Normal URL generation
- WARN: Validation warnings (unusual filenames, etc.)
- ERROR: Failures (execution not found, S3 errors)

### S3 Event Notifications (Future Enhancement)

**Upload Completion Detection**:
- Configure S3 event notification for PutObject
- Trigger Lambda to update artifact record status
- Set upload_status="completed" and uploaded_at timestamp
- Calculate and store file size

**Event Pattern**:
```json
{
  "Event": "s3:ObjectCreated:Put",
  "Bucket": "artifacts-bucket",
  "Key": "artifacts/{usecase_id}/executions/{execution_id}/*"
}
```

### Alarms

**CloudWatch Alarms**:
- High error rate (>5% of requests)
- High latency (p99 > 1 second)
- DynamoDB throttling
- S3 API errors

---

## Rollout Plan

### Phase 1: Development & Testing (Week 1)

**Tasks**:
- [ ] Implement Lambda functions (execution and step artifacts)
- [ ] Write unit tests (≥70% coverage)
- [ ] Deploy to development environment
- [ ] Run integration tests
- [ ] Configure S3 bucket CORS

**Success Criteria**:
- All unit tests pass
- Integration tests pass
- Presigned URLs work for uploads
- No regressions in existing functionality

### Phase 2: Staging Validation (Week 1-2)

**Tasks**:
- [ ] Deploy to staging environment
- [ ] Manual testing with real executions
- [ ] Upload test files (video, logs, images, JSON)
- [ ] Verify files in S3
- [ ] Security review
- [ ] Documentation review

**Success Criteria**:
- Endpoints work with real data
- Files successfully uploaded to S3
- Security review approved
- Documentation complete

### Phase 3: Production Deployment (Week 2)

**Tasks**:
- [ ] Deploy to production
- [ ] Monitor CloudWatch metrics
- [ ] Monitor error rates
- [ ] Enable for CI/CD runner (WP2)

**Success Criteria**:
- Zero errors in first 24 hours
- Latency within acceptable range
- CI/CD runner can upload artifacts successfully

### Rollback Plan

**If issues detected**:
1. Disable endpoints in API Gateway (remove routes)
2. Revert Lambda functions to previous version
3. Investigate issue in development environment
4. Fix and redeploy

**Rollback Triggers**:
- Error rate >10%
- Latency p99 >5 seconds
- S3 upload failures
- Security vulnerability discovered

---

## Dependencies

### Internal Dependencies

**WP1a (Execution Record & Trigger Type)**:
- Required: Execution records exist for ci_runner trigger type
- Required: Execution step records exist

**Existing Infrastructure**:
- DynamoDB table with existing schema
- API Gateway with Cognito authorizer
- Lambda execution role with DynamoDB and S3 permissions
- S3 bucket for artifacts (existing)

### External Dependencies

**AWS Services**:
- DynamoDB (existing)
- API Gateway (existing)
- Lambda (existing)
- Cognito (existing)
- S3 (existing)
- CloudWatch (existing)

**Python Libraries**:
- boto3 (AWS SDK)
- json (standard library)
- os (standard library)
- uuid (standard library)

### Downstream Dependencies

**WP2 (CI/CD Runner Core)**:
- Will call these endpoints to get upload URLs
- Will upload artifacts to presigned URLs
- Depends on response format
- Depends on error handling behavior

---

## API Documentation

### Endpoint 1: Execution-Level Artifacts

**Path**: `POST /usecase/{id}/executions/{executionId}/artifacts`

**Authentication**: Required (Cognito JWT token)

**Authorization**: Requires scope `api/execution.write`

**Path Parameters**:
- `id` (string, required) - Usecase UUID
- `executionId` (string, required) - Execution UUID

**Request Body**:
```json
{
  "type": "recording",
  "filename": "recording.webm",
  "content_type": "video/webm"
}
```

**Request Body Schema**:
- `type` (string, required) - Artifact type: "recording" or "logs"
- `filename` (string, required) - Original filename (max 255 characters)
- `content_type` (string, required) - MIME type

**Response (200 OK)**:
```json
{
  "artifact_id": "01234567-89ab-cdef-0123-456789abcdef",
  "upload_url": "https://s3.amazonaws.com/bucket/artifacts/usecase-123/executions/execution-456/recording.webm?X-Amz-Algorithm=AWS4-HMAC-SHA256&...",
  "expires_in": 3600,
  "s3_key": "artifacts/usecase-123/executions/execution-456/recording.webm"
}
```

**Error Responses**:

**400 Bad Request**:
```json
{
  "error": "Invalid artifact type",
  "message": "Artifact type must be one of: recording, logs"
}
```

**403 Forbidden**:
```json
{
  "error": "Forbidden",
  "message": "Missing required scopes: api/execution.write",
  "required_scopes": ["api/execution.write"],
  "token_scopes": ["api/execution.read"]
}
```

**404 Not Found**:
```json
{
  "error": "Execution not found",
  "message": "No execution found with ID: execution-456"
}
```

**500 Internal Server Error**:
```json
{
  "error": "Failed to generate presigned URL",
  "message": "Internal server error"
}
```

### Endpoint 2: Step-Level Artifacts

**Path**: `POST /usecase/{id}/executions/{executionId}/steps/{stepId}/artifacts`

**Authentication**: Required (Cognito JWT token)

**Authorization**: Requires scope `api/execution.write`

**Path Parameters**:
- `id` (string, required) - Usecase UUID
- `executionId` (string, required) - Execution UUID
- `stepId` (string, required) - Step UUID

**Request Body**:
```json
{
  "filename": "screenshot.png",
  "content_type": "image/png"
}
```

**Request Body Schema**:
- `filename` (string, required) - Original filename (max 255 characters)
- `content_type` (string, required) - MIME type

**Response (200 OK)**:
```json
{
  "artifact_id": "01234567-89ab-cdef-0123-456789abcdef",
  "upload_url": "https://s3.amazonaws.com/bucket/artifacts/usecase-123/executions/execution-456/steps/step-789/screenshot.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&...",
  "expires_in": 3600,
  "s3_key": "artifacts/usecase-123/executions/execution-456/steps/step-789/screenshot.png"
}
```

**Error Responses**: Same as Endpoint 1, plus:

**404 Not Found** (Step):
```json
{
  "error": "Step not found",
  "message": "No step found with ID: step-789"
}
```

### Example Usage

**cURL (Execution Artifact)**:
```bash
# 1. Get presigned URL
RESPONSE=$(curl -X POST \
  'https://api.example.com/usecase/usecase-123/executions/execution-456/artifacts' \
  -H 'Authorization: Bearer <jwt_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "recording",
    "filename": "recording.webm",
    "content_type": "video/webm"
  }')

UPLOAD_URL=$(echo $RESPONSE | jq -r '.upload_url')

# 2. Upload file to presigned URL
curl -X PUT \
  "$UPLOAD_URL" \
  -H 'Content-Type: video/webm' \
  --data-binary @recording.webm
```

**Python (Step Artifact)**:
```python
import requests

# 1. Get presigned URL
response = requests.post(
    'https://api.example.com/usecase/usecase-123/executions/execution-456/steps/step-789/artifacts',
    headers={
        'Authorization': f'Bearer {jwt_token}',
        'Content-Type': 'application/json'
    },
    json={
        'filename': 'screenshot.png',
        'content_type': 'image/png'
    }
)

data = response.json()
upload_url = data['upload_url']
artifact_id = data['artifact_id']

# 2. Upload file to presigned URL
with open('screenshot.png', 'rb') as f:
    upload_response = requests.put(
        upload_url,
        headers={'Content-Type': 'image/png'},
        data=f
    )

print(f'Upload status: {upload_response.status_code}')
print(f'Artifact ID: {artifact_id}')
```

---

## Open Questions

### 1. Artifact Upload Confirmation

**Question**: Should we implement a mechanism to confirm artifact uploads and update the artifact record status?

**Options**:
- A) S3 event notification triggers Lambda to update status (recommended)
- B) Client calls separate endpoint to confirm upload
- C) No confirmation, status remains "pending"

**Recommendation**: Option A for v2.0 (out of scope for v1.0)

**Rationale**: S3 events provide reliable upload confirmation without client involvement

**Decision needed by**: Before v2.0 planning

---

### 2. Artifact Size Limits

**Question**: Should we enforce maximum artifact size limits?

**Options**:
- A) No limits (rely on S3 limits)
- B) Enforce limits in presigned URL (max-content-length)
- C) Validate size after upload

**Recommendation**: Option A for v1.0 (S3 has 5TB object limit)

**Rationale**: CI/CD recordings can be large, don't want to artificially limit

**Decision needed by**: Before implementation

---

### 3. Artifact Retention Policy

**Question**: How long should artifacts be retained in S3?

**Options**:
- A) Indefinite retention
- B) 90 days, then transition to Glacier
- C) 365 days, then delete

**Recommendation**: Option B (90 days hot, then Glacier)

**Rationale**: Balance cost and accessibility

**Decision needed by**: Before production deployment

---

## Success Criteria

- [ ] Execution artifact endpoint created
- [ ] Step artifact endpoint created
- [ ] Presigned URLs generated successfully
- [ ] Artifact records stored in DynamoDB
- [ ] S3 uploads work via presigned URLs
- [ ] Presigned URLs expire after 1 hour
- [ ] Content-Type enforced in presigned URLs
- [ ] OAuth scope validation working
- [ ] Unit test coverage ≥70%
- [ ] Integration tests pass
- [ ] API documentation updated
- [ ] S3 bucket CORS configured correctly
- [ ] Error handling working for all error scenarios

---

## References

- [WP1c Requirements Document](./requirements.md)
- [WP1a Design Document](../wp1a-execution-record-trigger-type/design.md)
- [WP1b Design Document](../wp1b-test-suite-execution-endpoint/design.md)
- [API Documentation](../../../docs/API.md)
- [Existing Lambda Utils](../../../lambdas/endpoints/utils.py)
- [DynamoDB Steering Rules](../../../.kiro/steering/01_dynamodb.md)
- [API Design Steering Rules](../../../.kiro/steering/02_api-design.md)
- [Security Steering Rules](../../../.kiro/steering/03_security.md)
- [AWS S3 Presigned URLs Documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html)

