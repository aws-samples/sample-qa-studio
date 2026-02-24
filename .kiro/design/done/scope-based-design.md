# Implementation Plan: Scope-Based Access Control

## 0. Reorganize Lambda Directory Structure

**Create new directory structure:**
```
lambdas/
  ├── endpoints/           # API Gateway handlers
  │   ├── (all current endpoint files)
  │   ├── utils.py
  │   ├── requirements.txt
  │   └── dependencies/
  │
  ├── auth/               # Cognito triggers & authorizers
  │   ├── authorizer.py (move from endpoints/)
  │   └── pre_token_generation.py (new)
  │
  └── events/             # EventBridge/async handlers
      └── handle_task_state_change.py (move from endpoints/)
```

**Update lambda-stack.ts:**
- Update all lambda code paths from `endpoints/` to `lambdas/endpoints/`
- Update authorizer path to `lambdas/auth/authorizer.py`
- Update event handler path to `lambdas/events/handle_task_state_change.py`

## 1. Define Resource Server Scopes

**Update auth-stack.ts:**
- Modify existing resource server to include all scopes:
  - `api/usecases.read`
  - `api/usecases.write`
  - `api/executions.read`
  - `api/executions.write`
  - `api/usecases.execute`
  - `api/oauth-clients.manage`
  - `api/admin`

## 2. Create Cognito Groups

**Add to auth-stack.ts:**
- Create `users` group (default user permissions)
- Create `admins` group (admin permissions)
- Attach admin user to `admins` group on stack creation

## 3. Create Pre Token Generation Lambda

**New lambda function:**
- File: `lambdas/auth/pre_token_generation.py`
- Logic: Map Cognito groups to scopes
  - `users` group → usecases + executions scopes (read, write, execute)
  - `admins` group → all scopes including oauth-clients.manage + admin
- Add scope claim to access token

**Update lambda-stack.ts:**
- Create lambda function
- Grant Cognito invoke permissions
- Wire to user pool as trigger

## 4. Update User Pool Client Configuration

**Modify auth-stack.ts:**
- Add resource server scopes to user pool client's allowed OAuth scopes
- Ensure scopes are available for both OAuth and non-OAuth flows

## 5. Update OAuth Client Creation

**Modify create_oauth_client.py:**
- Accept `scopes` parameter in request body (array of scope names)
- Validate requested scopes against allowed list
- Create Cognito client with specified scopes in `AllowedOAuthScopes`
- Require `api/oauth-clients.manage` scope (admins only)

**Modify create_oauth_client API:**
- Update request validation to accept scopes array
- Default to minimal scopes if not specified

## 6. Add Scope Validation to Lambda Functions

**Create utility function:**
- File: `lambdas/endpoints/utils.py`
- Function: `require_scopes(event, required_scopes)` 
- Extract scopes from token claims
- **Implement inheritance: if `api/admin` present, grant all access**
- Validate required scopes are present (or admin scope)
- Return error if insufficient permissions
- **Log scope usage:** endpoint, user/client ID, scopes present, scopes required

**Update existing lambdas:**
- Use case endpoints: Require `api/usecases.read` or `api/usecases.write`
- Execution endpoints: Require `api/executions.read` or `api/executions.write`
- Execute use case endpoint: Require `api/usecases.execute`
- OAuth client endpoints: Require `api/oauth-clients.manage`
- Add scope validation logging to all endpoints

## 7. Update List/Delete OAuth Client Endpoints

**Modify list_oauth_clients.py:**
- Add scope check for `api/oauth-clients.manage`
- Log scope usage

**Modify delete_oauth_client.py:**
- Add scope check for `api/oauth-clients.manage`
- Log scope usage

## 8. Testing & Validation

**Test scenarios:**
- User token with default scopes can access usecases/executions
- User token without admin scope cannot manage OAuth clients
- Admin token can manage OAuth clients (via `api/admin` inheritance)
- Admin token can access all endpoints (inheritance)
- M2M token with limited scopes is restricted appropriately
- M2M token with no scope gets rejected
- Invalid scope requests are rejected during OAuth client creation
- Scope usage is logged in CloudWatch

## 9. Update Frontend UI

### OAuth Client Management UI

**Modify OAuth client creation form:**
- Add scope selection component (multi-select checkboxes or dropdown)
- Display available scopes with descriptions:
  - `api/usecases.read` - Read use cases
  - `api/usecases.write` - Create/update/delete use cases
  - `api/executions.read` - View execution results
  - `api/executions.write` - Modify execution records
  - `api/usecases.execute` - Trigger executions
  - `api/oauth-clients.manage` - Manage OAuth clients (admin only)
  - `api/admin` - Full admin access
- Validate at least one scope is selected
- Show scope inheritance note (admin scope grants all)

**Modify OAuth client list view:**
- Display scopes for each client (fetch from Cognito via API)
- Show scope badges/tags for visual clarity

### User Management UI

**Create new user management section:**
- Add "Users" navigation item (visible only to admins)
- List all Cognito users with their groups
- Show user details: email, groups, created date
- Add "Manage Groups" action per user

**User group management modal:**
- Checkbox for `users` group (default permissions)
- Checkbox for `admins` group (admin permissions)
- Show scope preview based on selected groups
- Save changes via API

**Create backend endpoints:**
- `GET /users` - List all users with their groups (requires `api/admin`)
- `PUT /users/{userId}/groups` - Update user group membership (requires `api/admin`)
- `GET /users/{userId}` - Get user details (requires `api/admin`)

### Navigation & Access Control

**Update navigation component:**
- Check user's scopes from token claims
- Hide "OAuth Clients" section if user lacks `api/oauth-clients.manage` or `api/admin`
- Hide "Users" section if user lacks `api/admin`
- Show/hide based on scope presence, not just group membership

**Frontend scope validation:**
- Extract scopes from JWT token on login
- Store in application state/context
- Use for conditional rendering throughout UI
- Re-validate on token refresh

## 10. Documentation

**Update:**
- API documentation with scope requirements per endpoint
- OAuth client creation examples with scope selection
- User group management guide
- Scope inheritance behavior (`api/admin` grants all access)
- Frontend UI guide for admin features

---

## Scope Design

### Read Scopes
- `api/usecases.read` - List and view use cases
- `api/executions.read` - View execution results and history

### Write Scopes
- `api/usecases.write` - Create, update, delete use cases
- `api/executions.write` - Modify execution records
- `api/usecases.execute` - Trigger use case executions

### Admin Scopes
- `api/oauth-clients.manage` - Create and delete OAuth clients
- `api/admin` - Full administrative access (grants all scopes via inheritance)

### Client Type Mapping

**User tokens:**
- Default: `api/usecases.read`, `api/usecases.write`, `api/executions.read`, `api/executions.write`, `api/usecases.execute`
- Admin users: Add `api/oauth-clients.manage`, `api/admin`

**M2M tokens:**
- CI/CD pipeline: `api/usecases.execute`, `api/executions.read`
- Monitoring: `api/executions.read`, `api/usecases.read`
- Admin automation: All scopes

---

## Decisions

1. ✓ OAuth client creation requires `api/oauth-clients.manage` (admins only)
2. ✓ Use scope inheritance (`api/admin` grants all scopes)
3. ✓ Log scope usage in CloudWatch via lambda loggers
4. ✓ No scope updates, delete and recreate instead
5. ✓ No maximum scopes per client
6. ✓ Scopes managed via CDK only
7. ✓ Scopes stored in Cognito only (not duplicated in DynamoDB)
8. ✓ Reorganize lambda directory structure (endpoints/, auth/, events/)
