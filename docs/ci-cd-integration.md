# CI/CD Integration Guide

This guide shows how to integrate QA Studio into your CI/CD pipelines using the `qa-studio` CLI tool.

## Overview

QA Studio can be integrated into any CI/CD platform that supports:
- Python 3.11+
- Command-line execution
- Environment variables or secret management

The `qa-studio run` command executes tests locally in your CI/CD environment, providing fast feedback without requiring cloud infrastructure.

---

## Quick Start

### Prerequisites

1. **Python 3.11+** installed in CI environment
2. **QA Studio CLI** installed: `pip install -e ./qa-studio-cli[runner]`
3. **Authentication** configured (see Authentication section below)
4. **AWS credentials** for Bedrock access (Nova Act)

### Basic Example

```bash
# Install CLI with runner dependencies
pip install -e "./qa-studio-cli[runner]"

# Configure (one-time setup)
qa-studio configure

# Authenticate
qa-studio login

# Run a test
qa-studio run --usecase-id test-123

# Run a test suite
qa-studio run --suite-id suite-456
```

---

## Authentication

The CLI supports multiple authentication methods. The token resolver tries them in this priority order:

1. Token file (`--token-file` flag)
2. Environment variables (`OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` / `OAUTH_TOKEN_ENDPOINT`)
3. Config file M2M credentials (`~/.qa-studio/config.json`)
4. Stored user token from `qa-studio login` (with auto-refresh)

Higher-priority sources override lower ones. For example, environment variables override config file values.

### Option 1: OAuth Client Credentials via Environment Variables (Recommended for CI/CD)

The recommended approach for CI/CD pipelines. No browser login required.

First, create an OAuth client in the QA Studio web UI:

1. Navigate to OAuth Clients (admin only)
2. Click "Create OAuth Client"
3. Name it (e.g., "CI/CD Pipeline")
4. Grant required scopes:
   - `api/suite.read`, `api/suite.write`
   - `api/usecases.read`, `api/usecases.execute`
   - `api/executions.read`, `api/executions.write`
5. Save the client ID and secret (secret is only shown once)

Then set these environment variables in your pipeline:

```bash
export OAUTH_CLIENT_ID="your-m2m-client-id"
export OAUTH_CLIENT_SECRET="your-m2m-client-secret"
export OAUTH_TOKEN_ENDPOINT="https://your-cognito-domain.auth.region.amazoncognito.com/oauth2/token"

# No login needed — just run
qa-studio run --suite-id suite-456
```

The CLI automatically requests a token using the OAuth client credentials grant, caches it in memory, and refreshes it when it expires (with a 5-minute buffer).

Granted scopes for M2M tokens: `api/suite.read`, `api/suite.write`, `api/usecases.read`, `api/usecases.execute`, `api/executions.read`, `api/executions.write`.

### Option 2: OAuth Client Credentials via Config File

Same as Option 1, but credentials are stored in `~/.qa-studio/config.json` instead of environment variables. Useful for dedicated CI/CD runners or local headless setups.

```json
{
  "api_url": "https://your-api-url",
  "cognito_domain": "https://your-cognito-domain.auth.region.amazoncognito.com",
  "client_id": "your-public-client-id",
  "oauth_client_id": "your-m2m-client-id",
  "oauth_client_secret": "your-m2m-client-secret",
  "oauth_token_endpoint": "https://your-cognito-domain.auth.region.amazoncognito.com/oauth2/token"
}
```

**Security Note**: The config file is created with `chmod 600` (owner-only read/write). Never commit this file to version control.

### Option 3: Token File

For pipelines where you pre-generate a token or receive one from a secrets manager:

```bash
qa-studio run --token-file /path/to/token.json --usecase-id test-123
```

Token file format:
```json
{
  "access_token": "eyJraWQiOiI...",
  "refresh_token": "eyJjdHkiOiJ...",
  "expires_at": 1234567890,
  "token_type": "Bearer"
}
```

