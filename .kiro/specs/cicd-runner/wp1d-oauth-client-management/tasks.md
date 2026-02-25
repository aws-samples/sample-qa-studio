# Implementation Plan: OAuth Client Management

## Overview

This implementation plan covers the OAuth client management feature for CI/CD authentication. The feature enables users to create, list, delete, and rotate OAuth clients (M2M tokens) that use OAuth 2.0 client credentials flow.

Most endpoints are already implemented (`create_oauth_client.py`, `delete_oauth_client.py`, `list_oauth_clients.py`). This plan focuses on implementing the missing rotate secret endpoint, adding comprehensive tests, and building the frontend UI.

## Tasks

- [ ] 1. Implement rotate client secret endpoint
  - [x] 1.1 Create `rotate_client_secret.py` Lambda function
    - Implement handler function with path parameter extraction
    - Verify user owns the client via DynamoDB metadata lookup
    - Fetch current client configuration from Cognito
    - Delete old Cognito app client
    - Create new Cognito app client with same settings
    - Update DynamoDB metadata with new client_id
    - Return new client_id and client_secret
    - _Requirements: US4.1, US4.2, US4.3_
  
  - [ ]* 1.2 Write property test for secret rotation
    - **Property 8: Secret Rotation**
    - **Validates: Requirements US4.1**
  
  - [ ]* 1.3 Write property test for old secret invalidation
    - **Property 9: Old Secret Invalidation**
    - **Validates: Requirements US4.2**
  
  - [ ]* 1.4 Write unit tests for rotate endpoint
    - Test successful rotation
    - Test rotation with non-existent client (404)
    - Test rotation by non-owner (403)
    - Test Cognito errors during rotation
    - Test DynamoDB errors during metadata update
    - _Requirements: US4.1, US4.2_

- [x] 2. Add comprehensive property-based tests for existing endpoints
  - [ ]* 2.1 Write property test for scope validation
    - **Property 1: Scope Validation Prevents Privilege Escalation**
    - **Validates: Requirements US1.3**
  
  - [ ]* 2.2 Write property test for client credentials generation
    - **Property 2: Client Credentials Generation**
    - **Validates: Requirements US1.4**
  
  - [ ]* 2.3 Write property test for secret confidentiality
    - **Property 3: Secret Confidentiality**
    - **Validates: Requirements US1.5, US2.3, US4.3**
  
  - [ ]* 2.4 Write property test for Cognito registration
    - **Property 4: Cognito Registration**
    - **Validates: Requirements US1.6**
  
  - [ ]* 2.5 Write property test for list response completeness
    - **Property 5: List Response Completeness**
    - **Validates: Requirements US2.2**
  
  - [ ]* 2.6 Write property test for ownership verification
    - **Property 6: Ownership Verification**
    - **Validates: Requirements US3.1**
  
  - [ ]* 2.7 Write property test for immediate revocation
    - **Property 7: Immediate Revocation**
    - **Validates: Requirements US3.3, US3.4**
  
  - [ ]* 2.8 Write property test for audit logging
    - **Property 10: Audit Logging**
    - **Validates: Requirements US4.4**
  
  - [ ]* 2.9 Write property test for rollback consistency
    - **Property 11: Rollback Consistency**
    - **Validates: Requirements (Error Handling)**

- [x] 3. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Update CDK infrastructure for rotate endpoint
  - [x] 4.1 Add rotate_client_secret Lambda function to CDK stack
    - Define Lambda function with Python 3.11 runtime
    - Grant Cognito permissions: DescribeUserPoolClient, DeleteUserPoolClient, CreateUserPoolClient
    - Grant DynamoDB permissions: GetItem, PutItem
    - Add environment variables: USER_POOL_ID, TABLE_NAME
    - _Requirements: US4.1_
  
  - [x] 4.2 Add API Gateway route for rotate endpoint
    - Add POST /api/oauth-clients/{clientId}/rotate-secret route
    - Attach Cognito authorizer
    - Configure CORS headers
    - Link to rotate_client_secret Lambda
    - _Requirements: US4.1_
  
  - [x] 4.3 Verify OAuth scopes exist in Cognito resource server
    - Check for api/oauth-clients.read scope
    - Check for api/oauth-clients.write scope
    - Add scopes if missing
    - _Requirements: US1.3_

