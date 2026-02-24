# Design Document: Test Suites

## Overview

The Test Suites feature enables users to group multiple use cases into logical test suites and execute them as a batch with real-time status tracking. This feature provides parallel execution, scope-based access control, scheduled execution, and comprehensive metrics tracking.

### Key Capabilities

- Group use cases into logical test suites
- Execute all use cases in a suite in parallel
- Continue execution even if individual tests fail
- Track execution status for each use case independently
- Provide scope-based access control with suite-specific OAuth scopes
- Support scheduled execution per test suite
- Display suite metrics: total tests, success count, last run status

### Design Philosophy

The design follows these core principles:

1. **Parallel Execution**: All use cases execute simultaneously for faster results
2. **Failure Isolation**: Individual test failures don't block other tests
3. **Independent Scopes**: Test suites have their own OAuth scopes separate from use case scopes
4. **Many-to-Many Relationships**: Use cases can belong to multiple suites for maximum flexibility
5. **Real-Time Tracking**: Status updates propagate immediately through event-driven architecture

## Architecture

### System Components

```
┌─────────────┐
│   Frontend  │
│   (React)   │
└──────┬──────┘
       │ HTTPS
       ▼
┌─────────────┐
│ API Gateway │
│  + Lambda   │
│  Authorizer │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│         Lambda Functions            │
│  ┌──────────────────────────────┐  │
│  │ Suite Management             │  │
│  │ - create/list/get/update/    │  │
│  │   delete test suites         │  │
│  │ - add/remove use cases       │  │
│  └──────────────────────────────┘  │
│  ┌──────────────────────────────┐  │
│  │ Execution Management         │  │
│  │ - execute suite              │  │
│  │ - track status               │  │
│  │ - stop execution             │  │
│  └──────────────────────────────┘  │
│  ┌──────────────────────────────┐  │
│  │ Scheduling                   │  │
│  │ - configure schedule         │  │
│  │ - manage EventBridge rules   │  │
│  └──────────────────────────────┘  │
└─────────┬───────────────────────────┘
          │
          ▼
    ┌─────────────┐
    │  DynamoDB   │
    │   (Single   │
    │    Table)   │
    └─────────────┘
          ▲
          │
    ┌─────────────┐
    │ EventBridge │
    │   (Cron     │
    │  Schedules) │
    └─────────────┘
          │
          ▼
    ┌─────────────┐
    │ ECS Cluster │
    │  (Parallel  │
    │  Execution) │
    └─────────────┘
```

### Data Flow

**Suite Execution Flow**:
1. User triggers execution via API
2. Lambda creates suite execution record
3. Lambda spawns ECS tasks for all use cases in parallel
4. ECS tasks execute independently
5. Task state changes trigger EventBridge events
6. Event handler updates suite execution status
7. Frontend polls for status updates

**Scheduled Execution Flow**:
1. EventBridge rule triggers at scheduled time
2. Rule invokes execute_test_suite Lambda
3. Execution proceeds as manual execution
4. Results stored with trigger_type='scheduled'

## Components and Interfaces

### DynamoDB Schema

Following the existing single-table design pattern with `pk` (partition key) and `sk` (sort key).

#### Test Suite Entity

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

#### Suite-UseCase Mapping

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

#### Suite Execution Metadata

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

#### Suite Execution Result (per use case)

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

### API Endpoints

#### Test Suite Management

**POST /test-suites** - Create a new test suite
- Request: `{ name, description, scope (optional), tags }`
- Response: Created suite object
- Scope validation: User must have `api/suite.write` or `api/admin`
- Note: If scope not provided, auto-generated from suite name

**GET /test-suites** - List all test suites
- Query params: `tag` (optional filter)
- Response: Array of suite objects
- Scope validation: User must have `api/suite.read` or `api/admin`

**GET /test-suites/{suite_id}** - Get a specific test suite
- Response: Suite object with all metadata
- Scope validation: User must have `api/suite.read` or `api/admin`

**PUT /test-suites/{suite_id}** - Update test suite metadata
- Request: `{ name, description, tags }`
- Response: Updated suite object
- Scope validation: User must have `api/suite.write` or `api/admin`

**DELETE /test-suites/{suite_id}** - Delete a test suite
- Response: 204 No Content
- Scope validation: User must have `api/suite.write` or `api/admin`
- Also deletes all mappings and disables schedule

