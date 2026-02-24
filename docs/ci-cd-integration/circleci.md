# CircleCI Integration

This guide shows how to integrate the Nova Act QA Studio CI/CD Runner into your CircleCI workflows for automated testing.

## Overview

The CI/CD runner can be integrated into CircleCI workflows to execute test suites automatically on code changes, pull requests, or scheduled intervals. The runner uses OAuth client credentials for authentication and reports test results via exit codes.

## Prerequisites

Before setting up CircleCI integration, ensure you have:

1. **CircleCI Account**: CircleCI.com account or self-hosted CircleCI installation
2. **OAuth Client**: Created via the Nova Act QA Studio platform with required scopes:
   - `api/suite.read` - Read test suite definitions
   - `api/suite.write` - Execute test suites
   - `api/execution.write` - Create and update execution records
3. **Test Suite ID**: UUID of the test suite to execute (found in platform UI)

## Quick Start

Basic configuration that runs tests on every push to main:

```yaml
version: 2.1

jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run QA Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --verbose

workflows:
  version: 2
  test:
    jobs:
      - qa-tests:
          context: nova-act-qa
```

## Setup Instructions

### Step 1: Create OAuth Client

Create an OAuth client in the Nova Act QA Studio platform:

1. Navigate to **Settings** → **OAuth Clients**
2. Click **Create OAuth Client**
3. Enter a name: `CircleCI - <Project Name>`
4. Select scopes:
   - `api/suite.read`
   - `api/suite.write`
   - `api/execution.write`
5. Click **Create**
6. **Save the client secret** - it will only be shown once!

### Step 2: Configure CircleCI Context

CircleCI contexts provide a secure way to share environment variables across projects.

**Create a Context**:

1. Go to CircleCI web app
2. Navigate to **Organization Settings** → **Contexts**
3. Click **Create Context**
4. Enter context name: `nova-act-qa`
5. Click **Create Context**

**Add Environment Variables to Context**:

1. Click on the `nova-act-qa` context
2. Click **Add Environment Variable**
3. Add the following variables:

| Variable Name | Value | Description |
|---------------|-------|-------------|
| `OAUTH_CLIENT_ID` | `7abc123def456` | OAuth client ID from platform |
| `OAUTH_CLIENT_SECRET` | `secret_xyz789...` | OAuth client secret (shown once at creation) |
| `OAUTH_TOKEN_ENDPOINT` | `https://domain.auth.us-east-1.amazoncognito.com/oauth2/token` | Cognito token endpoint URL |
| `API_ENDPOINT` | `https://abc123.execute-api.us-east-1.amazonaws.com/api` | Platform API base URL |
| `TEST_SUITE_ID` | `01234567-89ab-cdef-0123-456789abcdef` | Test suite UUID from platform |

**Security Notes**:
- Context variables are encrypted and masked in logs
- Restrict context access to specific security groups
- Never commit secrets to your repository
- Use separate OAuth clients for different projects/environments

### Step 3: Alternative - Project Environment Variables

If you prefer project-specific variables instead of contexts:

1. Go to your project in CircleCI
2. Click **Project Settings** → **Environment Variables**
3. Click **Add Environment Variable**
4. Add the same variables as listed above

**Note**: Project variables are only available to that specific project, while context variables can be shared across multiple projects.

### Step 4: Create CircleCI Configuration

Create `.circleci/config.yml` in your repository root:

```yaml
version: 2.1

jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run QA Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --verbose

workflows:
  version: 2
  test:
    jobs:
      - qa-tests:
          context: nova-act-qa
          filters:
            branches:
              only:
                - main
                - develop
```

### Step 5: Commit and Push

Commit the configuration file and push to your repository:

```bash
git add .circleci/config.yml
git commit -m "Add CircleCI QA test automation"
git push origin main
```

CircleCI will automatically detect the configuration and run the workflow.

## Docker Executor Configuration

