# OAuth Client Management - Design Document

## Overview

This design document specifies the OAuth client management system for CI/CD authentication. The system allows users to create, list, delete, and rotate OAuth clients (M2M tokens) that use the OAuth 2.0 client credentials flow. OAuth clients enable CI/CD pipelines to authenticate with the API without user credentials.

The implementation builds on existing endpoints (`create_oauth_client.py`, `delete_oauth_client.py`, `list_oauth_clients.py`) and adds a new secret rotation endpoint. The design emphasizes security through scope validation, preventing privilege escalation, and ensuring client secrets are only shown once.

## Architecture

### System Components

```
┌─────────────────┐
│   Frontend UI   │
│  (React/AWS)    │
└────────┬────────┘
         │ HTTPS/JWT
         ▼
┌─────────────────┐
│  API Gateway    │
│  + Authorizer   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│ Lambda Functions│◄────►│   Cognito    │
│  - create       │      │  User Pool   │
│  - list         │      │              │
│  - delete       │      │ (stores      │
│  - rotate       │      │  secrets)    │
└────────┬────────┘      └──────────────┘
         │
         ▼
┌─────────────────┐
│    DynamoDB     │
│  (metadata)     │
└─────────────────┘
```

### Data Flow

1. **Create OAuth Client**:
   - User submits client name and requested scopes
   - Lambda validates user has all requested scopes (prevents privilege escalation)
   - Lambda creates Cognito app client with client credentials flow
   - Lambda stores metadata in DynamoDB
   - Client secret returned once (never stored in DynamoDB)

2. **List OAuth Clients**:
   - Lambda queries Cognito for all app clients
   - Lambda enriches with metadata from DynamoDB (created_by)
   - Client secrets never returned

3. **Delete OAuth Client**:
   - Lambda verifies user owns the client (via DynamoDB metadata)
   - Lambda deletes from Cognito (immediate revocation)
   - Lambda deletes metadata from DynamoDB

4. **Rotate Client Secret**:
   - Lambda verifies user owns the client
   - Lambda deletes old Cognito app client
   - Lambda creates new Cognito app client with same settings
   - Lambda updates DynamoDB metadata with new client_id
   - New client secret returned once

## Components and Interfaces

### Lambda Functions

#### 1. Create OAuth Client (`create_oauth_client.py`)

**Status**: Already implemented

**Purpose**: Create a new OAuth client in Cognito with specified scopes

**Input**:
```python
{
    "name": str,              # Client name (required)
    "scopes": list[str]       # Requested scopes (required)
}
```

**Output**:
```python
{
    "client_id": str,
    "client_secret": str,     # Only shown once
    "client_name": str,
    "scopes": list[str],
    "created_date": str,      # ISO8601
    "created_by": str,
    "refresh_token_validity": int,
    "access_token_validity": int,
    "id_token_validity": int
}
```