#### Use Case Management

**POST /test-suites/{suite_id}/usecases** - Add use cases to suite
- Request: `{ usecase_ids: ["uuid1", "uuid2"] }`
- Response: `{ added: 2, total_usecases: 8 }`
- Scope validation: User must have `api/suite.write` or `api/admin`

**GET /test-suites/{suite_id}/usecases** - List use cases in suite
- Response: Array of use case objects with metadata
- Scope validation: User must have `api/suite.read` or `api/admin`

**DELETE /test-suites/{suite_id}/usecases/{usecase_id}** - Remove use case
- Response: 204 No Content
- Scope validation: User must have `api/suite.write` or `api/admin`

#### Suite Scheduling

**PUT /test-suites/{suite_id}/schedule** - Configure suite schedule
- Request: `{ schedule_expression, schedule_enabled, schedule_timezone }`
- Response: Updated suite object
- Creates/updates EventBridge rule

#### Suite Execution

**POST /test-suites/{suite_id}/execute** - Execute all use cases in suite
- Request: `{ trigger_type: "manual" }`
- Response: `{ suite_execution_id, status, total_usecases, started_at }`
- Scope validation: User must have `api/suite.write` or `api/admin`
- Spawns all use case executions in parallel

**GET /test-suites/{suite_id}/executions** - List suite executions
- Query params: `limit`, `status` (optional)
- Response: Array of execution objects
- Scope validation: User must have `api/suite.read` or `api/admin`

**GET /test-suites/{suite_id}/executions/{execution_id}** - Get execution status
- Response: Execution object with results array
- Includes real-time status for all use cases
- Scope validation: User must have `api/suite.read` or `api/admin`

### Lambda Functions

#### Core CRUD Operations

**create_test_suite.py**
- Validates scope access
- Generates UUID
- Creates suite item in DynamoDB
- Returns created suite object

**list_test_suites.py**
- Queries `pk = 'TEST_SUITES'`
- Filters by user's accessible scopes
- Supports tag and scope query parameters
- Returns array of suite objects

**get_test_suite.py**
- Gets suite by ID
- Validates user has read access
- Returns suite object

**update_test_suite.py**
- Validates write access
- Updates metadata
- Updates timestamp
- Returns updated suite

**delete_test_suite.py**
- Validates write access
- Deletes suite item
- Deletes all mappings
- Disables schedule
- Returns 204

#### Use Case Management

**add_usecases_to_suite.py**
- Validates write access to suite
- For each use case:
  - Validates read access
  - Gets use case metadata
  - Creates mapping (idempotent)
- Updates total_usecases count
- Returns count of added use cases

**list_suite_usecases.py**
- Validates read access
- Queries mappings
- Returns array of use cases

**remove_usecase_from_suite.py**
- Validates write access
- Deletes mapping
- Decrements count
- Returns 204

#### Scheduling

**update_suite_schedule.py**
- Validates write access
- Updates schedule fields
- Creates/updates EventBridge rule
- Returns updated suite

#### Execution Management

**execute_test_suite.py**
- Validates execute access
- Creates suite execution record
- Queries all use cases in suite
- Invokes execute_usecase Lambda for each (parallel)
- Creates execution result records
- Returns suite execution ID

**list_suite_executions.py**
- Validates read access
- Queries executions
- Supports pagination and filtering
- Returns array of executions

**get_suite_execution.py**
- Validates read access
- Gets execution metadata
- Queries all results
- Returns execution with results

**stop_suite_execution.py**
- Validates execute access
- Queries running results
- Stops ECS tasks
- Updates result statuses
- Returns count of stopped tasks

#### Event Handler Integration

**Modify handle_task_state_change.py**

When ECS task state changes, check if it's part of a suite execution:

```python
def handler(event, context):
    # Existing logic for use case execution
    # ...
    
    # Check if this execution is part of a suite
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
        
        # Check if all tests complete
        check_suite_completion(result['suite_execution_id'])
```

### Scope Validation

**Scope Format**:
- Suite scopes: `api/suite.read`, `api/suite.write`
- Admin scope: `api/admin` (bypasses all checks)

**Validation Function** (in utils.py):

