# Feature Specification: CI/CD Test Runner

## Document Information
- **Feature Name**: CI/CD Test Runner
- **Version**: 1.0
- **Date**: 2026-02-16
- **Status**: Design Phase
- **Author**: Product Team

---

## Executive Summary

Enable developers to execute Nova Act QA Studio test suites within their CI/CD pipelines through a containerized runner that authenticates via OAuth, executes tests locally with a bundled browser, and reports results back to the platform.

The runner is a Docker container that pulls test suite definitions via API, executes all use cases in parallel using Nova Act SDK with a local Chromium browser, uploads artifacts (videos, traces, logs) to S3 via presigned URLs, and exits with appropriate status codes to control CI/CD workflow success/failure.

### Key Capabilities
- Execute complete test suites from CI/CD pipelines (GitHub Actions, GitLab CI, Jenkins, etc.)
- OAuth client credentials authentication (machine-to-machine)
- Local parallel test execution with Nova Act SDK and bundled browser
- Base URL override for environment-specific testing (staging → production)
- Variable and secret override via CLI arguments
- Artifact upload (videos, traces, logs) via presigned S3 URLs
- Exit code-based CI/CD workflow control (0 = success, non-zero = failure)
- Comprehensive execution summary output for CI/CD logs

---

## Problem Statement

### Current State
- Test suites can only be executed from the web UI
- Execution happens exclusively in ECS Fargate with remote AgentCore browsers
- No integration with CI/CD pipelines
- Manual test execution workflow
- No way to override URLs or variables for different environments

### Limitations
- Cannot integrate with automated deployment pipelines
- No way to gate deployments on test results
- Developers must context-switch to web UI for test execution
- Cannot run tests in PR validation workflows
- No automated regression testing in CI/CD
- Cannot test different environments (staging vs production) with same test suite
- Manual intervention required for every test run

### User Impact
- DevOps engineers cannot automate QA validation
- Slower feedback loops in development process
- Higher risk of production bugs slipping through
- Reduced confidence in automated deployments
- Increased manual testing burden
- Cannot validate deployments before promoting to production

---

## Goals & Success Criteria

### Primary Goals
1. Enable test suite execution from any CI/CD platform via Docker container
2. Provide seamless OAuth client credentials authentication
3. Execute all use cases in parallel locally with Nova Act SDK
4. Support base URL override for environment-specific testing
5. Support variable and secret override via CLI arguments
6. Upload artifacts (videos, traces, logs) to S3 via API
7. Control CI/CD workflow with exit codes based on test results
8. Provide comprehensive execution summary for CI/CD logs

### Success Metrics
- Runner successfully executes test suites in CI/CD environment
- OAuth authentication works without user intervention
- All use cases execute in parallel with local browser
- Base URL override correctly replaces domain in all URLs
- Variable overrides take precedence over usecase variables and secrets
- Artifacts uploaded successfully to S3 via presigned URLs
- Exit codes correctly reflect test outcomes (0 = pass, 1+ = fail/error)
- Execution records appear in platform UI with trigger type "ci_runner"

### Non-Goals (Out of Scope for v1.0)
- Modifying existing UI-triggered execution flow
- Changing ECS-based execution architecture
- Supporting non-Docker runner distributions
- Real-time streaming of test execution to UI
- Live view functionality for CI/CD runs
- Custom concurrency control (all use cases run in parallel)
- Webhook notifications on completion
- Retry logic for failed tests

---

## Key Design Decisions

### 1. Local Execution Model with Bundled Browser
**Decision**: Runner executes tests locally using Nova Act SDK with bundled Chromium browser in the CI/CD environment.

**Rationale**:
- CI/CD environments already have compute resources
- Reduces AWS costs (no ECS tasks or AgentCore browsers for CI/CD runs)
- Faster feedback (no ECS task startup time, no remote browser provisioning)
- Simpler architecture (no orchestration needed)
- Better isolation (each CI/CD job is independent)
- Nova Act SDK includes Chromium browser out-of-the-box

