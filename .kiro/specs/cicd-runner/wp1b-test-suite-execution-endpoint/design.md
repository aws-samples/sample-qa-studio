# Work Package 1b: Test Suite Execution Endpoint - Design Document

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP1b - Test Suite Execution Endpoint
- **Version**: 1.0
- **Status**: Design Phase
- **Dependencies**: WP1a (Execution Record & Trigger Type)

---

## Design Overview

This workpackage implements a new API endpoint `POST /api/test-suites/{id}/execute` that serves as the entry point for CI/CD runners. The endpoint creates a suite execution record and execution records for ALL use cases in the suite, applies overrides (base_url, variables, region, model_id), and returns all execution IDs without spawning ECS tasks.

### Key Design Principles
1. **Batch Creation**: Create all execution records in a single API call
2. **Override Application**: Apply overrides at execution record creation time (not runtime)
3. **No ECS Tasks**: Leverage WP1a's ci_runner trigger type to skip ECS task creation
4. **Fail Fast**: Validate all variables are resolved before creating any execution records
5. **Query Efficiency**: Use existing DynamoDB patterns, no new GSI/LSI required

---

## Architecture

### High-Level Flow

```
CI/CD Runner
    ↓
POST /api/test-suites/{id}/execute
    ↓
Lambda: execute_test_suite
    ↓
1. Fetch test suite definition
2. Create suite execution record
3. For each usecase in suite:
   a. Fetch usecase definition
   b. Apply base URL override
   c. Merge variables (secrets < usecase vars < CLI overrides)
   d. Validate all variables resolved
   e. Create execution record (trigger_type=ci_runner)
4. Update suite execution with all execution IDs
5. Return response
    ↓
CI/CD Runner receives:
- suite_execution_id
- List of execution_ids
```

### Component Interaction

```
┌─────────────────┐
│   CI/CD Runner  │
└────────┬────────┘
         │ POST /api/test-suites/{id}/execute
         │ { base_url, variables, region, model_id }
         ↓
┌─────────────────────────────────────────────────┐
│         API Gateway + Lambda Authorizer         │
│         (Cognito OAuth validation)              │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│    Lambda: execute_test_suite                   │
│                                                  │
│  1. Query: TEST_SUITES / SUITE#{suite_id}      │
│  2. Query: SUITE#{suite_id} / USECASE#*        │
│  3. For each usecase:                           │
│     - Get: USECASES / USECASE#{usecase_id}     │
│     - Get: USECASE#{usecase_id} / SECRETS      │
│     - Get: USECASE#{usecase_id} / VARIABLES    │
│     - Apply overrides                           │
│     - Put: USECASE_EXECUTION#{usecase_id} /    │
│            EXECUTION#{execution_id}             │
│     - Put: EXECUTION#{execution_id} / STEPS    │
│     - Put: EXECUTION#{execution_id} / HOOKS    │
│     - Put: EXECUTION#{execution_id} / VARS     │
│     - Put: EXECUTION#{execution_id} / HEADERS  │
│  4. Put: SUITE#{suite_id} /                    │
│          SUITE_EXECUTION#{suite_execution_id}   │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│              DynamoDB Table                      │
│                                                  │
│  - Suite execution record                       │
│  - N execution records (one per usecase)        │
│  - N * M execution step records                 │
│  - N execution hooks/variables/headers          │
└─────────────────────────────────────────────────┘
```

---

## Components and Interfaces

### 1. Lambda Function: execute_test_suite

**Purpose**: Create suite execution and all usecase execution records with overrides applied

**Handler Signature**:
```python
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]
```

**Input** (API Gateway event):
```python
{
    'pathParameters': {
        'id': 'suite-uuid'
    },
    'body': json.dumps({
        'trigger_type': 'ci_runner',  # Required
        'base_url': 'https://example.com',  # Optional
        'variables': {  # Optional
            'key': 'value'
        },
        'region': 'us-east-1',  # Optional
        'model_id': 'us.anthropic.claude-3-5-sonnet-20241022-v2:0'  # Optional
    })
}
```

**Output**:
```python
{
    'statusCode': 200,
    'body': json.dumps({
        'suite_execution_id': 'uuid',
        'suite_id': 'uuid',
        'status': 'pending',
        'created_at': 'ISO8601 timestamp',
        'execution_ids': [
            {
                'usecase_id': 'uuid',
                'execution_id': 'uuid',
                'usecase_name': 'string'
            }
        ]
    })
}
```

**Core Functions**:

