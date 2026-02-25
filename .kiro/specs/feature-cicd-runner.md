# Feature Specification: CI/CD Test Runner

## Document Information
- **Feature Name**: CI/CD Test Runner
- **Version**: 1.0
- **Date**: 2026-02-11
- **Status**: Design Phase
- **Author**: Product Team

---

## Executive Summary

Enable developers to execute Nova Act QA Studio tests within their CI/CD pipelines through a containerized runner that authenticates via OAuth, executes tests locally with a bundled browser, and reports results back to the platform.

### Key Capabilities
- Execute individual use cases or complete test suites from CI/CD
- OAuth machine-to-machine authentication with Cognito
- Local test execution with Nova Act SDK and bundled Chromium browser
- Real-time status updates to platform via API
- Exit code-based CI/CD workflow control (0 = success, non-zero = failure)
- Artifact upload (videos, screenshots, logs) to S3
- Headless browser execution optimized for CI/CD environments

---

## Problem Statement

### Current State
- Tests can only be triggered from the web UI
- Execution happens exclusively in ECS Fargate with remote AgentCore browsers
- No integration with CI/CD pipelines
- Manual test execution workflow

### Limitations
- Cannot integrate with automated deployment pipelines
- No way to gate deployments on test results
- Developers must context-switch to web UI
- Cannot run tests in PR validation workflows
- No automated regression testing in CI/CD

### User Impact
- DevOps engineers cannot automate QA validation
- Slower feedback loops in development process
- Manual intervention required for test execution
- Reduced confidence in automated deployments
- Higher risk of production bugs

---

## Goals & Success Criteria

### Primary Goals
1. Enable test execution from any CI/CD platform (GitHub Actions, GitLab CI, Jenkins, CircleCI, etc.)
2. Provide seamless authentication via OAuth client credentials (machine-to-machine)
3. Execute tests locally in CI/CD environment with full Nova Act capabilities
4. Report results back to platform for centralized tracking and analytics
5. Control CI/CD workflow success/failure based on test results
6. Upload test artifacts (videos, screenshots, logs) to S3 for debugging

### Success Metrics
- Runner successfully executes tests in CI/CD environment
- OAuth authentication works without user intervention
- Test results appear in platform UI with CI/CD trigger type
- Exit codes correctly reflect test outcomes (0 = pass, 1 = fail, 2 = error)
- Artifacts (videos, logs) uploaded to S3 successfully
- Execution time comparable to ECS-based runs

### Non-Goals (Out of Scope for v1.0)
- Modifying existing UI-triggered execution flow
- Changing ECS-based execution architecture
- Supporting non-Docker runner distributions
- Real-time streaming of test execution to UI
- Live view functionality for CI/CD runs
- Parallel test execution within single runner instance

---

## Key Design Decisions

### 1. Local Execution Model with Bundled Browser
**Decision**: Runner executes tests locally using Nova Act SDK with bundled Chromium browser.

**Rationale**:
- CI/CD environments already have compute resources
- Reduces AWS costs (no ECS tasks or AgentCore browsers for CI/CD runs)
- Faster feedback (no ECS task startup time, no remote browser provisioning)
- Simpler architecture (no orchestration needed)
- Better isolation (each CI/CD job is independent)
- Nova Act SDK includes Chromium browser out-of-the-box

**Trade-offs**:
- Runner container must include Nova Act SDK and dependencies (~500MB)
- No live view capability (acceptable for CI/CD use case)
- Manual artifact upload required (vs automatic with AgentCore)
- CI/CD environment must support Docker

**Implementation Details**:
- Use Nova Act's local browser mode (no `create_browser()` calls)
- Always run in headless mode for CI/CD
- Use Nova Act's built-in recording capabilities
- Upload recordings to S3 after test completion

### 2. OAuth Machine-to-Machine Authentication
**Decision**: Use OAuth 2.0 Client Credentials flow with Cognito.

**Rationale**:
- Industry standard for service-to-service authentication
- No user credentials in CI/CD secrets
- Scoped access control (suite/usecase level)
- Token expiration and rotation support
- Leverages existing OAuth client infrastructure in platform

**Implementation**:
```bash
# Runner authenticates with Cognito
TOKEN=$(curl -X POST https://${COGNITO_DOMAIN}/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d "scope=suite:smoke-tests usecase:login-test")
```

**Scope Format**:
- Suite scopes: `suite:smoke-tests`, `suite:regression`
- Use case scopes: `usecase:login-test`, `usecase:checkout-flow`
- Runner requires appropriate scope to execute tests

### 3. Execution Ownership Transfer
**Decision**: Runner performs execution creation (copy from usecase), not Lambda.

**Rationale**:
- Runner needs execution_id before starting tests
- Simplifies API design (single create endpoint)
- Runner controls execution lifecycle
- Consistent with "local execution" model
- Allows runner to set CI/CD metadata (commit SHA, branch, etc.)

**Flow**:
1. Runner calls API: `POST /api/runner/executions` (copies usecase → execution)
2. API returns execution_id and metadata
3. Runner executes tests locally with Nova Act SDK
4. Runner updates status via API: `PUT /api/runner/executions/{id}/status`
5. Runner uploads artifacts via API: `POST /api/runner/executions/{id}/artifacts`

### 4. Dual Authentication Support
**Decision**: All new APIs accept both Cognito user tokens AND OAuth M2M tokens.

**Rationale**:
- Future-proof for UI refactoring
- Consistent API surface
- Easier testing and development
- No separate "runner-only" endpoints
- Allows manual testing with user tokens

**Implementation**: 
- API Gateway Authorizer Lambda checks token type
- Validates scopes for OAuth tokens
- Validates Cognito groups for user tokens
- Passes authentication context to Lambda functions

### 5. Trigger Type Differentiation
**Decision**: Add `trigger_type: 'cicd'` to executions created by runner.

**Rationale**:
- Distinguish CI/CD runs from UI/scheduled runs in analytics
- Enable filtering in UI ("Show only CI/CD runs")
- Different UX treatment (e.g., show commit SHA, pipeline link)
- Track adoption metrics

**Values**: 
- `manual`: Triggered from UI by user
- `scheduled`: Triggered by EventBridge schedule
- `cicd`: Triggered by CI/CD runner

### 6. Exit Code Strategy
**Decision**: 
- Exit 0: All tests passed successfully
- Exit 1: One or more tests failed
- Exit 2: Runner error (auth failure, API error, configuration error)

**Rationale**:
- Standard Unix convention
- CI/CD platforms understand exit codes natively
- Clear distinction between test failure and runner failure
- Enables proper CI/CD workflow control

**Examples**:
```yaml
# GitHub Actions
- name: Run QA Tests
  run: |
    docker run nova-act-runner \
      --usecase-id login-test-123 \
      --client-id ${{ secrets.CLIENT_ID }} \
      --client-secret ${{ secrets.CLIENT_SECRET }}
  # Job fails if exit code != 0
```

### 7. No Live View for CI/CD Runs
**Decision**: Skip live view functionality for CI/CD executions.

**Rationale**:
- No user watching tests in real-time during CI/CD
- Reduces complexity (no browser management)
- Saves AWS costs (no AgentCore browser provisioning)
- Recordings and logs provide sufficient debugging information

**Implementation**: 
- Do not create `LIVE_VIEW` record in DynamoDB
- Do not call `create_browser()` / `start_browser()` / `delete_browser()`
- UI shows "N/A" for live view on CI/CD executions

### 8. Headless Mode Always
**Decision**: Runner always executes in headless mode.

**Rationale**:
- CI/CD environments typically don't have displays
- Faster execution (no GPU rendering)
- Lower resource usage
- Standard practice for automated testing

**Implementation**: Nova Act initialized with `headless=True` always.

---