CircleCI requires `setup_remote_docker` to run Docker commands within jobs.

### Basic Docker Setup

The minimal Docker configuration:

```yaml
jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Tests
          command: docker run --rm nova-act-cicd-runner:latest --help
```

### Docker Layer Caching (DLC)

Enable Docker Layer Caching to speed up builds (requires Performance or Scale plan):

```yaml
jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
          docker_layer_caching: true
      - run:
          name: Run QA Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --verbose
```

### Custom Docker Registry

If using a private Docker registry:

```yaml
jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Docker Login
          command: |
            echo "${DOCKER_PASSWORD}" | docker login ${DOCKER_REGISTRY} \
              -u "${DOCKER_USERNAME}" --password-stdin
      - run:
          name: Run QA Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              ${DOCKER_REGISTRY}/nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --verbose
```

### Machine Executor (Alternative)

Use machine executor for direct Docker access without `setup_remote_docker`:

```yaml
jobs:
  qa-tests:
    machine:
      image: ubuntu-2204:2023.07.1
    steps:
      - run:
          name: Run QA Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --verbose
```

**Note**: Machine executor provides more resources but takes longer to start than Docker executor.

## Workflow Examples

### Example 1: Basic Workflow with Pull Requests

Run tests on pushes to main/develop and all pull requests:

```yaml
version: 2.1

jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run QA Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --verbose

workflows:
  version: 2
  test:
    jobs:
      - qa-tests:
          context: nova-act-qa
          filters:
            branches:
              only:
                - main
                - develop
```

### Example 2: Environment-Specific Testing

Test against staging environment with base URL override:

```yaml
version: 2.1

jobs:
  staging-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Staging Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --base-url ${STAGING_BASE_URL} \
              --verbose

workflows:
  version: 2
  test-staging:
    jobs:
      - staging-tests:
          context: nova-act-qa
          filters:
            branches:
              only:
                - develop
```

### Example 3: Variable Overrides

Override test variables for different test scenarios:

```yaml
version: 2.1

jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Tests with Variables
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --base-url ${STAGING_BASE_URL} \
              --var username=testuser \
              --var environment=staging \
              --var api_key=${TEST_API_KEY} \
              --verbose

workflows:
  version: 2
  test:
    jobs:
      - qa-tests:
          context: nova-act-qa
```

### Example 4: Scheduled Testing

Run tests on a schedule (e.g., nightly):

```yaml
version: 2.1

jobs:
  nightly-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Nightly Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --base-url ${PRODUCTION_BASE_URL} \
              --timeout 7200 \
              --verbose
      - run:
          name: Notify on Failure
          when: on_fail
          command: |
            echo "Nightly tests failed!"
            # Add notification logic here (Slack, email, etc.)

workflows:
  version: 2
  nightly:
    triggers:
      - schedule:
          cron: "0 2 * * *"  # Daily at 2 AM UTC
          filters:
            branches:
              only:
                - main
    jobs:
      - nightly-tests:
          context: nova-act-qa
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

**Common Schedules**:
- `0 2 * * *` - Daily at 2 AM UTC
- `0 */6 * * *` - Every 6 hours
- `0 0 * * 0` - Weekly on Sunday at midnight
- `0 0 1 * *` - Monthly on the 1st at midnight

### Example 5: Multiple Environments with Sequential Execution

Test against multiple environments sequentially:

```yaml
version: 2.1

jobs:
  test-staging:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Test Staging Environment
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --base-url ${STAGING_BASE_URL} \
              --var environment=staging \
              --verbose

  test-production:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Test Production Environment
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --base-url ${PRODUCTION_BASE_URL} \
              --var environment=production \
              --verbose

workflows:
  version: 2
  test-all-environments:
    jobs:
      - test-staging:
          context: nova-act-qa
      - test-production:
          context: nova-act-qa
          requires:
            - test-staging  # Only run if staging tests pass
          filters:
            branches:
              only:
                - main
