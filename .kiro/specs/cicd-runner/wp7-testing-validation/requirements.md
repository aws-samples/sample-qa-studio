# Work Package 7: Testing & Validation

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP7 - Testing & Validation
- **Estimated Duration**: 4 days
- **Dependencies**: WP6 (Documentation)
- **Status**: Not Started

---

## Overview

Perform comprehensive end-to-end testing and validation of the CI/CD runner across multiple CI/CD platforms, conduct load testing, security review, and performance benchmarking to ensure production readiness.

---

## User Stories

### US1: As a QA engineer, I need to validate the runner works in real CI/CD platforms
**Acceptance Criteria**:
- Runner tested in GitHub Actions
- Runner tested in GitLab CI
- Runner tested in Jenkins
- Runner tested in CircleCI
- All tests pass in each platform

### US2: As a platform owner, I need to ensure the runner handles large test suites
**Acceptance Criteria**:
- Load testing with 10+ use cases
- Load testing with 50+ use cases
- Load testing with 100+ use cases
- Performance metrics collected
- Resource usage monitored

### US3: As a security engineer, I need to verify the runner is secure
**Acceptance Criteria**:
- Security review completed
- Vulnerability scan passed
- Secret handling validated
- OAuth flow validated
- Container security verified

### US4: As a DevOps engineer, I need performance benchmarks
**Acceptance Criteria**:
- Execution time benchmarks
- Artifact upload time benchmarks
- Memory usage benchmarks
- CPU usage benchmarks
- Network usage benchmarks

---

## Testing Strategy

### 1. End-to-End Testing

**Test Scenarios**:
- Single use case execution
- Multiple use cases in parallel
- Test suite with base URL override
- Test suite with variable overrides
- Test suite with all overrides
- Failed test handling
- Timeout handling
- Network failure handling
- Authentication failure handling

### 2. CI/CD Platform Testing

**Platforms to Test**:
- GitHub Actions
- GitLab CI
- Jenkins
- CircleCI

**Test Cases per Platform**:
- Basic execution
- Execution with overrides
- Failed test handling
- Secret management
- Exit code handling
- Artifact access

### 3. Load Testing

**Test Suites**:
- Small: 1-5 use cases
- Medium: 10-25 use cases
- Large: 50-100 use cases

**Metrics to Collect**:
- Total execution time
- Memory usage (peak and average)
- CPU usage (peak and average)
- Network bandwidth
- Artifact upload time
- API request count

### 4. Security Testing

**Areas to Test**:
- OAuth authentication
- Secret handling
- Environment variable exposure
- Container security
- API communication (HTTPS)
- Presigned URL security

### 5. Performance Benchmarking

**Benchmarks**:
- Execution time per use case
- Parallel execution speedup
- Artifact upload time
- API response time
- Container startup time

---

## Implementation Details

### 1. E2E Test Suite

**File**: `tests/e2e/test_runner_e2e.py`

