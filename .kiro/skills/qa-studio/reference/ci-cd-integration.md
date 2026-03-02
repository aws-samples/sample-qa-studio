# CI/CD Integration

## Overview

Integrate QA Studio tests into CI/CD pipelines using machine-to-machine (M2M) authentication.

---

## Prerequisites

### 1. Create OAuth Client

In QA Studio web interface (admin only):
1. Navigate to **Settings** → **OAuth Clients**
2. Click **Create OAuth Client**
3. Enter name and description
4. Select scopes: `api/usecases.read`, `api/usecases.write`, `api/test-suites.read`, `api/test-suites.write`
5. Save and copy credentials (client ID and secret)

### 2. Store Credentials as Secrets

Store in your CI/CD platform's secret management:
- `OAUTH_CLIENT_ID`
- `OAUTH_CLIENT_SECRET`
- `OAUTH_TOKEN_ENDPOINT` (e.g., `https://your-domain.auth.us-east-1.amazoncognito.com/oauth2/token`)
- `API_ENDPOINT` (e.g., `https://your-api-id.execute-api.us-east-1.amazonaws.com/api`)
- `AWS_ACCESS_KEY_ID` (for Nova Act)
- `AWS_SECRET_ACCESS_KEY` (for Nova Act)

---

## GitHub Actions

```yaml
name: QA Studio Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  qa-tests:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install QA Studio CLI
        run: pip install qa-studio[runner]

      - name: Run Test Suite
        env:
          OAUTH_CLIENT_ID: ${{ secrets.OAUTH_CLIENT_ID }}
          OAUTH_CLIENT_SECRET: ${{ secrets.OAUTH_CLIENT_SECRET }}
          OAUTH_TOKEN_ENDPOINT: ${{ secrets.OAUTH_TOKEN_ENDPOINT }}
          API_ENDPOINT: ${{ secrets.API_ENDPOINT }}
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        run: |
          qa-studio run --suite-id ${{ vars.SUITE_ID }} \
            --base-url https://staging.example.com \
            --var environment=staging
```

---

## GitLab CI

```yaml
# .gitlab-ci.yml
qa-tests:
  stage: test
  image: python:3.12-slim
  variables:
    SUITE_ID: "abc12345-def6-7890-ghij-klmnopqrstuv"
  before_script:
    - pip install qa-studio[runner]
  script:
    - |
      qa-studio run --suite-id $SUITE_ID \
        --base-url https://staging.example.com \
        --var environment=staging
  only:
    - main
    - merge_requests
```

Store credentials as [CI/CD variables](https://docs.gitlab.com/ee/ci/variables/) with **Masked** flag enabled.

---

## Jenkins

```groovy
// Jenkinsfile
pipeline {
    agent any
    parameters {
        string(name: 'SUITE_ID', defaultValue: 'abc12345-def6-7890-ghij-klmnopqrstuv', description: 'Test suite ID')
        string(name: 'BASE_URL', defaultValue: 'https://staging.example.com', description: 'Base URL')
    }
    stages {
        stage('Setup') {
            steps {
                sh 'pip install qa-studio[runner]'
            }
        }
        stage('Run QA Tests') {
            steps {
                withCredentials([
                    string(credentialsId: 'oauth-client-id', variable: 'OAUTH_CLIENT_ID'),
                    string(credentialsId: 'oauth-client-secret', variable: 'OAUTH_CLIENT_SECRET'),
                    string(credentialsId: 'oauth-token-endpoint', variable: 'OAUTH_TOKEN_ENDPOINT'),
                    string(credentialsId: 'api-endpoint', variable: 'API_ENDPOINT'),
                    string(credentialsId: 'aws-access-key-id', variable: 'AWS_ACCESS_KEY_ID'),
                    string(credentialsId: 'aws-secret-access-key', variable: 'AWS_SECRET_ACCESS_KEY')
                ]) {
                    sh """
                        qa-studio run --suite-id ${params.SUITE_ID} \
                          --base-url ${params.BASE_URL} \
                          --var environment=staging
                    """
                }
            }
        }
    }
}
```

---

## Docker Execution

### Build Image

```bash
cd qa-studio-cli
docker build -t qa-studio-runner .
```

### Run in CI/CD

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID" \
  -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
  -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT" \
  -e API_ENDPOINT="$API_ENDPOINT" \
  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  qa-studio-runner \
    --suite-id abc12345 \
    --base-url https://staging.example.com
```

---

## Best Practices

1. **Use suite IDs, not individual test IDs** - Easier to manage and update
2. **Store credentials as secrets** - Never commit credentials to version control
3. **Use environment-specific variables** - Override base URLs and variables per environment
4. **Set appropriate timeouts** - Long-running suites may need `--timeout` increased
5. **Review artifacts on failure** - Use `--keep-artifacts` for debugging
6. **Use exit codes** - CI/CD platforms use exit codes to determine success/failure

---

## Troubleshooting

### Authentication Failure

**Error:**
```
AuthenticationError: OAuth authentication failed: 401
```

**Fix:**
1. Verify OAuth client credentials are correct
2. Check client has required scopes
3. Verify token endpoint URL is correct

### AWS Credentials Missing

**Error:**
```
RunnerError: No valid AWS session found
```

**Fix:**
1. Verify `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are set
2. Check credentials have Bedrock access permissions

### Suite Not Found

**Error:**
```
APIError: Test suite not found
```

**Fix:**
1. Verify suite ID is correct
2. Check OAuth client has `api/test-suites.read` scope

---

## Next Steps

- **Create test suites:** [📦 Test Suites](./test-suites.md)
- **Run tests locally first:** [▶️ Local Execution](./local-execution.md)
- **Troubleshoot issues:** [🔧 Troubleshooting](./troubleshooting.md)
