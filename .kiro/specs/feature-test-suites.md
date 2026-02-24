# Feature Specification: Test Suites

## Document Information
- **Feature Name**: Test Suites
- **Version**: 1.0
- **Date**: 2026-02-11
- **Status**: Design Phase

---

## Overview

### Purpose
Enable users to group multiple use cases into test suites and execute them as a batch with real-time status tracking.

### Goals
- Group use cases into logical test suites
- Execute all use cases in a suite in parallel
- Continue execution even if individual tests fail
- Track execution status for each use case independently
- Provide scope-based access control with suite-specific OAuth scopes
- Support scheduled execution per test suite
- Display suite metrics: total tests, success count, last run status

### Success Criteria
- Users can create and manage test suites through UI
- Suite execution completes in parallel with real-time updates
- Individual test failures don't block other tests
- Scope-based access control prevents unauthorized access
- Scheduled suites execute automatically
- Suite list view shows key metrics at a glance

---

## Key Design Decisions

### 1. Parallel Execution Strategy
**Decision**: All use cases in a suite execute simultaneously.

**Rationale**:
- Faster overall execution time
- Better resource utilization
- Aligns with modern CI/CD practices
- Leverages existing ECS infrastructure

**Implementation**: Spawn all ECS tasks concurrently when suite execution triggered. Each use case gets its own ECS task using existing pattern.

**Constraints**: Limited by ECS cluster capacity (default: 10 concurrent tasks).

### 2. Failure Handling Philosophy
**Decision**: Individual test failures do NOT stop suite execution.

**Rationale**:
- Maximizes test coverage per run
- Identifies all failing tests in one execution
- Reduces debugging time
- Common pattern in test frameworks

**Status Logic**:
- `running`: Suite execution in progress
- `completed`: All tests finished, all passed
- `partial`: All tests finished, some failed
- `failed`: Suite-level error (cannot start executions)

### 3. Scope Model
**Decision**: Test suites have independent OAuth scopes.

**Scope Format**:
- Suite scopes: `suite:smoke-tests`, `suite:regression`
- Independent of use case scopes: `usecase:login`

**Access Rules**:
- Create/edit suite: Write access to suite scope
- Execute suite: Execute access to suite scope
- View suite: Read access to suite scope
- Add use case to suite: Read access to use case scope

### 4. Many-to-Many Relationship
**Decision**: Use cases can belong to multiple test suites.

**Rationale**:
- Flexibility: Same test in multiple suites
- Reusability: Maintain once, use everywhere
- Industry standard: Matches pytest, jest patterns
- Practical: Login test in "Smoke", "Auth", "Regression" suites

**Implementation Impact**: Mapping table pattern in DynamoDB. When deleting use case, remove from all suites.

### 5. Per-Suite Scheduling
**Decision**: Each test suite has its own independent schedule.

**Implementation**: Cron expression stored on suite entity. EventBridge rule per suite when enabled. Scheduled executions tracked with trigger_type: 'scheduled'.

---

## Data Model

### DynamoDB Schema

Following existing pattern with pk (partition key) and sk (sort key).

#### 1. Test Suite Entity
**Keys**: pk='TEST_SUITES', sk='SUITE#{suite_id}'

**Attributes**:
- id: UUID
- name: Suite name
- description: Suite description
- scope: OAuth scope (e.g., 'suite:smoke-tests')
- created_at, updated_at: ISO 8601 timestamps
- created_by: user_id
- tags: Array of tags for filtering
- schedule_expression: Cron format (e.g., "0 9 * * MON-FRI")
- schedule_enabled: Boolean
- schedule_timezone: Default 'UTC'
- last_execution_id: UUID (denormalized for quick access)
- last_execution_status: 'completed'|'partial'|'failed'
- last_execution_time: ISO 8601 timestamp
- total_usecases: Count (denormalized)
- last_successful_count: Count (denormalized for dashboard)

**Access Pattern**: Query pk='TEST_SUITES', filter by user's accessible scopes at application level.

#### 2. Suite-UseCase Mapping
**Keys**: pk='SUITE#{suite_id}', sk='USECASE#{usecase_id}'

**Attributes**:
- suite_id: UUID
- usecase_id: UUID
- usecase_name: Denormalized for display
- usecase_scope: Denormalized for access validation
- added_at: ISO 8601 timestamp
- added_by: user_id