**Key Logic**:
- Extract user identity and scopes from JWT token
- Validate requested scopes exist in Cognito resource server
- **Security Check**: Verify user has all requested scopes (unless admin)
- Create Cognito app client with client credentials flow
- Store metadata in DynamoDB with rollback on failure
- Return client secret (only time it's accessible)

**Error Handling**:
- 400: Invalid scopes, missing name
- 403: Privilege escalation attempt (requesting scopes user doesn't have)
- 429: Too many OAuth clients
- 500: Cognito or DynamoDB errors

#### 2. List OAuth Clients (`list_oauth_clients.py`)

**Status**: Already implemented

**Purpose**: List all OAuth clients in the user pool with metadata

**Input**: None (query parameters)

**Output**:
```python
{
    "clients": list[{
        "client_id": str,
        "client_name": str,
        "created_date": str,
        "last_modified_date": str,
        "created_by": str,           # From DynamoDB
        "refresh_token_validity": int,
        "access_token_validity": int,
        "id_token_validity": int,
        "token_validity_units": dict,
        "explicit_auth_flows": list[str],
        "allowed_oauth_flows": list[str],
        "allowed_oauth_scopes": list[str],
        "enabled": bool
    }],
    "count": int
}
```

**Key Logic**:
- List all Cognito app clients (paginated)
- For each client, fetch detailed information
- Enrich with metadata from DynamoDB (created_by)
- Never return client secrets

#### 3. Delete OAuth Client (`delete_oauth_client.py`)

**Status**: Already implemented

**Purpose**: Delete an OAuth client from Cognito and DynamoDB

**Input**: `clientId` (path parameter)

**Output**:
```python
{
    "message": str,
    "client_id": str
}
```

**Key Logic**:
- Verify client has metadata in DynamoDB (only app-created clients can be deleted)
- Delete from Cognito (immediate revocation)
- Delete metadata from DynamoDB
- Handle case where client doesn't exist in Cognito but has metadata

**Error Handling**:
- 400: Missing client ID
- 403: Client not created through application (no metadata)
- 500: DynamoDB deletion failure

#### 4. Rotate Client Secret (`rotate_client_secret.py`)

**Status**: Not yet implemented

**Purpose**: Generate a new client secret by recreating the Cognito app client

**Input**: `clientId` (path parameter)

**Output**:
```python
{
    "client_id": str,         # New client ID
    "client_secret": str,     # New secret (only shown once)
    "rotated_at": str         # ISO8601 timestamp
}
```

**Key Logic**:
- Verify user owns the client (via DynamoDB metadata)
- Fetch current client configuration from Cognito
- Delete old Cognito app client
- Create new Cognito app client with same settings
- Update DynamoDB metadata with new client_id
- Return new client secret (only time it's accessible)

**Error Handling**:
- 400: Missing client ID
- 403: User doesn't own the client
- 404: Client not found
- 500: Cognito or DynamoDB errors

**Implementation Notes**:
- Cognito doesn't support in-place secret rotation
- Must delete and recreate the app client
- Old secret is immediately invalidated
- Client ID changes during rotation (update metadata)

### Utility Functions

#### `require_scopes(event, required_scopes)`

**Status**: Already implemented in `utils.py`

**Purpose**: Validate JWT token contains required scopes

**Logic**:
- Extract scopes from JWT token
- Check for `api/admin` scope (grants all access)
- Verify all required scopes are present
- Return user identity and error response

#### `extract_user_identity(event)`

**Status**: Already implemented in `utils.py`

**Purpose**: Extract user identity from API Gateway event

**Logic**:
- Handle both Cognito authorizer and Lambda authorizer formats
- Extract email, username, sub, client_id, scopes
- Determine identity type (user vs client)
- Return structured identity object

#### `get_valid_scopes_from_cognito(user_pool_id, resource_server_identifier)`

**Status**: Already implemented in `create_oauth_client.py`

**Purpose**: Fetch valid OAuth scopes from Cognito resource server

**Logic**:
- Call Cognito `describe_resource_server` API
- Extract scope definitions
- Format as `api/{scope_name}`
- Return list of valid scopes

## Data Models

### DynamoDB Schema

#### OAuth Client Metadata Record

```python
{
    "pk": "OAUTH_CLIENTS",           # Partition key (constant)
    "sk": str,                        # Sort key: client_id
    "client_id": str,                 # Cognito app client ID
    "client_name": str,               # User-provided name
    "created_by": str,                # User identity (email or sub)
    "created_at": str,                # ISO8601 timestamp
    "entity_type": "oauth_client"     # Entity type marker
}
```

**Access Patterns**:
- List all OAuth clients: Query by `pk = "OAUTH_CLIENTS"`
- Get specific client metadata: Get by `pk = "OAUTH_CLIENTS"` and `sk = client_id`
- Delete client metadata: Delete by `pk = "OAUTH_CLIENTS"` and `sk = client_id`

**Design Rationale**:
- Single partition key for all OAuth clients (simple querying)
- Client secrets NOT stored (security best practice)
- Minimal metadata (Cognito is source of truth for configuration)
- `created_by` enables ownership verification

### Cognito App Client Configuration

```python
{
    "ClientId": str,
    "ClientName": str,
    "ClientSecret": str,                    # Only accessible at creation
    "GenerateSecret": True,
    "AllowedOAuthFlows": ["client_credentials"],
    "AllowedOAuthScopes": list[str],        # e.g., ["api/execution.write"]
    "AllowedOAuthFlowsUserPoolClient": True,
    "ExplicitAuthFlows": [
        "ALLOW_REFRESH_TOKEN_AUTH",
        "ALLOW_USER_PASSWORD_AUTH",
        "ALLOW_USER_SRP_AUTH"
    ],
    "RefreshTokenValidity": 30,             # Days
    "AccessTokenValidity": 60,              # Minutes
    "IdTokenValidity": 60,                  # Minutes
    "TokenValidityUnits": {
        "AccessToken": "minutes",
        "IdToken": "minutes",
        "RefreshToken": "days"
    },
    "EnableTokenRevocation": True,
    "PreventUserExistenceErrors": "ENABLED"
}
```

### Cognito Resource Server

```python
{
    "Identifier": "api",
    "Scopes": [
        {
            "ScopeName": "admin",
            "ScopeDescription": "Full access to all resources"
        },
        {
            "ScopeName": "execution.write",
            "ScopeDescription": "Create and update executions"
        },
        {
            "ScopeName": "execution.read",
            "ScopeDescription": "Read execution data"
        },
        {
            "ScopeName": "usecases.write",
            "ScopeDescription": "Create and update usecases"
        },
        {
            "ScopeName": "usecases.read",
            "ScopeDescription": "Read usecase data"
        },
        {
            "ScopeName": "suite.write",
            "ScopeDescription": "Manage test suites"
        },
        {
            "ScopeName": "suite.read",
            "ScopeDescription": "Read test suite data"
        },
        {
            "ScopeName": "oauth-clients.write",
            "ScopeDescription": "Create and manage OAuth clients"
        },
        {
            "ScopeName": "oauth-clients.read",
            "ScopeDescription": "List OAuth clients"
        }
    ]
}
```

## API Endpoints

### 1. Create OAuth Client

**Endpoint**: `POST /api/oauth-clients`

**Required Scopes**: `api/oauth-clients.write` or `api/admin`

**Request**:
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

**Response (201)**:
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

### 2. List OAuth Clients

**Endpoint**: `GET /api/oauth-clients`

**Required Scopes**: `api/oauth-clients.read` or `api/admin`

**Response (200)**:
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
      "enabled": true
    }
  ],
  "count": 1
}
```

### 3. Delete OAuth Client

**Endpoint**: `DELETE /api/oauth-clients/{clientId}`

**Required Scopes**: `api/oauth-clients.write` or `api/admin`

**Response (200)**:
```json
{
  "message": "OAuth client deleted successfully",
  "client_id": "7abc123def456"
}
```

### 4. Rotate Client Secret

**Endpoint**: `POST /api/oauth-clients/{clientId}/rotate-secret`

**Required Scopes**: `api/oauth-clients.write` or `api/admin`

**Response (200)**:
```json
{
  "client_id": "8def456ghi789",
  "client_secret": "new_secret_abc123...",
  "rotated_at": "2026-02-16T15:00:00Z"
}
```

## Security Considerations

### Privilege Escalation Prevention

The system prevents privilege escalation through scope validation:

```python
# User can only grant scopes they possess (unless admin)
if not has_admin:
    unauthorized_scopes = [s for s in requested_scopes if s not in creator_scopes]
    if unauthorized_scopes:
        return error_response(403, "Cannot grant scopes you do not possess")