**Trade-offs**:
- Runner container size ~500MB with browser and dependencies
- No live view capability (acceptable for CI/CD use case)
- CI/CD environment must support Docker
- Requires sufficient memory/CPU in CI/CD runners

**Implementation Details**:
- Use Nova Act SDK's local browser mode
- Always run in headless mode for CI/CD
- Container includes Python 3.11+ with Nova Act SDK pre-installed
- No AWS service access required (all communication via API)

**Alternatives Considered**:
- **Remote ECS execution**: Rejected due to cost, latency, and complexity
- **Lambda-based runner**: Rejected due to 15-minute timeout and cold start issues

---

### 2. Parallel Execution of All Use Cases
**Decision**: All use cases in a test suite execute simultaneously in parallel.

**Rationale**:
- Faster overall execution time
- Better resource utilization in CI/CD environment
- Aligns with modern CI/CD practices
- Provides complete test results even if some tests fail

**Trade-offs**:
- Higher memory/CPU requirements during execution
- Potential for resource contention if too many use cases
- More complex error handling and result aggregation

**Implementation Details**:
- Use Python `asyncio` or `concurrent.futures` for parallel execution
- Each use case gets its own Nova Act session
- Continue execution even if individual tests fail
- Aggregate results at the end for summary report

**Alternatives Considered**:
- **Sequential execution**: Rejected due to slow feedback loops
- **Configurable concurrency**: Deferred to v2.0 for simplicity

---

### 3. API-Only Communication Pattern
**Decision**: All communication between runner and platform happens through REST API endpoints. No direct AWS service access.

**Rationale**:
- Keeps runner AWS-agnostic (can run anywhere Docker runs)
- Simplifies authentication (single OAuth token)
- Reduces security surface area (no AWS credentials needed)
- Easier to test and debug
- Consistent with existing architecture

**Trade-offs**:
- API becomes critical path for runner operation
- Potential latency for artifact uploads (mitigated by presigned URLs)
- API rate limiting considerations

**Implementation Details**:
- OAuth client credentials flow for authentication
- Presigned S3 URLs for artifact uploads (bypass API for large files)
- Reuse existing endpoints where possible
- Token caching and refresh logic in runner

**Alternatives Considered**:
- **Direct AWS access**: Rejected to avoid credential management complexity
- **Hybrid approach**: Rejected for consistency and simplicity

---

### 4. Base URL Override Strategy
**Decision**: Override domain/origin only, preserving URL paths and query parameters. Applied at execution record creation time.

**Rationale**:
- Most common use case is environment switching (staging → production)
- Preserves test logic while changing target environment
- Simple to understand and implement
- Reduces risk of breaking tests with incorrect URL manipulation
- Applied once at execution creation, not at runtime

**Trade-offs**:
- Cannot override full URLs (only domain)
- Assumes consistent URL structure across environments
- May not work for drastically different environments

**Implementation Details**:
- Parse starting URL from usecase definition
- Extract path and query parameters
- Replace origin with base_url from CLI
- Store modified URL in execution record's `starting_url` field
- Worker reads `starting_url` from execution record (no runtime changes needed)
- Example: `https://staging.example.com/login?foo=bar` + `--base-url https://prod.example.com` → `https://prod.example.com/login?foo=bar`

**Alternatives Considered**:
- **Full URL override**: Rejected as too complex and error-prone
- **Path-based override**: Rejected as less common use case
- **Runtime URL transformation**: Rejected to avoid worker changes

---

### 5. Variable Override Precedence
**Decision**: CLI arguments > usecase variables > secrets (highest to lowest priority). Applied at execution record creation time.

**Rationale**:
- CLI arguments are most specific to the current execution
- Usecase variables are defaults defined by test author
- Secrets are fallback for sensitive data
- Clear and predictable precedence rules
- Applied once at execution creation, stored in execution variables