**Access Pattern**: Query pk='SUITE#{suite_id}', sk begins_with 'USECASE#'

**Note**: Many-to-many relationship. Same use case can have multiple mappings with different suite_ids.

#### 3. Suite Execution Metadata
**Keys**: pk='SUITE_EXECUTION#{suite_id}', sk='EXECUTION#{suite_execution_id}'

**Attributes**:
- id: suite_execution_id (UUID)
- suite_id: UUID
- suite_name: Denormalized
- suite_scope: Denormalized
- status: 'pending'|'running'|'completed'|'partial'|'failed'
- started_at, completed_at: ISO 8601 timestamps
- duration_seconds: Calculated
- triggered_by: user_id
- trigger_type: 'manual'|'scheduled'
- total_usecases: Count
- completed_usecases: Incremented as tests finish
- successful_usecases: Count
- failed_usecases: Count
- running_usecases: Count
- error_message: Suite-level error (optional)

**Access Pattern**: Query pk='SUITE_EXECUTION#{suite_id}', sk begins_with 'EXECUTION#', sort by started_at descending.

#### 4. Suite Execution Result (per use case)
**Keys**: pk='SUITE_EXEC#{suite_execution_id}', sk='RESULT#{usecase_id}'

**Attributes**:
- suite_execution_id: UUID
- usecase_id: UUID
- usecase_name: Denormalized
- usecase_execution_id: Links to USECASE_EXECUTION table
- status: 'pending'|'running'|'completed'|'failed'
- started_at, completed_at: ISO 8601 timestamps
- duration_seconds: Calculated
- error_message: Error details (optional)
- task_arn: ECS task ARN for stopping
- recording_url: S3 URL to recording (optional)

**Access Pattern**: Query pk='SUITE_EXEC#{suite_execution_id}', sk begins_with 'RESULT#'

**Note**: Uses SUITE_EXEC# prefix to avoid conflict with existing EXECUTION# pattern.

### Schema Comparison with Existing Patterns

**Existing Use Case Execution**:
- pk='USECASE_EXECUTION#{usecase_id}', sk='EXECUTION#{execution_id}'
- pk='EXECUTION#{execution_id}', sk='EXECUTION_STEP#{step_id}'

**New Suite Execution (No Conflict)**:
- pk='SUITE_EXECUTION#{suite_id}', sk='EXECUTION#{suite_execution_id}'
- pk='SUITE_EXEC#{suite_execution_id}', sk='RESULT#{usecase_id}' (Different prefix!)

### Denormalization Strategy

To optimize read performance:
- Suite entity stores last_execution_* fields for dashboard
- Suite-UseCase mapping stores usecase_name and usecase_scope
- Suite execution stores suite_name and suite_scope
- Execution results store usecase_name

Trade-off: Slightly more complex writes, significantly faster reads.

---

## API Endpoints

### Test Suite Management

#### POST /test-suites
Create a new test suite.

**Request**: name, description, scope, tags (optional)
**Response**: Created suite object with generated ID
**Scope Validation**: User must have write access to specified scope

#### GET /test-suites
List all test suites filtered by user's scopes.

**Query Parameters**: tag (optional), scope (optional)
**Response**: Array of suite objects with metrics
**Scope Validation**: Filter by user's readable scopes

#### GET /test-suites/{suite_id}
Get a specific test suite.

**Response**: Suite object with all metadata including schedule configuration
**Scope Validation**: User must have read access to suite's scope

#### PUT /test-suites/{suite_id}
Update test suite metadata.

**Request**: name, description, tags (partial update)
**Response**: Updated suite object
**Scope Validation**: User must have write access to suite's scope

#### DELETE /test-suites/{suite_id}
Delete a test suite.

**Response**: 204 No Content
**Scope Validation**: User must have write access to suite's scope
**Behavior**: Also deletes all suite-usecase mappings and disables schedule

### Use Case Management in Suites

#### POST /test-suites/{suite_id}/usecases
Add use cases to a suite.

**Request**: usecase_ids (array)
**Response**: Count of added use cases, total_usecases
**Scope Validation**: User must have write access to suite scope AND read access to all use cases being added
**Behavior**: Idempotent - adding existing use case is no-op

#### GET /test-suites/{suite_id}/usecases
List all use cases in a suite.