## Architecture Overview

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ CI/CD Pipeline (GitHub Actions, GitLab CI, Jenkins, etc.)      │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Docker Container: nova-act-runner                        │  │
│  │                                                          │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │ Nova Act SDK + Chromium Browser (Local)            │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  │                                                          │  │
│  │  1. Parse CLI arguments (usecase/suite ID, scopes)     │  │
│  │  2. Authenticate with Cognito (OAuth M2M)              │  │
│  │  3. Call API: Create Execution (copy usecase)          │  │
│  │  4. Execute tests locally with Nova Act SDK            │  │
│  │  5. Update execution status via API (per step)         │  │
│  │  6. Upload artifacts (videos, logs) to S3              │  │
│  │  7. Exit with code (0=success, 1=failure, 2=error)     │  │
│  │                                                          │  │
│  └────────────┬─────────────────────────────────────────────┘  │
│               │                                                 │
└───────────────┼─────────────────────────────────────────────────┘
                │
                │ HTTPS (OAuth Token)
                ▼
┌─────────────────────────────────────────────────────────────────┐
│ AWS Cloud                                                       │
│                                                                 │
│  ┌──────────────┐      ┌─────────────────┐                    │
│  │   Cognito    │      │   API Gateway   │                    │
│  │              │      │                 │                    │
│  │ OAuth Token  │◄─────┤  Authorizer     │                    │
│  │  Endpoint    │      │  (Enhanced)     │                    │
│  └──────────────┘      └────────┬────────┘                    │
│                                 │                              │
│                                 │                              │
│                        ┌────────▼────────┐                    │
│                        │  Lambda         │                    │
│                        │  Functions      │                    │
│                        │  (New)          │                    │
│                        │                 │                    │
│                        │ • create_exec   │                    │
│                        │ • update_status │                    │
│                        │ • upload_artifact│                   │
│                        └────────┬────────┘                    │
│                                 │                              │
│                    ┌────────────┼────────────┐                │
│                    │            │            │                │
│              ┌─────▼─────┐ ┌───▼────┐  ┌───▼────┐           │
│              │ DynamoDB  │ │   S3   │  │ Secrets│           │
│              │           │ │        │  │Manager │           │
│              │ Executions│ │Artifacts│ │        │           │
│              └───────────┘ └────────┘  └────────┘           │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

#### 1. CI/CD Runner (Docker Container)
**Technology**: Python 3.11+ with Nova Act SDK

**Responsibilities**:
- Parse CLI arguments (usecase/suite ID, OAuth credentials, API endpoint)
- Authenticate with Cognito OAuth endpoint
- Call API to create execution (copy from usecase/suite)
- Initialize Nova Act SDK with local Chromium browser (headless)
- Execute test steps sequentially
- Update execution status in real-time via API
- Capture and upload artifacts (videos, screenshots, logs) to S3
- Return appropriate exit code based on test results

**Key Files**:
- `runner/main.py`: Entry point, CLI argument parsing
- `runner/auth.py`: OAuth authentication with Cognito
- `runner/api_client.py`: API communication layer
- `runner/executor.py`: Test execution logic (similar to worker.py)
- `runner/artifact_uploader.py`: S3 artifact upload
- `Dockerfile`: Container definition

**Dependencies**:
- Nova Act SDK (includes Chromium browser)
- boto3 (for S3 uploads)
- requests (for API calls)
- Python standard library



#### 2. New Lambda: `create_execution_for_runner`
**Purpose**: Create execution record by copying from usecase or suite.

**Responsibilities**:
- Accept usecase_id OR suite_id
- Validate OAuth scopes (caller has access to usecase/suite)
- Copy usecase steps → execution steps
- Copy variables → execution variables  
- Copy headers → execution headers
- Copy secrets references (not values)
- Generate unique execution_id
- Set trigger_type: 'cicd'
- Store CI metadata (commit SHA, branch, pipeline URL)
- Return execution_id and metadata to runner

**Input**:
```json
{
  "usecase_id": "login-test-123",
  "ci_metadata": {
    "commit_sha": "a1b2c3d4",
    "branch": "main",
    "pipeline_id": "github-actions-789",
    "pipeline_url": "https://github.com/org/repo/actions/runs/789"
  }
}
```

**Output**:
```json
{
  "execution_id": "exec-456",
  "usecase_id": "login-test-123",
  "starting_url": "https://example.com/login",
  "steps_count": 5,
  "variables": [
    {"key": "username", "value": "testuser"},
    {"key": "environment", "value": "staging"}
  ],
  "headers": {
    "X-API-Key": "{{API_KEY}}"
  },
  "region": "us-east-1"
}
```

**Logic** (similar to existing `execute_usecase.py`):
1. Get usecase from DynamoDB
2. Validate scope access
3. Create execution record with trigger_type='cicd'
4. Copy all steps with new execution_id
5. Copy variables
6. Copy headers
7. Return execution metadata

#### 3. New Lambda: `update_execution_status_runner`
**Purpose**: Update execution and step status from runner.

**Responsibilities**:
- Accept execution_id and status updates
- Update execution status (pending → executing → success/failed)
- Update individual step status and logs
- Update step act_id (Nova Act action ID)
- Update runtime variables (captured values)
- Validate OAuth scopes
- Send notifications on failure (reuse existing logic)

**Endpoints**:

**A. Update Execution Status**
```
PUT /api/runner/executions/{execution_id}/status
```

**Input**:
```json
{
  "status": "executing",
  "executing_at": "2026-02-11T15:00:05Z"
}
```

**B. Update Step Status**
```
PUT /api/runner/executions/{execution_id}/steps/{step_id}/status
```

**Input**:
```json
{
  "act_id": "act_abc123",
  "status": "success",
  "logs": "Step completed successfully",
  "actual_value": "Login successful"
}
```

**C. Update Runtime Variables**
```
PUT /api/runner/executions/{execution_id}/variables
```

**Input**:
```json
{
  "runtime_variables": [
    {"key": "session_token", "value": "xyz789"},
    {"key": "user_id", "value": "12345"}
  ]
}
```

#### 4. New Lambda: `generate_artifact_upload_url`
**Purpose**: Generate presigned S3 URL for artifact upload.

**Responsibilities**:
- Accept execution_id and artifact metadata
- Validate OAuth scopes
- Generate presigned S3 PUT URL (15 min expiration)
- Return URL to runner
- Validate file size limits (max 500MB per artifact)

**Endpoint**:
```
POST /api/runner/executions/{execution_id}/artifacts/upload-url
```

**Input**:
```json
{
  "artifact_type": "video",
  "filename": "execution.webm",
  "content_type": "video/webm",
  "size_bytes": 52428800
}
```

**Output**:
```json
{
  "upload_url": "https://s3.amazonaws.com/bucket/path?signature=...",
  "expires_at": "2026-02-11T15:15:00Z",
  "s3_key": "login-test-123/exec-456/execution.webm"
}
```

**Artifact Types**:
- `video`: Test execution recording (.webm)
- `screenshot`: Step screenshots (.png)
- `log`: Nova Act logs (.log)
- `trace`: Browser trace files (.json)

#### 5. API Gateway Authorizer Enhancement
**Purpose**: Support both Cognito user tokens and OAuth M2M tokens.

**Current State**: Only validates Cognito user tokens.

**Enhancement**: 
- Detect token type (Cognito vs OAuth)
- For OAuth tokens: Validate with Cognito OAuth endpoint
- Extract scopes from OAuth token
- Pass scope context to Lambda functions
- For Cognito tokens: Use existing validation logic

**Implementation**:
```python
def lambda_handler(event, context):
    token = extract_token(event)
    
    if is_oauth_token(token):
        # Validate OAuth token with Cognito
        claims = validate_oauth_token(token)
        scopes = claims.get('scope', '').split()
        
        return {
            'principalId': claims['client_id'],
            'context': {
                'auth_type': 'oauth',
                'client_id': claims['client_id'],
                'scopes': json.dumps(scopes)
            },
            'policyDocument': generate_policy('Allow', event['methodArn'])
        }
    else:
        # Existing Cognito user token validation
        return validate_cognito_token(token)
```

---

## Secret Sets and Stage Management

