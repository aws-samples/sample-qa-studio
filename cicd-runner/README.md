# QA Studio - CI/CD Runner

Python CLI application for executing Nova Act QA Studio test suites and individual use cases in CI/CD pipelines or locally. The runner authenticates with OAuth client credentials, fetches test suite or use case definitions, creates execution records, and runs automated browser-based tests using Nova Act. It supports full suite execution, single use case execution, and a local-only mode for quick iteration without creating execution records or uploading artifacts.

## Features

- OAuth 2.0 client credentials authentication with in-memory token caching
- Automatic token refresh on expiration
- Test suite execution via Platform API with parallel use case execution
- Single use case execution with execution records and artifact upload
- Local-only execution mode — no execution records, no S3 uploads, artifacts stored locally
- JSON and human-readable summary output formats for local execution
- Nova Act browser automation with headless Chromium
- Configurable AWS region for Nova Act browser execution
- Artifact collection and upload (screenshots, logs)
- Suite-level log capture
- Execution summary table output
- CLI argument parsing with variable overrides
- Comprehensive error handling and logging
- Secure credential management via environment variables

## Installation

### Prerequisites

- Python 3.9 to 3.12 (Python 3.13+ is not yet supported due to dependency compatibility)
- pip

### Setting Up a Virtual Environment

If you have multiple Python versions installed (e.g. via pyenv), make sure the venv is created with a compatible version:

```bash
cd cicd-runner

# Option A: If pyenv is configured and 3.12 is your local version
pyenv local 3.12.0
python -m venv venv

# Option B: Use the explicit pyenv path (avoids shell shim issues)
~/.pyenv/versions/3.12.0/bin/python -m venv venv

# Activate
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Verify
python --version  # Should show 3.12.x

# Install dependencies
pip install -r requirements.txt
```

### From Source (editable install)

```bash
cd cicd-runner
pip install -e .
```

### From Package

```bash
pip install cicd-runner
```

## Configuration

### Required Environment Variables

The runner requires the following environment variables to be set:

```bash
# OAuth credentials from Cognito
export OAUTH_CLIENT_ID="your-client-id"
export OAUTH_CLIENT_SECRET="your-client-secret"

# Cognito token endpoint
export OAUTH_TOKEN_ENDPOINT="https://your-domain.auth.us-east-1.amazoncognito.com/oauth2/token"

# Platform API endpoint
export API_ENDPOINT="https://your-api-id.execute-api.us-east-1.amazonaws.com/api"
```

### Optional Environment Variables

```bash
# Logging level (default: INFO)
export LOG_LEVEL="DEBUG"
```

### Using .env File

Create a `.env` file in your working directory:

```bash
cp .env.example .env
# Edit .env with your credentials
```

The runner will automatically load environment variables from `.env` if present.

## OAuth Client Setup

Before using the runner, you need to create an OAuth client in the QA Studio platform:

1. **Login to QA Studio** web interface
2. **Navigate to Settings** → OAuth Clients
3. **Create New Client**:
   - Name: "CI/CD Runner"
   - Grant Type: Client Credentials
   - Scopes: `api/suite.read`, `api/suite.write`, `api/usecases.read`, `api/usecases.execute`, `api/executions.read`, `api/executions.write`
4. **Save credentials**:
   - Copy the Client ID
   - Copy the Client Secret (shown only once)
5. **Set environment variables** with the credentials

> **Note**: Local-only execution (`--local-only`) only requires the `api/usecases.read` scope.

## Usage

### Execution Modes

The runner supports three execution modes:

1. **Suite execution**: Executes a full test suite, creates execution records, uploads artifacts
2. **Single use case execution**: Executes a single use case, creates execution records, uploads artifacts
3. **Local-only execution**: Executes a single use case locally — no execution records, no S3 uploads, artifacts stored in `/tmp/qa-studio-artifacts/<usecase-id>/`

### Suite Execution

Execute a test suite by ID:

```bash
cicd-runner --suite-id 01234567-89ab-cdef-0123-456789abcdef
```

### Single Use Case Execution

Execute a single use case by ID (creates execution records and uploads artifacts):

```bash
cicd-runner --usecase-id 01234567-89ab-cdef-0123-456789abcdef
```

### Local-Only Execution

