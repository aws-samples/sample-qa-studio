# Work Package 6: Documentation

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP6 - Documentation
- **Estimated Duration**: 3 days
- **Dependencies**: WP5 (Docker Container)
- **Status**: Not Started

---

## Overview

Create comprehensive user documentation for the CI/CD runner, including installation guide, configuration reference, CLI usage, CI/CD platform integration examples, troubleshooting guide, and best practices.

---

## User Stories

### US1: As a DevOps engineer, I need installation instructions
**Acceptance Criteria**:
- Clear step-by-step installation guide
- Prerequisites listed
- Docker installation verified
- OAuth client setup documented
- Environment variable configuration explained

### US2: As a CI/CD user, I need integration examples for my platform
**Acceptance Criteria**:
- GitHub Actions example provided
- GitLab CI example provided
- Jenkins example provided
- CircleCI example provided
- Generic Docker example provided

### US3: As a user, I need a troubleshooting guide
**Acceptance Criteria**:
- Common errors documented
- Solutions provided for each error
- Debug mode instructions
- Log interpretation guide
- Support contact information

### US4: As a developer, I need API documentation
**Acceptance Criteria**:
- All endpoints documented
- Request/response examples provided
- Authentication flow explained
- Error codes documented
- Rate limits documented

---

## Documentation Structure

```
docs/
├── README.md                    # Main documentation
├── installation.md              # Installation guide
├── configuration.md             # Configuration reference
├── cli-reference.md             # CLI arguments and options
├── ci-cd-integration/
│   ├── github-actions.md        # GitHub Actions integration
│   ├── gitlab-ci.md             # GitLab CI integration
│   ├── jenkins.md               # Jenkins integration
│   ├── circleci.md              # CircleCI integration
│   └── generic-docker.md        # Generic Docker usage
├── troubleshooting.md           # Troubleshooting guide
├── best-practices.md            # Best practices
├── api-reference.md             # API documentation
└── architecture.md              # Architecture overview
```

---

## Documentation Content

### 1. README.md

**Sections**:
- Overview
- Features
- Quick Start
- Installation
- Usage
- CI/CD Integration
- Configuration
- Troubleshooting
- Contributing
- License

**Example**:
```markdown
# Nova Act QA Studio - CI/CD Runner

Execute Nova Act QA Studio test suites in your CI/CD pipelines.

## Features

- 🚀 Execute test suites from any CI/CD platform
- 🔐 OAuth client credentials authentication
- 🎯 Parallel test execution
- 🌍 Environment-specific testing (base URL override)
- 📊 Comprehensive execution summary
- 🎬 Automatic artifact capture (videos, logs, traces)
- ✅ Exit code-based workflow control

## Quick Start

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="your-client-id" \
  -e OAUTH_CLIENT_SECRET="your-client-secret" \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.region.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://api.example.com" \
  nova-act-qa-studio-ci-runner:latest \
  --suite-id suite-123 \
  --base-url https://staging.example.com \
  --verbose
```

## Installation

See [Installation Guide](docs/installation.md)

## CI/CD Integration

- [GitHub Actions](docs/ci-cd-integration/github-actions.md)
- [GitLab CI](docs/ci-cd-integration/gitlab-ci.md)
- [Jenkins](docs/ci-cd-integration/jenkins.md)
- [CircleCI](docs/ci-cd-integration/circleci.md)

## Configuration

See [Configuration Reference](docs/configuration.md)

## Troubleshooting

See [Troubleshooting Guide](docs/troubleshooting.md)
```

### 2. installation.md

**Content**:
- Prerequisites (Docker, OAuth client)
- OAuth client creation steps
- Environment variable setup
- Container pull/build instructions
- Verification steps

### 3. configuration.md

**Content**:
- Environment variables reference
- CLI arguments reference
- OAuth configuration
- API endpoint configuration
- Timeout configuration
- Logging configuration

**Example**:
```markdown
# Configuration Reference

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `OAUTH_CLIENT_ID` | OAuth client ID from platform | `7abc123def456` |
| `OAUTH_CLIENT_SECRET` | OAuth client secret | `secret_xyz789...` |
| `OAUTH_TOKEN_ENDPOINT` | Cognito token endpoint URL | `https://domain.auth.us-east-1.amazoncognito.com/oauth2/token` |
| `API_ENDPOINT` | Platform API base URL | `https://api.example.com` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |

## CLI Arguments

### Required

- `--suite-id <id>` - Test suite ID to execute

### Optional

- `--base-url <url>` - Override base URL for all use cases
- `--var <key>=<value>` - Override variable (repeatable)
- `--region <region>` - Override AWS region
- `--model-id <id>` - Override Nova Act model ID
- `--verbose` - Enable verbose logging
- `--timeout <seconds>` - Global timeout (default: 3600)
- `--help` - Show help message
```

### 4. CI/CD Integration Examples

#### GitHub Actions

**File**: `docs/ci-cd-integration/github-actions.md`

```markdown
# GitHub Actions Integration

## Example Workflow

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
            nova-act-qa-studio-ci-runner:latest \
            --suite-id ${{ vars.TEST_SUITE_ID }} \
            --base-url https://staging.example.com \
            --var username=testuser \
            --verbose
      
      - name: Check test results
        if: failure()
        run: echo "Tests failed!"