```python
def get_test_suite(suite_id: str) -> Dict[str, Any]:
    """
    Fetch test suite definition from DynamoDB.
    
    Query: pk='TEST_SUITES', sk='SUITE#{suite_id}'
    
    Returns:
        Suite definition with metadata
    
    Raises:
        ValueError: If suite not found
    """

def get_suite_usecases(suite_id: str) -> List[Dict[str, Any]]:
    """
    Fetch all usecase mappings for a test suite.
    
    Query: pk='SUITE#{suite_id}', sk begins_with 'USECASE#'
    
    Returns:
        List of usecase mappings with usecase_id and usecase_name
    """

def get_usecase_definition(usecase_id: str) -> Dict[str, Any]:
    """
    Fetch usecase definition from DynamoDB.
    
    Query: pk='USECASES', sk='USECASE#{usecase_id}'
    
    Returns:
        Usecase definition with starting_url, region, model_id, etc.
    
    Raises:
        ValueError: If usecase not found
    """

def get_usecase_secrets(usecase_id: str) -> Dict[str, str]:
    """
    Fetch usecase secrets from DynamoDB.
    
    Query: pk='USECASE#{usecase_id}', sk='SECRETS'
    
    Returns:
        Dictionary of secret key-value pairs (empty dict if no secrets)
    """

def get_usecase_variables(usecase_id: str) -> Dict[str, str]:
    """
    Fetch usecase variables from DynamoDB.
    
    Query: pk='USECASE#{usecase_id}', sk='USECASE_VARIABLES'
    
    Returns:
        Dictionary of variable key-value pairs (empty dict if no variables)
    """

def apply_base_url_override(original_url: str, base_url: Optional[str]) -> str:
    """
    Replace domain/origin while preserving path and query parameters.
    
    Uses urllib.parse to parse URLs and replace scheme + netloc.
    
    Args:
        original_url: Original starting URL from usecase
        base_url: Override base URL (None = no override)
    
    Returns:
        Modified URL with new base, or original if base_url is None
    
    Example:
        original_url = "https://staging.example.com/login?foo=bar"
        base_url = "https://prod.example.com"
        result = "https://prod.example.com/login?foo=bar"
    """

def merge_variables(
    secrets: Dict[str, str],
    usecase_vars: Dict[str, str],
    cli_vars: Dict[str, str]
) -> Dict[str, str]:
    """
    Merge variables with precedence: CLI > usecase > secrets.
    
    Args:
        secrets: Variables from Secrets Manager
        usecase_vars: Variables from usecase definition
        cli_vars: Variables from CLI arguments
    
    Returns:
        Merged dictionary with CLI overrides taking precedence
    """

def validate_variables_resolved(
    usecase: Dict[str, Any],
    variables: Dict[str, str]
) -> None:
    """
    Ensure all {{variable}} placeholders are resolved.
    
    Checks starting_url, steps, hooks for unresolved template variables.
    
    Args:
        usecase: Usecase definition
        variables: Merged variables dictionary
    
    Raises:
        ValueError: If any unresolved variables found (with list of missing vars)
    """

def create_suite_execution_record(
    suite_id: str,
    suite_execution_id: str,
    suite_name: str,
    trigger_type: str,
    overrides: Dict[str, Any],
    total_usecases: int,
    created_at: str
) -> Dict[str, Any]:
    """
    Create suite execution record in DynamoDB.
    
    Put: pk='SUITE#{suite_id}', sk='SUITE_EXECUTION#{suite_execution_id}'
    
    Returns:
        Created suite execution record
    """

def create_execution_record_for_usecase(
    usecase_id: str,
    suite_execution_id: str,
    suite_id: str,
    trigger_type: str,
    starting_url: str,
    variables: Dict[str, str],
    region: str,
    model_id: str,
    created_at: str
) -> str:
    """
    Create execution record for a single usecase.
    
    Reuses logic from execute_usecase Lambda:
    - Creates execution record
    - Copies steps
    - Copies hooks
    - Copies variables (merged)
    - Copies headers
    
    Put: pk='USECASE_EXECUTION#{usecase_id}', sk='EXECUTION#{execution_id}'
    
    Returns:
        execution_id (UUIDv7)
    """

def update_suite_execution_with_executions(
    suite_execution_id: str,
    suite_id: str,
    execution_ids: List[Dict[str, str]]
) -> None:
    """
    Update suite execution record with list of usecase executions.
    
    Update: pk='SUITE#{suite_id}', sk='SUITE_EXECUTION#{suite_execution_id}'
    Set: usecase_executions = execution_ids
    """
```

### 2. API Gateway Configuration

**Path**: `/test-suites/{id}/execute`

**Method**: `POST`

**Authorizer**: Cognito User Pool Authorizer

**Required Scopes**: 
- `api/suite.write` - Execute test suites
- `api/execution.write` - Create execution records

**Request Validation**:
- Path parameter `id` is required
- Request body must be valid JSON
- `trigger_type` field is required in body

**Response Models**:
- 200: Success response with suite_execution_id and execution_ids
- 400: Bad request (invalid input, missing variables)
- 403: Forbidden (insufficient scopes)
- 404: Test suite not found
- 500: Internal server error

### 3. URL Override Module

**File**: `lambdas/utils/url_override.py` (new file)

```python
from urllib.parse import urlparse, urlunparse
from typing import Optional

def apply_base_url_override(original_url: str, base_url: Optional[str]) -> str:
    """
    Replace domain/origin while preserving path and query parameters.
    
    Implementation:
    1. Parse original URL into components
    2. Parse base URL into components
    3. Replace scheme and netloc from base URL
    4. Keep path, params, query, fragment from original
    5. Reconstruct URL
    
    Args:
        original_url: Original starting URL
        base_url: Override base URL (None = no override)
    
    Returns:
        Modified URL or original if base_url is None
    
    Examples:
        >>> apply_base_url_override(
        ...     "https://staging.example.com/login?foo=bar",
        ...     "https://prod.example.com"
        ... )
        "https://prod.example.com/login?foo=bar"
        
        >>> apply_base_url_override(
        ...     "http://localhost:3000/app/dashboard",
        ...     "https://example.com"
        ... )
        "https://example.com/app/dashboard"
        
        >>> apply_base_url_override(
        ...     "https://example.com/path",
        ...     None
        ... )
        "https://example.com/path"
    """
    if not base_url:
        return original_url
    
    parsed_original = urlparse(original_url)
    parsed_base = urlparse(base_url)
    
    # Replace scheme and netloc (domain), keep everything else
    return urlunparse((
        parsed_base.scheme,
        parsed_base.netloc,
        parsed_original.path,
        parsed_original.params,
        parsed_original.query,
        parsed_original.fragment
    ))
```