Execute a single use case locally without creating execution records or uploading artifacts:

```bash
cicd-runner --usecase-id 01234567-89ab-cdef-0123-456789abcdef --local-only
```

Artifacts are stored in `/tmp/qa-studio-artifacts/<usecase-id>/`.

### With Variable Overrides

Override test suite variables:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --var username=testuser \
  --var password=testpass \
  --var environment=staging
```

### With Base URL Override

Override the base URL for all use cases:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com
```

### With Model Override

Override Bedrock model:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --model-id nova-act-v1.0
```

### With Region Override

Override the AWS region for Nova Act browser execution:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --region us-east-1
```

### With Output Format (Local-Only)

Choose between JSON (default) and human-readable summary output in local-only mode:

```bash
# JSON output (default)
cicd-runner --usecase-id 01234567-89ab-cdef-0123-456789abcdef --local-only --output json

# Human-readable summary
cicd-runner --usecase-id 01234567-89ab-cdef-0123-456789abcdef --local-only --output summary
```

### With Verbose Logging

Enable detailed debug logging:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --verbose
```

### With Custom Timeout

Set global timeout in seconds (default: 3600):

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --timeout 7200
```

### Complete Example

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com \
  --var username=testuser \
  --var password=testpass \
  --model-id nova-act-v1.0 \
  --region us-east-1 \
  --timeout 7200 \
  --verbose
```

### Local-Only Complete Example

```bash
cicd-runner \
  --usecase-id 01234567-89ab-cdef-0123-456789abcdef \
  --local-only \
  --base-url https://staging.example.com \
  --var username=testuser \
  --var password=testpass \
  --region us-east-1 \
  --output summary \
  --verbose
```

## CLI Options

| Option | Required | Description | Default |
|--------|----------|-------------|---------|
| `--suite-id` | No* | Test suite UUID to execute | - |
| `--usecase-id` | No* | Single use case UUID to execute | - |
| `--local-only` | No | Local execution only, no execution records or S3 uploads (requires `--usecase-id`) | False |
| `--output` | No | Output format: `json` or `summary` (only applies to `--local-only` mode) | `json` |
| `--region` | No | Override AWS region for Nova Act browser execution | - |
| `--base-url` | No | Override base URL for all use cases | - |
| `--var` | No | Override variable (key=value, repeatable) | - |
| `--model-id` | No | Override Nova Act model ID | - |
| `--verbose` | No | Enable verbose logging (DEBUG level) | False |
| `--timeout` | No | Global timeout in seconds | 3600 |
| `--keep-artifacts` | No | Keep local artifact files after upload (for debugging) | False |
| `--help` | No | Show help message and exit | - |

\* Either `--suite-id` or `--usecase-id` is required. They are mutually exclusive.

## Local Execution Output

When using `--local-only`, the runner outputs execution results to stdout. The format is controlled by the `--output` flag.

### JSON Output (default)

Machine-readable JSON output, suitable for piping into other tools:

```json
{
  "status": "success",
  "usecaseId": "abc-123",
  "usecaseName": "Login Flow Test",
  "duration": 45.2,
  "steps": [
    {
      "stepId": "step-1",
      "instruction": "Navigate to login page",
      "status": "success",
      "duration": 2.1,
      "screenshot": "/tmp/qa-studio-artifacts/abc-123/step-1-screenshot.png"
    }
  ],
  "artifacts": {
    "video": "/tmp/qa-studio-artifacts/abc-123/recording.webm",
    "logs": "/tmp/qa-studio-artifacts/abc-123/execution.log"
  }
}
```

### Summary Output (`--output summary`)

Human-readable summary, suitable for terminal viewing:

```
QA Studio - Local Execution

Use Case: Login Flow Test
Use Case ID: abc-123
Duration: 45s
Status: ✓ PASSED

Steps:
  ✓ 1. Navigate to login page (2s)
  ✓ 2. Enter credentials (3s)
  ✓ 3. Click login button (2s)
  ✓ 4. Verify dashboard loads (5s)

Total: 4  |  Passed: 4  |  Failed: 0

Artifacts:
  Video: /tmp/qa-studio-artifacts/abc-123/recording.webm
  Logs:  /tmp/qa-studio-artifacts/abc-123/execution.log
