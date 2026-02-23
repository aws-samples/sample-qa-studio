# GitHub Actions Integration

This guide shows how to integrate the Nova Act QA Studio CI/CD Runner into your GitHub Actions workflows for automated testing.

## Overview

The CI/CD runner can be integrated into GitHub Actions workflows to execute test suites automatically on code changes, pull requests, or scheduled intervals. The runner uses OAuth client credentials for authentication and reports test results via exit codes.

## Prerequisites

Before setting up GitHub Actions integration, ensure you have:

1. **Docker**: GitHub Actions runners include Docker by default
2. **OAuth Client**: Created via the Nova Act QA Studio platform with required scopes:
   - `api/suite.read` - Read test suite definitions
   - `api/suite.write` - Execute test suites
   - `api/execution.write` - Create and update execution records
3. **Test Suite ID**: UUID of the test suite to execute (found in platform UI)

## Quick Start

Basic workflow that runs tests on every push to main:

```yaml
name: QA Tests

on:
  push:
    branches: [main]

jobs:
  qa-tests:
    runs-on: ubuntu-latest
    
    steps:
      - name: Run QA Tests
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars.TEST_SUITE_ID }} \
            --verbose
```

## Setup Instructions

### Step 1: Create OAuth Client

Create an OAuth client in the Nova Act QA Studio platform:

1. Navigate to **Settings** → **OAuth Clients**
2. Click **Create OAuth Client**
3. Enter a name: `GitHub Actions - <Repository Name>`
4. Select scopes:
   - `api/suite.read`
   - `api/suite.write`
   - `api/execution.write`
5. Click **Create**
6. **Save the client secret** - it will only be shown once!

### Step 2: Configure GitHub Secrets

Add OAuth credentials as GitHub repository secrets:

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add the following secrets:

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `OAUTH_CLIENT_ID` | `7abc123def456` | OAuth client ID from platform |
| `OAUTH_CLIENT_SECRET` | `secret_xyz789...` | OAuth client secret (shown once at creation) |
| `OAUTH_TOKEN_ENDPOINT` | `https://domain.auth.us-east-1.amazoncognito.com/oauth2/token` | Cognito token endpoint URL |
| `API_ENDPOINT` | `https://abc123.execute-api.us-east-1.amazonaws.com/api` | Platform API base URL |

**Security Notes**:
- Secrets are encrypted and masked in logs
- Never commit secrets to your repository
- Use separate OAuth clients for different repositories/environments

### Step 3: Configure GitHub Variables

Add non-sensitive configuration as GitHub repository variables:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Click the **Variables** tab
3. Click **New repository variable**
4. Add the following variables:

| Variable Name | Value | Description |
|---------------|-------|-------------|
| `TEST_SUITE_ID` | `01234567-89ab-cdef-0123-456789abcdef` | Test suite UUID from platform |
| `STAGING_BASE_URL` | `https://staging.example.com` | Staging environment URL (optional) |
| `PRODUCTION_BASE_URL` | `https://production.example.com` | Production environment URL (optional) |

**Note**: Variables are visible in logs, so only use them for non-sensitive data.

### Step 4: Create Workflow File

Create `.github/workflows/qa-tests.yml` in your repository:

```yaml
name: QA Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  qa-tests:
    runs-on: ubuntu-latest
    
    steps:
      - name: Run QA Tests
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars.TEST_SUITE_ID }} \
            --verbose
```

### Step 5: Commit and Push

Commit the workflow file and push to GitHub:

```bash
git add .github/workflows/qa-tests.yml
git commit -m "Add QA test automation workflow"
git push origin main
```

The workflow will run automatically on the next push or pull request.

## Workflow Examples

### Example 1: Basic Workflow with Pull Requests

Run tests on pushes to main and all pull requests:

```yaml
name: QA Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  qa-tests:
    runs-on: ubuntu-latest
    
    steps:
      - name: Run QA Tests
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars.TEST_SUITE_ID }} \
            --verbose
      
      - name: Check test results
        if: failure()
        run: echo "Tests failed! Check the logs above for details."
```

### Example 2: Environment-Specific Testing

Test against staging environment with base URL override:

```yaml
name: Staging QA Tests

on:
  push:
    branches: [develop]
  pull_request:
    branches: [develop]

jobs:
  staging-tests:
    runs-on: ubuntu-latest
    
    steps:
      - name: Run Staging Tests
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars.TEST_SUITE_ID }} \
            --base-url ${{ vars.STAGING_BASE_URL }} \
            --verbose
```

### Example 3: Variable Overrides

Override test variables for different test scenarios:

