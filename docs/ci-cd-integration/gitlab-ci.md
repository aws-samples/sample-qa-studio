# GitLab CI Integration

This guide shows how to integrate the Nova Act QA Studio CI/CD Runner into your GitLab CI/CD pipelines for automated testing.

## Overview

The CI/CD runner can be integrated into GitLab CI/CD pipelines to execute test suites automatically on code changes, merge requests, or scheduled intervals. The runner uses OAuth client credentials for authentication and reports test results via exit codes.

## Prerequisites

Before setting up GitLab CI integration, ensure you have:

1. **GitLab Runner**: GitLab.com provides shared runners with Docker support, or use your own runners
2. **OAuth Client**: Created via the Nova Act QA Studio platform with required scopes:
   - `api/suite.read` - Read test suite definitions
   - `api/suite.write` - Execute test suites
   - `api/execution.write` - Create and update execution records
3. **Test Suite ID**: UUID of the test suite to execute (found in platform UI)

## Quick Start

Basic pipeline that runs tests on every push to main:

```yaml
stages:
  - test

qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
  only:
    - main
```

## Setup Instructions

### Step 1: Create OAuth Client

Create an OAuth client in the Nova Act QA Studio platform:

1. Navigate to **Settings** → **OAuth Clients**
2. Click **Create OAuth Client**
3. Enter a name: `GitLab CI - <Project Name>`
4. Select scopes:
   - `api/suite.read`
   - `api/suite.write`
   - `api/execution.write`
5. Click **Create**
6. **Save the client secret** - it will only be shown once!

### Step 2: Configure GitLab CI/CD Variables

Add OAuth credentials as GitLab CI/CD variables:

1. Go to your project on GitLab
2. Navigate to **Settings** → **CI/CD** → **Variables**
3. Click **Add variable**
4. Add the following variables:

| Variable Name | Value | Type | Protected | Masked | Description |
|---------------|-------|------|-----------|--------|-------------|
| `OAUTH_CLIENT_ID` | `7abc123def456` | Variable | ✓ | ✗ | OAuth client ID from platform |
| `OAUTH_CLIENT_SECRET` | `secret_xyz789...` | Variable | ✓ | ✓ | OAuth client secret (shown once at creation) |
| `OAUTH_TOKEN_ENDPOINT` | `https://domain.auth.us-east-1.amazoncognito.com/oauth2/token` | Variable | ✓ | ✗ | Cognito token endpoint URL |
| `API_ENDPOINT` | `https://abc123.execute-api.us-east-1.amazonaws.com/api` | Variable | ✓ | ✗ | Platform API base URL |
| `TEST_SUITE_ID` | `01234567-89ab-cdef-0123-456789abcdef` | Variable | ✗ | ✗ | Test suite UUID from platform |

**Security Notes**:
- **Protected**: Variables are only available on protected branches (main, production, etc.)
- **Masked**: Variable values are masked in job logs (use for secrets)
- Never commit secrets to your repository
- Use separate OAuth clients for different projects/environments

### Step 3: Create Pipeline Configuration

Create `.gitlab-ci.yml` in your repository root:

```yaml
stages:
  - test

qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
  only:
    - main
    - merge_requests
```

### Step 4: Commit and Push

Commit the pipeline configuration and push to GitLab:

```bash
git add .gitlab-ci.yml
git commit -m "Add QA test automation pipeline"
git push origin main
```

The pipeline will run automatically on the next push or merge request.

## Docker-in-Docker Configuration

GitLab CI requires Docker-in-Docker (DinD) to run Docker containers within pipeline jobs.

### Basic DinD Setup

The minimal DinD configuration:

```yaml
qa-tests:
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm nova-act-cicd-runner:latest --help
```

### DinD with TLS (Recommended)

For enhanced security, use TLS with DinD:

```yaml
qa-tests:
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
    DOCKER_TLS_CERTDIR: "/certs"
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
```

### DinD without TLS (Not Recommended)

For testing or troubleshooting only:

```yaml
qa-tests:
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
    DOCKER_TLS_CERTDIR: ""
  script:
    - docker run --rm nova-act-cicd-runner:latest --help
```

