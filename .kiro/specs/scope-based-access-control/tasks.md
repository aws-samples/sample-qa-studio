# Implementation Plan: Scope-Based Access Control

## Overview

This implementation plan breaks down the scope-based access control feature into incremental, testable steps. Each task builds on previous work and includes validation through code execution. The plan follows the phased approach from the design document, starting with directory reorganization, then infrastructure, authorization logic, endpoint protection, and finally UI enhancements.

## Tasks

- [x] 1. Reorganize Lambda directory structure
  - Create new directory structure: `lambdas/endpoints/`, `lambdas/auth/`, `lambdas/events/`
  - Move `endpoints/authorizer.py` to `lambdas/auth/authorizer.py`
  - Move `endpoints/handle_task_state_change.py` to `lambdas/events/handle_task_state_change.py`
  - Move all other endpoint files to `lambdas/endpoints/`
  - Update `lib/lambda-stack.ts` to reference new paths
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

- [ ] 2. Define resource server scopes in Cognito
  - [x] 2.1 Update `lib/auth-stack.ts` to define all seven scopes in resource server
    - Add scopes: `usecases.read`, `usecases.write`, `executions.read`, `executions.write`, `usecases.execute`, `oauth-clients.manage`, `admin`
    - Include scope descriptions for each
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_
  
  - [x] 2.2 Write unit test to verify all scopes are defined
    - Query Cognito resource server after deployment
    - Assert all 7 scopes exist with correct names and descriptions
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [ ] 3. Create Cognito user groups
  - [x] 3.1 Add `users` and `admins` groups to `lib/auth-stack.ts`
    - Create `CfnUserPoolGroup` for `users` group
    - Create `CfnUserPoolGroup` for `admins` group
    - Add `CfnUserPoolUserToGroupAttachment` to assign admin user to `admins` group
    - _Requirements: 2.1, 2.2, 2.3_
  
  - [x] 3.2 Write unit test to verify groups are created
    - Query Cognito after deployment
    - Assert both groups exist
    - Assert admin user is in `admins` group
    - _Requirements: 2.1, 2.2, 2.3_

- [ ] 4. Implement pre-token generation Lambda
  - [x] 4.1 Create `lambdas/auth/pre_token_generation.py`
    - Extract user groups from event
    - Map `users` group to user scopes
    - Map `admins` group to all scopes including admin
    - Handle multiple groups by taking union of scopes
    - Inject scopes into token's `claimsToAddOrOverride`
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  
  - [x] 4.2 Write property test for users group scope injection
    - **Property 1: Users Group Scope Injection**
    - **Validates: Requirements 3.1**
  
  - [x] 4.3 Write property test for admins group scope injection
    - **Property 2: Admins Group Scope Injection**
    - **Validates: Requirements 3.2**
  
  - [x] 4.4 Write property test for multi-group scope union
    - **Property 3: Multi-Group Scope Union**
    - **Validates: Requirements 3.3**
  
  - [x] 4.5 Write property test for scope claim presence
    - **Property 4: Scope Claim Presence**
    - **Validates: Requirements 3.4**

- [ ] 5. Wire pre-token generation Lambda to Cognito
  - [x] 5.1 Add Lambda function to `lib/lambda-stack.ts`
    - Create Lambda function for pre-token generation
    - Grant Cognito invoke permissions
    - Export function ARN
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  
  - [x] 5.2 Update `lib/auth-stack.ts` to add Lambda trigger
    - Add `lambdaTriggers` to UserPool with `preTokenGeneration` trigger
    - Reference Lambda function ARN from lambda-stack
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 6. Update user pool client with resource server scopes
  - [x] 6.1 Modify `lib/auth-stack.ts` user pool client configuration
    - Add all resource server scopes to `oAuth.scopes` using `OAuthScope.resourceServer()`
    - Ensure scopes are available for both OAuth and non-OAuth flows
    - _Requirements: 4.1, 4.2_
  
  - [x] 6.2 Write unit test to verify user pool client scope configuration
    - Query user pool client configuration
    - Assert all resource server scopes are in `AllowedOAuthScopes`
    - _Requirements: 4.1_

- [ ] 7. Implement scope validation utility
  - [x] 7.1 Add `require_scopes()` function to `lambdas/endpoints/utils.py`
    - Extract scopes from token using `extract_user_identity()`
    - Check for `api/admin` scope (grants all access)
    - Validate required scopes are present
    - Log validation attempt with identity, scopes present, scopes required
    - Return 403 error if scopes insufficient
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  
  - [x] 7.2 Write property test for scope extraction
    - **Property 8: Scope Extraction from Token**
    - **Validates: Requirements 6.1**
  
  - [x] 7.3 Write property test for admin scope inheritance
    - **Property 9: Admin Scope Inheritance**
    - **Validates: Requirements 6.2**
  
  - [x] 7.4 Write property test for insufficient scope rejection
    - **Property 10: Insufficient Scope Rejection**
    - **Validates: Requirements 6.3**
  
  - [x] 7.5 Write property test for scope validation logging
    - **Property 11: Scope Validation Logging**
    - **Validates: Requirements 6.4**