**Response**: Array of use case objects with metadata (id, name, scope, added_at, added_by)
**Scope Validation**: User must have read access to suite's scope

#### DELETE /test-suites/{suite_id}/usecases/{usecase_id}
Remove a use case from a suite.

**Response**: 204 No Content
**Scope Validation**: User must have write access to suite's scope

### Suite Scheduling

#### PUT /test-suites/{suite_id}/schedule
Configure or update suite schedule.

**Request**: schedule_expression (cron), schedule_enabled (boolean), schedule_timezone (optional)
**Response**: Updated suite object
**Scope Validation**: User must have write access to suite's scope
**Behavior**: Creates/updates EventBridge rule for scheduled execution

### Suite Execution

#### POST /test-suites/{suite_id}/execute
Execute all use cases in a suite.

**Request**: trigger_type ('manual' or 'scheduled')
**Response**: suite_execution_id, status, total_usecases, started_at
**Scope Validation**: User must have execute access to suite's scope
**Behavior**: Creates suite execution record, triggers individual use case executions in parallel, returns immediately (async)

#### GET /test-suites/{suite_id}/executions
List all executions for a suite.

**Query Parameters**: limit (default 50, max 100), status (optional filter)
**Response**: Array of execution objects with summary metrics
**Scope Validation**: User must have read access to suite's scope

#### GET /test-suites/{suite_id}/executions/{execution_id}
Get detailed status of a suite execution.

**Response**: Execution object with results array containing status for each use case
**Scope Validation**: User must have read access to suite's scope
**Use Case**: Frontend polls this endpoint every 5 seconds for real-time updates

#### POST /test-suites/{suite_id}/executions/{execution_id}/stop
Stop a running suite execution.

**Response**: Count of stopped tasks
**Scope Validation**: User must have execute access to suite's scope
**Behavior**: Stops all running ECS tasks for use cases in the suite

---

## Backend Implementation

### Lambda Functions Required

#### Core CRUD Operations
- **create_test_suite.py**: Validates scope, generates UUID, creates suite item
- **list_test_suites.py**: Queries TEST_SUITES, filters by user scopes
- **get_test_suite.py**: Gets suite by ID, validates read access
- **update_test_suite.py**: Updates metadata, validates write access
- **delete_test_suite.py**: Deletes suite, mappings, and disables schedule

#### Use Case Management
- **add_usecases_to_suite.py**: Validates scopes, creates mappings, updates count
- **list_suite_usecases.py**: Queries mappings, returns use case list
- **remove_usecase_from_suite.py**: Deletes mapping, decrements count

#### Scheduling
- **update_suite_schedule.py**: Updates schedule fields, manages EventBridge rule

#### Execution Management
- **execute_test_suite.py**: Creates execution record, invokes execute_usecase for each use case in parallel
- **list_suite_executions.py**: Queries executions with pagination
- **get_suite_execution.py**: Gets execution metadata and all results
- **stop_suite_execution.py**: Stops running tasks, updates statuses

### Event Handler Integration

**Modify handle_task_state_change.py**:
When ECS task state changes, check if execution is part of a suite. If yes:
- Update suite execution result status
- Increment suite execution counters atomically
- Check if all tests complete, update suite status accordingly
- Update denormalized fields on suite entity

**Helper Functions Needed**:
- query_suite_execution_results: Find suite executions containing this use case execution
- update_suite_execution_result: Update individual result status
- update_suite_execution_counters: Increment completed/successful/failed counters
- check_suite_completion: Determine if suite is complete, set final status
- update_suite_last_execution: Update denormalized fields on suite entity

### Scope Validation Utility

**Add to utils.py**:
Function validate_scope_access(user_scopes, required_scope, permission_type) that:
- Checks if user has wildcard access
- Checks specific permission
- Checks if write permission implies read/execute
- Raises PermissionError if access denied

---

## Frontend Implementation

### Navigation Structure

Update App.tsx to add Test Suites in Testing section:
- Use Cases
- Test Suites (NEW)
- Executions

### New Components Required

#### TestSuites.tsx - List View
**Purpose**: Display all test suites with key metrics

**Table Columns**:
- Name (link to detail)
- Description
- Total Tests
- Last Run (formatted as "2h ago")
- Success Rate (badge showing "4/5")
- Status (StatusIndicator)
- Schedule (badge if enabled)
- Actions (dropdown: Execute, Edit, Delete)

