# WP2: Runner Integration

## Objective

Enhance CI/CD runner to support single use case execution with both local-only and remote modes, and add token file authentication.

## Duration

Week 2-3 (5-7 days)

## Current State

**Already Implemented:**
- ✅ `--base-url` - Override starting URL
- ✅ `--var` - Variable overrides (repeatable)
- ✅ `--region` - AWS region override
- ✅ `--model-id` - Model override
- ✅ `--suite-id` - Test suite execution

**Not Implemented:**
- ❌ Single use case execution
- ❌ Token file authentication
- ❌ Local-only mode

## Requirements

### 1. Add CLI Flags

**Modify: `qa-studio-ci-runner/src/cli/parser.py`**

**Changes:**
```python
@click.command()
@click.option('--suite-id', help='Test suite ID to execute')  # Make optional (remove required=True)
@click.option('--usecase-id', help='Single use case ID to execute')  # NEW
@click.option('--local-only', is_flag=True, help='Local execution only (no execution records)')  # NEW
@click.option('--token-file', help='Path to token file (alternative to client credentials)')  # NEW
@click.option('--base-url', help='Override base URL for all use cases')
@click.option('--var', 'variables', multiple=True, help='Override variable (key=value, repeatable)')
@click.option('--region', help='Override AWS region for browser')
@click.option('--model-id', help='Override Nova Act model ID')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
@click.option('--timeout', type=int, default=3600, help='Global timeout in seconds')
@click.option('--keep-artifacts', is_flag=True, help='Keep local artifact files after upload')
def main(
    suite_id: str,
    usecase_id: str,  # NEW
    local_only: bool,  # NEW
    token_file: str,  # NEW
    base_url: str,
    variables: tuple,
    region: str,
    model_id: str,
    verbose: bool,
    timeout: int,
    keep_artifacts: bool
):
    """Nova Act QA Studio CI/CD Runner"""
    
    # Validate: require either suite-id or usecase-id
    if not suite_id and not usecase_id:
        raise click.BadParameter("Either --suite-id or --usecase-id is required")
    
    if suite_id and usecase_id:
        raise click.BadParameter("Cannot use both --suite-id and --usecase-id")
    
    # Validate: local-only only works with usecase-id
    if local_only and not usecase_id:
        raise click.BadParameter("--local-only requires --usecase-id")
    
    # Parse variables...
    # Setup logging...
    
    # Route to appropriate execution
    if usecase_id:
        from ..main import run_usecase
        run_usecase(
            usecase_id=usecase_id,
            local_only=local_only,
            token_file=token_file,
            base_url=base_url,
            variables=parsed_vars,
            region=region,
            model_id=model_id,
            timeout=timeout
        )
    else:
        from ..main import run_runner
        run_runner(
            suite_id=suite_id,
            token_file=token_file,
            base_url=base_url,
            variables=parsed_vars,
            region=region,
            model_id=model_id,
            timeout=timeout,
            keep_artifacts=keep_artifacts
        )
```

### 2. Token File Authentication

**Modify: `qa-studio-ci-runner/src/auth/oauth_client.py`**

**Add token file support:**
```python
class OAuthClient:
    def __init__(self, client_id=None, client_secret=None, token_file=None):
        """
        Initialize OAuth client.
        
        Args:
            client_id: Cognito client ID (for client credentials flow)
            client_secret: Cognito client secret (for client credentials flow)
            token_file: Path to token file (alternative to client credentials)
        """
        if token_file:
            self.token = self._load_token_from_file(token_file)
            self.token_file = token_file
            self.use_token_file = True
        elif client_id and client_secret:
            self.client_id = client_id
            self.client_secret = client_secret
            self.use_token_file = False
        else:
            raise ValueError("Either token_file or (client_id and client_secret) required")
    
    def _load_token_from_file(self, token_file: str) -> str:
        """Load access token from file."""
        from pathlib import Path
        import json
        
        path = Path(token_file).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Token file not found: {token_file}")
        
        with open(path) as f:
            data = json.load(f)
            return data['access_token']
    
    def get_token(self) -> str:
        """Get access token."""
        if self.use_token_file:
            # Reload token from file (in case it was refreshed)
            return self._load_token_from_file(self.token_file)
        else:
            # Use client credentials flow
            return self._get_client_credentials_token()
```

### 3. Single Use Case Execution

**Create: `qa-studio-ci-runner/src/api/usecases.py`**

