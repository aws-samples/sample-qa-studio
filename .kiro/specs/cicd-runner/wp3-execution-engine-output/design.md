# Work Package 3: Execution Engine & Output - Design Document

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP3 - Execution Engine & Output
- **Version**: 1.0
- **Status**: Design Phase
- **Dependencies**: WP2 (Runner Core & Authentication)

---

## Design Overview

This workpackage implements the test execution engine using Nova Act SDK to run all use cases in parallel locally with a bundled Chromium browser. The engine includes execution status updates via API, result aggregation, summary output formatting, and exit code logic.

### Key Design Principles
1. **Parallel Execution**: Execute all use cases simultaneously using asyncio
2. **Fault Isolation**: Individual test failures don't stop other tests
3. **Status Reporting**: Update execution status via API throughout the lifecycle
4. **Clear Output**: Provide readable summary tables with pass/fail counts
5. **Exit Codes**: Return appropriate exit codes for CI/CD pipeline control

---

## Architecture

### High-Level Flow

```
CI/CD Runner (main.py)
    ↓
1. Authenticate & fetch suite execution
2. Initialize ExecutionEngine
3. Execute all usecases in parallel
    ↓
ExecutionEngine
    ↓
For each usecase (parallel):
  - Update status to "running"
  - Fetch execution details
  - Execute with Nova Act SDK
  - Update status to "completed"/"failed"
  - Return result
    ↓
4. Aggregate results
5. Update suite execution status
6. Print summary table
7. Return exit code
```

### Component Interaction

```
┌─────────────────────────────────────────────────┐
│         main.py (Runner Orchestrator)           │
│                                                  │
│  1. Authenticate with OAuth                     │
│  2. Call execute_suite API                      │
│  3. Get suite_execution_id + execution_ids      │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│         ExecutionEngine                          │
│                                                  │
│  async execute_all(executions):                 │
│    - Create parallel tasks                      │
│    - await asyncio.gather()                     │
│    - Handle exceptions                          │
│    - Return results                             │
│                                                  │
│  async execute_usecase(execution):              │
│    - Update status to "running"                 │
│    - Fetch execution details                    │
│    - Execute with Nova Act                      │
│    - Update status to "completed"/"failed"      │
│    - Return result                              │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│         Nova Act SDK                             │
│                                                  │
│  - Initialize browser session (headless)        │
│  - Navigate to starting URL                     │
│  - Execute steps sequentially                   │
│  - Return success/failure                       │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│         ExecutionAPI                             │
│                                                  │
│  - update_status(execution_id, status)          │
│  - get_execution(execution_id)                  │
│  - update_suite_status(suite_execution_id)      │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│         Platform API (Backend)                   │
│                                                  │
│  - PATCH /executions/{id}/status                │
│  - GET /executions/{id}                         │
│  - PATCH /suite-executions/{id}/status          │
└─────────────────────────────────────────────────┘
```

---

## Components and Interfaces

### 1. Execution Engine (`src/execution/engine.py`)

**Purpose**: Orchestrate parallel execution of all use cases with Nova Act SDK

**Class Definition**:

```python
import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime
from nova_act_sdk import NovaActClient
from ..api.executions import ExecutionAPI
from ..utils.errors import ExecutionError

logger = logging.getLogger(__name__)

class ExecutionEngine:
    """Parallel test execution engine using Nova Act SDK."""
    
    def __init__(self, execution_api: ExecutionAPI):
        """
        Initialize execution engine.
        
        Args:
            execution_api: API client for execution operations
        """
        self.execution_api = execution_api
    
    async def execute_all(
        self,
        executions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute all use cases in parallel.
        
        Args:
            executions: List of execution records with metadata
        
        Returns:
            List of execution results with status and duration
        """
    
    async def execute_usecase(
        self,
        execution: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a single use case with Nova Act SDK.
        
        Args:
            execution: Execution record with usecase_id, execution_id, etc.
        
        Returns:
            Execution result with status, error, and duration
        """
    
    async def _execute_with_nova_act(
        self,
        execution_details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute test using Nova Act SDK.
        
        Args:
            execution_details: Full execution details with steps, variables, etc.
        
        Returns:
            Result dict with success flag and optional error message
        """
    
    async def _execute_step(
        self,
        session,
        step: Dict[str, Any],
        variables: Dict[str, str]
    ) -> None:
        """
        Execute a single test step with Nova Act.
        
        Args:
            session: Nova Act browser session
            step: Step definition with instruction
            variables: Variable substitutions
        
        Raises:
            ExecutionError: If step execution fails
        """
    
    def _replace_variables(
        self,
        text: str,
        variables: Dict[str, str]
    ) -> str:
        """
        Replace {{variable}} placeholders in text.
        
        Args:
            text: Text with variable placeholders
            variables: Variable substitutions
        
        Returns:
            Text with variables replaced
        """
```