```python
def require_scopes(event, required_scopes):
    """
    Validate user has at least one of the required scopes.
    
    Args:
        event: API Gateway event with authorizer context
        required_scopes: List of acceptable scopes (e.g., ['api/suite.read'])
    
    Returns:
        Tuple of (user_identity dict, error_response or None)
        
    Notes:
        - Admin scope (api/admin) bypasses all other checks
        - Returns error response if user lacks required permissions
    """
    user_identity = extract_user_identity(event)
    user_scopes = user_identity.get('scopes', [])
    
    # Check for admin scope
    if 'api/admin' in user_scopes:
        return (user_identity, None)
    
    # Check if user has any of the required scopes
    for required_scope in required_scopes:
        if required_scope in user_scopes:
            return (user_identity, None)
    
    return (user_identity, create_response(403, {
        'error': f'Insufficient permissions. Required one of: {required_scopes}'
    }))
```

## Data Models

### TypeScript Interfaces (Frontend)

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
```

### Python Data Classes (Backend)

```python
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

@dataclass
class TestSuite:
    id: str
    name: str
    description: str
    scope: str
    created_at: str
    updated_at: str
    created_by: str
    tags: List[str]
    total_usecases: int
    schedule_enabled: bool
    schedule_expression: Optional[str] = None
    schedule_timezone: Optional[str] = None
    last_execution_id: Optional[str] = None
    last_execution_status: Optional[str] = None
    last_execution_time: Optional[str] = None
    last_successful_count: Optional[int] = None

@dataclass
class SuiteExecution:
    id: str
    suite_id: str
    suite_name: str
    suite_scope: str
    status: str
    started_at: str
    triggered_by: str
    trigger_type: str
    total_usecases: int
    completed_usecases: int
    successful_usecases: int
    failed_usecases: int
    running_usecases: int
    completed_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    error_message: Optional[str] = None