### Overview
Secret sets allow users to maintain different secret values for different environments (dev, staging, production) while keeping the same secret names across all stages. This enables the same test to run against different environments without modifying the test definition.

### Data Model

#### Secret Set Entity
**Keys**: pk='USECASE_SECRETS#{usecase_id}', sk='SECRET#{secret_name}#{stage}'

**Attributes**:
```python
{
  "pk": "USECASE_SECRETS#login-test-123",
  "sk": "SECRET#username#production",
  "secret_name": "username",
  "stage": "production",
  "secret_value_arn": "arn:aws:secretsmanager:us-east-1:123456789:secret:login-username-prod-abc123",
  "created_at": "2026-02-11T15:00:00Z",
  "updated_at": "2026-02-11T15:00:00Z",
  "created_by": "user-123"
}
```

**Example Secret Set**:
```
USECASE_SECRETS#login-test-123
├── SECRET#username#dev          → "testuser@dev.com"
├── SECRET#username#staging      → "testuser@staging.com"
├── SECRET#username#production   → "testuser@prod.com"
├── SECRET#password#dev          → "dev_password_123"
├── SECRET#password#staging      → "staging_password_456"
└── SECRET#password#production   → "prod_password_789"
```

### Secret Resolution Logic

**Without Stage Override** (default behavior):
- Runner uses secrets without stage suffix
- Falls back to existing secret resolution: `USECASE_SECRETS#{usecase_id}#SECRET#{secret_name}`

**With Stage Override** (`--stage production`):
- Runner looks for: `USECASE_SECRETS#{usecase_id}#SECRET#{secret_name}#production`
- If not found, falls back to default: `USECASE_SECRETS#{usecase_id}#SECRET#{secret_name}`
- If still not found, execution fails with error

**Priority Order**:
1. Stage-specific secret (if `--stage` provided)
2. Default secret (no stage)
3. Error if neither exists

### UI Changes for Secret Sets

#### 1. Secret Management Page
**Location**: Use Case → Secrets Tab

**New UI**:
```
┌─────────────────────────────────────────────────────────────┐
│ Secrets                                                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ [+ Add Secret]  [+ Add Stage]                              │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐│
│ │ Secret: username                                        ││
│ │                                                         ││
│ │ Stages:                                                 ││
│ │ • dev        [Edit] [Delete]                           ││
│ │ • staging    [Edit] [Delete]                           ││
│ │ • production [Edit] [Delete]                           ││
│ │                                                         ││
│ │ [+ Add Stage for username]                             ││
│ └─────────────────────────────────────────────────────────┘│
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐│
│ │ Secret: password                                        ││
│ │                                                         ││
│ │ Stages:                                                 ││
│ │ • dev        [Edit] [Delete]                           ││
│ │ • staging    [Edit] [Delete]                           ││
│ │ • production [Edit] [Delete]                           ││
│ └─────────────────────────────────────────────────────────┘│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 2. Add/Edit Secret Modal
**Enhanced Modal**:
```
┌─────────────────────────────────────────────────────────────┐
│ Add Secret                                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Secret Name: [username                    ]                │
│                                                             │
│ Stage (optional): [production            ▼]                │
│                   • dev                                     │
│                   • staging                                 │
│                   • production                              │
│                   • (none - default)                        │
│                                                             │
│ Secret Value: [********************      ]                 │
│                                                             │
│ Note: If no stage is selected, this will be the default    │
│       value used when no stage override is provided.       │
│                                                             │
│                              [Cancel]  [Save]               │
└─────────────────────────────────────────────────────────────┘
```

#### 3. Stage Management
**New Settings Section**: Settings → Stages

```
┌─────────────────────────────────────────────────────────────┐
│ Environment Stages                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Manage environment stages for secret sets and CI/CD runs.  │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐│
│ │ Stage Name    │ Description              │ Actions      ││
│ ├───────────────┼──────────────────────────┼──────────────┤│
│ │ dev           │ Development environment  │ [Edit] [Del] ││
│ │ staging       │ Staging environment      │ [Edit] [Del] ││
│ │ production    │ Production environment   │ [Edit] [Del] ││
│ └─────────────────────────────────────────────────────────┘│
│                                                             │
│ [+ Add Stage]                                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### API Changes

#### New Endpoint: Get Secrets for Stage
**Endpoint**: `GET /api/usecases/{usecase_id}/secrets?stage={stage}`

**Response**:
```json
{
  "secrets": [
    {
      "secret_name": "username",
      "stage": "production",
      "secret_value_arn": "arn:aws:secretsmanager:...",
      "has_default": true
    },
    {
      "secret_name": "password",
      "stage": "production",
      "secret_value_arn": "arn:aws:secretsmanager:...",
      "has_default": true
    }
  ]
}
```

#### Enhanced Endpoint: Create/Update Secret
**Endpoint**: `POST /api/usecases/{usecase_id}/secrets`

**Request**:
```json
{
  "secret_name": "username",
  "stage": "production",
  "secret_value": "testuser@prod.com"
}
```

**Note**: If `stage` is omitted or null, creates default secret.

### Runner Implementation

**Secret Resolution in Runner**:
```python
def get_secret_value(usecase_id, secret_name, stage=None):
    """Get secret value with stage fallback"""
    
    # Try stage-specific secret first
    if stage:
        secret_arn = get_secret_arn(usecase_id, secret_name, stage)
        if secret_arn:
            return get_secret_from_arn(secret_arn)
    
    # Fallback to default secret
    secret_arn = get_secret_arn(usecase_id, secret_name, stage=None)
    if secret_arn:
        return get_secret_from_arn(secret_arn)
    
    # Secret not found
    raise SecretNotFoundError(
        f"Secret '{secret_name}' not found for usecase '{usecase_id}'"
        f"{f' (stage: {stage})' if stage else ''}"
    )
```

**Step Execution with Stage**:
```python
def execute_secret_step(nova, step, usecase_id, stage=None):
    """Execute secret step with stage-aware secret resolution"""
    
    secret_name = step.secret_key
    secret_value = get_secret_value(usecase_id, secret_name, stage)
    
    # Execute step with resolved secret
    result = nova.act(step.instruction, secret_value)
    
    return result
```

### Lambda Changes

#### Enhanced: `create_execution_for_runner`
**Changes**:
- Accept `stage` in `ci_overrides`
- Store stage in execution record
- Return stage in response for runner to use

**Logic**:
```python
def create_execution(usecase_id, ci_overrides=None):
    # ... existing logic ...
    
    # Store stage for secret resolution
    stage = ci_overrides.get('stage') if ci_overrides else None
    
    execution = {
        'execution_id': execution_id,
        'usecase_id': usecase_id,
        'ci_overrides': {
            'stage': stage,
            'starting_url': ci_overrides.get('starting_url'),
            'variables': ci_overrides.get('variables', [])
        }
    }
    
    # Copy steps with stage information
    for step in steps:
        if step.step_type == 'secret':
            step.secret_stage = stage  # Add stage to step
    
    return execution
```

### Migration Strategy

**Existing Secrets**:
- All existing secrets remain as default (no stage)
- No migration required
- Tests continue to work without changes

**Gradual Adoption**:
1. Users can add stage-specific secrets incrementally
2. Tests work with default secrets until stages are added
3. CI/CD can start using `--stage` flag when ready

---

## Data Model Changes

### 1. Execution Entity (Enhanced)
**Keys**: pk='USECASE_EXECUTION#{usecase_id}', sk='EXECUTION#{execution_id}'