**Implementation Details**:

```python
async def execute_all(self, executions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Execute all use cases in parallel."""
    logger.info(f"Starting parallel execution of {len(executions)} use cases...")
    
    # Create tasks for parallel execution
    tasks = [
        self.execute_usecase(execution)
        for execution in executions
    ]
    
    # Execute all in parallel, catching exceptions
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert exceptions to error results
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Execution {executions[i]['execution_id']} raised exception: {result}")
            processed_results.append({
                'execution_id': executions[i]['execution_id'],
                'usecase_id': executions[i]['usecase_id'],
                'usecase_name': executions[i]['usecase_name'],
                'status': 'failed',
                'error': str(result),
                'duration': 0
            })
        else:
            processed_results.append(result)
    
    return processed_results

async def execute_usecase(self, execution: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a single use case."""
    execution_id = execution['execution_id']
    usecase_id = execution['usecase_id']
    usecase_name = execution['usecase_name']
    
    logger.info(f"[{usecase_name}] Starting execution: {execution_id}")
    
    start_time = datetime.utcnow()
    
    try:
        # Update status to running
        await self.execution_api.update_status(
            usecase_id=usecase_id,
            execution_id=execution_id,
            status='running'
        )
        
        # Fetch execution details (steps, variables, etc.)
        execution_details = await self.execution_api.get_execution(
            usecase_id=usecase_id,
            execution_id=execution_id
        )
        
        # Execute with Nova Act SDK
        result = await self._execute_with_nova_act(execution_details)
        
        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Update status to completed/failed
        final_status = 'completed' if result['success'] else 'failed'
        await self.execution_api.update_status(
            usecase_id=usecase_id,
            execution_id=execution_id,
            status=final_status,
            error_message=result.get('error')
        )
        
        logger.info(f"[{usecase_name}] Completed: {'PASSED' if result['success'] else 'FAILED'} ({duration:.1f}s)")
        
        return {
            'execution_id': execution_id,
            'usecase_id': usecase_id,
            'usecase_name': usecase_name,
            'status': final_status,
            'error': result.get('error'),
            'duration': duration
        }
        
    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"[{usecase_name}] Failed: {str(e)}")
        
        # Update status to failed
        try:
            await self.execution_api.update_status(
                usecase_id=usecase_id,
                execution_id=execution_id,
                status='failed',
                error_message=str(e)
            )
        except Exception as api_error:
            logger.error(f"Failed to update status: {api_error}")
        
        return {
            'execution_id': execution_id,
            'usecase_id': usecase_id,
            'usecase_name': usecase_name,
            'status': 'failed',
            'error': str(e),
            'duration': duration
        }
```

### 2. Execution API (`src/api/executions.py`)

**Purpose**: API operations for execution status updates and fetching execution details

**Class Definition**:

```python
from typing import Dict, Any, Optional
from .client import APIClient

class ExecutionAPI:
    """Execution API operations."""
    
    def __init__(self, client: APIClient):
        """
        Initialize execution API.
        
        Args:
            client: Base API client with authentication
        """
        self.client = client
    
    async def get_execution(
        self,
        usecase_id: str,
        execution_id: str
    ) -> Dict[str, Any]:
        """
        Fetch execution details including steps and variables.
        
        Args:
            usecase_id: Usecase UUID
            execution_id: Execution UUID
        
        Returns:
            Execution details with steps, variables, starting_url, etc.
        
        Raises:
            APIError: If request fails
        """
    
    async def update_status(
        self,
        usecase_id: str,
        execution_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update execution status.
        
        Args:
            usecase_id: Usecase UUID
            execution_id: Execution UUID
            status: New status (pending, running, completed, failed)
            error_message: Optional error message for failed executions
        
        Returns:
            API response
        
        Raises:
            APIError: If request fails
        """
    
    async def update_suite_status(
        self,
        suite_id: str,
        suite_execution_id: str,
        status: str
    ) -> Dict[str, Any]:
        """
        Update suite execution status.
        
        Args:
            suite_id: Suite UUID
            suite_execution_id: Suite execution UUID
            status: New status (pending, running, completed, failed)
        
        Returns:
            API response
        
        Raises:
            APIError: If request fails
        """
```

**Implementation Notes**:
- Use existing `APIClient` for HTTP requests
- Convert synchronous `requests` calls to async using `asyncio.to_thread()`
- Handle API errors with descriptive messages