```

**Example**:
- User has scopes: `["api/suite.read", "api/execution.write"]`
- User requests: `["api/suite.read", "api/admin"]`
- Result: 403 Forbidden (cannot grant `api/admin`)

### Client Secret Handling

- Client secrets are NEVER stored in DynamoDB
- Client secrets are ONLY returned at creation and rotation
- Client secrets are stored securely in Cognito
- Old secrets are immediately invalidated on rotation

### Ownership Verification

- Only clients with DynamoDB metadata can be deleted/rotated
- Metadata includes `created_by` field for ownership verification
- System-created clients (without metadata) cannot be deleted via API

### Scope Inheritance

- `api/admin` scope grants access to all endpoints
- Implemented in `require_scopes()` utility function
- Simplifies permission management

## Error Handling

### Error Response Format

```python
{
    "error": str,              # Short error message
    "message": str,            # Detailed description
    "required_scopes": list,   # For 403 errors
    "token_scopes": list,      # For 403 errors
    "valid_scopes": list       # For invalid scope errors
}
```

### Error Scenarios

| Scenario | Status | Error Message |
|----------|--------|---------------|
| Missing client name | 400 | "Client name is required" |
| Invalid scopes | 400 | "Invalid scopes: {scopes}" |
| Privilege escalation | 403 | "Cannot grant scopes you do not possess" |
| Insufficient permissions | 403 | "Missing required scopes: {scopes}" |
| Client not found | 404 | "OAuth client not found" |
| Too many clients | 429 | "Too many OAuth clients. Please delete unused clients." |
| Cognito error | 500 | "Internal server error" |
| DynamoDB error | 500 | "Failed to create OAuth client metadata" |

### Rollback Strategy

**Create OAuth Client**:
- If DynamoDB write fails after Cognito creation
- Delete the Cognito app client
- Return 500 error
- Prevents orphaned Cognito clients

**Delete OAuth Client**:
- Delete from Cognito first (immediate revocation)
- Then delete from DynamoDB
- If DynamoDB deletion fails, log error but return success
- Client is already revoked (primary goal achieved)

**Rotate Client Secret**:
- Fetch current configuration
- Delete old client
- Create new client
- If creation fails, old client is already deleted (acceptable)
- Update DynamoDB metadata
- If metadata update fails, log error but return success
- New client is functional (primary goal achieved)


## Correctness Properties

A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

### Property 1: Scope Validation Prevents Privilege Escalation

*For any* user with a set of scopes S and any requested set of scopes R, creating an OAuth client with scopes R should succeed if and only if R ⊆ S or the user has the `api/admin` scope.

**Validates: Requirements US1.3**

**Rationale**: This is a critical security property that prevents users from granting permissions they don't possess. It ensures that OAuth clients cannot be used to escalate privileges beyond what the creating user has access to.

**Test Strategy**: Generate random user scope sets and requested scope sets, verify that creation succeeds only when all requested scopes are present in user scopes (or user has admin).

### Property 2: Client Credentials Generation

*For any* successful OAuth client creation, the response must contain both a non-empty `client_id` and a non-empty `client_secret`.

**Validates: Requirements US1.4**

**Rationale**: OAuth client credentials flow requires both client_id and client_secret for authentication. Missing either credential would make the client unusable.

**Test Strategy**: Create random OAuth clients with various configurations, verify both fields are present and non-empty in all responses.

### Property 3: Secret Confidentiality

*For any* OAuth client, after creation or rotation, calling the list endpoint should never return the `client_secret` field in the response.

**Validates: Requirements US1.5, US2.3, US4.3**

**Rationale**: Client secrets are sensitive credentials that should only be shown once at creation/rotation. Exposing secrets in list operations would create a security vulnerability.

**Test Strategy**: Create random OAuth clients, call list endpoint, verify `client_secret` field is absent from all client objects in the response.

### Property 4: Cognito Registration

*For any* successfully created OAuth client with `client_id` C, querying Cognito for client C should return the client configuration.

**Validates: Requirements US1.6**

**Rationale**: OAuth clients must be registered in Cognito to enable authentication. A client that exists in DynamoDB but not in Cognito would be non-functional.

**Test Strategy**: Create random OAuth clients, query Cognito directly for each client_id, verify client exists with correct configuration.

### Property 5: List Response Completeness

*For any* OAuth client in the system, the list endpoint response should include `client_id`, `client_name`, `created_date`, and `allowed_oauth_scopes` fields for that client.

**Validates: Requirements US2.2**

**Rationale**: The list endpoint must provide sufficient information for users to identify and manage their OAuth clients. Missing fields would impair usability.

**Test Strategy**: Create random OAuth clients with various configurations, call list endpoint, verify all required fields are present for each client.

### Property 6: Ownership Verification

*For any* OAuth client created by user A, user A should be able to delete the client, and any user B (where B ≠ A and B does not have admin scope) should receive a 403 error when attempting to delete the client.

**Validates: Requirements US3.1**

**Rationale**: Users should only be able to delete OAuth clients they created. Allowing deletion of other users' clients would be a security vulnerability.

**Test Strategy**: Create random OAuth clients with different user identities, attempt deletion with both the owner and non-owner users, verify owner succeeds and non-owner fails with 403.

### Property 7: Immediate Revocation

*For any* deleted OAuth client with credentials (client_id, client_secret), attempting to authenticate with those credentials should fail immediately after deletion.

**Validates: Requirements US3.3, US3.4**

**Rationale**: Deleted OAuth clients must be immediately revoked to prevent unauthorized access. Any delay in revocation creates a security window.

**Test Strategy**: Create random OAuth clients, authenticate successfully, delete the client, attempt authentication again, verify it fails immediately.

### Property 8: Secret Rotation

*For any* OAuth client, calling the rotate secret endpoint should return a new `client_secret` that differs from the original secret.

**Validates: Requirements US4.1**

**Rationale**: Secret rotation must generate a new secret to be effective. Returning the same secret would defeat the purpose of rotation.

**Test Strategy**: Create random OAuth clients, store original secret, call rotate endpoint, verify new secret is different from original.

### Property 9: Old Secret Invalidation

*For any* rotated OAuth client, attempting to authenticate with the old `client_secret` should fail immediately after rotation, while authentication with the new `client_secret` should succeed.

**Validates: Requirements US4.2**

**Rationale**: Secret rotation must immediately invalidate old credentials to prevent unauthorized access. If old secrets remain valid, rotation provides no security benefit.

**Test Strategy**: Create random OAuth clients, authenticate with original secret, rotate secret, verify old secret fails and new secret succeeds.

### Property 10: Audit Logging

*For any* OAuth client secret rotation, there should be a corresponding log entry containing the `client_id`, rotation timestamp, and user identity.

**Validates: Requirements US4.4**

**Rationale**: Audit logs are essential for security monitoring and compliance. Missing rotation events would create blind spots in security auditing.

**Test Strategy**: Create random OAuth clients, rotate secrets, query CloudWatch logs, verify log entries exist with required fields for each rotation.

### Property 11: Rollback Consistency

*For any* OAuth client creation where DynamoDB write fails after Cognito creation, the Cognito client should be deleted (rollback), and no orphaned clients should exist in Cognito without corresponding DynamoDB metadata.

**Validates: Requirements (Error Handling - Rollback Strategy)**

**Rationale**: Failed operations should not leave the system in an inconsistent state. Orphaned Cognito clients without metadata would be unmanageable through the API.

**Test Strategy**: Simulate DynamoDB write failures during client creation, verify Cognito client is deleted, query both Cognito and DynamoDB to confirm no orphaned clients exist.

## Testing Strategy

### Dual Testing Approach

This feature requires both unit tests and property-based tests for comprehensive coverage:

**Unit Tests** (70% coverage target):
- Specific examples of OAuth client creation with known scopes
- Edge cases: empty client name, invalid scopes, missing required fields
- Error conditions: Cognito failures, DynamoDB failures, network errors
- Integration points: Cognito API calls, DynamoDB operations
- Rollback scenarios: DynamoDB write failure after Cognito creation

**Property-Based Tests** (100+ iterations per property):
- Property 1: Scope validation with random user and requested scopes
- Property 2: Client credentials generation with random client configurations
- Property 3: Secret confidentiality with random clients
- Property 4: Cognito registration verification with random clients
- Property 5: List response completeness with random clients
- Property 6: Ownership verification with random users and clients
- Property 7: Immediate revocation with random clients
- Property 8: Secret rotation with random clients
- Property 9: Old secret invalidation with random clients
- Property 10: Audit logging with random rotation events
- Property 11: Rollback consistency with simulated failures

### Property Test Configuration

- **Library**: Use `hypothesis` for Python property-based testing
- **Iterations**: Minimum 100 iterations per property test
- **Tagging**: Each test must reference its design property
  - Format: `# Feature: wp1d-oauth-client-management, Property N: {property_text}`
