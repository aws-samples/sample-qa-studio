# Work Package 1d: OAuth Client Management

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP1d - OAuth Client Management
- **Estimated Duration**: 3 days
- **Dependencies**: None (can run in parallel with WP1a-c)
- **Status**: Not Started

---

## Overview

Implement OAuth client management functionality to allow users to create machine-to-machine (M2M) OAuth clients for CI/CD runner authentication. OAuth clients use client credentials flow and are scoped to specific API permissions.

---

## User Stories

### US1: As a user, I need to create OAuth clients for CI/CD authentication
**Acceptance Criteria**:
- UI provides form to create OAuth client
- User can specify client name and description
- User can select scopes (limited to scopes they have access to)
- System generates client_id and client_secret
- Client secret is shown once and cannot be retrieved again
- OAuth client is registered in Cognito

### US2: As a user, I need to view my OAuth clients
**Acceptance Criteria**:
- UI displays list of OAuth clients
- List shows: client name, client_id, created date, scopes
- Client secret is never displayed after creation
- User can filter/search OAuth clients

### US3: As a user, I need to delete OAuth clients
**Acceptance Criteria**:
- User can delete OAuth clients they created
- Deletion requires confirmation
- Deleted clients cannot authenticate
- Deletion is immediate (no grace period)

### US4: As a user, I need to rotate OAuth client secrets
**Acceptance Criteria**:
- User can regenerate client secret
- Old secret is immediately invalidated
- New secret is shown once
- Rotation is logged for audit

---

## Technical Requirements

### Data Model

**OAuth Client Record (DynamoDB)**:
```python
{
    "PK": "USER#{user_id}",
    "SK": "OAUTH_CLIENT#{client_id}",
    "client_id": "string",  # Cognito app client ID
    "client_name": "string",
    "description": "string",
    "scopes": ["api/suite.read", "api/suite.write", "api/execution.write"],
    "created_at": "ISO8601 timestamp",
    "created_by": "user_id",
    "last_used_at": "ISO8601 timestamp",  # Updated on each auth
    "status": "active" | "revoked"
}
```

### Cognito Configuration

**App Client Settings**:
- OAuth flow: Client credentials
- Allowed scopes: Custom scopes defined in resource server
- Token expiration: 1 hour (configurable)
- Refresh token: Not applicable for client credentials

**Resource Server**:
- Identifier: `api`
- Custom scopes:
  - `api/suite.read` - Read test suites
  - `api/suite.write` - Execute test suites
  - `api/usecase.read` - Read use cases
  - `api/usecase.write` - Create/update use cases
  - `api/execution.read` - Read execution records
  - `api/execution.write` - Update execution status, upload artifacts

### API Endpoints

#### Create OAuth Client

**Endpoint**: `POST /api/oauth-clients`

**Request Body**:
```json
{
  "name": "CI/CD Runner - Production",
  "description": "OAuth client for production CI/CD pipeline",
  "scopes": [
    "api/suite.read",
    "api/suite.write",
    "api/execution.write"
  ]
}
```

**Response**:
```json
{
  "client_id": "7abc123def456",
  "client_secret": "secret_xyz789...",  // Only shown once
  "name": "CI/CD Runner - Production",
  "description": "OAuth client for production CI/CD pipeline",
  "scopes": [
    "api/suite.read",
    "api/suite.write",
    "api/execution.write"
  ],
  "created_at": "2026-02-16T12:00:00Z",
  "token_endpoint": "https://{domain}.auth.{region}.amazoncognito.com/oauth2/token"
}
```

#### List OAuth Clients

**Endpoint**: `GET /api/oauth-clients`

**Response**:
```json
{
  "clients": [
    {
      "client_id": "7abc123def456",
      "name": "CI/CD Runner - Production",
      "description": "OAuth client for production CI/CD pipeline",
      "scopes": ["api/suite.read", "api/suite.write", "api/execution.write"],
      "created_at": "2026-02-16T12:00:00Z",
      "last_used_at": "2026-02-16T14:30:00Z",
      "status": "active"
    }
  ]
}
```

#### Delete OAuth Client

**Endpoint**: `DELETE /api/oauth-clients/{clientId}`