```

### Example 6: Parallel Testing with Matrix Strategy

Test multiple configurations in parallel using matrix jobs:

```yaml
version: 2.1

jobs:
  qa-tests:
    parameters:
      environment:
        type: string
      region:
        type: string
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Tests - << parameters.environment >> (<< parameters.region >>)
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --base-url https://<< parameters.environment >>.example.com \
              --region << parameters.region >> \
              --var environment=<< parameters.environment >> \
              --verbose

workflows:
  version: 2
  matrix-tests:
    jobs:
      - qa-tests:
          name: test-staging-us-east-1
          context: nova-act-qa
          environment: staging
          region: us-east-1
      - qa-tests:
          name: test-staging-us-west-2
          context: nova-act-qa
          environment: staging
          region: us-west-2
      - qa-tests:
          name: test-production-us-east-1
          context: nova-act-qa
          environment: production
          region: us-east-1
      - qa-tests:
          name: test-production-us-west-2
          context: nova-act-qa
          environment: production
          region: us-west-2
```

### Example 7: Conditional Execution Based on Changes

Run different test suites based on changed files:

```yaml
version: 2.1

jobs:
  test-frontend:
    docker:
      - image: docker:latest
    steps:
      - checkout
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Check for Frontend Changes
          command: |
            if git diff --name-only HEAD~1 | grep -q "^frontend/"; then
              echo "Frontend changes detected"
            else
              echo "No frontend changes, skipping"
              circleci-agent step halt
            fi
      - run:
          name: Run Frontend Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${FRONTEND_SUITE_ID} \
              --verbose

  test-backend:
    docker:
      - image: docker:latest
    steps:
      - checkout
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Check for Backend Changes
          command: |
            if git diff --name-only HEAD~1 | grep -q "^backend/"; then
              echo "Backend changes detected"
            else
              echo "No backend changes, skipping"
              circleci-agent step halt
            fi
      - run:
          name: Run Backend Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${BACKEND_SUITE_ID} \
              --verbose

workflows:
  version: 2
  conditional-tests:
    jobs:
      - test-frontend:
          context: nova-act-qa
      - test-backend:
          context: nova-act-qa
```

### Example 8: Extended Timeout for Large Suites

Increase timeout for long-running test suites:

```yaml
version: 2.1

jobs:
  extended-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Extended Test Suite
          no_output_timeout: 3h  # CircleCI step timeout (3 hours)
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${EXTENDED_SUITE_ID} \
              --timeout 10800 \
              --verbose

workflows:
  version: 2
  extended-testing:
    jobs:
      - extended-tests:
          context: nova-act-qa
```

### Example 9: Multi-Stage Pipeline

Run smoke tests, then full tests, then deploy:

```yaml
version: 2.1

jobs:
  smoke-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Smoke Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${SMOKE_SUITE_ID} \
              --base-url ${STAGING_BASE_URL} \
              --verbose

  full-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Full Test Suite
          no_output_timeout: 2h
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${FULL_SUITE_ID} \
              --base-url ${STAGING_BASE_URL} \
              --timeout 7200 \
              --verbose

  deploy:
    docker:
      - image: cimg/base:stable
    steps:
      - run:
          name: Deploy to Production
          command: |
            echo "Deploying to production..."
            # Add deployment steps here

workflows:
  version: 2
  test-and-deploy:
    jobs:
      - smoke-tests:
          context: nova-act-qa
      - full-tests:
          context: nova-act-qa
          requires:
            - smoke-tests
      - deploy:
          requires:
            - full-tests
          filters:
            branches:
              only:
                - main
```

### Example 10: Approval Job for Production

Require manual approval before running production tests:

```yaml
version: 2.1

jobs:
  staging-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Staging Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --base-url ${STAGING_BASE_URL} \
              --verbose

  production-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Production Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --base-url ${PRODUCTION_BASE_URL} \
              --verbose