**Warning**: Disabling TLS reduces security. Only use for debugging.

### Custom Docker Registry

If using a private Docker registry:

```yaml
qa-tests:
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  before_script:
    - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin $CI_REGISTRY
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        $CI_REGISTRY/nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
```

## Pipeline Examples

### Example 1: Basic Pipeline with Merge Requests

Run tests on pushes to main/develop and all merge requests:

```yaml
stages:
  - test

qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
  only:
    - main
    - develop
    - merge_requests
```

### Example 2: Environment-Specific Testing

Test against staging environment with base URL override:

```yaml
stages:
  - test

staging-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --base-url $STAGING_BASE_URL
        --verbose
  only:
    - develop
    - merge_requests
  environment:
    name: staging
```

### Example 3: Variable Overrides

Override test variables for different test scenarios:

```yaml
stages:
  - test

qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --base-url $STAGING_BASE_URL
        --var username=testuser
        --var environment=staging
        --var api_key=$TEST_API_KEY
        --verbose
  only:
    - main
```

### Example 4: Scheduled Testing

Run tests on a schedule (e.g., nightly):

```yaml
stages:
  - test

nightly-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --base-url $PRODUCTION_BASE_URL
        --timeout 7200
        --verbose
  only:
    - schedules
  after_script:
    - |
      if [ $CI_JOB_STATUS == 'failed' ]; then
        echo "Nightly tests failed!"
        # Add notification logic here (Slack, email, etc.)
      fi
```

**To create a schedule**:
1. Go to **CI/CD** → **Schedules**
2. Click **New schedule**
3. Set interval (e.g., `0 2 * * *` for 2 AM daily)
4. Select target branch
5. Save schedule

### Example 5: Multiple Environments with Dependencies

Test against multiple environments sequentially:

```yaml
stages:
  - test-staging
  - test-production

test-staging:
  stage: test-staging
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --base-url $STAGING_BASE_URL
        --var environment=staging
        --verbose
  only:
    - main
  environment:
    name: staging

test-production:
  stage: test-production
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --base-url $PRODUCTION_BASE_URL
        --var environment=production
        --verbose
  only:
    - main
  environment:
    name: production
  when: on_success  # Only run if staging tests pass
```

### Example 6: Parallel Testing

Test multiple configurations in parallel using matrix strategy:

```yaml
stages:
  - test

.qa-test-template:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --base-url https://$ENVIRONMENT.example.com
        --region $REGION
        --var environment=$ENVIRONMENT
        --verbose
  only:
    - main

test-staging-us-east-1:
  extends: .qa-test-template
  variables:
    ENVIRONMENT: staging
    REGION: us-east-1

test-staging-us-west-2:
  extends: .qa-test-template
  variables:
    ENVIRONMENT: staging
    REGION: us-west-2

test-production-us-east-1:
  extends: .qa-test-template
  variables:
    ENVIRONMENT: production
    REGION: us-east-1

test-production-us-west-2:
  extends: .qa-test-template
  variables:
    ENVIRONMENT: production
    REGION: us-west-2
```

### Example 7: Conditional Execution Based on Changes

Run different test suites based on changed files:

```yaml
stages:
  - test

test-frontend:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $FRONTEND_SUITE_ID
        --verbose
  only:
    changes:
      - frontend/**/*
      - .gitlab-ci.yml

test-backend:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $BACKEND_SUITE_ID
        --verbose
  only:
    changes:
      - backend/**/*
      - .gitlab-ci.yml
```

### Example 8: Extended Timeout for Large Suites

Increase timeout for long-running test suites:

```yaml
stages:
  - test

extended-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  timeout: 3h  # GitLab job timeout (3 hours)
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $EXTENDED_SUITE_ID
        --timeout 10800
        --verbose
  only:
    - main
```

### Example 9: Manual Pipeline with Input Parameters

Allow manual pipeline execution with custom parameters:

```yaml
stages:
  - test

manual-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - |
      SUITE_ID="${MANUAL_SUITE_ID:-$TEST_SUITE_ID}"
      BASE_URL="${MANUAL_BASE_URL:-$STAGING_BASE_URL}"
      docker run --rm \
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID" \
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT" \
        -e API_ENDPOINT="$API_ENDPOINT" \
        nova-act-cicd-runner:latest \
        --suite-id "$SUITE_ID" \
        --base-url "$BASE_URL" \
        --var environment=$MANUAL_ENVIRONMENT \
        --verbose
  when: manual
  only:
    - main
```

**To run manually**:
1. Go to **CI/CD** → **Pipelines**
2. Click **Run pipeline**
3. Add variables: `MANUAL_SUITE_ID`, `MANUAL_BASE_URL`, `MANUAL_ENVIRONMENT`
4. Click **Run pipeline**

### Example 10: Retry on Failure

Automatically retry failed tests:

```yaml
stages:
  - test

qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
  retry:
    max: 2
    when:
      - runner_system_failure
      - stuck_or_timeout_failure
  only:
    - main
```

## Pipeline Stages and Dependencies

GitLab CI allows you to organize jobs into stages and define dependencies between them.

### Basic Stage Ordering

Stages run sequentially, jobs within a stage run in parallel:

```yaml
stages:
  - build
  - test
  - deploy

build-app:
  stage: build
  script:
    - echo "Building application..."

qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose

deploy-app:
  stage: deploy
  script:
    - echo "Deploying application..."
  when: on_success  # Only deploy if tests pass
```

### Explicit Job Dependencies

Use `needs` to create explicit dependencies and run jobs out of stage order:

```yaml
stages:
  - test
  - deploy

unit-tests:
  stage: test
  script:
    - echo "Running unit tests..."

qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose

deploy-staging:
  stage: deploy
  script:
    - echo "Deploying to staging..."
  needs:
    - unit-tests
    - qa-tests
  environment:
    name: staging
```

### Complex Pipeline with Multiple Test Stages

```yaml
stages:
  - smoke-test
  - integration-test
  - e2e-test
  - deploy

smoke-tests:
  stage: smoke-test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $SMOKE_SUITE_ID
        --verbose

integration-tests:
  stage: integration-test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $INTEGRATION_SUITE_ID
        --verbose
  needs:
    - smoke-tests

e2e-tests:
  stage: e2e-test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  timeout: 2h
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $E2E_SUITE_ID
        --timeout 7200
        --verbose
  needs:
    - integration-tests

deploy-production:
  stage: deploy
  script:
    - echo "Deploying to production..."
  needs:
    - e2e-tests
  when: manual
  environment:
    name: production
```

## Pipeline Triggers

GitLab CI supports various trigger types to control when pipelines run.

### Branch-Based Triggers

Run on specific branches:

```yaml
qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
  only:
    - main
    - develop
    - /^release\/.*$/  # Regex for release branches
```

### Merge Request Triggers

Run on merge requests:

```yaml
qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
  only:
    - merge_requests
```

### Tag-Based Triggers

Run on Git tags:

```yaml
qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
  only:
    - tags
    - /^v\d+\.\d+\.\d+$/  # Semantic version tags
```

### Schedule Triggers

Run on a schedule (configured in GitLab UI):

```yaml
nightly-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --timeout 7200
        --verbose
  only:
    - schedules
```

**To create a schedule**:
1. Navigate to **CI/CD** → **Schedules**
2. Click **New schedule**
3. Enter description: `Nightly QA Tests`
4. Set interval pattern (cron syntax): `0 2 * * *` (2 AM daily)
5. Select target branch: `main`
6. Optionally add schedule-specific variables
7. Click **Save pipeline schedule**

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

### Combined Triggers

Combine multiple trigger types:

```yaml
qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
  only:
    - main
    - develop
    - merge_requests
    - schedules
```

### Exclude Triggers

Exclude specific branches or conditions:

```yaml
qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
  except:
    - /^wip\/.*$/  # Skip work-in-progress branches
    - /^draft\/.*$/  # Skip draft branches
```

## Exit Codes and Pipeline Control

The runner uses exit codes to indicate test results, which GitLab CI uses to determine pipeline success or failure.