### 4. Variable Merge Module

**File**: `lambdas/utils/variable_merge.py` (new file)

```python
import re
import json
from typing import Dict, Any, List

def merge_variables(
    secrets: Dict[str, str],
    usecase_vars: Dict[str, str],
    cli_vars: Dict[str, str]
) -> Dict[str, str]:
    """
    Merge variables with precedence: CLI > usecase > secrets.
    
    Implementation:
    1. Start with secrets (lowest priority)
    2. Override with usecase variables
    3. Override with CLI variables (highest priority)
    
    Args:
        secrets: Variables from Secrets Manager
        usecase_vars: Variables from usecase definition
        cli_vars: Variables from CLI arguments
    
    Returns:
        Merged dictionary
    
    Example:
        >>> merge_variables(
        ...     {'username': 'secret_user', 'password': 'secret_pass'},
        ...     {'username': 'usecase_user'},
        ...     {'username': 'cli_user'}
        ... )
        {'username': 'cli_user', 'password': 'secret_pass'}
    """
    merged = {}
    merged.update(secrets)
    merged.update(usecase_vars)
    merged.update(cli_vars)
    return merged

def validate_variables_resolved(
    usecase: Dict[str, Any],
    variables: Dict[str, str]
) -> None:
    """
    Ensure all {{variable}} placeholders are resolved.
    
    Implementation:
    1. Convert usecase to JSON string
    2. Find all {{variable}} patterns using regex
    3. Check if each variable exists in variables dict
    4. Raise ValueError if any missing
    
    Args:
        usecase: Usecase definition (dict)
        variables: Merged variables dictionary
    
    Raises:
        ValueError: If unresolved variables found
    
    Example:
        >>> usecase = {'starting_url': 'https://example.com/{{env}}'}
        >>> variables = {'env': 'prod'}
        >>> validate_variables_resolved(usecase, variables)
        # No error
        
        >>> variables = {}
        >>> validate_variables_resolved(usecase, variables)
        ValueError: Unresolved variables: env
    """
    template_pattern = r'\{\{(\w+)\}\}'
    usecase_str = json.dumps(usecase)
    
    # Find all template variables
    found_vars = re.findall(template_pattern, usecase_str)
    
    # Check which ones are missing
    missing = [var for var in found_vars if var not in variables]
    
    if missing:
        raise ValueError(f"Unresolved variables: {', '.join(missing)}")

def get_unresolved_variables(usecase: Dict[str, Any]) -> List[str]:
    """
    Extract all {{variable}} placeholders from usecase definition.
    
    Helper function for testing and debugging.
    
    Args:
        usecase: Usecase definition
    
    Returns:
        List of variable names found in templates
    """
    template_pattern = r'\{\{(\w+)\}\}'
    usecase_str = json.dumps(usecase)
    return re.findall(template_pattern, usecase_str)
```

---

## Data Models

### Suite Execution Record

**DynamoDB Item**:
```python
{
    'pk': 'SUITE#{suite_id}',
    'sk': 'SUITE_EXECUTION#{suite_execution_id}',
    'suite_id': 'uuid',
    'suite_execution_id': 'uuid',
    'status': 'pending',  # pending | running | completed | failed
    'trigger_type': 'ci_runner',
    'created_at': 'ISO8601 timestamp',
    'started_at': 'ISO8601 timestamp',  # Optional, set when first usecase starts
    'completed_at': 'ISO8601 timestamp',  # Optional, set when all complete
    'usecase_executions': [
        {
            'usecase_id': 'uuid',
            'execution_id': 'uuid',
            'usecase_name': 'string',
            'status': 'pending'
        }
    ],
    'overrides': {
        'base_url': 'string',  # Optional
        'variables': {},  # Optional
        'region': 'string',  # Optional
        'model_id': 'string'  # Optional
    },
    'total_usecases': 5,
    'completed_usecases': 0,
    'successful_usecases': 0,
    'failed_usecases': 0
}
```

**Query Pattern**:
```python
# Get all suite executions for a suite
pk = 'SUITE#{suite_id}'
sk begins_with 'SUITE_EXECUTION#'
```

### Modified Execution Record

**DynamoDB Item** (extends existing execution record):
```python
{
    'pk': 'USECASE_EXECUTION#{usecase_id}',
    'sk': 'EXECUTION#{execution_id}',
    'suite_execution_id': 'uuid',  # NEW FIELD - links to parent suite execution
    'suite_id': 'uuid',  # NEW FIELD - links to parent suite
    'trigger_type': 'ci_runner',
    'starting_url': 'string',  # Modified with base_url override
    'status': 'pending',
    'created_at': 'ISO8601 timestamp',
    'executing_region': 'string',  # Overridden if specified
    'model_id': 'string',  # Overridden if specified
    # ... other existing fields
}
```

**Query Pattern**:
```python
# Get all executions for a usecase
pk = 'USECASE_EXECUTION#{usecase_id}'
sk begins_with 'EXECUTION#'

# Get specific execution
pk = 'USECASE_EXECUTION#{usecase_id}'
sk = 'EXECUTION#{execution_id}'
```

### Execution Variables Record

