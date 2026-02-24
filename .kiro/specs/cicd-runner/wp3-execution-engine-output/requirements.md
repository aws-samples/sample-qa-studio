# Work Package 3: Execution Engine & Output

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP3 - Execution Engine & Output
- **Estimated Duration**: 5 days
- **Dependencies**: WP2 (Runner Core & Authentication)
- **Status**: Not Started

---

## Overview

Implement the test execution engine using Nova Act SDK to run all use cases in parallel locally with a bundled Chromium browser. Include execution status updates via API, result aggregation, summary output formatting, and exit code logic.

---

## User Stories

### US1: As a CI/CD runner, I need to execute use cases in parallel with Nova Act SDK
**Acceptance Criteria**:
- Runner executes all use cases simultaneously
- Each use case runs in its own Nova Act session
- Execution continues even if individual tests fail
- All execution results are collected
- Execution status is updated via API

### US2: As a CI/CD runner, I need to update execution status via API
**Acceptance Criteria**:
- Runner updates status to "running" when execution starts
- Runner updates status to "completed" or "failed" when execution finishes
- Runner includes error messages for failed executions
- Status updates are sent for each usecase execution
- Suite execution status is updated when all tests complete

### US3: As a CI/CD user, I need a clear summary of test results
**Acceptance Criteria**:
- Summary table shows all use cases with status and duration
- Summary includes pass/fail counts and success percentage
- Summary is printed to stdout in a readable format
- Verbose mode shows detailed execution logs
- Summary includes suite execution ID for reference

### US4: As a CI/CD pipeline, I need exit codes to control workflow
**Acceptance Criteria**:
- Exit code 0 when all tests pass
- Exit code 1 when one or more tests fail
- Exit code 2 when runner encounters an error
- Exit code is set after summary is printed

---

## Technical Requirements

### Nova Act SDK Integration

**Dependencies**:
```
nova-act-sdk>=1.0.0
playwright>=1.40.0  # Bundled with Nova Act SDK
```

### Execution Engine Architecture

```python
# Parallel execution using asyncio
async def execute_all_usecases(executions: List[ExecutionRecord]) -> List[ExecutionResult]:
    tasks = [execute_usecase(execution) for execution in executions]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

---

## Implementation Details

### 1. Execution Engine

**File**: `src/execution/engine.py`

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
    """Parallel test execution engine."""
    
    def __init__(self, api_client, execution_api: ExecutionAPI):
        self.api_client = api_client
        self.execution_api = execution_api
    
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
            
            # Update status to completed
            await self.execution_api.update_status(
                usecase_id=usecase_id,
                execution_id=execution_id,
                status='completed' if result['success'] else 'failed',
                error_message=result.get('error')
            )
            
            logger.info(f"[{usecase_name}] Completed: {'PASSED' if result['success'] else 'FAILED'} ({duration:.1f}s)")
            
            return {
                'execution_id': execution_id,
                'usecase_id': usecase_id,
                'usecase_name': usecase_name,
                'status': 'completed' if result['success'] else 'failed',
                'error': result.get('error'),
                'duration': duration
            }
            
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"[{usecase_name}] Failed: {str(e)}")
            
            # Update status to failed
            await self.execution_api.update_status(
                usecase_id=usecase_id,
                execution_id=execution_id,
                status='failed',
                error_message=str(e)
            )
            
            return {
                'execution_id': execution_id,
                'usecase_id': usecase_id,
                'usecase_name': usecase_name,
                'status': 'failed',
                'error': str(e),
                'duration': duration
            }
    
    async def _execute_with_nova_act(self, execution_details: Dict[str, Any]) -> Dict[str, Any]:
        """Execute test using Nova Act SDK."""
        # Initialize Nova Act client
        client = NovaActClient(
            region=execution_details['region'],
            model_id=execution_details['model_id']
        )
        
        # Start browser session
        async with client.browser_session(headless=True) as session:
            # Navigate to starting URL
            await session.goto(execution_details['starting_url'])
            
            # Execute each step
            for step in execution_details['steps']:
                try:
                    await self._execute_step(session, step, execution_details['variables'])
                except Exception as e:
                    return {
                        'success': False,
                        'error': f"Step {step['step_number']} failed: {str(e)}"
                    }
            
            return {'success': True}
    
    async def _execute_step(self, session, step: Dict[str, Any], variables: Dict[str, str]):
        """Execute a single test step."""
        # Replace variables in step instruction
        instruction = self._replace_variables(step['instruction'], variables)
        
        # Execute step with Nova Act
        result = await session.execute(instruction)
        
        if not result.success:
            raise ExecutionError(f"Step failed: {result.error}")
```