### 3. Summary Formatter (`src/output/summary.py`)

**Purpose**: Format execution results as readable ASCII table for console output

**Class Definition**:

```python
from typing import List, Dict, Any
from datetime import datetime

class SummaryFormatter:
    """Format execution summary for console output."""
    
    @staticmethod
    def format_table(
        suite_name: str,
        suite_execution_id: str,
        results: List[Dict[str, Any]],
        start_time: datetime,
        end_time: datetime
    ) -> str:
        """
        Format results as ASCII table.
        
        Args:
            suite_name: Test suite name
            suite_execution_id: Suite execution UUID
            results: List of execution results
            start_time: Suite execution start time
            end_time: Suite execution end time
        
        Returns:
            Formatted ASCII table string
        """
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """
        Format duration as human-readable string.
        
        Args:
            seconds: Duration in seconds
        
        Returns:
            Formatted duration (e.g., "45s", "2m 30s", "1h 15m")
        """
```

**Table Format**:

```
╔════════════════════════════════════════════════════════════╗
║           Nova Act QA Studio - CI/CD Runner                ║
╠════════════════════════════════════════════════════════════╣
║ Suite: Login Test Suite                                    ║
║ Suite Execution ID: 01933d7e-8f2a-7890-abcd-ef1234567890  ║
║ Started: 2024-02-16 12:00:00                              ║
║ Completed: 2024-02-16 12:05:30                            ║
║ Duration: 5m 30s                                           ║
╠════════════════════════════════════════════════════════════╣
║ Use Case                          Status      Duration     ║
╠════════════════════════════════════════════════════════════╣
║ Login with valid credentials      ✓ PASSED    45s         ║
║ Login with invalid password       ✓ PASSED    30s         ║
║ Login with missing username       ✗ FAILED    15s         ║
║ Password reset flow               ✓ PASSED    120s        ║
╠════════════════════════════════════════════════════════════╣
║ Total: 4  |  Passed: 3  |  Failed: 1  |  Success: 75%    ║
╚════════════════════════════════════════════════════════════╝
```

### 4. Exit Code Logic (`src/main.py`)

**Purpose**: Determine appropriate exit code based on execution results

**Function Definition**:

```python
def determine_exit_code(results: List[Dict[str, Any]]) -> int:
    """
    Determine exit code based on execution results.
    
    Args:
        results: List of execution results
    
    Returns:
        Exit code:
        - 0: All tests passed
        - 1: One or more tests failed
        - 2: Runner error (no results)
    """
    if not results:
        return 2  # Error: no results
    
    failed = sum(1 for r in results if r['status'] == 'failed')
    
    if failed == 0:
        return 0  # Success: all passed
    else:
        return 1  # Failure: one or more failed
```

---

## Data Models

### Execution Record (from API)

**Structure**:
```python
{
    'execution_id': str,          # UUIDv7
    'usecase_id': str,            # UUID
    'usecase_name': str,          # Display name
    'suite_execution_id': str,    # Parent suite execution UUID
    'suite_id': str,              # Parent suite UUID
    'status': str,                # pending | running | completed | failed
    'starting_url': str,          # URL with overrides applied
    'executing_region': str,      # AWS region
    'model_id': str,              # Bedrock model ID
    'created_at': str,            # ISO8601 timestamp
    'started_at': str,            # ISO8601 timestamp (optional)
    'completed_at': str,          # ISO8601 timestamp (optional)
    'error_message': str          # Error details (optional)
}
```

### Execution Details (from API)

**Structure**:
```python
{
    'execution_id': str,
    'usecase_id': str,
    'starting_url': str,
    'executing_region': str,
    'model_id': str,
    'steps': List[{
        'step_id': str,
        'step_number': int,
        'instruction': str,        # May contain {{variables}}
        'status': str
    }],
    'variables': Dict[str, str],  # Merged variables
    'hooks': List[Dict[str, Any]],
    'headers': Dict[str, str]
}
```

### Execution Result (internal)

**Structure**:
```python
{
    'execution_id': str,
    'usecase_id': str,
    'usecase_name': str,
    'status': str,                # completed | failed
    'error': Optional[str],       # Error message if failed
    'duration': float             # Duration in seconds
}
```

---

## Error Handling

### Error Categories

#### 1. Nova Act SDK Errors

**Scenario**: Nova Act fails to execute a step

**Causes**:
- Element not found
- Timeout waiting for element
- Navigation failure
- Browser crash