**DynamoDB Item** (modified with merged variables):
```python
{
    'pk': 'EXECUTION#{execution_id}',
    'sk': 'EXECUTION_VARIABLES',
    'created_at': 'ISO8601 timestamp',
    'variables': {
        # Merged variables: secrets < usecase vars < CLI overrides
        'key1': 'value1',
        'key2': 'value2'
    }
}
```

**Query Pattern**:
```python
# Get variables for an execution
pk = 'EXECUTION#{execution_id}'
sk = 'EXECUTION_VARIABLES'
```

---

## Error Handling

### Error Response Format

All error responses follow this structure:
```json
{
    "error": "Error type",
    "message": "Detailed error description",
    "details": {}  // Optional additional context
}
```

### Error Scenarios

#### 1. Test Suite Not Found (404)
```python
if 'Item' not in suite_result:
    return create_response(404, {
        'error': 'Test suite not found',
        'message': f'No test suite found with ID: {suite_id}'
    })
```

#### 2. Missing Variables (400)
```python
try:
    validate_variables_resolved(usecase, merged_vars)
except ValueError as e:
    return create_response(400, {
        'error': 'Unresolved variables',
        'message': str(e),
        'details': {
            'usecase_id': usecase_id,
            'usecase_name': usecase['name']
        }
    })
```

#### 3. Invalid Base URL (400)
```python
try:
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError('Invalid URL format')
except Exception as e:
    return create_response(400, {
        'error': 'Invalid base URL',
        'message': f'Base URL must be a valid URL with scheme and domain: {base_url}'
    })
```

#### 4. Insufficient Permissions (403)
```python
# Handled by API Gateway authorizer
# If user lacks required scopes, returns:
{
    'error': 'Forbidden',
    'message': 'Insufficient permissions',
    'required_scopes': ['api/suite.write', 'api/execution.write'],
    'token_scopes': ['api/suite.read']
}
```

#### 5. Usecase Not Found (500)
```python
# If a usecase in the suite doesn't exist, this is a data integrity issue
if 'Item' not in usecase_result:
    print(f'ERROR: Usecase {usecase_id} not found but is in suite {suite_id}')
    return create_response(500, {
        'error': 'Data integrity error',
        'message': f'Usecase {usecase_id} referenced by suite but not found'
    })
```

#### 6. DynamoDB Error (500)
```python
except ClientError as e:
    print(f'DynamoDB error: {str(e)}')
    return create_response(500, {
        'error': 'Database error',
        'message': 'Failed to create execution records'
    })
```

### Error Handling Strategy

1. **Fail Fast**: Validate all inputs before creating any records
2. **Atomic Operations**: If any usecase fails validation, don't create any execution records
3. **Clear Messages**: Provide actionable error messages with context
4. **Logging**: Log all errors to CloudWatch for debugging
5. **Rollback**: If execution record creation fails partway through, log error but don't attempt rollback (DynamoDB doesn't support transactions across multiple items in this pattern)

---

## Testing Strategy

### Unit Tests

**File**: `lambdas/endpoints/test_execute_test_suite.py` (new file)

**Test Coverage Target**: ≥70%

**Test Classes**:

```python
class TestExecuteTestSuite:
    """Test suite execution endpoint"""
    
    def test_execute_suite_creates_suite_execution_record(self):
        """Verify suite execution record created with correct fields"""
    
    def test_execute_suite_creates_all_usecase_executions(self):
        """Verify execution records created for all usecases in suite"""
    
    def test_execute_suite_returns_all_execution_ids(self):
        """Verify response contains all execution IDs"""
    
    def test_execute_suite_no_ecs_tasks_spawned(self):
        """Verify no ECS tasks created (trigger_type=ci_runner)"""

class TestBaseUrlOverride:
    """Test base URL override logic"""
    
    def test_base_url_override_replaces_domain(self):
        """Verify domain replaced correctly"""
    
    def test_base_url_override_preserves_path(self):
        """Verify path preserved"""
    
    def test_base_url_override_preserves_query_params(self):
        """Verify query parameters preserved"""
    
    def test_base_url_override_with_none_returns_original(self):
        """Verify no override when base_url is None"""
    
    def test_base_url_override_changes_scheme(self):
        """Verify scheme (http/https) can be changed"""

class TestVariableMerge:
    """Test variable merge logic"""
    
    def test_cli_variables_override_usecase_variables(self):
        """Verify CLI variables take precedence over usecase variables"""
    
    def test_usecase_variables_override_secrets(self):
        """Verify usecase variables take precedence over secrets"""
    
    def test_cli_variables_override_secrets(self):
        """Verify CLI variables take precedence over secrets"""
    
    def test_merge_with_empty_dicts(self):
        """Verify merge works with empty dictionaries"""
    
    def test_merge_preserves_all_variables(self):
        """Verify all variables from all sources are included"""

class TestVariableValidation:
    """Test variable validation logic"""
    
    def test_validation_passes_with_all_variables_resolved(self):
        """Verify validation passes when all variables present"""
    
    def test_validation_fails_with_missing_variables(self):
        """Verify validation fails with clear error message"""
    
    def test_validation_checks_starting_url(self):
        """Verify starting_url is checked for unresolved variables"""
    
    def test_validation_checks_steps(self):
        """Verify steps are checked for unresolved variables"""
    
    def test_validation_checks_hooks(self):
        """Verify hooks are checked for unresolved variables"""

class TestErrorHandling:
    """Test error scenarios"""
    
    def test_suite_not_found_returns_404(self):
        """Verify 404 when suite doesn't exist"""
    
    def test_missing_variables_returns_400(self):
        """Verify 400 when variables unresolved"""
    
    def test_invalid_base_url_returns_400(self):
        """Verify 400 when base_url is invalid"""
    
    def test_insufficient_permissions_returns_403(self):
        """Verify 403 when scopes missing"""
    
    def test_usecase_not_found_returns_500(self):
        """Verify 500 when usecase in suite doesn't exist"""
```