- [ ] 5. Implement frontend OAuth clients page
  - [x] 5.1 Create OAuth clients list page component
    - Use Cloudscape Table component with pagination
    - Display columns: client_name, client_id, created_date, scopes, actions
    - Add "Create OAuth Client" button
    - Add delete action with confirmation modal
    - Add rotate secret action with warning modal
    - Implement API calls to list endpoint
    - _Requirements: US2.1, US2.2, US2.4_
  
  - [x] 5.2 Create OAuth client creation modal
    - Add name field (required, text input)
    - Add description field (optional, textarea)
    - Add scopes field (multi-select, limited to user's scopes)
    - Implement API call to create endpoint
    - Show client_secret in success modal with copy button
    - Display warning: "This is the only time you'll see the secret"
    - Add download button for credentials JSON file
    - _Requirements: US1.1, US1.2, US1.3, US1.4, US1.5_
  
  - [x] 5.3 Implement delete confirmation modal
    - Show client name and client_id
    - Display warning about immediate revocation
    - Implement API call to delete endpoint
    - Handle success and error states
    - _Requirements: US3.1, US3.2, US3.3_
  
  - [x] 5.4 Implement rotate secret modal
    - Show client name and client_id
    - Display warning about old secret invalidation
    - Implement API call to rotate endpoint
    - Show new client_secret with copy button
    - Display warning: "This is the only time you'll see the new secret"
    - _Requirements: US4.1, US4.2, US4.3_

- [ ]* 6. Write end-to-end tests for complete workflows
  - [ ]* 6.1 Write E2E test for OAuth client creation workflow
    - Create OAuth client via API
    - Authenticate with client credentials (Cognito OAuth flow)
    - Call protected endpoint with OAuth token
    - Verify access granted with correct scopes
    - _Requirements: US1.3, US1.4, US1.6_
  
  - [ ]* 6.2 Write E2E test for OAuth client deletion workflow
    - Create OAuth client via API
    - Authenticate successfully with credentials
    - Delete OAuth client via API
    - Verify authentication fails immediately
    - Verify client removed from both Cognito and DynamoDB
    - _Requirements: US3.1, US3.3, US3.4_
  
  - [ ]* 6.3 Write E2E test for secret rotation workflow
    - Create OAuth client via API
    - Authenticate successfully with original credentials
    - Rotate client secret via API
    - Verify old credentials fail immediately
    - Verify new credentials work
    - _Requirements: US4.1, US4.2_
  
  - [ ]* 6.4 Write E2E test for CI/CD integration
    - Create OAuth client with CI/CD scopes
    - Use client credentials in simulated CI/CD runner
    - Execute test suite via API
    - Upload artifacts via presigned URLs
    - Verify execution records created correctly
    - _Requirements: US1.3, US1.6_

- [x] 7. Update API documentation
  - [x] 7.1 Document rotate secret endpoint in API.md
    - Add endpoint specification
    - Add request/response examples
    - Add error responses
    - Add cURL and Python examples
    - _Requirements: US4.1_
  
  - [x] 7.2 Update OAuth client management section
    - Document complete OAuth client lifecycle
    - Add authentication flow examples
    - Add CI/CD integration examples
    - Document scope requirements
    - _Requirements: US1.3, US1.6_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties (100+ iterations each)
- Unit tests validate specific examples and edge cases (70% coverage target)
- E2E tests validate complete workflows across multiple components
- Frontend implementation reuses existing Cloudscape patterns
- Most backend endpoints already implemented, only rotate endpoint is new