**Trade-offs**:
- CLI arguments can override secrets (security consideration)
- Requires careful documentation to avoid confusion
- Missing variables cause immediate failure (no silent defaults)

**Implementation Details**:
1. Load secrets from Secrets Manager for the usecase
2. Load usecase variables from definition
3. Apply CLI argument overrides
4. Merge all into execution variables record
5. Store in DynamoDB as `EXECUTION_VARIABLES`
6. Validate all template variables are resolved
7. Error immediately if any `{{variable}}` remains unresolved
8. Worker reads variables from execution record (no runtime resolution needed)

**Alternatives Considered**:
- **Secrets always win**: Rejected as less flexible for testing
- **Silent defaults**: Rejected as error-prone
- **Runtime variable resolution**: Rejected to avoid worker changes

---

### 6. Artifact Upload via Presigned URLs
**Decision**: Runner uploads artifacts directly to S3 using presigned URLs obtained from API. Single endpoint for execution-level artifacts with type parameter, separate endpoint for step-level artifacts.

**Rationale**:
- Bypasses API layer for large file uploads (videos can be 100MB+)
- Reduces API Gateway payload limits and Lambda execution time
- Faster uploads with direct S3 access
- Standard AWS pattern for large file uploads
- Single execution-level endpoint is cleaner and more extensible
- Type parameter allows easy addition of new artifact types

**Trade-offs**:
- Requires two API calls per artifact (get URL, then upload)
- Presigned URL expiration handling
- More complex error handling

**Implementation Details**:
- Single endpoint for execution-level artifacts (recording, logs)
- Type specified in request body: `{ "type": "recording" | "logs" }`
- Separate endpoint for step-level artifacts (screenshots, traces)
- Retry logic for failed uploads
- Filename and content-type provided in request body

**Alternatives Considered**:
- **Upload via API**: Rejected due to size limits and performance
- **Direct S3 access with credentials**: Rejected to avoid credential management
- **Separate endpoints per artifact type**: Rejected in favor of single extensible endpoint

---

### 7. Exit Code Strategy
**Decision**: Use standard exit codes to control CI/CD workflow.

**Rationale**:
- Standard practice for CI/CD tools
- Simple integration with any CI/CD platform
- Clear success/failure indication
- Enables automated deployment gating

**Exit Codes**:
- `0`: All tests passed
- `1`: One or more tests failed
- `2`: Runner error (auth failed, network issue, invalid config, etc.)

**Implementation Details**:
- Track test results during execution
- Aggregate results at the end
- Exit with appropriate code
- Print summary to stdout before exit

**Alternatives Considered**:
- **Always exit 0**: Rejected as defeats purpose of CI/CD integration
- **Detailed exit codes**: Deferred to v2.0 for simplicity

---

## Architecture Overview

### High-Level Flow

```
CI/CD Pipeline → Docker Runner → OAuth Auth → API Gateway → Lambda Functions
                      ↓                                           ↓
                 Nova Act SDK                              DynamoDB (execution records)
                      ↓                                           ↓
                Local Browser                           S3 (presigned URLs for artifacts)
                      ↓
                  Artifacts → S3 Upload
```

### Component Responsibilities

**Docker Runner (Python CLI)**:
- Authenticate with OAuth client credentials
- Fetch test suite definition via API (required starting point)
- Get all usecase IDs from test suite
- Create execution records for ALL use cases in suite (via API)
- Create suite execution record linking all usecase executions
- Apply base URL and variable overrides to each usecase execution
- Execute all use cases in parallel with Nova Act SDK (locally, not ECS)
- Upload artifacts (video, trace, logs) to S3 for each execution
- Update individual execution status via API as tests complete
- Update suite execution status when all complete
- Print summary and exit with appropriate code

**API Layer (Existing + Minor Extensions)**:
- Authenticate OAuth clients
- Serve test suite and usecase definitions
- Create execution records without triggering ECS tasks
- Generate presigned S3 URLs for artifact uploads
- Accept execution status updates
- Record trigger type as "ci_runner"

