# Nova Act QA Studio - API Documentation

## Overview

Nova Act QA Studio provides a RESTful API for managing test automation workflows. All endpoints require authentication via AWS Cognito and use OAuth 2.0 scopes for authorization.

## Authentication

All API requests must include a valid JWT token in the Authorization header:

```
Authorization: Bearer <jwt_token>
```

### Token Types

- **User Tokens**: Obtained via Cognito user authentication
- **M2M (Machine-to-Machine) Tokens**: OAuth client credentials for CI/CD integration

### OAuth Scopes

Scopes follow the pattern `api/{resource}.{permission}`:

- `api/admin` - Full access to all resources
- `api/execution.write` - Create and update executions
- `api/execution.read` - Read execution data
- `api/usecases.write` - Create and update usecases
- `api/usecases.read` - Read usecase data
- `api/suite.write` - Manage test suites
- `api/suite.read` - Read test suite data
- `api/oauth-clients.write` - Create, delete, and rotate OAuth clients
- `api/oauth-clients.read` - List OAuth clients

## Base URL

```
https://{api-gateway-id}.execute-api.{region}.amazonaws.com/{stage}/
```

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
- `400` - Missing usecase ID or invalid trigger type
- `401` - Unauthorized (missing or invalid token)
- `403` - Forbidden (insufficient scopes)
- `404` - Usecase not found
- `500` - Internal server error

**Example (ci_runner)**:
```bash
curl -X POST \
  'https://api.example.com/usecase/usecase-123/execute?trigger-type=ci_runner' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json'
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
- `400` - Invalid status value or missing required fields
- `401` - Unauthorized
- `403` - Forbidden (requires `api/execution.write` scope)
- `404` - Execution or step not found
- `500` - Internal server error

**Example**:
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
- `400` - Invalid artifact type, missing fields, or invalid content type
- `401` - Unauthorized
- `403` - Forbidden (requires `api/execution.write` scope)
- `404` - Execution not found
- `500` - Internal server error

**Example**:
```bash
# 1. Get presigned URL
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

# 2. Upload file to S3 using presigned URL
curl -X PUT "$UPLOAD_URL" \
  -H 'Content-Type: video/webm' \
  --data-binary @recording.webm
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
- `400` - Missing fields or invalid content type
- `401` - Unauthorized
- `403` - Forbidden (requires `api/execution.write` scope)
- `404` - Execution or step not found
- `500` - Internal server error