workflows:
  version: 2
  test-with-approval:
    jobs:
      - staging-tests:
          context: nova-act-qa
      - hold-for-approval:
          type: approval
          requires:
            - staging-tests
          filters:
            branches:
              only:
                - main
      - production-tests:
          context: nova-act-qa
          requires:
            - hold-for-approval
```

## Workflow Orchestration

CircleCI workflows provide powerful orchestration capabilities for complex testing scenarios.

### Sequential Jobs

Jobs run one after another:

```yaml
workflows:
  version: 2
  sequential:
    jobs:
      - job-a
      - job-b:
          requires:
            - job-a
      - job-c:
          requires:
            - job-b
```

### Parallel Jobs

Jobs run simultaneously:

```yaml
workflows:
  version: 2
  parallel:
    jobs:
      - job-a
      - job-b
      - job-c
```

### Fan-Out/Fan-In Pattern

Multiple jobs run in parallel, then converge:

```yaml
workflows:
  version: 2
  fan-out-fan-in:
    jobs:
      - smoke-tests
      - test-frontend:
          requires:
            - smoke-tests
      - test-backend:
          requires:
            - smoke-tests
      - test-api:
          requires:
            - smoke-tests
      - deploy:
          requires:
            - test-frontend
            - test-backend
            - test-api
```

### Branch Filtering

Run jobs only on specific branches:

```yaml
workflows:
  version: 2
  branch-specific:
    jobs:
      - qa-tests:
          filters:
            branches:
              only:
                - main
                - develop
                - /^release\/.*/  # Regex for release branches
      - production-tests:
          filters:
            branches:
              only:
                - main
              ignore:
                - develop
                - /^feature\/.*/
```

### Tag Filtering

Run jobs on Git tags:

```yaml
workflows:
  version: 2
  tag-based:
    jobs:
      - qa-tests:
          filters:
            tags:
              only:
                - /^v\d+\.\d+\.\d+$/  # Semantic version tags
            branches:
              ignore: /.*/  # Don't run on branches
```

### Combined Workflows

Multiple workflows in one configuration:

```yaml
version: 2.1

jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run QA Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --verbose

workflows:
  version: 2
  
  # Run on every commit
  commit-workflow:
    jobs:
      - qa-tests:
          context: nova-act-qa
          filters:
            branches:
              only:
                - main
                - develop
  
  # Run nightly
  nightly-workflow:
    triggers:
      - schedule:
          cron: "0 2 * * *"
          filters:
            branches:
              only:
                - main
    jobs:
      - qa-tests:
          context: nova-act-qa
```

## Exit Codes and Workflow Control

The runner uses exit codes to indicate test results, which CircleCI uses to determine job success or failure.

| Exit Code | Meaning | Workflow Behavior |
|-----------|---------|-------------------|
| `0` | All tests passed | Job succeeds, workflow continues |
| `1` | One or more tests failed | Job fails, workflow stops (unless configured otherwise) |
| `2` | Runner error (auth, config, API) | Job fails, workflow stops |

### Fail Job on Test Failure

Default behavior - job fails if tests fail:

```yaml
jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run QA Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --verbose
```

### Continue on Test Failure

Continue workflow even if tests fail:

```yaml
jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run QA Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --verbose || true
      - run:
          name: This step runs even if tests fail
          command: echo "Continuing despite test failure"
```

### Custom Handling Based on Exit Code

Handle different exit codes differently:

```yaml
jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run QA Tests
          command: |
            set +e  # Don't exit on error
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
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
      - run:
          name: Handle test failure
          when: on_fail
          command: |
            echo "Tests failed - creating notification"
            # Add notification logic here
```

### Conditional Deployment Based on Test Results

Deploy only if tests pass:

```yaml
version: 2.1

jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run QA Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --verbose

  deploy-production:
    docker:
      - image: cimg/base:stable
    steps:
      - run:
          name: Deploy to Production
          command: |
            echo "Deploying to production..."
            # Add deployment steps here