```python
import pytest
import subprocess
import os

@pytest.fixture
def runner_env():
    """Setup environment variables for runner."""
    return {
        'OAUTH_CLIENT_ID': os.getenv('TEST_OAUTH_CLIENT_ID'),
        'OAUTH_CLIENT_SECRET': os.getenv('TEST_OAUTH_CLIENT_SECRET'),
        'OAUTH_TOKEN_ENDPOINT': os.getenv('TEST_OAUTH_TOKEN_ENDPOINT'),
        'API_ENDPOINT': os.getenv('TEST_API_ENDPOINT')
    }

def test_single_usecase_execution(runner_env):
    """Test execution of single use case."""
    result = subprocess.run(
        [
            'docker', 'run', '--rm',
            '-e', f"OAUTH_CLIENT_ID={runner_env['OAUTH_CLIENT_ID']}",
            '-e', f"OAUTH_CLIENT_SECRET={runner_env['OAUTH_CLIENT_SECRET']}",
            '-e', f"OAUTH_TOKEN_ENDPOINT={runner_env['OAUTH_TOKEN_ENDPOINT']}",
            '-e', f"API_ENDPOINT={runner_env['API_ENDPOINT']}",
            'qa-studio-ci-runner:latest',
            '--suite-id', 'test-suite-single',
            '--verbose'
        ],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0, f"Runner failed: {result.stderr}"
    assert "✓ PASSED" in result.stdout

def test_parallel_execution(runner_env):
    """Test parallel execution of multiple use cases."""
    result = subprocess.run(
        [
            'docker', 'run', '--rm',
            '-e', f"OAUTH_CLIENT_ID={runner_env['OAUTH_CLIENT_ID']}",
            '-e', f"OAUTH_CLIENT_SECRET={runner_env['OAUTH_CLIENT_SECRET']}",
            '-e', f"OAUTH_TOKEN_ENDPOINT={runner_env['OAUTH_TOKEN_ENDPOINT']}",
            '-e', f"API_ENDPOINT={runner_env['API_ENDPOINT']}",
            'qa-studio-ci-runner:latest',
            '--suite-id', 'test-suite-parallel',
            '--verbose'
        ],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    # Verify all use cases executed
    assert result.stdout.count("✓ PASSED") >= 3

def test_base_url_override(runner_env):
    """Test base URL override functionality."""
    result = subprocess.run(
        [
            'docker', 'run', '--rm',
            '-e', f"OAUTH_CLIENT_ID={runner_env['OAUTH_CLIENT_ID']}",
            '-e', f"OAUTH_CLIENT_SECRET={runner_env['OAUTH_CLIENT_SECRET']}",
            '-e', f"OAUTH_TOKEN_ENDPOINT={runner_env['OAUTH_TOKEN_ENDPOINT']}",
            '-e', f"API_ENDPOINT={runner_env['API_ENDPOINT']}",
            'qa-studio-ci-runner:latest',
            '--suite-id', 'test-suite-url-override',
            '--base-url', 'https://staging.example.com',
            '--verbose'
        ],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert "base URL override" in result.stdout.lower()

def test_variable_override(runner_env):
    """Test variable override functionality."""
    result = subprocess.run(
        [
            'docker', 'run', '--rm',
            '-e', f"OAUTH_CLIENT_ID={runner_env['OAUTH_CLIENT_ID']}",
            '-e', f"OAUTH_CLIENT_SECRET={runner_env['OAUTH_CLIENT_SECRET']}",
            '-e', f"OAUTH_TOKEN_ENDPOINT={runner_env['OAUTH_TOKEN_ENDPOINT']}",
            '-e', f"API_ENDPOINT={runner_env['API_ENDPOINT']}",
            'qa-studio-ci-runner:latest',
            '--suite-id', 'test-suite-variables',
            '--var', 'username=testuser',
            '--var', 'password=testpass',
            '--verbose'
        ],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0

def test_failed_test_exit_code(runner_env):
    """Test exit code when test fails."""
    result = subprocess.run(
        [
            'docker', 'run', '--rm',
            '-e', f"OAUTH_CLIENT_ID={runner_env['OAUTH_CLIENT_ID']}",
            '-e', f"OAUTH_CLIENT_SECRET={runner_env['OAUTH_CLIENT_SECRET']}",
            '-e', f"OAUTH_TOKEN_ENDPOINT={runner_env['OAUTH_TOKEN_ENDPOINT']}",
            '-e', f"API_ENDPOINT={runner_env['API_ENDPOINT']}",
            'qa-studio-ci-runner:latest',
            '--suite-id', 'test-suite-failing'
        ],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 1, "Expected exit code 1 for failed test"
    assert "✗ FAILED" in result.stdout

def test_authentication_failure():
    """Test exit code when authentication fails."""
    result = subprocess.run(
        [
            'docker', 'run', '--rm',
            '-e', 'OAUTH_CLIENT_ID=invalid',
            '-e', 'OAUTH_CLIENT_SECRET=invalid',
            '-e', 'OAUTH_TOKEN_ENDPOINT=https://invalid.com/oauth2/token',
            '-e', 'API_ENDPOINT=https://api.example.com',
            'qa-studio-ci-runner:latest',
            '--suite-id', 'test-suite-id'
        ],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 2, "Expected exit code 2 for auth failure"
    assert "authentication failed" in result.stderr.lower()
```

### 2. Load Testing Script

**File**: `tests/load/load_test.py`