| Exit Code | Meaning | Pipeline Behavior |
|-----------|---------|-------------------|
| `0` | All tests passed | Job succeeds, pipeline continues |
| `1` | One or more tests failed | Job fails, pipeline stops (unless configured otherwise) |
| `2` | Runner error (auth, config, API) | Job fails, pipeline stops |

### Fail Pipeline on Test Failure

Default behavior - pipeline fails if tests fail:

```yaml
qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
```

### Continue on Test Failure

Continue pipeline even if tests fail:

```yaml
qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
  allow_failure: true
```

### Custom Handling Based on Exit Code

Handle different exit codes differently:

```yaml
qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - |
      set +e  # Don't exit on error
      docker run --rm \
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID" \
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT" \
        -e API_ENDPOINT="$API_ENDPOINT" \
        nova-act-cicd-runner:latest \
        --suite-id $TEST_SUITE_ID \
        --verbose
      EXIT_CODE=$?
      
      if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ All tests passed!"
      elif [ $EXIT_CODE -eq 1 ]; then
        echo "❌ Tests failed - check logs above"
        exit 1
      elif [ $EXIT_CODE -eq 2 ]; then
        echo "⚠️ Runner error - check configuration"
        exit 2
      fi
```

### Conditional Deployment Based on Test Results

Deploy only if tests pass:

```yaml
stages:
  - test
  - deploy

qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose

deploy-production:
  stage: deploy
  script:
    - echo "Deploying to production..."
  when: on_success  # Only deploy if tests pass
  only:
    - main
```

## Best Practices

### Security

1. **Use Masked Variables**: Mark sensitive variables (secrets) as masked in GitLab CI/CD settings
2. **Protected Variables**: Use protected variables for production credentials (only available on protected branches)
3. **Separate OAuth Clients**: Use different OAuth clients for different projects/environments
4. **Minimal Scopes**: Grant only required scopes to OAuth clients
5. **Rotate Credentials**: Rotate OAuth client secrets regularly (every 90 days)
6. **Never Commit Secrets**: Never commit secrets to `.gitlab-ci.yml` or repository

### Performance

1. **Parallel Execution**: Use parallel jobs to test multiple configurations simultaneously
2. **Conditional Execution**: Use `only:changes` to run tests only when relevant files change
3. **Cache Docker Images**: Use GitLab Container Registry to cache runner images
4. **Timeout Configuration**: Set appropriate timeouts for large test suites
5. **Stage Optimization**: Use `needs` to run jobs as soon as dependencies are met

### Reliability

1. **Retry Logic**: Add `retry` configuration for transient failures
2. **Verbose Logging**: Use `--verbose` flag for troubleshooting
3. **Health Checks**: Add smoke tests before running full test suites
4. **Notifications**: Set up notifications for pipeline failures (Slack, email, etc.)
5. **Manual Triggers**: Enable manual jobs for production deployments

### Organization

1. **Descriptive Names**: Use clear job and stage names
2. **Comments**: Add comments to explain complex pipeline logic
3. **Templates**: Use YAML anchors and extends for reusable job definitions
4. **Environment Variables**: Use GitLab Variables for non-sensitive configuration
5. **Pipeline Visualization**: Structure stages logically for clear pipeline visualization

### Example: Well-Organized Pipeline

```yaml
# Pipeline stages
stages:
  - smoke-test
  - test
  - deploy

# Reusable template for QA tests
.qa-test-template: &qa-test-template
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  before_script:
    - echo "Starting QA tests for $CI_COMMIT_REF_NAME"
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $SUITE_ID
        --base-url $BASE_URL
        --verbose
  retry:
    max: 2
    when:
      - runner_system_failure
      - stuck_or_timeout_failure

# Smoke tests - fast, critical paths only
smoke-tests:
  <<: *qa-test-template
  stage: smoke-test
  variables:
    SUITE_ID: $SMOKE_SUITE_ID
    BASE_URL: $STAGING_BASE_URL
  only:
    - main
    - develop
    - merge_requests

# Full test suite - comprehensive testing
full-tests:
  <<: *qa-test-template
  stage: test
  variables:
    SUITE_ID: $FULL_SUITE_ID
    BASE_URL: $STAGING_BASE_URL
  timeout: 2h
  needs:
    - smoke-tests
  only:
    - main
    - develop

# Production deployment - manual approval required
deploy-production:
  stage: deploy
  script:
    - echo "Deploying to production..."
  when: manual
  needs:
    - full-tests
  only:
    - main
  environment:
    name: production
```