**File**: `lambdas/utils/test_url_override.py` (new file)

```python
class TestUrlOverride:
    """Test URL override utility functions"""
    
    def test_apply_base_url_override_basic(self):
        """Test basic domain replacement"""
    
    def test_apply_base_url_override_with_path(self):
        """Test domain replacement with path"""
    
    def test_apply_base_url_override_with_query(self):
        """Test domain replacement with query parameters"""
    
    def test_apply_base_url_override_with_fragment(self):
        """Test domain replacement with URL fragment"""
    
    def test_apply_base_url_override_scheme_change(self):
        """Test changing http to https"""
    
    def test_apply_base_url_override_none(self):
        """Test no override when base_url is None"""
```

**File**: `lambdas/utils/test_variable_merge.py` (new file)

```python
class TestVariableMerge:
    """Test variable merge utility functions"""
    
    def test_merge_variables_precedence(self):
        """Test CLI > usecase > secrets precedence"""
    
    def test_validate_variables_resolved_success(self):
        """Test validation passes with all variables"""
    
    def test_validate_variables_resolved_failure(self):
        """Test validation fails with missing variables"""
    
    def test_get_unresolved_variables(self):
        """Test extraction of template variables"""
```

### Integration Tests

**Test Scenarios**:

1. **Execute suite with no overrides**
   - Create test suite with 3 usecases
   - Call endpoint with no overrides
   - Verify suite execution record created
   - Verify 3 execution records created
   - Verify no ECS tasks spawned
   - Verify response contains all execution IDs

2. **Execute suite with base_url override**
   - Create test suite with usecases having different starting URLs
   - Call endpoint with base_url override
   - Verify all execution records have modified starting_url
   - Verify paths and query params preserved

3. **Execute suite with variable overrides**
   - Create test suite with usecases using variables
   - Call endpoint with variable overrides
   - Verify execution variables records have merged variables
   - Verify CLI variables override usecase variables

4. **Execute suite with all overrides**
   - Call endpoint with base_url, variables, region, model_id
   - Verify all overrides applied correctly

5. **Execute suite with missing variables**
   - Create usecase with unresolved {{variable}}
   - Call endpoint without providing variable
   - Verify 400 error returned
   - Verify no execution records created

6. **Execute suite not found**
   - Call endpoint with non-existent suite ID
   - Verify 404 error returned

### Manual Testing Checklist

- [ ] Deploy Lambda function
- [ ] Create test suite with 3 usecases via UI
- [ ] Call endpoint with Postman/curl
- [ ] Verify suite execution record in DynamoDB
- [ ] Verify 3 execution records in DynamoDB
- [ ] Verify no ECS tasks in ECS console
- [ ] Test base_url override with different domains
- [ ] Test variable override with CLI variables
- [ ] Test error cases (missing suite, missing variables)
- [ ] Verify OAuth scope validation works

---

## Correctness Properties

A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

### Property 1: Suite Execution Record Creation

*For any* valid test suite ID, when the endpoint is called with trigger_type="ci_runner", a suite execution record should be created in DynamoDB with status="pending" and trigger_type="ci_runner".

**Validates: Requirements US1.2, US5.1**

### Property 2: Complete Execution Record Creation

*For any* test suite with N usecases, calling the endpoint should create exactly N execution records and return exactly N execution IDs in the response, where each execution ID corresponds to one usecase in the suite.

**Validates: Requirements US1.3, US1.4**

### Property 3: No ECS Task Spawning

*For any* suite execution with trigger_type="ci_runner", no ECS tasks should be spawned (the ECS run_task API should never be called).

**Validates: Requirements US1.5**

### Property 4: Base URL Transformation Preserves Path and Query

*For any* starting URL with a path and query parameters, and any valid base URL, applying the base URL override should replace only the scheme and domain while preserving the path, query parameters, and fragment exactly as they were in the original URL.

**Validates: Requirements US2.2, US2.3, US2.4**

### Property 5: Variable Merge Precedence

*For any* combination of secrets, usecase variables, and CLI variables with overlapping keys, the merged result should always prioritize CLI variables over usecase variables, and usecase variables over secrets (CLI > usecase > secrets).

**Validates: Requirements US3.2, US3.4**

### Property 6: Unresolved Variables Rejection

*For any* usecase definition containing template variables ({{variable}}), if the merged variables dictionary does not contain values for all template variables, the endpoint should return a 400 error with a clear message listing the missing variables, and no execution records should be created.

**Validates: Requirements US3.3, US3.5**

### Property 7: Override Application to All Executions

*For any* test suite with N usecases, if region and/or model_id overrides are provided in the request, all N execution records should have these override values; if not provided, each execution record should use the default values from its respective usecase definition.

**Validates: Requirements US4.3, US4.4**

### Property 8: Bidirectional Suite-Execution Linking

*For any* suite execution with N usecase executions, the suite execution record should contain all N execution IDs in its usecase_executions array, and each of the N execution records should contain the suite_execution_id field linking back to the parent suite execution.

**Validates: Requirements US5.2, US5.4**

### Property 9: Suite Metadata Propagation

*For any* test suite with name and description fields, the suite execution record should include these metadata fields with the same values as the original suite definition.