```


## Correctness Properties

A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

### Property 1: Suite CRUD Round Trip

*For any* valid test suite data (name, description, scope, tags), creating a suite then retrieving it should return an equivalent suite with all fields preserved and a valid unique identifier assigned.

**Validates: Requirements 1.1, 1.3**

### Property 2: Suite Update Persistence

*For any* existing test suite and valid update data, updating the suite then retrieving it should return the suite with the updated fields applied and an updated timestamp that is later than the original.

**Validates: Requirements 1.4**

### Property 3: Suite Deletion Cascade

*For any* test suite with use case mappings and an enabled schedule, deleting the suite should result in the suite, all its mappings, and its EventBridge rule being removed from the system.

**Validates: Requirements 1.5, 6.5**

### Property 4: Scope-Based Suite Filtering

*For any* set of test suites with different scopes and any user scope set, listing suites should return only those suites where the user has read access to the suite's scope.

**Validates: Requirements 1.2**

### Property 5: Use Case Mapping Creation

*For any* test suite and set of use case IDs, adding the use cases to the suite should create mappings for each use case with denormalized metadata (name, scope) and increment the suite's total_usecases count by the number of new mappings.

**Validates: Requirements 2.1, 10.2**

### Property 6: Use Case Mapping Idempotency

*For any* test suite and use case that is already in the suite, adding the use case again should not create duplicate mappings and should not change the total_usecases count.

**Validates: Requirements 2.2**

### Property 7: Use Case Mapping Removal

*For any* test suite with use case mappings, removing a use case should delete the mapping and decrement the total_usecases count by one.

**Validates: Requirements 2.4**

### Property 8: Many-to-Many Use Case Deletion

*For any* use case that belongs to multiple test suites, deleting the use case should remove it from all suites' mappings.

**Validates: Requirements 2.5, 10.1, 10.5**

### Property 9: Parallel Execution Initialization

*For any* test suite with N use cases, executing the suite should create N execution result records with status 'pending' and spawn N use case executions with timestamps within a small time window (indicating parallel execution).

**Validates: Requirements 3.1, 3.2**

### Property 10: Independent Result Updates

*For any* suite execution with multiple use case results, updating one result's status should not affect the status of other results in the same suite execution.

**Validates: Requirements 3.3**

### Property 11: Failure Isolation

*For any* suite execution where one use case fails, the other use cases should continue to completion with their own independent status outcomes.

**Validates: Requirements 3.4**

### Property 12: Suite Status Determination

*For any* suite execution where all use cases have completed, the suite execution status should be 'completed' if all use cases succeeded, 'partial' if some failed, and 'failed' only if a suite-level error occurred.

**Validates: Requirements 3.5, 4.4, 4.5**

### Property 13: Execution Counter Accuracy

*For any* suite execution at any point in time, the sum of completed_usecases, running_usecases, and pending_usecases should equal total_usecases, and completed_usecases should equal successful_usecases plus failed_usecases.

**Validates: Requirements 4.1, 4.2, 10.3**

### Property 14: Execution Status Query Completeness

*For any* suite execution, querying the execution status should return results for all use cases in the suite with their current status.

**Validates: Requirements 4.3**

### Property 15: Authorization Enforcement

*For any* operation (create, read, update, delete, execute) on a test suite, the operation should succeed only if the user has the required permission (write, read, write, write, execute respectively) on the suite's scope, otherwise an authorization error should be returned.

**Validates: Requirements 5.1, 5.2, 5.3, 5.5**

### Property 16: Cross-Resource Authorization

*For any* attempt to add a use case to a suite, the operation should succeed only if the user has write access to the suite's scope AND read access to the use case's scope.

**Validates: Requirements 5.4**

### Property 17: Schedule Configuration Persistence

*For any* test suite and valid schedule configuration (cron expression, enabled flag, timezone), configuring the schedule should create or update an EventBridge rule with the specified cron expression and enabled state.

**Validates: Requirements 6.1, 6.4**

### Property 18: Scheduled Execution Metadata

*For any* suite execution triggered by EventBridge, the execution record should have trigger_type set to 'scheduled'.

**Validates: Requirements 6.3**

### Property 19: Execution Metrics Denormalization

*For any* completed suite execution, the suite entity should have its last_execution_id, last_execution_status, last_execution_time, and last_successful_count fields updated to reflect the completed execution.

**Validates: Requirements 7.1, 7.4**

### Property 20: Suite List Metrics Presence

*For any* suite returned in a list operation, the suite object should include total_usecases, last_execution_status, and last_successful_count fields.

**Validates: Requirements 7.2**

### Property 21: Success Rate Calculation

*For any* suite execution, the success rate (last_successful_count / total_usecases) should accurately reflect the ratio of successful use cases to total use cases.

**Validates: Requirements 7.5**

### Property 22: Stop Execution Completeness

*For any* running suite execution, stopping the execution should stop all running ECS tasks, update all running results to 'failed' status with an error message, and return the count of stopped tasks.

**Validates: Requirements 8.1, 8.2, 8.3**

### Property 23: Stop Execution Status Update

*For any* suite execution that is stopped, the suite execution status should be updated to 'partial' or 'failed' based on whether any use cases completed successfully before stopping.

**Validates: Requirements 8.4**

### Property 24: Stop Execution Authorization

*For any* attempt to stop a suite execution, the operation should succeed only if the user has execute access to the suite's scope.

**Validates: Requirements 8.5**

### Property 25: Execution List Sort Order

*For any* set of suite executions, listing them should return the executions sorted by started_at timestamp in descending order (most recent first).

**Validates: Requirements 9.1**

### Property 26: Execution List Pagination

*For any* suite with more executions than the specified limit, listing executions with a limit should return exactly that number of executions.

**Validates: Requirements 9.2**

### Property 27: Execution List Filtering

*For any* suite with executions in different statuses, listing executions filtered by a specific status should return only executions matching that status.

**Validates: Requirements 9.3**

### Property 28: Execution Detail Completeness

*For any* suite execution, viewing the execution detail should return all use case results with their status, duration, and error messages (if any).

**Validates: Requirements 9.4, 9.5**

### Property 29: Partition Key Isolation

*For any* suite execution and use case execution created in the system, they should use different partition key prefixes ('SUITE_EXEC#' vs 'EXECUTION#') to avoid conflicts.

**Validates: Requirements 10.4**

## Error Handling

### Suite-Level Errors

**Cannot Query Use Cases**:
- Status: 'failed'
- Error message: "Failed to query use cases in suite"
- Suite execution record created but no use case executions spawned

**Cannot Invoke Execute UseCase Lambda**:
- Status: 'failed'
- Error message: "Failed to invoke use case execution"
- Partial execution results may exist for successfully invoked use cases

**DynamoDB Errors**:
- Status: 'failed'
- Error message: Specific DynamoDB error details
- Transaction rollback where applicable

### Use Case-Level Errors

**Individual Test Failures**:
- Result status: 'failed'
- Error message: Specific failure details from use case execution
- Suite continues executing other use cases

**Task Launch Failures**:
- Result status: 'failed'
- Error message: "Failed to launch ECS task"
- Other use cases continue

**Execution Timeout**:
- Result status: 'failed'
- Error message: "Execution timeout"
- Timeout value configurable per use case

**User Stopped Execution**:
- Result status: 'stopped'
- Treated as 'failed' for suite execution counter purposes
- Suite execution counters updated (completed_usecases +1, failed_usecases +1, running_usecases -1)
- Suite continues executing other use cases
- Suite completion check triggered when all use cases finish

### Authorization Errors

**Insufficient Permissions**:
- HTTP Status: 403 Forbidden
- Error message: "User lacks {permission} permission on {scope}"
- Operation not performed

**Invalid Scope Format**:
- HTTP Status: 400 Bad Request
- Error message: "Invalid scope format"
- Operation not performed

### Validation Errors

**Invalid Cron Expression**:
- HTTP Status: 400 Bad Request
- Error message: "Invalid cron expression format"
- Schedule not created/updated

**Use Case Not Found**:
- HTTP Status: 404 Not Found
- Error message: "Use case {id} not found"
- Mapping not created

**Suite Not Found**:
- HTTP Status: 404 Not Found
- Error message: "Test suite {id} not found"
- Operation not performed

## Testing Strategy

### Dual Testing Approach

The test suite feature requires both unit tests and property-based tests for comprehensive coverage:

**Unit Tests** focus on:
- Specific examples of suite creation, execution, and management
- Edge cases like empty suites, single use case suites
- Error conditions and authorization failures
- Integration points between Lambda functions and DynamoDB
- EventBridge rule creation and management

**Property-Based Tests** focus on:
- Universal properties that hold for all inputs
- CRUD operations with randomly generated suite data
- Concurrent execution scenarios with multiple use cases
- Authorization with various scope combinations
- Data integrity across cascading operations

### Property-Based Testing Configuration

**Testing Library**: Use `hypothesis` for Python backend tests

**Test Configuration**:
- Minimum 100 iterations per property test
- Each property test references its design document property
- Tag format: `# Feature: test-suites, Property {number}: {property_text}`