- [x] 8. Checkpoint - Ensure scope validation utility works
  - Deploy changes and test scope validation utility
  - Verify logging appears in CloudWatch
  - Ask the user if questions arise

- [ ] 9. Update OAuth client creation endpoint with scope selection
  - [x] 9.1 Modify `lambdas/endpoints/create_oauth_client.py`
    - Add scope validation using `require_scopes(event, ['api/oauth-clients.manage'])`
    - Accept `scopes` parameter from request body
    - Validate requested scopes against valid scope list
    - Set default scopes if parameter omitted
    - Pass scopes to `AllowedOAuthScopes` in Cognito client creation
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 9.1_
  
  - [x] 9.2 Write property test for OAuth client scope acceptance
    - **Property 5: OAuth Client Scope Acceptance**
    - **Validates: Requirements 5.1**
  
  - [x] 9.3 Write property test for invalid scope rejection
    - **Property 6: Invalid Scope Rejection**
    - **Validates: Requirements 5.2, 5.5**
  
  - [x] 9.4 Write property test for OAuth client scope configuration
    - **Property 7: OAuth Client Scope Configuration**
    - **Validates: Requirements 5.4**
  
  - [x] 9.5 Write unit test for default scope assignment
    - Create OAuth client without scopes parameter
    - Verify default scope is assigned
    - _Requirements: 5.3_

- [ ] 10. Update list and delete OAuth client endpoints
  - [x] 10.1 Add scope validation to `lambdas/endpoints/list_oauth_clients.py`
    - Add `require_scopes(event, ['api/oauth-clients.manage'])` at start of handler
    - _Requirements: 9.2_
  
  - [x] 10.2 Add scope validation to `lambdas/endpoints/delete_oauth_client.py`
    - Add `require_scopes(event, ['api/oauth-clients.manage'])` at start of handler
    - _Requirements: 9.3_

- [ ] 11. Update use case endpoints with scope validation
  - [x] 11.1 Add scope validation to list/view use case endpoints
    - Update `list_usecases.py`, `get_usecase.py` with `require_scopes(event, ['api/usecases.read'])`
    - _Requirements: 7.1_
  
  - [x] 11.2 Add scope validation to create/update/delete use case endpoints
    - Update `create_usecase.py`, `update_usecase.py`, `delete_usecase.py` with `require_scopes(event, ['api/usecases.write'])`
    - _Requirements: 7.2_
  
  - [x] 11.3 Write property test for endpoint scope enforcement
    - **Property 12: Endpoint Scope Enforcement**
    - **Validates: Requirements 7.1, 7.2**

- [ ] 12. Update execution endpoints with scope validation
  - [x] 12.1 Add scope validation to view execution endpoints
    - Update `list_executions.py`, `get_execution.py`, `get_execution_step.py`, `list_execution_steps.py` with `require_scopes(event, ['api/executions.read'])`
    - _Requirements: 8.1_
  
  - [x] 12.2 Add scope validation to modify execution endpoints
    - Update any endpoints that modify execution records with `require_scopes(event, ['api/executions.write'])`
    - _Requirements: 8.2_
  
  - [x] 12.3 Add scope validation to execute use case endpoint
    - Update `execute_usecase.py` with `require_scopes(event, ['api/usecases.execute'])`
    - _Requirements: 8.3_

- [ ] 13. Checkpoint - Ensure all endpoints are protected
  - Test each endpoint with tokens containing different scopes
  - Verify 403 errors for insufficient scopes
  - Verify admin scope grants access to all endpoints
  - Ask the user if questions arise

- [ ] 14. Create user management backend endpoints
  - [x] 14.1 Create `lambdas/endpoints/list_users.py`
    - Implement handler with `require_scopes(event, ['api/admin'])`
    - List all Cognito users using `list_users()` API
    - For each user, get groups using `admin_list_groups_for_user()`
    - Return user list with email, groups, created date, enabled status
    - _Requirements: 14.1, 14.4_
  
  - [x] 14.2 Create `lambdas/endpoints/get_user.py`
    - Implement handler with `require_scopes(event, ['api/admin'])`
    - Get user details from Cognito using `admin_get_user()`
    - Get user groups using `admin_list_groups_for_user()`
    - Return user details with groups
    - _Requirements: 14.3, 14.4_
  
  - [x] 14.3 Create `lambdas/endpoints/update_user_groups.py`
    - Implement handler with `require_scopes(event, ['api/admin'])`
    - Accept `groups` array in request body
    - Validate groups against valid group list
    - Get current groups using `admin_list_groups_for_user()`
    - Remove user from old groups using `admin_remove_user_from_group()`
    - Add user to new groups using `admin_add_user_to_group()`
    - Return updated user with new groups
    - _Requirements: 14.2, 14.4_
  
  - [x] 14.4 Write property test for user group update synchronization
    - **Property 13: User Group Update Synchronization**
    - **Validates: Requirements 11.3**
  
  - [x] 14.5 Write property test for user management endpoint admin scope requirement
    - **Property 17: User Management Endpoint Admin Scope Requirement**
    - **Validates: Requirements 14.4**
  
  - [x] 14.6 Write unit tests for user management endpoints
    - Test list users returns correct data structure
    - Test get user returns user details
    - Test update groups with invalid group name returns error
    - Test update groups with non-existent user returns 404
    - _Requirements: 14.1, 14.2, 14.3_

