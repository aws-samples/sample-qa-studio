# Work Package 1b: Test Suite Execution Endpoint

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP1b - Test Suite Execution Endpoint
- **Estimated Duration**: 3 days
- **Dependencies**: WP1a (Execution Record & Trigger Type)
- **Status**: Not Started

---

## Overview

Create a new API endpoint `POST /api/test-suites/{id}/execute` that serves as the entry point for CI/CD runner. This endpoint creates a suite execution record and execution records for ALL use cases in the suite, applies overrides (base_url, variables, region, model_id), and returns all execution IDs without spawning ECS tasks.

---

## User Stories

### US1: As a CI/CD runner, I need to execute an entire test suite with one API call
**Acceptance Criteria**:
- Single API endpoint accepts test suite ID
- Endpoint creates suite execution record
- Endpoint creates execution records for ALL use cases in the suite
- Endpoint returns suite_execution_id and list of all execution_ids
- No ECS tasks are spawned

### US2: As a CI/CD runner, I need to override base URLs for environment-specific testing
**Acceptance Criteria**:
- Endpoint accepts optional `base_url` parameter
- Base URL override replaces domain/origin in each usecase's starting_url
- URL path and query parameters are preserved
- Modified starting_url is stored in execution record
- Example: `https://staging.example.com/login?foo=bar` + `base_url=https://prod.example.com` → `https://prod.example.com/login?foo=bar`

### US3: As a CI/CD runner, I need to override variables for all use cases in a suite
**Acceptance Criteria**:
- Endpoint accepts optional `variables` object
- Variables are merged with precedence: CLI overrides > usecase variables > secrets
- All template variables must be resolved (no `{{variable}}` remaining)
- Merged variables are stored in execution record as EXECUTION_VARIABLES
- Missing variables cause immediate 400 error with clear message

### US4: As a CI/CD runner, I need to override region and model for all executions
**Acceptance Criteria**:
- Endpoint accepts optional `region` parameter
- Endpoint accepts optional `model_id` parameter
- Overrides are applied to all execution records in the suite
- Default values used if not specified

### US5: As a platform, I need to track suite-level execution status
**Acceptance Criteria**:
- Suite execution record is created with status "pending"
- Suite execution record links to all usecase execution IDs
- Suite execution record includes suite metadata (name, description)
- Individual execution records include `suite_execution_id` field

---

## Technical Requirements

### New Data Model

**Suite Execution Record (DynamoDB)**:
```python
{
    "PK": "SUITE#{suite_id}",
    "SK": "SUITE_EXECUTION#{suite_execution_id}",
    "suite_id": "uuid",
    "suite_execution_id": "uuid",
    "status": "pending" | "running" | "completed" | "failed",
    "trigger_type": "ci_runner",  # Always ci_runner for this endpoint
    "created_at": "ISO8601 timestamp",
    "started_at": "ISO8601 timestamp",
    "completed_at": "ISO8601 timestamp",
    "usecase_executions": [
        {
            "usecase_id": "uuid",
            "execution_id": "uuid",
            "status": "pending"
        }
    ],
    "overrides": {
        "base_url": "string",  # Optional
        "variables": {},       # Optional
        "region": "string",    # Optional
        "model_id": "string"   # Optional
    }
}
```

**Modified Execution Record**:
```python
{
    "PK": "USECASE#{usecase_id}",
    "SK": "EXECUTION#{execution_id}",
    "suite_execution_id": "uuid",  # NEW FIELD - links to parent suite execution
    "trigger_type": "ci_runner",
    "starting_url": "string",  # Modified with base_url override
    # ... existing fields
}
```

### New API Endpoint

**Endpoint**: `POST /api/test-suites/{id}/execute`

**Request Body**:
```json
{
  "trigger_type": "ci_runner",  // Required for this endpoint
  "base_url": "https://example.com",  // Optional
  "variables": {                       // Optional
    "username": "testuser",
    "api_key": "secret123"
  },
  "region": "us-east-1",              // Optional
  "model_id": "us.anthropic.claude-3-5-sonnet-20241022-v2:0"  // Optional
}
```

**Response**:
```json
{
  "suite_execution_id": "uuid",
  "suite_id": "uuid",
  "status": "pending",
  "created_at": "ISO8601 timestamp",
  "execution_ids": [
    {
      "usecase_id": "uuid",
      "execution_id": "uuid",
      "usecase_name": "Login with valid credentials"
    },
    {
      "usecase_id": "uuid",
      "execution_id": "uuid",
      "usecase_name": "Login with invalid password"
    }
  ]
}
```

**Error Responses**:
- `400`: Invalid request (missing variables, invalid base_url, etc.)
- `404`: Test suite not found
- `403`: Insufficient permissions (missing scopes)
- `500`: Internal server error

---

## Implementation Details

### Lambda Function: `execute_test_suite`