**Handling**:
- Catch exception in `_execute_with_nova_act()`
- Return `{'success': False, 'error': str(e)}`
- Update execution status to 'failed' with error message
- Continue with other executions (don't stop)

**Example**:
```python
try:
    result = await session.execute(instruction)
    if not result.success:
        raise ExecutionError(f"Step failed: {result.error}")
except Exception as e:
    return {
        'success': False,
        'error': f"Step {step['step_number']} failed: {str(e)}"
    }
```

#### 2. API Communication Errors

**Scenario**: API request fails during execution

**Causes**:
- Network timeout
- API returns 500 error
- Authentication token expired

**Handling**:
- Log error details
- Continue execution (don't fail test due to status update failure)
- Return result with error noted in logs

**Example**:
```python
try:
    await self.execution_api.update_status(
        usecase_id=usecase_id,
        execution_id=execution_id,
        status='failed',
        error_message=str(e)
    )
except Exception as api_error:
    logger.error(f"Failed to update status: {api_error}")
    # Continue - don't fail test due to status update failure
```

#### 3. Parallel Execution Errors

**Scenario**: One or more executions raise unhandled exceptions

**Handling**:
- Use `asyncio.gather(*tasks, return_exceptions=True)`
- Convert exceptions to error results
- Log exception details
- Continue with other executions

**Example**:
```python
results = await asyncio.gather(*tasks, return_exceptions=True)

for i, result in enumerate(results):
    if isinstance(result, Exception):
        logger.error(f"Execution raised exception: {result}")
        processed_results.append({
            'execution_id': executions[i]['execution_id'],
            'status': 'failed',
            'error': str(result),
            'duration': 0
        })
```

#### 4. Variable Substitution Errors

**Scenario**: Variable placeholder not found in variables dict

**Handling**:
- Should not occur (validated in WP1b)
- If occurs, log warning and leave placeholder unchanged
- Test will likely fail due to invalid instruction

**Example**:
```python
def _replace_variables(self, text: str, variables: Dict[str, str]) -> str:
    """Replace {{variable}} placeholders."""
    import re
    
    def replace(match):
        var_name = match.group(1)
        if var_name in variables:
            return variables[var_name]
        else:
            logger.warning(f"Variable not found: {var_name}")
            return match.group(0)  # Leave unchanged
    
    return re.sub(r'\{\{(\w+)\}\}', replace, text)
```

### Error Messages

**Clear and Actionable**:
- Include context (usecase name, step number)
- Include error type and details
- Suggest potential fixes when possible

**Examples**:
```
[Login Test] Failed: Step 3 failed: Element not found: #username
[Password Reset] Failed: Navigation timeout: https://example.com/reset
[Checkout Flow] Failed: Browser crashed during execution
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/test_execution_engine.py`

**Test Coverage Target**: ≥70%

**Test Classes**:

```python
class TestExecutionEngine:
    """Test execution engine orchestration"""
    
    def test_execute_all_creates_parallel_tasks(self):
        """Verify tasks created for all executions"""
    
    def test_execute_all_handles_exceptions(self):
        """Verify exceptions converted to error results"""
    
    def test_execute_usecase_updates_status_to_running(self):
        """Verify status updated at start"""
    
    def test_execute_usecase_updates_status_to_completed(self):
        """Verify status updated on success"""
    
    def test_execute_usecase_updates_status_to_failed(self):
        """Verify status updated on failure"""
    
    def test_execute_usecase_calculates_duration(self):
        """Verify duration calculated correctly"""

class TestNovaActIntegration:
    """Test Nova Act SDK integration"""
    
    def test_execute_with_nova_act_success(self):
        """Verify successful execution with Nova Act"""
    
    def test_execute_with_nova_act_step_failure(self):
        """Verify step failure handling"""
    
    def test_execute_step_replaces_variables(self):
        """Verify variable substitution in steps"""
    
    def test_execute_step_handles_nova_act_error(self):
        """Verify Nova Act errors handled gracefully"""

class TestSummaryFormatter:
    """Test summary output formatting"""
    
    def test_format_table_structure(self):
        """Verify table structure correct"""
    
    def test_format_table_includes_all_results(self):
        """Verify all results included in table"""
    
    def test_format_table_calculates_statistics(self):
        """Verify pass/fail counts correct"""
    
    def test_format_duration_seconds(self):
        """Verify duration formatting for seconds"""
    
    def test_format_duration_minutes(self):
        """Verify duration formatting for minutes"""
    
    def test_format_duration_hours(self):
        """Verify duration formatting for hours"""

class TestExitCodeLogic:
    """Test exit code determination"""
    
    def test_exit_code_0_all_passed(self):
        """Verify exit code 0 when all tests pass"""
    
    def test_exit_code_1_some_failed(self):
        """Verify exit code 1 when tests fail"""
    
    def test_exit_code_2_no_results(self):
        """Verify exit code 2 when no results"""
```

### Integration Tests

**Test Scenarios**:

1. **Execute single usecase end-to-end**
   - Create execution record via API
   - Execute with Nova Act SDK
   - Verify status updates sent
   - Verify result returned

2. **Execute multiple usecases in parallel**
   - Create 3 execution records
   - Execute in parallel
   - Verify all complete
   - Verify results aggregated

3. **Execute with failing test**
   - Create execution with invalid step
   - Execute and expect failure
   - Verify status updated to 'failed'
   - Verify error message included

4. **Execute with Nova Act error**
   - Mock Nova Act to raise exception
   - Execute and expect failure
   - Verify error handled gracefully
   - Verify other tests continue

5. **Verify summary output format**
   - Execute multiple tests
   - Generate summary
   - Verify table format correct
   - Verify statistics accurate

6. **Verify exit codes**
   - Execute all passing tests → exit 0
   - Execute with failures → exit 1
   - Execute with no results → exit 2

### Manual Testing Checklist

- [ ] Deploy runner with Nova Act SDK
- [ ] Create test suite with 3 usecases
- [ ] Execute suite via runner
- [ ] Verify parallel execution (check logs)
- [ ] Verify status updates in DynamoDB
- [ ] Verify summary table printed
- [ ] Verify exit code correct
- [ ] Test with failing usecase
- [ ] Test with Nova Act error
- [ ] Verify verbose logging works

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


Before writing the correctness properties, I need to perform prework analysis on the acceptance criteria from the requirements document.

### Property Reflection

After analyzing the acceptance criteria, I identified several properties that can be consolidated:

**Redundancy Analysis**:
- US2.1 (status to "running") and US2.2 (status to "completed"/"failed") can be combined into a single property about status lifecycle
- US2.4 (status updates for each execution) is implied by US2.1 and US2.2 - if every execution gets running/completed updates, then all executions get updates
- US4.1 (exit 0 all pass) and US4.2 (exit 1 some fail) are complementary but both needed - they test different conditions
- US3.1 (table shows all results) and US3.5 (includes suite ID) can be combined into a single property about summary completeness

**Properties to Write**:
1. Parallel execution (US1.1)
2. Session isolation (US1.2)
3. Fault isolation (US1.3)
4. Result completeness (US1.4)
5. Status lifecycle (US2.1, US2.2, US2.4 combined)
6. Error message inclusion (US2.3)
7. Suite status update (US2.5)
8. Summary completeness (US3.1, US3.5 combined)
9. Statistics calculation (US3.2)
10. Exit code for success (US4.1)
11. Exit code for failure (US4.2)
12. Exit code for error (US4.3)

### Property 1: Parallel Execution

*For any* list of N executions, when `execute_all()` is called, all N executions should start within a small time window (< 1 second), demonstrating that they are executed concurrently rather than sequentially.

**Validates: Requirements US1.1**

### Property 2: Session Isolation

*For any* two executions running in parallel, state changes in one Nova Act session (cookies, local storage, navigation) should not affect the other session, ensuring complete isolation between test executions.

**Validates: Requirements US1.2**

### Property 3: Fault Isolation

*For any* list of N executions where at least one execution fails, all N executions should complete and return results, demonstrating that individual failures do not stop other executions from running.

**Validates: Requirements US1.3**

### Property 4: Result Completeness

*For any* list of N executions passed to `execute_all()`, exactly N results should be returned, where each result corresponds to one execution (even if exceptions occurred).

**Validates: Requirements US1.4**

### Property 5: Status Lifecycle

*For any* execution, the status should transition from "pending" → "running" → ("completed" | "failed"), with API calls made at each transition, and the final status should never remain as "running" after execution completes.

**Validates: Requirements US2.1, US2.2, US2.4**

### Property 6: Error Message Inclusion

*For any* execution that completes with status="failed", the status update API call should include an error_message field containing a non-empty string describing the failure.

**Validates: Requirements US2.3**

### Property 7: Suite Status Update

*For any* suite execution where all usecase executions have completed, the suite execution status should be updated via API to reflect the overall result (completed if all passed, failed if any failed).

**Validates: Requirements US2.5**

### Property 8: Summary Completeness

*For any* list of N execution results, the formatted summary table should include all N results with their usecase names, statuses, and durations, and should also include the suite_execution_id in the header.

**Validates: Requirements US3.1, US3.5**

### Property 9: Statistics Calculation

*For any* list of execution results, the summary statistics should correctly calculate: total count = N, passed count = number with status="completed", failed count = number with status="failed", and success percentage = (passed / total) * 100.

**Validates: Requirements US3.2**

### Property 10: Exit Code for Success

*For any* list of execution results where all results have status="completed", the `determine_exit_code()` function should return 0.

**Validates: Requirements US4.1**

### Property 11: Exit Code for Failure

*For any* list of execution results where at least one result has status="failed", the `determine_exit_code()` function should return 1.

**Validates: Requirements US4.2**

### Property 12: Exit Code for Error

*For any* empty list of execution results (indicating a runner error), the `determine_exit_code()` function should return 2.

**Validates: Requirements US4.3**

---

## Dependencies

### Python Packages

**Required Dependencies** (add to `qa-studio-ci-runner/requirements.txt`):

```
nova-act-sdk>=1.0.0
playwright>=1.40.0
asyncio>=3.4.3
aiohttp>=3.9.0
```

**Development Dependencies** (add to `qa-studio-ci-runner/requirements-dev.txt`):

```
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-mock>=3.12.0
hypothesis>=6.92.0
```

### Nova Act SDK

**Installation**:
```bash
pip install nova-act-sdk
```

**Bundled Browser**:
- Nova Act SDK includes Playwright with bundled Chromium
- No separate browser installation required
- Chromium version managed by Nova Act SDK

**Configuration**:
- Region: AWS region for Bedrock API calls
- Model ID: Bedrock model identifier (e.g., `us.anthropic.claude-3-5-sonnet-20241022-v2:0`)
- Headless mode: Always true for CI/CD

### API Endpoints

**Required Endpoints** (from WP1):
- `GET /usecase/{id}/executions/{executionId}` - Fetch execution details
- `PATCH /usecase/{id}/executions/{executionId}/status` - Update execution status
- `PATCH /test-suites/{id}/executions/{executionId}/status` - Update suite status

**Authentication**:
- OAuth client credentials flow (implemented in WP2)
- Required scopes: `api/execution.read`, `api/execution.write`

---

## Performance Considerations

### Parallel Execution

**Concurrency**:
- Use `asyncio.gather()` for parallel execution
- No limit on concurrent executions (all run simultaneously)
- Each execution is independent (no shared state)

**Resource Usage**:
- Each execution spawns a Chromium browser instance
- Memory: ~100-200 MB per browser instance
- CPU: Depends on test complexity
- Recommendation: Limit to 10-20 parallel executions on typical CI/CD runners

**Optimization Opportunities**:
- Add `--max-parallel` CLI flag to limit concurrency
- Implement semaphore to control browser instance count
- Monitor system resources and adjust dynamically

### API Rate Limiting

**Status Updates**:
- 2 API calls per execution (running, completed/failed)
- 1 API call per suite (suite status update)
- Total: 2N + 1 API calls for N executions

**Throttling**:
- No throttling implemented (API should handle burst)
- If rate limiting becomes an issue, implement exponential backoff
- Consider batching status updates (future enhancement)

### Browser Performance

**Headless Mode**:
- Always run in headless mode for CI/CD
- Reduces memory usage by ~30%
- Faster startup time

**Browser Reuse**:
- Current design: New browser per execution
- Future enhancement: Browser pool with page isolation
- Trade-off: Complexity vs resource usage

---

## Security Considerations

### Credentials Management

**OAuth Tokens**:
- Tokens cached in `.token_cache.json` (implemented in WP2)
- Tokens expire after 1 hour
- Automatic refresh on expiration

**Secrets in Variables**:
- Variables may contain sensitive data (passwords, API keys)
- Never log variable values
- Redact variables in error messages

**Example**:
```python
# BAD: Logs sensitive data
logger.info(f"Executing with variables: {variables}")

# GOOD: Logs variable keys only
logger.info(f"Executing with variables: {list(variables.keys())}")
```

### Browser Security

**Isolation**:
- Each execution runs in separate browser instance
- No shared cookies or local storage
- No cross-execution data leakage

**Network Access**:
- Browser has full network access (required for testing)
- No network isolation or sandboxing
- Tests can access any URL

### Error Message Sanitization

**Sensitive Data in Errors**:
- Nova Act errors may include page content
- Page content may include sensitive data
- Sanitize error messages before logging/storing

**Example**:
```python
def sanitize_error(error_message: str) -> str:
    """Remove potentially sensitive data from error messages."""
    # Remove URLs with query parameters
    error_message = re.sub(r'https?://[^\s]+\?[^\s]+', '[URL]', error_message)
    # Remove email addresses
    error_message = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', error_message)
    return error_message
```

---

## Monitoring & Observability

### Logging

**Log Levels**:
- INFO: Execution start/complete, status updates
- DEBUG: Step-by-step execution details (verbose mode)
- ERROR: Execution failures, API errors
- WARNING: Recoverable errors, missing variables

**Log Format**:
```python
logger.info(f"[{usecase_name}] Starting execution: {execution_id}")
logger.info(f"[{usecase_name}] Completed: {'PASSED' if success else 'FAILED'} ({duration:.1f}s)")
logger.error(f"[{usecase_name}] Failed: {error_message}")
```

**Structured Logging** (future enhancement):
```python
logger.info("execution_started", extra={
    'usecase_id': usecase_id,
    'execution_id': execution_id,
    'usecase_name': usecase_name
})
```

### Metrics

**Execution Metrics**:
- Total executions
- Passed executions
- Failed executions
- Average duration
- Success rate

**Performance Metrics**:
- Parallel execution count
- API call latency
- Browser startup time
- Total suite duration

**Implementation** (future enhancement):
```python
import time

class MetricsCollector:
    def __init__(self):
        self.metrics = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'durations': []
        }
    
    def record_result(self, result: Dict[str, Any]):
        self.metrics['total'] += 1
        if result['status'] == 'completed':
            self.metrics['passed'] += 1
        else:
            self.metrics['failed'] += 1
        self.metrics['durations'].append(result['duration'])
    
    def get_summary(self) -> Dict[str, Any]:
        return {
            'total': self.metrics['total'],
            'passed': self.metrics['passed'],
            'failed': self.metrics['failed'],
            'success_rate': self.metrics['passed'] / self.metrics['total'] if self.metrics['total'] > 0 else 0,
            'avg_duration': sum(self.metrics['durations']) / len(self.metrics['durations']) if self.metrics['durations'] else 0
        }
```

### Error Tracking

**Error Categories**:
- Nova Act errors (element not found, timeout)
- API errors (network, authentication)
- Runner errors (configuration, initialization)

**Error Reporting**:
- Log all errors with full stack traces
- Include execution context (usecase_id, execution_id)
- Aggregate errors for summary

---

## Implementation Notes

### Async/Await Pattern

**Converting Sync to Async**:
- Existing `APIClient` uses synchronous `requests` library
- Need to convert to async for parallel execution
- Use `asyncio.to_thread()` to wrap sync calls

**Example**:
```python
async def update_status(self, usecase_id: str, execution_id: str, status: str):
    """Update execution status (async wrapper)."""
    return await asyncio.to_thread(
        self.client.patch,
        f"/usecase/{usecase_id}/executions/{execution_id}/status",
        data={'status': status}
    )
```

**Alternative**: Use `aiohttp` for true async HTTP (future enhancement)

### Nova Act SDK Usage

**Basic Pattern**:
```python
from nova_act_sdk import NovaActClient

async def execute_with_nova_act(execution_details):
    client = NovaActClient(
        region=execution_details['executing_region'],
        model_id=execution_details['model_id']
    )
    
    async with client.browser_session(headless=True) as session:
        await session.goto(execution_details['starting_url'])
        
        for step in execution_details['steps']:
            result = await session.execute(step['instruction'])
            if not result.success:
                return {'success': False, 'error': result.error}
        
        return {'success': True}
```

**Error Handling**:
- Nova Act raises exceptions for browser errors
- Catch and convert to result dict
- Include step number in error message

### Variable Substitution

**Pattern**:
```python
import re

def replace_variables(text: str, variables: Dict[str, str]) -> str:
    """Replace {{variable}} placeholders."""
    def replace(match):
        var_name = match.group(1)
        return variables.get(var_name, match.group(0))
    
    return re.sub(r'\{\{(\w+)\}\}', replace, text)
```

**Application**:
- Apply to step instructions before execution
- Variables already merged in WP1b (secrets < usecase < CLI)
- Should not have unresolved variables (validated in WP1b)

---

## Future Enhancements

### Artifact Upload (WP4)

**Integration Points**:
- After execution completes, upload artifacts
- Recording: Browser recording of entire execution
- Logs: Execution logs and Nova Act logs
- Screenshots: Per-step screenshots
- Traces: Browser traces for debugging

**Implementation**:
```python
async def execute_usecase(self, execution: Dict[str, Any]) -> Dict[str, Any]:
    # ... existing execution logic ...
    
    # Upload artifacts (WP4)
    if recording_file:
        await self.artifact_uploader.upload_recording(execution_id, recording_file)
    if log_file:
        await self.artifact_uploader.upload_logs(execution_id, log_file)
    
    return result
```

### Retry Logic

**Automatic Retries**:
- Retry failed executions automatically
- Configurable retry count (default: 0)
- Exponential backoff between retries

**Implementation**:
```python
async def execute_usecase_with_retry(self, execution: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
    for attempt in range(max_retries + 1):
        result = await self.execute_usecase(execution)
        if result['status'] == 'completed':
            return result
        if attempt < max_retries:
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    return result
```

### Parallel Execution Limits

**Concurrency Control**:
- Add `--max-parallel` CLI flag
- Use semaphore to limit concurrent executions
- Prevents resource exhaustion

**Implementation**:
```python
async def execute_all(self, executions: List[Dict[str, Any]], max_parallel: int = 10) -> List[Dict[str, Any]]:
    semaphore = asyncio.Semaphore(max_parallel)
    
    async def execute_with_semaphore(execution):
        async with semaphore:
            return await self.execute_usecase(execution)
    
    tasks = [execute_with_semaphore(e) for e in executions]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

### Real-time Progress Updates

**Live Progress Display**:
- Show progress bar during execution
- Update as tests complete
- Display current test being executed

**Implementation** (using `rich` library):
```python
from rich.progress import Progress

async def execute_all_with_progress(self, executions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    with Progress() as progress:
        task = progress.add_task("[cyan]Executing tests...", total=len(executions))
        
        results = []
        for execution in executions:
            result = await self.execute_usecase(execution)
            results.append(result)
            progress.update(task, advance=1)
        
        return results
```

---

## Deployment Considerations

### CI/CD Environment

**Requirements**:
- Python 3.9+
- Sufficient memory for parallel browser instances (2GB+ recommended)
- Network access to Platform API
- Network access to AWS Bedrock (for Nova Act)

**Environment Variables**:
- `OAUTH_CLIENT_ID`: OAuth client ID
- `OAUTH_CLIENT_SECRET`: OAuth client secret
- `OAUTH_TOKEN_ENDPOINT`: Cognito token endpoint
- `API_ENDPOINT`: Platform API base URL
- `LOG_LEVEL`: Logging level (optional, default: INFO)

### Docker Support

**Dockerfile** (future enhancement):
```dockerfile
FROM python:3.9-slim

# Install dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps

# Copy application
COPY src/ ./src/
COPY setup.py .
RUN pip install -e .

# Run runner
ENTRYPOINT ["python", "-m", "src.cli.parser"]
```

**Usage**:
```bash
docker run --rm \
  -e OAUTH_CLIENT_ID=$CLIENT_ID \
  -e OAUTH_CLIENT_SECRET=$CLIENT_SECRET \
  -e OAUTH_TOKEN_ENDPOINT=$TOKEN_ENDPOINT \
  -e API_ENDPOINT=$API_ENDPOINT \
  qa-studio-ci-runner \
  --suite-id $SUITE_ID
```

### GitHub Actions Integration

**Workflow Example**:
```yaml
name: Run Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      
      - name: Install dependencies
        run: |
          cd qa-studio-ci-runner
          pip install -r requirements.txt
      
      - name: Run tests
        env:
          OAUTH_CLIENT_ID: ${{ secrets.OAUTH_CLIENT_ID }}
          OAUTH_CLIENT_SECRET: ${{ secrets.OAUTH_CLIENT_SECRET }}
          OAUTH_TOKEN_ENDPOINT: ${{ secrets.OAUTH_TOKEN_ENDPOINT }}
          API_ENDPOINT: ${{ secrets.API_ENDPOINT }}
        run: |
          cd qa-studio-ci-runner
          python -m src.cli.parser --suite-id ${{ vars.TEST_SUITE_ID }}
```

---

## Summary

This design document describes the implementation of the test execution engine for the CI/CD runner. The engine uses Nova Act SDK to execute tests in parallel, updates execution status via API, aggregates results, and provides clear summary output with appropriate exit codes.

**Key Features**:
- Parallel execution using asyncio
- Fault isolation (individual failures don't stop other tests)
- Real-time status updates via API
- Readable summary table output
- Appropriate exit codes for CI/CD integration

**Next Steps**:
1. Implement `ExecutionEngine` class
2. Implement `ExecutionAPI` class (async wrappers)
3. Implement `SummaryFormatter` class
4. Update `main.py` to use execution engine
5. Write unit tests (≥70% coverage)
6. Write integration tests
7. Manual testing with real test suite