**Platform Backend (Minimal Changes)**:
- Separate execution record creation from ECS task triggering
- Support "ci_runner" trigger type (no ECS task spawned)
- Link suite executions to individual usecase executions
- Display CI/CD executions in UI with appropriate badge/indicator

---

## Key Architectural Change: Execution Record Creation

### Current Flow (UI/Scheduled Execution)
1. User triggers execution via UI or schedule
2. `execute_usecase` Lambda creates execution record
3. Lambda copies usecase data (steps, hooks, variables, headers) to execution
4. Lambda spawns ECS task with execution_id
5. ECS worker executes test and updates status

### New Flow (CI/CD Runner)
1. Runner starts with test suite ID (required CLI argument)
2. Runner calls `POST /api/test-suites/{id}/execute` with trigger_type="ci_runner" and overrides
3. API creates suite execution record
4. API creates execution records for ALL use cases in suite with overrides applied:
   - `starting_url` - Overridden with base URL transformation
   - `variables` - Merged with CLI variable overrides
   - `region` - Overridden if specified
   - `model_id` - Overridden if specified
5. API returns suite_execution_id and list of all execution_ids (no ECS tasks spawned)
6. Runner executes all use cases in parallel locally with Nova Act SDK
7. Runner updates individual execution status via API as tests complete
8. Runner updates suite execution status when all tests complete
9. Runner uploads artifacts via presigned URLs
10. Runner prints summary and exits with appropriate code

### Required New Endpoint
`POST /api/test-suites/{id}/execute` must:
- Accept trigger_type="ci_runner" in request body
- Accept overrides: base_url, variables, region, model_id
- Create suite execution record
- Create execution records for all use cases in suite
- Apply base URL transformation to each usecase's starting_url
- Merge variables for each usecase execution
- Link all usecase executions to suite execution
- Return suite_execution_id and array of execution_ids
- Skip ECS task creation for all executions

### Data Overrides Required
Based on worker implementation, these fields must be overridable:
- **`starting_url`**: Worker reads this to initialize Nova Act browser
- **`variables`**: Worker uses TemplateParser with execution variables
- **`region`**: Worker uses this for browser creation and management
- **`model_id`**: Worker uses this for Nova Act GA service
- **`created_at`**: Auto-generated, used by TemplateParser for UniqueID

---

## API Requirements

### Existing Endpoints (Reuse)
- `GET /test-suites/{id}` - Fetch test suite metadata and usecase list
- `GET /usecase/{id}` - Fetch usecase definition
- `GET /usecase/{id}/secrets` - Fetch usecase secrets
- `GET /usecase/{id}/variables` - Fetch usecase variables

### New/Modified Endpoints

#### `POST /test-suites/{id}/execute`
Execute test suite (CI/CD runner entry point)

**When trigger_type="ci_runner"**:
- Creates suite execution record
- Creates execution records for ALL use cases in suite (no ECS tasks spawned)
- Applies overrides to each execution record
- Returns suite_execution_id and list of execution_ids

**Request Body**:
```json
{
  "trigger_type": "ci_runner",
  "base_url": "https://example.com",  // Optional: Override base URL
  "variables": {                       // Optional: Override variables
    "key": "value"
  },
  "region": "us-east-1",              // Optional: Override region
  "model_id": "us.anthropic.claude-3-5-sonnet-20241022-v2:0"  // Optional: Override model
}
```

**Response**:
```json
{
  "suite_execution_id": "uuid",
  "execution_ids": [
    {
      "usecase_id": "uuid",
      "execution_id": "uuid"
    }
  ]
}
```

#### `PATCH /usecase/{id}/executions/{executionId}/status`
Update execution status

**Request Body**:
```json
{
  "status": "running" | "completed" | "failed",
  "error_message": "string"  // Optional, for failed status
}
```