**New Attributes**:
```python
{
  # Existing fields
  "pk": "USECASE_EXECUTION#login-test-123",
  "sk": "EXECUTION#exec-456",
  "status": "success",
  "starting_url": "https://example.com/login",
  "created_at": "2026-02-11T15:00:00Z",
  "executing_at": "2026-02-11T15:00:05Z",
  "completed_at": "2026-02-11T15:02:30Z",
  "region": "us-east-1",
  
  # NEW: Trigger information
  "trigger_type": "cicd",  # 'manual' | 'scheduled' | 'cicd'
  "triggered_by_client_id": "cicd-client-abc",  # OAuth client_id (for cicd)
  "triggered_by_user_id": null,  # user_id (for manual)
  
  # NEW: CI/CD metadata
  "ci_metadata": {
    "commit_sha": "a1b2c3d4e5f6",
    "branch": "main",
    "pipeline_id": "github-actions-789",
    "pipeline_url": "https://github.com/org/repo/actions/runs/789",
    "repository": "org/repo"
  },
  
  # NEW: CI/CD overrides
  "ci_overrides": {
    "stage": "production",
    "starting_url": "https://prod.example.com/login",
    "variables": [
      {"key": "environment", "value": "production"},
      {"key": "api_endpoint", "value": "https://api.prod.example.com"}
    ]
  },
  
  # NEW: Suite linkage (if part of suite execution)
  "suite_execution_id": "suite-exec-789"  # Links to parent suite execution
}
```

**Access Patterns**:
- Get execution: pk='USECASE_EXECUTION#{usecase_id}', sk='EXECUTION#{execution_id}'
- List executions for usecase: pk='USECASE_EXECUTION#{usecase_id}', sk begins_with 'EXECUTION#'
- Filter by trigger_type: Use FilterExpression
- Find executions by suite: Requires GSI (see below)

### 2. Suite Execution Entity (Enhanced)
**Keys**: pk='SUITE_EXECUTION#{suite_id}', sk='EXECUTION#{suite_execution_id}'

**New Attributes**:
```python
{
  # Existing fields
  "pk": "SUITE_EXECUTION#smoke-tests",
  "sk": "EXECUTION#suite-exec-789",
  "suite_id": "smoke-tests",
  "suite_name": "Smoke Tests",
  "status": "partial",  # 'pending' | 'running' | 'completed' | 'partial' | 'failed'
  "started_at": "2026-02-11T15:00:00Z",
  "completed_at": "2026-02-11T15:05:00Z",
  "total_usecases": 3,
  "successful_count": 2,
  "failed_count": 1,
  
  # NEW: Trigger information
  "trigger_type": "cicd",
  "triggered_by_client_id": "cicd-client-abc",
  
  # NEW: CI/CD metadata
  "ci_metadata": {
    "commit_sha": "a1b2c3d4e5f6",
    "branch": "main",
    "pipeline_id": "github-actions-789",
    "pipeline_url": "https://github.com/org/repo/actions/runs/789"
  },
  
  # NEW: Individual execution IDs (for tracking)
  "execution_ids": [
    "exec-456",  # login-test
    "exec-457",  # checkout-test
    "exec-458"   # search-test
  ]
}
```

### 3. Global Secondary Index (GSI) for Suite Execution Queries
**Purpose**: Query all individual executions that belong to a suite execution.

**GSI Name**: `GSI_SuiteExecution`

**Keys**:
- Partition Key: `suite_execution_id`
- Sort Key: `created_at`

**Projection**: ALL

**Query Pattern**:
```python
# Get all individual test runs for suite execution
response = table.query(
    IndexName='GSI_SuiteExecution',
    KeyConditionExpression=Key('suite_execution_id').eq('suite-exec-789')
)
```

**Use Cases**:
- Display all tests in a suite run
- Calculate suite execution metrics
- Track which tests passed/failed in suite
- Link from suite execution to individual test results

### 4. Execution Steps (No Changes)
**Keys**: pk='EXECUTION#{execution_id}', sk='EXECUTION_STEP#{step_id}'

**Note**: No schema changes needed. Steps are copied from usecase as-is.

### 5. Execution Variables (No Changes)
**Keys**: pk='EXECUTION#{execution_id}', sk='EXECUTION_VARIABLES'

**Note**: No schema changes needed. Variables are copied from usecase as-is.

### 6. Execution Headers (No Changes)
**Keys**: pk='EXECUTION#{execution_id}', sk='HEADERS'

**Note**: No schema changes needed. Headers are copied from usecase as-is.

---

## API Specifications

### Authentication
All endpoints require either:
- **Cognito User Token**: `Authorization: Bearer <cognito_token>`
- **OAuth M2M Token**: `Authorization: Bearer <oauth_token>`

Authorizer validates scopes based on token type.

### Base URL
```
https://api.nova-act-qa-studio.example.com/api/runner
```

### Endpoints

#### 1. Create Execution
**Purpose**: Create execution by copying from usecase or suite.

**Endpoint**: `POST /api/runner/executions`

**Request Headers**:
```
Authorization: Bearer <oauth_token>
Content-Type: application/json
```

**Request Body**:
```json
{
  "usecase_id": "login-test-123",
  "ci_metadata": {
    "commit_sha": "a1b2c3d4e5f6",
    "branch": "main",
    "pipeline_id": "github-actions-789",
    "pipeline_url": "https://github.com/org/repo/actions/runs/789",
    "repository": "org/repo"
  },
  "ci_overrides": {
    "stage": "production",
    "starting_url": "https://prod.example.com/login",
    "variables": [
      {"key": "environment", "value": "production"},
      {"key": "api_endpoint", "value": "https://api.prod.example.com"}
    ]
  }
}
```

**OR for suite execution**:
```json
{
  "suite_id": "smoke-tests",
  "ci_metadata": {
    "commit_sha": "a1b2c3d4e5f6",
    "branch": "main",
    "pipeline_id": "github-actions-789",
    "pipeline_url": "https://github.com/org/repo/actions/runs/789"
  },
  "ci_overrides": {
    "stage": "staging",
    "variables": [
      {"key": "environment", "value": "staging"}
    ]
  }
}
```

**Response** (200 OK):
```json
{
  "execution_id": "exec-456",
  "usecase_id": "login-test-123",
  "starting_url": "https://prod.example.com/login",
  "region": "us-east-1",
  "steps": [
    {
      "step_id": "step-001",
      "sort": 1,
      "instruction": "Navigate to login page",
      "step_type": "navigation"
    },
    {
      "step_id": "step-002",
      "sort": 2,
      "instruction": "Enter username",
      "step_type": "secret",
      "secret_key": "username",
      "secret_stage": "production"
    }
  ],
  "variables": [
    {"key": "environment", "value": "production"},
    {"key": "api_endpoint", "value": "https://api.prod.example.com"},
    {"key": "base_url", "value": "https://staging.example.com"}
  ],
  "headers": {
    "X-API-Key": "{{API_KEY}}"
  },
  "ci_overrides": {
    "stage": "production",
    "starting_url": "https://prod.example.com/login",
    "variables": [
      {"key": "environment", "value": "production"},
      {"key": "api_endpoint", "value": "https://api.prod.example.com"}
    ]
  }
}
```

**Response for Suite** (200 OK):
```json
{
  "suite_execution_id": "suite-exec-789",
  "suite_id": "smoke-tests",
  "suite_name": "Smoke Tests",
  "executions": [
    {
      "execution_id": "exec-456",
      "usecase_id": "login-test-123",
      "usecase_name": "Login Test",
      "starting_url": "https://example.com/login"
    },
    {
      "execution_id": "exec-457",
      "usecase_id": "checkout-test-456",
      "usecase_name": "Checkout Test",
      "starting_url": "https://example.com/checkout"
    }
  ],
  "ci_overrides": {
    "stage": "staging",
    "variables": [
      {"key": "environment", "value": "staging"}
    ]
  }
}
```

**Override Behavior**:
- `stage`: Used to fetch secrets from stage-specific secret sets (e.g., `username:production`, `password:production`)
- `starting_url`: Overrides the usecase's default starting URL
- `variables`: Merged with usecase variables, CI overrides take precedence

**Error Responses**:
- `401 Unauthorized`: Invalid or expired token
- `403 Forbidden`: Insufficient scopes
- `404 Not Found`: Usecase/suite not found
- `500 Internal Server Error`: Server error

**Scope Requirements**:
- For usecase: `usecase:{usecase_id}` or `usecase:*`
- For suite: `suite:{suite_id}` or `suite:*`