workflows:
  version: 2
  test-and-deploy:
    jobs:
      - qa-tests:
          context: nova-act-qa
      - deploy-production:
          requires:
            - qa-tests  # Only deploy if tests pass
          filters:
            branches:
              only:
                - main
```

## CircleCI Orbs (Advanced)

CircleCI Orbs are reusable configuration packages. You can create a custom orb for the runner.

### Custom Orb Example

**orb.yml**:
```yaml
version: 2.1

description: |
  Run Nova Act QA Studio test suites in CircleCI

commands:
  run-tests:
    description: Execute a test suite
    parameters:
      suite-id:
        type: string
        description: Test suite ID to execute
      base-url:
        type: string
        default: ""
        description: Base URL override (optional)
      timeout:
        type: integer
        default: 3600
        description: Test execution timeout in seconds
      verbose:
        type: boolean
        default: true
        description: Enable verbose logging
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run QA Tests
          command: |
            BASE_URL_ARG=""
            if [ -n "<< parameters.base-url >>" ]; then
              BASE_URL_ARG="--base-url << parameters.base-url >>"
            fi
            
            VERBOSE_ARG=""
            if [ "<< parameters.verbose >>" = "true" ]; then
              VERBOSE_ARG="--verbose"
            fi
            
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id << parameters.suite-id >> \
              ${BASE_URL_ARG} \
              --timeout << parameters.timeout >> \
              ${VERBOSE_ARG}

jobs:
  test:
    description: Run QA tests in a Docker executor
    parameters:
      suite-id:
        type: string
        description: Test suite ID to execute
      base-url:
        type: string
        default: ""
        description: Base URL override (optional)
      timeout:
        type: integer
        default: 3600
        description: Test execution timeout in seconds
    docker:
      - image: docker:latest
    steps:
      - run-tests:
          suite-id: << parameters.suite-id >>
          base-url: << parameters.base-url >>
          timeout: << parameters.timeout >>
```

### Using the Custom Orb

```yaml
version: 2.1

orbs:
  nova-act: your-org/nova-act-qa@1.0.0

workflows:
  version: 2
  test:
    jobs:
      - nova-act/test:
          context: nova-act-qa
          suite-id: "suite-123"
          base-url: "https://staging.example.com"
```

## Best Practices

### Security

1. **Use Contexts**: Store OAuth credentials in CircleCI contexts for secure sharing across projects
2. **Restrict Context Access**: Limit context access to specific security groups
3. **Separate OAuth Clients**: Use different OAuth clients for different projects/environments
4. **Minimal Scopes**: Grant only required scopes to OAuth clients
5. **Rotate Credentials**: Rotate OAuth client secrets regularly (every 90 days)
6. **Never Commit Secrets**: Never commit secrets to `.circleci/config.yml` or repository

### Performance

1. **Docker Layer Caching**: Enable DLC to speed up Docker builds (requires paid plan)
2. **Parallel Execution**: Use parallel jobs to test multiple configurations simultaneously
3. **Resource Classes**: Use appropriate resource classes for your workload
4. **Conditional Execution**: Use branch/path filters to run tests only when needed
5. **Workflow Optimization**: Structure workflows to fail fast on critical tests

### Reliability

1. **Timeout Configuration**: Set appropriate timeouts for large test suites
2. **Verbose Logging**: Use `--verbose` flag for troubleshooting
3. **Health Checks**: Add smoke tests before running full test suites
4. **Notifications**: Set up notifications for workflow failures (Slack, email, etc.)
5. **Approval Jobs**: Use approval jobs for production deployments

### Organization

1. **Descriptive Names**: Use clear job and workflow names
2. **Comments**: Add comments to explain complex configuration logic
3. **Reusable Commands**: Use CircleCI commands for repeated steps
4. **Orbs**: Create custom orbs for common patterns
5. **Workflow Visualization**: Structure workflows logically for clear visualization

### Example: Well-Organized Configuration

```yaml
version: 2.1