**Security Note**: Store token files as secrets in your CI/CD platform. Access tokens expire after 1 hour; refresh tokens are valid for 30 days.

### Option 4: User Authentication (Development)

For local development and interactive use:

```bash
# Interactive browser-based login (opens Cognito hosted UI)
qa-studio login

# Tokens stored in ~/.qa-studio/token.json
# Automatically refreshed when expired
```

---

## CLI Command Reference

### `qa-studio run`

Execute tests locally with Nova Act.

**Usage**:
```bash
qa-studio run [OPTIONS]
```

**Options**:

| Option | Type | Required | Description | Default |
|--------|------|----------|-------------|---------|
| `--suite-id` | TEXT | No* | Test suite ID to execute | - |
| `--usecase-id` | TEXT | No* | Single use case ID to execute | - |
| `--local-only` | FLAG | No | Local-only execution (no remote records) | False |
| `--token-file` | TEXT | No | Path to JSON token file | ~/.qa-studio/tokens.json |
| `--base-url` | TEXT | No | Override base URL for all use cases | - |
| `--var` | TEXT | No | Override variable (key=value, repeatable) | - |
| `--region` | TEXT | No | Override AWS region for browser | - |
| `--model-id` | TEXT | No | Override Nova Act model ID | - |
| `--verbose` | FLAG | No | Enable verbose logging | False |
| `--timeout` | INTEGER | No | Global timeout in seconds | 3600 |
| `--keep-artifacts` | FLAG | No | Keep local artifact files after upload | False |
| `--format` | CHOICE | No | Output format (json or human) | json |

\* Either `--suite-id` or `--usecase-id` is required

**Examples**:

```bash
# Run single test
qa-studio run --usecase-id test-123

# Run test suite
qa-studio run --suite-id suite-456

# Run with environment override
qa-studio run --usecase-id test-123 --base-url https://staging.example.com

# Run with variable overrides
qa-studio run --usecase-id test-123 --var username=testuser --var password=testpass

# Run locally without creating remote execution records
qa-studio run --usecase-id test-123 --local-only

# Run with custom region and model
qa-studio run --usecase-id test-123 \
  --region us-west-2 \
  --model-id anthropic.claude-3-5-sonnet-20240620-v1:0

# Run with verbose logging
qa-studio run --usecase-id test-123 --verbose

# Run with custom timeout (2 hours)
qa-studio run --suite-id suite-456 --timeout 7200
```

**Exit Codes**:

| Code | Meaning | Description |
|------|---------|-------------|
| 0 | Success | All tests passed |
| 1 | Failure | One or more tests failed |
| 2 | Error | CLI error (authentication, configuration, API error) |

---

## CI/CD Platform Examples

### GitHub Actions

**.github/workflows/qa-tests.yml**:

```yaml
name: QA Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM

jobs:
  smoke-tests:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install QA Studio CLI
        run: |
          pip install -e "./qa-studio-cli[runner]"
      
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      
      - name: Run Smoke Tests
        env:
          OAUTH_CLIENT_ID: ${{ secrets.OAUTH_CLIENT_ID }}
          OAUTH_CLIENT_SECRET: ${{ secrets.OAUTH_CLIENT_SECRET }}
          OAUTH_TOKEN_ENDPOINT: ${{ secrets.OAUTH_TOKEN_ENDPOINT }}
          QA_STUDIO_API_URL: ${{ secrets.QA_STUDIO_API_URL }}
        run: |
          qa-studio run \
            --suite-id ${{ vars.SMOKE_TEST_SUITE_ID }} \
            --base-url https://staging.example.com \
            --format human
      
      - name: Upload Artifacts
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: test-artifacts
          path: ~/.qa-studio/artifacts/
```

**Secrets to Configure**:
- `OAUTH_CLIENT_ID`: OAuth M2M client ID
- `OAUTH_CLIENT_SECRET`: OAuth M2M client secret
- `OAUTH_TOKEN_ENDPOINT`: Cognito token endpoint URL
- `QA_STUDIO_API_URL`: QA Studio API base URL
- `AWS_ACCESS_KEY_ID`: AWS access key for Bedrock
- `AWS_SECRET_ACCESS_KEY`: AWS secret key