#### 2. Update Execution Status
**Purpose**: Update execution status and timestamps.

**Endpoint**: `PUT /api/runner/executions/{execution_id}/status`

**Request Body**:
```json
{
  "status": "executing",
  "executing_at": "2026-02-11T15:00:05Z"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "execution_id": "exec-456",
  "status": "executing"
}
```

**Valid Status Transitions**:
- `pending` → `executing`
- `executing` → `success`
- `executing` → `failed`

#### 3. Update Step Status
**Purpose**: Update individual step status, logs, and act_id.

**Endpoint**: `PUT /api/runner/executions/{execution_id}/steps/{step_id}/status`

**Request Body**:
```json
{
  "act_id": "act_abc123",
  "status": "success",
  "logs": "Step completed successfully",
  "actual_value": "Login successful"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "step_id": "step-001",
  "status": "success"
}
```

#### 4. Update Runtime Variables
**Purpose**: Update runtime variables captured during execution.

**Endpoint**: `PUT /api/runner/executions/{execution_id}/variables`

**Request Body**:
```json
{
  "runtime_variables": [
    {"key": "session_token", "value": "xyz789"},
    {"key": "user_id", "value": "12345"}
  ]
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "variables_updated": 2
}
```

#### 5. Generate Artifact Upload URL
**Purpose**: Get presigned S3 URL for artifact upload.

**Endpoint**: `POST /api/runner/executions/{execution_id}/artifacts/upload-url`

**Request Body**:
```json
{
  "artifact_type": "video",
  "filename": "execution.webm",
  "content_type": "video/webm",
  "size_bytes": 52428800
}
```

**Response** (200 OK):
```json
{
  "upload_url": "https://s3.amazonaws.com/bucket/path?signature=...",
  "expires_at": "2026-02-11T15:15:00Z",
  "s3_key": "login-test-123/exec-456/execution.webm",
  "method": "PUT"
}
```

**Artifact Types**:
- `video`: Test execution recording (.webm)
- `screenshot`: Step screenshots (.png)
- `log`: Nova Act logs (.log)
- `trace`: Browser trace files (.json)

**Size Limits**:
- Video: 500MB max
- Screenshot: 10MB max
- Log: 50MB max
- Trace: 100MB max

---

## Runner Implementation

### Docker Container Structure

```
nova-act-runner/
├── Dockerfile
├── requirements.txt
├── runner/
│   ├── __init__.py
│   ├── main.py              # Entry point, CLI parsing
│   ├── auth.py              # OAuth authentication
│   ├── api_client.py        # API communication
│   ├── executor.py          # Test execution (similar to worker.py)
│   ├── artifact_uploader.py # S3 artifact upload
│   └── models.py            # Data models
└── README.md
```

### CLI Interface

```bash
docker run nova-act-runner \
  --api-endpoint https://api.example.com \
  --cognito-domain auth.example.com \
  --client-id <client_id> \
  --client-secret <client_secret> \
  --usecase-id login-test-123 \
  --commit-sha a1b2c3d4 \
  --branch main \
  --pipeline-url https://github.com/org/repo/actions/runs/789
```

**OR for suite execution**:

```bash
docker run nova-act-runner \
  --api-endpoint https://api.example.com \
  --cognito-domain auth.example.com \
  --client-id <client_id> \
  --client-secret <client_secret> \
  --suite-id smoke-tests \
  --commit-sha a1b2c3d4 \
  --branch main
```

### Required Arguments
- `--api-endpoint`: API Gateway endpoint
- `--cognito-domain`: Cognito domain for OAuth
- `--client-id`: OAuth client ID
- `--client-secret`: OAuth client secret
- `--usecase-id` OR `--suite-id`: Test to execute

### Optional Arguments
- `--commit-sha`: Git commit hash
- `--branch`: Git branch name
- `--pipeline-id`: CI/CD pipeline identifier
- `--pipeline-url`: Link to CI/CD run
- `--repository`: Git repository (org/repo)
- `--region`: AWS region (default: us-east-1)
- `--log-level`: Logging level (default: INFO)

### Test Configuration Overrides
- `--stage`: Secret stage/environment (e.g., dev, staging, production)
- `--starting-url`: Override starting URL from usecase
- `--variable KEY=VALUE`: Override or add variables (can be specified multiple times)

**Examples**:
```bash
# Override starting URL for different environment
docker run nova-act-runner \
  --usecase-id login-test-123 \
  --starting-url https://staging.example.com/login

# Use production secrets
docker run nova-act-runner \
  --usecase-id login-test-123 \
  --stage production

# Override multiple variables
docker run nova-act-runner \
  --usecase-id login-test-123 \
  --variable environment=staging \
  --variable api_endpoint=https://api.staging.example.com \
  --variable timeout=30

# Combine all overrides
docker run nova-act-runner \
  --usecase-id login-test-123 \
  --stage production \
  --starting-url https://prod.example.com \
  --variable environment=production \
  --variable region=us-west-2
```

### Environment Variables (Alternative)
```bash
export NOVA_ACT_API_ENDPOINT=https://api.example.com
export NOVA_ACT_COGNITO_DOMAIN=auth.example.com
export NOVA_ACT_CLIENT_ID=<client_id>
export NOVA_ACT_CLIENT_SECRET=<client_secret>

docker run nova-act-runner --usecase-id login-test-123
```

### Execution Flow

```python
# Pseudocode for runner/main.py

def main():
    # 1. Parse CLI arguments
    args = parse_arguments()
    
    # 2. Authenticate with Cognito
    token = authenticate_oauth(
        cognito_domain=args.cognito_domain,
        client_id=args.client_id,
        client_secret=args.client_secret,
        scopes=get_required_scopes(args)
    )
    
    # 3. Initialize API client
    api_client = APIClient(
        endpoint=args.api_endpoint,
        token=token
    )
    
    # 4. Build CI overrides from CLI arguments
    ci_overrides = {
        'stage': args.stage,
        'starting_url': args.starting_url,
        'variables': parse_variable_overrides(args.variables)
    }
    
    # 5. Create execution
    if args.usecase_id:
        execution = api_client.create_execution(
            usecase_id=args.usecase_id,
            ci_metadata=build_ci_metadata(args),
            ci_overrides=ci_overrides
        )
        executions = [execution]
    else:
        suite_execution = api_client.create_suite_execution(
            suite_id=args.suite_id,
            ci_metadata=build_ci_metadata(args),
            ci_overrides=ci_overrides
        )
        executions = suite_execution['executions']
    
    # 6. Execute tests
    all_success = True
    for execution in executions:
        success = execute_test(execution, api_client, args.stage)
        if not success:
            all_success = False
    
    # 7. Exit with appropriate code
    if all_success:
        sys.exit(0)  # Success
    else:
        sys.exit(1)  # Test failure


def parse_variable_overrides(variable_args):
    """Parse --variable KEY=VALUE arguments into list of dicts"""
    variables = []
    if variable_args:
        for var in variable_args:
            key, value = var.split('=', 1)
            variables.append({'key': key, 'value': value})
    return variables


def execute_test(execution, api_client, stage=None):
    """Execute single test (similar to worker.py)"""
    
    # Apply overrides from execution
    starting_url = execution.get('ci_overrides', {}).get('starting_url') or execution['starting_url']
    override_variables = execution.get('ci_overrides', {}).get('variables', [])
    
    # Merge variables: base variables + overrides (overrides take precedence)
    merged_variables = merge_variables(execution['variables'], override_variables)
    
    # Update status to executing
    api_client.update_execution_status(
        execution_id=execution['execution_id'],
        status='executing'
    )
    
    try:
        # Initialize Nova Act with local browser
        with NovaAct(
            starting_page=starting_url,  # Use overridden URL
            headless=True,
            logs_directory=f"./logs/{execution['execution_id']}",
            ignore_https_errors=True,
            chrome_channel="chromium"
        ) as nova:
            
            # Initialize template parser with merged variables
            template_parser = TemplateParser(
                execution_id=execution['execution_id'],
                variables=merged_variables
            )
            
            # Execute steps
            for step in execution['steps']:
                success = execute_step(
                    nova, 
                    step, 
                    execution, 
                    api_client, 
                    template_parser,
                    stage  # Pass stage for secret resolution
                )
                if not success:
                    return False
            
            # Upload artifacts
            upload_artifacts(execution['execution_id'], api_client)
            
            # Update status to success
            api_client.update_execution_status(
                execution_id=execution['execution_id'],
                status='success'
            )
            
            return True
            
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        api_client.update_execution_status(
            execution_id=execution['execution_id'],
            status='failed'
        )
        return False


def merge_variables(base_variables, override_variables):
    """Merge base and override variables, overrides take precedence"""
    # Convert to dict for easy merging
    merged = {var['key']: var['value'] for var in base_variables}
    
    # Apply overrides
    for var in override_variables:
        merged[var['key']] = var['value']
    
    # Convert back to list
    return [{'key': k, 'value': v} for k, v in merged.items()]


def execute_step(nova, step, execution, api_client, template_parser, stage=None):
    """Execute single step with stage-aware secret resolution"""
    
    try:
        # Parse step with template variables
        parsed_step = template_parser.parse_single_step(step)
        
        if parsed_step.step_type == 'secret':
            # Resolve secret with stage
            secret_value = api_client.get_secret_value(
                usecase_id=execution['usecase_id'],
                secret_name=parsed_step.secret_key,
                stage=stage
            )
            result = nova.act(parsed_step.instruction, secret_value)
        else:
            # Execute non-secret step
            result = execute_navigation_step(nova, parsed_step)
        
        # Update step status
        api_client.update_step_status(
            execution_id=execution['execution_id'],
            step_id=parsed_step.step_id,
            act_id=result.metadata.act_id,
            status='success'
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Step failed: {e}")
        api_client.update_step_status(
            execution_id=execution['execution_id'],
            step_id=step['step_id'],
            status='error',
            logs=str(e)
        )
        return False
```