# Reusable commands
commands:
  run-qa-tests:
    description: Execute QA test suite
    parameters:
      suite-id:
        type: string
      base-url:
        type: string
        default: ""
      environment:
        type: string
        default: "staging"
    steps:
      - setup_remote_docker:
          version: 20.10.14
          docker_layer_caching: true
      - run:
          name: Run QA Tests - << parameters.environment >>
          command: |
            BASE_URL_ARG=""
            if [ -n "<< parameters.base-url >>" ]; then
              BASE_URL_ARG="--base-url << parameters.base-url >>"
            fi
            
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id << parameters.suite-id >> \
              ${BASE_URL_ARG} \
              --var environment=<< parameters.environment >> \
              --verbose

# Jobs
jobs:
  smoke-tests:
    docker:
      - image: docker:latest
    steps:
      - run-qa-tests:
          suite-id: ${SMOKE_SUITE_ID}
          base-url: ${STAGING_BASE_URL}
          environment: staging

  full-tests:
    docker:
      - image: docker:latest
    resource_class: large  # Use larger resource for long-running tests
    steps:
      - run-qa-tests:
          suite-id: ${FULL_SUITE_ID}
          base-url: ${STAGING_BASE_URL}
          environment: staging
      - run:
          name: Notify on Failure
          when: on_fail
          command: |
            echo "Full tests failed!"
            # Add notification logic

  production-tests:
    docker:
      - image: docker:latest
    steps:
      - run-qa-tests:
          suite-id: ${FULL_SUITE_ID}
          base-url: ${PRODUCTION_BASE_URL}
          environment: production

# Workflows
workflows:
  version: 2
  
  # Run on every commit to main/develop
  continuous-testing:
    jobs:
      - smoke-tests:
          context: nova-act-qa
          filters:
            branches:
              only:
                - main
                - develop
      - full-tests:
          context: nova-act-qa
          requires:
            - smoke-tests
          filters:
            branches:
              only:
                - main
                - develop
  
  # Nightly production tests
  nightly-production:
    triggers:
      - schedule:
          cron: "0 2 * * *"
          filters:
            branches:
              only:
                - main
    jobs:
      - production-tests:
          context: nova-act-qa
```

## Troubleshooting

### Workflow Not Triggering

**Problem**: Workflow doesn't run on push or pull request

**Solutions**:
1. Verify `.circleci/config.yml` is in repository root
2. Check YAML syntax is valid (use CircleCI config validator)
3. Ensure branch names match workflow filters
4. Check project is set up in CircleCI web app
5. Verify CircleCI has access to your repository

### Authentication Failures

**Problem**: `OAuth authentication failed: 401`

**Solutions**:
1. Verify environment variables are set correctly in context or project settings
2. Check OAuth client exists and is active in platform
3. Ensure OAuth client has required scopes (`api/suite.read`, `api/suite.write`, `api/execution.write`)
4. Verify token endpoint URL is correct
5. Check if context is properly attached to job in workflow

### Docker Setup Issues

**Problem**: `Cannot connect to the Docker daemon` or `setup_remote_docker` fails

**Solutions**:
1. Ensure `setup_remote_docker` step is included before Docker commands
2. Verify Docker executor version is specified
3. Check if using machine executor instead (doesn't need `setup_remote_docker`)
4. Verify CircleCI plan supports Docker (Free plan has limitations)
5. Try different Docker executor version

### Docker Pull Failures

**Problem**: `Unable to find image 'nova-act-cicd-runner:latest'`

**Solutions**:
1. Ensure Docker image is available in registry
2. Add authentication if using private registry
3. Specify full image path including registry URL
4. Check network connectivity from CircleCI runners

### Test Timeouts

**Problem**: Tests timeout before completion

**Solutions**:
1. Increase runner timeout: `--timeout 7200`
2. Increase CircleCI step timeout: `no_output_timeout: 3h`
3. Split large test suites into smaller suites
4. Run tests in parallel using multiple jobs
5. Use larger resource class for the job

### Context Not Available

**Problem**: Environment variables from context are empty or undefined

**Solutions**:
1. Verify context is attached to job in workflow: `context: nova-act-qa`
2. Check context name matches exactly (case-sensitive)
3. Ensure user/team has access to the context
4. Verify variables are set in the context (Organization Settings → Contexts)
5. Check if using project variables instead of context

### Resource Class Issues

**Problem**: Job fails with resource constraints or OOM errors

**Solutions**:
1. Increase resource class: `resource_class: large` or `resource_class: xlarge`
2. Reduce test suite size
3. Run tests sequentially instead of parallel
4. Use machine executor for more resources
5. Check CircleCI plan supports requested resource class

### Scheduled Workflow Not Running

**Problem**: Scheduled workflow doesn't trigger at expected time

**Solutions**:
1. Verify cron syntax is correct
2. Check timezone (CircleCI uses UTC)
3. Ensure branch filter matches existing branch
4. Verify workflow is enabled in CircleCI web app
5. Check CircleCI status page for service issues

## Advanced Patterns

### Dynamic Configuration

Use CircleCI's dynamic configuration feature to generate workflows based on changed files:

**Enable Dynamic Configuration**:
1. Go to Project Settings → Advanced
2. Enable "Enable dynamic config using setup workflows"

**.circleci/config.yml**:
```yaml
version: 2.1