```python
"""API client for use case operations."""

class UseCaseAPI:
    def __init__(self, api_client):
        self.client = api_client
    
    def get_usecase(self, usecase_id: str) -> dict:
        """
        Get use case metadata.
        
        Returns:
            {
                'id': str,
                'name': str,
                'starting_url': str,
                'executing_region': str,
                'model_id': str,
                ...
            }
        """
        return self.client.get(f'/usecase/{usecase_id}')
    
    def get_steps(self, usecase_id: str) -> list:
        """Get steps for use case."""
        response = self.client.get(f'/usecase/{usecase_id}/steps')
        return response.get('steps', [])
    
    def get_variables(self, usecase_id: str) -> dict:
        """Get variables for use case."""
        response = self.client.get(f'/usecase/{usecase_id}/variables')
        return response.get('variables', {})
    
    def get_secrets(self, usecase_id: str) -> list:
        """Get secret keys for use case."""
        response = self.client.get(f'/usecase/{usecase_id}/secrets')
        return response.get('secrets', [])
    
    def create_execution(self, usecase_id: str, trigger_type: str = 'ci_runner') -> dict:
        """
        Create execution record.
        
        Returns:
            {
                'execution_id': str,
                'usecase_id': str,
                'status': str,
                ...
            }
        """
        return self.client.post(
            f'/usecase/{usecase_id}/execute',
            params={'trigger-type': trigger_type}
        )
```

**Modify: `qa-studio-ci-runner/src/main.py`**

**Add new function:**
```python
def run_usecase(
    usecase_id: str,
    local_only: bool,
    token_file: str = None,
    base_url: str = None,
    variables: dict = None,
    region: str = None,
    model_id: str = None,
    timeout: int = 3600
) -> None:
    """
    Execute single use case.
    
    Args:
        usecase_id: Use case UUID
        local_only: If True, skip execution records and S3 uploads
        token_file: Path to token file
        base_url: Optional base URL override
        variables: Variable overrides
        region: Optional AWS region override
        model_id: Optional model ID override
        timeout: Global timeout in seconds
    """
    try:
        # Load configuration
        settings = Settings.from_env()
        
        # Validate AWS session
        validate_aws_session()
        
        # Initialize OAuth client
        if token_file:
            oauth_client = OAuthClient(token_file=token_file)
        else:
            oauth_client = OAuthClient(
                client_id=settings.client_id,
                client_secret=settings.client_secret
            )
        
        # Initialize API client
        api_client = APIClient(settings.api_url, oauth_client)
        usecase_api = UseCaseAPI(api_client)
        
        if local_only:
            # Local-only mode: Fetch use case directly
            logger.info(f"Executing use case {usecase_id} in local-only mode")
            
            # Fetch use case definition
            usecase = usecase_api.get_usecase(usecase_id)
            steps = usecase_api.get_steps(usecase_id)
            variables_data = usecase_api.get_variables(usecase_id)
            secrets = usecase_api.get_secrets(usecase_id)
            
            # Merge variable overrides
            merged_variables = {**variables_data, **(variables or {})}
            
            # Override starting URL if provided
            starting_url = base_url or usecase['starting_url']
            
            # Execute locally
            engine = ExecutionEngine(
                api_client=api_client,
                region=region or usecase['executing_region'],
                model_id=model_id or usecase['model_id'],
                timeout=timeout
            )
            
            result = engine.execute_usecase_local(
                usecase_id=usecase_id,
                usecase_name=usecase['name'],
                starting_url=starting_url,
                steps=steps,
                variables=merged_variables,
                secrets=secrets
            )
            
            # Output results as JSON
            print(json.dumps(result, indent=2))
            
            # Exit with appropriate code
            sys.exit(0 if result['status'] == 'success' else 1)
            
        else:
            # Remote mode: Create execution record
            logger.info(f"Executing use case {usecase_id} with execution tracking")
            
            # Create execution
            execution = usecase_api.create_execution(usecase_id)
            execution_id = execution['execution_id']
            
            # Fetch execution details
            execution_api = ExecutionAPI(api_client)
            execution_details = execution_api.get_execution_details(
                usecase_id=usecase_id,
                execution_id=execution_id
            )
            
            # Execute with tracking
            engine = ExecutionEngine(
                api_client=api_client,
                region=region or execution_details['executing_region'],
                model_id=model_id or execution_details['model_id'],
                timeout=timeout
            )
            
            result = engine.execute_with_tracking(
                usecase_id=usecase_id,
                execution_id=execution_id,
                execution_details=execution_details,
                base_url=base_url,
                variables=variables
            )
            
            # Output results
            print(json.dumps(result, indent=2))
            
            # Exit with appropriate code
            sys.exit(0 if result['status'] == 'success' else 1)
            
    except Exception as e:
        logger.error(f"Error executing use case: {str(e)}", exc_info=True)
        sys.exit(2)
```

### 4. Execution Engine Updates

**Modify: `qa-studio-ci-runner/src/execution/engine.py`**

