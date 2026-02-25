# Requirements Document: Scope-Based Access Control

## Introduction

This feature implements OAuth 2.0 scope-based authorization for the application using AWS Cognito. The system will define granular resource server scopes, map Cognito groups to scope sets, inject scopes into JWT tokens, and validate scopes at all API endpoints. This enables fine-grained access control for both user tokens and machine-to-machine (M2M) OAuth clients.

## Glossary

- **Resource_Server**: AWS Cognito resource server that defines available OAuth scopes
- **Scope**: An OAuth 2.0 permission that grants access to specific API operations (format: `api/resource.action`)
- **User_Group**: AWS Cognito group that maps users to a set of scopes
- **Pre_Token_Generation_Lambda**: AWS Lambda function triggered by Cognito to inject scopes into JWT tokens
- **M2M_Token**: Machine-to-machine OAuth token obtained via client credentials flow
- **User_Token**: JWT token obtained by user authentication (username/password or SRP)
- **OAuth_Client**: Cognito user pool client configured for client credentials flow
- **Scope_Inheritance**: Authorization rule where `api/admin` scope grants access to all other scopes
- **Endpoint**: Lambda function that handles API Gateway requests

## Requirements

### Requirement 1: Define Resource Server Scopes

**User Story:** As a system architect, I want to define granular OAuth scopes in Cognito, so that I can control access to different API operations.

#### Acceptance Criteria

1. THE Resource_Server SHALL define scope `api/usecases.read` for listing and viewing use cases
2. THE Resource_Server SHALL define scope `api/usecases.write` for creating, updating, and deleting use cases
3. THE Resource_Server SHALL define scope `api/executions.read` for viewing execution results and history
4. THE Resource_Server SHALL define scope `api/executions.write` for modifying execution records
5. THE Resource_Server SHALL define scope `api/usecases.execute` for triggering use case executions
6. THE Resource_Server SHALL define scope `api/oauth-clients.manage` for creating and deleting OAuth clients
7. THE Resource_Server SHALL define scope `api/admin` for full administrative access with inheritance

### Requirement 2: Create Cognito User Groups

**User Story:** As a system administrator, I want to organize users into groups with different permission levels, so that I can manage access control efficiently.

#### Acceptance Criteria

1. THE System SHALL create a `users` group for default user permissions
2. THE System SHALL create an `admins` group for administrative permissions
3. WHEN the stack is deployed, THE System SHALL assign the admin user to the `admins` group

### Requirement 3: Inject Scopes into JWT Tokens

**User Story:** As a developer, I want user group memberships to automatically translate into JWT token scopes, so that authorization decisions can be made from the token alone.

#### Acceptance Criteria

1. WHEN a user in the `users` group authenticates, THE Pre_Token_Generation_Lambda SHALL inject scopes: `api/usecases.read`, `api/usecases.write`, `api/executions.read`, `api/executions.write`, `api/usecases.execute`
2. WHEN a user in the `admins` group authenticates, THE Pre_Token_Generation_Lambda SHALL inject all scopes including `api/oauth-clients.manage` and `api/admin`
3. WHEN a user belongs to multiple groups, THE Pre_Token_Generation_Lambda SHALL inject the union of all scopes from those groups
4. THE Pre_Token_Generation_Lambda SHALL add scopes to the access token's scope claim

### Requirement 4: Configure User Pool Client with Scopes

**User Story:** As a system architect, I want the user pool client to support all defined scopes, so that users can receive appropriate scopes in their tokens.

#### Acceptance Criteria

1. THE User_Pool_Client SHALL include all resource server scopes in its allowed OAuth scopes
2. THE User_Pool_Client SHALL support scope injection for both OAuth and non-OAuth authentication flows

### Requirement 5: Create OAuth Clients with Scope Selection

**User Story:** As an administrator, I want to create OAuth clients with specific scopes, so that M2M integrations have only the permissions they need.

#### Acceptance Criteria

1. WHEN creating an OAuth client, THE System SHALL accept a `scopes` parameter containing an array of scope names
2. WHEN the `scopes` parameter is provided, THE System SHALL validate that all requested scopes exist in the resource server
3. WHEN the `scopes` parameter is omitted, THE System SHALL assign a default minimal scope set
4. WHEN creating an OAuth client, THE System SHALL configure the client with the specified scopes in `AllowedOAuthScopes`
5. WHEN an invalid scope is requested, THE System SHALL return an error and prevent client creation

### Requirement 6: Validate Scopes at API Endpoints

**User Story:** As a security engineer, I want all API endpoints to validate required scopes, so that unauthorized access is prevented.

#### Acceptance Criteria