## Troubleshooting

### Pipeline Not Triggering

**Problem**: Pipeline doesn't run on push or merge request

**Solutions**:
1. Verify `.gitlab-ci.yml` is in repository root
2. Check YAML syntax is valid (use GitLab CI Lint tool: **CI/CD** → **Editor** → **Validate**)
3. Ensure branch names match `only` configuration
4. Check project settings allow CI/CD pipelines
5. Verify GitLab Runner is available and active

### Authentication Failures

**Problem**: `OAuth authentication failed: 401`

**Solutions**:
1. Verify variables are set correctly in **Settings** → **CI/CD** → **Variables**
2. Check OAuth client exists and is active in platform
3. Ensure OAuth client has required scopes (`api/suite.read`, `api/suite.write`, `api/execution.write`)
4. Verify token endpoint URL is correct
5. Check if variables are protected and job is running on unprotected branch

### Docker-in-Docker Issues

**Problem**: `Cannot connect to the Docker daemon`

**Solutions**:
1. Ensure `docker:dind` service is configured
2. Verify `DOCKER_DRIVER: overlay2` is set
3. Check if TLS configuration is correct (`DOCKER_TLS_CERTDIR`)
4. Try disabling TLS for debugging: `DOCKER_TLS_CERTDIR: ""`
5. Ensure GitLab Runner has Docker executor enabled

### Docker Pull Failures

**Problem**: `Unable to find image 'nova-act-cicd-runner:latest'`

**Solutions**:
1. Ensure Docker image is available in registry
2. Add authentication if using private registry (see Docker Registry example)
3. Specify full image path including registry URL
4. Check network connectivity from GitLab Runner to registry

### Test Timeouts

**Problem**: Tests timeout before completion

**Solutions**:
1. Increase runner timeout: `--timeout 7200`
2. Increase GitLab job timeout: `timeout: 2h`
3. Split large test suites into smaller suites
4. Run tests in parallel using multiple jobs
5. Check for network issues or slow test steps

### Variables Not Available

**Problem**: Variables are empty or undefined in pipeline

**Solutions**:
1. Verify variables are set at project level (not group level, unless intended)
2. Check variable names match exactly (case-sensitive)
3. Ensure variables are not protected if running on unprotected branch
4. For merge requests from forks, variables may not be available (security feature)
5. Check variable scope and environment settings

### Job Stuck in Pending

**Problem**: Job stays in "pending" state and never runs

**Solutions**:
1. Check if GitLab Runners are available and active
2. Verify runner tags match job requirements (if using tags)
3. Check runner capacity - may be at maximum concurrent jobs
4. Review runner configuration and ensure it can execute Docker jobs
5. Check project settings for runner availability

### YAML Syntax Errors

**Problem**: Pipeline fails with YAML syntax error

**Solutions**:
1. Use GitLab CI Lint tool: **CI/CD** → **Editor** → **Validate**
2. Check indentation (use spaces, not tabs)
3. Verify YAML anchors and references are correct
4. Ensure all required fields are present
5. Check for special characters that need quoting

### Debug Mode

Enable verbose logging for troubleshooting:

```yaml
qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
    CI_DEBUG_TRACE: "true"  # Enable GitLab CI debug mode
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        -e LOG_LEVEL=DEBUG
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
```

**Warning**: Debug mode may expose sensitive information in logs. Use only for troubleshooting and disable afterwards.

## Advanced Patterns

### Using YAML Anchors for Reusability

Define reusable configuration blocks:

```yaml
# Define anchors
.docker-config: &docker-config
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2

.qa-script: &qa-script
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose

# Use anchors
staging-tests:
  stage: test
  <<: *docker-config
  <<: *qa-script
  variables:
    TEST_SUITE_ID: $STAGING_SUITE_ID

production-tests:
  stage: test
  <<: *docker-config
  <<: *qa-script
  variables:
    TEST_SUITE_ID: $PRODUCTION_SUITE_ID
```