- **Generators**: Create custom generators for:
  - User identities with random scope sets
  - OAuth client names (valid and invalid)
  - Scope lists (valid, invalid, mixed)
  - Client configurations

### Test Data Generators

```python
# Example generator for user scopes
@given(
    user_scopes=st.lists(
        st.sampled_from([
            "api/suite.read",
            "api/suite.write",
            "api/execution.read",
            "api/execution.write",
            "api/oauth-clients.read",
            "api/oauth-clients.write",
            "api/admin"
        ]),
        min_size=1,
        max_size=7,
        unique=True
    ),
    requested_scopes=st.lists(
        st.sampled_from([
            "api/suite.read",
            "api/suite.write",
            "api/execution.read",
            "api/execution.write",
            "api/oauth-clients.read",
            "api/oauth-clients.write",
            "api/admin"
        ]),
        min_size=1,
        max_size=5,
        unique=True
    )
)
def test_property_1_scope_validation(user_scopes, requested_scopes):
    # Feature: wp1d-oauth-client-management, Property 1: Scope Validation Prevents Privilege Escalation
    # Test implementation here
    pass
```

### Integration Testing

**End-to-End Workflow Tests**:
1. Create OAuth client via API
2. Authenticate with client credentials (Cognito OAuth flow)
3. Call protected endpoint with OAuth token
4. Verify access granted with correct scopes
5. Delete OAuth client
6. Verify authentication fails
7. Verify client removed from both Cognito and DynamoDB