```yaml
name: QA Tests with Variables

on:
  push:
    branches: [main]

jobs:
  qa-tests:
    runs-on: ubuntu-latest
    
    steps:
      - name: Run Tests with Custom Variables
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars.TEST_SUITE_ID }} \
            --base-url ${{ vars.STAGING_BASE_URL }} \
            --var username=testuser \
            --var environment=staging \
            --var api_key=${{ secrets.TEST_API_KEY }} \
            --verbose
```

### Example 4: Scheduled Testing

Run tests on a schedule (e.g., nightly):

```yaml
name: Nightly QA Tests

on:
  schedule:
    # Run at 2 AM UTC every day
    - cron: '0 2 * * *'
  workflow_dispatch:  # Allow manual triggering

jobs:
  nightly-tests:
    runs-on: ubuntu-latest
    
    steps:
      - name: Run Nightly Tests
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars.TEST_SUITE_ID }} \
            --base-url ${{ vars.PRODUCTION_BASE_URL }} \
            --timeout 7200 \
            --verbose
      
      - name: Notify on failure
        if: failure()
        run: |
          echo "Nightly tests failed!"
          # Add notification logic here (Slack, email, etc.)
```

### Example 5: Multiple Environments

Test against multiple environments in parallel:

```yaml
name: Multi-Environment QA Tests

on:
  push:
    branches: [main]

jobs:
  test-staging:
    runs-on: ubuntu-latest
    
    steps:
      - name: Test Staging Environment
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars.TEST_SUITE_ID }} \
            --base-url ${{ vars.STAGING_BASE_URL }} \
            --var environment=staging \
            --verbose
  
  test-production:
    runs-on: ubuntu-latest
    needs: test-staging  # Run only if staging tests pass
    
    steps:
      - name: Test Production Environment
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars.TEST_SUITE_ID }} \
            --base-url ${{ vars.PRODUCTION_BASE_URL }} \
            --var environment=production \
            --verbose
```

### Example 6: Matrix Testing

Test multiple configurations using matrix strategy:

```yaml
name: Matrix QA Tests

on:
  push:
    branches: [main]

jobs:
  qa-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        environment: [staging, production]
        region: [us-east-1, us-west-2, eu-west-1]
    
    steps:
      - name: Run Tests - ${{ matrix.environment }} (${{ matrix.region }})
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars.TEST_SUITE_ID }} \
            --base-url https://${{ matrix.environment }}.example.com \
            --region ${{ matrix.region }} \
            --var environment=${{ matrix.environment }} \
            --verbose
```

### Example 7: Conditional Execution

Run different test suites based on changed files:

```yaml
name: Conditional QA Tests

on:
  pull_request:
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      frontend: ${{ steps.filter.outputs.frontend }}
      backend: ${{ steps.filter.outputs.backend }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v2
        id: filter
        with:
          filters: |
            frontend:
              - 'frontend/**'
            backend:
              - 'backend/**'
  
  test-frontend:
    needs: detect-changes
    if: needs.detect-changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    
    steps:
      - name: Run Frontend Tests
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars.FRONTEND_SUITE_ID }} \
            --verbose
  
  test-backend:
    needs: detect-changes
    if: needs.detect-changes.outputs.backend == 'true'
    runs-on: ubuntu-latest
    
    steps:
      - name: Run Backend Tests
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars.BACKEND_SUITE_ID }} \
            --verbose
```

### Example 8: Extended Timeout for Large Suites

Increase timeout for long-running test suites:

```yaml
name: Extended QA Tests

on:
  push:
    branches: [main]

jobs:
  extended-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 180  # GitHub Actions job timeout (3 hours)
    
    steps:
      - name: Run Extended Test Suite
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars.EXTENDED_SUITE_ID }} \
            --timeout 10800 \
            --verbose
```

## Workflow Triggers

GitHub Actions supports various trigger types:

### Push Events

Trigger on pushes to specific branches:

```yaml
on:
  push:
    branches:
      - main
      - develop
      - 'release/**'
```

### Pull Request Events

Trigger on pull request activity:

```yaml
on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened]
```

### Schedule (Cron)

Run tests on a schedule:

```yaml
on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
    - cron: '0 */6 * * *'  # Every 6 hours
    - cron: '0 0 * * 0'  # Weekly on Sunday at midnight
```

**Cron Syntax**:
```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6) (Sunday to Saturday)
│ │ │ │ │
* * * * *
```

### Manual Trigger

Allow manual workflow execution:

```yaml
on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Environment to test'
        required: true
        default: 'staging'
        type: choice
        options:
          - staging
          - production
      suite_id:
        description: 'Test suite ID'
        required: false
        type: string

jobs:
  manual-tests:
    runs-on: ubuntu-latest
    steps:
      - name: Run Manual Tests
        run: |
          SUITE_ID="${{ inputs.suite_id || vars.TEST_SUITE_ID }}"
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id "$SUITE_ID" \
            --var environment=${{ inputs.environment }} \
            --verbose
```