**Variables to Configure**:
- `SMOKE_TEST_SUITE_ID`: Test suite ID

### GitLab CI

**.gitlab-ci.yml**:

```yaml
stages:
  - test

variables:
  PYTHON_VERSION: "3.11"

smoke-tests:
  stage: test
  image: python:${PYTHON_VERSION}
  
  before_script:
    - pip install -e "./qa-studio-cli[runner]"
    - export OAUTH_CLIENT_ID=$OAUTH_CLIENT_ID
    - export OAUTH_CLIENT_SECRET=$OAUTH_CLIENT_SECRET
    - export OAUTH_TOKEN_ENDPOINT=$OAUTH_TOKEN_ENDPOINT
    - export QA_STUDIO_API_URL=$QA_STUDIO_API_URL
    - export AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID
    - export AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY
    - export AWS_DEFAULT_REGION=us-east-1
  
  script:
    - |
      qa-studio run \
        --suite-id $SMOKE_TEST_SUITE_ID \
        --base-url https://staging.example.com \
        --format human
  
  artifacts:
    when: always
    paths:
      - ~/.qa-studio/artifacts/
    expire_in: 7 days
  
  only:
    - main
    - develop
    - merge_requests

regression-tests:
  stage: test
  image: python:${PYTHON_VERSION}
  
  before_script:
    - pip install -e "./qa-studio-cli[runner]"
    - export OAUTH_CLIENT_ID=$OAUTH_CLIENT_ID
    - export OAUTH_CLIENT_SECRET=$OAUTH_CLIENT_SECRET
    - export OAUTH_TOKEN_ENDPOINT=$OAUTH_TOKEN_ENDPOINT
    - export QA_STUDIO_API_URL=$QA_STUDIO_API_URL
    - export AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID
    - export AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY
    - export AWS_DEFAULT_REGION=us-east-1
  
  script:
    - |
      qa-studio run \
        --suite-id $REGRESSION_TEST_SUITE_ID \
        --base-url https://staging.example.com \
        --timeout 7200 \
        --format human
  
  artifacts:
    when: always
    paths:
      - ~/.qa-studio/artifacts/
    expire_in: 7 days
  
  only:
    - schedules
```

**CI/CD Variables to Configure**:
- `OAUTH_CLIENT_ID`: OAuth M2M client ID - Protected, Masked
- `OAUTH_CLIENT_SECRET`: OAuth M2M client secret - Protected, Masked
- `OAUTH_TOKEN_ENDPOINT`: Cognito token endpoint URL - Protected
- `QA_STUDIO_API_URL`: QA Studio API base URL - Protected
- `AWS_ACCESS_KEY_ID`: AWS access key - Protected, Masked
- `AWS_SECRET_ACCESS_KEY`: AWS secret key - Protected, Masked
- `SMOKE_TEST_SUITE_ID`: Test suite ID
- `REGRESSION_TEST_SUITE_ID`: Test suite ID

### Jenkins

**Jenkinsfile**:

```groovy
pipeline {
    agent any
    
    environment {
        PYTHON_VERSION = '3.11'
        AWS_DEFAULT_REGION = 'us-east-1'
    }
    
    stages {
        stage('Setup') {
            steps {
                sh '''
                    python${PYTHON_VERSION} -m venv venv
                    . venv/bin/activate
                    pip install -e "./qa-studio-cli[runner]"
                '''
            }
        }
        
        stage('Configure') {
            steps {
                withCredentials([
                    string(credentialsId: 'oauth-client-id', variable: 'OAUTH_CLIENT_ID'),
                    string(credentialsId: 'oauth-client-secret', variable: 'OAUTH_CLIENT_SECRET'),
                    string(credentialsId: 'oauth-token-endpoint', variable: 'OAUTH_TOKEN_ENDPOINT'),
                    string(credentialsId: 'qa-studio-api-url', variable: 'QA_STUDIO_API_URL'),
                    string(credentialsId: 'aws-access-key-id', variable: 'AWS_ACCESS_KEY_ID'),
                    string(credentialsId: 'aws-secret-access-key', variable: 'AWS_SECRET_ACCESS_KEY')
                ]) {
                    sh '''
                        export OAUTH_CLIENT_ID=$OAUTH_CLIENT_ID
                        export OAUTH_CLIENT_SECRET=$OAUTH_CLIENT_SECRET
                        export OAUTH_TOKEN_ENDPOINT=$OAUTH_TOKEN_ENDPOINT
                        export QA_STUDIO_API_URL=$QA_STUDIO_API_URL
                        export AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID
                        export AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY
                    '''
                }
            }
        }
        
        stage('Smoke Tests') {
            steps {
                sh '''
                    . venv/bin/activate
                    qa-studio run \
                        --suite-id ${SMOKE_TEST_SUITE_ID} \
                        --base-url https://staging.example.com \
                        --format human
                '''
            }
        }
    }
    
    post {
        always {
            archiveArtifacts artifacts: '~/.qa-studio/artifacts/**/*', allowEmptyArchive: true
        }
    }
}
```

**Credentials to Configure**:
- `oauth-client-id`: Secret text (OAuth M2M client ID)
- `oauth-client-secret`: Secret text (OAuth M2M client secret)
- `oauth-token-endpoint`: Secret text (Cognito token endpoint URL)
- `qa-studio-api-url`: Secret text (QA Studio API base URL)
- `aws-access-key-id`: Secret text
- `aws-secret-access-key`: Secret text

**Environment Variables**:
- `SMOKE_TEST_SUITE_ID`: Test suite ID

### CircleCI

**.circleci/config.yml**:

```yaml
version: 2.1

executors:
  python-executor:
    docker:
      - image: cimg/python:3.11
    working_directory: ~/project

jobs:
  smoke-tests:
    executor: python-executor
    steps:
      - checkout
      
      - run:
          name: Install QA Studio CLI
          command: |
            pip install -e "./qa-studio-cli[runner]"
      
      - run:
          name: Configure Authentication
          command: |
            echo "Using OAuth client credentials from environment"
      
      - run:
          name: Run Smoke Tests
          command: |
            qa-studio run \
              --suite-id $SMOKE_TEST_SUITE_ID \
              --base-url https://staging.example.com \
              --format human
          environment:
            OAUTH_CLIENT_ID: $OAUTH_CLIENT_ID
            OAUTH_CLIENT_SECRET: $OAUTH_CLIENT_SECRET
            OAUTH_TOKEN_ENDPOINT: $OAUTH_TOKEN_ENDPOINT
            QA_STUDIO_API_URL: $QA_STUDIO_API_URL
            AWS_ACCESS_KEY_ID: $AWS_ACCESS_KEY_ID
            AWS_SECRET_ACCESS_KEY: $AWS_SECRET_ACCESS_KEY
            AWS_DEFAULT_REGION: us-east-1
      
      - store_artifacts:
          path: ~/.qa-studio/artifacts
          destination: test-artifacts

workflows:
  version: 2
  test:
    jobs:
      - smoke-tests:
          context: qa-studio
          filters:
            branches:
              only:
                - main
                - develop
  
  nightly:
    triggers:
      - schedule:
          cron: "0 2 * * *"
          filters:
            branches:
              only: main
    jobs:
      - smoke-tests:
          context: qa-studio
```

**Context Variables** (qa-studio):
- `OAUTH_CLIENT_ID`: OAuth M2M client ID
- `OAUTH_CLIENT_SECRET`: OAuth M2M client secret
- `OAUTH_TOKEN_ENDPOINT`: Cognito token endpoint URL
- `QA_STUDIO_API_URL`: QA Studio API base URL
- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key
- `SMOKE_TEST_SUITE_ID`: Test suite ID

---

## Environment-Specific Testing

