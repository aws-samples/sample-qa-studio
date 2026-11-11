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

1. Navigate to OAuth Clients (Editors, Team Leads and Admins)
2. Click "Create OAuth Client"
3. Name it (e.g., "CI/CD Pipeline")
4. Pick the **Team** that owns the suites the pipeline runs (required). The client acts as a member of that team with your role, capped at Editor, and can't reach other teams' resources.
5. Grant required scopes:
   - `api/suite.read`, `api/suite.write`
   - `api/usecases.read`, `api/usecases.execute`
   - `api/executions.read`, `api/executions.write`
6. Save the client ID and secret (secret is only shown once)

Clients created before team binding show as "Unbound (no access)" and get 403 on every team-owned resource. Re-create them with a team. See [User Management](user-management.md#oauth-clients-m2m).

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
| `--usecase-id` | TEXT | No* | One or more use case IDs separated by whitespace (quote the value, e.g. `"id-a id-b"`). Several IDs run sequentially and end with a summary. | - |
| `--execution-id` | TEXT | No | Attach to a pre-created execution record (skips creation). Only valid with exactly one `--usecase-id` in remote mode. | - |
| `--fail-fast` | FLAG | No | Stop after the first failed use case; remaining use cases are reported as `skipped`. Only with `--usecase-id`. | False |
| `--local-only` | FLAG | No | Local-only execution (no remote records). Repeat steps that reference an application dataset are resolved by the CLI through `GET /applications/{id}/datasets/{datasetId}`, so the token needs `api/applications.read` (see [Application-level configuration](#application-level-configuration-variables-secrets-datasets)); remote runs resolve them server-side. | False |
| `--token-file` | TEXT | No | Path to JSON token file | ~/.qa-studio/tokens.json |
| `--base-url` | TEXT | No | Override base URL for all use cases | - |
| `--var` | TEXT | No | Override variable (key=value, repeatable) | - |
| `--dataset-file` | `[LABEL=]PATH` | No | CSV that replaces the stored rows of a repeat step for this run (repeatable) — whether the step carries inline rows or references an application dataset. The header row must name exactly the repeat's columns; `LABEL` is the repeat step's label and may be omitted when the use case has exactly one repeat. Only with `--usecase-id`; not with `--suite-id` or `--execution-id`. | - |
| `--region` | TEXT | No | AWS region for the run's regional AWS calls, in local **and** remote mode. Local: the browser provisioner context and the S3 app-binary download (mobile). Suite runs: the region of the created executions. Precedence: `--region` > `AWS_REGION` / `AWS_DEFAULT_REGION` > AWS profile region. Nova Act always runs in `us-east-1` and Device Farm in `us-west-2`; `--region` does not move them. | AWS default chain |
| `--model-id` | TEXT | No | Override Nova Act model ID | - |
| `--device-arn` | TEXT | No | Override Device Farm device ARN for mobile tests | - |
| `--app-path` | TEXT | No | Application under test. Mobile: local `.apk`/`.ipa` uploaded to Device Farm. Electron: `.app` bundle or executable to launch (required for electron usecases). | - |
| `--app-arg` | TEXT | No | Extra argument for the Electron app, repeatable (e.g. the app directory when `--app-path` is the bare `electron` binary). Requires `--app-path`. | - |
| `--app-user-data-dir` | PATH | No | Electron `--user-data-dir` to reuse (pre-seeded profile). Default is a fresh temp dir per run, removed at teardown. Requires `--app-path`. | temp dir |
| `--browser` | CHOICE | No | Browser provisioner: `local`, `agentcore`, `cdp-external`. `agentcore` requires the `[agentcore]` extra. | local |
| `--cdp-endpoint-url` | TEXT | No | CDP websocket URL. Required when `--browser=cdp-external`. | - |
| `--cdp-headers-file` | PATH | No | Path to a JSON file with CDP connection headers (used with `--browser=cdp-external`). | - |
| `--verbose` | FLAG | No | Show full runner logging (API calls, engine internals, Nova Act think/act trace). Default output is one progress line per test and per step, on stderr. | False |
| `--timeout` | INTEGER ≥ 1 | No | Stop the **whole run** after N seconds (integer ≥ 1). Default: no limit. Checked before each test and each step; on expiry the running test fails with `Run timed out after Ns (--timeout)`, remaining tests are `skipped`, browsers are torn down, remote executions are marked failed, and the exit code is `3`. A step that hangs is hard-stopped 30 s after the deadline. The cloud worker passes no `--timeout`; its ceiling is the MicroVM's `maximumDurationInSeconds` (config `maxExecutionDurationMinutes`), enforced by the supervisor. | no limit |
| `--keep-artifacts` | FLAG | No | Keep local artifact files after upload | False |
| `--format` | CHOICE | No | Output format (json or human) | json |

\* Either `--suite-id` or `--usecase-id` is required

**Examples**:

```bash
# Run single test
qa-studio run --usecase-id test-123

# Run several tests in one call (sequential, one summary at the end)
qa-studio run --usecase-id "test-123 test-456 test-789" --format human

# Stop at the first failure; the rest are reported as skipped
qa-studio run --usecase-id "test-123 test-456 test-789" --fail-fast

# Run test suite
qa-studio run --suite-id suite-456

# Run with environment override
qa-studio run --usecase-id test-123 --base-url https://staging.example.com

# Run with variable overrides
qa-studio run --usecase-id test-123 --var username=testuser --var password=testpass

# Run a data-driven test (repeat step) with a CSV instead of the stored rows
qa-studio run --usecase-id test-123 --dataset-file "Login as each user=users-staging.csv"

# Run locally without creating remote execution records
qa-studio run --usecase-id test-123 --local-only

# Run with custom region and model
qa-studio run --usecase-id test-123 \
  --region us-west-2 \
  --model-id us.amazon.nova-2-lite-v1:0

# Run a mobile test (auto-detects platform from use case config)
qa-studio run --usecase-id mobile-test-123

# Run a mobile test with a specific device
qa-studio run --usecase-id mobile-test-123 \
  --device-arn arn:aws:devicefarm:us-west-2::device:ABC123

# Run a mobile test with a local app binary (first-time upload to Device Farm)
qa-studio run --usecase-id mobile-test-123 \
  --app-path /path/to/app.ipa

# Run an Electron desktop test (platform auto-detected; the app is launched by the runner)
qa-studio run --usecase-id desktop-test-123 \
  --app-path "/Applications/My App.app"

# Show full runner logging (API calls, engine internals, Nova Act trace)
qa-studio run --usecase-id test-123 --verbose

# Run with custom timeout (2 hours)
qa-studio run --suite-id suite-456 --timeout 7200
```

**Output**:

By default `qa-studio run` prints one line when a test starts and one line when each step starts. There is no per-step completion line; the verdict is in the summary (or JSON document) at the end.

| Line | Format |
|------|--------|
| Test start | `[HH:MM:SS] Executing Test "{name}"` — remote runs append ` (execution {execution_id})` |
| Step start | `[HH:MM:SS] Step {n}: {instruction}` — validation steps append ` ({validation_value})`; repeat rows render as `Step {n} (row {i}/{total})` |
| Step start in a suite | `[HH:MM:SS] [{test name}] Step {n}: {instruction}` — suite use cases run in parallel in remote mode, so lines interleave |
| Run stopped by `--timeout` | `[HH:MM:SS] ERROR Run timed out after {N}s (--timeout)` — exit code `3` |
| Run stopped by SIGTERM | `[HH:MM:SS] ERROR terminated: run stopped by SIGTERM` — exit code `143` (or `ERROR timeout: run exceeded the configured ceiling of {N}s`, exit code `3`, when the parent set `QA_STUDIO_TERMINATION_REASON=timeout`) |

```
$ qa-studio run --usecase-id 7f3a… --local-only --format human
[14:02:11] Executing Test "Login with valid credentials"
[14:02:14] Step 1: Open the login page
[14:02:19] Step 2: Type the username into the email field
[14:02:23] Step 3: Click into the password field
[14:02:27] Step 4: Click "Sign in"
[14:02:33] Step 5: Check the greeting in the header (Welcome back, Jane)

QA Studio - Local Execution

Test: Login with valid credentials
Duration: 24s
  ✓ [navigation] Open the login page (3s)
  …
✓ PASSED  |  Steps: 5/5 passed  |  Failed: 0
```

Progress lines go to **stderr**; **stdout** carries only the result (the `--format json` document or the human summary), so `qa-studio run … 2>/dev/null | jq .status` works. Warnings and errors (e.g. `[14:02:35] WARNING Failed to update step status: …`) are still printed without `--verbose`.

With `--verbose` the console additionally shows the runner's DEBUG logging (`[HH:MM:SS] DEBUG → GET https://…`, engine internals) and the Nova Act think/act trace — the output the CLI printed before the quiet default. The per-execution log artifact (`logs.txt`, uploaded in remote mode) always contains the full DEBUG log regardless of the flag.

**Exit Codes**:

| Code | Meaning | Description |
|------|---------|-------------|
| 0 | Success | All tests passed |
| 1 | Failure | One or more tests failed or were skipped (`--fail-fast`) |
| 2 | Error | CLI error before execution started (authentication, configuration, unknown use case ID, API error) |
| 3 | Timeout | `--timeout` expired, or the parent process sent SIGTERM with `QA_STUDIO_TERMINATION_REASON=timeout` (the cloud MicroVM worker does this). Remote executions are marked `failed` with `error_message` starting `timeout:` |
| 143 | Terminated | SIGTERM received (a cancelled CI job, `docker stop`, `kill`). The runner tears down the browser and marks in-flight remote executions `failed` with `error_message` `terminated: run stopped by SIGTERM`, then exits `128 + 15` |

**SIGTERM handling** (`qa_studio_cli/runner/termination.py`): the signal is turned into a cooperative stop in the main thread, so the same `finally` blocks run as on a normal finish — the AgentCore/local browser is deleted, the live-view record removed and the execution status PATCHed. The run gets 10 s to stop on its own, then a hard stop marks every in-flight execution failed and exits without waiting for a stuck step. A second SIGTERM ends the grace at once. Two environment variables shape the report; CI pipelines normally set neither:

| Variable | Type | Default | Effect |
|---|---|---|---|
| `QA_STUDIO_TERMINATION_REASON` | `terminated` \| `timeout` | `terminated` | Chooses the `error_message` prefix (`terminated:` / `timeout:`) and the exit code (`143` / `3`). Unknown values are logged and treated as `terminated`. Read when the signal arrives |
| `QA_STUDIO_MAX_DURATION_SECONDS` | integer | unset | With `timeout`, named in the message: `timeout: run exceeded the configured ceiling of Ns` |

Nothing changes for CI runners with the Lambda MicroVM worker: `qa-studio run` behaves the same on your CI host as inside a VM, a `ci_runner` execution never starts a VM, and the CI integration needs no new scopes, flags or configuration.

**Summary output (several `--usecase-id` values)**:

With a single ID the output is the bare result of that run, exactly as before. With two or more IDs every definition is fetched first (an unknown ID exits with code 2 before any browser starts), each use case runs in turn, and a summary is printed at the end. In `--format human` the per-test detail is printed as each test finishes, followed by:

```
QA Studio - Run Summary

Passed: 2/3

✓ Login
✗ Checkout
○ Search (skipped)
```

In `--format json` (default) a single document is printed:

| Field | Type | Description |
|-------|------|-------------|
| `total` | integer | Number of use case IDs given |
| `passed` | integer | Use cases with status `success` |
| `failed` | integer | Use cases with status `failed` (including runner exceptions during that use case) |
| `skipped` | integer | Use cases not started because of `--fail-fast` |
| `results[]` | array | One entry per use case, in command-line order |
| `results[].usecaseId` | string | Use case ID |
| `results[].usecaseName` | string | Use case name from its definition |
| `results[].status` | `success` \| `failed` \| `skipped` | Verdict |
| `results[].executionId` | string \| null | Execution record ID (remote mode only) |
| `results[].duration` | number | Seconds; `0` for skipped |
| `results[].error` | string \| null | Sanitised error when the runner raised during this use case |

Each use case still gets its own execution record in remote mode (trigger type `ci_runner`); there is no suite-execution grouping.

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

### Using Dataset Overrides (repeat steps)

A use case with a **repeat** step carries its own small table (columns + rows) and runs the steps inside the repeat once per row. In CI you can swap the stored rows for an environment-specific CSV with `--dataset-file`:

```csv
email,role
alice@staging.example,admin
bob@staging.example,viewer
```

```bash
# LABEL is the repeat step's label (its instruction text)
qa-studio run --usecase-id test-123 \
  --dataset-file "Login as each user=users-staging.csv"

# LABEL may be omitted when the use case has exactly one repeat step
qa-studio run --usecase-id test-123 --dataset-file users-staging.csv

# Works in local-only mode too (the CLI unrolls the rows itself)
qa-studio run --usecase-id test-123 --local-only --dataset-file users-staging.csv
```

Rules:

| Rule | Behaviour |
|---|---|
| Header row | Required; must contain exactly the repeat's columns (any order). A mismatch exits with code 2 before any browser starts. |
| Cells | Read as strings; missing trailing cells become `""`; blank lines are skipped. |
| Caps | 100 rows, 20 columns, 200 KB serialized (same as the server). |
| Scope | `--usecase-id` only. Not accepted with `--suite-id` or `--execution-id`. |
| Output | Expanded steps are prefixed with `[row i/n]` in human output and carry `repeat_row_index` / `repeat_row_total` / `repeat_label` in JSON output. |
| Application datasets | A repeat step that references an application dataset (`dataset_id`) is overridden the same way, by label. The CSV replaces the whole table for this run only; the dataset itself is untouched. |

### Application-level configuration (variables, secrets, datasets)

Values shared by every use case of an application can live on the application instead of on each use case (see [User Guide → Applications](./user-guide.md#applications-shared-variables-secrets-and-datasets)). At run time the layers resolve in this order — later rows win:

| Precedence | Layer | Variables | Secrets | Repeat datasets |
|---|---|---|---|---|
| 1 (lowest) | Application | `qa-studio apps variables set <app-id> KEY=VALUE` / Variables page | `qa-studio apps secrets set <app-id> KEY` / Secrets page | `qa-studio apps datasets create <app-id> NAME --file rows.csv`, referenced by the repeat step's `dataset_id` |
| 2 | Use case | use-case variable with the same key | use-case secret with the same key | the repeat step's own inline rows (a step has `dataset_id` **or** inline rows, never both) |
| 3 (highest) | CLI run | `--var KEY=VALUE` | — (no per-run secret override; rotate with `apps secrets set`) | `--dataset-file [LABEL=]file.csv` replaces the whole table for this run |

Variables and secrets merge **per key**; datasets are replaced **as a whole**. A missing key still fails the run with the existing "unresolved variable" / "secret not found" errors.

Remote runs (the default) need nothing extra: the server merges variables, resolves secrets and copies dataset rows onto the execution before the runner starts. Two cases need the `api/applications.read` scope on the token:

- `qa-studio run --local-only` on a use case whose repeat step references an application dataset — the CLI fetches the dataset itself (`GET /applications/{id}/datasets/{datasetId}`). Without the scope the run exits with code 2 and `--local-only with application datasets needs the api/applications.read scope`.
- `qa-studio apps variables|secrets|datasets list/get` (writes need `api/applications.write`).

Which tokens carry it:

| Token | `api/applications.read` present? |
|---|---|
| User token from `qa-studio login` | Yes — user scopes come from Cognito groups; every team role (Viewer and up) includes `api/applications.read`, Editor+ includes `api/applications.write`. |
| OAuth client (`OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET`, config-file M2M) | **No.** The CLI requests a fixed scope list for client-credentials tokens (`api/suite.read api/suite.write api/usecases.read api/usecases.execute api/executions.read api/executions.write`, `qa_studio_cli/auth/client_credentials.py`), and Cognito issues only the requested scopes. Granting `api/applications.read` to the client is necessary but not sufficient today; until the CLI requests it, run such use cases in remote mode (drop `--local-only`) or use a user token. |

```bash
# Set shared values once per application
qa-studio apps variables set <app-id> base_api=https://api.staging.example.com
qa-studio apps secrets set <app-id> admin_password --value-file ./admin_password.txt
qa-studio apps datasets create <app-id> customers --file ./customers.csv

# One run with the application overridden
qa-studio run --usecase-id test-123 --var base_api=https://api.pr-42.example.com \
  --dataset-file "Check each customer=customers-pr-42.csv"
```

`qa-studio apps …` option tables are in the [CLI README](../qa-studio-cli/README.md#application-configuration).

---

## Mobile Testing in CI/CD

The CLI supports running mobile tests on AWS Device Farm. Mobile use cases are auto-detected from the use case configuration — no special flags are required for basic usage.

### Prerequisites

- AWS credentials with Device Farm permissions (`devicefarm:*` in `us-west-2`)
- A mobile use case created in QA Studio with app binary uploaded
- The app binary must have been uploaded to Device Farm at least once (via the web UI or a previous CLI run with `--app-path`)

### How It Works

1. The CLI fetches the use case from the API and detects `test_platform: "mobile"`
2. It looks for an existing Device Farm upload matching the app filename (no re-download needed)
3. A Device Farm remote access session is provisioned on a real device
4. Nova Act controls the device via Appium and executes the test steps
5. After execution, the CLI requests an async recording download via the API
6. The recording becomes available in the QA Studio UI within 5-10 minutes

### App Binary Resolution

The CLI resolves the app binary in this order:
1. `--app-path` flag — local file, uploaded directly to Device Farm
2. `app_arn` on the use case — pre-existing Device Farm upload ARN
3. `app_binary_s3_path` on the use case — searches Device Farm for an existing upload by filename
4. `app_binary_s3_path` + `S3_BUCKET` env var — downloads from S3 and uploads to Device Farm

For CI/CD, the simplest approach is to ensure the app has been uploaded at least once (via the web UI or `--app-path`), then subsequent runs reuse the existing Device Farm upload automatically.

### Example: Mobile Test in GitHub Actions

```yaml
- name: Run Mobile Tests
  env:
    OAUTH_CLIENT_ID: ${{ secrets.OAUTH_CLIENT_ID }}
    OAUTH_CLIENT_SECRET: ${{ secrets.OAUTH_CLIENT_SECRET }}
    OAUTH_TOKEN_ENDPOINT: ${{ secrets.OAUTH_TOKEN_ENDPOINT }}
    QA_STUDIO_API_URL: ${{ secrets.QA_STUDIO_API_URL }}
  run: |
    # Run mobile test (auto-detects from use case config)
    qa-studio run --usecase-id ${{ vars.MOBILE_TEST_ID }}

    # Or with a fresh app binary
    qa-studio run \
      --usecase-id ${{ vars.MOBILE_TEST_ID }} \
      --app-path ./build/output/app-release.apk
```

### Limitations

- Device Farm session provisioning adds 1-2 minutes to execution time
- Session recordings are available asynchronously (5-10 minutes after completion)
- Device Farm is only available in `us-west-2`
- Specific devices may occasionally be unavailable — prefer "Highly available" devices or use auto-selection

---

## Electron Testing in CI/CD

Electron usecases (`test_platform: "electron"`) are the one platform that **only** the CI runner can execute: the app needs a display, which the cloud worker does not have. The API rejects every other trigger with `400 Electron usecases can only be executed by the CI runner (qa-studio run)`.

### Prerequisites

- A macOS runner (the app's only release target) with a **logged-in GUI session** — headless agents and `ssh`-only sessions cannot open windows
- The application build available on the runner (download the release artifact or build it in an earlier job)
- `qa-studio[runner]` installed, Nova Act / Bedrock credentials, and an M2M OAuth client with `api/executions.write`
- A **single-tenant** runner: the DevTools port is loopback-only but unauthenticated, so any local user could attach while a test runs

### How It Works

1. The CLI fetches the use case and detects `test_platform: "electron"`.
2. It launches `<app> --remote-debugging-port=0 --user-data-dir=<temp> <extra args>` in its own process group and reads the `DevTools listening on ws://127.0.0.1:<port>/…` line.
3. Nova Act attaches to the window the app opened (`cdp_use_existing_page`), and steps run exactly as for web tests.
4. Step status and artifacts are posted to QA Studio; the app is terminated (SIGTERM, then SIGKILL) and the temp profile removed.

### Example: Electron Test in GitHub Actions (macOS runner)

```yaml
jobs:
  desktop-e2e:
    runs-on: [self-hosted, macOS, gui]   # a runner with a logged-in desktop session
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: my-app-macos-arm64
          path: dist
      - run: unzip -q dist/*.zip -d dist/app
      - run: pip install "qa-studio[runner] @ git+https://…"   # or your internal index
      - name: Run Electron suite
        env:
          OAUTH_CLIENT_ID: ${{ secrets.OAUTH_CLIENT_ID }}
          OAUTH_CLIENT_SECRET: ${{ secrets.OAUTH_CLIENT_SECRET }}
          OAUTH_TOKEN_ENDPOINT: ${{ secrets.OAUTH_TOKEN_ENDPOINT }}
          QA_STUDIO_API_URL: ${{ secrets.QA_STUDIO_API_URL }}
          QA_STUDIO_ELECTRON_START_TIMEOUT: "60"
        run: |
          qa-studio run --suite-id ${{ vars.DESKTOP_SUITE_ID }} \
            --app-path "dist/app/My App.app"
```

One `--app-path` applies to every Electron usecase in the suite; web usecases in a mixed suite ignore it.

### Login

Drive the app's own login UI with `secret` steps, or seed a profile once by hand and pass it with `--app-user-data-dir`. Never put credentials in `--app-arg` — those values are logged.

### Cleanup

Teardown kills the app's process group. If the runner itself is killed mid-run, an orphaned app may survive; a pre-job step such as `pkill -f -- --remote-debugging-port || true` keeps runners clean.

### Limitations

- No video (Nova Act cannot record over CDP); screenshots and traces are captured
- No live view, no step caching, no wizard
- `HEADLESS` has no effect; the host must be able to show windows

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

### Cost ledgers for CI and BI

QA Studio allocates the daily Cost Explorer bill per use case, application and overall ([User Guide → Cost](user-guide.md#cost-per-use-case-application-and-overall)). Besides the API routes (`GET /applications/{id}/costs`, `GET /usecase/{id}/costs`, `GET /dashboard/costs` — [API Reference → Cost Endpoints](api-reference.md#cost-endpoints)), the full history is available as plain files for pipelines and BI tools: one NDJSON ledger per dimension under `s3://<account>-<baseName>-artefacts-<region>/cost_allocation/` (`overall.ndjson`, `{application_id}/raw.ndjson`, `{application_id}/{usecase_id}.ndjson`, `_unassigned/{usecase_id}.ndjson`), one JSON row per UTC day, sorted by date, with `date`, `estimated`, `cost[]` (`service`, `cost`, `list_cost`, `usage_seconds`, `launches`) and — on application and overall rows — `buckets` ([field table](architecture.md#cost-allocation)). Reading them needs S3 read access on that prefix (an IAM role, not a QA Studio token); the files are rewritten by the collector every morning (the last `lookbackDays` days change, older rows do not), so a nightly job after 07:00 UTC sees final data. Example: the daily cost of one application for the current month, from a CI job with AWS credentials:

```bash
aws s3 cp "s3://${ACCOUNT}-${BASE_NAME}-artefacts-${REGION}/cost_allocation/${APP_ID}/raw.ndjson" - \
  | jq -r 'select(.date | startswith("2026-11")) | [.date, ([.cost[].cost] | add), .buckets.unmetered] | @tsv'
```

Point Athena or any NDJSON-capable loader at the prefix for dashboards. Do not write to these files: the collector performs conditional puts and a hand-edited row with a duplicate date breaks the summary.

### Error Handling

**Fail Pipeline on Test Failures**:
```bash
# Exit code 0 = success, 1 = test failures, 2 = error, 3 = --timeout expired, 143 = terminated by SIGTERM
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

### `--local-only` fails with `dataset ... not found` or a scope hint

**Symptoms**: `qa-studio run --local-only` exits with code 2 and `dataset <id> not found in application <app>` or `--local-only with application datasets needs the api/applications.read scope`.

**Cause**: The use case has a repeat step that references an application dataset. In local-only mode the CLI fetches the dataset; the token either lacks `api/applications.read` (OAuth client tokens never carry it today — see [Application-level configuration](#application-level-configuration-variables-secrets-datasets)) or the dataset was deleted / belongs to another application.

**Solutions**: Run in remote mode (drop `--local-only`; the server resolves the dataset), authenticate with a user token, or feed the rows yourself with `--dataset-file "<label>=rows.csv"` (the override wins, but the reference is still fetched first in local-only mode).

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

**Error**: `Run timed out after 3600s (--timeout)` (exit code 3)

`--timeout` has no default; this only happens when the pipeline passes one.

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

### Device Farm Session Fails (Mobile)

**Error**: "Device Farm session failed to reach RUNNING state" or "Unknown error with device"

**Solutions**:
1. Try a different device:
   ```bash
   qa-studio run --usecase-id test-123 \
     --device-arn arn:aws:devicefarm:us-west-2::device:DIFFERENT_DEVICE
   ```

2. Let the system auto-select a device (omit `--device-arn` and clear `device_arn` on the use case)

3. Verify the app binary is compatible with the selected device's OS version

4. Check Device Farm service health in the AWS Console

### App Not Found on Device (Mobile)

**Error**: "App with bundle identifier 'com.example.app' unknown"

**Solutions**:
1. Upload the app binary:
   ```bash
   qa-studio run --usecase-id test-123 --app-path /path/to/app.ipa
   ```

2. Verify the app was previously uploaded to Device Farm:
   ```bash
   aws devicefarm list-uploads \
     --arn <project-arn> \
     --type IOS_APP \
     --region us-west-2
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
| `QA_STUDIO_ELECTRON_START_TIMEOUT` | Seconds to wait for an Electron app to expose DevTools and open its first window | 30 | No |

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