**Response**:
```json
{
  "success": true
}
```

#### `POST /usecase/{id}/executions/{executionId}/artifacts`
Get presigned S3 URL for execution-level artifacts

**Request Body**:
```json
{
  "type": "recording" | "logs",
  "filename": "string",
  "content_type": "string"
}
```

**Response**:
```json
{
  "upload_url": "https://s3.amazonaws.com/...",
  "artifact_id": "uuid"
}
```

#### `POST /usecase/{id}/executions/{executionId}/steps/{stepId}/artifacts`
Get presigned S3 URL for step-level artifacts

**Request Body**:
```json
{
  "filename": "string",
  "content_type": "string"
}
```

**Response**:
```json
{
  "upload_url": "https://s3.amazonaws.com/...",
  "artifact_id": "uuid"
}
```

### OAuth Scopes Required
- `api/suite.read` - Read test suite definitions
- `api/suite.write` - Execute test suites and update suite execution status
- `api/usecase.read` - Read usecase definitions, variables, secrets
- `api/execution.read` - Read execution records and status
- `api/execution.write` - Update execution status and upload artifacts

---

## Data Model Changes

### Execution Record Extensions

**New field**: `trigger_type`
- Values: `"manual"` | `"scheduled"` | `"ci_runner"`
- Used to display execution source in UI

**New field**: `suite_execution_id` (optional)
- Links individual usecase execution to parent suite execution
- Enables suite-level status aggregation

### Test Suite Execution Record

**Existing fields** (no changes needed):
- `suite_id` - Test suite identifier
- `status` - Overall suite status
- `started_at` - Execution start time
- `completed_at` - Execution completion time
- `usecase_executions` - List of execution IDs

---

## Implementation Plan

### Work Package 1: API Extensions (Week 1)
**Goal**: Prepare backend to support CI/CD runner

**Tasks**:
- [ ] Modify `execute_usecase` Lambda to support "create-only" mode for ci_runner trigger
- [ ] Skip ECS task creation when trigger_type="ci_runner"
- [ ] Add `trigger_type` field to execution records
- [ ] Modify `PUT /api/executions/{id}/status` to accept trigger_type
- [ ] Implement `POST /api/executions/{id}/artifacts/recording` endpoint for presigned URLs
- [ ] Implement `POST /api/executions/{id}/artifacts/logs` endpoint for presigned URLs
- [ ] Implement `POST /api/executions/{id}/steps/{step_id}/artifacts` endpoint for presigned URLs
- [ ] Add OAuth scope validation for test-suites and usecases
- [ ] Update DynamoDB schema to support new fields
- [ ] Write unit tests for new/modified endpoints

**Deliverables**:
- Modified Lambda functions deployed
- Execution records created without ECS tasks for ci_runner
- API documentation updated
- Test coverage for new functionality

**Dependencies**: None

---

### Work Package 2: Runner Core (Week 2)
**Goal**: Build basic runner that can authenticate, fetch data, and create execution records

**Tasks**:
- [ ] Create Python CLI project structure
- [ ] Implement OAuth client credentials flow
- [ ] Implement token caching and refresh logic
- [ ] Build API client module (fetch suite, usecases, secrets, variables)
- [ ] Implement execution record creation for suite and all use cases
- [ ] Implement CLI argument parsing (suite-id, base-url, var overrides)
- [ ] Implement variable resolution and validation logic
- [ ] Write unit tests for core modules

**Deliverables**:
- Python CLI that can authenticate and fetch test data
- Execution records created via API for all use cases in suite
- Variable override logic working
- Error handling for missing variables

**Dependencies**: Work Package 1 (API extensions)

---

### Work Package 3: Execution Engine (Week 3)
**Goal**: Execute use cases with Nova Act SDK