**High-Level Flow**:
```python
def execute_test_suite(event, context):
    # 1. Validate request
    suite_id = event['pathParameters']['id']
    body = json.loads(event['body'])
    
    # 2. Fetch test suite definition
    suite = get_test_suite(suite_id)
    if not suite:
        return error_response(404, 'Test suite not found')
    
    # 3. Create suite execution record
    suite_execution_id = str(uuid.uuid4())
    suite_execution = create_suite_execution_record(
        suite_id=suite_id,
        suite_execution_id=suite_execution_id,
        trigger_type='ci_runner',
        overrides=body
    )
    
    # 4. For each usecase in suite:
    execution_ids = []
    for usecase_id in suite['usecase_ids']:
        # Fetch usecase definition
        usecase = get_usecase(usecase_id)
        
        # Apply base URL override
        starting_url = apply_base_url_override(
            usecase['starting_url'],
            body.get('base_url')
        )
        
        # Merge variables (secrets < usecase vars < CLI overrides)
        secrets = get_usecase_secrets(usecase_id)
        usecase_vars = get_usecase_variables(usecase_id)
        merged_vars = merge_variables(secrets, usecase_vars, body.get('variables', {}))
        
        # Validate all variables resolved
        validate_variables_resolved(usecase, merged_vars)
        
        # Create execution record (trigger_type=ci_runner, no ECS task)
        execution_id = create_execution_record(
            usecase_id=usecase_id,
            suite_execution_id=suite_execution_id,
            trigger_type='ci_runner',
            starting_url=starting_url,
            variables=merged_vars,
            region=body.get('region', usecase.get('region')),
            model_id=body.get('model_id', usecase.get('model_id'))
        )
        
        execution_ids.append({
            'usecase_id': usecase_id,
            'execution_id': execution_id,
            'usecase_name': usecase['name']
        })
    
    # 5. Update suite execution with all execution IDs
    update_suite_execution_with_executions(suite_execution_id, execution_ids)
    
    # 6. Return response
    return success_response({
        'suite_execution_id': suite_execution_id,
        'suite_id': suite_id,
        'status': 'pending',
        'created_at': suite_execution['created_at'],
        'execution_ids': execution_ids
    })
```

### Base URL Override Logic
```python
def apply_base_url_override(original_url, base_url):
    """
    Replace domain/origin while preserving path and query params.
    
    Example:
        original_url = "https://staging.example.com/login?foo=bar"
        base_url = "https://prod.example.com"
        result = "https://prod.example.com/login?foo=bar"
    """
    if not base_url:
        return original_url
    
    from urllib.parse import urlparse, urlunparse
    
    parsed_original = urlparse(original_url)
    parsed_base = urlparse(base_url)
    
    # Replace scheme and netloc (domain), keep path, params, query, fragment
    return urlunparse((
        parsed_base.scheme,
        parsed_base.netloc,
        parsed_original.path,
        parsed_original.params,
        parsed_original.query,
        parsed_original.fragment
    ))
```

### Variable Merge Logic
```python
def merge_variables(secrets, usecase_vars, cli_vars):
    """
    Merge variables with precedence: CLI > usecase > secrets
    """
    merged = {}
    
    # Start with secrets (lowest priority)
    merged.update(secrets)
    
    # Override with usecase variables
    merged.update(usecase_vars)
    
    # Override with CLI variables (highest priority)
    merged.update(cli_vars)
    
    return merged

def validate_variables_resolved(usecase, variables):
    """
    Ensure all {{variable}} placeholders are resolved.
    """
    import re
    
    # Check starting_url, steps, hooks for unresolved variables
    template_pattern = r'\{\{(\w+)\}\}'
    
    usecase_str = json.dumps(usecase)
    unresolved = re.findall(template_pattern, usecase_str)
    
    missing = [var for var in unresolved if var not in variables]
    
    if missing:
        raise ValueError(f"Unresolved variables: {', '.join(missing)}")
```

---

## API Gateway Configuration

**Path**: `/test-suites/{id}/execute`
**Method**: `POST`
**Authorizer**: Cognito User Pool Authorizer
**Required Scopes**: `api/suite.write`, `api/execution.write`
**Lambda**: `execute_test_suite`

---

## Testing Requirements

### Unit Tests
- Test suite execution record creation
- Test base URL override logic with various URL formats
- Test variable merge precedence (CLI > usecase > secrets)
- Test variable validation (missing variables)
- Test execution record creation for all use cases
- Test suite_execution_id linking

### Integration Tests
- Execute test suite with no overrides
- Execute test suite with base_url override
- Execute test suite with variable overrides
- Execute test suite with region/model overrides
- Execute test suite with all overrides combined
- Verify no ECS tasks spawned
- Verify all execution records created in DynamoDB
- Verify suite execution record links to all executions

### Error Cases
- Test suite not found (404)
- Missing required variables (400)
- Invalid base_url format (400)
- Insufficient permissions (403)

---

## Security Considerations

- Validate OAuth scopes: `api/suite.write`, `api/execution.write`
- Ensure user has access to test suite
- Validate base_url is a valid URL
- Sanitize variable values to prevent injection
- Secrets are fetched server-side (not exposed in API response)

---

## DynamoDB Query Patterns

**Query suite executions**:
```python
PK = "SUITE#{suite_id}"
SK begins_with "SUITE_EXECUTION#"
```

**Query usecase executions by suite**:
```python
# Use GSI if needed, or query each usecase individually
# For now, store usecase_executions array in suite execution record
```

---

## Success Criteria

- [ ] New endpoint `POST /api/test-suites/{id}/execute` created
- [ ] Suite execution records created in DynamoDB
- [ ] All usecase execution records created with overrides applied
- [ ] Base URL override logic working correctly
- [ ] Variable merge logic with correct precedence
- [ ] No ECS tasks spawned for ci_runner trigger
- [ ] Unit test coverage ≥ 70%
- [ ] Integration tests pass
- [ ] API documentation updated