**Response**: `204 No Content`

#### Rotate Client Secret

**Endpoint**: `POST /api/oauth-clients/{clientId}/rotate-secret`

**Response**:
```json
{
  "client_id": "7abc123def456",
  "client_secret": "new_secret_abc123...",  // Only shown once
  "rotated_at": "2026-02-16T15:00:00Z"
}
```

---

## Implementation Details

### Lambda: `create_oauth_client`

```python
import boto3
import uuid
from datetime import datetime

def create_oauth_client(event, context):
    # 1. Parse request
    user_id = event['requestContext']['authorizer']['claims']['sub']
    user_scopes = get_user_scopes(user_id)
    body = json.loads(event['body'])
    
    name = body['name']
    description = body.get('description', '')
    requested_scopes = body['scopes']
    
    # 2. Validate scopes (user cannot grant more than they have)
    if not all(scope in user_scopes for scope in requested_scopes):
        return error_response(403, 'Cannot grant scopes you do not have')
    
    # 3. Create Cognito app client
    cognito_client = boto3.client('cognito-idp')
    
    response = cognito_client.create_user_pool_client(
        UserPoolId=USER_POOL_ID,
        ClientName=f"{name} ({user_id})",
        GenerateSecret=True,
        AllowedOAuthFlows=['client_credentials'],
        AllowedOAuthScopes=requested_scopes,
        AllowedOAuthFlowsUserPoolClient=True,
        ExplicitAuthFlows=[],  # No user auth flows
        TokenValidityUnits={
            'AccessToken': 'hours'
        },
        AccessTokenValidity=1  # 1 hour
    )
    
    client_id = response['UserPoolClient']['ClientId']
    client_secret = response['UserPoolClient']['ClientSecret']
    
    # 4. Store OAuth client record in DynamoDB
    oauth_client_record = {
        'PK': f"USER#{user_id}",
        'SK': f"OAUTH_CLIENT#{client_id}",
        'client_id': client_id,
        'client_name': name,
        'description': description,
        'scopes': requested_scopes,
        'created_at': datetime.utcnow().isoformat(),
        'created_by': user_id,
        'status': 'active'
    }
    save_oauth_client(oauth_client_record)
    
    # 5. Return response (client_secret only shown once)
    return success_response({
        'client_id': client_id,
        'client_secret': client_secret,  # ONLY TIME THIS IS RETURNED
        'name': name,
        'description': description,
        'scopes': requested_scopes,
        'created_at': oauth_client_record['created_at'],
        'token_endpoint': f"https://{COGNITO_DOMAIN}.auth.{REGION}.amazoncognito.com/oauth2/token"
    })
```

### Lambda: `list_oauth_clients`

```python
def list_oauth_clients(event, context):
    user_id = event['requestContext']['authorizer']['claims']['sub']
    
    # Query DynamoDB for user's OAuth clients
    clients = query_oauth_clients(user_id)
    
    # Never return client_secret
    return success_response({
        'clients': [
            {
                'client_id': c['client_id'],
                'name': c['client_name'],
                'description': c.get('description', ''),
                'scopes': c['scopes'],
                'created_at': c['created_at'],
                'last_used_at': c.get('last_used_at'),
                'status': c['status']
            }
            for c in clients
        ]
    })
```

### Lambda: `delete_oauth_client`

```python
def delete_oauth_client(event, context):
    user_id = event['requestContext']['authorizer']['claims']['sub']
    client_id = event['pathParameters']['clientId']
    
    # 1. Verify user owns this client
    oauth_client = get_oauth_client(user_id, client_id)
    if not oauth_client:
        return error_response(404, 'OAuth client not found')
    
    if oauth_client['created_by'] != user_id:
        return error_response(403, 'Cannot delete OAuth client you do not own')
    
    # 2. Delete from Cognito
    cognito_client = boto3.client('cognito-idp')
    cognito_client.delete_user_pool_client(
        UserPoolId=USER_POOL_ID,
        ClientId=client_id
    )
    
    # 3. Mark as revoked in DynamoDB (soft delete for audit)
    update_oauth_client_status(user_id, client_id, 'revoked')
    
    return success_response({}, status_code=204)
```