**Tasks**:
- [ ] Integrate Nova Act SDK
- [ ] Implement base URL override logic
- [ ] Build parallel execution orchestrator (asyncio/concurrent.futures)
- [ ] Implement execution status updates via API
- [ ] Handle test failures gracefully (continue other tests)
- [ ] Implement result aggregation
- [ ] Write integration tests with mock API

**Deliverables**:
- Runner can execute use cases in parallel
- Base URL override working correctly
- Status updates sent to API

**Dependencies**: Work Package 2 (Runner core)

---

### Work Package 4: Artifact Management (Week 4)
**Goal**: Upload artifacts to S3

**Tasks**:
- [ ] Implement artifact capture (video, trace, logs)
- [ ] Build presigned URL fetcher for both execution and step endpoints
- [ ] Implement S3 upload with retry logic
- [ ] Handle upload failures gracefully
- [ ] Implement artifact association with execution and steps
- [ ] Write tests for artifact upload flow

**Deliverables**:
- Artifacts uploaded to S3 successfully via both endpoints
- Artifacts visible in platform UI
- Robust error handling for upload failures

**Dependencies**: Work Package 3 (Execution engine)

---

### Work Package 5: Docker Container (Week 5)
**Goal**: Package runner as Docker container

**Tasks**:
- [ ] Create Dockerfile with Python 3.11 base
- [ ] Install Nova Act SDK and dependencies
- [ ] Configure headless browser mode
- [ ] Optimize container size
- [ ] Create entrypoint script
- [ ] Test container in local Docker environment
- [ ] Write container build documentation

**Deliverables**:
- Docker container (~500MB) with runner
- Container runs successfully in Docker
- Build instructions documented

**Dependencies**: Work Package 4 (Artifact management)

---

### Work Package 6: Output & Exit Codes (Week 5)
**Goal**: Implement summary output and exit codes

**Tasks**:
- [ ] Design summary output format (table/JSON)
- [ ] Implement summary printer
- [ ] Implement exit code logic (0/1/2)
- [ ] Add verbose logging mode
- [ ] Test exit codes in CI/CD scenarios
- [ ] Write documentation for output format

**Deliverables**:
- Clear summary output printed to stdout
- Exit codes working correctly
- CI/CD integration examples

**Dependencies**: Work Package 3 (Execution engine)

---

### Work Package 7: Documentation (Week 6)
**Goal**: Comprehensive user documentation

**Tasks**:
- [ ] Write installation guide
- [ ] Document all CLI flags and options
- [ ] Create CI/CD integration examples (GitHub Actions, GitLab CI, Jenkins)
- [ ] Write troubleshooting guide
- [ ] Create architecture diagrams
- [ ] Document OAuth client setup process
- [ ] Write best practices guide
- [ ] Create video tutorial (optional)

**Deliverables**:
- Complete documentation in README
- CI/CD integration examples
- Troubleshooting guide

**Dependencies**: Work Package 5 (Docker container)

---

### Work Package 8: Testing & Validation (Week 6)
**Goal**: End-to-end testing and validation

**Tasks**:
- [ ] Test runner in GitHub Actions
- [ ] Test runner in GitLab CI
- [ ] Test runner in Jenkins
- [ ] Load testing (large test suites)
- [ ] Error scenario testing (network failures, auth failures, etc.)
- [ ] Performance benchmarking
- [ ] Security review

**Deliverables**:
- Runner validated in multiple CI/CD platforms
- Performance benchmarks documented
- Security review completed

**Dependencies**: Work Package 7 (Documentation)

---

## Parallel Work Streams

**Stream A (Backend)**: WP1 → WP4 (artifact API)
**Stream B (Runner)**: WP2 → WP3 → WP4 → WP5 → WP6
**Stream C (Documentation)**: WP7 (can start after WP5)
**Stream D (Testing)**: WP8 (final validation)

**Critical Path**: WP1 → WP2 → WP3 → WP4 → WP5 → WP8

---

## Security Considerations

### Authentication & Authorization
- OAuth client credentials stored as environment variables (not in code)
- Token refresh logic to handle expiration
- Scope-based access control enforced by API
- No AWS credentials required in runner