```

## Exit Codes

- `0`: All tests passed
- `1`: One or more tests failed
- `2`: Runner error (authentication, API, or configuration failure)

## Troubleshooting

### Authentication Errors

**Error**: `AuthenticationError: OAuth authentication failed: 401`

**Solution**:
- Verify `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET` are correct
- Check that the OAuth client exists in the platform
- Ensure the client has the required scopes

### Configuration Errors

**Error**: `ConfigurationError: Missing required environment variable: OAUTH_CLIENT_ID`

**Solution**:
- Verify all required environment variables are set (`OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_TOKEN_ENDPOINT`, `API_ENDPOINT`)
- Check for typos in variable names
- Ensure `.env` file is in the current directory (if using)

### API Errors

**Error**: `APIError: API request failed: 403 - Missing required scopes`

**Solution**:
- Verify OAuth client has scopes: `api/suite.read`, `api/suite.write`, `api/usecases.read`, `api/usecases.execute`, `api/executions.read`, `api/executions.write`
- Recreate the OAuth client with correct scopes

**Error**: `APIError: API request failed: 404 - Test suite not found`

**Solution**:
- Verify the suite ID is correct
- Check that the test suite exists in the platform
- Ensure you have access to the test suite

### Network Errors

**Error**: `AuthenticationError: OAuth authentication failed: Connection timeout`

**Solution**:
- Check network connectivity
- Verify the `OAUTH_TOKEN_ENDPOINT` URL is correct
- Check firewall rules allow HTTPS connections

## Docker

The CI/CD runner is available as a Docker container that bundles all dependencies including the Nova Act SDK and headless Chromium browser.

### Building the Image

```bash
cd cicd-runner
docker build -t cicd-runner .
```

The build uses a multi-stage Dockerfile (`python:3.12-slim` base) to keep the final image lean. The builder stage compiles Python dependencies, and the runtime stage adds only Playwright Chromium and the packaged CLI.

### Running the Container

Pass required environment variables and CLI arguments directly:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="your-client-id" \
  -e OAUTH_CLIENT_SECRET="your-client-secret" \
  -e OAUTH_TOKEN_ENDPOINT="https://your-domain.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://your-api-id.execute-api.us-east-1.amazonaws.com/api" \
  cicd-runner --suite-id 01234567-89ab-cdef-0123-456789abcdef
```

With variable overrides and verbose logging:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="your-client-id" \
  -e OAUTH_CLIENT_SECRET="your-client-secret" \
  -e OAUTH_TOKEN_ENDPOINT="https://your-domain.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://your-api-id.execute-api.us-east-1.amazonaws.com/api" \
  cicd-runner \
    --suite-id 01234567-89ab-cdef-0123-456789abcdef \
    --var username=testuser \
    --var environment=staging \
    --verbose
```

### Environment Variables

#### Required

| Variable | Description |
|----------|-------------|
| `OAUTH_CLIENT_ID` | OAuth client ID from Cognito |
| `OAUTH_CLIENT_SECRET` | OAuth client secret from Cognito |
| `OAUTH_TOKEN_ENDPOINT` | Cognito token endpoint URL (must be HTTPS) |
| `API_ENDPOINT` | Platform API base URL (must be HTTPS) |

If any required variable is missing, the container exits with code 2 and logs which variable is absent.

#### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_ACCESS_KEY_ID` | AWS access key for Nova Act SDK Bedrock access | From IAM role |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key for Nova Act SDK Bedrock access | From IAM role |
| `AWS_SESSION_TOKEN` | AWS session token (for temporary credentials) | — |
| `LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

AWS credentials can be provided via environment variables or inherited from an IAM role attached to the CI/CD runner (e.g., GitHub Actions OIDC, ECS task role).

### Resource Requirements

| Resource | Recommended | Notes |
|----------|-------------|-------|
| Memory | 2 GB | Chromium headless requires ~1 GB; additional headroom for the Python runtime and test execution |
| CPU | 2 cores | Concurrent browser automation benefits from multiple cores |

The container runs as a non-root user (`runner`, uid 1000) and writes logs to `/app/logs` inside the container.

### CI/CD Integration

#### GitHub Actions

```yaml
name: Run QA Suite