**CI/CD Integration Test**:
1. Create OAuth client with CI/CD scopes
2. Use client credentials in simulated CI/CD runner
3. Execute test suite via API
4. Upload artifacts via presigned URLs
5. Verify execution records created correctly
6. Rotate client secret
7. Verify old credentials fail, new credentials work

### Security Testing

**Privilege Escalation Tests**:
- User with `api/suite.read` attempts to create client with `api/admin`
- User with no scopes attempts to create client
- User attempts to grant scopes they don't have

**Ownership Tests**:
- User A creates client, User B attempts to delete
- User A creates client, User B attempts to rotate secret
- Admin user can delete any client

**Secret Exposure Tests**:
- Verify secrets never in list responses
- Verify secrets never in DynamoDB
- Verify secrets only in Cognito (encrypted)
- Verify secrets only returned at creation/rotation

### Performance Testing

**Load Tests**:
- Create 100 OAuth clients concurrently
- List OAuth clients with 1000+ clients in pool
- Delete 50 OAuth clients concurrently
- Rotate secrets for 50 clients concurrently

**Latency Tests**:
- Measure p50, p95, p99 latency for each endpoint
- Target: p95 < 500ms for all operations

## Implementation Notes

### Existing Implementation Status

The following endpoints are already implemented:
- `create_oauth_client.py` - Fully functional with scope validation
- `delete_oauth_client.py` - Fully functional with ownership verification
- `list_oauth_clients.py` - Fully functional with metadata enrichment