### Secret Handling
- Secrets fetched via API (encrypted in transit)
- CLI variable overrides can override secrets (documented security consideration)
- Secrets never logged or printed to stdout
- Environment variables cleared after execution

### Container Security
- Base image from trusted source (official Python image)
- Regular security updates for dependencies
- No privileged mode required
- Read-only filesystem where possible

### Network Security
- All communication over HTTPS
- Certificate validation enabled
- No inbound connections required
- Outbound only to API endpoint and S3

---

## Runner Configuration Reference

### Environment Variables (Required)
- `OAUTH_CLIENT_ID` - OAuth client ID from platform
- `OAUTH_CLIENT_SECRET` - OAuth client secret from platform  
- `OAUTH_TOKEN_ENDPOINT` - Cognito token endpoint URL (e.g., `https://<domain>.auth.<region>.amazoncognito.com/oauth2/token`)
- `API_ENDPOINT` - Platform API endpoint URL

### CLI Arguments
- `--suite-id <id>` - **Required**: Test suite ID to execute (runner always starts from suite)
- `--base-url <url>` - Optional: Override base URL for all use cases in suite
- `--var <key>=<value>` - Optional: Override variable for all use cases (repeatable)
- `--verbose` - Optional: Enable verbose logging
- `--timeout <seconds>` - Optional: Global timeout (default: 3600)
- `--help` - Show help message

### Example Invocation
Docker container run with environment variables for authentication, suite ID specified, base URL override for production environment, and variable overrides for username and API key.

---

## Output Format

### Summary Table
```
╔════════════════════════════════════════════════════════════╗
║              Nova Act QA Studio - CI/CD Runner             ║
╠════════════════════════════════════════════════════════════╣
║ Suite: Login Flow Tests (suite-789)                       ║
║ Started: 2026-02-16 12:00:00                              ║
║ Completed: 2026-02-16 12:05:23                            ║
║ Duration: 5m 23s                                           ║
╠════════════════════════════════════════════════════════════╣
║ Use Case                          Status      Duration     ║
╠════════════════════════════════════════════════════════════╣
║ Login with valid credentials      ✓ PASSED    45s         ║
║ Login with invalid password       ✓ PASSED    32s         ║
║ Password reset flow               ✗ FAILED    1m 12s      ║
║ Two-factor authentication         ✓ PASSED    58s         ║
╠════════════════════════════════════════════════════════════╣
║ Total: 4  |  Passed: 3  |  Failed: 1  |  Success: 75%    ║
╚════════════════════════════════════════════════════════════╝

Exit code: 1 (tests failed)
```

### Verbose Logging
```
[12:00:00] INFO: Authenticating with OAuth client credentials...
[12:00:01] INFO: Successfully authenticated
[12:00:01] INFO: Fetching test suite: suite-789
[12:00:02] INFO: Found 4 use cases in suite
[12:00:02] INFO: Applying base URL override: https://production.example.com
[12:00:02] INFO: Applying variable overrides: username, api_key
[12:00:02] INFO: Starting parallel execution of 4 use cases...
[12:00:02] INFO: [usecase-1] Starting execution: Login with valid credentials
[12:00:02] INFO: [usecase-2] Starting execution: Login with invalid password
[12:00:02] INFO: [usecase-3] Starting execution: Password reset flow
[12:00:02] INFO: [usecase-4] Starting execution: Two-factor authentication
[12:00:47] INFO: [usecase-1] Completed: PASSED (45s)
[12:00:47] INFO: [usecase-1] Uploading artifacts...
[12:01:34] INFO: [usecase-2] Completed: PASSED (32s)
[12:02:14] ERROR: [usecase-3] Failed: Assertion failed at step 5
[12:02:14] INFO: [usecase-3] Uploading artifacts...
[12:03:00] INFO: [usecase-4] Completed: PASSED (58s)
[12:05:23] INFO: All executions completed
[12:05:23] INFO: Generating summary...
```