### Artifact Upload

```python
def upload_artifacts(execution_id, api_client):
    """Upload videos, logs, screenshots to S3"""
    
    artifacts = [
        {
            'type': 'video',
            'path': f'./logs/{execution_id}/recording.webm',
            'content_type': 'video/webm'
        },
        {
            'type': 'log',
            'path': f'./logs/{execution_id}/nova_act.log',
            'content_type': 'text/plain'
        }
    ]
    
    for artifact in artifacts:
        if not os.path.exists(artifact['path']):
            continue
        
        # Get presigned URL
        response = api_client.get_upload_url(
            execution_id=execution_id,
            artifact_type=artifact['type'],
            filename=os.path.basename(artifact['path']),
            content_type=artifact['content_type'],
            size_bytes=os.path.getsize(artifact['path'])
        )
        
        # Upload to S3
        with open(artifact['path'], 'rb') as f:
            requests.put(
                response['upload_url'],
                data=f,
                headers={'Content-Type': artifact['content_type']}
            )
```

---

## UI Changes

### 1. OAuth Client Management
**Location**: Settings → OAuth Clients

**New UI Section**: Display OAuth client credentials for CI/CD setup.

**Information to Show**:
```
┌─────────────────────────────────────────────────────────────┐
│ CI/CD Integration                                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Client ID:     cicd-client-abc123                          │
│ Client Secret: ******************************** [Show]      │
│                                                             │
│ Scopes:        suite:smoke-tests, usecase:login-test      │
│                                                             │
│ Cognito Domain: auth.nova-act-qa-studio.example.com        │
│ API Endpoint:   https://api.nova-act-qa-studio.example.com│
│                                                             │
│ ┌─────────────────────────────────────────────────────┐   │
│ │ Example Usage (GitHub Actions)                      │   │
│ │                                                      │   │
│ │ - name: Run QA Tests                                │   │
│ │   run: |                                            │   │
│ │     docker run nova-act-runner \                    │   │
│ │       --api-endpoint $API_ENDPOINT \                │   │
│ │       --cognito-domain $COGNITO_DOMAIN \            │   │
│ │       --client-id ${{ secrets.CLIENT_ID }} \        │   │
│ │       --client-secret ${{ secrets.CLIENT_SECRET }} \│   │
│ │       --usecase-id login-test-123                   │   │
│ └─────────────────────────────────────────────────────┘   │
│                                                             │
│ [Copy to Clipboard]  [Regenerate Secret]                   │
└─────────────────────────────────────────────────────────────┘
```

### 2. Execution List View
**Enhancement**: Show trigger type and CI metadata.

**New Columns**:
- **Trigger**: Badge showing "Manual", "Scheduled", or "CI/CD"
- **Source**: For CI/CD runs, show commit SHA and branch
- **Pipeline**: Link to CI/CD pipeline run

**Example Row**:
```
┌──────────────┬──────────┬─────────┬──────────────────┬─────────────┐
│ Execution ID │ Status   │ Trigger │ Source           │ Duration    │
├──────────────┼──────────┼─────────┼──────────────────┼─────────────┤
│ exec-456     │ Success  │ [CI/CD] │ main@a1b2c3d     │ 2m 30s      │
│              │          │         │ [View Pipeline]  │             │
└──────────────┴──────────┴─────────┴──────────────────┴─────────────┘
```

### 3. Execution Detail View
**Enhancement**: Show CI/CD metadata section.

**New Section**:
```
┌─────────────────────────────────────────────────────────────┐
│ CI/CD Information                                           │
├─────────────────────────────────────────────────────────────┤
│ Commit:     a1b2c3d4e5f6                                   │
│ Branch:     main                                            │
│ Repository: org/repo                                        │
│ Pipeline:   GitHub Actions #789                             │
│             [View Pipeline Run →]                           │
│                                                             │
│ Triggered by: cicd-client-abc (OAuth Client)               │
│                                                             │
│ Configuration Overrides:                                    │
│ • Stage: production                                         │
│ • Starting URL: https://prod.example.com/login             │
│ • Variables:                                                │
│   - environment = production                                │
│   - api_endpoint = https://api.prod.example.com            │
└─────────────────────────────────────────────────────────────┘
```

### 4. Live View Handling
**Change**: For CI/CD executions, show "N/A" or hide live view section.