**Features**: Filter by tags, filter by scope, search by name, "Create Test Suite" button

#### CreateTestSuite.tsx - Create/Edit Modal
**Purpose**: Create or edit test suite metadata

**Form Fields**:
- Name (required, 3-100 characters)
- Description (textarea)
- Scope (required, dropdown with user's writable scopes, format: suite:*)
- Tags (token group, comma-separated)

#### TestSuiteDetail.tsx - Detail View
**Purpose**: View and manage a single test suite

**Layout Sections**:
1. Header: Suite name, description, scope badge, tags, edit/delete buttons
2. Actions Bar: "Execute Suite" (primary), "Add Use Cases", "Configure Schedule"
3. Use Cases Table: Name, Scope, Status (from last run), Actions (View Details, Remove)
4. Recent Executions: Last 10 executions with status, success rate, trigger type

#### AddUsecasesToSuite.tsx - Modal
**Purpose**: Add use cases to a suite

**Features**: Multi-select table, filter by name/tags/scope, shows which use cases already in suite (disabled), search bar, "Add Selected" button

#### ConfigureSchedule.tsx - Modal
**Purpose**: Configure suite schedule

**Form Fields**:
- Enable Schedule (toggle)
- Schedule Expression (cron input with helper/presets)
- Timezone (dropdown)
- Next Run Preview (calculated from cron)

**Cron Presets**: "Every day at 9 AM", "Weekdays at 6 PM", "Every Monday at 8 AM", Custom

#### SuiteExecutionDetail.tsx - Execution Status View
**Purpose**: Real-time status of suite execution

**Layout**:
1. Header: Suite name, execution ID, started timestamp, duration (live updating), overall status
2. Progress Bar: Visual progress with color coding (green=success, red=failed, blue=running)
3. Summary Cards: Total Tests, Completed (%), Successful, Failed, Running
4. Results Table: Use Case Name, Status (StatusIndicator), Started, Duration, Actions (View Details, View Recording)
5. Actions: "Stop Execution" (if running), "Re-run Suite", "Export Results" (future)

**Polling Logic**: Poll GET /test-suites/{suite_id}/executions/{execution_id} every 5 seconds while status is 'running'

### API Integration

Add to frontend/src/utils/api.ts:
- testSuites.create, list, get, update, delete
- testSuites.addUsecases, listUsecases, removeUsecase
- testSuites.updateSchedule
- testSuites.execute, listExecutions, getExecution, stopExecution

### TypeScript Interfaces

Define interfaces for:
- TestSuite
- SuiteExecution
- SuiteExecutionResult
- CreateTestSuiteRequest
- UpdateTestSuiteRequest
- ScheduleConfig

---

## Infrastructure Changes

### CDK Stack Updates

#### lib/api-stack.ts
Add API Gateway routes:
- /test-suites (GET, POST)
- /test-suites/{suite_id} (GET, PUT, DELETE)
- /test-suites/{suite_id}/usecases (GET, POST)
- /test-suites/{suite_id}/usecases/{usecase_id} (DELETE)
- /test-suites/{suite_id}/schedule (PUT)
- /test-suites/{suite_id}/execute (POST)
- /test-suites/{suite_id}/executions (GET)
- /test-suites/{suite_id}/executions/{execution_id} (GET)
- /test-suites/{suite_id}/executions/{execution_id}/stop (POST)

#### lib/lambda-stack.ts
Create Lambda functions for all operations with appropriate environment variables and IAM permissions.

### IAM Permissions

**DynamoDB Access**: All Lambda functions need read/write access to DynamoDB table using existing managed policies.

**EventBridge Access**:
- update_suite_schedule: PutRule, PutTargets, EnableRule, DisableRule
- delete_test_suite: DeleteRule, RemoveTargets

**Lambda Invocation**:
- execute_test_suite: Invoke execute_usecase Lambda
- EventBridge rules: Invoke execute_test_suite Lambda

**ECS Access**:
- stop_suite_execution: StopTask permission

### EventBridge Rules

**Rule Naming Convention**: {baseName}-suite-{suite_id}

**Rule Configuration**: ScheduleExpression from suite.schedule_expression, State based on suite.schedule_enabled, Target is execute_test_suite Lambda with suite_id and trigger_type in input.

---

## Security & Access Control

### Scope-Based Authorization

Test suites use OAuth scopes for fine-grained access control, independent of use case scopes.

#### Scope Format

**Suite Scopes (NEW)**:
- suite:{suite-name}:read - View suite
- suite:{suite-name}:write - Create/edit/delete suite
- suite:{suite-name}:execute - Execute suite
- suite:{suite-name}:* - All permissions

**Use Case Scopes (existing)**:
- usecase:{name}:read, write, execute

#### Adding Suite Scopes to Cognito

**Update User Pool Configuration**:
1. Add Resource Server Scope (if using Cognito Resource Server) with identifier 'test-suites' and scopes: read, write, execute
2. Update Pre-Token Generation Lambda to add suite scopes based on user groups
3. Authorizer Lambda already passes scopes to Lambda context (no changes needed)

**Default Scope Mappings**:
- admin group → suite:*:* (all suites, all permissions)
- qa-team group → suite:*:write (all suites, write access)
- developers group → suite:*:read + suite:*:execute (view and execute)
- viewers group → suite:*:read (view only)

#### Authorization Matrix

| Operation | Required Scope | Additional Checks |
|-----------|---------------|-------------------|
| Create suite | suite:{scope}:write | User must have write on specified scope |
| List suites | suite:*:read | Filter by user's readable scopes |
| View suite | suite:{suite_scope}:read | - |
| Update suite | suite:{suite_scope}:write | - |
| Delete suite | suite:{suite_scope}:write | - |
| Add use case to suite | suite:{suite_scope}:write | User must have usecase:{usecase_scope}:read |
| Remove use case | suite:{suite_scope}:write | - |
| List use cases in suite | suite:{suite_scope}:read | - |
| Configure schedule | suite:{suite_scope}:write | - |
| Execute suite | suite:{suite_scope}:execute | - |
| View execution | suite:{suite_scope}:read | - |
| Stop execution | suite:{suite_scope}:execute | - |

#### Implementation in Lambda Functions

Each Lambda function:
1. Extracts user scopes from authorizer context
2. Gets suite/resource being accessed
3. Validates user has required permission on scope
4. Proceeds with operation or raises PermissionError

#### Cross-Scope Use Case Addition

When adding use cases to suite, validate both:
- User has write access to suite scope
- User has read access to each use case scope

### Audit Trail

All operations logged with user_id, action, resource_id, and timestamp for audit purposes.

### Data Isolation

Users can only see suites they have read access to. List operations filter by user's scopes at application level. DynamoDB queries don't inherently filter by scope (single-table design), so application-level filtering ensures data isolation.

---

## Execution Flow

### Manual Execution Flow

1. **User Triggers Execution**: User clicks "Execute Suite", frontend calls POST /test-suites/{suite_id}/execute
2. **Suite Execution Initialization**: Lambda validates permissions, creates suite execution record with status='running', queries all use cases in suite
3. **Parallel Use Case Execution**: For each use case, invoke execute_usecase Lambda asynchronously, create execution result record with status='pending', store task ARN. All invocations happen in parallel.
4. **Return to User**: Lambda returns suite execution ID immediately, frontend redirects to execution detail page
5. **Real-Time Status Updates**: Frontend polls GET /test-suites/{suite_id}/executions/{execution_id} every 5 seconds, updates UI with live progress
6. **ECS Task State Changes**: As each use case completes, handle_task_state_change Lambda updates suite execution result and increments counters atomically
7. **Suite Completion**: When all use cases complete, determine final status (completed/partial/failed), update suite execution and denormalized fields on suite entity
8. **User Views Results**: Frontend displays final results with links to individual executions and recordings

### Scheduled Execution Flow

1. **Schedule Configuration**: User configures schedule, Lambda creates EventBridge rule
2. **EventBridge Triggers**: At scheduled time, EventBridge invokes execute_test_suite with suite_id and trigger_type='scheduled'
3. **Execution Proceeds**: Same flow as manual execution, triggered_by set to "system"
4. **Notifications (Future)**: On completion, send notification via SNS

### Stop Execution Flow

1. **User Stops Execution**: User clicks "Stop Execution", frontend calls POST stop endpoint
2. **Stop All Running Tasks**: Lambda queries all results with status='running', calls ECS StopTask for each, updates result status to 'failed'
3. **Update Suite Status**: Updates suite execution status to 'partial' or 'failed', sets completed_at
4. **Frontend Updates**: Displays "Execution stopped" message with final results

### Error Handling

**Suite-Level Errors**: Cannot query use cases, cannot invoke execute_usecase, DynamoDB errors → Status='failed', error_message set

**Use Case-Level Errors**: Individual test failures, task launch failures, timeouts → Result status='failed', suite continues

**Resilience**: Suite execution continues even if individual tests fail. Partial results always available. Users can retry failed tests individually.

---

## Implementation Plan

### Phase 1: Backend Foundation (Week 1-2)
**Goal**: Core data model and API endpoints

**Tasks**:
- Create DynamoDB schema (no migration needed)
- Implement 8 CRUD Lambda functions
- Update utils.py with scope validation
- Add API Gateway routes
- Write unit tests

**Deliverables**: Working CRUD API for test suites, use case management API, scope-based access control

### Phase 2: Execution Engine (Week 2-3)
**Goal**: Parallel execution and status tracking

**Tasks**:
- Implement 4 execution Lambda functions
- Modify handle_task_state_change.py for suite tracking
- Add helper functions for suite completion
- Write integration tests

**Deliverables**: Working parallel execution, real-time status tracking, stop execution capability

### Phase 3: Frontend Implementation (Week 3-4)
**Goal**: User interface for test suites

**Tasks**:
- Create 6 React components
- Add API integration
- Add TypeScript interfaces
- Update navigation and routing
- Implement polling for real-time updates

**Deliverables**: Complete UI for test suite management, execution monitoring interface

### Phase 4: Scheduling (Week 4-5)
**Goal**: Automated scheduled execution

**Tasks**:
- Implement update_suite_schedule.py
- Add EventBridge rule management
- Create ConfigureSchedule.tsx component
- Add cron validation and preview
- Test scheduled execution

**Deliverables**: Working scheduled execution, UI for schedule configuration, cron helper

### Phase 5: Polish & Documentation (Week 5-6)
**Goal**: Production-ready feature

**Tasks**:
- Add error handling and user feedback
- Optimize DynamoDB queries
- Add loading states
- Write user documentation
- Performance testing
- Security audit

**Deliverables**: Production-ready feature, documentation, performance benchmarks, security review

### Rollout Strategy

**Week 6**: Beta release to staging, invite select users, gather feedback
**Week 7**: Production release, announce feature, monitor usage
**Week 8**: Iteration based on feedback

### Success Metrics

**Adoption**: Number of suites created, executions per day, average use cases per suite, percentage of users using feature

**Performance**: Average suite execution time, parallel execution efficiency, API response times, error rates

**Business**: Time saved vs individual execution, reduction in manual coordination, increase in test coverage, user satisfaction

### Future Enhancements

**Phase 6+ (Post-Launch)**:
1. Advanced Execution Options: Conditional execution, dependency management, auto-retry
2. Reporting & Analytics: History charts, success rate trends, PDF/HTML reports, CSV export
3. Notifications: Email, Slack, webhooks, custom rules
4. Suite Templates: Predefined templates, clone suites, import/export
5. Advanced Scheduling: Multiple schedules, conditional scheduling, dependencies
6. Collaboration: Suite sharing, comments, tagging
7. Performance: Caching, batch operations, optimistic UI

---

## Appendix

### Example Use Cases

**Smoke Test Suite**:
- Tests: Login, Dashboard, Create Item, View Item, Logout
- Schedule: Every hour
- Scope: suite:smoke-tests

**Regression Test Suite**:
- Tests: All smoke tests + advanced features
- Schedule: Nightly at 2 AM
- Scope: suite:regression

**Pre-Deployment Suite**:
- Tests: Critical path + security + performance
- Schedule: On-demand only
- Scope: suite:pre-deploy

### Cron Expression Examples

- 0 9 * * MON-FRI - Every weekday at 9 AM
- 0 */2 * * * - Every 2 hours
- 0 0 * * * - Daily at midnight
- 0 0 * * SUN - Every Sunday at midnight
- 0 6,18 * * * - Daily at 6 AM and 6 PM

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-11 | Design Team | Initial design document |

---

## Approval

This design document requires approval from:
- [ ] Engineering Lead
- [ ] Product Manager
- [ ] Security Team
- [ ] QA Lead

---

*End of Document*