```python
import time
import psutil
import subprocess
from typing import Dict, List

class LoadTester:
    """Load testing for CI/CD runner."""
    
    def __init__(self, runner_env: Dict[str, str]):
        self.runner_env = runner_env
        self.results = []
    
    def run_load_test(self, suite_id: str, suite_size: str):
        """Run load test for a test suite."""
        print(f"\n{'='*60}")
        print(f"Load Test: {suite_size} ({suite_id})")
        print(f"{'='*60}\n")
        
        # Start monitoring
        start_time = time.time()
        process = psutil.Process()
        
        # Run runner
        result = subprocess.run(
            [
                'docker', 'run', '--rm',
                '-e', f"OAUTH_CLIENT_ID={self.runner_env['OAUTH_CLIENT_ID']}",
                '-e', f"OAUTH_CLIENT_SECRET={self.runner_env['OAUTH_CLIENT_SECRET']}",
                '-e', f"OAUTH_TOKEN_ENDPOINT={self.runner_env['OAUTH_TOKEN_ENDPOINT']}",
                '-e', f"API_ENDPOINT={self.runner_env['API_ENDPOINT']}",
                'qa-studio-ci-runner:latest',
                '--suite-id', suite_id,
                '--verbose'
            ],
            capture_output=True,
            text=True
        )
        
        # Calculate metrics
        end_time = time.time()
        duration = end_time - start_time
        
        # Parse results
        passed = result.stdout.count("✓ PASSED")
        failed = result.stdout.count("✗ FAILED")
        
        # Store results
        test_result = {
            'suite_size': suite_size,
            'suite_id': suite_id,
            'duration': duration,
            'passed': passed,
            'failed': failed,
            'exit_code': result.returncode
        }
        
        self.results.append(test_result)
        
        # Print summary
        print(f"Duration: {duration:.2f}s")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Exit Code: {result.returncode}")
    
    def print_summary(self):
        """Print load test summary."""
        print(f"\n{'='*60}")
        print("Load Test Summary")
        print(f"{'='*60}\n")
        
        for result in self.results:
            print(f"{result['suite_size']:15} | "
                  f"Duration: {result['duration']:6.2f}s | "
                  f"Passed: {result['passed']:3} | "
                  f"Failed: {result['failed']:3}")

if __name__ == '__main__':
    import os
    
    runner_env = {
        'OAUTH_CLIENT_ID': os.getenv('TEST_OAUTH_CLIENT_ID'),
        'OAUTH_CLIENT_SECRET': os.getenv('TEST_OAUTH_CLIENT_SECRET'),
        'OAUTH_TOKEN_ENDPOINT': os.getenv('TEST_OAUTH_TOKEN_ENDPOINT'),
        'API_ENDPOINT': os.getenv('TEST_API_ENDPOINT')
    }
    
    tester = LoadTester(runner_env)
    
    # Run load tests
    tester.run_load_test('suite-small', 'Small (5 tests)')
    tester.run_load_test('suite-medium', 'Medium (25 tests)')
    tester.run_load_test('suite-large', 'Large (100 tests)')
    
    # Print summary
    tester.print_summary()
```

### 3. Security Testing

**Checklist**:
- [ ] OAuth credentials not exposed in logs
- [ ] Secrets not exposed in error messages
- [ ] Container runs as non-root user (optional)
- [ ] No hardcoded credentials in code
- [ ] HTTPS enforced for all API calls
- [ ] Presigned URLs expire after 1 hour
- [ ] Container vulnerability scan passed (Trivy)
- [ ] Dependency vulnerability scan passed (Safety)

**Commands**:
```bash
# Scan container for vulnerabilities
trivy image qa-studio-ci-runner:latest

# Scan Python dependencies
safety check -r requirements.txt

# Check for secrets in code
trufflehog --regex --entropy=False .
```

### 4. Performance Benchmarking

**Metrics to Collect**:
```python
{
    "suite_size": 10,
    "total_duration": 120.5,
    "avg_usecase_duration": 12.05,
    "parallel_speedup": 8.3,  # vs sequential
    "memory_peak_mb": 512,
    "memory_avg_mb": 384,
    "cpu_peak_percent": 85,
    "cpu_avg_percent": 45,
    "artifact_upload_time": 15.2,
    "api_requests": 45,
    "api_avg_response_time": 0.25
}
```

---

## CI/CD Platform Testing

### GitHub Actions Test

**File**: `.github/workflows/test-runner.yml`

```yaml
name: Test CI/CD Runner

on:
  push:
    branches: [main]

jobs:
  test-runner:
    runs-on: ubuntu-latest
    
    steps:
      - name: Test Small Suite
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            qa-studio-ci-runner:latest \
            --suite-id suite-small \
            --verbose
      
      - name: Test Medium Suite
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            qa-studio-ci-runner:latest \
            --suite-id suite-medium \
            --verbose
```

---

## Test Data Setup

**Required Test Suites**:
- `test-suite-single` - 1 use case (passing)
- `test-suite-parallel` - 5 use cases (all passing)
- `test-suite-failing` - 1 use case (failing)
- `test-suite-url-override` - 1 use case (tests base URL override)
- `test-suite-variables` - 1 use case (tests variable override)
- `suite-small` - 5 use cases (load testing)
- `suite-medium` - 25 use cases (load testing)
- `suite-large` - 100 use cases (load testing)

---

## Success Criteria

- [ ] E2E tests pass for all scenarios
- [ ] Runner tested in 4+ CI/CD platforms
- [ ] Load testing completed for small/medium/large suites
- [ ] Performance benchmarks collected
- [ ] Security review completed
- [ ] Vulnerability scans passed
- [ ] All test suites execute successfully
- [ ] Exit codes work correctly in all platforms
- [ ] Artifacts uploaded successfully
- [ ] Documentation validated with real usage
