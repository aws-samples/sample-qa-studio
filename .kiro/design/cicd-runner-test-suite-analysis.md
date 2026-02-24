# Test Suite Implementation Analysis (Branch: 102-feature-test-suites)

## Current Implementation Overview

The test suite feature is already implemented in branch `102-feature-test-suites` and provides the foundation for the CI/CD runner.

### Key Components

#### 1. Lambda Functions
- `execute_test_suite.py` - Executes all use cases in a suite in parallel
- `create_test_suite.py` - Creates new test suites
- `get_test_suite.py` - Retrieves test suite details
- `list_test_suites.py` - Lists all test suites
- `update_test_suite.py` - Updates test suite metadata
- `delete_test_suite.py` - Deletes test suites
- `add_usecases_to_suite.py` - Adds use cases to suite
- `remove_usecase_from_suite.py` - Removes use cases from suite
- `list_suite_usecases.py` - Lists use cases in suite
- `list_suite_executions.py` - Lists suite execution history
- `get_suite_execution.py` - Gets suite execution details
- `update_suite_schedule.py` - Manages suite scheduling

#### 2. DynamoDB Schema (Single-Table Design)

**Test Suite:**
- PK: `TEST_SUITES`
- SK: `SUITE#{suite_id}`
- Attributes: name, scope, created_at, etc.

**Suite-UseCase Mapping:**
- PK: `SUITE#{suite_id}`
- SK: `USECASE#{usecase_id}`
- Attributes: usecase_id, usecase_name, added_at

**Suite Execution:**
- PK: `SUITE_EXECUTION#{suite_id}`
- SK: `EXECUTION#{suite_execution_id}`
- Attributes: status, started_at, completed_at, total_usecases, successful_usecases, failed_usecases, running_usecases, triggered_by, trigger_type

**Suite Execution Result:**
- PK: `SUITE_EXEC#{suite_execution_id}`
- SK: `RESULT#{usecase_id}`
- Attributes: usecase_execution_id, status, task_arn, etc.

#### 3. Current Execution Flow

1. User calls `POST /api/test-suites/{suite_id}/execute`
2. Lambda validates scopes (`api/suite.write`)
3. Lambda creates suite execution record (status='running')
4. Lambda queries all use cases in suite
5. Lambda invokes `execute_usecase` Lambda for each use case **asynchronously**
6. Each `execute_usecase` invocation:
   - Creates usecase execution record
   - Spawns ECS task
   - Returns immediately
7. ECS tasks execute in parallel
8. EventBridge monitors task state changes
9. Lambda updates suite execution status as use cases complete

### Key Observations for CI/CD Runner

#### ✅ What's Already Built
1. **Test suite CRUD operations** - Complete
2. **Suite execution tracking** - Complete
3. **Parallel execution orchestration** - Via async Lambda invocations
4. **Suite-level status aggregation** - Tracks total/successful/failed/running counts
5. **OAuth scopes** - `api/suite.write` for execution
6. **Trigger types** - Supports 'manual' and 'scheduled'

#### ⚠️ What Needs Modification for CI/CD Runner

1. **`execute_test_suite.py` needs new trigger_type**:
   - Current: `manual`, `scheduled`
   - **Add**: `ci_runner`
   - When `ci_runner`: Skip Lambda invocations, return execution IDs immediately

2. **`execute_usecase.py` needs modification**:
   - Current: Always creates execution + spawns ECS task
   - **Add**: When `trigger_type='ci_runner'`: Create execution record only, skip ECS

3. **New endpoint needed**:
   - Current: `POST /api/test-suites/{suite_id}/execute` invokes Lambdas
   - **Add**: Support for overrides (base_url, variables, region, model_id) in request body
   - **Add**: Return all execution_ids for runner to manage

4. **Artifact endpoints**:
   - **New**: `POST /api/usecases/{usecase_id}/executions/{execution_id}/artifacts`
   - **New**: `POST /api/usecases/{usecase_id}/executions/{execution_id}/steps/{step_id}/artifacts`

5. **Status update endpoint**:
   - **New**: `PATCH /api/usecases/{usecase_id}/executions/{execution_id}/status`

### Integration Points

#### Current Flow (UI/Scheduled)
```
User → execute_test_suite Lambda → execute_usecase Lambda (async) → ECS Task
```

#### New Flow (CI/CD Runner)
```
Runner → execute_test_suite Lambda (trigger_type=ci_runner) → Returns execution IDs
Runner → Executes locally with Nova Act SDK
Runner → Updates status via PATCH endpoint
Runner → Uploads artifacts via POST endpoints
```

### Recommendations

1. **Extend existing `execute_test_suite.py`**:
   - Add `ci_runner` trigger type support
   - Accept overrides in request body
   - Create all execution records with overrides applied
   - Return execution IDs without invoking Lambdas

2. **Modify `execute_usecase.py`**:
   - Check for `trigger_type='ci_runner'` in query params
   - Skip ECS task creation when ci_runner
   - Apply overrides from request body

3. **Add new artifact endpoints**:
   - Reuse existing S3 bucket structure
   - Generate presigned URLs for direct upload
   - Associate artifacts with execution records

4. **Add status update endpoint**:
   - PATCH endpoint for partial updates
   - Update suite execution aggregates when usecase completes

### OAuth Scopes

Current scopes in test suite implementation:
- `api/suite.read` - Read test suites
- `api/suite.write` - Execute and modify test suites

For CI/CD runner, we need:
- `test-suites:read` - Read test suite definitions
- `test-suites:write` - Execute test suites and update suite execution status
- `usecases:read` - Read usecase definitions, variables, secrets
- `executions:read` - Read execution records and status
- `executions:write` - Update execution status and upload artifacts

**Note**: Scope naming convention may need alignment (`api/suite.write` vs `test-suites:write`)

### Next Steps

1. Review and align OAuth scope naming conventions
2. Extend `execute_test_suite.py` to support ci_runner trigger
3. Modify `execute_usecase.py` to support create-only mode
4. Implement artifact upload endpoints
5. Implement status update endpoint
6. Build CI/CD runner with Nova Act SDK

---

## Summary

The test suite feature provides a solid foundation for the CI/CD runner. The main work is:
- Adding `ci_runner` trigger type support
- Implementing override logic (base_url, variables)
- Adding artifact and status update endpoints
- Building the Docker runner itself

The existing parallel execution orchestration, suite tracking, and DynamoDB schema are already in place and can be reused with minimal modifications.