### Combined Triggers

Combine multiple trigger types:

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:
```

## Exit Codes and Workflow Control

The runner uses exit codes to indicate test results:

| Exit Code | Meaning | Workflow Behavior |
|-----------|---------|-------------------|
| `0` | All tests passed | Workflow succeeds, continues to next steps |
| `1` | One or more tests failed | Workflow fails, subsequent steps skipped |
| `2` | Runner error (auth, config, API) | Workflow fails, subsequent steps skipped |

### Fail Build on Test Failure

Default behavior - workflow fails if tests fail:

```yaml
steps:
  - name: Run QA Tests
    run: |
      docker run --rm \
        -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
        -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
        -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
        -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
        nova-act-cicd-runner:latest \
        --suite-id ${{ vars.TEST_SUITE_ID }}
```

### Continue on Test Failure

Continue workflow even if tests fail:

```yaml
steps:
  - name: Run QA Tests
    continue-on-error: true
    run: |
      docker run --rm \
        -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
        -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
        -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
        -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
        nova-act-cicd-runner:latest \
        --suite-id ${{ vars.TEST_SUITE_ID }}
  
  - name: This step runs even if tests fail
    run: echo "Continuing despite test failure"
```

### Custom Handling Based on Exit Code

Handle different exit codes differently:

```yaml
steps:
  - name: Run QA Tests
    id: qa-tests
    continue-on-error: true
    run: |
      docker run --rm \
        -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
        -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
        -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
        -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
        nova-act-cicd-runner:latest \
        --suite-id ${{ vars.TEST_SUITE_ID }}
  
  - name: Handle test failure
    if: steps.qa-tests.outcome == 'failure'
    run: |
      echo "Tests failed - creating issue"
      # Add logic to create GitHub issue, send notification, etc.
  
  - name: Handle success
    if: steps.qa-tests.outcome == 'success'
    run: echo "All tests passed!"
```

## Best Practices

### Security

1. **Use Repository Secrets**: Store OAuth credentials in GitHub Secrets, never in code
2. **Separate OAuth Clients**: Use different OAuth clients for different repositories/environments
3. **Minimal Scopes**: Grant only required scopes to OAuth clients
4. **Rotate Credentials**: Rotate OAuth client secrets regularly (every 90 days)
5. **Protected Branches**: Require passing tests before merging to protected branches

### Performance

1. **Parallel Execution**: Use matrix strategy to test multiple configurations in parallel
2. **Conditional Execution**: Use path filters to run only relevant tests
3. **Caching**: Cache Docker images to speed up workflow execution
4. **Timeout Configuration**: Set appropriate timeouts for large test suites

### Reliability

1. **Retry Logic**: Add retry logic for flaky tests or network issues
2. **Verbose Logging**: Use `--verbose` flag for troubleshooting
3. **Notifications**: Set up notifications for test failures (Slack, email, etc.)
4. **Manual Triggers**: Enable `workflow_dispatch` for manual test execution

### Organization

1. **Descriptive Names**: Use clear workflow and job names
2. **Comments**: Add comments to explain complex workflow logic
3. **Reusable Workflows**: Create reusable workflows for common patterns
4. **Environment Variables**: Use GitHub Variables for non-sensitive configuration

## Troubleshooting

### Workflow Not Triggering

**Problem**: Workflow doesn't run on push or pull request

**Solutions**:
1. Verify workflow file is in `.github/workflows/` directory
2. Check YAML syntax is valid (use YAML validator)
3. Ensure branch names match trigger configuration
4. Check repository settings allow Actions to run

### Authentication Failures

**Problem**: `OAuth authentication failed: 401`

**Solutions**:
1. Verify secrets are set correctly in repository settings
2. Check OAuth client exists and is active in platform
3. Ensure OAuth client has required scopes
4. Verify token endpoint URL is correct

### Docker Pull Failures

**Problem**: `Unable to find image 'nova-act-cicd-runner:latest'`

**Solutions**:
1. Ensure Docker image is available in registry
2. Add authentication if using private registry
3. Specify full image path including registry URL

### Test Timeouts

**Problem**: Tests timeout before completion

**Solutions**:
1. Increase runner timeout: `--timeout 7200`
2. Increase GitHub Actions job timeout: `timeout-minutes: 180`
3. Split large test suites into smaller suites
4. Run tests in parallel using matrix strategy

### Secrets Not Available

**Problem**: Secrets are empty or undefined in workflow

**Solutions**:
1. Verify secrets are set at repository level (not organization level)
2. Check secret names match exactly (case-sensitive)
3. Ensure workflow has permission to access secrets
4. For pull requests from forks, secrets are not available (security feature)

## Advanced Patterns

### Reusable Workflow

Create a reusable workflow for common test patterns:

**.github/workflows/reusable-qa-tests.yml**:
```yaml
name: Reusable QA Tests