### Lambda: `rotate_client_secret`

```python
def rotate_client_secret(event, context):
    user_id = event['requestContext']['authorizer']['claims']['sub']
    client_id = event['pathParameters']['clientId']
    
    # 1. Verify user owns this client
    oauth_client = get_oauth_client(user_id, client_id)
    if not oauth_client or oauth_client['created_by'] != user_id:
        return error_response(403, 'Cannot rotate secret for client you do not own')
    
    # 2. Update Cognito app client (regenerate secret)
    cognito_client = boto3.client('cognito-idp')
    
    # Delete old client
    cognito_client.delete_user_pool_client(
        UserPoolId=USER_POOL_ID,
        ClientId=client_id
    )
    
    # Create new client with same settings but new secret
    response = cognito_client.create_user_pool_client(
        UserPoolId=USER_POOL_ID,
        ClientName=oauth_client['client_name'],
        GenerateSecret=True,
        AllowedOAuthFlows=['client_credentials'],
        AllowedOAuthScopes=oauth_client['scopes'],
        AllowedOAuthFlowsUserPoolClient=True,
        ExplicitAuthFlows=[],
        TokenValidityUnits={'AccessToken': 'hours'},
        AccessTokenValidity=1
    )
    
    new_client_id = response['UserPoolClient']['ClientId']
    new_client_secret = response['UserPoolClient']['ClientSecret']
    
    # 3. Update DynamoDB record
    update_oauth_client_id(user_id, client_id, new_client_id)
    
    return success_response({
        'client_id': new_client_id,
        'client_secret': new_client_secret,  # Only shown once
        'rotated_at': datetime.utcnow().isoformat()
    })
```

---

## Frontend Components

### OAuth Clients Page

**Location**: `/oauth-clients`

**Components**:
- Table displaying OAuth clients
- "Create OAuth Client" button
- Delete action for each client
- Rotate secret action for each client

### Create OAuth Client Modal

**Fields**:
- Name (required)
- Description (optional)
- Scopes (multi-select, limited to user's scopes)

**Behavior**:
- On submit, call `POST /api/oauth-clients`
- Display client_secret in modal with copy button
- Show warning: "This is the only time you'll see the secret"
- Provide download option for credentials

---

## Testing Requirements

### Unit Tests
- Test OAuth client creation
- Test scope validation (cannot grant more than user has)
- Test OAuth client listing
- Test OAuth client deletion
- Test client secret rotation
- Test Cognito integration

### Integration Tests
- Create OAuth client via API
- Authenticate with client credentials
- Call protected endpoint with OAuth token
- Delete OAuth client
- Verify deleted client cannot authenticate
- Rotate client secret
- Verify old secret no longer works

### Security Tests
- Test scope enforcement
- Test user cannot delete other user's clients
- Test client secret is never returned after creation
- Test token expiration (1 hour)

---

## Security Considerations

- Client secrets are never stored in DynamoDB (only in Cognito)
- Client secrets are only shown once at creation/rotation
- Users cannot grant scopes they don't have
- OAuth clients are tied to user accounts
- Deleted clients are immediately revoked
- All OAuth operations are logged for audit

---

## API Gateway Configuration

**Endpoints**:
- `POST /api/oauth-clients` - Create OAuth client (scope: `api/oauth.write`)
- `GET /api/oauth-clients` - List OAuth clients (scope: `api/oauth.read`)
- `DELETE /api/oauth-clients/{clientId}` - Delete OAuth client (scope: `api/oauth.write`)
- `POST /api/oauth-clients/{clientId}/rotate-secret` - Rotate secret (scope: `api/oauth.write`)

---

## Success Criteria

- [ ] Users can create OAuth clients via UI
- [ ] OAuth clients registered in Cognito
- [ ] Client credentials flow working
- [ ] Scope validation enforced
- [ ] Client secrets shown only once
- [ ] Users can list their OAuth clients
- [ ] Users can delete OAuth clients
- [ ] Users can rotate client secrets
- [ ] Unit test coverage ≥ 70%
- [ ] Integration tests pass
- [ ] API documentation updated