**Example Property Test Structure**:

```python
from hypothesis import given, strategies as st
import pytest

@given(
    suite_name=st.text(min_size=3, max_size=100),
    suite_description=st.text(max_size=500),
    suite_scope=st.from_regex(r'suite:[a-z-]+', fullmatch=True),
    suite_tags=st.lists(st.text(min_size=1, max_size=20), max_size=10)
)
def test_suite_crud_round_trip(suite_name, suite_description, suite_scope, suite_tags):
    """
    Feature: test-suites, Property 1: Suite CRUD Round Trip
    For any valid test suite data, creating then retrieving should return equivalent data.
    """
    # Create suite
    created_suite = create_test_suite(
        name=suite_name,
        description=suite_description,
        scope=suite_scope,
        tags=suite_tags
    )
    
    # Retrieve suite
    retrieved_suite = get_test_suite(created_suite['id'])
    
    # Verify all fields match
    assert retrieved_suite['name'] == suite_name
    assert retrieved_suite['description'] == suite_description
    assert retrieved_suite['scope'] == suite_scope
    assert retrieved_suite['tags'] == suite_tags
    assert 'id' in retrieved_suite
    assert 'created_at' in retrieved_suite
```

### Integration Testing

**Suite Execution Flow**:
1. Create test suite with multiple use cases
2. Execute suite
3. Verify all use case executions are created
4. Simulate use case completions
5. Verify suite execution status updates correctly
6. Verify denormalized metrics are updated

**Scheduled Execution Flow**:
1. Create suite with schedule
2. Verify EventBridge rule created
3. Simulate scheduled trigger
4. Verify execution created with trigger_type='scheduled'

**Authorization Flow**:
1. Create suites with different scopes
2. Test operations with various user scope combinations
3. Verify only authorized operations succeed

### Performance Testing

**Parallel Execution Scalability**:
- Test suites with 1, 5, 10, 20, 50 use cases
- Measure execution initialization time
- Verify all use cases start within acceptable time window

**Concurrent Suite Executions**:
- Execute multiple suites simultaneously
- Verify no resource contention
- Verify counter updates remain accurate

**Large Suite Management**:
- Create suites with 100+ use cases
- Measure query performance for listing use cases
- Verify pagination works correctly