**Validates: Requirements US5.3**

---

## Security Considerations

### Authentication & Authorization

**OAuth Scopes Required**:
- `api/suite.write` - Required to execute test suites
- `api/execution.write` - Required to create execution records

**Scope Validation**:
```python
# Lambda function must validate scopes using existing allow_m2m_token utility
user_identity, error_response = allow_m2m_token(event)
if error_response:
    return error_response

# Verify required scopes are present
required_scopes = ['api/suite.write', 'api/execution.write']
token_scopes = user_identity.get('scopes', [])

if not all(scope in token_scopes for scope in required_scopes):
    return create_response(403, {
        'error': 'Insufficient permissions',
        'required_scopes': required_scopes,
        'token_scopes': token_scopes
    })
```

**M2M Token Support**:
- Endpoint must support both user tokens and M2M tokens (OAuth client credentials)
- Use existing `allow_m2m_token()` function from utils
- CI/CD runners will use M2M tokens exclusively

### Input Validation

**Suite ID Validation**:
- Validate suite_id is a valid UUID format
- Verify suite exists before processing
- Return 404 if suite not found

**Base URL Validation**:
```python
if base_url:
    try:
        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError('Invalid URL format')
        if parsed.scheme not in ['http', 'https']:
            raise ValueError('Scheme must be http or https')
    except Exception as e:
        return create_response(400, {
            'error': 'Invalid base URL',
            'message': str(e)
        })
```

**Variable Validation**:
- Validate variables is a dictionary (if provided)
- Validate all variable values are strings
- Check for SQL injection patterns (sanitize values)
- Validate no reserved variable names are used

**Region Validation**:
- Validate region is a valid AWS region format
- Use allowlist of supported regions if needed

**Model ID Validation**:
- Validate model_id follows expected format
- Verify model is available in specified region (optional)

### Secret Handling

**Secrets Fetching**:
- Secrets are fetched server-side from Secrets Manager
- Secrets are never exposed in API responses
- Secrets are merged with other variables server-side
- CLI variables can override secrets (documented behavior)

**Logging**:
- Never log secret values
- Redact sensitive information in CloudWatch Logs
- Log only variable keys, not values

### Data Access Control

**Suite Access**:
- Verify user has access to the test suite (scope-based)
- Verify user has access to all usecases in the suite
- Return 403 if access denied

**Execution Records**:
- Execution records inherit access control from parent usecase
- Suite execution records inherit access control from parent suite

---

## Performance Considerations

### Execution Record Creation