### Using Extends for Job Templates

Create job templates with `extends`:

```yaml
.qa-test-base:
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --base-url $BASE_URL
        --verbose
  retry:
    max: 2

staging-tests:
  extends: .qa-test-base
  stage: test
  variables:
    TEST_SUITE_ID: $STAGING_SUITE_ID
    BASE_URL: $STAGING_BASE_URL
  only:
    - develop

production-tests:
  extends: .qa-test-base
  stage: test
  variables:
    TEST_SUITE_ID: $PRODUCTION_SUITE_ID
    BASE_URL: $PRODUCTION_BASE_URL
  only:
    - main
  when: manual
```

### Multi-Project Pipelines

Trigger pipelines in other projects:

```yaml
stages:
  - test
  - trigger

qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        nova-act-cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose

trigger-deployment:
  stage: trigger
  trigger:
    project: group/deployment-project
    branch: main
  needs:
    - qa-tests
  only:
    - main
```

### Parent-Child Pipelines

Generate dynamic child pipelines:

**.gitlab-ci.yml**:
```yaml
stages:
  - generate
  - test

generate-config:
  stage: generate
  script:
    - |
      cat > child-pipeline.yml <<EOF
      stages:
        - test

      test-suite-1:
        stage: test
        image: docker:latest
        services:
          - docker:dind
        variables:
          DOCKER_DRIVER: overlay2
        script:
          - docker run --rm
              -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
              -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
              -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
              -e API_ENDPOINT="$API_ENDPOINT"
              nova-act-cicd-runner:latest
              --suite-id suite-1
              --verbose

      test-suite-2:
        stage: test
        image: docker:latest
        services:
          - docker:dind
        variables:
          DOCKER_DRIVER: overlay2
        script:
          - docker run --rm
              -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
              -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
              -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
              -e API_ENDPOINT="$API_ENDPOINT"
              nova-act-cicd-runner:latest
              --suite-id suite-2
              --verbose
      EOF
  artifacts:
    paths:
      - child-pipeline.yml

trigger-tests:
  stage: test
  trigger:
    include:
      - artifact: child-pipeline.yml
        job: generate-config
    strategy: depend
```

### Using GitLab Container Registry

Store and use runner image from GitLab Container Registry:

```yaml
stages:
  - build
  - test

build-runner:
  stage: build
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  before_script:
    - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin $CI_REGISTRY
  script:
    - docker build -t $CI_REGISTRY_IMAGE/cicd-runner:$CI_COMMIT_SHA .
    - docker push $CI_REGISTRY_IMAGE/cicd-runner:$CI_COMMIT_SHA
    - docker tag $CI_REGISTRY_IMAGE/cicd-runner:$CI_COMMIT_SHA $CI_REGISTRY_IMAGE/cicd-runner:latest
    - docker push $CI_REGISTRY_IMAGE/cicd-runner:latest
  only:
    - main

qa-tests:
  stage: test
  image: docker:latest
  services:
    - docker:dind
  variables:
    DOCKER_DRIVER: overlay2
  before_script:
    - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin $CI_REGISTRY
  script:
    - docker run --rm
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT"
        -e API_ENDPOINT="$API_ENDPOINT"
        $CI_REGISTRY_IMAGE/cicd-runner:latest
        --suite-id $TEST_SUITE_ID
        --verbose
  needs:
    - build-runner
```

## Complete Example Pipeline

Here's a comprehensive example combining best practices:

```yaml
# Complete GitLab CI pipeline for Nova Act QA Studio
# This pipeline demonstrates best practices for test automation

# Define pipeline stages
stages:
  - smoke-test
  - integration-test
  - e2e-test
  - deploy

# Global variables (can be overridden per job)
variables:
  DOCKER_DRIVER: overlay2
  DOCKER_TLS_CERTDIR: "/certs"

# Reusable job template
.qa-test-template:
  image: docker:latest
  services:
    - docker:dind
  before_script:
    - echo "🚀 Starting QA tests for $CI_COMMIT_REF_NAME (commit $CI_COMMIT_SHORT_SHA)"
  script:
    - |
      docker run --rm \
        -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID" \
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
        -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT" \
        -e API_ENDPOINT="$API_ENDPOINT" \
        nova-act-cicd-runner:latest \
        --suite-id $SUITE_ID \
        --base-url $BASE_URL \
        --var environment=$ENVIRONMENT \
        --var commit_sha=$CI_COMMIT_SHORT_SHA \
        --verbose
  after_script:
    - |
      if [ $CI_JOB_STATUS == 'success' ]; then
        echo "✅ Tests passed successfully"
      else
        echo "❌ Tests failed - check logs above"
      fi
  retry:
    max: 2
    when:
      - runner_system_failure
      - stuck_or_timeout_failure

# Smoke tests - fast, critical paths only
smoke-tests:
  extends: .qa-test-template
  stage: smoke-test
  variables:
    SUITE_ID: $SMOKE_SUITE_ID
    BASE_URL: $STAGING_BASE_URL
    ENVIRONMENT: staging
  only:
    - main
    - develop
    - merge_requests
  except:
    - schedules

# Integration tests - API and service integration
integration-tests:
  extends: .qa-test-template
  stage: integration-test
  variables:
    SUITE_ID: $INTEGRATION_SUITE_ID
    BASE_URL: $STAGING_BASE_URL
    ENVIRONMENT: staging
  timeout: 1h
  needs:
    - smoke-tests
  only:
    - main
    - develop
    - merge_requests
  except:
    - schedules

# End-to-end tests - full user journeys
e2e-tests:
  extends: .qa-test-template
  stage: e2e-test
  variables:
    SUITE_ID: $E2E_SUITE_ID
    BASE_URL: $STAGING_BASE_URL
    ENVIRONMENT: staging
  timeout: 2h
  needs:
    - integration-tests
  only:
    - main
    - develop
  except:
    - schedules

# Nightly regression tests - comprehensive testing
nightly-regression:
  extends: .qa-test-template
  stage: e2e-test
  variables:
    SUITE_ID: $REGRESSION_SUITE_ID
    BASE_URL: $PRODUCTION_BASE_URL
    ENVIRONMENT: production
  timeout: 3h
  only:
    - schedules
  after_script:
    - |
      if [ $CI_JOB_STATUS == 'failed' ]; then
        echo "🚨 Nightly regression tests failed!"
        # Add notification logic here (Slack webhook, email, etc.)
      fi

# Production smoke tests - verify production health
production-smoke:
  extends: .qa-test-template
  stage: smoke-test
  variables:
    SUITE_ID: $SMOKE_SUITE_ID
    BASE_URL: $PRODUCTION_BASE_URL
    ENVIRONMENT: production
  only:
    - main
  when: manual
  allow_failure: true

# Deploy to staging - automatic after tests pass
deploy-staging:
  stage: deploy
  script:
    - echo "🚀 Deploying to staging environment..."
    # Add deployment commands here
  needs:
    - e2e-tests
  only:
    - develop
  environment:
    name: staging
    url: https://staging.example.com

# Deploy to production - manual approval required
deploy-production:
  stage: deploy
  script:
    - echo "🚀 Deploying to production environment..."
    # Add deployment commands here
  needs:
    - e2e-tests
  only:
    - main
  when: manual
  environment:
    name: production
    url: https://production.example.com
```

## Related Documentation

- [Configuration Reference](../configuration.md) - Environment variables and CLI arguments
- [CLI Reference](../cli-reference.md) - Detailed CLI usage
- [Troubleshooting Guide](../troubleshooting.md) - Common errors and solutions
- [Best Practices](../best-practices.md) - Security and optimization guidance
- [API Reference](../api-reference.md) - API documentation for advanced integration

## Support

For GitLab CI integration assistance:

1. Check the [GitLab CI/CD documentation](https://docs.gitlab.com/ee/ci/)
2. Review [Troubleshooting Guide](../troubleshooting.md)
3. Enable verbose logging (`--verbose`) for detailed diagnostics
4. Use GitLab CI Lint tool to validate YAML syntax
5. Check [GitLab Issues](https://gitlab.com/gitlab-org/gitlab/-/issues)
6. Contact your platform administrator