### New Implementation Required

Only the rotate secret endpoint needs to be implemented:
- `rotate_client_secret.py` - New Lambda function

### API Gateway Configuration

**Endpoints**:
- `POST /api/oauth-clients` - Create OAuth client (scope: `api/oauth-clients.write`)
- `GET /api/oauth-clients` - List OAuth clients (scope: `api/oauth-clients.read`)
- `DELETE /api/oauth-clients/{clientId}` - Delete OAuth client (scope: `api/oauth-clients.write`)
- `POST /api/oauth-clients/{clientId}/rotate-secret` - Rotate secret (scope: `api/oauth-clients.write`)

All endpoints must:
- Have Cognito authorizer attached
- Validate required scopes using `require_scopes()` utility
- Return 204 for DELETE operations (per API design rules)
- Use GET for read operations, POST/DELETE for write operations

### DynamoDB Access Patterns

**Query Operations** (preferred):
- List all OAuth clients: Query by `pk = "OAUTH_CLIENTS"`
- Get specific client metadata: Get by `pk = "OAUTH_CLIENTS"` and `sk = client_id`

**No Scan Operations Required**: All access patterns use query operations with known partition key.

**No GSI/LSI Required**: Single partition key design supports all access patterns efficiently.

### Frontend Integration

**OAuth Clients Page** (`/oauth-clients`):
- Reuse existing table patterns from other list pages
- Use Cloudscape Table component with pagination
- Add "Create OAuth Client" button (opens modal)
- Add delete action with confirmation modal
- Add rotate secret action with warning modal
- Display client secret in modal with copy button (creation/rotation only)
- Show warning: "This is the only time you'll see the secret"