---

## CI/CD Integration Examples

### GitHub Actions
Runner executed as Docker container with secrets stored in GitHub repository settings. OAuth credentials (client ID, client secret, token endpoint) and API endpoint configured as repository secrets. Triggered on push to main branch and pull requests. Base URL set to staging environment with variable overrides passed as CLI arguments.

### GitLab CI
Runner executed in test stage using Docker-in-Docker service. OAuth credentials (client ID, client secret, token endpoint) and API endpoint stored as GitLab CI/CD variables (masked and protected). Triggered on main branch and merge requests. Environment-specific variables passed to runner.

### Jenkins
Runner executed in pipeline stage using Docker agent. Credentials stored in Jenkins credential store and injected as environment variables. Base URL and variables passed as CLI arguments from Jenkins configuration. Pipeline configured to fail build on non-zero exit code.

---

## Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| CI/CD environment lacks resources | High | Medium | Document minimum requirements (4GB RAM, 2 CPU) |
| OAuth token expiration during long runs | Medium | Low | Implement token refresh logic |
| Network failures during execution | High | Medium | Retry logic for API calls and uploads |
| Parallel execution resource contention | Medium | High | Document resource requirements, consider concurrency limits in v2.0 |
| Large test suites timeout | High | Low | Implement global timeout with clear error message |
| Artifact upload failures | Medium | Medium | Retry logic with exponential backoff |
| Variable resolution errors | High | Low | Fail fast with clear error messages |
| Docker image size too large | Low | Medium | Optimize layers, use multi-stage builds |

---

## Future Enhancements (Post v1.0)

### Short-term (Next 3-6 months)
- Configurable concurrency control (limit parallel executions)
- Retry logic for failed tests
- Webhook notifications on completion
- JSON output format for programmatic parsing
- Test result caching to skip unchanged tests
- Incremental test execution (only changed use cases)

### Long-term (6-12 months)
- Distributed execution across multiple runners
- Test sharding for massive test suites
- Real-time progress streaming to UI
- Custom reporter plugins
- Integration with test management tools (TestRail, Zephyr)
- Performance metrics and trends

---

## Open Questions

1. **Container Registry**
   - Where should we publish the Docker image?
   - Options: Docker Hub (public), ECR Public, GitHub Container Registry
   - Decision needed by: Before WP5

2. **Concurrency Limits**
   - Should we enforce a maximum number of parallel executions in v1.0?
   - What happens if a suite has 100+ use cases?
   - Decision needed by: Before WP3

3. **Timeout Behavior**
   - Should individual use cases have timeouts?
   - Should the global timeout kill all executions or wait for in-progress tests?
   - Decision needed by: Before WP3

4. **Artifact Storage Limits**
   - Should we limit artifact sizes (e.g., max 500MB per execution)?
   - What happens if S3 upload fails?
   - Decision needed by: Before WP4

---

## Success Metrics (Post-Launch)

### Adoption Metrics
- Number of CI/CD runner executions per week
- Number of unique OAuth clients created
- Percentage of test suites executed via runner vs UI

### Performance Metrics
- Average execution time per test suite
- Artifact upload success rate
- API error rate for runner requests

### Quality Metrics
- Runner crash rate
- Exit code accuracy (false positives/negatives)
- User-reported issues

---

## Appendix

### Related Documents
- OAuth Client Implementation Spec
- Test Suite Feature Spec
- API Documentation

### Glossary
- **Test Suite**: Collection of use cases executed together
- **Use Case**: Individual test scenario with steps
- **OAuth Client**: Machine-to-machine authentication credential
- **Base URL**: Domain override for environment-specific testing
- **Artifact**: Output file from test execution (video, trace, logs)
- **Presigned URL**: Temporary S3 upload URL with embedded credentials
- **Trigger Type**: Source of execution (manual, scheduled, ci_runner)