```
┌─────────────────────────────────────────────────────────────┐
│ Live View                                                   │
├─────────────────────────────────────────────────────────────┤
│ Not available for CI/CD executions                         │
│                                                             │
│ View recorded video and logs below.                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: API Foundation (Week 1-2)
**Goal**: Build API endpoints and Lambda functions.

**Tasks**:
1. Enhance API Gateway Authorizer for OAuth token support
2. Implement `create_execution_for_runner` Lambda
3. Implement `update_execution_status_runner` Lambda
4. Implement `generate_artifact_upload_url` Lambda
5. Add DynamoDB schema changes (trigger_type, ci_metadata, suite_execution_id)
6. Create GSI for suite execution queries
7. Write unit tests for Lambda functions
8. Deploy to dev environment

**Deliverables**:
- Working API endpoints
- Postman collection for testing
- API documentation

### Phase 2: Runner Development (Week 3-4)
**Goal**: Build Docker container with test execution logic.

**Tasks**:
1. Create runner project structure
2. Implement OAuth authentication module
3. Implement API client module
4. Port test execution logic from worker.py
5. Implement artifact upload logic
6. Create Dockerfile with Nova Act SDK
7. Write integration tests
8. Build and publish Docker image to ECR

**Deliverables**:
- Docker image: `nova-act-runner:v1.0`
- Runner documentation
- Example CI/CD configurations

### Phase 3: UI Updates (Week 5)
**Goal**: Update UI to show CI/CD executions and OAuth client info.

**Tasks**:
1. Add OAuth client credentials display in Settings
2. Update execution list view with trigger type
3. Update execution detail view with CI metadata
4. Handle live view for CI/CD executions
5. Add filtering by trigger type
6. Update frontend tests

**Deliverables**:
- Updated UI components
- User documentation

### Phase 4: Testing & Documentation (Week 6)
**Goal**: End-to-end testing and documentation.

**Tasks**:
1. Test runner in GitHub Actions
2. Test runner in GitLab CI
3. Test runner in Jenkins
4. Load testing (concurrent executions)
5. Write user guide
6. Write troubleshooting guide
7. Create video tutorial

**Deliverables**:
- Tested runner in multiple CI/CD platforms
- Complete documentation
- Tutorial video



---

## Security Considerations

### 1. OAuth Client Secret Management
**Risk**: Client secrets exposed in CI/CD logs or configuration files.

**Mitigation**:
- Store secrets in CI/CD platform's secret management (GitHub Secrets, GitLab CI/CD Variables)
- Never log client secrets
- Support environment variables for credentials
- Provide secret rotation mechanism in UI
- Implement secret expiration (90 days)

### 2. Scope-Based Access Control
**Risk**: Overly permissive scopes allow unauthorized test execution.

**Mitigation**:
- Enforce principle of least privilege
- Validate scopes on every API call
- Audit scope usage in CloudWatch
- Allow scope restrictions per OAuth client
- Document scope requirements clearly

### 3. API Rate Limiting
**Risk**: Malicious or misconfigured runners overwhelm API.

**Mitigation**:
- Implement rate limiting in API Gateway (100 req/min per client)
- Use throttling for artifact uploads (10 concurrent uploads per client)
- Monitor API usage per OAuth client
- Alert on unusual patterns

### 4. Artifact Upload Security
**Risk**: Malicious file uploads or oversized artifacts.

**Mitigation**:
- Validate file size limits before generating presigned URL
- Restrict content types (video/webm, image/png, text/plain, application/json)
- Use presigned URLs with short expiration (15 minutes)
- Scan uploaded files for malware (future enhancement)
- Implement S3 bucket policies to prevent public access

### 5. Token Expiration
**Risk**: Long-lived tokens increase security risk.

**Mitigation**:
- OAuth tokens expire after 1 hour
- Runner must re-authenticate for long-running suites
- Implement token refresh logic in runner
- Log token usage for audit trail

---

## Monitoring & Observability

### CloudWatch Metrics

**Custom Metrics**:
- `RunnerExecutions`: Count of executions triggered by runner
- `RunnerExecutionDuration`: Duration of runner executions
- `RunnerExecutionSuccess`: Success rate of runner executions
- `RunnerExecutionFailure`: Failure rate of runner executions
- `RunnerAPIErrors`: API errors encountered by runner
- `RunnerArtifactUploads`: Count of artifact uploads
- `RunnerArtifactUploadSize`: Size of uploaded artifacts

**Dimensions**:
- `ClientId`: OAuth client ID
- `UsecaseId`: Use case being executed
- `SuiteId`: Suite being executed (if applicable)
- `TriggerType`: Always 'cicd' for runner

### CloudWatch Logs

**Log Groups**:
- `/aws/lambda/create-execution-runner`: Execution creation logs
- `/aws/lambda/update-execution-status-runner`: Status update logs
- `/aws/lambda/generate-artifact-upload-url`: Artifact upload logs
- `/aws/apigateway/runner-api`: API Gateway access logs

**Log Format** (JSON):
```json
{
  "timestamp": "2026-02-11T15:00:00Z",
  "level": "INFO",
  "client_id": "cicd-client-abc",
  "execution_id": "exec-456",
  "usecase_id": "login-test-123",
  "action": "create_execution",
  "duration_ms": 250,
  "status": "success"
}
```

### CloudWatch Alarms

**Critical Alarms**:
- `RunnerAPIErrorRate > 5%`: Alert if API error rate exceeds threshold
- `RunnerExecutionFailureRate > 20%`: Alert if test failure rate is high
- `RunnerAuthenticationFailures > 10/min`: Alert on authentication issues
- `ArtifactUploadFailures > 5/min`: Alert on S3 upload issues

**Warning Alarms**:
- `RunnerExecutionDuration > 10min`: Alert on slow executions
- `RunnerAPILatency > 2s`: Alert on slow API responses

### X-Ray Tracing

**Enable X-Ray** for:
- API Gateway requests
- Lambda function executions
- DynamoDB operations
- S3 operations

**Trace Segments**:
- OAuth authentication
- Execution creation
- Step execution
- Artifact upload

---

## Cost Analysis

### Current State (UI/Scheduled Executions)
**Per Execution**:
- ECS Fargate task: $0.04 (2 vCPU, 4GB RAM, 5 min)
- AgentCore browser: $0.10 (5 min session)
- S3 storage: $0.001 (artifacts)
- DynamoDB: $0.001 (reads/writes)
- **Total**: ~$0.15 per execution

### With CI/CD Runner
**Per Execution**:
- CI/CD compute: $0 (customer's infrastructure)
- API Gateway: $0.0035 (10 API calls)
- Lambda: $0.002 (3 invocations, 1GB, 1s each)
- S3 storage: $0.001 (artifacts)
- DynamoDB: $0.001 (reads/writes)
- **Total**: ~$0.008 per execution

**Cost Savings**: ~95% reduction per CI/CD execution

**Assumptions**:
- 1000 CI/CD executions per month
- Current cost: $150/month
- With runner: $8/month
- **Monthly savings**: $142

**Note**: Savings increase with scale. At 10,000 executions/month, savings = $1,420/month.

---

## Testing Strategy

### Unit Tests

**Lambda Functions**:
- Test `create_execution_for_runner` with valid/invalid inputs
- Test scope validation logic
- Test error handling (usecase not found, invalid scope)
- Test DynamoDB operations (mocked)

**Runner Modules**:
- Test OAuth authentication (mocked Cognito)
- Test API client (mocked responses)
- Test execution logic (mocked Nova Act)
- Test artifact upload (mocked S3)

### Integration Tests

**API Endpoints**:
- Test end-to-end execution creation
- Test status updates
- Test artifact upload flow
- Test OAuth token validation
- Test scope enforcement

**Runner**:
- Test runner with real API (dev environment)
- Test execution of simple usecase
- Test execution of suite
- Test artifact upload to S3
- Test error handling (API failures, network issues)

### End-to-End Tests

**CI/CD Platforms**:
- GitHub Actions: Test runner in workflow
- GitLab CI: Test runner in pipeline
- Jenkins: Test runner in job
- CircleCI: Test runner in workflow

**Test Scenarios**:
- Single usecase execution (success)
- Single usecase execution (failure)
- Suite execution (all pass)
- Suite execution (some fail)
- Network failure during execution
- API rate limiting
- Large artifact upload (video)

### Load Tests

**Scenarios**:
- 10 concurrent runner executions
- 50 concurrent runner executions
- 100 concurrent runner executions

**Metrics**:
- API latency (p50, p95, p99)
- Lambda cold start time
- DynamoDB throttling
- S3 upload throughput

---

## Rollout Plan

### Phase 1: Internal Testing (Week 1)
**Audience**: Development team only

**Activities**:
- Deploy to dev environment
- Test with sample usecases
- Validate OAuth flow
- Test artifact uploads
- Fix critical bugs

**Success Criteria**:
- Runner executes successfully in dev
- All API endpoints working
- Artifacts uploaded to S3
- No critical bugs

### Phase 2: Beta Testing (Week 2-3)
**Audience**: Selected customers (5-10)

**Activities**:
- Deploy to staging environment
- Provide beta access to customers
- Collect feedback
- Monitor usage and errors
- Iterate on documentation

**Success Criteria**:
- 80% of beta users successfully integrate runner
- No P0/P1 bugs reported
- Positive feedback on usability
- Documentation is clear

### Phase 3: General Availability (Week 4)
**Audience**: All customers

**Activities**:
- Deploy to production
- Announce feature in release notes
- Publish blog post and tutorial
- Monitor adoption metrics
- Provide support

**Success Criteria**:
- 20% of customers adopt runner in first month
- 95% success rate for runner executions
- No production incidents
- Positive customer feedback

---

## Success Metrics

### Adoption Metrics
- **OAuth Clients Created**: Number of OAuth clients created for CI/CD
- **Runner Executions**: Number of executions triggered by runner
- **Active CI/CD Users**: Number of unique OAuth clients used per week
- **Adoption Rate**: % of customers using runner (target: 30% in 3 months)

### Performance Metrics
- **Execution Success Rate**: % of runner executions that succeed (target: >95%)
- **API Latency**: p95 latency for API calls (target: <500ms)
- **Artifact Upload Success**: % of artifact uploads that succeed (target: >99%)
- **Runner Execution Time**: Average duration of runner executions (target: <5min)

### Business Metrics
- **Cost Savings**: Total AWS cost savings from runner vs ECS (target: $1000/month)
- **Customer Satisfaction**: NPS score for CI/CD feature (target: >8)
- **Support Tickets**: Number of support tickets related to runner (target: <5/month)

---

## Future Enhancements

### v1.1: Parallel Execution
**Description**: Run multiple tests in parallel within single runner instance.

**Benefits**:
- Faster suite execution
- Better resource utilization
- Reduced CI/CD pipeline time

**Implementation**: Use Python multiprocessing or threading.

### v1.2: Test Result Caching
**Description**: Cache test results and skip unchanged tests.

**Benefits**:
- Faster feedback for incremental changes
- Reduced execution time
- Lower costs

**Implementation**: Hash test definition + dependencies, compare with previous run.

### v1.3: Binary Distribution
**Description**: Provide standalone binary (Go or Rust) instead of Docker.

**Benefits**:
- Faster startup (no Docker overhead)
- Smaller download size
- Easier installation

**Implementation**: Rewrite runner in Go, bundle Nova Act SDK.

### v1.4: Real-Time Streaming
**Description**: Stream test execution logs to UI in real-time.

**Benefits**:
- Better debugging experience
- Immediate feedback
- Live progress tracking

**Implementation**: WebSocket connection from runner to API Gateway.

### v1.5: Test Sharding
**Description**: Split large test suites across multiple runner instances.

**Benefits**:
- Faster suite execution
- Better parallelization
- Scalability

**Implementation**: Coordinator service distributes tests to runners.

---

## Appendix

### A. Example CI/CD Configurations

#### GitHub Actions
```yaml
name: QA Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  qa-tests:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
      
      - name: Run Login Test
        run: |
          docker run \
            --rm \
            -e NOVA_ACT_API_ENDPOINT=${{ secrets.API_ENDPOINT }} \
            -e NOVA_ACT_COGNITO_DOMAIN=${{ secrets.COGNITO_DOMAIN }} \
            -e NOVA_ACT_CLIENT_ID=${{ secrets.CLIENT_ID }} \
            -e NOVA_ACT_CLIENT_SECRET=${{ secrets.CLIENT_SECRET }} \
            nova-act-runner:latest \
            --usecase-id login-test-123 \
            --commit-sha ${{ github.sha }} \
            --branch ${{ github.ref_name }} \
            --pipeline-url ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
      
      - name: Run Smoke Test Suite
        run: |
          docker run \
            --rm \
            -e NOVA_ACT_API_ENDPOINT=${{ secrets.API_ENDPOINT }} \
            -e NOVA_ACT_COGNITO_DOMAIN=${{ secrets.COGNITO_DOMAIN }} \
            -e NOVA_ACT_CLIENT_ID=${{ secrets.CLIENT_ID }} \
            -e NOVA_ACT_CLIENT_SECRET=${{ secrets.CLIENT_SECRET }} \
            nova-act-runner:latest \
            --suite-id smoke-tests \
            --commit-sha ${{ github.sha }} \
            --branch ${{ github.ref_name }}