setup: true

orbs:
  continuation: circleci/continuation@0.3.1

jobs:
  setup:
    docker:
      - image: cimg/base:stable
    steps:
      - checkout
      - run:
          name: Generate Dynamic Config
          command: |
            # Detect changes and generate appropriate config
            if git diff --name-only HEAD~1 | grep -q "^frontend/"; then
              echo "Frontend changes detected"
              cp .circleci/frontend-config.yml /tmp/generated-config.yml
            elif git diff --name-only HEAD~1 | grep -q "^backend/"; then
              echo "Backend changes detected"
              cp .circleci/backend-config.yml /tmp/generated-config.yml
            else
              echo "No specific changes, running all tests"
              cp .circleci/full-config.yml /tmp/generated-config.yml
            fi
      - continuation/continue:
          configuration_path: /tmp/generated-config.yml

workflows:
  setup-workflow:
    jobs:
      - setup
```

### Workspace Persistence

Share data between jobs using workspaces:

```yaml
version: 2.1

jobs:
  generate-test-data:
    docker:
      - image: cimg/base:stable
    steps:
      - run:
          name: Generate Test Data
          command: |
            mkdir -p /tmp/test-data
            echo "test-suite-123" > /tmp/test-data/suite-id.txt
      - persist_to_workspace:
          root: /tmp/test-data
          paths:
            - suite-id.txt

  run-tests:
    docker:
      - image: docker:latest
    steps:
      - attach_workspace:
          at: /tmp/test-data
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Tests with Generated Data
          command: |
            SUITE_ID=$(cat /tmp/test-data/suite-id.txt)
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${SUITE_ID} \
              --verbose

workflows:
  version: 2
  test-with-workspace:
    jobs:
      - generate-test-data
      - run-tests:
          requires:
            - generate-test-data
```

### Artifact Storage

Store test artifacts for later review:

```yaml
version: 2.1

jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run QA Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              -v /tmp/artifacts:/artifacts \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --verbose
      - store_artifacts:
          path: /tmp/artifacts
          destination: test-artifacts
      - store_test_results:
          path: /tmp/artifacts/test-results
```

### Pipeline Parameters

Use pipeline parameters for flexible workflow execution:

```yaml
version: 2.1

parameters:
  run-integration-tests:
    type: boolean
    default: false
  environment:
    type: string
    default: "staging"

jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run QA Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --var environment=<< pipeline.parameters.environment >> \
              --verbose

  integration-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Integration Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${INTEGRATION_SUITE_ID} \
              --verbose

