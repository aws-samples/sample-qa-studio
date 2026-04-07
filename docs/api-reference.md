# API Reference

## Overview

Nova Act QA Studio provides a RESTful API for managing test automation workflows, including test execution, OAuth client management, and artifact handling. All endpoints require authentication via AWS Cognito and use OAuth 2.0 scopes for authorization.

**Base URL**: `https://{api-gateway-id}.execute-api.{region}.amazonaws.com/{stage}/`

**API Version**: 1.2.0

---

## Table of Contents

- [Authentication](#authentication)
  - [OAuth 2.0 Client Credentials Flow](#oauth-20-client-credentials-flow)
  - [Token Management](#token-management)
  - [OAuth Scopes](#oauth-scopes)
- [Usecase Management Endpoints](#usecase-management-endpoints)
  - [Create Usecase](#create-usecase)
  - [Get Usecase](#get-usecase)
  - [Update Usecase](#update-usecase)
  - [Get Usecase Steps](#get-usecase-steps)
- [Execution Endpoints](#execution-endpoints)
  - [Execute Usecase](#execute-usecase)
  - [Update Execution Step Status](#update-execution-step-status)
  - [Generate Execution Artifact Presigned URL](#generate-execution-artifact-presigned-url)
  - [Generate Step Artifact Presigned URL](#generate-step-artifact-presigned-url)
  - [Request Recording Download](#request-recording-download)
- [Device Farm Endpoints](#device-farm-endpoints)
  - [List Devices](#list-devices)
- [Test Suite Endpoints](#test-suite-endpoints)
  - [Execute Test Suite](#execute-test-suite)
- [OAuth Client Management](#oauth-client-management)
  - [Create OAuth Client](#create-oauth-client)
  - [List OAuth Clients](#list-oauth-clients)
  - [Delete OAuth Client](#delete-oauth-client)
  - [Rotate Client Secret](#rotate-client-secret)
- [Error Handling](#error-handling)
- [Rate Limiting](#rate-limiting)
- [Pagination](#pagination)

---

## Authentication

All API requests must include a valid JWT token in the Authorization header:

```http
Authorization: Bearer <jwt_token>
```

### OAuth 2.0 Client Credentials Flow

For CI/CD integration and machine-to-machine (M2M) authentication, use the OAuth 2.0 client credentials flow:

**Step 1: Create OAuth Client**

Create an OAuth client via the web UI or API (requires user authentication):


```bash
curl -X POST 'https://api.example.com/api/oauth-clients' \
  -H 'Authorization: Bearer <user_jwt_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "CI/CD Runner - Production",
    "scopes": ["api/suite.read", "api/suite.write", "api/execution.write"]
  }'
```

**Response**:
```json
{
  "client_id": "7abc123def456",
  "client_secret": "secret_xyz789...",
  "created_date": "2026-02-16T12:00:00Z"
}
```

**IMPORTANT**: Save the `client_secret` - it will only be shown once!

**Step 2: Obtain Access Token**

Use the client credentials to obtain an access token from Cognito:

```bash
curl -X POST \
  'https://{cognito-domain}.auth.{region}.amazoncognito.com/oauth2/token' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=client_credentials' \
  -d 'client_id=7abc123def456' \
  -d 'client_secret=secret_xyz789...' \
  -d 'scope=api/suite.read api/suite.write api/execution.write'
```

**Response**:
```json
{
  "access_token": "eyJraWQiOiJ...",
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

**Step 3: Use Access Token**

Include the access token in all API requests:

```bash
curl -X POST 'https://api.example.com/usecase/usecase-123/execute' \
  -H 'Authorization: Bearer eyJraWQiOiJ...' \
  -H 'Content-Type: application/json'
```


### Token Management

- **Token Lifetime**: Access tokens typically expire after 1 hour (3600 seconds)
- **Token Refresh**: No refresh tokens are issued for client credentials flow - request a new token when expired
- **Token Storage**: Store credentials securely using environment variables or secrets manager
- **Token Validation**: Tokens are validated on every API request

### OAuth Scopes

Scopes follow the pattern `api/{resource}.{permission}`:

| Scope | Description | Access Level |
|-------|-------------|--------------|
| `api/admin` | Full access to all resources | Admin |
| `api/execution.write` | Create and update executions | Write |
| `api/execution.read` | Read execution data | Read |
| `api/usecases.write` | Create and update usecases | Write |
| `api/usecases.read` | Read usecase data | Read |
| `api/suite.write` | Manage test suites | Write |
| `api/suite.read` | Read test suite data | Read |
| `api/oauth-clients.write` | Create, delete, and rotate OAuth clients | Write |
| `api/oauth-clients.read` | List OAuth clients | Read |

**Scope Requirements by Operation**:

| Operation | Required Scopes |
|-----------|----------------|
| Execute test suite | `api/suite.write`, `api/execution.write` |
| Read test suite | `api/suite.read` |
| Create execution | `api/execution.write` |
| Update step status | `api/execution.write` |
| Upload artifacts | `api/execution.write` |
| Read execution data | `api/execution.read` |
| Manage OAuth clients | `api/oauth-clients.write`, `api/oauth-clients.read` |

**Best Practice**: Grant only the minimum scopes required for your use case.

---

## Usecase Management Endpoints

Usecase management endpoints allow you to create, read, and update test usecases, including enabling step caching for performance optimization.

### Create Usecase

Create a new test usecase with optional step caching enabled.

**Endpoint**: `POST /usecases`

**Required Scopes**: `api/usecases.write` or `api/admin`

**Request Body**:
```json
{
  "name": "Login with valid credentials",
  "description": "Test user login flow with valid username and password",
  "steps": [
    {
      "type": "navigation",
      "url": "https://example.com/login",
      "description": "Navigate to login page"
    },
    {
      "type": "action",
      "action": "fill",
      "selector": "#username",
      "value": "testuser",
      "description": "Enter username"
    }
  ],
  "enableCache": true
}
```

**Request Body Fields**:
- `name` (string, required) - Usecase name
- `description` (string, optional) - Usecase description
- `steps` (array, required) - List of test steps
- `enableCache` (boolean, optional, default: false) - Enable step caching for navigation steps
- `test_platform` (string, optional, default: "web") - Test platform: `"web"` or `"mobile"`
- `platform` (string, optional) - Mobile platform: `"ANDROID"` or `"IOS"` (required when test_platform is "mobile")
- `app_package` (string, optional) - Android app package name (e.g., `"com.example.myapp"`)
- `app_activity` (string, optional) - Android app activity (e.g., `"com.example.myapp.MainActivity"`)
- `bundle_id` (string, optional) - iOS bundle identifier (e.g., `"com.example.myapp"`)
- `device_arn` (string, optional) - Device Farm device ARN (auto-selects newest device if omitted)

**Response (201 Created)**:
```json
{
  "id": "01234567-89ab-cdef-0123-456789abcdef",
  "name": "Login with valid credentials",
  "description": "Test user login flow with valid username and password",
  "enableCache": true,
  "created_at": "2026-03-03T10:00:00Z",
  "updated_at": "2026-03-03T10:00:00Z"
}
```

**Error Responses**:
- `400 Bad Request` - Missing required fields or invalid data
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Insufficient scopes
- `500 Internal Server Error` - Server error

**Example (cURL)**:
```bash
curl -X POST \
  'https://api.example.com/usecases' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Login with valid credentials",
    "description": "Test user login flow",
    "steps": [...],
    "enableCache": true
  }'
```

**Example (Python)**:
```python
import requests

response = requests.post(
    'https://api.example.com/usecases',
    headers={
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    },
    json={
        'name': 'Login with valid credentials',
        'description': 'Test user login flow',
        'steps': [...],
        'enableCache': True
    }
)

data = response.json()
usecase_id = data['id']
print(f"Usecase created: {usecase_id} (cache enabled: {data['enableCache']})")
```

---

### Get Usecase

Retrieve a usecase by ID, including cache status and metadata.

**Endpoint**: `GET /usecases/{id}`

**Path Parameters**:
- `id` (string, required) - Usecase ID

**Required Scopes**: `api/usecases.read` or `api/admin`

**Response (200 OK)**:
```json
{
  "id": "01234567-89ab-cdef-0123-456789abcdef",
  "name": "Login with valid credentials",
  "description": "Test user login flow with valid username and password",
  "enableCache": true,
  "created_at": "2026-03-03T10:00:00Z",
  "updated_at": "2026-03-03T10:15:00Z",
  "steps": [
    {
      "id": "step-001",
      "type": "navigation",
      "url": "https://example.com/login",
      "description": "Navigate to login page"
    }
  ]
}
```

**Response Fields**:
- `id` - Usecase unique identifier
- `name` - Usecase name
- `description` - Usecase description
- `enableCache` - Whether step caching is enabled
- `created_at` - ISO8601 timestamp of creation
- `updated_at` - ISO8601 timestamp of last update
- `steps` - List of test steps

**Error Responses**:
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Insufficient scopes
- `404 Not Found` - Usecase not found
- `500 Internal Server Error` - Server error

**Example (cURL)**:
```bash
curl -X GET \
  'https://api.example.com/usecases/01234567-89ab-cdef-0123-456789abcdef' \
  -H 'Authorization: Bearer <token>'
```

**Example (Python)**:
```python
import requests

response = requests.get(
    f'https://api.example.com/usecases/{usecase_id}',
    headers={'Authorization': f'Bearer {access_token}'}
)

data = response.json()
print(f"Usecase: {data['name']}")
print(f"Cache enabled: {data['enableCache']}")
```

---

### Update Usecase

Update an existing usecase, including enabling or disabling step caching.

**Endpoint**: `PATCH /usecases/{id}`

**Path Parameters**:
- `id` (string, required) - Usecase ID

**Required Scopes**: `api/usecases.write` or `api/admin`

**Request Body**:
```json
{
  "name": "Login with valid credentials (updated)",
  "description": "Updated description",
  "enableCache": true
}
```

**Request Body Fields** (all optional):
- `name` (string) - Updated usecase name
- `description` (string) - Updated description
- `steps` (array) - Updated test steps
- `enableCache` (boolean) - Enable or disable step caching

**Response (200 OK)**:
```json
{
  "id": "01234567-89ab-cdef-0123-456789abcdef",
  "name": "Login with valid credentials (updated)",
  "description": "Updated description",
  "enableCache": true,
  "updated_at": "2026-03-03T10:30:00Z"
}
```

**Error Responses**:
- `400 Bad Request` - Invalid data
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Insufficient scopes
- `404 Not Found` - Usecase not found
- `500 Internal Server Error` - Server error

**Example (cURL)**:
```bash
curl -X PATCH \
  'https://api.example.com/usecases/01234567-89ab-cdef-0123-456789abcdef' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "enableCache": true
  }'
```

**Example (Python)**:
```python
import requests

response = requests.patch(
    f'https://api.example.com/usecases/{usecase_id}',
    headers={
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    },
    json={'enableCache': True}
)

data = response.json()
print(f"Cache enabled: {data['enableCache']}")
```

---

### Get Usecase Steps

Retrieve all steps for a usecase, including cache metadata for cached steps.

**Endpoint**: `GET /usecases/{id}/steps`

**Path Parameters**:
- `id` (string, required) - Usecase ID

**Required Scopes**: `api/usecases.read` or `api/admin`

**Response (200 OK)**:
```json
{
  "usecase_id": "01234567-89ab-cdef-0123-456789abcdef",
  "steps": [
    {
      "id": "step-001",
      "sort": 1,
      "type": "navigation",
      "url": "https://example.com/login",
      "description": "Navigate to login page",
      "cacheable": true
    },
    {
      "id": "step-002",
      "sort": 2,
      "type": "action",
      "action": "fill",
      "selector": "#username",
      "value": "testuser",
      "description": "Enter username",
      "cacheable": false
    }
  ],
  "cachedSteps": "[{\"action\":\"goto\",\"url\":\"https://example.com/login\",\"options\":{\"waitUntil\":\"networkidle\"}}]",
  "cacheLastUpdated": "2026-03-03T10:15:00Z"
}
```

**Response Fields**:
- `usecase_id` - Usecase unique identifier
- `steps` - List of test steps with metadata
  - `cacheable` - Whether this step type can be cached (navigation steps only)
- `cachedSteps` - JSON string of cached Playwright actions (null if no cache)
- `cacheLastUpdated` - ISO8601 timestamp when cache was last built (null if no cache)

**Error Responses**:
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Insufficient scopes
- `404 Not Found` - Usecase not found
- `500 Internal Server Error` - Server error

**Example (cURL)**:
```bash
curl -X GET \
  'https://api.example.com/usecases/01234567-89ab-cdef-0123-456789abcdef/steps' \
  -H 'Authorization: Bearer <token>'
```

**Example (Python)**:
```python
import requests
import json

response = requests.get(
    f'https://api.example.com/usecases/{usecase_id}/steps',
    headers={'Authorization': f'Bearer {access_token}'}
)

data = response.json()
print(f"Total steps: {len(data['steps'])}")

if data['cachedSteps']:
    cached_actions = json.loads(data['cachedSteps'])
    print(f"Cached actions: {len(cached_actions)}")
    print(f"Cache last updated: {data['cacheLastUpdated']}")
else:
    print("No cache available")
```

---

### Cache Field Reference

The following table summarizes all cache-related fields across usecase endpoints:

| Field | Type | Default | Endpoints | Description |
|-------|------|---------|-----------|-------------|
| `enableCache` | boolean | false | POST /usecases, PATCH /usecases, GET /usecases | Whether step caching is enabled for this usecase |
| `cachedSteps` | string (JSON) | null | GET /usecases/{id}/steps | JSON-serialized list of cached Playwright actions |
| `cacheLastUpdated` | string (ISO8601) | null | GET /usecases/{id}/steps | Timestamp when cache was last built |
| `cacheable` | boolean | - | GET /usecases/{id}/steps | Whether a specific step type can be cached (read-only, computed field) |

**Cache Building Process**:
1. Usecase executes successfully with `enableCache: true`
2. EventBridge triggers cache builder Lambda asynchronously
3. Lambda parses Nova Act responses from S3
4. Lambda stores cached Playwright actions in DynamoDB
5. Subsequent executions use cached actions for navigation steps

**Cache Execution Behavior**:
- First execution: Cache miss (normal execution time)
- Subsequent executions: Cache hit (40-60% faster for navigation steps)
- Cache failures: Automatic fallback to Nova Act

**Notes**:
- Only navigation steps are cacheable (goto, goBack, goForward, reload)
- Cache builds asynchronously after successful execution
- Cache is invalidated when usecase steps are modified
- Cache execution failures automatically fall back to Nova Act

---

## Execution Endpoints

### Execute Usecase

Create and start a usecase execution.

**Endpoint**: `POST /usecase/{id}/execute`

**Path Parameters**:
- `id` (string, required) - Usecase ID

**Query Parameters**:
- `trigger-type` (string, optional) - Execution trigger type
  - `OnDemand` (default) - Queue execution for worker processing
  - `Scheduled` - Direct ECS task execution (used by EventBridge)
  - `OnDemandHeadless` - Direct ECS task execution (used by UI)
  - `ci_runner` - Create execution record only, no ECS task (for CI/CD)
- `suite-execution-id` (string, optional) - Suite execution ID if part of a suite
- `suite-id` (string, optional) - Suite ID if part of a suite

**Required Scopes**: `api/execution.write` or `api/admin`

**Request Body**: None


**Response (OnDemand)**:
```json
{
  "status": "usecase queued",
  "usecaseId": "usecase-123"
}
```

**Response (Scheduled/OnDemandHeadless)**:
```json
{
  "status": "task started",
  "usecaseId": "usecase-123",
  "executionId": "execution-456",
  "taskArn": "arn:aws:ecs:us-east-1:123456789:task/cluster/task-id",
  "taskId": "task-id",
  "cloudWatchLogsUrl": "https://console.aws.amazon.com/cloudwatch/..."
}
```

**Response (ci_runner)**:
```json
{
  "status": "execution created",
  "usecaseId": "usecase-123",
  "executionId": "execution-456"
}
```

**Error Responses**:
- `400 Bad Request` - Missing usecase ID or invalid trigger type
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Insufficient scopes
- `404 Not Found` - Usecase not found
- `500 Internal Server Error` - Server error

**Example (cURL)**:
```bash
curl -X POST \
  'https://api.example.com/usecase/usecase-123/execute?trigger-type=ci_runner' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json'
```

**Example (Python)**:
```python
import requests

response = requests.post(
    'https://api.example.com/usecase/usecase-123/execute',
    params={'trigger-type': 'ci_runner'},
    headers={
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
)

data = response.json()
execution_id = data['executionId']
print(f"Execution created: {execution_id}")
```

**Example (JavaScript)**:
```javascript
const response = await fetch(
  'https://api.example.com/usecase/usecase-123/execute?trigger-type=ci_runner',
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    }
  }
);

const data = await response.json();
console.log(`Execution created: ${data.executionId}`);
```

---

### Update Execution Step Status

Update the status of an individual execution step. Used by CI/CD runners to report step progress.

**Endpoint**: `PATCH /usecase/{id}/executions/{executionId}/steps/{stepId}/status`

**Path Parameters**:
- `id` (string, required) - Usecase ID
- `executionId` (string, required) - Execution ID
- `stepId` (string, required) - Step ID

**Required Scopes**: `api/execution.write` or `api/admin`

**Request Body**:
```json
{
  "status": "running",
  "started_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:35:00Z",
  "error_message": "Element not found"
}
```

**Request Body Fields**:
- `status` (string, required) - Step status
  - Valid values: `pending`, `running`, `completed`, `failed`, `skipped`
- `started_at` (string, optional) - ISO8601 timestamp when step started
- `completed_at` (string, optional) - ISO8601 timestamp when step completed
- `error_message` (string, optional) - Error message for failed steps

**Response**:
```json
{
  "success": true,
  "step_id": "step-789",
  "status": "running"
}
```

**Error Responses**:
- `400 Bad Request` - Invalid status value or missing required fields
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Insufficient scopes
- `404 Not Found` - Execution or step not found
- `500 Internal Server Error` - Server error

**Example (cURL)**:
```bash
curl -X PATCH \
  'https://api.example.com/usecase/usecase-123/executions/execution-456/steps/step-789/status' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "status": "completed",
    "started_at": "2024-01-15T10:30:00Z",
    "completed_at": "2024-01-15T10:35:00Z"
  }'
```

**Example (Python)**:
```python
import requests
from datetime import datetime

response = requests.patch(
    f'https://api.example.com/usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/status',
    headers={
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    },
    json={
        'status': 'completed',
        'started_at': datetime.utcnow().isoformat() + 'Z',
        'completed_at': datetime.utcnow().isoformat() + 'Z'
    }
)

print(f"Step status updated: {response.json()}")
```

**Example (JavaScript)**:
```javascript
const response = await fetch(
  `https://api.example.com/usecase/${usecaseId}/executions/${executionId}/steps/${stepId}/status`,
  {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      status: 'completed',
      started_at: new Date().toISOString(),
      completed_at: new Date().toISOString()
    })
  }
);

const data = await response.json();
console.log('Step status updated:', data);
```

---

### Generate Execution Artifact Presigned URL

Generate a presigned S3 URL for uploading execution-level artifacts (recording, logs). This allows CI/CD runners to upload large files directly to S3, bypassing API Gateway payload limits.

**Endpoint**: `POST /usecase/{id}/executions/{executionId}/artifacts`

**Path Parameters**:
- `id` (string, required) - Usecase ID
- `executionId` (string, required) - Execution ID

**Required Scopes**: `api/execution.write` or `api/admin`

**Request Body**:
```json
{
  "type": "recording",
  "filename": "recording.webm",
  "content_type": "video/webm"
}
```

**Request Body Fields**:
- `type` (string, required) - Artifact type
  - Valid values: `recording`, `logs`
- `filename` (string, required) - Original filename
- `content_type` (string, required) - MIME type
  - For recording: `video/webm`, `video/mp4`
  - For logs: `text/plain`

**Response**:
```json
{
  "artifact_id": "01933d7e-8f2a-7890-abcd-ef1234567890",
  "upload_url": "https://s3.amazonaws.com/bucket/artifacts/usecase-123/executions/execution-456/recording.webm?X-Amz-Algorithm=...",
  "expires_in": 3600,
  "s3_key": "artifacts/usecase-123/executions/execution-456/recording.webm"
}
```

**Response Fields**:
- `artifact_id` - Unique artifact identifier
- `upload_url` - Presigned S3 URL for uploading (expires in 1 hour)
- `expires_in` - URL expiration time in seconds
- `s3_key` - S3 object key where file will be stored

**Error Responses**:
- `400 Bad Request` - Invalid artifact type, missing fields, or invalid content type
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Insufficient scopes
- `404 Not Found` - Execution not found
- `500 Internal Server Error` - Server error

**Example (cURL)**:
```bash
# Step 1: Get presigned URL
RESPONSE=$(curl -X POST \
  'https://api.example.com/usecase/usecase-123/executions/execution-456/artifacts' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "recording",
    "filename": "recording.webm",
    "content_type": "video/webm"
  }')

UPLOAD_URL=$(echo $RESPONSE | jq -r '.upload_url')

# Step 2: Upload file to S3 using presigned URL
curl -X PUT "$UPLOAD_URL" \
  -H 'Content-Type: video/webm' \
  --data-binary @recording.webm
```

**Example (Python)**:
```python
import requests

# Step 1: Get presigned URL
response = requests.post(
    f'https://api.example.com/usecase/{usecase_id}/executions/{execution_id}/artifacts',
    headers={
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    },
    json={
        'type': 'recording',
        'filename': 'recording.webm',
        'content_type': 'video/webm'
    }
)

data = response.json()
upload_url = data['upload_url']

# Step 2: Upload file to S3
with open('recording.webm', 'rb') as f:
    upload_response = requests.put(
        upload_url,
        headers={'Content-Type': 'video/webm'},
        data=f
    )

print(f"Upload status: {upload_response.status_code}")
```

**Example (JavaScript)**:
```javascript
// Step 1: Get presigned URL
const response = await fetch(
  `https://api.example.com/usecase/${usecaseId}/executions/${executionId}/artifacts`,
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      type: 'recording',
      filename: 'recording.webm',
      content_type: 'video/webm'
    })
  }
);

const data = await response.json();

// Step 2: Upload file to S3
const uploadResponse = await fetch(data.upload_url, {
  method: 'PUT',
  headers: {
    'Content-Type': 'video/webm'
  },
  body: recordingBlob
});

console.log(`Upload status: ${uploadResponse.status}`);
```

---

### Generate Step Artifact Presigned URL

Generate a presigned S3 URL for uploading step-level artifacts (screenshots, traces). This allows CI/CD runners to upload step-specific files directly to S3.

**Endpoint**: `POST /usecase/{id}/executions/{executionId}/steps/{stepId}/artifacts`

**Path Parameters**:
- `id` (string, required) - Usecase ID
- `executionId` (string, required) - Execution ID
- `stepId` (string, required) - Step ID

**Required Scopes**: `api/execution.write` or `api/admin`

**Request Body**:
```json
{
  "filename": "screenshot.png",
  "content_type": "image/png"
}
```

**Request Body Fields**:
- `filename` (string, required) - Original filename
- `content_type` (string, required) - MIME type
  - For screenshots: `image/png`, `image/jpeg`
  - For traces: `application/json`

**Response**:
```json
{
  "artifact_id": "01933d7e-8f2a-7890-abcd-ef1234567890",
  "upload_url": "https://s3.amazonaws.com/bucket/artifacts/usecase-123/executions/execution-456/steps/step-789/screenshot.png?X-Amz-Algorithm=...",
  "expires_in": 3600,
  "s3_key": "artifacts/usecase-123/executions/execution-456/steps/step-789/screenshot.png"
}
```

**Error Responses**:
- `400 Bad Request` - Missing fields or invalid content type
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Insufficient scopes
- `404 Not Found` - Execution or step not found
- `500 Internal Server Error` - Server error

**Example (cURL)**:
```bash
# Step 1: Get presigned URL
RESPONSE=$(curl -X POST \
  'https://api.example.com/usecase/usecase-123/executions/execution-456/steps/step-789/artifacts' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "filename": "screenshot.png",
    "content_type": "image/png"
  }')

UPLOAD_URL=$(echo $RESPONSE | jq -r '.upload_url')

# Step 2: Upload file to S3 using presigned URL
curl -X PUT "$UPLOAD_URL" \
  -H 'Content-Type: image/png' \
  --data-binary @screenshot.png
```

**Example (Python)**:
```python
import requests

# Step 1: Get presigned URL
response = requests.post(
    f'https://api.example.com/usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/artifacts',
    headers={
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    },
    json={
        'filename': 'screenshot.png',
        'content_type': 'image/png'
    }
)

data = response.json()
upload_url = data['upload_url']

# Step 2: Upload file to S3
with open('screenshot.png', 'rb') as f:
    upload_response = requests.put(
        upload_url,
        headers={'Content-Type': 'image/png'},
        data=f
    )

print(f"Upload status: {upload_response.status_code}")
```

**Example (JavaScript)**:
```javascript
// Step 1: Get presigned URL
const response = await fetch(
  `https://api.example.com/usecase/${usecaseId}/executions/${executionId}/steps/${stepId}/artifacts`,
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      filename: 'screenshot.png',
      content_type: 'image/png'
    })
  }
);

const data = await response.json();

// Step 2: Upload file to S3
const uploadResponse = await fetch(data.upload_url, {
  method: 'PUT',
  headers: {
    'Content-Type': 'image/png'
  },
  body: screenshotBlob
});

console.log(`Upload status: ${uploadResponse.status}`);
```

---

### Request Recording Download

Request an asynchronous download of the Device Farm session recording for a mobile execution. The recording is downloaded from Device Farm and uploaded to S3 after a 5-minute delay (to allow Device Farm to finalize the session).

**Endpoint**: `POST /usecase/{id}/executions/{executionId}/download-recording`

**Path Parameters**:
- `id` (string, required) - Usecase ID
- `executionId` (string, required) - Execution ID

**Required Scopes**: `api/executions.write` or `api/admin`

**Request Body**:
```json
{
  "session_arn": "arn:aws:devicefarm:us-west-2:123456789:session:project-id/session-id/00000",
  "nova_session_id": "019d1234-5678-abcd-ef01-234567890abc"
}
```

**Request Body Fields**:
- `session_arn` (string, required) - Device Farm remote access session ARN
- `nova_session_id` (string, optional) - Nova Act session ID (defaults to execution ID)

**Response (200 OK)**:
```json
{
  "message": "Recording download requested",
  "delay_seconds": 300
}
```

**Example (cURL)**:
```bash
curl -X POST \
  'https://api.example.com/api/usecase/usecase-123/executions/execution-456/download-recording' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "session_arn": "arn:aws:devicefarm:us-west-2:123456789:session:project-id/session-id/00000"
  }'
```

---

## Device Farm Endpoints

### List Devices

List available AWS Device Farm devices for mobile testing. Returns devices with remote access enabled, filtered by platform.

**Endpoint**: `GET /devices`

**Query Parameters**:
- `platform` (string, optional) - Filter by platform: `"ANDROID"` or `"IOS"`

**Required Scopes**: `api/usecases.read` or `api/admin`

**Response (200 OK)**:
```json
{
  "devices": [
    {
      "arn": "arn:aws:devicefarm:us-west-2::device:ABC123",
      "name": "Apple iPhone 15",
      "platform": "IOS",
      "os": "18.0",
      "formFactor": "PHONE",
      "manufacturer": "Apple",
      "modelId": "iPhone15",
      "availability": "HIGHLY_AVAILABLE"
    }
  ]
}
```

**Response Fields**:
- `arn` - Device Farm device ARN (use this as `device_arn` when creating a usecase)
- `name` - Device display name
- `platform` - `"ANDROID"` or `"IOS"`
- `os` - Operating system version
- `formFactor` - `"PHONE"` or `"TABLET"`
- `manufacturer` - Device manufacturer
- `availability` - `"HIGHLY_AVAILABLE"`, `"AVAILABLE"`, or `"BUSY"`

**Example (cURL)**:
```bash
curl -X GET \
  'https://api.example.com/api/devices?platform=IOS' \
  -H 'Authorization: Bearer <token>'
```

---

## Test Suite Endpoints

### Execute Test Suite

Create a suite execution record and execution records for all usecases in a test suite with overrides applied. This endpoint is designed for CI/CD runners and does not spawn ECS tasks.

**Endpoint**: `POST /test-suites/{id}/execute`

**Path Parameters**:
- `id` (string, required) - Test suite UUID

**Required Scopes**: `api/suite.write`, `api/execution.write`

**Request Body**:
```json
{
  "trigger_type": "ci_runner",
  "base_url": "https://example.com",
  "variables": {
    "username": "testuser",
    "api_key": "secret123"
  },
  "region": "us-east-1",
  "model_id": "us.amazon.nova-2-lite-v1:0"
}
```

**Request Body Schema**:
- `trigger_type` (string, required) - Must be "ci_runner"
- `base_url` (string, optional) - Base URL override for all usecases. Replaces domain/origin while preserving path and query parameters
- `variables` (object, optional) - Variable overrides (key-value pairs). Precedence: CLI > usecase > secrets
- `region` (string, optional) - AWS region override for all executions
- `model_id` (string, optional) - Bedrock model ID override for all executions

**Response (200 OK)**:
```json
{
  "suite_execution_id": "01234567-89ab-cdef-0123-456789abcdef",
  "suite_id": "01234567-89ab-cdef-0123-456789abcdef",
  "status": "pending",
  "created_at": "2024-02-16T12:00:00Z",
  "execution_ids": [
    {
      "usecase_id": "01234567-89ab-cdef-0123-456789abcdef",
      "execution_id": "01234567-89ab-cdef-0123-456789abcdef",
      "usecase_name": "Login with valid credentials"
    },
    {
      "usecase_id": "01234567-89ab-cdef-0123-456789abcdef",
      "execution_id": "01234567-89ab-cdef-0123-456789abcdef",
      "usecase_name": "Login with invalid password"
    }
  ]
}
```

**Error Responses**:

**400 Bad Request** - Invalid input or unresolved variables:
```json
{
  "error": "Unresolved variables",
  "message": "Unresolved variables: username, password",
  "details": {
    "usecase_id": "01234567-89ab-cdef-0123-456789abcdef",
    "usecase_name": "Login test"
  }
}
```

**403 Forbidden** - Insufficient permissions:
```json
{
  "error": "Forbidden",
  "message": "Missing required scopes: api/suite.write, api/execution.write",
  "required_scopes": ["api/suite.write", "api/execution.write"],
  "token_scopes": ["api/suite.read"]
}
```

**404 Not Found** - Test suite not found:
```json
{
  "error": "Test suite not found",
  "message": "No test suite found with ID: 01234567-89ab-cdef-0123-456789abcdef"
}
```

**500 Internal Server Error** - Database or system error:
```json
{
  "error": "Failed to execute test suite",
  "message": "Error details"
}
```


**Example (cURL)**:
```bash
curl -X POST \
  'https://api.example.com/test-suites/01234567-89ab-cdef-0123-456789abcdef/execute' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "trigger_type": "ci_runner",
    "base_url": "https://production.example.com",
    "variables": {
      "username": "prod_user",
      "api_key": "prod_key_123"
    },
    "region": "us-west-2",
    "model_id": "us.amazon.nova-2-lite-v1:0"
  }'
```

**Example (Python)**:
```python
import requests

response = requests.post(
    'https://api.example.com/test-suites/01234567-89ab-cdef-0123-456789abcdef/execute',
    headers={
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    },
    json={
        'trigger_type': 'ci_runner',
        'base_url': 'https://production.example.com',
        'variables': {
            'username': 'prod_user',
            'api_key': 'prod_key_123'
        },
        'region': 'us-west-2',
        'model_id': 'us.amazon.nova-2-lite-v1:0'
    }
)

data = response.json()
suite_execution_id = data['suite_execution_id']
execution_ids = data['execution_ids']

print(f"Suite execution created: {suite_execution_id}")
print(f"Created {len(execution_ids)} executions")
```

**Example (JavaScript)**:
```javascript
const response = await fetch(
  'https://api.example.com/test-suites/01234567-89ab-cdef-0123-456789abcdef/execute',
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      trigger_type: 'ci_runner',
      base_url: 'https://production.example.com',
      variables: {
        username: 'prod_user',
        api_key: 'prod_key_123'
      },
      region: 'us-west-2',
      model_id: 'us.amazon.nova-2-lite-v1:0'
    })
  }
);

const data = await response.json();
console.log(`Suite execution created: ${data.suite_execution_id}`);
console.log(`Created ${data.execution_ids.length} executions`);
```

**Notes**:
- No ECS tasks are spawned when using `trigger_type=ci_runner`
- All execution records are created with `status=pending`
- Base URL override replaces only the scheme and domain, preserving path and query parameters
- Variable merge precedence: CLI overrides > usecase variables > secrets
- Maximum recommended suite size: 10 usecases (to avoid API Gateway timeout)

---

## OAuth Client Management

OAuth clients enable machine-to-machine (M2M) authentication for CI/CD pipelines and automated systems. Clients use the OAuth 2.0 client credentials flow and are scoped to specific API permissions.

### Create OAuth Client

Create a new OAuth client with specified scopes for CI/CD authentication.

**Endpoint**: `POST /api/oauth-clients`

**Required Scopes**: `api/oauth-clients.write` or `api/admin`

**Request Body**:
```json
{
  "name": "CI/CD Runner - Production",
  "scopes": [
    "api/suite.read",
    "api/suite.write",
    "api/execution.write"
  ]
}
```

**Request Body Fields**:
- `name` (string, required) - Client name for identification
- `scopes` (array, required) - List of OAuth scopes to grant
  - User can only grant scopes they possess (unless admin)
  - Valid scopes: `api/suite.read`, `api/suite.write`, `api/execution.read`, `api/execution.write`, `api/oauth-clients.read`, `api/oauth-clients.write`, `api/admin`

**Response (201 Created)**:
```json
{
  "client_id": "7abc123def456",
  "client_secret": "secret_xyz789...",
  "client_name": "CI/CD Runner - Production",
  "scopes": [
    "api/suite.read",
    "api/suite.write",
    "api/execution.write"
  ],
  "created_date": "2026-02-16T12:00:00Z",
  "created_by": "user@example.com",
  "refresh_token_validity": 30,
  "access_token_validity": 60,
  "id_token_validity": 60
}
```

**Response Fields**:
- `client_id` - Unique client identifier for authentication
- `client_secret` - Client secret (ONLY shown once, cannot be retrieved later)
- `client_name` - Client name
- `scopes` - Granted OAuth scopes
- `created_date` - ISO8601 timestamp of creation
- `created_by` - User who created the client
- Token validity fields in minutes/days

**Error Responses**:
- `400 Bad Request` - Invalid scopes, missing name, or invalid request format
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Insufficient scopes or privilege escalation attempt
- `429 Too Many Requests` - Too many OAuth clients
- `500 Internal Server Error` - Server error

**Example (cURL)**:
```bash
curl -X POST \
  'https://api.example.com/api/oauth-clients' \
  -H 'Authorization: Bearer <jwt_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "CI/CD Runner - Production",
    "scopes": [
      "api/suite.read",
      "api/suite.write",
      "api/execution.write"
    ]
  }'
```

**Example (Python)**:
```python
import requests

response = requests.post(
    'https://api.example.com/api/oauth-clients',
    headers={
        'Authorization': f'Bearer {jwt_token}',
        'Content-Type': 'application/json'
    },
    json={
        'name': 'CI/CD Runner - Production',
        'scopes': [
            'api/suite.read',
            'api/suite.write',
            'api/execution.write'
        ]
    }
)

data = response.json()
client_id = data['client_id']
client_secret = data['client_secret']  # Save this - it won't be shown again!

print(f"Client ID: {client_id}")
print(f"Client Secret: {client_secret}")
```

**Example (JavaScript)**:
```javascript
const response = await fetch('https://api.example.com/api/oauth-clients', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${jwtToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    name: 'CI/CD Runner - Production',
    scopes: [
      'api/suite.read',
      'api/suite.write',
      'api/execution.write'
    ]
  })
});

const data = await response.json();
console.log(`Client ID: ${data.client_id}`);
console.log(`Client Secret: ${data.client_secret}`); // Save this!
```

**Security Notes**:
- Client secret is ONLY returned at creation - save it securely
- Users cannot grant scopes they don't possess (prevents privilege escalation)
- Admin users can grant any scope

---

### List OAuth Clients

List all OAuth clients in the user pool with metadata.

**Endpoint**: `GET /api/oauth-clients`

**Required Scopes**: `api/oauth-clients.read` or `api/admin`

**Response (200 OK)**:
```json
{
  "clients": [
    {
      "client_id": "7abc123def456",
      "client_name": "CI/CD Runner - Production",
      "created_date": "2026-02-16T12:00:00Z",
      "last_modified_date": "2026-02-16T12:00:00Z",
      "created_by": "user@example.com",
      "allowed_oauth_scopes": [
        "api/suite.read",
        "api/suite.write",
        "api/execution.write"
      ],
      "refresh_token_validity": 30,
      "access_token_validity": 60,
      "id_token_validity": 60,
      "enabled": true
    }
  ],
  "count": 1
}
```

**Error Responses**:
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Insufficient scopes
- `500 Internal Server Error` - Server error

**Example (cURL)**:
```bash
curl -X GET \
  'https://api.example.com/api/oauth-clients' \
  -H 'Authorization: Bearer <jwt_token>'
```

**Example (Python)**:
```python
import requests

response = requests.get(
    'https://api.example.com/api/oauth-clients',
    headers={'Authorization': f'Bearer {jwt_token}'}
)

data = response.json()
print(f"Found {data['count']} OAuth clients")
for client in data['clients']:
    print(f"  - {client['client_name']} ({client['client_id']})")
```

**Example (JavaScript)**:
```javascript
const response = await fetch('https://api.example.com/api/oauth-clients', {
  headers: {
    'Authorization': `Bearer ${jwtToken}`
  }
});

const data = await response.json();
console.log(`Found ${data.count} OAuth clients`);
data.clients.forEach(client => {
  console.log(`  - ${client.client_name} (${client.client_id})`);
});
```

**Security Notes**:
- Client secrets are NEVER returned in list responses
- Only shows clients created through the application (with metadata)

---

### Delete OAuth Client

Delete an OAuth client, immediately revoking its credentials.

**Endpoint**: `DELETE /api/oauth-clients/{clientId}`

**Path Parameters**:
- `clientId` (string, required) - OAuth client ID to delete

**Required Scopes**: `api/oauth-clients.write` or `api/admin`

**Response (200 OK)**:
```json
{
  "message": "OAuth client deleted successfully",
  "client_id": "7abc123def456"
}
```

**Error Responses**:
- `400 Bad Request` - Missing client ID
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Client not created through application or insufficient permissions
- `404 Not Found` - Client not found
- `500 Internal Server Error` - Server error

**Example (cURL)**:
```bash
curl -X DELETE \
  'https://api.example.com/api/oauth-clients/7abc123def456' \
  -H 'Authorization: Bearer <jwt_token>'
```

**Example (Python)**:
```python
import requests

response = requests.delete(
    'https://api.example.com/api/oauth-clients/7abc123def456',
    headers={'Authorization': f'Bearer {jwt_token}'}
)

if response.status_code == 200:
    print("OAuth client deleted successfully")
```

**Example (JavaScript)**:
```javascript
const response = await fetch(
  'https://api.example.com/api/oauth-clients/7abc123def456',
  {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${jwtToken}`
    }
  }
);

if (response.ok) {
  console.log('OAuth client deleted successfully');
}
```

**Security Notes**:
- Deletion is immediate - client cannot authenticate after deletion
- Only clients with metadata (created through application) can be deleted
- Users can only delete clients they created (unless admin)

---

### Rotate Client Secret

Generate a new client secret by recreating the OAuth client. Old secret is immediately invalidated.

**Endpoint**: `POST /api/oauth-clients/{clientId}/rotate-secret`

**Path Parameters**:
- `clientId` (string, required) - OAuth client ID to rotate

**Required Scopes**: `api/oauth-clients.write` or `api/admin`

**Response (200 OK)**:
```json
{
  "client_id": "8def456ghi789",
  "client_secret": "new_secret_abc123...",
  "rotated_at": "2026-02-16T15:00:00Z"
}
```

**Response Fields**:
- `client_id` - New client ID (changes during rotation)
- `client_secret` - New client secret (ONLY shown once, cannot be retrieved later)
- `rotated_at` - ISO8601 timestamp of rotation

**Error Responses**:
- `400 Bad Request` - Missing client ID
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - User doesn't own client or insufficient permissions
- `404 Not Found` - Client not found
- `500 Internal Server Error` - Server error

**Example (cURL)**:
```bash
curl -X POST \
  'https://api.example.com/api/oauth-clients/7abc123def456/rotate-secret' \
  -H 'Authorization: Bearer <jwt_token>' \
  -H 'Content-Type: application/json'
```

**Example (Python)**:
```python
import requests

response = requests.post(
    'https://api.example.com/api/oauth-clients/7abc123def456/rotate-secret',
    headers={
        'Authorization': f'Bearer {jwt_token}',
        'Content-Type': 'application/json'
    }
)

data = response.json()
new_client_id = data['client_id']
new_client_secret = data['client_secret']  # Save this - it won't be shown again!

print(f"New Client ID: {new_client_id}")
print(f"New Client Secret: {new_client_secret}")
print(f"Rotated at: {data['rotated_at']}")
```

**Example (JavaScript)**:
```javascript
const response = await fetch(
  'https://api.example.com/api/oauth-clients/7abc123def456/rotate-secret',
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'Content-Type': 'application/json'
    }
  }
);

const data = await response.json();
console.log(`New Client ID: ${data.client_id}`);
console.log(`New Client Secret: ${data.client_secret}`); // Save this!
console.log(`Rotated at: ${data.rotated_at}`);
```

**Security Notes**:
- Old secret is immediately invalidated - update all systems using the client
- Client ID changes during rotation - update configuration accordingly
- New secret is ONLY shown once - save it securely
- Users can only rotate secrets for clients they created (unless admin)

**Implementation Notes**:
- Cognito doesn't support in-place secret rotation
- Rotation deletes and recreates the app client with same settings
- All configuration (scopes, token validity) is preserved

---

## Error Handling

### Standard Error Response Format

All error responses follow this consistent format:

```json
{
  "error": "Error type or category",
  "message": "Detailed error description",
  "required_scopes": ["api/execution.write"],
  "token_scopes": ["api/execution.read"]
}
```

**Error Response Fields**:
- `error` - Short error type or category
- `message` - Detailed human-readable error description
- `required_scopes` (optional) - Scopes required for the operation (403 errors)
- `token_scopes` (optional) - Scopes present in the token (403 errors)
- `details` (optional) - Additional context-specific error details

### HTTP Status Codes

| Status Code | Description | Common Causes |
|-------------|-------------|---------------|
| `200 OK` | Request succeeded | Successful GET, PATCH, POST operations |
| `201 Created` | Resource created successfully | Successful POST operations creating new resources |
| `204 No Content` | Successful deletion | Successful DELETE operations |
| `400 Bad Request` | Invalid input | Missing required fields, invalid values, malformed JSON |
| `401 Unauthorized` | Authentication failed | Missing token, expired token, invalid token |
| `403 Forbidden` | Insufficient permissions | Missing required scopes, privilege escalation attempt |
| `404 Not Found` | Resource not found | Invalid ID, deleted resource, wrong endpoint |
| `429 Too Many Requests` | Rate limit exceeded | Too many requests in short time period |
| `500 Internal Server Error` | Server error | Database errors, AWS service errors, unexpected exceptions |

### Common Error Scenarios

#### Authentication Errors (401)

**Missing Authorization Header**:
```json
{
  "error": "Unauthorized",
  "message": "Missing Authorization header"
}
```

**Invalid or Expired Token**:
```json
{
  "error": "Unauthorized",
  "message": "Invalid or expired token"
}
```

**Solution**: Obtain a new access token using the OAuth 2.0 client credentials flow.

#### Authorization Errors (403)

**Insufficient Scopes**:
```json
{
  "error": "Forbidden",
  "message": "Missing required scopes: api/suite.write, api/execution.write",
  "required_scopes": ["api/suite.write", "api/execution.write"],
  "token_scopes": ["api/suite.read"]
}
```

**Solution**: Request an OAuth client with the required scopes or use a token with sufficient permissions.

**Privilege Escalation Attempt**:
```json
{
  "error": "Forbidden",
  "message": "Cannot grant scopes that you don't possess: api/admin"
}
```

**Solution**: Only grant scopes that your user account possesses, or contact an administrator.

#### Validation Errors (400)

**Missing Required Fields**:
```json
{
  "error": "Bad Request",
  "message": "Missing required field: name"
}
```

**Invalid Field Values**:
```json
{
  "error": "Bad Request",
  "message": "Invalid status value: invalid_status. Valid values: pending, running, completed, failed, skipped"
}
```

**Unresolved Variables**:
```json
{
  "error": "Unresolved variables",
  "message": "Unresolved variables: username, password",
  "details": {
    "usecase_id": "01234567-89ab-cdef-0123-456789abcdef",
    "usecase_name": "Login test"
  }
}
```

**Solution**: Provide all required variables via the `variables` parameter.

#### Resource Not Found (404)

```json
{
  "error": "Test suite not found",
  "message": "No test suite found with ID: 01234567-89ab-cdef-0123-456789abcdef"
}
```

**Solution**: Verify the resource ID is correct and the resource exists.

#### Rate Limiting (429)

```json
{
  "error": "Too Many Requests",
  "message": "Rate limit exceeded. Please retry after 60 seconds."
}
```

**Solution**: Implement exponential backoff and retry logic in your client.

---

## Rate Limiting

API Gateway enforces the following rate limits to ensure fair usage and system stability:

**Limits**:
- **Burst Capacity**: 5,000 requests
- **Steady-State Rate**: 10,000 requests per second

**Behavior**:
- Requests exceeding the burst capacity are throttled
- Throttled requests receive a `429 Too Many Requests` response
- Rate limits apply per AWS account

**Best Practices**:
- Implement exponential backoff for retry logic
- Cache responses when appropriate
- Batch operations when possible
- Monitor your request rate and adjust accordingly

**Example Retry Logic (Python)**:
```python
import requests
import time

def api_request_with_retry(url, headers, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers)
        
        if response.status_code == 429:
            # Exponential backoff: 1s, 2s, 4s
            wait_time = 2 ** attempt
            print(f"Rate limited. Retrying in {wait_time}s...")
            time.sleep(wait_time)
            continue
        
        return response
    
    raise Exception("Max retries exceeded")
```

**Example Retry Logic (JavaScript)**:
```javascript
async function apiRequestWithRetry(url, headers, maxRetries = 3) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    const response = await fetch(url, { headers });
    
    if (response.status === 429) {
      // Exponential backoff: 1s, 2s, 4s
      const waitTime = Math.pow(2, attempt) * 1000;
      console.log(`Rate limited. Retrying in ${waitTime}ms...`);
      await new Promise(resolve => setTimeout(resolve, waitTime));
      continue;
    }
    
    return response;
  }
  
  throw new Error('Max retries exceeded');
}
```

---

## Pagination

Currently, the API does not implement pagination for list endpoints. All results are returned in a single response.

**Future Enhancement**: Pagination will be added in a future version using cursor-based pagination:

```json
{
  "items": [...],
  "next_cursor": "eyJsYXN0X2lkIjogIjEyMyJ9",
  "has_more": true
}
```

**Recommended Limits**:
- OAuth clients list: Returns all clients (typically < 100)
- Test suite executions: Consider filtering by date range in future versions

---

## Complete CI/CD Workflow Example

This example demonstrates a complete CI/CD workflow using the API, from authentication to test execution and artifact upload.

### Bash Script Example

```bash
#!/bin/bash
set -e

# Configuration
COGNITO_DOMAIN="your-user-pool-domain"
REGION="us-east-1"
API_BASE_URL="https://api.example.com"
CLIENT_ID="${OAUTH_CLIENT_ID}"
CLIENT_SECRET="${OAUTH_CLIENT_SECRET}"
SUITE_ID="01234567-89ab-cdef-0123-456789abcdef"

echo "=== CI/CD Test Execution Workflow ==="

# Step 1: Obtain access token
echo "Step 1: Obtaining access token..."
TOKEN_RESPONSE=$(curl -s -X POST \
  "https://${COGNITO_DOMAIN}.auth.${REGION}.amazoncognito.com/oauth2/token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=client_credentials' \
  -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d 'scope=api/suite.read api/suite.write api/execution.read api/execution.write')

TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
  echo "ERROR: Failed to obtain access token"
  echo $TOKEN_RESPONSE
  exit 1
fi

echo "✓ Access token obtained"

# Step 2: Execute test suite
echo "Step 2: Executing test suite..."
SUITE_RESPONSE=$(curl -s -X POST \
  "${API_BASE_URL}/test-suites/${SUITE_ID}/execute" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{
    "trigger_type": "ci_runner",
    "base_url": "https://staging.example.com",
    "variables": {
      "username": "testuser",
      "password": "testpass"
    }
  }')

SUITE_EXECUTION_ID=$(echo $SUITE_RESPONSE | jq -r '.suite_execution_id')
EXECUTION_IDS=$(echo $SUITE_RESPONSE | jq -r '.execution_ids')

echo "✓ Suite execution created: ${SUITE_EXECUTION_ID}"
echo "✓ Created $(echo $EXECUTION_IDS | jq length) executions"

# Step 3: Execute each usecase and report progress
echo "Step 3: Executing usecases..."
echo $EXECUTION_IDS | jq -c '.[]' | while read execution; do
  USECASE_ID=$(echo $execution | jq -r '.usecase_id')
  EXECUTION_ID=$(echo $execution | jq -r '.execution_id')
  USECASE_NAME=$(echo $execution | jq -r '.usecase_name')
  
  echo "  Executing: ${USECASE_NAME}"
  
  # Get execution steps
  STEPS=$(curl -s -X GET \
    "${API_BASE_URL}/usecase/${USECASE_ID}/executions/${EXECUTION_ID}/steps" \
    -H "Authorization: Bearer ${TOKEN}")
  
  # Execute each step
  echo $STEPS | jq -c '.[]' | while read step; do
    STEP_ID=$(echo $step | jq -r '.id')
    STEP_NAME=$(echo $step | jq -r '.name')
    
    echo "    Step: ${STEP_NAME}"
    
    # Mark step as running
    curl -s -X PATCH \
      "${API_BASE_URL}/usecase/${USECASE_ID}/executions/${EXECUTION_ID}/steps/${STEP_ID}/status" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H 'Content-Type: application/json' \
      -d "{
        \"status\": \"running\",
        \"started_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
      }" > /dev/null
    
    # Execute step logic here
    # ... your test execution code ...
    
    # Upload screenshot if available
    if [ -f "screenshot_${STEP_ID}.png" ]; then
      ARTIFACT_RESPONSE=$(curl -s -X POST \
        "${API_BASE_URL}/usecase/${USECASE_ID}/executions/${EXECUTION_ID}/steps/${STEP_ID}/artifacts" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H 'Content-Type: application/json' \
        -d '{
          "filename": "screenshot.png",
          "content_type": "image/png"
        }')
      
      UPLOAD_URL=$(echo $ARTIFACT_RESPONSE | jq -r '.upload_url')
      
      curl -s -X PUT "$UPLOAD_URL" \
        -H 'Content-Type: image/png' \
        --data-binary @"screenshot_${STEP_ID}.png" > /dev/null
      
      echo "      ✓ Screenshot uploaded"
    fi
    
    # Mark step as completed
    curl -s -X PATCH \
      "${API_BASE_URL}/usecase/${USECASE_ID}/executions/${EXECUTION_ID}/steps/${STEP_ID}/status" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H 'Content-Type: application/json' \
      -d "{
        \"status\": \"completed\",
        \"completed_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
      }" > /dev/null
    
    echo "      ✓ Step completed"
  done
  
  # Upload execution-level artifacts
  if [ -f "recording_${EXECUTION_ID}.webm" ]; then
    echo "    Uploading recording..."
    ARTIFACT_RESPONSE=$(curl -s -X POST \
      "${API_BASE_URL}/usecase/${USECASE_ID}/executions/${EXECUTION_ID}/artifacts" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H 'Content-Type: application/json' \
      -d '{
        "type": "recording",
        "filename": "recording.webm",
        "content_type": "video/webm"
      }')
    
    UPLOAD_URL=$(echo $ARTIFACT_RESPONSE | jq -r '.upload_url')
    
    curl -s -X PUT "$UPLOAD_URL" \
      -H 'Content-Type: video/webm' \
      --data-binary @"recording_${EXECUTION_ID}.webm" > /dev/null
    
    echo "    ✓ Recording uploaded"
  fi
  
  echo "  ✓ Usecase completed: ${USECASE_NAME}"
done

echo "=== Workflow completed successfully ==="
```

### Python Script Example

```python
import requests
import time
from datetime import datetime
from typing import Dict, List

class NovaActCICDClient:
    def __init__(self, cognito_domain: str, region: str, api_base_url: str,
                 client_id: str, client_secret: str):
        self.cognito_domain = cognito_domain
        self.region = region
        self.api_base_url = api_base_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expiry = 0
    
    def get_access_token(self) -> str:
        """Obtain access token using OAuth 2.0 client credentials flow."""
        # Check if token is still valid
        if self.access_token and time.time() < self.token_expiry:
            return self.access_token
        
        token_url = f"https://{self.cognito_domain}.auth.{self.region}.amazoncognito.com/oauth2/token"
        
        response = requests.post(
            token_url,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'scope': 'api/suite.read api/suite.write api/execution.read api/execution.write'
            }
        )
        
        response.raise_for_status()
        data = response.json()
        
        self.access_token = data['access_token']
        self.token_expiry = time.time() + data['expires_in'] - 60  # Refresh 1 min early
        
        return self.access_token
    
    def execute_test_suite(self, suite_id: str, base_url: str = None,
                          variables: Dict[str, str] = None) -> Dict:
        """Execute a test suite with optional overrides."""
        token = self.get_access_token()
        
        payload = {'trigger_type': 'ci_runner'}
        if base_url:
            payload['base_url'] = base_url
        if variables:
            payload['variables'] = variables
        
        response = requests.post(
            f"{self.api_base_url}/test-suites/{suite_id}/execute",
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            },
            json=payload
        )
        
        response.raise_for_status()
        return response.json()
    
    def update_step_status(self, usecase_id: str, execution_id: str,
                          step_id: str, status: str, error_message: str = None):
        """Update the status of an execution step."""
        token = self.get_access_token()
        
        payload = {
            'status': status,
            'started_at': datetime.utcnow().isoformat() + 'Z'
        }
        
        if status in ['completed', 'failed']:
            payload['completed_at'] = datetime.utcnow().isoformat() + 'Z'
        
        if error_message:
            payload['error_message'] = error_message
        
        response = requests.patch(
            f"{self.api_base_url}/usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/status",
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            },
            json=payload
        )
        
        response.raise_for_status()
        return response.json()
    
    def upload_step_artifact(self, usecase_id: str, execution_id: str,
                            step_id: str, file_path: str, content_type: str):
        """Upload a step artifact (screenshot, trace)."""
        token = self.get_access_token()
        
        # Get presigned URL
        response = requests.post(
            f"{self.api_base_url}/usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/artifacts",
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            },
            json={
                'filename': file_path.split('/')[-1],
                'content_type': content_type
            }
        )
        
        response.raise_for_status()
        data = response.json()
        upload_url = data['upload_url']
        
        # Upload file to S3
        with open(file_path, 'rb') as f:
            upload_response = requests.put(
                upload_url,
                headers={'Content-Type': content_type},
                data=f
            )
        
        upload_response.raise_for_status()
        return data['artifact_id']
    
    def upload_execution_artifact(self, usecase_id: str, execution_id: str,
                                  artifact_type: str, file_path: str,
                                  content_type: str):
        """Upload an execution artifact (recording, logs)."""
        token = self.get_access_token()
        
        # Get presigned URL
        response = requests.post(
            f"{self.api_base_url}/usecase/{usecase_id}/executions/{execution_id}/artifacts",
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            },
            json={
                'type': artifact_type,
                'filename': file_path.split('/')[-1],
                'content_type': content_type
            }
        )
        
        response.raise_for_status()
        data = response.json()
        upload_url = data['upload_url']
        
        # Upload file to S3
        with open(file_path, 'rb') as f:
            upload_response = requests.put(
                upload_url,
                headers={'Content-Type': content_type},
                data=f
            )
        
        upload_response.raise_for_status()
        return data['artifact_id']


# Usage example
if __name__ == '__main__':
    client = NovaActCICDClient(
        cognito_domain='your-user-pool-domain',
        region='us-east-1',
        api_base_url='https://api.example.com',
        client_id='7abc123def456',
        client_secret='secret_xyz789...'
    )
    
    # Execute test suite
    result = client.execute_test_suite(
        suite_id='01234567-89ab-cdef-0123-456789abcdef',
        base_url='https://staging.example.com',
        variables={'username': 'testuser', 'password': 'testpass'}
    )
    
    print(f"Suite execution created: {result['suite_execution_id']}")
    print(f"Created {len(result['execution_ids'])} executions")
    
    # Process each execution
    for execution in result['execution_ids']:
        usecase_id = execution['usecase_id']
        execution_id = execution['execution_id']
        
        print(f"Executing: {execution['usecase_name']}")
        
        # Execute steps and update status
        # ... your test execution logic ...
        
        # Upload artifacts
        client.upload_execution_artifact(
            usecase_id, execution_id,
            'recording', 'recording.webm', 'video/webm'
        )
```

---

## API Versioning

**Current Version**: 1.2.0

The API uses semantic versioning (MAJOR.MINOR.PATCH):
- **MAJOR**: Breaking changes that require client updates
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, backward compatible

**Version History**:

### Version 1.2.0 (Current)
- Added OAuth client management endpoints
- Added client credentials flow support for M2M authentication
- Added scope validation and privilege escalation prevention
- Added client secret rotation capability

### Version 1.1.0
- Added test suite execution endpoint for CI/CD
- Added support for base URL, variable, region, and model overrides
- Added structured logging and CloudWatch metrics

### Version 1.0.0
- Initial release with execution endpoints
- Added `ci_runner` trigger type
- Added step status update endpoint
- Added artifact presigned URL endpoints

**Deprecation Policy**:
- Deprecated endpoints will be supported for at least 6 months
- Deprecation notices will be included in API responses
- Breaking changes will increment the major version

---

## Security Best Practices

### OAuth Client Management

1. **Least Privilege**: Grant only the minimum scopes required
2. **Secret Storage**: Store client secrets in secure secret managers (AWS Secrets Manager, HashiCorp Vault)
3. **Secret Rotation**: Rotate client secrets regularly (recommended: every 90 days)
4. **Access Review**: Regularly review and remove unused OAuth clients
5. **Monitoring**: Monitor OAuth client usage and authentication failures

### Token Management

1. **Token Expiry**: Access tokens expire after 1 hour - implement automatic refresh
2. **Secure Storage**: Never commit tokens or credentials to version control
3. **Environment Variables**: Use environment variables or secret managers for credentials
4. **Token Validation**: Validate token expiry before making API requests

### API Request Security

1. **HTTPS Only**: Always use HTTPS for API requests
2. **Input Validation**: Validate and sanitize all input data
3. **Error Handling**: Don't expose sensitive information in error messages
4. **Rate Limiting**: Implement client-side rate limiting to avoid throttling
5. **Logging**: Log API requests for audit purposes (exclude sensitive data)

### Network Security

1. **IP Whitelisting**: Consider restricting API access to known IP ranges
2. **VPC Endpoints**: Use VPC endpoints for internal AWS service communication
3. **WAF Rules**: Implement AWS WAF rules for additional protection
4. **DDoS Protection**: Use AWS Shield for DDoS protection

---

## Support and Resources

### Documentation
- [Installation Guide](installation.md)
- [Configuration Reference](configuration.md)
- [CLI Reference](cli-reference.md)
- [CI/CD Integration Examples](ci-cd-integration/)
- [Troubleshooting Guide](troubleshooting.md)
- [Best Practices](best-practices.md)

### Getting Help
- **GitHub Issues**: [https://github.com/aws-samples/sample-nova-act-qa-studio/issues](https://github.com/aws-samples/sample-nova-act-qa-studio/issues)
- **Documentation**: [https://github.com/aws-samples/sample-nova-act-qa-studio](https://github.com/aws-samples/sample-nova-act-qa-studio)

### Reporting Security Issues
If you discover a security vulnerability, please email security@example.com instead of using the public issue tracker.

---

## Changelog

### 2024-02-16 - Version 1.2.0
**Added**:
- OAuth client management endpoints (`POST /api/oauth-clients`, `GET /api/oauth-clients`, `DELETE /api/oauth-clients/{clientId}`, `POST /api/oauth-clients/{clientId}/rotate-secret`)
- OAuth 2.0 client credentials flow documentation
- Scope validation and privilege escalation prevention
- Client secret rotation capability
- Complete CI/CD workflow examples in Bash and Python

**Security**:
- Client secrets only shown once at creation/rotation
- Immediate credential revocation on deletion
- Ownership verification for client management operations
- Audit logging for all OAuth client operations

### 2024-01-15 - Version 1.1.0
**Added**:
- Test suite execution endpoint (`POST /test-suites/{id}/execute`)
- Support for base URL overrides
- Support for variable overrides with precedence
- Support for region and model_id overrides
- Structured logging and CloudWatch metrics

### 2024-01-01 - Version 1.0.0
**Initial Release**:
- Execute usecase endpoint with `ci_runner` trigger type
- Update execution step status endpoint
- Generate execution artifact presigned URL endpoint
- Generate step artifact presigned URL endpoint
- M2M token authentication support

---

## Appendix

### Valid OAuth Scopes

| Scope | Resource | Permission | Description |
|-------|----------|------------|-------------|
| `api/admin` | All | Full | Full access to all resources |
| `api/execution.write` | Executions | Write | Create and update executions |
| `api/execution.read` | Executions | Read | Read execution data |
| `api/usecases.write` | Usecases | Write | Create and update usecases |
| `api/usecases.read` | Usecases | Read | Read usecase data |
| `api/suite.write` | Test Suites | Write | Manage test suites |
| `api/suite.read` | Test Suites | Read | Read test suite data |
| `api/oauth-clients.write` | OAuth Clients | Write | Create, delete, and rotate OAuth clients |
| `api/oauth-clients.read` | OAuth Clients | Read | List OAuth clients |

### Valid Step Status Values

| Status | Description | Terminal State |
|--------|-------------|----------------|
| `pending` | Step has not started | No |
| `running` | Step is currently executing | No |
| `completed` | Step completed successfully | Yes |
| `failed` | Step failed with error | Yes |
| `skipped` | Step was skipped | Yes |

### Valid Artifact Types

**Execution-Level Artifacts**:
| Type | Content Types | Description |
|------|---------------|-------------|
| `recording` | `video/webm`, `video/mp4` | Video recording of execution |
| `logs` | `text/plain` | Execution logs |

**Step-Level Artifacts**:
| Type | Content Types | Description |
|------|---------------|-------------|
| Screenshot | `image/png`, `image/jpeg` | Screenshot of step |
| Trace | `application/json` | Playwright trace file |

### Valid Trigger Types

| Trigger Type | Description | ECS Task | Use Case |
|--------------|-------------|----------|----------|
| `OnDemand` | Queue for worker | No | Default execution |
| `Scheduled` | Direct ECS task | Yes | EventBridge scheduled |
| `OnDemandHeadless` | Direct ECS task | Yes | UI-triggered execution |
| `ci_runner` | Record only | No | CI/CD integration |

---

**Last Updated**: 2024-02-16  
**API Version**: 1.2.0  
**Document Version**: 1.0.0