**Add method:**
```python
def execute_usecase_local(
    self,
    usecase_id: str,
    usecase_name: str,
    starting_url: str,
    steps: list,
    variables: dict,
    secrets: list
) -> dict:
    """
    Execute use case locally without creating execution records.
    
    Args:
        usecase_id: Use case UUID
        usecase_name: Use case name
        starting_url: Starting URL
        steps: List of steps
        variables: Variables
        secrets: Secret keys
    
    Returns:
        {
            'status': 'success' | 'failed',
            'usecaseId': str,
            'usecaseName': str,
            'duration': float,
            'steps': [...],
            'artifacts': {
                'video': str,
                'logs': str
            }
        }
    """
    import time
    from pathlib import Path
    
    start_time = time.time()
    
    # Create local artifacts directory
    artifacts_dir = Path(f'/tmp/qa-studio-artifacts/{usecase_id}')
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Execute steps
    step_results = []
    overall_status = 'success'
    
    for step in steps:
        step_result = self._execute_step(
            step=step,
            variables=variables,
            secrets=secrets,
            artifacts_dir=artifacts_dir
        )
        step_results.append(step_result)
        
        if step_result['status'] == 'failed':
            overall_status = 'failed'
            break
    
    duration = time.time() - start_time
    
    return {
        'status': overall_status,
        'usecaseId': usecase_id,
        'usecaseName': usecase_name,
        'duration': duration,
        'steps': step_results,
        'artifacts': {
            'video': str(artifacts_dir / 'recording.webm'),
            'logs': str(artifacts_dir / 'execution.log')
        }
    }
```

### 5. CLI Wrapper

**Create: `qa-studio-cli/src/runner/executor.py`**

```python
"""Wrapper for CI/CD runner execution."""

import subprocess
import json
from pathlib import Path

def execute_local(usecase_id: str, base_url: str = None, variables: dict = None) -> dict:
    """
    Execute test locally using bundled runner.
    
    Args:
        usecase_id: Use case UUID
        base_url: Optional base URL override
        variables: Optional variable overrides
    
    Returns:
        Execution result dict
    """
    token_file = Path.home() / '.qa-studio' / 'token.json'
    
    cmd = [
        'python', '-m', 'qa_studio_ci_runner',
        '--usecase-id', usecase_id,
        '--local-only',
        '--token-file', str(token_file)
    ]
    
    if base_url:
        cmd.extend(['--base-url', base_url])
    
    for key, value in (variables or {}).items():
        cmd.extend(['--var', f'{key}={value}'])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        raise RuntimeError(f"Execution failed: {result.stderr}")
```

## Testing

### Manual Testing

```bash
# Local-only execution
qa-studio-ci-runner --usecase-id <id> --local-only --token-file ~/.qa-studio/token.json

# Local-only with overrides
qa-studio-ci-runner --usecase-id <id> --local-only \
  --token-file ~/.qa-studio/token.json \
  --base-url http://localhost:3000 \
  --var username=testuser

# Remote execution (creates records)
qa-studio-ci-runner --usecase-id <id> --token-file ~/.qa-studio/token.json

# Suite execution (should still work)
qa-studio-ci-runner --suite-id <id> --token-file ~/.qa-studio/token.json

# Verify artifacts stored locally
ls /tmp/qa-studio-artifacts/<usecase-id>/
```

### Test Cases

1. **Token File Authentication**
   - Token loaded from file successfully
   - Invalid token file path handled
   - Missing token file handled

2. **Local-Only Mode**
   - Use case fetched directly from API
   - Steps executed locally
   - Artifacts stored in /tmp
   - No execution records created
   - No S3 uploads

3. **Remote Mode**
   - Execution record created
   - Steps fetched from execution API
   - Artifacts uploaded to S3
   - Execution status updated

4. **Variable Overrides**
   - Base URL override works
   - Variable overrides work
   - Variables merged correctly

5. **Suite Execution**
   - Existing suite execution still works
   - Token file works with suites

## Success Criteria

- ✅ Runner accepts `--token-file` flag
- ✅ Runner can execute single use case with `--usecase-id`
- ✅ `--local-only` skips execution records and S3 uploads
- ✅ Without `--local-only`, creates execution records and uploads artifacts
- ✅ CLI can spawn runner and capture output
- ✅ Base URL and variable overrides work with use case execution
- ✅ Existing suite execution still works
- ✅ All tests passing

## Dependencies

- Package 1 (CLI with authentication working)

## Deliverable

Enhanced runner with single use case execution:
```bash
# Local execution
qa-studio run <usecase-id> --base-url http://localhost:3000

# Remote execution (from CLI wrapper)
qa-studio-ci-runner --usecase-id <id> --token-file ~/.qa-studio/token.json
```

## Next Steps

After completion, proceed to Package 3 (Agent Skills) to create skills that use the CLI.