1. WHEN an endpoint receives a request, THE System SHALL extract scopes from the JWT token
2. WHEN the token contains the `api/admin` scope, THE System SHALL grant access to all endpoints regardless of other scopes (inheritance)
3. WHEN the token lacks required scopes and lacks `api/admin`, THE System SHALL return a 403 Forbidden error
4. WHEN scope validation occurs, THE System SHALL log the endpoint, user/client identity, scopes present, and scopes required to CloudWatch
5. THE System SHALL validate scopes before executing any business logic

### Requirement 7: Protect Use Case Endpoints

**User Story:** As a product owner, I want use case management operations to require appropriate scopes, so that only authorized users can modify use cases.

#### Acceptance Criteria

1. WHEN listing or viewing use cases, THE Endpoint SHALL require scope `api/usecases.read` or `api/admin`
2. WHEN creating, updating, or deleting use cases, THE Endpoint SHALL require scope `api/usecases.write` or `api/admin`

### Requirement 8: Protect Execution Endpoints

**User Story:** As a product owner, I want execution operations to require appropriate scopes, so that execution data is protected.

#### Acceptance Criteria

1. WHEN viewing execution results or history, THE Endpoint SHALL require scope `api/executions.read` or `api/admin`
2. WHEN modifying execution records, THE Endpoint SHALL require scope `api/executions.write` or `api/admin`
3. WHEN triggering a use case execution, THE Endpoint SHALL require scope `api/usecases.execute` or `api/admin`

### Requirement 9: Protect OAuth Client Management Endpoints

**User Story:** As a security engineer, I want OAuth client management to be restricted to administrators, so that only trusted users can create M2M credentials.

#### Acceptance Criteria

1. WHEN creating an OAuth client, THE Endpoint SHALL require scope `api/oauth-clients.manage` or `api/admin`
2. WHEN listing OAuth clients, THE Endpoint SHALL require scope `api/oauth-clients.manage` or `api/admin`
3. WHEN deleting an OAuth client, THE Endpoint SHALL require scope `api/oauth-clients.manage` or `api/admin`

### Requirement 10: Display OAuth Client Scopes in UI

**User Story:** As an administrator, I want to see which scopes are assigned to each OAuth client, so that I can audit permissions.

#### Acceptance Criteria

1. WHEN viewing the OAuth clients list, THE UI SHALL display the scopes for each client
2. WHEN creating an OAuth client, THE UI SHALL provide a scope selection interface with checkboxes or multi-select
3. WHEN displaying scopes, THE UI SHALL show scope descriptions to help users understand permissions
4. THE UI SHALL validate that at least one scope is selected before allowing client creation

### Requirement 11: Manage User Groups via UI

**User Story:** As an administrator, I want to manage user group memberships through the UI, so that I can control user permissions without using the AWS console.

#### Acceptance Criteria

1. WHEN an admin views the users section, THE UI SHALL display all Cognito users with their group memberships
2. WHEN an admin selects a user, THE UI SHALL provide a group management interface
3. WHEN an admin modifies user groups, THE System SHALL update the user's Cognito group membership
4. WHEN displaying group options, THE UI SHALL show a preview of scopes granted by each group

### Requirement 12: Control UI Navigation Based on Scopes

**User Story:** As a user, I want to see only the UI sections I have permission to access, so that the interface is clear and relevant.

#### Acceptance Criteria

1. WHEN a user lacks scope `api/oauth-clients.manage` and `api/admin`, THE UI SHALL hide the OAuth Clients navigation section
2. WHEN a user lacks scope `api/admin`, THE UI SHALL hide the Users management navigation section
3. WHEN determining UI visibility, THE System SHALL extract scopes from the JWT token stored in the application state

### Requirement 13: Reorganize Lambda Directory Structure

**User Story:** As a developer, I want Lambda functions organized by purpose, so that the codebase is maintainable and scalable.

#### Acceptance Criteria

1. THE System SHALL organize Lambda functions into three directories: `lambdas/endpoints/`, `lambdas/auth/`, and `lambdas/events/`
2. WHEN deploying Lambda functions, THE System SHALL reference the correct paths in CDK stack definitions
3. THE System SHALL move the authorizer to `lambdas/auth/authorizer.py`
4. THE System SHALL move the event handler to `lambdas/events/handle_task_state_change.py`
5. THE System SHALL keep all API Gateway handlers in `lambdas/endpoints/`

### Requirement 14: Provide Backend Endpoints for User Management

**User Story:** As a frontend developer, I want backend APIs for user management, so that I can build the user management UI.

#### Acceptance Criteria

1. THE System SHALL provide a `GET /users` endpoint that lists all users with their groups
2. THE System SHALL provide a `PUT /users/{userId}/groups` endpoint that updates user group membership
3. THE System SHALL provide a `GET /users/{userId}` endpoint that retrieves user details
4. WHEN accessing user management endpoints, THE System SHALL require scope `api/admin`