**Create OAuth Client Modal**:
- Name field (required, text input)
- Description field (optional, textarea)
- Scopes field (multi-select, limited to user's scopes)
- Submit button creates client and shows secret
- Copy button for client_id and client_secret
- Download button for credentials JSON file

## Deployment Considerations

### CDK Changes Required

**New Lambda Function**:
- Add `rotate_client_secret` Lambda function to CDK stack
- Grant Cognito permissions: `cognito-idp:DescribeUserPoolClient`, `cognito-idp:DeleteUserPoolClient`, `cognito-idp:CreateUserPoolClient`
- Grant DynamoDB permissions: `dynamodb:GetItem`, `dynamodb:PutItem`
- Add environment variables: `USER_POOL_ID`, `TABLE_NAME`

**API Gateway Routes**:
- Add `POST /api/oauth-clients/{clientId}/rotate-secret` route
- Attach Cognito authorizer
- Configure CORS headers

**No Infrastructure Changes Required**:
- Existing Cognito User Pool supports OAuth clients
- Existing DynamoDB table supports OAuth client metadata
- Existing S3 bucket not needed for this feature

### Deployment Steps

1. Deploy Lambda function: `rotate_client_secret.py`
2. Update API Gateway with new route
3. Deploy frontend changes (OAuth clients page)
4. Update API documentation
5. Create OAuth scopes in Cognito resource server (if not exist):
   - `api/oauth-clients.read`
   - `api/oauth-clients.write`

### Monitoring and Observability

**CloudWatch Metrics**:
- OAuth client creation count
- OAuth client deletion count
- OAuth client rotation count
- Scope validation failures (privilege escalation attempts)
- Rollback operations (DynamoDB write failures)

**CloudWatch Logs**:
- All OAuth client operations (create, delete, rotate)
- Scope validation results
- Ownership verification results
- Cognito API errors
- DynamoDB errors

**Alarms**:
- High rate of scope validation failures (potential attack)
- High rate of rollback operations (system issue)
- High rate of Cognito API errors
- High rate of DynamoDB errors

## Success Criteria

- [ ] Users can create OAuth clients via UI with scope selection
- [ ] Scope validation prevents privilege escalation
- [ ] Client secrets shown only once at creation/rotation
- [ ] Users can list their OAuth clients with metadata
- [ ] Users can delete OAuth clients they created
- [ ] Deleted clients cannot authenticate immediately
- [ ] Users can rotate client secrets
- [ ] Old secrets invalidated immediately after rotation
- [ ] Rollback works correctly on DynamoDB failures
- [ ] Unit test coverage ≥ 70%
- [ ] All property tests pass with 100+ iterations
- [ ] Integration tests pass for complete workflows
- [ ] API documentation updated
- [ ] Frontend UI implemented and functional