**Example**:
```bash
# 1. Get presigned URL
RESPONSE=$(curl -X POST \
  'https://api.example.com/usecase/usecase-123/executions/execution-456/steps/step-789/artifacts' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "filename": "screenshot.png",
    "content_type": "image/png"
  }')

UPLOAD_URL=$(echo $RESPONSE | jq -r '.upload_url')

# 2. Upload file to S3 using presigned URL
curl -X PUT "$UPLOAD_URL" \
  -H 'Content-Type: image/png' \
  --data-binary @screenshot.png
```

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
- `400` - Invalid scopes, missing name, or invalid request format
- `401` - Unauthorized
- `403` - Forbidden (insufficient scopes or privilege escalation attempt)
- `429` - Too many OAuth clients
- `500` - Internal server error

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
- `401` - Unauthorized
- `403` - Forbidden (requires `api/oauth-clients.read` scope)
- `500` - Internal server error

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
- `400` - Missing client ID
- `401` - Unauthorized
- `403` - Forbidden (client not created through application or insufficient permissions)
- `404` - Client not found
- `500` - Internal server error

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
- `400` - Missing client ID
- `401` - Unauthorized
- `403` - Forbidden (user doesn't own client or insufficient permissions)
- `404` - Client not found
- `500` - Internal server error

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

## CI/CD Integration

### Workflow Overview

The CI/CD runner integration allows external systems to execute usecases and report step progress:

1. **Create OAuth Client**: Create an OAuth client via the web UI or API with required scopes
2. **Authenticate**: Use client credentials flow to obtain access token
3. **Create Execution**: Call `POST /usecase/{id}/execute?trigger-type=ci_runner`
4. **Get Execution Steps**: Call `GET /usecase/{id}/executions/{executionId}/steps`
5. **Execute Steps**: Run each step in your CI/CD environment
6. **Report Progress**: Call `PATCH /usecase/{id}/executions/{executionId}/steps/{stepId}/status` for each step
7. **Upload Artifacts**: Upload screenshots, traces, recordings, and logs using presigned URLs

### Authentication for CI/CD

#### Step 1: Create OAuth Client

Create an OAuth client via the web UI or API:

```bash
# Create OAuth client
curl -X POST \
  'https://api.example.com/api/oauth-clients' \
  -H 'Authorization: Bearer <user_jwt_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "CI/CD Runner - Production",
    "scopes": [
      "api/suite.read",
      "api/suite.write",
      "api/execution.read",
      "api/execution.write"
    ]
  }'
```

Response:
```json
{
  "client_id": "7abc123def456",
  "client_secret": "secret_xyz789...",
  "created_date": "2026-02-16T12:00:00Z"
}
```

**IMPORTANT**: Save the `client_secret` - it will only be shown once!

#### Step 2: Obtain Access Token

Use the OAuth 2.0 client credentials flow to obtain an access token:

```bash
# Get Cognito domain from your deployment
COGNITO_DOMAIN="your-user-pool-domain"
REGION="us-east-1"

# Request access token
TOKEN_RESPONSE=$(curl -X POST \
  "https://${COGNITO_DOMAIN}.auth.${REGION}.amazoncognito.com/oauth2/token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=client_credentials' \
  -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d 'scope=api/suite.read api/suite.write api/execution.read api/execution.write')

# Extract access token
ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')
```

Python example:
```python
import requests
import base64

# Cognito token endpoint
cognito_domain = "your-user-pool-domain"
region = "us-east-1"
token_url = f"https://{cognito_domain}.auth.{region}.amazoncognito.com/oauth2/token"

# Request access token
response = requests.post(
    token_url,
    headers={'Content-Type': 'application/x-www-form-urlencoded'},
    data={
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': 'api/suite.read api/suite.write api/execution.read api/execution.write'
    }
)

access_token = response.json()['access_token']
expires_in = response.json()['expires_in']  # Token lifetime in seconds (typically 3600)

print(f"Access token obtained, expires in {expires_in} seconds")
```

#### Step 3: Use Access Token

Include the access token in all API requests:

```bash
curl -X POST \
  'https://api.example.com/usecase/usecase-123/execute?trigger-type=ci_runner' \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H 'Content-Type: application/json'
```

**Token Management**:
- Access tokens typically expire after 1 hour
- Request a new token when the current one expires
- No refresh tokens are issued for client credentials flow
- Store credentials securely (use environment variables or secrets manager)

### OAuth Client Lifecycle Management

#### Rotating Secrets

Rotate client secrets periodically for security:

```bash
# Rotate secret
curl -X POST \
  'https://api.example.com/api/oauth-clients/7abc123def456/rotate-secret' \
  -H 'Authorization: Bearer <user_jwt_token>' \
  -H 'Content-Type: application/json'
```

Response:
```json
{
  "client_id": "8def456ghi789",
  "client_secret": "new_secret_abc123...",
  "rotated_at": "2026-02-16T15:00:00Z"
}
```

**IMPORTANT**: 
- Old secret is immediately invalidated
- Client ID changes during rotation - update your configuration
- Save the new secret - it will only be shown once

#### Deleting OAuth Clients

Delete unused OAuth clients:

```bash
curl -X DELETE \
  'https://api.example.com/api/oauth-clients/7abc123def456' \
  -H 'Authorization: Bearer <user_jwt_token>'
```

**IMPORTANT**: Deletion is immediate - the client cannot authenticate after deletion.

### Scope Requirements

Different operations require different scopes:

| Operation | Required Scopes |
|-----------|----------------|
| Execute test suite | `api/suite.write`, `api/execution.write` |
| Read test suite | `api/suite.read` |
| Create execution | `api/execution.write` |
| Update step status | `api/execution.write` |
| Upload artifacts | `api/execution.write` |
| Read execution data | `api/execution.read` |
| Manage OAuth clients | `api/oauth-clients.write`, `api/oauth-clients.read` |

**Best Practice**: Grant only the minimum scopes required for your CI/CD pipeline.

### Example CI/CD Workflow

Complete example showing OAuth authentication and test execution:

```bash
#!/bin/bash

# Configuration
COGNITO_DOMAIN="your-user-pool-domain"
REGION="us-east-1"
API_BASE_URL="https://api.example.com"
CLIENT_ID="7abc123def456"
CLIENT_SECRET="secret_xyz789..."

# 1. Get access token (OAuth client credentials flow)
echo "Obtaining access token..."
TOKEN_RESPONSE=$(curl -s -X POST \
  "https://${COGNITO_DOMAIN}.auth.${REGION}.amazoncognito.com/oauth2/token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=client_credentials' \
  -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d 'scope=api/suite.read api/suite.write api/execution.read api/execution.write')

TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
  echo "Failed to obtain access token"
  echo $TOKEN_RESPONSE
  exit 1
fi

echo "Access token obtained successfully"

# 2. Create execution
RESPONSE=$(curl -X POST \
  "https://api.example.com/usecase/usecase-123/execute?trigger-type=ci_runner" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json')

EXECUTION_ID=$(echo $RESPONSE | jq -r '.executionId')

# 3. Get execution steps
STEPS=$(curl -X GET \
  "https://api.example.com/usecase/usecase-123/executions/$EXECUTION_ID/steps" \
  -H "Authorization: Bearer $TOKEN")

# 4. Execute each step and report status
echo $STEPS | jq -c '.[]' | while read step; do
  STEP_ID=$(echo $step | jq -r '.id')
  
  # Mark step as running
  curl -X PATCH \
    "https://api.example.com/usecase/usecase-123/executions/$EXECUTION_ID/steps/$STEP_ID/status" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d "{
      \"status\": \"running\",
      \"started_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
    }"
  
  # Execute step logic here
  # ...
  
  # Upload screenshot artifact for this step
  if [ -f "screenshot_${STEP_ID}.png" ]; then
    ARTIFACT_RESPONSE=$(curl -X POST \
      "https://api.example.com/usecase/usecase-123/executions/$EXECUTION_ID/steps/$STEP_ID/artifacts" \
      -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/json' \
      -d "{
        \"filename\": \"screenshot.png\",
        \"content_type\": \"image/png\"
      }")
    
    UPLOAD_URL=$(echo $ARTIFACT_RESPONSE | jq -r '.upload_url')
    
    curl -X PUT "$UPLOAD_URL" \
      -H 'Content-Type: image/png' \
      --data-binary @"screenshot_${STEP_ID}.png"
  fi
  
  # Mark step as completed
  curl -X PATCH \
    "https://api.example.com/usecase/usecase-123/executions/$EXECUTION_ID/steps/$STEP_ID/status" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d "{
      \"status\": \"completed\",
      \"completed_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
    }"
done

# 5. Upload execution-level artifacts (recording, logs)
if [ -f "recording.webm" ]; then
  ARTIFACT_RESPONSE=$(curl -X POST \
    "https://api.example.com/usecase/usecase-123/executions/$EXECUTION_ID/artifacts" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{
      "type": "recording",
      "filename": "recording.webm",
      "content_type": "video/webm"
    }')
  
  UPLOAD_URL=$(echo $ARTIFACT_RESPONSE | jq -r '.upload_url')
  
  curl -X PUT "$UPLOAD_URL" \
    -H 'Content-Type: video/webm' \
    --data-binary @recording.webm
fi

if [ -f "execution.log" ]; then
  ARTIFACT_RESPONSE=$(curl -X POST \
    "https://api.example.com/usecase/usecase-123/executions/$EXECUTION_ID/artifacts" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{
      "type": "logs",
      "filename": "execution.log",
      "content_type": "text/plain"
    }')
  
  UPLOAD_URL=$(echo $ARTIFACT_RESPONSE | jq -r '.upload_url')
  
  curl -X PUT "$UPLOAD_URL" \
    -H 'Content-Type: text/plain' \
    --data-binary @execution.log
fi
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
  -H 'Authorization: Bearer <jwt_token>' \
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
        'Authorization': f'Bearer {jwt_token}',
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

**Notes**:
- No ECS tasks are spawned when using `trigger_type=ci_runner`
- All execution records are created with `status=pending`
- Base URL override replaces only the scheme and domain, preserving path and query parameters
- Variable merge precedence: CLI overrides > usecase variables > secrets
- All template variables ({{variable}}) must be resolved or the request will fail with 400
- Maximum recommended suite size: 10 usecases (to avoid API Gateway timeout)

---

## Error Handling

### Standard Error Response

All error responses follow this format:

```json
{
  "error": "Error message",
  "message": "Detailed error description",
  "required_scopes": ["api/execution.write"],
  "token_scopes": ["api/execution.read"]
}
```

### HTTP Status Codes

- `200` - Success
- `201` - Created
- `204` - No Content (successful deletion)
- `400` - Bad Request (invalid input)
- `401` - Unauthorized (missing or invalid token)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `500` - Internal Server Error

---

## Rate Limiting

API Gateway enforces rate limits:
- **Burst**: 5000 requests
- **Rate**: 10000 requests per second

Exceeded limits return `429 Too Many Requests`.

---

## Changelog

### Version 1.2.0 (WP1d)

**New Features**:
- Added OAuth client management endpoints for CI/CD authentication
- `POST /api/oauth-clients` - Create OAuth client with scoped permissions
- `GET /api/oauth-clients` - List all OAuth clients with metadata
- `DELETE /api/oauth-clients/{clientId}` - Delete OAuth client (immediate revocation)
- `POST /api/oauth-clients/{clientId}/rotate-secret` - Rotate client secret
- Scope validation prevents privilege escalation (users cannot grant scopes they don't have)
- Client secrets shown only once at creation/rotation for security
- Ownership verification ensures users can only manage their own clients
- Support for OAuth 2.0 client credentials flow for M2M authentication

**Security Enhancements**:
- Client secrets never stored in DynamoDB (only in Cognito)
- Immediate credential revocation on deletion
- Immediate old secret invalidation on rotation
- Audit logging for all OAuth client operations

**Breaking Changes**: None

**Deprecations**: None

### Version 1.1.0 (WP1b)

**New Features**:
- Added `POST /test-suites/{id}/execute` endpoint for CI/CD test suite execution
- Support for base URL overrides across all usecases in a suite
- Support for variable overrides with precedence (CLI > usecase > secrets)
- Support for region and model_id overrides
- Structured logging and CloudWatch metrics for suite executions
- EventBridge events for suite execution lifecycle

**Breaking Changes**: None

**Deprecations**: None

### Version 1.0.0 (WP1a)

**New Features**:
- Added `ci_runner` trigger type to `POST /usecase/{id}/execute`
- Added `PATCH /usecase/{id}/executions/{executionId}/steps/{stepId}/status` endpoint
- Support for M2M token authentication on execution endpoints

**Breaking Changes**: None

**Deprecations**: None

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/aws-samples/sample-nova-act-qa-studio/issues
- Documentation: https://github.com/aws-samples/sample-nova-act-qa-studio