**Batch Operations**:
- Create execution records sequentially (DynamoDB doesn't support batch writes across different partition keys)
- Each usecase requires multiple DynamoDB operations:
  - 1 Put for execution record
  - N Puts for execution steps (where N = number of steps)
  - 1 Put for execution hooks (if present)
  - 1 Put for execution variables
  - 1 Put for execution headers (if present)

**Estimated Latency**:
- Small suite (3 usecases, 5 steps each): ~2-3 seconds
- Medium suite (10 usecases, 10 steps each): ~8-10 seconds
- Large suite (50 usecases, 20 steps each): ~40-60 seconds

**Timeout Configuration**:
- Lambda timeout: 300 seconds (5 minutes)
- API Gateway timeout: 29 seconds (hard limit)
- **Problem**: Large suites will exceed API Gateway timeout

**Solution for Large Suites**:
- For v1.0: Document maximum suite size (recommend ≤10 usecases)
- For v2.0: Consider async pattern:
  - Endpoint returns immediately with suite_execution_id
  - Lambda continues processing in background
  - Client polls for completion status

### DynamoDB Throughput

**Read Operations**:
- 1 read for suite definition
- 1 query for suite-usecase mappings
- N reads for usecase definitions (where N = number of usecases)
- N reads for usecase secrets
- N reads for usecase variables
- Total: ~4N + 2 read operations

**Write Operations**:
- 1 write for suite execution record
- N writes for execution records
- N * M writes for execution steps (where M = avg steps per usecase)
- N writes for execution hooks
- N writes for execution variables
- N writes for execution headers
- Total: ~(4N + N*M + 1) write operations

**Provisioned Capacity**:
- Use on-demand billing mode (existing configuration)
- No throttling expected for typical usage patterns
- Monitor CloudWatch metrics for throttling

### Memory Usage

**Lambda Memory**:
- Recommended: 512 MB
- Peak usage: ~200-300 MB for large suites
- Includes usecase definitions, steps, and execution records in memory

### Optimization Opportunities

**Parallel Fetching**:
- Fetch usecase definitions in parallel using asyncio
- Fetch secrets and variables in parallel
- Reduces latency by ~50% for large suites

**Caching**:
- Cache usecase definitions if same usecase appears in multiple suites (future enhancement)
- Cache secrets for duration of Lambda execution

---

## Monitoring & Observability

### CloudWatch Metrics

**Custom Metrics**:
```python
# Publish custom metrics using boto3 CloudWatch client
cloudwatch = boto3.client('cloudwatch')

cloudwatch.put_metric_data(
    Namespace='NovaActQA/SuiteExecution',
    MetricData=[
        {
            'MetricName': 'SuiteExecutionCreated',
            'Value': 1,
            'Unit': 'Count',
            'Dimensions': [
                {'Name': 'TriggerType', 'Value': 'ci_runner'}
            ]
        },
        {
            'MetricName': 'UsecaseExecutionsCreated',
            'Value': len(execution_ids),
            'Unit': 'Count'
        },
        {
            'MetricName': 'ExecutionCreationDuration',
            'Value': duration_ms,
            'Unit': 'Milliseconds'
        }
    ]
)
```

**Metrics to Track**:
- Suite executions created (count)
- Usecase executions created (count)
- Execution creation duration (milliseconds)
- Errors by type (count)
- Base URL overrides applied (count)
- Variable overrides applied (count)

### CloudWatch Logs

**Structured Logging**:
```python
import json

def log_event(event_type, data):
    log_entry = {
        'timestamp': get_current_timestamp(),
        'event_type': event_type,
        'data': data
    }
    print(json.dumps(log_entry))

# Usage
log_event('suite_execution_started', {
    'suite_id': suite_id,
    'suite_execution_id': suite_execution_id,
    'usecase_count': len(usecases),
    'overrides': {
        'base_url': bool(base_url),
        'variables': bool(variables),
        'region': bool(region),
        'model_id': bool(model_id)
    }
})
```

**Log Levels**:
- INFO: Normal execution flow
- WARN: Recoverable issues (missing optional fields)
- ERROR: Failures (validation errors, DynamoDB errors)

### EventBridge Events

**Suite Execution Events**:
```python
eventbridge.put_events(
    Entries=[{
        'Source': 'nova-act-qa-studio.suite-execution',
        'DetailType': 'nova-act-qa-studio.suite-execution.created',
        'Detail': json.dumps({
            'suite_id': suite_id,
            'suite_execution_id': suite_execution_id,
            'trigger_type': 'ci_runner',
            'usecase_count': len(execution_ids),
            'timestamp': get_current_timestamp()
        }),
        'EventBusName': 'default'
    }]
)
```

**Event Types**:
- `suite-execution.created` - Suite execution record created
- `suite-execution.completed` - All usecases completed (future)
- `suite-execution.failed` - Suite execution failed (future)

### Alarms

**CloudWatch Alarms**:
- High error rate (>5% of requests)
- High latency (p99 > 10 seconds)
- DynamoDB throttling
- Lambda timeout errors

---

## Rollout Plan

### Phase 1: Development & Testing (Week 1)

**Tasks**:
- [ ] Implement Lambda function
- [ ] Implement URL override utility
- [ ] Implement variable merge utility
- [ ] Write unit tests (≥70% coverage)
- [ ] Deploy to development environment
- [ ] Run integration tests

**Success Criteria**:
- All unit tests pass
- Integration tests pass
- No regressions in existing functionality

### Phase 2: Staging Validation (Week 2)

**Tasks**:
- [ ] Deploy to staging environment
- [ ] Manual testing with real test suites
- [ ] Performance testing with large suites
- [ ] Security review
- [ ] Documentation review

**Success Criteria**:
- Endpoint works with real data
- Performance meets expectations
- Security review approved
- Documentation complete

### Phase 3: Production Deployment (Week 2)

**Tasks**:
- [ ] Deploy to production
- [ ] Monitor CloudWatch metrics
- [ ] Monitor error rates
- [ ] Enable for CI/CD runner (WP2)

**Success Criteria**:
- Zero errors in first 24 hours
- Latency within acceptable range
- CI/CD runner can use endpoint successfully

### Rollback Plan

**If issues detected**:
1. Disable endpoint in API Gateway (remove route)
2. Revert Lambda function to previous version
3. Investigate issue in development environment
4. Fix and redeploy

**Rollback Triggers**:
- Error rate >10%
- Latency p99 >30 seconds
- DynamoDB throttling
- Security vulnerability discovered

---

## Dependencies

### Internal Dependencies

**WP1a (Execution Record & Trigger Type)**:
- Required: ci_runner trigger type support
- Required: execute_usecase Lambda accepts ci_runner
- Required: Execution records created without ECS tasks

**Existing Infrastructure**:
- DynamoDB table with existing schema
- API Gateway with Cognito authorizer
- Lambda execution role with DynamoDB permissions
- EventBridge event bus

### External Dependencies

**AWS Services**:
- DynamoDB (existing)
- API Gateway (existing)
- Lambda (existing)
- Cognito (existing)
- Secrets Manager (existing)
- EventBridge (existing)
- CloudWatch (existing)

**Python Libraries**:
- boto3 (AWS SDK)
- urllib.parse (standard library)
- json (standard library)
- re (standard library)
- uuid (standard library)

### Downstream Dependencies

**WP2 (CI/CD Runner Core)**:
- Will call this endpoint to create suite executions
- Depends on response format
- Depends on error handling behavior

---

## API Documentation

### Endpoint Specification

**Path**: `POST /api/test-suites/{id}/execute`

**Authentication**: Required (Cognito JWT token)

**Authorization**: Requires scopes `api/suite.write` and `api/execution.write`

**Path Parameters**:
- `id` (string, required) - Test suite UUID

**Request Body**:
```json
{
  "trigger_type": "ci_runner",
  "base_url": "https://example.com",
  "variables": {
    "username": "testuser",
    "api_key": "secret123"
  },
  "region": "us-east-1",
  "model_id": "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
}
```

**Request Body Schema**:
- `trigger_type` (string, required) - Must be "ci_runner"
- `base_url` (string, optional) - Base URL override for all usecases
- `variables` (object, optional) - Variable overrides (key-value pairs)
- `region` (string, optional) - AWS region override
- `model_id` (string, optional) - Bedrock model ID override

**Response (200 OK)**:
```json
{
  "suite_execution_id": "01234567-89ab-cdef-0123-456789abcdef",
  "suite_id": "01234567-89ab-cdef-0123-456789abcdef",
  "status": "pending",
  "created_at": "2024-02-16T12:00:00Z",
  "execution_ids": [
    {
      "usecase_id": "01234567-89ab-cdef-0123-456789abcdef",
      "execution_id": "01234567-89ab-cdef-0123-456789abcdef",
      "usecase_name": "Login with valid credentials"
    },
    {
      "usecase_id": "01234567-89ab-cdef-0123-456789abcdef",
      "execution_id": "01234567-89ab-cdef-0123-456789abcdef",
      "usecase_name": "Login with invalid password"
    }
  ]
}
```

**Error Responses**:

**400 Bad Request**:
```json
{
  "error": "Unresolved variables",
  "message": "Unresolved variables: username, password",
  "details": {
    "usecase_id": "01234567-89ab-cdef-0123-456789abcdef",
    "usecase_name": "Login test"
  }
}
```

**403 Forbidden**:
```json
{
  "error": "Forbidden",
  "message": "Insufficient permissions",
  "required_scopes": ["api/suite.write", "api/execution.write"],
  "token_scopes": ["api/suite.read"]
}
```

**404 Not Found**:
```json
{
  "error": "Test suite not found",
  "message": "No test suite found with ID: 01234567-89ab-cdef-0123-456789abcdef"
}
```

**500 Internal Server Error**:
```json
{
  "error": "Database error",
  "message": "Failed to create execution records"
}
```

### Example Usage

**cURL**:
```bash
curl -X POST \
  'https://api.example.com/api/test-suites/01234567-89ab-cdef-0123-456789abcdef/execute' \
  -H 'Authorization: Bearer <jwt_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "trigger_type": "ci_runner",
    "base_url": "https://production.example.com",
    "variables": {
      "username": "prod_user",
      "api_key": "prod_key_123"
    },
    "region": "us-west-2",
    "model_id": "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
  }'
```

**Python**:
```python
import requests

response = requests.post(
    'https://api.example.com/api/test-suites/01234567-89ab-cdef-0123-456789abcdef/execute',
    headers={
        'Authorization': f'Bearer {jwt_token}',
        'Content-Type': 'application/json'
    },
    json={
        'trigger_type': 'ci_runner',
        'base_url': 'https://production.example.com',
        'variables': {
            'username': 'prod_user',
            'api_key': 'prod_key_123'
        },
        'region': 'us-west-2',
        'model_id': 'us.anthropic.claude-3-5-sonnet-20241022-v2:0'
    }
)

data = response.json()
suite_execution_id = data['suite_execution_id']
execution_ids = data['execution_ids']
```

---

## Open Questions

### 1. API Gateway Timeout for Large Suites

**Question**: How should we handle test suites with >10 usecases that may exceed API Gateway's 29-second timeout?

**Options**:
- A) Document maximum suite size (≤10 usecases) for v1.0
- B) Implement async pattern (return immediately, process in background)
- C) Split large suites into smaller batches