```

## Setup

1. Go to repository Settings → Secrets and variables → Actions
2. Add secrets:
   - `OAUTH_CLIENT_ID`
   - `OAUTH_CLIENT_SECRET`
   - `OAUTH_TOKEN_ENDPOINT`
   - `API_ENDPOINT`
3. Add variables:
   - `TEST_SUITE_ID`
4. Commit workflow file to `.github/workflows/qa-tests.yml`
```

#### GitLab CI

**File**: `docs/ci-cd-integration/gitlab-ci.md`

```markdown
# GitLab CI Integration

## Example Pipeline

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
        nova-act-qa-studio-ci-runner:latest
        --suite-id $TEST_SUITE_ID
        --base-url https://staging.example.com
        --verbose
  only:
    - main
    - merge_requests
```

## Setup

1. Go to Settings → CI/CD → Variables
2. Add masked variables:
   - `OAUTH_CLIENT_ID`
   - `OAUTH_CLIENT_SECRET`
   - `OAUTH_TOKEN_ENDPOINT`
   - `API_ENDPOINT`
   - `TEST_SUITE_ID`
3. Commit `.gitlab-ci.yml` to repository root
```

#### Jenkins

**File**: `docs/ci-cd-integration/jenkins.md`

```markdown
# Jenkins Integration

## Example Pipeline

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                script {
                    def exitCode = sh(
                        script: """
                            docker run --rm \
                                -e OAUTH_CLIENT_ID="\${OAUTH_CLIENT_ID}" \
                                -e OAUTH_CLIENT_SECRET="\${OAUTH_CLIENT_SECRET}" \
                                -e OAUTH_TOKEN_ENDPOINT="\${OAUTH_TOKEN_ENDPOINT}" \
                                -e API_ENDPOINT="\${API_ENDPOINT}" \
                                nova-act-qa-studio-ci-runner:latest \
                                --suite-id \${TEST_SUITE_ID} \
                                --base-url https://staging.example.com \
                                --verbose
                        """,
                        returnStatus: true
                    )
                    
                    if (exitCode != 0) {
                        error("QA tests failed with exit code ${exitCode}")
                    }
                }
            }
        }
    }
}
```

## Setup

1. Install Docker plugin in Jenkins
2. Add credentials in Jenkins:
   - `oauth-client-id` (Secret text)
   - `oauth-client-secret` (Secret text)
   - `oauth-token-endpoint` (Secret text)
   - `api-endpoint` (Secret text)
3. Create new Pipeline job
4. Configure pipeline from SCM or paste script
```

### 5. troubleshooting.md

**Content**:
```markdown
# Troubleshooting Guide

## Common Errors

### Authentication Failed

**Error**: `OAuth authentication failed: 401`

**Causes**:
- Invalid client ID or secret
- Expired credentials
- Incorrect token endpoint

**Solutions**:
1. Verify `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET` are correct
2. Check token endpoint URL format
3. Regenerate OAuth client credentials
4. Verify OAuth client has required scopes

### Test Suite Not Found

**Error**: `API request failed: 404 - Test suite not found`

**Causes**:
- Invalid suite ID
- Suite deleted
- Insufficient permissions

**Solutions**:
1. Verify suite ID is correct
2. Check suite exists in platform UI
3. Verify OAuth client has `api/suite.read` scope

### Execution Timeout

**Error**: `Execution timed out after 3600 seconds`

**Causes**:
- Test suite too large
- Slow network
- Browser issues

**Solutions**:
1. Increase timeout: `--timeout 7200`
2. Split test suite into smaller suites
3. Check network connectivity
4. Review test steps for inefficiencies

### Container Out of Memory

**Error**: `Container killed (OOMKilled)`

**Causes**:
- Too many parallel executions
- Insufficient container memory
- Memory leak

**Solutions**:
1. Increase container memory limit
2. Reduce test suite size
3. Run tests sequentially (future feature)

## Debug Mode

Enable verbose logging:

```bash
docker run --rm \
  -e LOG_LEVEL=DEBUG \
  ... \
  --verbose
```

## Getting Help

- GitHub Issues: https://github.com/org/repo/issues
- Email: support@example.com
- Slack: #qa-studio-support
```

### 6. best-practices.md

**Content**:
- Test suite organization
- Variable management
- Secret handling
- Artifact retention
- Performance optimization
- Security best practices

---

## API Documentation

### api-reference.md

**Content**:
- Authentication flow
- Endpoint reference
- Request/response examples
- Error codes
- Rate limits
- Pagination

---

## Testing Requirements

### Documentation Tests
- All links work
- Code examples are valid
- Commands execute successfully
- Screenshots are up-to-date
- Spelling and grammar checked

---

## Success Criteria

- [ ] README.md created with overview
- [ ] Installation guide complete
- [ ] Configuration reference complete
- [ ] CLI reference complete
- [ ] CI/CD integration examples for 4+ platforms
- [ ] Troubleshooting guide with common errors
- [ ] Best practices documented
- [ ] API reference complete
- [ ] All code examples tested
- [ ] Documentation reviewed for clarity