on:
  workflow_call:
    inputs:
      suite_id:
        required: true
        type: string
      base_url:
        required: false
        type: string
      environment:
        required: false
        type: string
        default: 'staging'
    secrets:
      oauth_client_id:
        required: true
      oauth_client_secret:
        required: true
      oauth_token_endpoint:
        required: true
      api_endpoint:
        required: true

jobs:
  qa-tests:
    runs-on: ubuntu-latest
    
    steps:
      - name: Run QA Tests
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.oauth_client_id }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.oauth_client_secret }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.oauth_token_endpoint }}" \
            -e API_ENDPOINT="${{ secrets.api_endpoint }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ inputs.suite_id }} \
            ${{ inputs.base_url && format('--base-url {0}', inputs.base_url) || '' }} \
            --var environment=${{ inputs.environment }} \
            --verbose
```

**Use the reusable workflow**:
```yaml
name: Staging Tests

on:
  push:
    branches: [develop]

jobs:
  test-staging:
    uses: ./.github/workflows/reusable-qa-tests.yml
    with:
      suite_id: ${{ vars.TEST_SUITE_ID }}
      base_url: ${{ vars.STAGING_BASE_URL }}
      environment: staging
    secrets:
      oauth_client_id: ${{ secrets.OAUTH_CLIENT_ID }}
      oauth_client_secret: ${{ secrets.OAUTH_CLIENT_SECRET }}
      oauth_token_endpoint: ${{ secrets.OAUTH_TOKEN_ENDPOINT }}
      api_endpoint: ${{ secrets.API_ENDPOINT }}
```

### Composite Action

Create a composite action for the runner:

**.github/actions/run-qa-tests/action.yml**:
```yaml
name: 'Run QA Tests'
description: 'Execute Nova Act QA Studio test suite'
inputs:
  suite-id:
    description: 'Test suite ID'
    required: true
  base-url:
    description: 'Base URL override'
    required: false
  oauth-client-id:
    description: 'OAuth client ID'
    required: true
  oauth-client-secret:
    description: 'OAuth client secret'
    required: true
  oauth-token-endpoint:
    description: 'OAuth token endpoint'
    required: true
  api-endpoint:
    description: 'API endpoint'
    required: true

runs:
  using: 'composite'
  steps:
    - name: Run QA Tests
      shell: bash
      run: |
        docker run --rm \
          -e OAUTH_CLIENT_ID="${{ inputs.oauth-client-id }}" \
          -e OAUTH_CLIENT_SECRET="${{ inputs.oauth-client-secret }}" \
          -e OAUTH_TOKEN_ENDPOINT="${{ inputs.oauth-token-endpoint }}" \
          -e API_ENDPOINT="${{ inputs.api-endpoint }}" \
          nova-act-cicd-runner:latest \
          --suite-id ${{ inputs.suite-id }} \
          ${{ inputs.base-url && format('--base-url {0}', inputs.base-url) || '' }} \
          --verbose
```

**Use the composite action**:
```yaml
name: QA Tests

on:
  push:
    branches: [main]

jobs:
  qa-tests:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Run Tests
        uses: ./.github/actions/run-qa-tests
        with:
          suite-id: ${{ vars.TEST_SUITE_ID }}
          base-url: ${{ vars.STAGING_BASE_URL }}
          oauth-client-id: ${{ secrets.OAUTH_CLIENT_ID }}
          oauth-client-secret: ${{ secrets.OAUTH_CLIENT_SECRET }}
          oauth-token-endpoint: ${{ secrets.OAUTH_TOKEN_ENDPOINT }}
          api-endpoint: ${{ secrets.API_ENDPOINT }}
```

## Related Documentation

- [Configuration Reference](../configuration.md) - Environment variables and CLI arguments
- [CLI Reference](../cli-reference.md) - Detailed CLI usage
- [Troubleshooting Guide](../troubleshooting.md) - Common errors and solutions
- [Best Practices](../best-practices.md) - Security and optimization guidance
- [API Reference](../api-reference.md) - API documentation for advanced integration

## Support

For GitHub Actions integration assistance:

1. Check the [GitHub Actions documentation](https://docs.github.com/en/actions)
2. Review [Troubleshooting Guide](../troubleshooting.md)
3. Enable verbose logging (`--verbose`) for detailed diagnostics
4. Check [GitHub Issues](https://github.com/aws-samples/sample-nova-act-qa-studio/issues)
5. Contact your platform administrator
