# Feature Specification: Test Suites

## Document Information
- **Feature Name**: Test Suites
- **Version**: 1.0
- **Date**: 2026-02-11
- **Status**: Design Phase

## Table of Contents
1. [Overview](#overview)
2. [Key Design Decisions](#key-design-decisions)
3. [Data Model](#data-model)
4. [API Endpoints](#api-endpoints)
5. [Backend Implementation](#backend-implementation)
6. [Frontend Implementation](#frontend-implementation)
7. [Infrastructure Changes](#infrastructure-changes)
8. [Security & Access Control](#security--access-control)
9. [Execution Flow](#execution-flow)
10. [Implementation Plan](#implementation-plan)

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

**Implementation**:
- Spawn all ECS tasks concurrently when suite execution triggered
- Each use case gets its own ECS task (existing pattern)
- No dependency management between tests

**Constraints**:
- Limited by ECS cluster capacity (default: 10 concurrent tasks)

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

**Implementation Impact**:
- Mapping table pattern in DynamoDB
- When deleting use case, remove from all suites
- UI shows "Used in X suites" on use case detail

### 5. Per-Suite Scheduling
**Decision**: Each test suite has its own independent schedule.

**Implementation**:
- Cron expression stored on suite entity
- EventBridge rule per suite (when enabled)
- Scheduled executions tracked with `trigger_type: 'scheduled'`

---

## Data Model

### DynamoDB Schema

Following existing pattern with `pk` (partition key) and `sk` (sort key).

#### 1. Test Suite Entity
```
pk: 'TEST_SUITES'
sk: 'SUITE#{suite_id}'

Attributes:
{
  id: string,                          // UUID
  name: string,                        // "Smoke Tests"
  description: string,                 // "Critical path tests"
  scope: string,                       // "suite:smoke-tests"
  created_at: string,                  // ISO 8601 timestamp
  updated_at: string,                  // ISO 8601 timestamp
  created_by: string,                  // user_id
  tags: string[],                      // ["smoke", "critical"]
  schedule_expression: string,         // "0 9 * * MON-FRI" (cron)
  schedule_enabled: boolean,           // false
  schedule_timezone: string,           // "UTC"
  last_execution_id: string,           // UUID (denormalized)
  last_execution_status: string,       // "completed"|"partial"|"failed"
  last_execution_time: string,         // ISO 8601 timestamp
  total_usecases: number,              // 5
  last_successful_count: number        // 4 (for dashboard)
}
```

**Access Pattern**: List all suites
- Query: `pk = 'TEST_SUITES'`
- Filter: User has read access to suite scope (application-level)

#### 2. Suite-UseCase Mapping
```
pk: 'SUITE#{suite_id}'
sk: 'USECASE#{usecase_id}'

Attributes:
{
  suite_id: string,                    // UUID
  usecase_id: string,                  // UUID
  usecase_name: string,                // "Login Test" (denormalized)
  usecase_scope: string,               // "usecase:auth" (denormalized)
  added_at: string,                    // ISO 8601 timestamp
  added_by: string                     // user_id
}
```

**Access Pattern**: List use cases in suite
- Query: `pk = 'SUITE#{suite_id}', sk begins_with 'USECASE#'`

**Note**: Many-to-many relationship. Same use case can have multiple mappings with different suite_ids.

#### 3. Suite Execution Metadata
```
pk: 'SUITE_EXECUTION#{suite_id}'
sk: 'EXECUTION#{suite_execution_id}'

Attributes:
{
  id: string,                          // suite_execution_id (UUID)
  suite_id: string,                    // UUID
  suite_name: string,                  // "Smoke Tests" (denormalized)
  suite_scope: string,                 // "suite:smoke-tests" (denormalized)
  status: string,                      // "pending"|"running"|"completed"|"partial"|"failed"
  started_at: string,                  // ISO 8601 timestamp
  completed_at: string,                // ISO 8601 timestamp (optional)
  duration_seconds: number,            // 120 (optional)
  triggered_by: string,                // user_id
  trigger_type: string,                // "manual"|"scheduled"
  total_usecases: number,              // 5
  completed_usecases: number,          // 3 (incremented as tests finish)
  successful_usecases: number,         // 2
  failed_usecases: number,             // 1
  running_usecases: number,            // 2
  error_message: string                // Suite-level error (optional)
}
```

**Access Pattern**: List executions for suite
- Query: `pk = 'SUITE_EXECUTION#{suite_id}', sk begins_with 'EXECUTION#'`
- Sort: By `started_at` descending

#### 4. Suite Execution Result (per use case)
```
pk: 'SUITE_EXEC#{suite_execution_id}'
sk: 'RESULT#{usecase_id}'

Attributes:
{
  suite_execution_id: string,          // UUID
  usecase_id: string,                  // UUID
  usecase_name: string,                // "Login Test" (denormalized)
  usecase_execution_id: string,        // Links to USECASE_EXECUTION table
  status: string,                      // "pending"|"running"|"completed"|"failed"
  started_at: string,                  // ISO 8601 timestamp (optional)
  completed_at: string,                // ISO 8601 timestamp (optional)
  duration_seconds: number,            // 45 (optional)
  error_message: string,               // Error details (optional)
  task_arn: string,                    // ECS task ARN (optional, for stopping)
  recording_url: string                // S3 URL to recording (optional)
}
```

**Access Pattern**: Get all results for suite execution
- Query: `pk = 'SUITE_EXEC#{suite_execution_id}', sk begins_with 'RESULT#'`

**Note**: Uses `SUITE_EXEC#` prefix to avoid conflict with existing `EXECUTION#` pattern.

### Schema Comparison with Existing Patterns

**Existing Use Case Execution**:
```
pk: 'USECASE_EXECUTION#{usecase_id}'
sk: 'EXECUTION#{execution_id}'

pk: 'EXECUTION#{execution_id}'
sk: 'EXECUTION_STEP#{step_id}'
```

**New Suite Execution (No Conflict)**:
```
pk: 'SUITE_EXECUTION#{suite_id}'
sk: 'EXECUTION#{suite_execution_id}'

pk: 'SUITE_EXEC#{suite_execution_id}'  // Different prefix!
sk: 'RESULT#{usecase_id}'
```

### Denormalization Strategy

To optimize read performance:
- Suite entity stores `last_execution_*` fields for dashboard
- Suite-UseCase mapping stores `usecase_name` and `usecase_scope`
- Suite execution stores `suite_name` and `suite_scope`
- Execution results store `usecase_name`

**Trade-off**: Slightly more complex writes, significantly faster reads.


---

## API Endpoints

### Test Suite Management

#### `POST /test-suites`
Create a new test suite.

**Request**:
```json
{
  "name": "Smoke Tests",
  "description": "Critical path smoke tests",
  "scope": "suite:smoke-tests",
  "tags": ["smoke", "critical"]
}
```

**Response** (201 Created):
```json
{
  "id": "uuid",
  "name": "Smoke Tests",
  "description": "Critical path smoke tests",
  "scope": "suite:smoke-tests",
  "tags": ["smoke", "critical"],
  "created_at": "2026-02-11T12:00:00Z",
  "updated_at": "2026-02-11T12:00:00Z",
  "created_by": "user-123",
  "total_usecases": 0,
  "schedule_enabled": false
}
```

**Scope Validation**: User must have write access to specified scope.

#### `GET /test-suites`
List all test suites (filtered by user's scopes).

**Query Parameters**:
- `tag`: Filter by tag (optional)
- `scope`: Filter by scope (optional)

**Response** (200 OK):
```json
{
  "suites": [
    {
      "id": "uuid",
      "name": "Smoke Tests",
      "description": "Critical path tests",
      "scope": "suite:smoke-tests",
      "tags": ["smoke"],
      "total_usecases": 5,
      "last_execution_status": "completed",
      "last_execution_time": "2026-02-11T10:00:00Z",
      "last_successful_count": 5,
      "schedule_enabled": true
    }
  ]
}
```

#### `GET /test-suites/{suite_id}`
Get a specific test suite.

**Response** (200 OK):
```json
{
  "id": "uuid",
  "name": "Smoke Tests",
  "description": "Critical path tests",
  "scope": "suite:smoke-tests",
  "tags": ["smoke", "critical"],
  "created_at": "2026-02-11T12:00:00Z",
  "updated_at": "2026-02-11T12:00:00Z",
  "created_by": "user-123",
  "total_usecases": 5,
  "last_execution_id": "exec-uuid",
  "last_execution_status": "completed",
  "last_execution_time": "2026-02-11T10:00:00Z",
  "last_successful_count": 5,
  "schedule_expression": "0 9 * * MON-FRI",
  "schedule_enabled": true,
  "schedule_timezone": "UTC"
}
```

**Scope Validation**: User must have read access to suite's scope.

#### `PUT /test-suites/{suite_id}`
Update test suite metadata.

**Request**:
```json
{
  "name": "Updated Smoke Tests",
  "description": "Updated description",
  "tags": ["smoke", "critical", "daily"]
}
```

**Response** (200 OK): Updated suite object.

**Scope Validation**: User must have write access to suite's scope.

#### `DELETE /test-suites/{suite_id}`
Delete a test suite.

**Response** (204 No Content)

**Scope Validation**: User must have write access to suite's scope.

**Behavior**: Also deletes all suite-usecase mappings and disables schedule.

### Use Case Management in Suites

#### `POST /test-suites/{suite_id}/usecases`
Add use cases to a suite.

**Request**:
```json
{
  "usecase_ids": ["uuid1", "uuid2", "uuid3"]
}
```

**Response** (200 OK):
```json
{
  "added": 3,
  "total_usecases": 8
}
```

**Scope Validation**:
- User must have write access to suite's scope
- User must have read access to all use cases being added

**Behavior**: Idempotent - adding existing use case is no-op.

#### `GET /test-suites/{suite_id}/usecases`
List all use cases in a suite.

**Response** (200 OK):
```json
{
  "usecases": [
    {
      "id": "uuid1",
      "name": "Login Test",
      "scope": "usecase:auth",
      "added_at": "2026-02-11T12:00:00Z",
      "added_by": "user-123"
    }
  ]
}
```

**Scope Validation**: User must have read access to suite's scope.

#### `DELETE /test-suites/{suite_id}/usecases/{usecase_id}`
Remove a use case from a suite.

**Response** (204 No Content)

**Scope Validation**: User must have write access to suite's scope.

### Suite Scheduling

#### `PUT /test-suites/{suite_id}/schedule`
Configure or update suite schedule.

**Request**:
```json
{
  "schedule_expression": "0 9 * * MON-FRI",
  "schedule_enabled": true,
  "schedule_timezone": "America/New_York"
}
```

**Response** (200 OK): Updated suite object.

**Scope Validation**: User must have write access to suite's scope.

**Behavior**: Creates/updates EventBridge rule for scheduled execution.

### Suite Execution

#### `POST /test-suites/{suite_id}/execute`
Execute all use cases in a suite.

**Request**:
```json
{
  "trigger_type": "manual"
}
```

**Response** (202 Accepted):
```json
{
  "suite_execution_id": "uuid",
  "status": "running",
  "total_usecases": 5,
  "started_at": "2026-02-11T12:00:00Z"
}
```

**Scope Validation**: User must have execute access to suite's scope.

**Behavior**:
- Creates suite execution record
- Triggers individual use case executions in parallel
- Returns immediately (async execution)

#### `GET /test-suites/{suite_id}/executions`
List all executions for a suite.

**Query Parameters**:
- `limit`: Number of results (default: 50, max: 100)
- `status`: Filter by status (optional)

**Response** (200 OK):
```json
{
  "executions": [
    {
      "id": "uuid",
      "suite_id": "suite-uuid",
      "suite_name": "Smoke Tests",
      "status": "completed",
      "started_at": "2026-02-11T10:00:00Z",
      "completed_at": "2026-02-11T10:05:00Z",
      "duration_seconds": 300,
      "trigger_type": "scheduled",
      "triggered_by": "system",
      "total_usecases": 5,
      "successful_usecases": 5,
      "failed_usecases": 0
    }
  ]
}
```

#### `GET /test-suites/{suite_id}/executions/{execution_id}`
Get detailed status of a suite execution.

**Response** (200 OK):
```json
{
  "id": "uuid",
  "suite_id": "suite-uuid",
  "suite_name": "Smoke Tests",
  "status": "running",
  "started_at": "2026-02-11T12:00:00Z",
  "total_usecases": 5,
  "completed_usecases": 3,
  "successful_usecases": 2,
  "failed_usecases": 1,
  "running_usecases": 2,
  "results": [
    {
      "usecase_id": "uuid1",
      "usecase_name": "Login Test",
      "status": "completed",
      "usecase_execution_id": "exec-uuid1",
      "started_at": "2026-02-11T12:00:00Z",
      "completed_at": "2026-02-11T12:01:30Z",
      "duration_seconds": 90
    },
    {
      "usecase_id": "uuid2",
      "usecase_name": "Checkout Test",
      "status": "failed",
      "usecase_execution_id": "exec-uuid2",
      "started_at": "2026-02-11T12:00:00Z",
      "completed_at": "2026-02-11T12:02:00Z",
      "duration_seconds": 120,
      "error_message": "Element not found"
    },
    {
      "usecase_id": "uuid3",
      "usecase_name": "Search Test",
      "status": "running",
      "usecase_execution_id": "exec-uuid3",
      "started_at": "2026-02-11T12:00:00Z"
    }
  ]
}
```

#### `POST /test-suites/{suite_id}/executions/{execution_id}/stop`
Stop a running suite execution.

**Response** (200 OK):
```json
{
  "stopped": 2,
  "message": "Stopped 2 running tasks"
}
```

**Scope Validation**: User must have execute access to suite's scope.

**Behavior**: Stops all running ECS tasks for use cases in the suite.


---

## Backend Implementation

### Lambda Functions

#### Core CRUD Operations

**`create_test_suite.py`**
- Validates scope access (user has write permission)
- Generates UUID for suite
- Creates suite item in DynamoDB
- Returns created suite object

**`list_test_suites.py`**
- Queries `pk = 'TEST_SUITES'`
- Filters by user's accessible scopes (application-level)
- Supports tag and scope query parameters
- Returns array of suite objects

**`get_test_suite.py`**
- Gets suite by ID
- Validates user has read access to suite scope
- Returns suite object with all metadata

**`update_test_suite.py`**
- Validates user has write access to suite scope
- Updates suite metadata (name, description, tags)
- Updates `updated_at` timestamp
- Returns updated suite object

**`delete_test_suite.py`**
- Validates user has write access to suite scope
- Deletes suite item
- Queries and deletes all suite-usecase mappings
- Disables schedule (deletes EventBridge rule)
- Returns 204 No Content

#### Use Case Management

**`add_usecases_to_suite.py`**
- Validates user has write access to suite scope
- For each use case:
  - Validates user has read access to use case scope
  - Gets use case name and scope (for denormalization)
  - Creates mapping item (idempotent)
- Updates `total_usecases` count on suite
- Returns count of added use cases

**`list_suite_usecases.py`**
- Validates user has read access to suite scope
- Queries `pk = 'SUITE#{suite_id}', sk begins_with 'USECASE#'`
- Returns array of use case objects with metadata

**`remove_usecase_from_suite.py`**
- Validates user has write access to suite scope
- Deletes mapping item
- Decrements `total_usecases` count on suite
- Returns 204 No Content

#### Scheduling

**`update_suite_schedule.py`**
- Validates user has write access to suite scope
- Updates schedule fields on suite entity
- If `schedule_enabled = true`:
  - Creates/updates EventBridge rule with cron expression
  - Sets target to `execute_test_suite` Lambda
- If `schedule_enabled = false`:
  - Disables EventBridge rule
- Returns updated suite object

#### Execution Management

**`execute_test_suite.py`**
- Validates user has execute access to suite scope
- Creates suite execution record with status='running'
- Queries all use cases in suite
- For each use case in parallel:
  - Invokes existing `execute_usecase` Lambda
  - Creates execution result record with status='pending'
  - Stores task ARN and usecase_execution_id
- Returns suite execution ID and metadata

**`list_suite_executions.py`**
- Validates user has read access to suite scope
- Queries `pk = 'SUITE_EXECUTION#{suite_id}', sk begins_with 'EXECUTION#'`
- Supports pagination (limit parameter)
- Supports status filtering
- Returns array of execution objects

**`get_suite_execution.py`**
- Validates user has read access to suite scope
- Gets suite execution metadata
- Queries all execution results
- Returns execution object with results array

**`stop_suite_execution.py`**
- Validates user has execute access to suite scope
- Queries all execution results with status='running'
- For each running result:
  - Invokes existing `stop_execution` Lambda with task ARN
  - Updates result status to 'failed'
- Updates suite execution status
- Returns count of stopped tasks

### Event Handler Integration

**Modify `handle_task_state_change.py`**

When ECS task state changes, check if it's part of a suite execution:

```python
def handler(event, context):
    # Existing logic for use case execution
    # ...
    
    # NEW: Check if this execution is part of a suite
    suite_execution_results = query_suite_execution_results(execution_id)
    
    for result in suite_execution_results:
        # Update suite execution result
        update_suite_execution_result(
            suite_execution_id=result['suite_execution_id'],
            usecase_id=result['usecase_id'],
            status=task_status,
            completed_at=timestamp,
            duration_seconds=duration
        )
        
        # Update suite execution counters
        update_suite_execution_counters(
            suite_execution_id=result['suite_execution_id'],
            status=task_status
        )
        
        # Check if all tests in suite are complete
        check_suite_completion(result['suite_execution_id'])
```

**Helper Functions**:

```python
def query_suite_execution_results(usecase_execution_id):
    """Find all suite executions that include this use case execution"""
    # Scan SUITE_EXEC# items where usecase_execution_id matches
    # (Infrequent operation, acceptable to scan)
    pass

def update_suite_execution_result(suite_execution_id, usecase_id, status, completed_at, duration_seconds):
    """Update individual result status"""
    table.update_item(
        Key={
            'pk': f'SUITE_EXEC#{suite_execution_id}',
            'sk': f'RESULT#{usecase_id}'
        },
        UpdateExpression='SET #status = :status, completed_at = :completed_at, duration_seconds = :duration',
        ExpressionAttributeNames={'#status': 'status'},
        ExpressionAttributeValues={
            ':status': status,
            ':completed_at': completed_at,
            ':duration': duration_seconds
        }
    )

def update_suite_execution_counters(suite_execution_id, status):
    """Increment appropriate counter based on status"""
    if status == 'completed':
        increment_expr = 'ADD completed_usecases :inc, successful_usecases :inc'
        decrement_expr = 'ADD running_usecases :dec'
    elif status == 'failed':
        increment_expr = 'ADD completed_usecases :inc, failed_usecases :inc'
        decrement_expr = 'ADD running_usecases :dec'
    
    # Update counters atomically
    pass

def check_suite_completion(suite_execution_id):
    """Check if all tests complete, update suite status"""
    execution = get_suite_execution(suite_execution_id)
    
    if execution['completed_usecases'] == execution['total_usecases']:
        # All tests complete
        if execution['failed_usecases'] == 0:
            final_status = 'completed'
        else:
            final_status = 'partial'
        
        # Update suite execution
        table.update_item(
            Key={
                'pk': f'SUITE_EXECUTION#{execution["suite_id"]}',
                'sk': f'EXECUTION#{suite_execution_id}'
            },
            UpdateExpression='SET #status = :status, completed_at = :completed_at, duration_seconds = :duration',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': final_status,
                ':completed_at': datetime.now().isoformat(),
                ':duration': calculate_duration(execution['started_at'])
            }
        )
        
        # Update denormalized fields on suite entity
        update_suite_last_execution(
            suite_id=execution['suite_id'],
            execution_id=suite_execution_id,
            status=final_status,
            successful_count=execution['successful_usecases']
        )
```

### Scope Validation Utility

**`utils.py` additions**:

```python
def validate_scope_access(user_scopes, required_scope, permission_type):
    """
    Validate user has required permission on scope.
    
    Args:
        user_scopes: List of scopes from JWT token
        required_scope: Scope to check (e.g., 'suite:smoke-tests')
        permission_type: 'read', 'write', or 'execute'
    
    Raises:
        PermissionError: If user lacks required permission
    """
    # Check if user has wildcard access
    if f'{required_scope}:*' in user_scopes:
        return True
    
    # Check specific permission
    required_permission = f'{required_scope}:{permission_type}'
    if required_permission in user_scopes:
        return True
    
    # Check if user has write (implies read and execute)
    if permission_type in ['read', 'execute']:
        if f'{required_scope}:write' in user_scopes:
            return True
    
    raise PermissionError(f'User lacks {permission_type} permission on {required_scope}')
```


---

## Frontend Implementation

### Navigation Structure

Update `App.tsx` to add Test Suites in the same section as Use Cases:

```tsx
{
  type: "section",
  text: "Testing",
  items: [
    { type: "link", text: "Use Cases", href: "/usecases" },
    { type: "link", text: "Test Suites", href: "/test-suites" },  // NEW
    { type: "link", text: "Executions", href: "/executions" }
  ]
}
```

### New Components

#### `TestSuites.tsx` - List View

**Purpose**: Display all test suites with key metrics.

**Layout**: Similar to `HomeScreen.tsx` for use cases.

**Table Columns**:
- Name (link to detail)
- Description
- Total Tests (number)
- Last Run (timestamp, formatted as "2h ago")
- Success Rate (e.g., "4/5" with badge)
- Status (StatusIndicator: success/warning/error)
- Schedule (badge if enabled)
- Actions (dropdown: Execute, Edit, Delete)

**Features**:
- Filter by tags
- Filter by scope
- Search by name
- "Create Test Suite" button
- Batch actions (future: execute multiple suites)

**Key Metrics Display**:
```tsx
<Badge color={suite.last_execution_status === 'completed' ? 'green' : 'red'}>
  {suite.last_successful_count}/{suite.total_usecases}
</Badge>
```

#### `CreateTestSuite.tsx` - Create/Edit Modal

**Purpose**: Create or edit test suite metadata.

**Form Fields**:
- Name (required, text input)
- Description (textarea)
- Scope (required, dropdown with user's writable scopes)
- Tags (token group, comma-separated)

**Validation**:
- Name: 3-100 characters
- Scope: Must be valid scope format `suite:*`
- User must have write access to selected scope

**Similar to**: `CreateUsecase.tsx` pattern

#### `TestSuiteDetail.tsx` - Detail View

**Purpose**: View and manage a single test suite.

**Layout Sections**:

1. **Header**:
   - Suite name and description
   - Scope badge
   - Tags
   - Edit button
   - Delete button

2. **Actions Bar**:
   - "Execute Suite" button (primary)
   - "Add Use Cases" button
   - "Configure Schedule" button

3. **Use Cases Table**:
   - Columns: Name, Scope, Status (from last run), Actions
   - Status shows result from last suite execution
   - Actions: View Details, Remove from Suite
   - Empty state: "No use cases added yet"

4. **Recent Executions**:
   - Table with last 10 executions
   - Columns: Started, Duration, Status, Success Rate, Trigger Type
   - Click row to view execution detail
   - "View All" link to full execution history

**Similar to**: `UsecaseDetailRefactored.tsx` layout

#### `AddUsecasesToSuite.tsx` - Modal

**Purpose**: Add use cases to a suite.

**Layout**:
- Multi-select table of available use cases
- Filter by name, tags, scope
- Shows which use cases are already in suite (disabled)
- Search bar
- "Add Selected" button

**Behavior**:
- Loads all use cases user has read access to
- Disables use cases already in suite
- Allows multi-select
- On confirm, calls API to add selected use cases

#### `ConfigureSchedule.tsx` - Modal

**Purpose**: Configure suite schedule.

**Form Fields**:
- Enable Schedule (toggle)
- Schedule Expression (cron input with helper)
- Timezone (dropdown)
- Next Run Preview (calculated from cron)

**Cron Helper**:
- Presets: "Every day at 9 AM", "Weekdays at 6 PM", "Every Monday at 8 AM"
- Custom cron expression input
- Validation and preview

#### `SuiteExecutionDetail.tsx` - Execution Status View

**Purpose**: Real-time status of suite execution.

**Layout**:

1. **Header**:
   - Suite name
   - Execution ID
   - Started timestamp
   - Duration (live updating if running)
   - Overall status (StatusIndicator)

2. **Progress Bar**:
   - Visual progress: completed/total tests
   - Color-coded: green (success), red (failed), blue (running)

3. **Summary Cards**:
   - Total Tests
   - Completed (with percentage)
   - Successful (green)
   - Failed (red)
   - Running (blue)

4. **Results Table**:
   - Columns: Use Case Name, Status, Started, Duration, Actions
   - Status: StatusIndicator with icon
   - Actions: View Details, View Recording
   - Sort by status (running first, then failed, then completed)
   - Real-time updates via polling

5. **Actions**:
   - "Stop Execution" button (if running)
   - "Re-run Suite" button (if completed)
   - "Export Results" button (future)

**Polling Logic**:
```tsx
useEffect(() => {
  if (execution.status === 'running') {
    const interval = setInterval(() => {
      fetchExecutionStatus();
    }, 5000); // Poll every 5 seconds
    
    return () => clearInterval(interval);
  }
}, [execution.status]);
```

**Similar to**: `ExecutionDetailRefactored.tsx` but for multiple use cases

### API Integration

Add to `frontend/src/utils/api.ts`:

```typescript
export const api = {
  // ... existing methods ...
  
  // Test Suites
  testSuites: {
    create: (data: CreateTestSuiteRequest) => 
      apiRequest('test-suites', { 
        method: 'POST', 
        body: JSON.stringify(data) 
      }),
    
    list: (params?: { tag?: string; scope?: string }) => 
      apiRequest(`test-suites${buildQueryString(params)}`),
    
    get: (suiteId: string) => 
      apiRequest(`test-suites/${suiteId}`),
    
    update: (suiteId: string, data: UpdateTestSuiteRequest) => 
      apiRequest(`test-suites/${suiteId}`, { 
        method: 'PUT', 
        body: JSON.stringify(data) 
      }),
    
    delete: (suiteId: string) => 
      apiRequest(`test-suites/${suiteId}`, { method: 'DELETE' }),
    
    // Use Cases
    addUsecases: (suiteId: string, usecaseIds: string[]) => 
      apiRequest(`test-suites/${suiteId}/usecases`, { 
        method: 'POST', 
        body: JSON.stringify({ usecase_ids: usecaseIds }) 
      }),
    
    listUsecases: (suiteId: string) => 
      apiRequest(`test-suites/${suiteId}/usecases`),
    
    removeUsecase: (suiteId: string, usecaseId: string) => 
      apiRequest(`test-suites/${suiteId}/usecases/${usecaseId}`, { 
        method: 'DELETE' 
      }),
    
    // Schedule
    updateSchedule: (suiteId: string, data: ScheduleConfig) => 
      apiRequest(`test-suites/${suiteId}/schedule`, { 
        method: 'PUT', 
        body: JSON.stringify(data) 
      }),
    
    // Execution
    execute: (suiteId: string) => 
      apiRequest(`test-suites/${suiteId}/execute`, { 
        method: 'POST', 
        body: JSON.stringify({ trigger_type: 'manual' }) 
      }),
    
    listExecutions: (suiteId: string, params?: { limit?: number; status?: string }) => 
      apiRequest(`test-suites/${suiteId}/executions${buildQueryString(params)}`),
    
    getExecution: (suiteId: string, executionId: string) => 
      apiRequest(`test-suites/${suiteId}/executions/${executionId}`),
    
    stopExecution: (suiteId: string, executionId: string) => 
      apiRequest(`test-suites/${suiteId}/executions/${executionId}/stop`, { 
        method: 'POST' 
      })
  }
};
```

### TypeScript Interfaces

```typescript
interface TestSuite {
  id: string;
  name: string;
  description: string;
  scope: string;
  tags: string[];
  created_at: string;
  updated_at: string;
  created_by: string;
  total_usecases: number;
  last_execution_id?: string;
  last_execution_status?: 'completed' | 'partial' | 'failed';
  last_execution_time?: string;
  last_successful_count?: number;
  schedule_expression?: string;
  schedule_enabled: boolean;
  schedule_timezone?: string;
}

interface SuiteExecution {
  id: string;
  suite_id: string;
  suite_name: string;
  suite_scope: string;
  status: 'pending' | 'running' | 'completed' | 'partial' | 'failed';
  started_at: string;
  completed_at?: string;
  duration_seconds?: number;
  triggered_by: string;
  trigger_type: 'manual' | 'scheduled';
  total_usecases: number;
  completed_usecases: number;
  successful_usecases: number;
  failed_usecases: number;
  running_usecases: number;
  results?: SuiteExecutionResult[];
}

interface SuiteExecutionResult {
  usecase_id: string;
  usecase_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  usecase_execution_id: string;
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  error_message?: string;
  recording_url?: string;
}

interface CreateTestSuiteRequest {
  name: string;
  description: string;
  scope: string;
  tags?: string[];
}

interface UpdateTestSuiteRequest {
  name?: string;
  description?: string;
  tags?: string[];
}

interface ScheduleConfig {
  schedule_expression: string;
  schedule_enabled: boolean;
  schedule_timezone?: string;
}
```


---

## Infrastructure Changes

### CDK Stack Updates

#### `lib/api-stack.ts`

Add new API Gateway routes:

```typescript
// Test Suites
const testSuites = this.addResource(this.api.root, 'test-suites')
this.addMethod(testSuites, HttpMethod.GET, l.listTestSuitesLambda)
this.addMethod(testSuites, HttpMethod.POST, l.createTestSuiteLambda)

const testSuite = this.addResource(testSuites, '{suite_id}')
this.addMethod(testSuite, HttpMethod.GET, l.getTestSuiteLambda)
this.addMethod(testSuite, HttpMethod.PUT, l.updateTestSuiteLambda)
this.addMethod(testSuite, HttpMethod.DELETE, l.deleteTestSuiteLambda)

// Suite Use Cases
const suiteUsecases = this.addResource(testSuite, 'usecases')
this.addMethod(suiteUsecases, HttpMethod.GET, l.listSuiteUsecasesLambda)
this.addMethod(suiteUsecases, HttpMethod.POST, l.addUsecasesToSuiteLambda)

const suiteUsecase = this.addResource(suiteUsecases, '{usecase_id}')
this.addMethod(suiteUsecase, HttpMethod.DELETE, l.removeUsecaseFromSuiteLambda)

// Suite Schedule
const suiteSchedule = this.addResource(testSuite, 'schedule')
this.addMethod(suiteSchedule, HttpMethod.PUT, l.updateSuiteScheduleLambda)

// Suite Execution
const suiteExecute = this.addResource(testSuite, 'execute')
this.addMethod(suiteExecute, HttpMethod.POST, l.executeSuiteLambda)

const suiteExecutions = this.addResource(testSuite, 'executions')
this.addMethod(suiteExecutions, HttpMethod.GET, l.listSuiteExecutionsLambda)

const suiteExecution = this.addResource(suiteExecutions, '{execution_id}')
this.addMethod(suiteExecution, HttpMethod.GET, l.getSuiteExecutionLambda)

const suiteExecutionStop = this.addResource(suiteExecution, 'stop')
this.addMethod(suiteExecutionStop, HttpMethod.POST, l.stopSuiteExecutionLambda)
```

#### `lib/lambda-stack.ts`

Create Lambda functions for all test suite operations:

```typescript
// Test Suite Management
this.createTestSuiteLambda = this.createPythonLambda({
  path: 'create_test_suite',
  environment: { TABLE_NAME: props.table.tableName }
});
props.table.grantReadWriteData(this.createTestSuiteLambda);

this.listTestSuitesLambda = this.createPythonLambda({
  path: 'list_test_suites',
  environment: { TABLE_NAME: props.table.tableName }
});
props.table.grantReadData(this.listTestSuitesLambda);

this.getTestSuiteLambda = this.createPythonLambda({
  path: 'get_test_suite',
  environment: { TABLE_NAME: props.table.tableName }
});
props.table.grantReadData(this.getTestSuiteLambda);

this.updateTestSuiteLambda = this.createPythonLambda({
  path: 'update_test_suite',
  environment: { TABLE_NAME: props.table.tableName }
});
props.table.grantReadWriteData(this.updateTestSuiteLambda);

this.deleteTestSuiteLambda = this.createPythonLambda({
  path: 'delete_test_suite',
  environment: { 
    TABLE_NAME: props.table.tableName,
    EVENTBRIDGE_RULE_PREFIX: props.baseName
  }
});
props.table.grantReadWriteData(this.deleteTestSuiteLambda);
// Grant EventBridge permissions
this.deleteTestSuiteLambda.addToRolePolicy(new PolicyStatement({
  actions: ['events:DeleteRule', 'events:RemoveTargets'],
  resources: [`arn:aws:events:${Stack.of(this).region}:${Stack.of(this).account}:rule/${props.baseName}-suite-*`]
}));

// Suite Use Case Management
this.addUsecasesToSuiteLambda = this.createPythonLambda({
  path: 'add_usecases_to_suite',
  environment: { TABLE_NAME: props.table.tableName }
});
props.table.grantReadWriteData(this.addUsecasesToSuiteLambda);

this.listSuiteUsecasesLambda = this.createPythonLambda({
  path: 'list_suite_usecases',
  environment: { TABLE_NAME: props.table.tableName }
});
props.table.grantReadData(this.listSuiteUsecasesLambda);

this.removeUsecaseFromSuiteLambda = this.createPythonLambda({
  path: 'remove_usecase_from_suite',
  environment: { TABLE_NAME: props.table.tableName }
});
props.table.grantReadWriteData(this.removeUsecaseFromSuiteLambda);

// Suite Scheduling
this.updateSuiteScheduleLambda = this.createPythonLambda({
  path: 'update_suite_schedule',
  environment: { 
    TABLE_NAME: props.table.tableName,
    EVENTBRIDGE_RULE_PREFIX: props.baseName,
    EXECUTE_SUITE_LAMBDA_ARN: '' // Set after creating execute lambda
  }
});
props.table.grantReadWriteData(this.updateSuiteScheduleLambda);
this.updateSuiteScheduleLambda.addToRolePolicy(new PolicyStatement({
  actions: ['events:PutRule', 'events:PutTargets', 'events:DisableRule', 'events:EnableRule'],
  resources: [`arn:aws:events:${Stack.of(this).region}:${Stack.of(this).account}:rule/${props.baseName}-suite-*`]
}));

// Suite Execution
this.executeSuiteLambda = this.createPythonLambda({
  path: 'execute_test_suite',
  timeout: Duration.minutes(5), // Longer timeout for spawning multiple tasks
  environment: { 
    TABLE_NAME: props.table.tableName,
    EXECUTE_USECASE_LAMBDA_ARN: props.executeUsecaseLambda.functionArn
  }
});
props.table.grantReadWriteData(this.executeSuiteLambda);
// Grant permission to invoke execute_usecase Lambda
props.executeUsecaseLambda.grantInvoke(this.executeSuiteLambda);

this.listSuiteExecutionsLambda = this.createPythonLambda({
  path: 'list_suite_executions',
  environment: { TABLE_NAME: props.table.tableName }
});
props.table.grantReadData(this.listSuiteExecutionsLambda);

this.getSuiteExecutionLambda = this.createPythonLambda({
  path: 'get_suite_execution',
  environment: { TABLE_NAME: props.table.tableName }
});
props.table.grantReadData(this.getSuiteExecutionLambda);

this.stopSuiteExecutionLambda = this.createPythonLambda({
  path: 'stop_suite_execution',
  environment: { 
    TABLE_NAME: props.table.tableName,
    CLUSTER_ARN: props.clusterArn
  }
});
props.table.grantReadWriteData(this.stopSuiteExecutionLambda);
this.stopSuiteExecutionLambda.addToRolePolicy(new PolicyStatement({
  actions: ['ecs:StopTask'],
  resources: ['*']
}));

// Update execute suite Lambda ARN in schedule Lambda
this.updateSuiteScheduleLambda.addEnvironment(
  'EXECUTE_SUITE_LAMBDA_ARN', 
  this.executeSuiteLambda.functionArn
);
```

### IAM Permissions

**DynamoDB Access**:
- All Lambda functions need read/write access to DynamoDB table
- Use existing managed policies from `storage-stack.ts`

**EventBridge Access**:
- `update_suite_schedule`: PutRule, PutTargets, EnableRule, DisableRule
- `delete_test_suite`: DeleteRule, RemoveTargets

**Lambda Invocation**:
- `execute_test_suite`: Invoke `execute_usecase` Lambda
- EventBridge rules: Invoke `execute_test_suite` Lambda

**ECS Access**:
- `stop_suite_execution`: StopTask permission

### EventBridge Rules

**Rule Naming Convention**:
```
{baseName}-suite-{suite_id}
```

**Rule Configuration**:
```typescript
{
  Name: `${baseName}-suite-${suite_id}`,
  ScheduleExpression: suite.schedule_expression, // e.g., "cron(0 9 * * MON-FRI)"
  State: suite.schedule_enabled ? 'ENABLED' : 'DISABLED',
  Targets: [{
    Arn: executeSuiteLambda.functionArn,
    Input: JSON.stringify({
      suite_id: suite.id,
      trigger_type: 'scheduled'
    })
  }]
}
```


---

## Security & Access Control

### Scope-Based Authorization

Test suites use OAuth scopes for fine-grained access control, independent of use case scopes.

#### Scope Format

**Suite Scopes** (NEW):
- `suite:smoke-tests:read` - View suite
- `suite:smoke-tests:write` - Create/edit/delete suite
- `suite:smoke-tests:execute` - Execute suite
- `suite:smoke-tests:*` - All permissions

**Use Case Scopes** (existing):
- `usecase:login:read` - View use case
- `usecase:login:write` - Edit use case
- `usecase:login:execute` - Execute use case

#### Adding Suite Scopes to Cognito

**Update User Pool Configuration**:

1. **Add Resource Server Scope** (if using Cognito Resource Server):
   - Resource Server Identifier: `test-suites`
   - Scopes: `read`, `write`, `execute`
   - Full scope format: `test-suites/suite:{suite-name}:read`

2. **Update Pre-Token Generation Lambda** (`lambdas/auth/pre_token_generation.py`):
   ```python
   # Add suite scopes based on user groups
   if 'qa-team' in user_groups:
       scopes.extend([
           'suite:smoke-tests:*',
           'suite:regression:*'
       ])
   
   if 'developers' in user_groups:
       scopes.extend([
           'suite:smoke-tests:read',
           'suite:smoke-tests:execute'
       ])
   ```

3. **Update Authorizer Lambda** (`lambdas/auth/authorizer.py`):
   - No changes needed - already passes scopes to Lambda context
   - Existing scope validation logic handles `suite:*` pattern

**Default Scope Mappings**:
- `admin` group → `suite:*:*` (all suites, all permissions)
- `qa-team` group → `suite:*:write` (all suites, write access)
- `developers` group → `suite:*:read` + `suite:*:execute` (view and execute)
- `viewers` group → `suite:*:read` (view only)

#### Authorization Matrix

| Operation | Required Scope | Additional Checks |
|-----------|---------------|-------------------|
| Create suite | `suite:{scope}:write` | User must have write on specified scope |
| List suites | `suite:*:read` | Filter by user's readable scopes |
| View suite | `suite:{suite_scope}:read` | - |
| Update suite | `suite:{suite_scope}:write` | - |
| Delete suite | `suite:{suite_scope}:write` | - |
| Add use case to suite | `suite:{suite_scope}:write` | User must have `usecase:{usecase_scope}:read` |
| Remove use case from suite | `suite:{suite_scope}:write` | - |
| List use cases in suite | `suite:{suite_scope}:read` | - |
| Configure schedule | `suite:{suite_scope}:write` | - |
| Execute suite | `suite:{suite_scope}:execute` | - |
| View execution | `suite:{suite_scope}:read` | - |
| Stop execution | `suite:{suite_scope}:execute` | - |

#### Implementation in Lambda Authorizer

Update `lambdas/auth/authorizer.py` to handle suite scopes:

```python
def generate_policy(principal_id, effect, resource, scopes):
    """Generate IAM policy with scopes in context"""
    return {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [{
                'Action': 'execute-api:Invoke',
                'Effect': effect,
                'Resource': resource
            }]
        },
        'context': {
            'scopes': json.dumps(scopes),  # Pass scopes to Lambda
            'user_id': principal_id
        }
    }
```

#### Scope Validation in Lambda Functions

Each Lambda function validates scopes:

```python
from utils import validate_scope_access

def handler(event, context):
    # Extract user scopes from authorizer context
    user_scopes = json.loads(event['requestContext']['authorizer']['scopes'])
    user_id = event['requestContext']['authorizer']['user_id']
    
    # Get suite
    suite = get_suite(suite_id)
    
    # Validate access
    validate_scope_access(user_scopes, suite['scope'], 'write')
    
    # Proceed with operation
    # ...
```

#### Cross-Scope Use Case Addition

When adding use cases to a suite, validate both scopes:

```python
def add_usecases_to_suite(event, context):
    user_scopes = json.loads(event['requestContext']['authorizer']['scopes'])
    suite_id = event['pathParameters']['suite_id']
    usecase_ids = json.loads(event['body'])['usecase_ids']
    
    # Validate write access to suite
    suite = get_suite(suite_id)
    validate_scope_access(user_scopes, suite['scope'], 'write')
    
    # Validate read access to each use case
    for usecase_id in usecase_ids:
        usecase = get_usecase(usecase_id)
        validate_scope_access(user_scopes, usecase['scope'], 'read')
    
    # Proceed with adding use cases
    # ...
```

### Audit Trail

All operations are logged with user context:

```python
logger.info(f"User {user_id} created suite {suite_id} with scope {suite['scope']}")
logger.info(f"User {user_id} added {len(usecase_ids)} use cases to suite {suite_id}")
logger.info(f"User {user_id} executed suite {suite_id}, execution_id: {execution_id}")
```

### Data Isolation

- Users can only see suites they have read access to
- List operations filter by user's scopes at application level
- DynamoDB queries don't inherently filter by scope (single-table design)
- Application-level filtering ensures data isolation

---

## Execution Flow

### Manual Execution Flow

1. **User Triggers Execution**
   - User clicks "Execute Suite" button in UI
   - Frontend calls `POST /test-suites/{suite_id}/execute`
   - Request includes `trigger_type: 'manual'`

2. **Suite Execution Initialization**
   - `execute_test_suite` Lambda validates user has execute permission
   - Creates suite execution record:
     ```
     pk: 'SUITE_EXECUTION#{suite_id}'
     sk: 'EXECUTION#{execution_id}'
     status: 'running'
     ```
   - Queries all use cases in suite

3. **Parallel Use Case Execution**
   - For each use case in suite:
     - Invoke `execute_usecase` Lambda asynchronously
     - Create execution result record:
       ```
       pk: 'SUITE_EXEC#{execution_id}'
       sk: 'RESULT#{usecase_id}'
       status: 'pending'
       ```
     - Store task ARN and usecase_execution_id
   - All invocations happen in parallel (no waiting)

4. **Return to User**
   - Lambda returns suite execution ID immediately
   - Frontend redirects to execution detail page
   - Status: "running"

5. **Real-Time Status Updates**
   - Frontend polls `GET /test-suites/{suite_id}/executions/{execution_id}` every 5 seconds
   - Returns current status and results for all use cases
   - Updates UI with live progress

6. **ECS Task State Changes**
   - As each use case execution completes, ECS emits state change event
   - `handle_task_state_change` Lambda processes event
   - Updates suite execution result:
     ```
     status: 'completed' or 'failed'
     completed_at: timestamp
     duration_seconds: calculated
     ```
   - Increments suite execution counters atomically

7. **Suite Completion**
   - When all use cases complete, `check_suite_completion` runs
   - Determines final status:
     - `completed`: All tests passed
     - `partial`: Some tests failed
     - `failed`: Suite-level error
   - Updates suite execution record
   - Updates denormalized fields on suite entity

8. **User Views Results**
   - Frontend displays final results
   - Shows success/failure for each use case
   - Links to individual execution details
   - Links to recordings

### Scheduled Execution Flow

1. **Schedule Configuration**
   - User configures schedule via UI
   - `update_suite_schedule` Lambda creates EventBridge rule
   - Rule targets `execute_test_suite` Lambda

2. **EventBridge Triggers**
   - At scheduled time, EventBridge invokes `execute_test_suite`
   - Event payload includes:
     ```json
     {
       "suite_id": "uuid",
       "trigger_type": "scheduled"
     }
     ```

3. **Execution Proceeds**
   - Same flow as manual execution
   - `triggered_by` set to "system"
   - `trigger_type` set to "scheduled"

4. **Notifications** (Future Enhancement)
   - On completion, send notification via SNS
   - Email/Slack with execution summary

### Stop Execution Flow

1. **User Stops Execution**
   - User clicks "Stop Execution" button
   - Frontend calls `POST /test-suites/{suite_id}/executions/{execution_id}/stop`

2. **Stop All Running Tasks**
   - `stop_suite_execution` Lambda queries all results with status='running'
   - For each running task:
     - Calls ECS StopTask API with task ARN
     - Updates result status to 'failed'
     - Sets error_message to "Stopped by user"

3. **Update Suite Status**
   - Updates suite execution status to 'partial' or 'failed'
   - Sets completed_at timestamp
   - Returns count of stopped tasks

4. **Frontend Updates**
   - Displays "Execution stopped" message
   - Shows final results for completed tests
   - Shows "Stopped" status for interrupted tests

### Error Handling

**Suite-Level Errors**:
- Cannot query use cases: Status = 'failed', error_message set
- Cannot invoke execute_usecase: Status = 'failed', error_message set
- DynamoDB errors: Status = 'failed', error_message set

**Use Case-Level Errors**:
- Individual test failures: Result status = 'failed', suite continues
- Task launch failures: Result status = 'failed', error_message set
- Timeout: Result status = 'failed', error_message = "Execution timeout"

**Resilience**:
- Suite execution continues even if individual tests fail
- Partial results are always available
- Users can retry failed tests individually


---

## Implementation Plan

### Phase 1: Backend Foundation (Week 1-2)

**Goal**: Core data model and API endpoints.

**Tasks**:
1. Create DynamoDB schema (no migration needed, new tables)
2. Implement Lambda functions:
   - `create_test_suite.py`
   - `list_test_suites.py`
   - `get_test_suite.py`
   - `update_test_suite.py`
   - `delete_test_suite.py`
   - `add_usecases_to_suite.py`
   - `list_suite_usecases.py`
   - `remove_usecase_from_suite.py`
3. Update `utils.py` with scope validation
4. Add API Gateway routes in `api-stack.ts`
5. Add Lambda definitions in `lambda-stack.ts`
6. Write unit tests for Lambda functions

**Deliverables**:
- Working CRUD API for test suites
- Use case management API
- Scope-based access control

**Testing**:
- Postman/curl tests for all endpoints
- Scope validation tests
- Error handling tests

### Phase 2: Execution Engine (Week 2-3)

**Goal**: Parallel execution and status tracking.

**Tasks**:
1. Implement execution Lambda functions:
   - `execute_test_suite.py`
   - `list_suite_executions.py`
   - `get_suite_execution.py`
   - `stop_suite_execution.py`
2. Modify `handle_task_state_change.py` for suite execution tracking
3. Add helper functions for suite completion detection
4. Add API Gateway routes for execution
5. Write integration tests

**Deliverables**:
- Working parallel execution
- Real-time status tracking
- Stop execution capability

**Testing**:
- Execute suite with 5 use cases
- Verify parallel execution
- Test failure scenarios (some tests fail)
- Test stop execution

### Phase 3: Frontend Implementation (Week 3-4)

**Goal**: User interface for test suites.

**Tasks**:
1. Create components:
   - `TestSuites.tsx` (list view)
   - `CreateTestSuite.tsx` (modal)
   - `TestSuiteDetail.tsx` (detail view)
   - `AddUsecasesToSuite.tsx` (modal)
   - `SuiteExecutionDetail.tsx` (execution status)
2. Add API integration in `api.ts`
3. Add TypeScript interfaces
4. Update navigation in `App.tsx`
5. Add routing for new pages
6. Implement polling for real-time updates

**Deliverables**:
- Complete UI for test suite management
- Execution monitoring interface
- Responsive design matching existing UI

**Testing**:
- Manual UI testing
- Create/edit/delete suites
- Add/remove use cases
- Execute suites and monitor status

### Phase 4: Scheduling (Week 4-5)

**Goal**: Automated scheduled execution.

**Tasks**:
1. Implement `update_suite_schedule.py`
2. Add EventBridge rule management
3. Create `ConfigureSchedule.tsx` component
4. Add cron expression validation and preview
5. Test scheduled execution
6. Add schedule status to suite list view

**Deliverables**:
- Working scheduled execution
- UI for schedule configuration
- Cron expression helper

**Testing**:
- Configure schedule with various cron expressions
- Verify EventBridge rule creation
- Test scheduled execution triggers
- Test enable/disable schedule

### Phase 5: Polish & Documentation (Week 5-6)

**Goal**: Production-ready feature.

**Tasks**:
1. Add error handling and user feedback
2. Optimize DynamoDB queries
3. Add loading states and skeletons
4. Write user documentation
5. Create demo video
6. Performance testing
7. Security audit
8. Add metrics and monitoring

**Deliverables**:
- Production-ready feature
- User documentation
- Performance benchmarks
- Security review completed

**Testing**:
- Load testing (large suites, many concurrent executions)
- Security testing (scope bypass attempts)
- Edge case testing
- User acceptance testing

### Rollout Strategy

**Week 6: Beta Release**
- Deploy to staging environment
- Invite select users for beta testing
- Gather feedback
- Fix critical bugs

**Week 7: Production Release**
- Deploy to production
- Announce feature to all users
- Monitor usage and errors
- Provide support

**Week 8: Iteration**
- Address user feedback
- Optimize based on usage patterns
- Plan future enhancements

### Success Metrics

**Adoption Metrics**:
- Number of test suites created
- Number of suite executions per day
- Average use cases per suite
- Percentage of users using test suites

**Performance Metrics**:
- Average suite execution time
- Parallel execution efficiency
- API response times
- Error rates

**Business Metrics**:
- Time saved vs. individual execution
- Reduction in manual test coordination
- Increase in test coverage
- User satisfaction score

### Future Enhancements

**Phase 6+ (Post-Launch)**:

1. **Advanced Execution Options**
   - Conditional execution (stop on first failure)
   - Dependency management between tests
   - Retry failed tests automatically

2. **Reporting & Analytics**
   - Suite execution history charts
   - Success rate trends
   - PDF/HTML report generation
   - Export to CSV

3. **Notifications**
   - Email notifications on completion
   - Slack integration
   - Webhook support
   - Custom notification rules

4. **Suite Templates**
   - Predefined suite templates
   - Clone suites
   - Import/export suites

5. **Advanced Scheduling**
   - Multiple schedules per suite
   - Conditional scheduling (only if changes detected)
   - Schedule dependencies (run after another suite)

6. **Collaboration Features**
   - Suite sharing across teams
   - Comments on suite executions
   - Tagging team members

7. **Performance Optimizations**
   - Caching frequently accessed suites
   - Batch operations for large suites
   - Optimistic UI updates

---

## Appendix

### Example Use Cases

**Smoke Test Suite**:
- Login
- Navigate to Dashboard
- Create Item
- View Item
- Logout
- **Schedule**: Every hour
- **Scope**: `suite:smoke-tests`

**Regression Test Suite**:
- All smoke tests
- Advanced search
- Bulk operations
- Export functionality
- Import functionality
- User management
- **Schedule**: Nightly at 2 AM
- **Scope**: `suite:regression`

**Pre-Deployment Suite**:
- Critical path tests
- Security tests
- Performance tests
- **Schedule**: On-demand only
- **Scope**: `suite:pre-deploy`

### Cron Expression Examples

- `0 9 * * MON-FRI` - Every weekday at 9 AM
- `0 */2 * * *` - Every 2 hours
- `0 0 * * *` - Daily at midnight
- `0 0 * * SUN` - Every Sunday at midnight
- `0 6,18 * * *` - Daily at 6 AM and 6 PM

### API Request Examples

**Create Suite**:
```bash
curl -X POST https://api.example.com/test-suites \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Smoke Tests",
    "description": "Critical path tests",
    "scope": "suite:smoke-tests",
    "tags": ["smoke", "critical"]
  }'
```

**Add Use Cases**:
```bash
curl -X POST https://api.example.com/test-suites/{suite_id}/usecases \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "usecase_ids": ["uuid1", "uuid2", "uuid3"]
  }'
```

**Execute Suite**:
```bash
curl -X POST https://api.example.com/test-suites/{suite_id}/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "trigger_type": "manual"
  }'
```

**Get Execution Status**:
```bash
curl https://api.example.com/test-suites/{suite_id}/executions/{execution_id} \
  -H "Authorization: Bearer $TOKEN"
```

### Database Query Examples

**List all suites**:
```python
response = table.query(
    KeyConditionExpression=Key('pk').eq('TEST_SUITES')
)
```

**List use cases in suite**:
```python
response = table.query(
    KeyConditionExpression=Key('pk').eq(f'SUITE#{suite_id}') & Key('sk').begins_with('USECASE#')
)
```

**Get suite execution with results**:
```python
# Get execution metadata
execution = table.get_item(
    Key={
        'pk': f'SUITE_EXECUTION#{suite_id}',
        'sk': f'EXECUTION#{execution_id}'
    }
)

# Get all results
results = table.query(
    KeyConditionExpression=Key('pk').eq(f'SUITE_EXEC#{execution_id}') & Key('sk').begins_with('RESULT#')
)
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-11 | Design Team | Initial comprehensive design document |

---

## Approval

This design document requires approval from:
- [ ] Engineering Lead
- [ ] Product Manager
- [ ] Security Team
- [ ] QA Lead

**Approved By**: _________________  
**Date**: _________________

---

*End of Document*