### 2. Execution API

**File**: `src/api/executions.py`

```python
from typing import Dict, Any
from .client import APIClient

class ExecutionAPI:
    """Execution API operations."""
    
    def __init__(self, client: APIClient):
        self.client = client
    
    async def get_execution(self, usecase_id: str, execution_id: str) -> Dict[str, Any]:
        """Fetch execution details."""
        return self.client.get(f"/usecase/{usecase_id}/executions/{execution_id}")
    
    async def update_status(
        self,
        usecase_id: str,
        execution_id: str,
        status: str,
        error_message: str = None
    ) -> Dict[str, Any]:
        """Update execution status."""
        payload = {'status': status}
        if error_message:
            payload['error_message'] = error_message
        
        return self.client.patch(
            f"/usecase/{usecase_id}/executions/{execution_id}/status",
            data=payload
        )
    
    async def update_suite_status(
        self,
        suite_id: str,
        suite_execution_id: str,
        status: str
    ) -> Dict[str, Any]:
        """Update suite execution status."""
        return self.client.patch(
            f"/test-suites/{suite_id}/executions/{suite_execution_id}/status",
            data={'status': status}
        )
```

### 3. Summary Output

**File**: `src/output/summary.py`

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
        """Format results as ASCII table."""
        
        total = len(results)
        passed = sum(1 for r in results if r['status'] == 'completed')
        failed = total - passed
        success_rate = (passed / total * 100) if total > 0 else 0
        duration = (end_time - start_time).total_seconds()
        
        # Build table
        lines = []
        lines.append("╔" + "═" * 60 + "╗")
        lines.append("║" + "Nova Act QA Studio - CI/CD Runner".center(60) + "║")
        lines.append("╠" + "═" * 60 + "╣")
        lines.append(f"║ Suite: {suite_name[:45]:<45} ║")
        lines.append(f"║ Suite Execution ID: {suite_execution_id[:37]:<37} ║")
        lines.append(f"║ Started: {start_time.strftime('%Y-%m-%d %H:%M:%S'):<46} ║")
        lines.append(f"║ Completed: {end_time.strftime('%Y-%m-%d %H:%M:%S'):<44} ║")
        lines.append(f"║ Duration: {self._format_duration(duration):<47} ║")
        lines.append("╠" + "═" * 60 + "╣")
        lines.append("║ Use Case                          Status      Duration ║")
        lines.append("╠" + "═" * 60 + "╣")
        
        for result in results:
            name = result['usecase_name'][:30]
            status = "✓ PASSED" if result['status'] == 'completed' else "✗ FAILED"
            duration_str = self._format_duration(result['duration'])
            lines.append(f"║ {name:<30} {status:<10} {duration_str:>8} ║")
        
        lines.append("╠" + "═" * 60 + "╣")
        summary_line = f"Total: {total}  |  Passed: {passed}  |  Failed: {failed}  |  Success: {success_rate:.0f}%"
        lines.append(f"║ {summary_line:<58} ║")
        lines.append("╚" + "═" * 60 + "╝")
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration as human-readable string."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
```

### 4. Exit Code Logic

**File**: `src/main.py` (updated)

```python
def determine_exit_code(results: List[Dict[str, Any]]) -> int:
    """Determine exit code based on results."""
    if not results:
        return 2  # Error: no results
    
    failed = sum(1 for r in results if r['status'] == 'failed')
    
    if failed == 0:
        return 0  # Success: all passed
    else:
        return 1  # Failure: one or more failed
```

---

## Testing Requirements

### Unit Tests
- Test parallel execution orchestration
- Test Nova Act SDK integration
- Test execution status updates
- Test summary formatting
- Test exit code logic
- Test error handling during execution

### Integration Tests
- Execute single use case end-to-end
- Execute multiple use cases in parallel
- Test execution with failing test
- Test execution with Nova Act error
- Verify status updates sent to API
- Verify summary output format

---

## Success Criteria

- [ ] Use cases execute in parallel with Nova Act SDK
- [ ] Execution status updated via API
- [ ] Summary table printed to stdout
- [ ] Exit codes set correctly (0/1/2)
- [ ] Failed tests don't stop other tests
- [ ] Unit test coverage ≥ 70%
- [ ] Integration tests pass
- [ ] Execution logs are clear and helpful