```

#### GitLab CI
```yaml
stages:
  - test

qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run
        --rm
        -e NOVA_ACT_API_ENDPOINT=$API_ENDPOINT
        -e NOVA_ACT_COGNITO_DOMAIN=$COGNITO_DOMAIN
        -e NOVA_ACT_CLIENT_ID=$CLIENT_ID
        -e NOVA_ACT_CLIENT_SECRET=$CLIENT_SECRET
        nova-act-runner:latest
        --usecase-id login-test-123
        --commit-sha $CI_COMMIT_SHA
        --branch $CI_COMMIT_BRANCH
        --pipeline-url $CI_PIPELINE_URL
  only:
    - main
    - merge_requests
```

#### Jenkins
```groovy
pipeline {
    agent any
    
    environment {
        API_ENDPOINT = credentials('nova-act-api-endpoint')
        COGNITO_DOMAIN = credentials('nova-act-cognito-domain')
        CLIENT_ID = credentials('nova-act-client-id')
        CLIENT_SECRET = credentials('nova-act-client-secret')
    }
    
    stages {
        stage('QA Tests') {
            steps {
                script {
                    docker.image('nova-act-runner:latest').inside {
                        sh """
                            nova-act-runner \
                                --api-endpoint ${API_ENDPOINT} \
                                --cognito-domain ${COGNITO_DOMAIN} \
                                --client-id ${CLIENT_ID} \
                                --client-secret ${CLIENT_SECRET} \
                                --usecase-id login-test-123 \
                                --commit-sha ${GIT_COMMIT} \
                                --branch ${GIT_BRANCH} \
                                --pipeline-url ${BUILD_URL}
                        """
                    }
                }
            }
        }
    }
}
```

### B. Troubleshooting Guide

#### Issue: Authentication Failed
**Symptoms**: Runner exits with code 2, error message "Authentication failed"

**Causes**:
- Invalid client_id or client_secret
- Expired OAuth client
- Incorrect Cognito domain

**Solutions**:
1. Verify client_id and client_secret in UI (Settings → OAuth Clients)
2. Check Cognito domain matches deployment
3. Regenerate client secret if expired
4. Verify scopes are correct

#### Issue: Insufficient Scopes
**Symptoms**: Runner exits with code 2, error message "403 Forbidden"

**Causes**:
- OAuth client doesn't have required scopes
- Usecase/suite scope mismatch

**Solutions**:
1. Check OAuth client scopes in UI
2. Add required scopes: `usecase:{usecase_id}` or `suite:{suite_id}`
3. Regenerate OAuth client with correct scopes

#### Issue: Test Execution Failed
**Symptoms**: Runner exits with code 1, test marked as failed

**Causes**:
- Test assertion failed
- Website unavailable
- Network timeout
- Nova Act error

**Solutions**:
1. Check execution logs in UI
2. Review video recording for visual debugging
3. Verify website is accessible
4. Check test steps for errors
5. Review Nova Act logs

#### Issue: Artifact Upload Failed
**Symptoms**: Test succeeds but artifacts missing in UI

**Causes**:
- S3 upload timeout
- Network issues
- File size exceeds limit
- Invalid presigned URL

**Solutions**:
1. Check runner logs for upload errors
2. Verify S3 bucket permissions
3. Check file size (max 500MB for videos)
4. Retry execution

---

## Glossary

- **CI/CD**: Continuous Integration / Continuous Deployment
- **OAuth M2M**: OAuth Machine-to-Machine authentication
- **Runner**: Docker container that executes tests in CI/CD environment
- **Execution**: Single test run instance
- **Suite Execution**: Batch execution of multiple tests
- **Artifact**: Test output file (video, screenshot, log)
- **Scope**: OAuth permission to access specific resources
- **Trigger Type**: How execution was initiated (manual, scheduled, cicd)
- **Act ID**: Nova Act action identifier
- **Presigned URL**: Temporary S3 upload URL with embedded credentials

---

## Document History

| Version | Date       | Author       | Changes                          |
|---------|------------|--------------|----------------------------------|
| 1.0     | 2026-02-11 | Product Team | Initial design document          |

---

## Approval

| Role                | Name | Signature | Date |
|---------------------|------|-----------|------|
| Product Manager     |      |           |      |
| Engineering Lead    |      |           |      |
| Security Lead       |      |           |      |
| DevOps Lead         |      |           |      |