on:
  workflow_dispatch:
    inputs:
      suite_id:
        description: "Test suite ID to execute"
        required: true

jobs:
  qa-run:
    runs-on: ubuntu-latest
    steps:
      - name: Run CI/CD Runner
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            -e AWS_ACCESS_KEY_ID="${{ secrets.AWS_ACCESS_KEY_ID }}" \
            -e AWS_SECRET_ACCESS_KEY="${{ secrets.AWS_SECRET_ACCESS_KEY }}" \
            -e AWS_SESSION_TOKEN="${{ secrets.AWS_SESSION_TOKEN }}" \
            your-registry/cicd-runner:latest \
              --suite-id "${{ github.event.inputs.suite_id }}"
```

#### GitLab CI

```yaml
# .gitlab-ci.yml
qa-run:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    SUITE_ID: "01234567-89ab-cdef-0123-456789abcdef"
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID"
        -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY"
        your-registry/cicd-runner:latest
          --suite-id "$SUITE_ID"
```

Store `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_TOKEN_ENDPOINT`, `API_ENDPOINT`, and AWS credentials as [CI/CD variables](https://docs.gitlab.com/ee/ci/variables/) with the **Masked** flag enabled.

#### Jenkins

```groovy
// Jenkinsfile
pipeline {
    agent any
    parameters {
        string(name: 'SUITE_ID', description: 'Test suite ID to execute')
    }
    stages {
        stage('Run QA Suite') {
            steps {
                withCredentials([
                    string(credentialsId: 'oauth-client-id',     variable: 'OAUTH_CLIENT_ID'),
                    string(credentialsId: 'oauth-client-secret', variable: 'OAUTH_CLIENT_SECRET'),
                    string(credentialsId: 'oauth-token-endpoint', variable: 'OAUTH_TOKEN_ENDPOINT'),
                    string(credentialsId: 'api-endpoint',        variable: 'API_ENDPOINT'),
                    string(credentialsId: 'aws-access-key-id',   variable: 'AWS_ACCESS_KEY_ID'),
                    string(credentialsId: 'aws-secret-access-key', variable: 'AWS_SECRET_ACCESS_KEY')
                ]) {
                    sh """
                        docker run --rm \
                          -e OAUTH_CLIENT_ID="\$OAUTH_CLIENT_ID" \
                          -e OAUTH_CLIENT_SECRET="\$OAUTH_CLIENT_SECRET" \
                          -e OAUTH_TOKEN_ENDPOINT="\$OAUTH_TOKEN_ENDPOINT" \
                          -e API_ENDPOINT="\$API_ENDPOINT" \
                          -e AWS_ACCESS_KEY_ID="\$AWS_ACCESS_KEY_ID" \
                          -e AWS_SECRET_ACCESS_KEY="\$AWS_SECRET_ACCESS_KEY" \
                          your-registry/cicd-runner:latest \
                            --suite-id "\${params.SUITE_ID}"
                    """
                }
            }
        }
    }
}
```

Store all secrets in Jenkins **Credentials** as "Secret text" entries. The `withCredentials` block injects them as environment variables scoped to the build step.

## Development

### Running Tests

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run property-based tests
pytest -k property
```

### Project Structure

```
cicd-runner/
├── src/
│   ├── api/           # API client (suites, executions)
│   ├── auth/          # OAuth authentication
│   ├── cli/           # CLI argument parsing
│   ├── config/        # Configuration management (pydantic Settings)
│   ├── execution/     # Test execution engine, artifact upload, log capture
│   ├── output/        # Execution summary formatting
│   └── utils/         # Errors, logging, log filters
├── tests/             # Unit and property tests
├── Dockerfile         # Multi-stage Docker build
├── .dockerignore      # Docker build exclusions
├── requirements.txt   # Runtime dependencies
├── requirements-dev.txt  # Development dependencies
├── setup.py          # Package setup
└── README.md         # This file
```

## Security

- Never commit `.env` files to version control
- Store OAuth credentials securely (use secrets management in CI/CD)
- Rotate OAuth client secrets regularly
- Use least-privilege scopes for OAuth clients
- Review CloudWatch logs for suspicious activity

## License

This project is licensed under the MIT-0 License. See the LICENSE file for details.