workflows:
  version: 2
  test:
    jobs:
      - qa-tests:
          context: nova-act-qa
      - integration-tests:
          context: nova-act-qa
          when: << pipeline.parameters.run-integration-tests >>
```

**Trigger with parameters**:
```bash
curl -X POST \
  https://circleci.com/api/v2/project/gh/your-org/your-repo/pipeline \
  -H "Circle-Token: ${CIRCLECI_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "run-integration-tests": true,
      "environment": "production"
    }
  }'
```

### Slack Notifications

Send Slack notifications on test failures:

```yaml
version: 2.1

orbs:
  slack: circleci/slack@4.12.0

jobs:
  qa-tests:
    docker:
      - image: docker:latest
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run QA Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${TEST_SUITE_ID} \
              --verbose
      - slack/notify:
          event: fail
          template: basic_fail_1
      - slack/notify:
          event: pass
          template: success_tagged_deploy_1

workflows:
  version: 2
  test-with-notifications:
    jobs:
      - qa-tests:
          context:
            - nova-act-qa
            - slack-secrets
```

### Resource Class Configuration

Choose appropriate resource classes for different test types:

```yaml
version: 2.1

jobs:
  smoke-tests:
    docker:
      - image: docker:latest
    resource_class: medium  # Default, good for quick tests
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Smoke Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${SMOKE_SUITE_ID} \
              --verbose

  full-tests:
    docker:
      - image: docker:latest
    resource_class: large  # More CPU/RAM for intensive tests
    steps:
      - setup_remote_docker:
          version: 20.10.14
      - run:
          name: Run Full Test Suite
          no_output_timeout: 2h
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${FULL_SUITE_ID} \
              --timeout 7200 \
              --verbose

  performance-tests:
    machine:
      image: ubuntu-2204:2023.07.1
    resource_class: large  # Machine executor with more resources
    steps:
      - run:
          name: Run Performance Tests
          command: |
            docker run --rm \
              -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
              -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
              -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
              -e API_ENDPOINT="${API_ENDPOINT}" \
              nova-act-cicd-runner:latest \
              --suite-id ${PERFORMANCE_SUITE_ID} \
              --verbose
```

**Available Resource Classes**:
- `small`: 1 vCPU, 2GB RAM
- `medium`: 2 vCPU, 4GB RAM (default)
- `medium+`: 3 vCPU, 6GB RAM
- `large`: 4 vCPU, 8GB RAM
- `xlarge`: 8 vCPU, 16GB RAM
- `2xlarge`: 16 vCPU, 32GB RAM (requires Performance plan)

## Related Documentation

- [Configuration Reference](../configuration.md) - Environment variables and CLI arguments
- [CLI Reference](../cli-reference.md) - Detailed CLI usage
- [Troubleshooting Guide](../troubleshooting.md) - Common errors and solutions
- [Best Practices](../best-practices.md) - Security and optimization guidance
- [API Reference](../api-reference.md) - API documentation for advanced integration

## Support

For CircleCI integration assistance:

1. Check the [CircleCI documentation](https://circleci.com/docs/)
2. Review [Troubleshooting Guide](../troubleshooting.md)
3. Enable verbose logging (`--verbose`) for detailed diagnostics
4. Check [CircleCI Community Forum](https://discuss.circleci.com/)
5. Contact your platform administrator

## Additional Resources

- [CircleCI Configuration Reference](https://circleci.com/docs/configuration-reference/)
- [CircleCI Orbs Registry](https://circleci.com/developer/orbs)
- [CircleCI Docker Executor](https://circleci.com/docs/executor-intro/#docker)
- [CircleCI Workflows](https://circleci.com/docs/workflows/)
- [CircleCI Contexts](https://circleci.com/docs/contexts/)
- [CircleCI Dynamic Configuration](https://circleci.com/docs/dynamic-config/)