### Using Base URL Override

Test against different environments without modifying tests:

```bash
# Development
qa-studio run --suite-id suite-123 --base-url https://dev.example.com

# Staging
qa-studio run --suite-id suite-123 --base-url https://staging.example.com

# Production
qa-studio run --suite-id suite-123 --base-url https://example.com
```

### Using Variable Overrides

Override test variables for different scenarios:

```bash
# Test with different user
qa-studio run --usecase-id test-123 \
  --var username=testuser1 \
  --var password=testpass1

# Test with different API key
qa-studio run --usecase-id test-123 \
  --var api_key=staging_key_123

# Multiple variables
qa-studio run --usecase-id test-123 \
  --var environment=staging \
  --var username=testuser \
  --var password=testpass \
  --var api_key=staging_key
```

---

## Best Practices

### Test Organization

**Separate Suites by Purpose**:
- Smoke tests: Critical paths, run on every commit
- Regression tests: Comprehensive coverage, run nightly
- Integration tests: Cross-feature workflows, run on PR

**Example**:
```yaml
# GitHub Actions
jobs:
  smoke:
    # Run on every push
    if: github.event_name == 'push'
    steps:
      - run: qa-studio run --suite-id $SMOKE_SUITE_ID
  
  regression:
    # Run nightly
    if: github.event_name == 'schedule'
    steps:
      - run: qa-studio run --suite-id $REGRESSION_SUITE_ID
```

### Parallel Execution

Run multiple suites in parallel for faster feedback:

```yaml
# GitHub Actions
jobs:
  smoke-tests:
    steps:
      - run: qa-studio run --suite-id $SMOKE_SUITE_ID
  
  api-tests:
    steps:
      - run: qa-studio run --suite-id $API_SUITE_ID
  
  ui-tests:
    steps:
      - run: qa-studio run --suite-id $UI_SUITE_ID
```

### Artifact Management

**Keep Artifacts for Failed Tests**:
```yaml
# GitHub Actions
- name: Upload Artifacts
  if: failure()  # Only upload on failure
  uses: actions/upload-artifact@v3
  with:
    name: test-artifacts
    path: ~/.qa-studio/artifacts/
```

**Set Retention Period**:
```yaml
# GitHub Actions
- uses: actions/upload-artifact@v3
  with:
    name: test-artifacts
    path: ~/.qa-studio/artifacts/
    retention-days: 7  # Keep for 7 days
```

### Error Handling

**Fail Pipeline on Test Failures**:
```bash
# Exit code 0 = success, 1 = test failures, 2 = error
qa-studio run --suite-id suite-123
EXIT_CODE=$?

if [ $EXIT_CODE -eq 1 ]; then
  echo "Tests failed"
  exit 1
elif [ $EXIT_CODE -eq 2 ]; then
  echo "CLI error occurred"
  exit 2
fi
```

**Continue on Failure** (for reporting):
```yaml
# GitHub Actions
- name: Run Tests
  continue-on-error: true
  run: qa-studio run --suite-id suite-123

- name: Generate Report
  if: always()
  run: ./generate-report.sh
```

### Security

**Store Secrets Securely**:
- Use CI/CD platform's secret management
- Never commit tokens or credentials
- Rotate tokens regularly
- Use least-privilege AWS credentials

**Mask Sensitive Output**:
```yaml
# GitHub Actions
- name: Run Tests
  env:
    QA_STUDIO_TOKEN: ${{ secrets.QA_STUDIO_TOKEN }}
  run: |
    # Token is automatically masked in logs
    qa-studio run --suite-id suite-123
```

---

## Troubleshooting

### Authentication Fails

**Error**: "Authentication failed: Invalid token"

**Solutions**:
1. Regenerate token file:
   ```bash
   qa-studio login
   # Copy new tokens.json to CI/CD secrets
   ```

2. Check token file format:
   ```json
   {
     "access_token": "...",
     "refresh_token": "...",
     "expires_at": 1234567890
   }
   ```