- [ ] 15. Add user management endpoints to API Gateway
  - [x] 15.1 Update `lib/api-stack.ts` to add new routes
    - Add `GET /users` route pointing to `list_users` Lambda
    - Add `GET /users/{userId}` route pointing to `get_user` Lambda
    - Add `PUT /users/{userId}/groups` route pointing to `update_user_groups` Lambda
    - Configure authorizer for all routes
    - _Requirements: 14.1, 14.2, 14.3_

- [ ] 16. Update frontend OAuth client creation form
  - [x] 16.1 Modify `frontend/src/components/CreateOAuthClient.tsx`
    - Add scope selection UI with checkboxes for each scope
    - Display scope descriptions next to each checkbox
    - Add validation to require at least one scope
    - Add info box explaining scope inheritance
    - Pass selected scopes in API request body
    - _Requirements: 10.2, 10.3, 10.4_
  
  - [x] 16.2 Write unit tests for OAuth client creation form
    - Test form renders all scope checkboxes
    - Test form validation prevents submission with no scopes
    - Test form includes scope descriptions
    - _Requirements: 10.2, 10.3, 10.4_

- [ ] 17. Update frontend OAuth client list to display scopes
  - [x] 17.1 Modify `frontend/src/components/OAuthClients.tsx`
    - Display scopes for each client in the list
    - Format scopes as badges or tags for visual clarity
    - _Requirements: 10.1_
  
  - [x] 17.2 Write unit test for OAuth client list scope display
    - Test that scopes are rendered for each client
    - _Requirements: 10.1_

- [ ] 18. Create user management UI component
  - [x] 18.1 Create `frontend/src/components/UserManagement.tsx`
    - Implement user list table with columns: Email, Groups, Created Date, Actions
    - Add "Manage Groups" button per user
    - Implement group management modal with checkboxes for `users` and `admins`
    - Show scope preview based on selected groups
    - Call `PUT /users/{userId}/groups` API on save
    - _Requirements: 11.1, 11.2, 11.3, 11.4_
  
  - [x] 18.2 Write unit tests for user management component
    - Test user list renders correctly
    - Test group management modal appears on button click
    - Test scope preview updates based on group selection
    - _Requirements: 11.1, 11.2, 11.4_

- [ ] 19. Update frontend navigation with scope-based visibility
  - [x] 19.1 Modify `frontend/src/components/Navigation.tsx`
    - Extract scopes from JWT token in auth context
    - Hide "OAuth Clients" section if user lacks `api/oauth-clients.manage` and `api/admin`
    - Hide "Users" section if user lacks `api/admin`
    - _Requirements: 12.1, 12.2, 12.3_
  
  - [x] 19.2 Write property test for UI navigation scope-based visibility
    - **Property 14: UI Navigation Scope-Based Visibility**
    - **Validates: Requirements 12.1**
  
  - [x] 19.3 Write property test for UI admin section visibility
    - **Property 15: UI Admin Section Visibility**
    - **Validates: Requirements 12.2**
  
  - [x] 19.4 Write property test for UI scope extraction
    - **Property 16: UI Scope Extraction**
    - **Validates: Requirements 12.3**

- [ ] 20. Add user management route to frontend
  - [x] 20.1 Update frontend routing configuration
    - Add `/users` route pointing to `UserManagement` component
    - Protect route with scope check (require `api/admin`)
    - Add navigation link (conditionally rendered based on scopes)
    - _Requirements: 11.1_

- [x] 21. Final checkpoint - End-to-end testing
  - Deploy all changes to test environment
  - Test complete user authentication flow with scope injection
  - Test complete admin authentication flow with all scopes
  - Test M2M OAuth flow with limited scopes
  - Test scope inheritance with admin token
  - Test UI visibility for regular user vs admin
  - Test user group management via UI
  - Verify all scope validation logs in CloudWatch
  - Ask the user if questions arise

- [ ] 22. Update documentation
  - [x] 22.1 Update API documentation
    - Document scope requirements for each endpoint
    - Document OAuth client creation with scope selection
    - Document user management endpoints
    - _Requirements: All_
  
  - [x] 22.2 Create user guide for scope management
    - Document how to create OAuth clients with specific scopes
    - Document how to manage user groups
    - Document scope inheritance behavior
    - Document frontend UI for admin features
    - _Requirements: All_

## Notes

- All tasks are required for comprehensive implementation with full test coverage
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- The implementation follows a phased approach: infrastructure → authorization → endpoints → UI
- All scope validation uses the centralized `require_scopes()` utility for consistency
