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
  - [Team Ownership and Access Control](#team-ownership-and-access-control)
- [Usecase Management Endpoints](#usecase-management-endpoints)
  - [Create Usecase](#create-usecase)
  - [Get Usecase](#get-usecase)
  - [Update Usecase](#update-usecase)
  - [Get Usecase Steps](#get-usecase-steps)
  - [Step Definition Fields](#step-definition-fields)
  - [Import Usecase](#import-usecase)
- [Template Endpoints](#template-endpoints)
  - [Import Template Definition](#import-template-definition)
  - [Apply Template](#apply-template)
  - [Import Template into Usecase](#import-template-into-usecase)
  - [Update Step from Template](#update-step-from-template)
  - [Check Template Updates](#check-template-updates)
  - [Template Versioning](#template-versioning)
- [Application Configuration Endpoints](#application-configuration-endpoints)
  - [Application Variables](#application-variables)
  - [Application Secrets](#application-secrets)
  - [Application Datasets](#application-datasets)
  - [Effective Use Case Variables and Secrets](#effective-use-case-variables-and-secrets)
  - [Dataset References on Repeat Steps](#dataset-references-on-repeat-steps)
- [Cost Endpoints](#cost-endpoints)
  - [Application Costs](#application-costs)
  - [Use Case Costs](#use-case-costs)
  - [Dashboard Costs](#dashboard-costs)
  - [Cost Summary and Ledger Row Fields](#cost-summary-and-ledger-row-fields)
- [Execution Endpoints](#execution-endpoints)
  - [Execute Usecase](#execute-usecase)
  - [Update Execution Status](#update-execution-status)
  - [Stop Execution](#stop-execution)
  - [Update Execution Step Status](#update-execution-step-status)
  - [Generate Execution Artifact Presigned URL](#generate-execution-artifact-presigned-url)
  - [Generate Step Artifact Presigned URL](#generate-step-artifact-presigned-url)
  - [Request Recording Download](#request-recording-download)
- [Wizard Session Endpoints](#wizard-session-endpoints)
  - [Start Wizard Session](#start-wizard-session)
  - [Terminate Wizard Session](#terminate-wizard-session)
- [Device Farm Endpoints](#device-farm-endpoints)
  - [List Devices](#list-devices)
- [Test Suite Endpoints](#test-suite-endpoints)
  - [Execute Test Suite](#execute-test-suite)
- [OAuth Client Management](#oauth-client-management)
  - [Create OAuth Client](#create-oauth-client)
  - [List OAuth Clients](#list-oauth-clients)
  - [Delete OAuth Client](#delete-oauth-client)
  - [Rotate Client Secret](#rotate-client-secret)
- [User Management Endpoints](#user-management-endpoints)
  - [Delete User](#delete-user)
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
    "teamId": "team-123",
    "scopes": ["api/suite.read", "api/suite.write", "api/executions.write"]
  }'
```

The client is bound to `teamId` and acts with your role in that team, capped at Editor.

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
  -d 'scope=api/suite.read api/suite.write api/executions.write'
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
| `api/admin` | Full access to all resources. Users in the `admins` group only; never granted to OAuth clients | Admin |
| `api/teams.manage` | Manage teams and membership. Never granted to OAuth clients | Admin |
| `api/usecases.execute` | Trigger use case executions and read secret values | Execute |
| `api/executions.write` | Modify execution records (status, steps, artifacts, live view) | Write |
| `api/executions.read` | Read execution data, recordings, trajectories | Read |
| `api/usecases.write` | Create, update, delete use cases | Write |
| `api/usecases.read` | Read use case data | Read |
| `api/suite.write` | Create, update, delete and execute test suites | Write |
| `api/suite.read` | Read test suites and suite executions | Read |
| `api/applications.write` | Create, update, delete applications (Team Lead of the owning team only); write application variables, secrets and datasets (Editor+ of the owning team) | Write |
| `api/applications.read` | Read applications and their variables, secret keys and datasets | Read |
| `api/templates.write` | Create and edit templates and template steps | Write |
| `api/templates.read` | Read templates; required alongside `api/usecases.*` for the usecase↔template endpoints | Read |
| `api/oauth-clients.write` | Create, delete, and rotate OAuth clients | Write |
| `api/oauth-clients.read` | List OAuth clients | Read |

**Scope Requirements by Operation** (each also needs the team role in [Team ownership](#team-ownership-and-access-control)):

| Operation | Required Scopes | Team action |
|-----------|----------------|-------------|
| Execute use case (`POST /usecase/{id}/execute`) | `api/usecases.execute` | execute |
| Read a secret value (`GET /usecase/{id}/secrets/{key}/value`) | `api/usecases.execute` (was `api/usecases.read`) | execute |
| Trajectory download URL (`GET .../trajectory/download-url`) | `api/executions.read` (was `api/executions.write`) | view |
| Trajectory upload URL | `api/executions.write` | execute |
| Execute test suite | `api/suite.write`, `api/executions.write` | execute |
| Read test suite | `api/suite.read` | view |
| Update execution / step status, upload artifacts | `api/executions.write` | execute |
| Delete an execution | `api/executions.write` | edit (Editor+) |
| Read execution data | `api/executions.read` | view |
| `POST /generate-s3-url` (`app_binary`, `browser_policy`) | `api/usecases.write` | edit |
| `POST /generate-s3-url` (`html`, `video`) | `api/executions.read` | view |
| `GET /models` | `api/usecases.read` | – |
| Manage OAuth clients | `api/oauth-clients.write`, `api/oauth-clients.read` | Editor+ of the client's team |
| Create usecase from template (`POST /templates/{id}/apply`) | `api/templates.read`, `api/usecases.write` | edit (on the target application) |
| Insert template into usecase (`POST /usecase/{id}/import-template`) | `api/usecases.write`, `api/templates.read` | edit |
| Update step from template (`POST /usecase/{id}/steps/{stepId}/update-from-template`) | `api/usecases.write`, `api/templates.read` | edit |
| Check template updates (`GET /usecase/{id}/template-updates`) | `api/usecases.read`, `api/templates.read` | view |
| Replace a template definition (`PUT /templates/{id}`) | `api/templates.write` | – |
| Delete a template (`DELETE /templates/{id}`) | `api/templates.write` (also unlinks the use-case steps that came from it — no per-usecase check) | – |
| List the tests using a template (`GET /templates/{id}/usages`) | `api/templates.read` | – |
| Read application variables / secret keys / datasets (`GET /applications/{id}/{variables\|secrets\|datasets}`) | `api/applications.read` | view (on the application) |
| Write application variables / secrets / datasets (`POST`, `PUT`, `DELETE` under `/applications/{id}/…`) | `api/applications.write` | edit (Editor+ of the owning team or a Full share) |

**Best Practice**: Grant only the minimum scopes required for your use case.

### Team ownership and access control

Scopes alone aren't enough. Every route on a team-owned resource (application, use case, step, variable, hook, header, secret, schedule, execution, execution step, artifact, live view, wizard session, test suite, suite execution) resolves the owning team and checks the caller's role in it. The role rules are in [User Management](user-management.md#how-access-control-works).

- **Users** get their team roles from Cognito groups (`team-{id}-{team_lead|editor|executor|viewer}`). Admins (`admins` group) bypass team checks.
- **OAuth clients** act with the team role stored on the client (`team_id`, `team_role`, capped at `editor`). Clients without a team get 403 on every team-owned resource.
- **The cloud worker** must send `X-QA-Execution-Token` (below).
- **Orphans** (no `application_id`) are Admin-only.

**Status codes added by these checks:**

| Status | When |
|--------|------|
| `400` | Invalid path/body ID; missing `teamId` or `application_id`; missing `usecaseId` on wizard step/command; `role: "admin"` on a team member endpoint; forbidden scope on an OAuth client; invalid `secret_key` |
| `403` | Missing scope; no role (or too low a role) in the owning team; share level too low; orphan resource for a non-admin; unbound OAuth client; worker without a valid execution token; application update/delete by anyone but the owning Team Lead or an Admin |
| `404` | Unknown resource; execution not under the use case in the path (or suite execution not under the suite); wizard session not under the use case; use case hidden by a visibility override; unknown `teamId` |
| `409` | Demoting or deleting the last member of the `admins` group; creating or renaming an application dataset to a name already used in the application; deleting a dataset that repeat steps still reference; moving a use case into an application while its repeat steps reference datasets (see [Application Datasets](#application-datasets)); `PATCH …/executions/{executionId}/status` with a different status on an execution that is already terminal (see [Update Execution Status](#update-execution-status)) |

#### `X-QA-Execution-Token` header

| Header | Format | Sent by | Accepted when |
|--------|--------|---------|---------------|
| `X-QA-Execution-Token` | `{usecase_id}:{execution_id}:{token}` | The `qa-studio` CLI when `QA_STUDIO_EXECUTION_TOKEN` is set (the cloud worker) | The caller is the worker client, the route allows the worker, the token's SHA-256 matches `worker_token_hash` on that execution, the execution is `pending` or `running`, and the path's use case / `executionId` / suite execution match it |

Header name matching is case-insensitive. Human and CI callers don't need it; a forged header never replaces the team check for them.

#### Request body changes

| Endpoint | Change |
|----------|--------|
| `POST /applications` | `teamId` (string) required. Caller must be Team Lead of that team or Admin. 404 for an unknown team |
| `PATCH /applications/{id}`, `DELETE /applications/{id}` | Team Lead of the owning team or Admin. `DELETE` returns 204 and also deletes the application's Secrets Manager secrets (by `application_id` tag); its `VARIABLES` and `DATASET#` records go with the partition |
| `POST /applications/{id}/usecases` | `409 {error: "use case references application datasets", usecases: [{usecase_id, name, steps: [{id, instruction}]}]}` when a use case being moved in has a repeat step with `dataset_id` (the id belongs to the application it is leaving). Nothing is written. |
| `POST /oauth-clients` | `teamId` (string) required; caller must be Editor+ in it. Response adds `team_id`, `team_role` |
| `POST /usecase` | `application_id` required (edit on that app); 404 for an unknown app |
| `POST /import`, `POST /wizard/start`, `POST /templates/{id}/apply` | `application_id` (string) required; edit on that app. The new use case gets `application_id` and `owner_team_id` |
| `POST /usecase/{id}/clone` | Optional `application_id` (defaults to the source's app); edit on that app |
| `POST /usecase/{id}/steps` | The use case comes from the path; a different body `usecaseId` returns 400 |
| `PATCH /usecase/{id}`, `PUT /test-suites/{suite_id}` | Changing `application_id` needs edit on the target app; clearing it is Admin-only |
| `POST /wizard/{sessionId}/step`, `/command` | `usecaseId` (string, required) in the body |
| `POST /test-suites/{suite_id}/usecases` | Each use case must belong to the suite's owning team (Admins exempt) |
| `POST /generate-usecase` | `screenshot_manifest_key` must be `{usecase_id}/{session_id}/screenshot_manifest.json` for a session the caller can edit |
| `POST /teams/{id}/members`, `PATCH /teams/{id}/members/{userId}` | `role` must be `team_lead`, `editor`, `executor` or `viewer`; `admin` returns 400 |

#### Deletes return 204

These now return `204 No Content` with an empty body: `DELETE /applications/{id}`, `DELETE /oauth-clients/{clientId}`, `DELETE /usecase/{id}`, `DELETE /usecase/{id}/steps/{stepId}`, `DELETE /usecase/{id}/schedule`, `DELETE /usecase/{id}/secrets`, `DELETE /usecase/{id}/executions/{executionId}`, `DELETE .../executions/{executionId}/live-view`, `DELETE /applications/{id}/usecases/{usecaseId}`, `DELETE /teams/{id}` (the orphaned-app and unassigned-member counts it used to return are kept in the `team_delete` audit entry).

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
- `test_platform` (string, optional, default: "web") - Test platform: `"web"`, `"mobile"` or `"electron"`. Electron usecases need no `starting_url` and no mobile fields; they can only be executed by the CI runner (`qa-studio run --app-path …`), never from the UI or a schedule.
- `platform` (string, optional) - Mobile platform: `"ANDROID"` or `"IOS"` (required when test_platform is "mobile")
- `app_package` (string, optional) - Android app package name (e.g., `"com.example.myapp"`)
- `app_activity` (string, optional) - Android app activity (e.g., `"com.example.myapp.MainActivity"`)
- `bundle_id` (string, optional) - iOS bundle identifier (e.g., `"com.example.myapp"`); for `test_platform: "electron"` the desktop app's `CFBundleIdentifier`, verified by the CI runner against the launched `.app`
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

Step caching is native trajectory replay done by the runner (`qa-studio run`). Fields (snake_case, as returned):

| Field | Type | Default | Where | Description |
|-------|------|---------|-------|-------------|
| `enable_cache` | boolean | false | use case (POST/PATCH/GET), copied to the execution record | Step caching setting of the use case |
| `trajectory_s3_key` | string | null | STEP# / EXECUTION_STEP#, `GET /usecase/{id}/steps` | S3 key of the recorded trajectory a navigation step replays. Drives the UI "Cached" badge |
| `trajectory_last_updated` | string (ISO 8601) | null | same | When the trajectory was recorded |
| `cached_steps`, `cache_last_updated` | string / string | null | same | **Deprecated.** Written only by the removed bbox step cache; still returned for one release, then dropped |

**Replay**:
1. A successful navigation step records its trajectory through `POST …/steps/{stepId}/trajectory/upload-url`
   (`trajectory_s3_key` / `trajectory_last_updated` are set on the STEP record).
2. Later runs download it (`GET …/trajectory/download-url`) and replay it instead of calling the model.
3. A failed replay falls back to Nova Act and clears the step's fields (`clear_cache_fields` on the step-status call).

**Invalidation**: a failed execution clears every trajectory of the use case; switching `enable_cache` from true to
false does the same.

---

### Network Assertion Fields

Fields specific to steps of type `network_assertion`. All fields except `network_url_pattern` are optional. Defaults match the worker-side fallback behaviour.

**Request-side fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `network_url_pattern` | string | — (required) | Playwright glob pattern identifying the request, e.g. `**/api/users` |
| `network_method` | string | empty | Expected HTTP verb: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`. Empty means no method check. |
| `network_request_body` | string (JSON) | null | Expected request body, interpreted per `network_body_match_type` |
| `network_body_match_type` | string | `exact` | One of `exact`, `subset`, `schema`. See "Match Types" below. |

**Mock response fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `network_mock_response` | string (JSON) | null | `{"status": …, "body": …, "headers": …}`. When set, the matching request is intercepted. |
| `network_mock_passthrough` | boolean | `false` | If `true`, fetch the real response and merge `network_mock_response` fields over it. If `false`, the real request is never sent. |

**Response-side assertion fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `network_response_status` | integer | null | Exact-match expected HTTP status code. Must be in `[100, 599]` when set. |
| `network_response_body` | string (JSON) | null | Expected response body, interpreted per `network_response_body_match_type` |
| `network_response_body_match_type` | string | `subset` | One of `subset` or `schema`. **`exact` is not permitted on the response side** because response payloads frequently contain non-deterministic values. |

**Timing:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `network_timeout` | integer | `15` | Seconds to wait for a matching request, capped at `120`. |

**Match Types:**

- **`exact`** — parsed-JSON equality between expected and captured body. Request side only.
- **`subset`** — every key/value in the expected template must be present in the captured body with matching values. Extra keys are ignored. Arrays match element-by-element; lengths must match.
- **`schema`** — the expected body is a [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) document. The captured body is validated against the schema. External `$ref` (http/https/file) is rejected; only local-pointer refs (`#/...`) are allowed.

**Size limits:**

Request body, response body, mock response, and schema documents are each capped in bytes. The default is 1 MiB (`1_048_576`) on both server and client. Operators can override the server-side cap via the `networkAssertionBodyMaxBytes` setting in `configuration.json`, which flows to the worker and Lambda environment as `NETWORK_ASSERTION_BODY_MAX_BYTES`. The CLI uses a fixed 1 MiB default for pre-submit validation and relies on the server for authoritative enforcement.

The captured response body is always size-checked, even when no response body assertion is configured, so oversized responses surface early.

**Security:**

- External `$ref` targets (`http://`, `https://`, `file://`) in schema documents are rejected at validation time to prevent SSRF and file-read attacks.
- The subset matcher refuses JSON nested deeper than 20 levels.
- Captured bodies are truncated to 500 characters in logs. Only a compact match summary (e.g. `method=POST body_match=subset:pass resp_status=201 resp_body=schema:pass`) is persisted in execution records.
- Route handlers registered via `network_mock_response` are always torn down on step exit, even on Nova Act failure, timeout, or assertion failure.

**Caching:**

`network_assertion` steps are intentionally **not cached**. The Nova Act action portion participates in the usecase's existing caching ladder (trajectory replay / Playwright cache) identically to a navigation step, but the interception and assertion logic always runs fresh. An API contract change must never be masked by a cache hit.

---

### Repeat Step Fields

Fields specific to steps of type `repeat` (a data-driven loop) and to its children. Validation is shared by `POST /usecase/{id}/steps`, `PATCH /usecase/{id}/steps/{step_id}` and `POST /import`; violations return `400` with the joined error list.

| Field | Type | Default | Applies to | Description |
|-------|------|---------|------------|-------------|
| `step_type` | string | — | repeat | `"repeat"` |
| `instruction` | string | — (required) | repeat | Human label. Must be unique among the repeat steps of the usecase; `repeat_datasets` / `--dataset-file` address the repeat by it. |
| `dataset_id` | string | absent | repeat | Id of an [application dataset](#application-datasets) of the usecase's application. **Exactly one** of `dataset_id` or `repeat_columns` + `repeat_rows` must be present: both → `400 repeat step cannot have both dataset_id and inline rows`; neither → `400 repeat step must have either dataset_id or repeat_columns/repeat_rows`; unknown id or usecase without an application → `400 dataset not found in this application`. Rejected on template steps (`400 dataset references (dataset_id) are not supported in templates`). |
| `repeat_columns` | list[string] | — (required unless `dataset_id`) | repeat | 1–20 identifiers matching `^[A-Za-z_][A-Za-z0-9_]*$`, unique, not one of `UniqueID`, `Time`, `ExecutionID`, `CreatedAt`, `RepeatIndex`, `RepeatTotal`. |
| `repeat_rows` | list[list[string]] | — (required unless `dataset_id`) | repeat | 1–100 rows, each with exactly `len(repeat_columns)` string cells. `json.dumps(columns) + json.dumps(rows)` ≤ 200 KB. |
| `parent_step_id` | string | absent | child | `id` of a `repeat` step of the same usecase. The parent must itself have no `parent_step_id` (one nesting level); a child may not be of type `repeat`. |

Behaviour:

- `DELETE /usecase/{id}/steps/{step_id}` on a repeat also deletes its children (`204 No Content`).
- `PATCH` that changes a repeat's `step_type` to anything else while it still has children → `400`. Changing `repeat_columns` re-validates the stored rows.
- `POST /templates/{id}/steps` and `PATCH /templates/{id}/steps/{step_id}` reject `step_type: "repeat"` and any `parent_step_id` with `400 "repeat steps are not supported in templates"`.
- `GET /usecase/{id}/export` nests children under the repeat as `steps: [...]`; `POST /import` accepts that shape (and the flat `id` + `parent_step_id` shape), assigns new ids and remaps `parent_step_id`. `dataset_id` is exported as-is (never inlined); import and clone validate it against the **target** application (see [Dataset References on Repeat Steps](#dataset-references-on-repeat-steps)).
- `PATCH /usecase/{id}/steps/{step_id}` treats the body as naming the source: a body with `dataset_id` switches the step to the dataset (stored inline rows are dropped); a body with `repeat_columns` + `repeat_rows` switches back to inline (`dataset_id` is dropped).

**Expanded execution steps.** The repeat itself produces no execution step. When an execution is created, each child is copied once per row (row-major, children in `sort` order); `sort` is renumbered 1..n over the flattened list. `GET /usecase/{id}/executions/{execution_id}/steps` returns these additional fields on expanded steps:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `repeat_step_id` | string | absent | `id` of the repeat the step came from |
| `repeat_label` | string | absent | The repeat's `instruction` |
| `repeat_row_index` | number | absent | 1-based row index |
| `repeat_row_total` | number | absent | Row count |
| `row_variables` | map[string,string] | absent | `{column: cell}` for the row plus `RepeatIndex` and `RepeatTotal` |

`trajectory_s3_key`, `trajectory_last_updated`, `cached_steps` and `cache_last_updated` are never copied onto expanded steps (trajectory replay is off inside a repeat). A repeat with `dataset_id` is resolved into columns/rows at execution creation (`dataset_ref.py`), so expanded steps carry the dataset's `row_variables` and no `dataset_id`; a missing dataset fails the execute call with `400 {"error": "dataset not found", "dataset_id": "…"}` before anything is written.

---

### Step Definition Fields

Every optional, authored step field below is preserved verbatim by **all** step-copying endpoints: `GET /usecase/{id}/export`, `POST /import`, `POST /usecase/{id}/clone`, `POST /templates/{id}/steps`, `PATCH /templates/{id}/steps/{step_id}`, `POST /templates/{id}/apply`, `POST /usecase/{id}/import-template`, `POST /usecase/{id}/steps/{step_id}/update-from-template`, the wizard step endpoints, and execution creation (`EXECUTION_STEP#` records). The list is a single constant on the server (`step_copy.COPYABLE_STEP_FIELDS`) that a test keeps identical to the CLI's `ExportStep` model, so a field cannot be dropped on one path only.

Copy rule: a field is copied when it is present and neither `null` nor `""`; `false` and `0` (e.g. `network_mock_passthrough: false`, `network_timeout: 0`) are kept.

| Field | Type | Step types | Description |
|-------|------|------------|-------------|
| `secret_key` | string | secret | Key of the usecase secret typed into the focused field |
| `capture_variable` | string | retrieve_value, transform, download | Variable the step's result is stored in |
| `assertion_variable` | string | assertion | Variable compared by the assertion |
| `validation_type` | string | validation, assertion | `string`, `number`, `date`, … |
| `validation_operator` | string | validation, assertion | e.g. `exact`, `contains`, `greater_than` |
| `validation_value` | string | validation, assertion | Expected value |
| `value_type` | string | retrieve_value | `text`, `number`, `date`, … |
| `value_source` | string | retrieve_value | Where the value is read from |
| `value_format` | string | retrieve_value | Date format when `value_type: "date"` |
| `value_step` | string | (legacy) | Kept for very old exports; no runtime meaning |
| `enable_advanced_click_types` | boolean | navigation | Allow double/right-click actions |
| `browser_action` | string | browser | `navigate`, `reload`, `back`, `forward`, … |
| `browser_args` | string (JSON) | browser | Action arguments, e.g. `{"url": "…"}` |
| `transform_operation` | string | transform | `math`, `date`, `string`, … |
| `transform_args` | string (JSON) | transform | Operation arguments |
| `network_*` (10 fields) | see [Network Assertion Fields](#network-assertion-fields) | network_assertion | Request / mock / response / timing fields |
| `repeat_columns`, `repeat_rows` | see [Repeat Step Fields](#repeat-step-fields) | repeat | Inline dataset (not allowed on template steps; not copied onto execution steps) |
| `dataset_id` | string | repeat | Application dataset reference, alternative to the inline dataset (not allowed on template steps; not copied onto execution steps — the resolved rows are) |

Runtime state (`cached_steps`, `cache_last_updated`, `trajectory_s3_key`, `trajectory_last_updated`) is **not** a definition field: it is copied only from `STEP#` to `EXECUTION_STEP#` and never by export, clone or template operations.

### Import Usecase

Create a usecase from an export JSON (the shape produced by `GET /usecase/{id}/export`; this is what `qa-studio tests import` posts).

**Endpoint**: `POST /import`
**Required Scopes**: `api/usecases.write` — plus `api/templates.read` when the body contains template placeholder steps.

**Request Body**: the export JSON (`exportVersion: "1.0"`, `usecase`, `steps`, `variables`, `secrets`, `hooks`, optional `regionOverride`). Every entry of `steps` is either a regular step or a **template placeholder**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sort` | integer > 0 | yes | Slot where the template's steps are inserted |
| `step_type` | `"template"` | yes | Marks the placeholder; not an executable step type |
| `template_id` | string (UUID) | yes | Template to expand. UUIDs are environment-specific. |

A placeholder may carry **no other field** (`400`). Placeholders are allowed only at the top level of `steps` (not under a `repeat`); the same template may be referenced several times. Templates cannot contain placeholders.

Processing order — **nothing is written until all checks pass**:

1. Placeholder shape check (`400 {"success": false, "message": "steps[i]: …"}`).
2. Scope check for `api/templates.read` if any placeholder is present (`403`).
3. Every referenced template is loaded; any missing → `400 {"success": false, "error": "Template not found", "templateIds": ["…"]}`.
3a. Every `dataset_id` on a repeat step is looked up in the **target** application (`application_id` of the body); any missing → `400 {"success": false, "error": "dataset not found in this application", "message": "dataset not found in this application: <id>[, <id>]", "datasetIds": ["…"]}`. Files without `dataset_id` read nothing. `POST /usecase/{id}/clone` applies the same check against the clone's application.
4. Steps are emitted in file order; each placeholder is replaced by the template's steps (new ids, all [step definition fields](#step-definition-fields), and the linkage `template_id` / `template_step_id` / `template_version`); final `sort` is `1..n`.
5. Template `variables` are merged into the file's `variables` (the file's value wins on a duplicate key). Template `secret_key`s join the file's `secrets` (deduplicated) and get `SECRET#` placeholder records like file secrets.

**Response** (200):

```json
{
  "success": true,
  "usecaseId": "7a7a…",
  "message": "Usecase imported successfully",
  "missingSecrets": ["shop_username", "shop_password"],
  "templatesApplied": [{"templateId": "3f1c…", "version": 4, "stepsCreated": 3}]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `usecaseId` | string | Id of the created usecase (a new usecase is always created; nothing is overwritten) |
| `missingSecrets` | string[] | Omitted when empty. Keys that still need a value via `POST /usecase/{id}/secrets`. |
| `templatesApplied` | object[] | Omitted when no placeholder was present. One entry per placeholder, in file order. |

Files without placeholders behave exactly as before (no template read, no `templatesApplied`).

---

## Template Endpoints

Templates are reusable step blueprints stored at `pk=TEMPLATES, sk=TEMPLATE#{id}` (metadata, incl. `version`) with steps at `pk=TEMPLATE#{id}, sk=STEP#{uuid}`. Template CRUD (`/templates`, `/templates/{id}`, `/templates/{id}/steps…`) requires `api/templates.write` (or `.read` for `GET`s). The endpoints below connect templates to usecases.

### Import Template Definition

Create a template — metadata, steps and variables — from a template file in **one** call (used by `qa-studio templates create`). A failed request leaves no half-built template behind.

**Endpoint**: `POST /templates/import`
**Required Scopes**: `api/templates.write`

**Request Body** (the template file format):

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `templateVersion` | `"1.0"` | yes | — | File format version |
| `template.name` | string, min 1 | yes | — | |
| `template.description` | string | no | `""` | |
| `template.category` | string | no | `""` | |
| `template.tags` | string[] | no | `[]` | |
| `steps` | step[], min 1 | yes | — | Same shape as export-JSON steps (`sort`, `step_type`, `instruction` + [step definition fields](#step-definition-fields)). Renumbered `1..n` in `sort` order. |
| `variables` | `{key: string (min 1), value: string}[]` | no | `[]` | Written as the template's `VARIABLES` record when non-empty |

Secrets are not declared — they are the `secret_key`s of the `secret` steps.

**Errors**: `400 {"error": "templates cannot contain template steps"}` for a `step_type: "template"` step; `400 {"error": "repeat steps are not supported in templates"}` for a `repeat` step or a `parent_step_id`; `400 {"error": "Invalid template file", "message": "<field>: <problem>; …"}` for schema violations; `403` without `api/templates.write`.

**Response** (201):

```json
{"id": "3f1c…", "name": "Login – Shop", "stepsCreated": 4}
```

Records written: `TEMPLATES / TEMPLATE#{id}` (`version: 1`, `created_by` = caller), `TEMPLATE#{id} / STEP#{uuid}` per step, and `TEMPLATE#{id} / VARIABLES` when variables are present. A `steps[].id` in the body is accepted and ignored (new step ids are always generated — see `PUT /templates/{id}` for id-aware updates).

### Replace Template Definition

Replace a template's metadata, steps and variables **atomically** from a template file (used by `qa-studio templates update`). The body is the same format as `POST /templates/import`; steps may carry the `id` of an existing template step.

**Endpoint**: `PUT /templates/{id}`
**Required Scopes**: `api/templates.write`

**Step matching**:

| Step in body | Existing template step | Action |
|---|---|---|
| has `id`, matches | yes | Whole-item put: `id` and `created_at` kept, `sort` = position in the body, every other field from the body (a field removed from the body disappears) |
| has `id`, no match | — | `400 {"error": "steps[i]: id <id> does not belong to template <tid>"}` — nothing written |
| no `id` | — | Put with a fresh uuid |
| — | exists, absent from body | Deleted |

Everything — step puts/deletes, one metadata `Update` (`name`, `description`, `category`, `tags`, `updated_at`, `version + 1`), and a `VARIABLES` put (non-empty) or delete (empty) — goes into **one** `transact_write_items`, so there is exactly one version bump and a failure leaves the template unchanged. DynamoDB transactions hold 100 items; a body with more than **98 steps** is `400 {"error": "template too large for an atomic update (max 98 steps)"}`.

**Errors**: `400` for schema violations (`{"error": "Invalid template file", "message": "steps: duplicate step id …"}` incl. duplicate ids), `step_type: "template"` steps, `repeat` steps, unknown ids, oversize; `404` when the template does not exist; `403` without `api/templates.write`.

**Response** (200):

```json
{"id": "3f1c…", "name": "Login – Shop", "version": 7, "stepsCreated": 1, "stepsUpdated": 4, "stepsDeleted": 0}
```

`stepsUpdated` counts every step matched by `id` (whether or not its content changed). Use-case steps linked to a template step that was deleted keep their `template_step_id`; readers already tolerate that.

### Template Usages

The use cases that have steps linked to a template (via `POST /usecase/{id}/import-template` or placeholder expansion in `POST /import`). Shown by `qa-studio templates get` / `templates delete` and by the web UI's delete dialog *before* a template is deleted.

**Endpoint**: `GET /templates/{id}/usages`
**Required Scopes**: `api/templates.read`

**Response** (200), sorted by `name`:

```json
{"usages": [{"usecase_id": "7b2d…", "name": "Checkout"}, {"usecase_id": "9c01…", "name": "Refund"}], "count": 2}
```

Backed by the `TEMPLATE#{id} / USAGE#{usecase_id}` records (see [Template usage tracking](architecture.md#template-usage-tracking)); a record whose use case no longer exists is skipped and logged — this endpoint never writes. `404` when the template does not exist.

### Delete Template

**Endpoint**: `DELETE /templates/{id}`
**Required Scopes**: `api/templates.write`

Order of operations: (1) for every `USAGE#` record, the linked use-case steps lose their `template_id` / `template_step_id` / `template_version` attributes (the steps themselves are kept — they become plain steps; the update is conditional on `template_id` still matching, so a step relinked concurrently is skipped); (2) the whole `TEMPLATE#{id}` partition (steps, variables, usages) is deleted; (3) the metadata record is deleted last, so a Lambda that dies halfway leaves a template that can simply be deleted again. The unlink runs under `api/templates.write` without per-use-case authorization — it is a system side effect of deleting a shared resource.

**Response**: `204 No Content` (previously `200 {"message"}`). `404` when the template does not exist.

### Apply Template

Create a **new** usecase from a template.

**Endpoint**: `POST /templates/{id}/apply`
**Required Scopes**: `api/templates.read`, `api/usecases.write`

**Request Body**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Name of the new usecase |
| `description` | string | no | Description |
| `starting_url` | string | no | Starting URL |

**Response** (200):

```json
{
  "success": true,
  "usecaseId": "7f3c…",
  "message": "Use case created from template successfully",
  "missingSecrets": ["username", "password"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `usecaseId` | string | Id of the created usecase |
| `missingSecrets` | string[] | Omitted when empty. Distinct `secret_key` values of the copied `secret` steps. Nothing is stored for them yet — the caller collects the values and stores them via `POST /usecase/{id}/secrets` (the web UI shows one password field per key on the template form; until a value is set, a run fails at that step). |

All [step definition fields](#step-definition-fields) of the template steps are copied; template variables become the usecase's variables. The created usecase has no `application_id` and its steps carry no template linkage.

### Import Template into Usecase

Insert a template's steps into an **existing** usecase.

**Endpoint**: `POST /usecase/{id}/import-template`
**Required Scopes**: `api/usecases.write`, `api/templates.read`
**Resource authorization**: `edit` access to the usecase's application (creator-retains-edit applies). `404` when the usecase does not exist.

**Request Body**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `template_id` | string | yes | — | Template to insert |
| `insert_position` | integer | no | `-1` | **Ordinal** position: the template's first step becomes step N. See the contract below. |

| `insert_position` | Meaning |
|---|---|
| omitted / `-1` | append after the last step |
| `0` | treated as `1` (back-compat with the web UI's "At the beginning") |
| `1 … n+1` | template's first step becomes step N (`n` = current step count) |
| `> n+1`, `< -1`, non-integer | `400 {"error": "insert_position must be …"}`; nothing is written |

After the insert **all** steps of the usecase are renumbered `1..n` contiguously (gaps in historical `sort` values disappear); only steps whose `sort` changed are rewritten.

**Response** (201):

```json
{
  "message": "Template imported successfully",
  "steps_created": 4,
  "missingSecrets": ["username", "password"]
}
```

`missingSecrets` has the same meaning as for Apply Template and is omitted when empty. The web UI only asks for keys the use case does not have yet (`GET /usecase/{id}/secrets`). Inserted steps carry `template_id`, `template_step_id` and `template_version` (the template's `version` at insert time); template variables are merged into the usecase variables without overwriting existing keys.

### Update Step from Template

Replace a linked usecase step with the current content of its template step.

**Endpoint**: `POST /usecase/{id}/steps/{stepId}/update-from-template`
**Required Scopes**: `api/usecases.write`, `api/templates.read`
**Resource authorization**: `edit` access to the usecase's application. `404` when the usecase, step, template or template step does not exist; `400` when the step has no `template_id`.

**Response** (200):

```json
{ "message": "Step updated from template", "previous_version": 3, "new_version": 5 }
```

`pk`, `sk`, `id`, `sort` and `created_at` are kept; `instruction`, `step_type` and every [step definition field](#step-definition-fields) are taken from the template step (fields the template step no longer has are removed); `template_version` becomes the template's current `version`.

### Check Template Updates

List the usecase's template-linked steps and whether their template has changed since they were inserted.

**Endpoint**: `GET /usecase/{id}/template-updates`
**Required Scopes**: `api/usecases.read`, `api/templates.read`
**Resource authorization**: `view` access to the usecase's application. `404` when the usecase does not exist.

**Response** (200):

```json
{
  "updates": [
    {
      "step_id": "…", "template_id": "…", "template_step_id": "…",
      "current_version": 3, "latest_version": 5, "has_update": true
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `step_id` | string | Usecase step id |
| `template_id` / `template_step_id` | string | Linkage written at insert time |
| `current_version` | number | `template_version` stored on the step |
| `latest_version` | number | Template's current `version` |
| `has_update` | boolean | `latest_version > current_version` |

Steps without `template_id`, and steps whose template no longer exists, are not listed.

### Template Versioning

`version` is **template-level** (one number per template, starting at `1`) and is incremented by every write to the template:

| Operation | Endpoint | Effect on `version` |
|-----------|----------|---------------------|
| Edit metadata | `PATCH /templates/{id}` | +1 |
| Replace definition | `PUT /templates/{id}` | +1 per request (atomic with the step puts/deletes) |
| Create step | `POST /templates/{id}/steps` | +1 |
| Update step | `PATCH /templates/{id}/steps/{step_id}` | +1 |
| Delete step | `DELETE /templates/{id}/steps/{step_id}` | +1 |
| Reorder steps | `PATCH /templates/{id}/steps/reorder` | +1 per request (atomic with the reorder) |

Consequently any step change flags **all** linked steps of that template as having an update; per-step versioning is not implemented. The bump is conditional on the metadata record existing (no upsert).

---

## Application Configuration Endpoints

Variables, secrets and repeat datasets can be defined once on an application and are inherited by every use case stamped with its `application_id`. **Precedence (lowest → highest): Application → Use case → CLI run override** (`--var`, `--dataset-file`). Variables and secrets merge per key (a use-case key shadows the application key); datasets do not merge — a repeat step references an application dataset **or** carries inline rows.

All routes below are dispatched by the `application_router` Lambda (`/applications/{proxy+}`); none is an explicit API Gateway resource (the `api` stack is at 489/500 resources — see [Architecture → Resource ceiling](architecture.md#application-level-configuration)). Authorization uses the application in the path: reads need `api/applications.read` plus **view** on the application; writes need `api/applications.write` plus **edit** (Editor+ of the owning team or a Full share — the same rule as creating a use case in the application, and looser than `PATCH /applications/{id}`, which is Team Lead only). Status codes shared by all routes: `400` invalid application or dataset id / malformed JSON, `403` missing scope or role, `404` unknown application (or dataset).

### Application Variables

| Method | Endpoint | Scope / access | Body | Response |
|--------|----------|----------------|------|----------|
| GET | `/applications/{id}/variables` | `api/applications.read`, view | — | `200 {"variables": [{"key", "value"}]}` (`[]` when none) |
| POST | `/applications/{id}/variables` | `api/applications.write`, edit | `{"variables": [{"key", "value"}]}` | `200 {"variables": [...]}` |

POST **replaces** the whole list (same as `POST /usecase/{id}/variables`): send every variable to keep. Rules: `key` matches `^[A-Za-z_][A-Za-z0-9_]*$`, keys are unique (`400 duplicate key <k>`), at most 100 entries, `value` is a string. Stored at `APPLICATION#{id}` / `VARIABLES` with `updated_at` and `updated_by`.

```bash
curl -X POST 'https://api.example.com/applications/app-123/variables' \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{"variables": [{"key": "base_api", "value": "https://api.staging.example.com"}]}'
```

### Application Secrets

| Method | Endpoint | Scope / access | Body | Response |
|--------|----------|----------------|------|----------|
| GET | `/applications/{id}/secrets` | `api/applications.read`, view | — | `200 {"secrets": [{"key", "secret_name", "description", "created_at"}]}` — keys only, never values |
| POST | `/applications/{id}/secrets` | `api/applications.write`, edit | `{"secrets": [{"key", "value"}]}` | `201 {"created": ["<key>"], "updated": ["<key>"]}` |
| DELETE | `/applications/{id}/secrets` | `api/applications.write`, edit | `{"secret_key": "<key>"}` | `204 No Content`; `404 {"error": "Secret '<key>' not found"}` |

Secrets live in AWS Secrets Manager as `{SECRET_PREFIX}/application/{app_id}/{key}`, tagged `application_id` (listing filters by tag and name prefix). `key` matches `^[A-Za-z0-9_.-]{1,128}$` (`400 Invalid secret key`); `value` must not be empty (`400 value must not be empty` — Secrets Manager cannot store an empty string); the list must be non-empty and keys unique. Every entry is validated before the first write. POST creates missing keys and updates existing ones; DELETE removes the secret without a recovery window. There is **no application-level value endpoint** — values are only read through `GET /usecase/{id}/secrets/{key}/value` by executors and the worker (see below). `DELETE /applications/{id}` removes all application secrets by tag.

```bash
curl -X POST 'https://api.example.com/applications/app-123/secrets' \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{"secrets": [{"key": "admin_password", "value": "'"$ADMIN_PASSWORD"'"}]}'
# → 201 {"created": ["admin_password"], "updated": []}
```

### Application Datasets

A dataset is a named `columns` + `rows` table (`APPLICATION#{id}` / `DATASET#{dataset_id}`) that repeat steps of the application's use cases reference by `dataset_id` instead of carrying inline rows.

| Method | Endpoint | Scope / access | Body | Response |
|--------|----------|----------------|------|----------|
| GET | `/applications/{id}/datasets` | `api/applications.read`, view | — | `200 {"datasets": [{"dataset_id", "name", "description", "column_count", "row_count", "updated_at"}]}` sorted by name (summaries, no rows) |
| POST | `/applications/{id}/datasets` | `api/applications.write`, edit | `{"name", "description"?, "columns", "rows"}` | `201 {"dataset": {...}}` |
| GET | `/applications/{id}/datasets/{datasetId}` | `api/applications.read`, view | — | `200 {"dataset": {"dataset_id", "name", "description", "columns", "rows", "created_at", "updated_at", "created_by"}}` |
| PUT | `/applications/{id}/datasets/{datasetId}` | `api/applications.write`, edit | `{"name", "description"?, "columns", "rows"}` (full replace) | `200 {"dataset": {...}}` |
| DELETE | `/applications/{id}/datasets/{datasetId}` | `api/applications.write`, edit | — | `204 No Content`, or `409 {"error": "dataset is referenced by repeat steps of this application; remove the references first", "usecases": [{"usecase_id", "name"}]}` |

Validation (`400 {"error": "<joined>", "errors": ["<rule>", ...]}`, one entry per failed rule, same strings as inline repeat steps):

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `name` | string | yes | `^[A-Za-z_][A-Za-z0-9_ -]{0,63}$` (letters, digits, spaces, `_`, `-`; starts with a letter or `_`; ≤ 64 chars). Unique within the application, case-insensitive: `409 {"error": "a dataset named \"<name>\" already exists in this application"}` on create and on rename |
| `description` | string | no (`""`) | — |
| `columns` | list[string] | yes | 1–20 identifiers `^[A-Za-z_][A-Za-z0-9_]*$`, unique, none of `UniqueID`, `Time`, `ExecutionID`, `CreatedAt`, `RepeatIndex`, `RepeatTotal` |
| `rows` | list[list[string]] | yes | 1–100 rows, each with exactly `len(columns)` string cells; `json.dumps(columns) + json.dumps(rows)` ≤ 200 KB |

PUT keeps `dataset_id`, `created_at` and `created_by`. The delete check walks the application's use cases and their steps (bounded queries, no scan); the `usecases` list is sorted by name.

```bash
curl -X POST 'https://api.example.com/applications/app-123/datasets' \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{"name": "customers", "columns": ["first_name", "last_name", "email"],
       "rows": [["Ada", "Lovelace", "ada@example.com"], ["Alan", "Turing", "alan@example.com"]]}'
# → 201 {"dataset": {"dataset_id": "0192…", "name": "customers", "columns": [...], "rows": [...], ...}}
```

### Effective Use Case Variables and Secrets

The use-case routes return the **effective** configuration, so the CLI, TUI and worker keep reading `key`/`value` and see inherited values without any change:

| Endpoint | Change |
|----------|--------|
| `GET /usecase/{id}/variables` | Returns the application layer merged with the use case's own rows. Each row carries `"source": "application" \| "usecase"`. Application rows that the use case does not shadow come first, sorted by key; then the use-case rows in stored order. `POST /usecase/{id}/variables` is unchanged and must receive only the use case's own rows (the web UI never posts inherited rows back). |
| `GET /usecase/{id}/secrets` | Lists the use case's secrets followed by the owning application's secrets whose key is not shadowed; each row carries `source`. Values are never returned. |
| `GET /usecase/{id}/secrets/{key}/value` | Resolves the use-case secret first, then the application secret of the same key; `404` only when both are missing. The access log line gains `source=usecase\|application\|none`. Scope and access are unchanged (`api/usecases.execute`, execute). |
| `POST /usecase/{id}/execute`, `POST /test-suites/{id}/execute` | Snapshot the same effective variable list onto the execution (`EXECUTION#{id}` variables record) and resolve `dataset_id` repeat steps before expansion (see below). |

Example `GET /usecase/{id}/variables`:

```json
{
  "variables": [
    {"key": "base_api", "value": "https://api.staging.example.com", "source": "application"},
    {"key": "environment", "value": "staging", "source": "usecase"}
  ]
}
```

A use case without an application resolves exactly as before (every row `source: "usecase"`).

`GET /usecase/{id}/executions/{executionId}/variables` (scope `api/executions.read`, view access; the run's worker token is accepted too) returns three fields:

| Field | Type | Meaning |
|-------|------|---------|
| `variables` | `list[{key: str, value: str}]` | The use case's **current** `USECASE_VARIABLES` rows (no application rows; edits made after the run show up here). Kept for compatibility. |
| `runtime_variables` | `list[{key: str, value: str}]` | Variables captured during the run (`retrieve_value` / `transform`), final value per key. |
| `execution_variables` | `dict[str, str]` | Snapshot of the merged variables the run started with (application + use case + overrides), read from `EXECUTION#{id} / EXECUTION_VARIABLES`. Filled for single runs (stored as a `{key, value}` list) and suite runs (stored as a map); `{}` when nothing was recorded. |

Clients should prefer `execution_variables` and fall back to `variables` only when it is empty (the CLI does).

### Dataset References on Repeat Steps

| Endpoint | Behaviour |
|----------|-----------|
| `POST /usecase/{id}/steps`, `PATCH /usecase/{id}/steps/{step_id}` | Accept `dataset_id` on `repeat` steps (XOR with `repeat_columns` + `repeat_rows`; see [Repeat Step Fields](#repeat-step-fields)). The dataset must exist in the use case's application: `400 {"error": "dataset not found in this application"}`. |
| `POST /templates/{id}/steps`, `PATCH /templates/{id}/steps/{step_id}` | `400 dataset references (dataset_id) are not supported in templates`. |
| `GET /usecase/{id}/export` | Keeps `dataset_id` on the step (rows are not inlined), so the export is byte-stable and round-trips within the same application. |
| `POST /import`, `POST /usecase/{id}/clone` | Validate every `dataset_id` against the target application before writing anything: `400 {"success": false, "error": "dataset not found in this application", "message": "…: <id>", "datasetIds": ["<id>"]}`. |
| `POST /applications/{id}/usecases` (move in) | `409 {"error": "use case references application datasets", "usecases": [{"usecase_id", "name", "steps": [{"id", "instruction"}]}]}` — switch those steps to inline rows (or re-create the dataset in the target application and repoint them) first. Removing use cases from an application is not affected. |
| `POST /usecase/{id}/execute`, `POST /test-suites/{id}/execute` | Copy the dataset's columns/rows onto the referencing steps before `expand_repeat_steps`, so `repeat_datasets` / `--dataset-file` overrides still replace the table by label. Missing dataset → `400 {"error": "dataset not found", "dataset_id": "…"}` (suite: plus `details.usecase_id`) before any record is written. |

---

## Cost Endpoints

Read-only views of the cost allocation the daily collector writes (design: `.kiro/docs/cost-allocation/design.md`). Nothing is computed on request: each route returns the dimension's `USAGE#… / SUMMARY` item from DynamoDB and, where the response has `days`, the last 30 rows of the dimension's S3 ledger (`cost_allocation/…ndjson`). All three routes are served by the `application_router` Lambda; `GET /applications/{id}/costs` rides `/applications/{proxy+}`, the other two are explicit API Gateway resources (the `api` stack is at 489/500 resources after them).

Until the collector has run for a dimension, `summary` is `null` and `days` is `[]` — still `200`, never `404`. No new scope: reads reuse `api/applications.read` / `api/usecases.read` plus **view** on the resource in the path (team members, Viewer+, or a share at any level); `/dashboard/costs` filters rows exactly like `/dashboard/overview`.

| Method | Endpoint | Scope / access | Response |
|--------|----------|----------------|----------|
| GET | `/applications/{id}/costs` | `api/applications.read`, view on the application | `200 {"summary": <CostSummary>\|null, "days": [<LedgerRow>…], "usecases": [{"usecase_id", "name", "summary": <CostSummary>\|null}]}` |
| GET | `/usecase/{id}/costs` | `api/usecases.read`, view on the use case | `200 {"summary": <CostSummary>\|null, "days": [<LedgerRow>…]}` |
| GET | `/dashboard/costs` | `api/applications.read`; rows filtered to visible applications | `200 {"overall": <CostSummary>\|null, "applications": [{"application_id", "summary": <CostSummary>\|null}]}` |

Shared status codes: `400` invalid id, `403` missing scope or no view access, `404` unknown application / use case (or a use case hidden by a per-test-case override), `500` when the summary item or ledger could not be read.

### Application Costs

`GET /applications/{id}/costs` — the application's summary, its 30-day series and one row per associated use case (`APPLICATION#{id} / USECASE#…`), sorted by `window_30d` descending; use cases without a summary come last with `summary: null`. Use case summaries and names are fetched with one `BatchGetItem` (chunked at 100 keys).

```bash
curl 'https://api.example.com/applications/app-123/costs' -H 'Authorization: Bearer <token>'
```

```json
{
  "summary": {
    "as_of": "2026-11-04",
    "window_1d": 1.42,  "window_1d_trend": "up",  "window_1d_change_pct": 29.1, "window_1d_list": 1.5,
    "window_7d": 9.8,   "window_7d_trend": "up",  "window_7d_change_pct": 10.1, "window_7d_list": 10.2,
    "window_30d": 42.1, "window_30d_trend": null, "window_30d_change_pct": null, "window_30d_list": 44.0,
    "by_source_30d": {"nova_act": 39.0, "compute": 3.1},
    "days_available": 31,
    "estimated_days": 1,
    "updated_at": "2026-11-05T06:02:11Z"
  },
  "days": [
    {"date": "2026-10-06", "estimated": false, "application_id": null,
     "cost": [{"service": "nova_act", "cost": 0.9, "list_cost": 0.95, "usage_seconds": 720.0, "launches": null}],
     "buckets": {"unassigned": 0.0, "unallocated": 0.07, "unmetered": 0.0},
     "collected_at": "2026-10-07T06:02:11Z"},
    "…"
  ],
  "usecases": [
    {"usecase_id": "0192…", "name": "Checkout", "summary": {"as_of": "2026-11-04", "window_30d": 30.0, "…": "…"}},
    {"usecase_id": "0193…", "name": "Brand new", "summary": null}
  ]
}
```

### Use Case Costs

`GET /usecase/{id}/costs` — the use case's summary and 30-day series. `days` comes from the use case's **current** ledger file, i.e. the one under the application it belongs to now (`cost_allocation/_unassigned/…` for a use case without an application, which only studio admins can view). Rows written while the use case belonged to a previous application stay in that application's folder as history and are **not** returned, so the series restarts when a use case is moved.

```bash
curl 'https://api.example.com/usecase/0192…/costs' -H 'Authorization: Bearer <token>'
# → 200 {"summary": {...}, "days": [{"date": "2026-10-06", "application_id": "app-123", "cost": [...], "buckets": null, ...}, "…"]}
```

### Dashboard Costs

`GET /dashboard/costs` — one `{application_id, summary}` row per application the caller may view (own teams' applications plus shared ones; studio admins see all), sorted by `window_30d` descending with missing summaries last. `overall` is the studio-wide `USAGE#OVERALL / SUMMARY` and is returned **only to studio admins** (`isAdmin` or the `api/admin` scope); every other caller gets `"overall": null`. The `unassigned` / `unallocated` / `unmetered` buckets are not broken out as rows (they are visible per day in the overall ledger's `buckets`). This route reads SUMMARY items only — one `BatchGetItem` per 100 applications — and never a ledger.

```bash
curl 'https://api.example.com/dashboard/costs' -H 'Authorization: Bearer <token>'
# → 200 {"overall": {"as_of": "2026-11-04", "window_30d": 99.0, "…": "…"},
#        "applications": [{"application_id": "app-123", "summary": {...}}, {"application_id": "app-456", "summary": null}]}
```

### Cost Summary and Ledger Row Fields

`CostSummary` (the `summary` / `overall` object; the SUMMARY item minus `pk`/`sk`). Money is USD, serialised with 6 decimals.

| Field | Type | Description |
|-------|------|-------------|
| `as_of` | `YYYY-MM-DD` | Newest day included |
| `window_1d`, `window_7d`, `window_30d` | number | Allocated bill over the last 1 / 7 / 30 days ending at `as_of` |
| `window_1d_trend`, `window_7d_trend`, `window_30d_trend` | `"up"` \| `"down"` \| `"flat"` \| null | Current window vs. the previous window of the same length; `null` until `2 × window` days of data exist; `flat` within ±5 % |
| `window_1d_change_pct`, `window_7d_change_pct`, `window_30d_change_pct` | number \| null | Percentage behind the trend; `null` when the previous window is 0 |
| `window_1d_list`, `window_7d_list`, `window_30d_list` | number | The same windows at list price |
| `by_source_30d` | map `source → number` | `nova_act`, `compute` |
| `days_available` | integer | Ledger rows that exist for the dimension (UI: "not enough data") |
| `estimated_days` | integer | Rows in the 30-day window still flagged `Estimated` by Cost Explorer |
| `updated_at` | ISO 8601 | When the collector last wrote the summary |

`LedgerRow` (one entry of `days`, oldest first, at most 30):

| Field | Type | Description |
|-------|------|-------------|
| `date` | `YYYY-MM-DD` | UTC day |
| `estimated` | boolean | Cost Explorer `Estimated` flag for that day |
| `application_id` | string \| null | Use case rows only: the application the use case belonged to on that day |
| `cost[]` | list | One entry per source: `{"service": "nova_act" \| "compute", "cost", "list_cost", "usage_seconds", "launches": integer \| null}` (`launches` is set for `compute` only) |
| `buckets` | object \| null | Application and overall rows only: `{"unassigned", "unallocated", "unmetered"}` in USD |
| `collected_at` | ISO 8601 | Last (re-)processing time of the row |

---

## Execution Endpoints

### Execute Usecase

Create and start a usecase execution.

**Endpoint**: `POST /usecase/{id}/execute`

**Path Parameters**:
- `id` (string, required) - Usecase ID

**Query Parameters**:
- `trigger-type` (string, optional, default `OnDemandHeadless`) - Execution trigger type:

  | Value | Behaviour | Used by |
  |-------|-----------|---------|
  | `OnDemandHeadless` (default) | Starts a cloud worker: one Lambda MicroVM per execution | UI "Trigger Execution", suite runs, API callers without the parameter |
  | `Scheduled` | Starts a cloud worker (one Lambda MicroVM per execution) | EventBridge schedules |
  | `ci_runner` | Creates the execution record only, no cloud worker. The **only** trigger allowed for `test_platform: "electron"` use cases | CI/CD runner (`qa-studio run`) |

  Any other value, including the removed use-case-level `OnDemand`, returns `400` naming the valid values, before
  any record is written. (`OnDemand` is still valid on `POST /test-suites/{id}/execute`, where it means "spawn each
  use case headless".) Historical execution records may still carry `trigger_type: "OnDemand"`.
- `suite-execution-id` (string, optional) - Suite execution ID if part of a suite
- `suite-id` (string, optional) - Suite ID if part of a suite

**Required Scopes**: `api/usecases.execute` or `api/admin`, plus **execute** on the use case's owning application (Executor+ of the owning team, a team with an Execute/Full share, or an OAuth client bound to such a team). Orphan use cases (no application) are Admin-only. The worker identity can't start executions.

For `Scheduled` and `OnDemandHeadless` runs the execution record gets a `worker_token_hash` and the worker gets the matching token as `execution_token` in the MicroVM run-hook payload (see [`X-QA-Execution-Token`](#x-qa-execution-token-header)). The token is never returned in the response.

**Request Body** (optional JSON):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `repeat_datasets` | object | absent | `{"<repeat label>": {"columns": [...], "rows": [[...]]}}` — replaces the stored rows of the labelled repeat step for this execution. Columns must equal the repeat's columns (order-insensitive; rows are re-ordered to the stored column order). Same caps as stored datasets. |

```json
{
  "repeat_datasets": {
    "Login as each user": {
      "columns": ["email", "role"],
      "rows": [["alice@staging.example", "Administrator"], ["bob@staging.example", "Viewer"]]
    }
  }
}
```

`400` (no records written) when: malformed JSON, unknown label, column mismatch, caps exceeded, or a repeat step that cannot be unrolled (zero rows, zero children). `POST /test-suites/{id}/execute` rejects `repeat_datasets` with `400 "repeat_datasets is not supported for suites"`.


**Response (Scheduled/OnDemandHeadless)**:
```json
{
  "status": "microvm started",
  "usecaseId": "usecase-123",
  "executionId": "execution-456",
  "microvmId": "mvm-0123456789abcdef0",
  "cloudWatchLogsUrl": "https://console.aws.amazon.com/cloudwatch/..."
}
```

`cloudWatchLogsUrl` is a deep link to the worker's log stream (`/qa-studio/<baseName>/microvm`, stream named after the execution id). `microvmId` is the VM's identifier; both are stored on the execution record as `microvm_id` and `cloudwatch_logs_url`. If the launch fails (after the `RunMicrovm` throttling retries, 5 attempts) the response is `500 {"error": "Failed to start MicroVM: …"}` and the execution is marked `failed` with that message.

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
- `400 Bad Request` - `{"error": "Electron usecases can only be executed by the CI runner (qa-studio run)"}` when `test_platform` is `electron` and `trigger-type` is not `ci_runner`. Returned before any execution record is written. The suite execute endpoint returns the same error with `details.usecase_ids` listing the offending usecases.
- `400 Bad Request` - `{"error": "dataset not found", "dataset_id": "…"}` when a repeat step references an application dataset that no longer exists in the use case's application (or the use case has no application). Returned before any execution record is written. The suite execute endpoint returns the same body with `details.usecase_id`. A `repeat_datasets` override for that label does not bypass the check.
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Missing `api/usecases.execute`, no execute access on the owning application, orphan use case, unbound OAuth client, or worker identity
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

### Update Execution Status

Set the status of an execution. Called by the runner (worker token or `api/executions.write`) when the run starts and when it finishes; CI runners use it the same way.

**Endpoint**: `PATCH /usecase/{id}/executions/{executionId}/status`

**Required Scopes**: `api/executions.write` or `api/admin`, or a valid [`X-QA-Execution-Token`](#x-qa-execution-token-header)

**Request Body**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | yes | `pending`, `running`, `completed`, `failed`, `success` |
| `error_message` | string | no | Stored on the record for `failed`; the runner uses the prefixes `timeout:` and `terminated:` for runs stopped by a ceiling or SIGTERM, the reconciler uses `reconciler:` |
| `nova_session_id` | string | no | Nova Act session id for the artifact browser |

**Response**: `200 {"execution_id", "status", "updated_at"}`. On a terminal transition (`success`, `failed`) the Lambda also records the VM's lifetime on the execution record (`microvm_started_at` / `microvm_terminated_at` from `GetMicrovm`, best-effort; see [MicroVM attributes](architecture.md#data-storage)), emits `nova-act-qa-studio.execution.status.changed`, updates suite counters, clears cache artifacts (`failed`) and deletes the `RUNNING_EXECUTIONS` tracking record (MicroVM).

**Error Responses**:
- `400 Bad Request` - Missing or invalid `status`
- `404 Not Found` - Execution not found
- `409 Conflict` - `{"error": "execution already terminal", "status": "<current>"}`: the record is already `success`, `failed`, `stopped`, `error` or `completed` and the request carries a *different* status. Nothing is written. Repeating the same terminal status returns `200` (idempotent no-op). This is how a `stopped` execution stays `stopped` when the terminated runner reports `failed` a few seconds later.

---

### Stop Execution

Stop a running cloud execution and terminate its worker.

**Endpoint**: `POST /usecase/{id}/executions/{executionId}/stop`

**Required Scopes**: `api/executions.write` or `api/admin`, plus **execute** on the owning application

**Behaviour**: the record is set to `stopped` *first*, then `TerminateMicrovm(microvm_id)` is called; the platform's `/terminate` hook SIGTERMs the runner, whose own `failed` report is rejected with `409`. The VM's lifetime is then recorded on the execution record (`microvm_started_at` from `GetMicrovm.startedAt`, `microvm_terminated_at` = the stop time, because the VM is still winding down; best-effort) and the `RUNNING_EXECUTIONS` tracking record is deleted. On dev the VM reaches `TERMINATED` about 22 s after the call.

**Response**:
```json
{ "status": "stopped", "executionId": "execution-456", "microvmId": "mvm-0123456789abcdef0", "stoppedAt": "2026-05-01T10:35:00Z" }
```

**Error Responses**:
- `400 Bad Request` - `execution has no associated MicroVM` (a `ci_runner` execution, or a record from before the MicroVM runner that only carries `task_arn` — those are all terminal), or `execution is already in terminal state: <status>`
- `404 Not Found` - Execution not found
- `500 Internal Server Error` - Server error (a failed `TerminateMicrovm` is logged, not returned: the record is already `stopped`)

---

### Update Execution Step Status

Update the status of an individual execution step. Used by CI/CD runners to report step progress.

**Endpoint**: `PATCH /usecase/{id}/executions/{executionId}/steps/{stepId}/status`

**Path Parameters**:
- `id` (string, required) - Usecase ID
- `executionId` (string, required) - Execution ID
- `stepId` (string, required) - Step ID

**Required Scopes**: `api/executions.write` or `api/admin`

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

**Required Scopes**: `api/executions.write` or `api/admin`

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

**Required Scopes**: `api/executions.write` or `api/admin`

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

### Runtime Variables

Upsert a single captured runtime variable on an in-flight execution. Called by the CLI runner once per `retrieve_value` or `transform` step so the UI reflects captured values incrementally rather than only at completion.

**Endpoint**: `POST /api/usecase/{id}/executions/{executionId}/runtime-variables`

**Scope**: `api/executions.write`

**Path Parameters**:

| Parameter | Type | Description |
|---|---|---|
| `id` | string | Usecase ID |
| `executionId` | string | Execution ID |

**Request Body**:

```json
{
  "key": "orderId",
  "value": "ORD-42"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `key` | string | Yes | Variable name (≤128 chars, may be a DynamoDB reserved word) |
| `value` | string / number / bool | Yes | Variable value. Coerced to string on storage (≤4096 chars) |

**Responses**:

| Status | Meaning |
|---|---|
| 200 | `{"status": "ok", "key": "<key>"}` |
| 400 | Missing key/value, oversized value, or invalid body |
| 403 | Missing `api/executions.write` scope |
| 404 | Execution variables record not found |
| 500 | DynamoDB error |

---

### Live View

The live-view URL is the user-visible streaming URL of a running AgentCore browser session. The runner publishes it at provisioning time; the frontend polls `GET` and the runner cleans up with `DELETE` on teardown.

#### Publish Live View

**Endpoint**: `POST /api/usecase/{id}/executions/{executionId}/live-view`

**Scope**: `api/executions.write`

**Request Body**:

```json
{
  "live_view_url": "https://live.example.com/session-abc"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `live_view_url` | string | Yes | HTTPS URL of the live view, ≤2048 chars |

**Responses**: 200 (`{"status": "ok"}`), 400 (bad URL), 403, 500.

#### Delete Live View

**Endpoint**: `DELETE /api/usecase/{id}/executions/{executionId}/live-view`

**Scope**: `api/executions.write`

**Responses**:

| Status | Meaning |
|---|---|
| 204 | Deleted |
| 403 | Missing scope |
| 404 | No live-view record to delete (callers may treat as already-clean) |
| 500 | DynamoDB error |

---

### Mobile Metadata

Partial update for Device Farm session metadata on a mobile execution. Called by the runner right after the session starts (session ARN only) and again after the session stops (final ARN + optional device details).

**Endpoint**: `PATCH /api/usecase/{id}/executions/{executionId}/mobile-metadata`

**Scope**: `api/executions.write`

**Request Body** (at least one field required; missing fields are NOT cleared server-side):

```json
{
  "device_farm_session_arn": "arn:aws:devicefarm:us-west-2:123456789012:session:abcdef",
  "device_name": "Pixel 6",
  "device_os_version": "Android 13"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `device_farm_session_arn` | string | No | Must start with `arn:aws:devicefarm:` |
| `device_name` | string | No | ≤512 chars |
| `device_os_version` | string | No | ≤512 chars |

**Responses**: 200 (`{"status": "ok", "updated_fields": [...]}`), 400, 403, 404 (execution not found), 500.

---

### Use Case Headers

Custom HTTP headers sent with every request of the use case's executions. Stored as one `HEADERS` record per use case.

| Method | Endpoint | Scope | Body / Response |
|--------|----------|-------|-----------------|
| GET | `/api/usecase/{id}/headers` | `api/usecases.read` | `{"headers": {"<name>": "<value>"}}` (`{}` when none) |
| POST | `/api/usecase/{id}/headers` | `api/usecases.write` | Body `{"headers": {"<name>": "<value>"}}`; responds `{"message": "Headers saved successfully"}` |

POST **replaces** the whole map: send every header to keep. The web UI's Headers tab merges new rows into the current map on save and posts the map without the key on delete.

---

### Get Execution Headers

Read-only access to custom HTTP headers stored on an execution. The runner reads these and calls `nova.page.set_extra_http_headers(...)` before navigation. Returns `{"headers": {}}` (not 404) when no headers are configured.

**Endpoint**: `GET /api/usecase/{id}/executions/{executionId}/headers`

**Scope**: `api/executions.read`

**Response**:

```json
{
  "headers": {
    "X-Custom": "value",
    "Authorization": "Bearer …"
  }
}
```

---

### Trajectory Upload/Download URLs

Presigned S3 URLs for per-step trajectory JSONs used by Nova Act's trajectory-replay cache.

#### Request Upload URL

**Endpoint**: `POST /api/usecase/{id}/steps/{stepId}/trajectory/upload-url`

**Scope**: `api/executions.write`

**Request Body**:

```json
{
  "content_type": "application/json"
}
```

**Response**:

```json
{
  "upload_url": "https://s3.example.com/…",
  "s3_key": "uc-1/trajectories/step-1.json",
  "expires_in": 900
}
```

Calling this endpoint atomically writes `trajectory_s3_key` and `trajectory_last_updated` on the STEP record server-side. If the runner's subsequent PUT fails, the pointer is stale; the next replay attempt triggers cleanup via the `clear_cache_fields` extension on the step-status endpoint.

#### Get Download URL

**Endpoint**: `GET /api/usecase/{id}/steps/{stepId}/trajectory/download-url`

**Scope**: `api/executions.write` (cache data is execution-flow-sensitive)

**Response (200)**:

```json
{
  "download_url": "https://s3.example.com/…",
  "expires_in": 900
}
```

**Response (404)**: when no trajectory has been recorded for the step — expected when the step hasn't been executed yet.

---

### Clear Cache Fields on Step Status

The existing `PATCH /api/usecase/{id}/executions/{executionId}/steps/{stepId}/status` endpoint accepts an optional `clear_cache_fields` array that lets the runner clean up stale cache pointers in the same request.

**Allow-listed field names** (anything else rejected 400):
- `trajectory_s3_key`
- `trajectory_last_updated`
- `cached_steps`
- `cache_last_updated`

**Example**:

```json
{
  "status": "failed",
  "error_message": "step timed out",
  "clear_cache_fields": ["trajectory_s3_key", "trajectory_last_updated"]
}
```

The server does a combined `SET status = …, REMOVE trajectory_s3_key, trajectory_last_updated` in a single DynamoDB update. No extra round-trip.

---

## Wizard Session Endpoints

The interactive wizard runs `wizard_worker.py` on a Lambda MicroVM started with `mode: wizard` — the same image and supervisor as batch executions (see [architecture → Stop and timeout paths](architecture.md#stop-and-timeout-paths)). The session is bounded by `maxWizardSessionMinutes` (default 240) and ends after 30 minutes without activity. Only the two endpoints that touch the VM are listed here; the step/accept/reject/command/recording routes are UI-internal.

### Start Wizard Session

**Endpoint**: `POST /wizard/start`

**Required Scopes**: `api/usecases.write` or `api/admin`, plus **edit** on the application in the body

**Request Body**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `application_id` | string | Yes | Application the new use case belongs to |
| `name` | string | Yes | Name of the use case the wizard creates |
| `starting_url` | string | Yes | URL the wizard browser opens first |
| `description` | string | No | Use-case description |
| `executing_region` | string | No | Region the AgentCore browser runs in (default: the stack's default region) |
| `model_id` | string | No | Nova Act model id (default `nova-act-v1.0`) |
| `tags` | string[] | No | Tags for the new use case |

**Response** (`201 Created`):
```json
{
  "sessionId": "01a18ed0-…",
  "usecaseId": "usecase-123",
  "status": "initializing",
  "microvmId": "mvm-0123456789abcdef0"
}
```

The session id is also the execution id of the wizard's execution record (`status: pending`, `wizard_status: active`, `microvm_id`, `cloudwatch_logs_url`). A launch failure returns `500 {"error": "Failed to start MicroVM: …"}` and leaves the session `failed`.

### Terminate Wizard Session

**Endpoint**: `POST /wizard/{sessionId}/terminate/{usecaseId}`

**Required Scopes**: `api/usecases.write` or `api/admin`, plus **edit** on the use case

**Behaviour**: the execution record is made terminal *first* (`status = success`, `wizard_status = closed`, `completed_at`; an already `failed` / `timeout` record keeps its status), then the `terminate` command is sent to the worker, then `TerminateMicrovm(microvm_id)` is called, the VM's lifetime is recorded on the execution record (`microvm_started_at` / `microvm_terminated_at` from `GetMicrovm`; the VM's own `terminatedAt` when the worker already ended the session, otherwise the terminate time; best-effort) and the `RUNNING_EXECUTIONS` record is deleted. The worker's SIGTERM handler only cleans up the browser.

**Response** (`200 OK`):
```json
{ "status": "terminated", "microvmId": "mvm-0123456789abcdef0" }
```

`microvmId` is omitted when the session's record carries no `microvm_id` (a session started before the MicroVM runner).

**Error Responses**:
- `400 Bad Request` - Missing or invalid `sessionId` / `usecaseId`
- `403 Forbidden` - Insufficient scopes or no edit access to the use case
- `404 Not Found` - Session not found under the use case
- `500 Internal Server Error` - Error terminating the session (a failed `TerminateMicrovm` is logged, not returned)

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

Create a suite execution record and execution records for all usecases in a test suite with overrides applied. This endpoint is designed for CI/CD runners and does not start cloud workers.

**Endpoint**: `POST /test-suites/{id}/execute`

**Path Parameters**:
- `id` (string, required) - Test suite UUID

**Required Scopes**: `api/suite.write`, `api/executions.write`

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
- `variables` (object, optional) - Variable overrides (key-value pairs). Precedence: CLI > usecase. Secret values are never copied into execution variables; the runner reads them per step.
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
  "message": "Missing required scopes: api/suite.write, api/executions.write",
  "required_scopes": ["api/suite.write", "api/executions.write"],
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
- No cloud workers (MicroVMs) are started when using `trigger_type=ci_runner`
- All execution records are created with `status=pending`
- Base URL override replaces only the scheme and domain, preserving path and query parameters
- Variable merge precedence: CLI overrides > usecase variables (secret values are not merged)
- Maximum recommended suite size: 10 usecases (to avoid API Gateway timeout)

---

## OAuth Client Management

OAuth clients enable machine-to-machine (M2M) authentication for CI/CD pipelines and automated systems. Clients use the OAuth 2.0 client credentials flow and are scoped to specific API permissions.

### Create OAuth Client

Create a new OAuth client with specified scopes for CI/CD authentication.

**Endpoint**: `POST /api/oauth-clients`

**Required Scopes**: `api/oauth-clients.write` or `api/admin`, and Editor+ in `teamId` (or Admin)

**Request Body**:
```json
{
  "name": "CI/CD Runner - Production",
  "teamId": "team-123",
  "scopes": [
    "api/suite.read",
    "api/suite.write",
    "api/executions.write"
  ]
}
```

**Request Body Fields**:
- `name` (string, required) - Client name for identification
- `teamId` (string, required) - Team the client is bound to. The client acts with `team_role` = your role in that team, capped at `editor` (Admins create `editor` clients)
- `scopes` (array, required) - List of OAuth scopes to grant
  - User can only grant scopes they possess (unless admin)
  - `api/admin` and `api/teams.manage` can't be granted to a client, even by an Admin (400)

**Response (201 Created)**:
```json
{
  "client_id": "7abc123def456",
  "client_secret": "secret_xyz789...",
  "client_name": "CI/CD Runner - Production",
  "scopes": [
    "api/suite.read",
    "api/suite.write",
    "api/executions.write"
  ],
  "created_date": "2026-02-16T12:00:00Z",
  "created_by": "user@example.com",
  "team_id": "team-123",
  "team_role": "editor",
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
- `team_id` - Team the client is bound to
- `team_role` - The client's role in that team (`editor`, `executor` or `viewer`)
- Token validity fields in minutes/days

**Error Responses**:
- `400 Bad Request` - Invalid scopes, `api/admin` / `api/teams.manage` requested, missing name, missing `teamId`, or invalid request format
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Insufficient scopes, not Editor+ in `teamId`, or privilege escalation attempt
- `404 Not Found` - `teamId` doesn't exist
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
    "teamId": "team-123",
    "scopes": [
      "api/suite.read",
      "api/suite.write",
      "api/executions.write"
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
        'teamId': 'team-123',
        'scopes': [
            'api/suite.read',
            'api/suite.write',
            'api/executions.write'
        ]
    }
)

data = response.json()
client_id = data['client_id']
client_secret = data['client_secret']

print(f"Client ID: {client_id}")
# The secret is shown only once. Store it securely; never print or log it.
import boto3, json
boto3.client('secretsmanager').put_secret_value(
    SecretId='qa-studio/ci-client',  # an existing secret you control
    SecretString=json.dumps({'client_id': client_id, 'client_secret': client_secret}),
)
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
    teamId: 'team-123',
    scopes: [
      'api/suite.read',
      'api/suite.write',
      'api/executions.write'
    ]
  })
});

const data = await response.json();
console.log(`Client ID: ${data.client_id}`);
// data.client_secret is shown only once. Store it in a secrets manager
// (e.g. AWS Secrets Manager or your CI secret store); never print or log it.
```

**Security Notes**:
- Client secret is ONLY returned at creation - save it securely
- Users cannot grant scopes they don't possess (prevents privilege escalation)
- Admin users can grant any scope except `api/admin` and `api/teams.manage`
- The authorizer reads the binding on every (uncached) request; clients created before team binding have no `team_id` and get 403 on team-owned resources. Re-create them with a `teamId`

---

### List OAuth Clients

List OAuth clients with metadata. Admins see every client; other callers see only clients bound to teams where they are Editor or Team Lead.

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
      "team_id": "team-123",
      "allowed_oauth_scopes": [
        "api/suite.read",
        "api/suite.write",
        "api/executions.write"
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
- `team_id` is `null` for unbound legacy clients (shown as "Unbound (no access)" in the UI)

---

### Delete OAuth Client

Delete an OAuth client, immediately revoking its credentials.

**Endpoint**: `DELETE /api/oauth-clients/{clientId}`

**Path Parameters**:
- `clientId` (string, required) - OAuth client ID to delete

**Required Scopes**: `api/oauth-clients.write` or `api/admin`, and the caller must be the client's creator, a Team Lead of the client's team, or an Admin

**Response (204 No Content)**: empty body

**Error Responses**:
- `400 Bad Request` - Missing client ID
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Client not created through application, or caller isn't the creator, a Team Lead of the client's team, or an Admin
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

if response.status_code == 204:
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
- Only the creator, a Team Lead of the client's team, or an Admin can delete a client

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
- `400 Bad Request` - Missing client ID, or the client holds `api/admin` / `api/teams.manage` (re-create it instead)
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Caller isn't the creator, a Team Lead of the client's team, or an Admin
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
new_client_secret = data['client_secret']

print(f"New Client ID: {new_client_id}")
# The secret is shown only once. Store it securely; never print or log it.
import boto3, json
boto3.client('secretsmanager').put_secret_value(
    SecretId='qa-studio/ci-client',  # an existing secret you control
    SecretString=json.dumps({'client_id': new_client_id, 'client_secret': new_client_secret}),
)
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
// data.client_secret is shown only once. Store it in a secrets manager
// (e.g. AWS Secrets Manager or your CI secret store); never print or log it.
console.log(`Rotated at: ${data.rotated_at}`);
```

**Security Notes**:
- Old secret is immediately invalidated - update all systems using the client
- Client ID changes during rotation - update configuration accordingly
- New secret is ONLY shown once - save it securely
- Only the creator, a Team Lead of the client's team, or an Admin can rotate a client

**Implementation Notes**:
- Cognito doesn't support in-place secret rotation
- Rotation deletes and recreates the app client with same settings
- All configuration (scopes, token validity, `team_id`, `team_role`) is preserved

---

## User Management Endpoints

### Delete User

**Endpoint**: `DELETE /users/{userId}`

**Path Parameters**:
- `userId` (string, required) - Cognito username of the user (the `userId` returned by `GET /users`; a GUID on
  email-username pools)

**Required Scopes**: `api/admin`

Served by the application router (`handlers/delete_user.py`). In order:

1. Last-admin guard: deleting the final member of the global `admins` group returns `409`; if the check itself
   fails, `500` and nothing is deleted.
2. Every team membership record (`TEAM#{team_id}` / `MEMBER#{user_sub}`) of the user is deleted.
3. The Cognito user is deleted (an already-missing user is not an error).
4. A `user_delete` audit entry is written with the actor, the target `user_sub` and `removed_teams`.

**Response**: `204 No Content` (empty body).

| Status | When |
|--------|------|
| 204 | Deleted |
| 400 | Missing `userId` |
| 403 | Caller lacks `api/admin` |
| 409 | Last studio admin |
| 500 | Last-admin check or Cognito delete failed |

---

## Error Handling

### Standard Error Response Format

All error responses follow this consistent format:

```json
{
  "error": "Error type or category",
  "message": "Detailed error description",
  "required_scopes": ["api/executions.write"],
  "token_scopes": ["api/executions.read"]
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
  "message": "Missing required scopes: api/suite.write, api/executions.write",
  "required_scopes": ["api/suite.write", "api/executions.write"],
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

**Team Access Denied** (scope present, but no role in the owning team or a matching share, which includes unbound OAuth clients):
```json
{
  "error": "Forbidden",
  "message": "No access to this application"
}
```

Other messages: `"Insufficient permissions for this action"` (role or share level too low), `"Application not accessible"` (orphan resource, Admin-only), `"Team lead of the owning team required"` (application update/delete).

**Worker Without a Valid Execution Token**:
```json
{
  "error": "Forbidden",
  "message": "Worker capability required"
}
```

**Solution**: Ask a Team Lead to add you (or bind your OAuth client) to the owning team with the required role. See [Team ownership and access control](#team-ownership-and-access-control).

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
  -d 'scope=api/suite.read api/suite.write api/executions.read api/executions.write')

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
                'scope': 'api/suite.read api/suite.write api/executions.read api/executions.write'
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
2. **Egress**: the worker VMs reach AWS services over the public internet (`NO_INGRESS` connector, no VPC); the API is TLS-only behind API Gateway
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

### Application-level variables, secrets and datasets
**Added**:
- `GET`/`POST /applications/{id}/variables`, `GET`/`POST`/`DELETE /applications/{id}/secrets`, `GET`/`POST /applications/{id}/datasets`, `GET`/`PUT`/`DELETE /applications/{id}/datasets/{datasetId}` (all via the application router; `api/applications.read` + view, `api/applications.write` + edit)
- `dataset_id` on repeat steps (XOR with inline rows; kept by export/import/clone; rejected on template steps)
- `source` on the rows of `GET /usecase/{id}/variables` and `GET /usecase/{id}/secrets`

**Changed**:
- `GET /usecase/{id}/variables` returns the effective (application + use case) list; `GET /usecase/{id}/secrets/{key}/value` falls back to the application secret
- `POST /import`, `POST /usecase/{id}/clone`: `400` with `datasetIds` for unknown dataset references; `POST /usecase/{id}/execute`, `POST /test-suites/{id}/execute`: `400 dataset not found` before any write
- `POST /applications/{id}/usecases`: `409` when a moved use case references datasets; `DELETE /applications/{id}` also deletes the application's secrets

### Team-bound authorization (security fixes C-1, H-1, H-2, H-3)
**Breaking**:
- Every team-owned resource route checks the caller's role in the owning team; orphan resources are Admin-only
- `POST /oauth-clients` and `POST /applications` require `teamId`; `POST /import`, `POST /wizard/start` and `POST /templates/{id}/apply` require `application_id`; wizard `step` / `command` require `usecaseId` in the body (`POST /wizard/{sessionId}/restart` was removed — the unified wizard has no restart)
- OAuth clients without a team get 403 on team-owned resources; `api/admin` and `api/teams.manage` are never granted to or honored for clients
- `POST /usecase/{id}/execute` and `GET /usecase/{id}/secrets/{key}/value` require `api/usecases.execute`; trajectory download URLs require `api/executions.read`
- Application create/update/delete: Team Lead of the owning team or Admin
- Team member endpoints reject `role: "admin"` (400); the last `admins` member can't be demoted or deleted (409)
- More deletes return 204 (see [Deletes return 204](#deletes-return-204))

**Added**:
- `X-QA-Execution-Token` header for the cloud worker
- `team_id` / `team_role` on OAuth client responses

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
| `api/executions.write` | Executions | Write | Create and update executions |
| `api/executions.read` | Executions | Read | Read execution data |
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

| Trigger Type | Description | MicroVM started | Use Case |
|--------------|-------------|-----------------|----------|
| `OnDemandHeadless` | One Lambda MicroVM per execution | Yes | Default; UI-triggered execution |
| `Scheduled` | One Lambda MicroVM per execution | Yes | EventBridge scheduled |
| `ci_runner` | Record only | No | CI/CD integration |

These are the use-case trigger types (`POST /usecase/{id}/execute`). The suite endpoint accepts `OnDemand`,
`scheduled` and `ci_runner`.

---

**Last Updated**: 2024-02-16  
**API Version**: 1.2.0  
**Document Version**: 1.0.0