3. Verify token file is readable:
   ```bash
   cat ~/.qa-studio/tokens.json
   ```

### AWS Credentials Not Found

**Error**: "Unable to locate credentials"

**Solutions**:
1. Set AWS environment variables:
   ```bash
   export AWS_ACCESS_KEY_ID=your-key
   export AWS_SECRET_ACCESS_KEY=your-secret
   export AWS_DEFAULT_REGION=us-east-1
   ```

2. Or use AWS credentials file:
   ```bash
   mkdir -p ~/.aws
   cat > ~/.aws/credentials << EOF
   [default]
   aws_access_key_id = your-key
   aws_secret_access_key = your-secret
   EOF
   ```

### Tests Timeout

**Error**: "Execution timed out after 3600 seconds"

**Solutions**:
1. Increase timeout:
   ```bash
   qa-studio run --suite-id suite-123 --timeout 7200
   ```

2. Split large suites into smaller ones

3. Optimize test steps

### Module Not Found

**Error**: "ModuleNotFoundError: No module named 'nova_act'"

**Solutions**:
1. Install with runner dependencies:
   ```bash
   pip install -e "./qa-studio-cli[runner]"
   ```

2. Verify installation:
   ```bash
   pip show qa-studio-cli
   python -c "import nova_act; print(nova_act.__version__)"
   ```

---

## Configuration Reference

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `QA_STUDIO_API_URL` | API base URL | From config | No |
| `QA_STUDIO_COGNITO_DOMAIN` | Cognito domain | From config | No |
| `QA_STUDIO_CLIENT_ID` | Cognito client ID | From config | No |
| `OAUTH_CLIENT_ID` | OAuth M2M client ID (for client credentials flow) | From config | No* |
| `OAUTH_CLIENT_SECRET` | OAuth M2M client secret | From config | No* |
| `OAUTH_TOKEN_ENDPOINT` | Cognito token endpoint URL | From config | No* |
| `AWS_ACCESS_KEY_ID` | AWS access key for Bedrock | - | Yes |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key for Bedrock | - | Yes |
| `AWS_DEFAULT_REGION` | AWS region | us-east-1 | No |

\* All three `OAUTH_*` variables must be set together for client credentials auth. If any is missing, the CLI falls back to the next auth source.

### Configuration File

Location: `~/.qa-studio/config.json`

```json
{
  "api_url": "https://api.example.com",
  "cognito_domain": "https://myapp.auth.us-east-1.amazoncognito.com",
  "client_id": "7abc123def456",
  "oauth_client_id": "your-m2m-client-id",
  "oauth_client_secret": "your-m2m-client-secret",
  "oauth_token_endpoint": "https://myapp.auth.us-east-1.amazoncognito.com/oauth2/token"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `api_url` | string | Yes | QA Studio API base URL (must start with `https://`) |
| `cognito_domain` | string | Yes | Cognito hosted UI domain (must start with `https://`) |
| `client_id` | string | Yes | Cognito app client ID (public, for browser-based login) |
| `oauth_client_id` | string | No | OAuth M2M client ID (for client credentials flow) |
| `oauth_client_secret` | string | No | OAuth M2M client secret |
| `oauth_token_endpoint` | string | No | Cognito token endpoint URL (must start with `https://`) |

The M2M fields (`oauth_client_id`, `oauth_client_secret`, `oauth_token_endpoint`) are optional and only needed for headless/CI authentication. They are excluded from the JSON file when not set.

### Token File

Location: `~/.qa-studio/tokens.json`

```json
{
  "access_token": "eyJraWQiOiI...",
  "refresh_token": "eyJjdHkiOiJ...",
  "expires_at": 1234567890,
  "token_type": "Bearer"
}
```

---

## Additional Resources

- [CLI README](../qa-studio-cli/README.md) - Complete CLI documentation
- [User Guide](user-guide.md) - Web interface walkthrough
- [API Reference](api-reference.md) - Complete API documentation
- [Best Practices](best-practices.md) - Testing best practices
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