**Recommendation**: Option A for v1.0, Option B for v2.0

**Decision needed by**: Before production deployment

---

### 2. Parallel vs Sequential Execution Record Creation

**Question**: Should we create execution records in parallel or sequentially?

**Options**:
- A) Sequential (simpler, easier to debug)
- B) Parallel (faster, more complex)

**Trade-offs**:
- Sequential: Easier error handling, slower for large suites
- Parallel: Faster, but harder to handle partial failures

**Recommendation**: Sequential for v1.0 (simpler), parallel for v2.0 (optimization)

**Decision needed by**: Before implementation

---

### 3. Partial Failure Handling

**Question**: If execution record creation fails for one usecase (e.g., usecase not found), should we:

**Options**:
- A) Fail entire request, create no execution records
- B) Create execution records for successful usecases, return partial success
- C) Create execution records for all, mark failed ones as "failed"

**Recommendation**: Option A (fail fast, atomic operation)

**Rationale**: Easier to reason about, prevents partial state

**Decision needed by**: Before implementation

---

## Success Criteria

- [ ] Endpoint accepts POST requests with suite ID
- [ ] Suite execution record created in DynamoDB
- [ ] Execution records created for all usecases in suite
- [ ] Base URL override applied correctly
- [ ] Variable merge precedence working (CLI > usecase > secrets)
- [ ] Variable validation rejects unresolved templates
- [ ] Region and model_id overrides applied
- [ ] No ECS tasks spawned (trigger_type=ci_runner)
- [ ] Response contains suite_execution_id and all execution_ids
- [ ] OAuth scope validation working
- [ ] Unit test coverage ≥70%
- [ ] Integration tests pass
- [ ] API documentation updated
- [ ] Performance acceptable for suites with ≤10 usecases
- [ ] Error handling working for all error scenarios

---

## References

- [WP1b Requirements Document](./requirements.md)
- [WP1a Design Document](../wp1a-execution-record-trigger-type/design.md)
- [CI/CD Runner Design Document](../../../.kiro/design/qa-studio-ci-runner.md)
- [Test Suite Schema Documentation](../../../lambdas/endpoints/test_suite_schema.py)
- [Existing execute_usecase Lambda](../../../lambdas/endpoints/execute_usecase.py)
- [DynamoDB Steering Rules](../../../.kiro/steering/01_dynamodb.md)
- [API Design Steering Rules](../../../.kiro/steering/02_api-design.md)
- [Security Steering Rules](../../../.kiro/steering/03_security.md)

