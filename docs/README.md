# Nova Act QA Studio - CI/CD Runner

Execute Nova Act QA Studio test suites in your CI/CD pipelines with OAuth authentication, parallel execution, and comprehensive artifact capture.

## Features

🚀 **Execute test suites** from any CI/CD platform  
🔐 **OAuth client credentials** authentication  
🎯 **Parallel test execution** for faster feedback  
🌍 **Environment-specific testing** with base URL override  
📊 **Comprehensive execution summary** with detailed reporting  
🎬 **Automatic artifact capture** (videos, logs, traces, screenshots)  
✅ **Exit code-based workflow control** for CI/CD integration  
🔄 **Variable overrides** for flexible test configuration  
⚙️ **Region and model overrides** for AWS Bedrock customization

## Quick Start

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="your-client-id" \
  -e OAUTH_CLIENT_SECRET="your-client-secret" \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.region.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://api.example.com" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --base-url https://staging.example.com \
  --verbose
```

## Documentation

### Getting Started

- [Installation Guide](installation.md) - Prerequisites, OAuth setup, and container installation
- [Configuration Reference](configuration.md) - Environment variables and CLI arguments
- [CLI Reference](cli-reference.md) - Detailed CLI usage and examples

### CI/CD Integration

Platform-specific integration guides with complete examples:

- [GitHub Actions](ci-cd-integration/github-actions.md) - Workflow configuration and secrets setup
- [GitLab CI](ci-cd-integration/gitlab-ci.md) - Pipeline configuration with Docker-in-Docker
- [Jenkins](ci-cd-integration/jenkins.md) - Declarative pipeline with credentials
- [CircleCI](ci-cd-integration/circleci.md) - Configuration with contexts
- [Generic Docker](ci-cd-integration/generic-docker.md) - Platform-agnostic Docker usage

### Reference

- [API Reference](api-reference.md) - Complete API documentation with examples
- [Architecture Overview](architecture.md) - System design and data flows
- [Troubleshooting Guide](troubleshooting.md) - Common errors and solutions
- [Best Practices](best-practices.md) - Security, performance, and organizational guidance

## Installation

### Prerequisites

**Docker Installation (Recommended)**:
- Docker installed and running
- OAuth client credentials from Nova Act QA Studio platform
- Network access to API endpoint and Cognito

**Direct Installation (Alternative)**:
- Python 3.9 or later
- pip (Python package manager)
- OAuth client credentials from Nova Act QA Studio platform
- Network access to API endpoint and Cognito

### Quick Setup

**With Docker**:
1. Create an OAuth client in the Nova Act QA Studio web interface
2. Save the client ID and secret
3. Set environment variables
4. Run the Docker container

**Without Docker**:
1. Create an OAuth client in the Nova Act QA Studio web interface
2. Clone the repository and navigate to `cicd-runner/`
3. Create a virtual environment: `python3 -m venv venv`
4. Activate it: `source venv/bin/activate`
5. Install: `pip install -e .`
6. Configure environment variables in `.env` file
7. Run: `cicd-runner --suite-id YOUR_SUITE_ID`

See the [Installation Guide](installation.md) for detailed instructions for both methods.

## Usage Examples

### Basic Execution

Execute a test suite with minimal configuration:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="7abc123def456" \
  -e OAUTH_CLIENT_SECRET="secret_xyz789..." \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://api.example.com" \
  nova-act-cicd-runner:latest \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef
```

### With Environment Override

Test against a specific environment:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="7abc123def456" \
  -e OAUTH_CLIENT_SECRET="secret_xyz789..." \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://api.example.com" \
  nova-act-cicd-runner:latest \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com
```

### With Variable Overrides

Override test variables for different scenarios:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="7abc123def456" \
  -e OAUTH_CLIENT_SECRET="secret_xyz789..." \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://api.example.com" \
  nova-act-cicd-runner:latest \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --var username=testuser \
  --var password=testpass \
  --var environment=staging
```

### Complete Example

All options combined:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="7abc123def456" \
  -e OAUTH_CLIENT_SECRET="secret_xyz789..." \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://api.example.com" \
  -e LOG_LEVEL="DEBUG" \
  nova-act-cicd-runner:latest \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com \
  --var username=testuser \
  --var password=testpass \
  --region us-west-2 \
  --model-id anthropic.claude-3-5-sonnet-20240620-v1:0 \
  --timeout 7200 \
  --verbose
```

## Exit Codes

The runner uses exit codes to control CI/CD workflow behavior:

- `0` - Success: All tests passed
- `1` - Test failures: One or more tests failed
- `2` - Error: Authentication, configuration, or API error

Use these exit codes in your CI/CD pipeline to determine workflow outcomes.

## Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OAUTH_CLIENT_ID` | OAuth client ID from platform | `7abc123def456` |
| `OAUTH_CLIENT_SECRET` | OAuth client secret | `secret_xyz789...` |
| `OAUTH_TOKEN_ENDPOINT` | Cognito token endpoint URL | `https://domain.auth.us-east-1.amazoncognito.com/oauth2/token` |
| `API_ENDPOINT` | Platform API base URL | `https://api.example.com` |

### Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |

### CLI Arguments

| Option | Required | Description | Default |
|--------|----------|-------------|---------|
| `--suite-id` | Yes | Test suite UUID to execute | - |
| `--base-url` | No | Override base URL for all use cases | - |
| `--var` | No | Override variable (key=value, repeatable) | - |
| `--region` | No | Override AWS region for browser | - |
| `--model-id` | No | Override Nova Act model ID | - |
| `--verbose` | No | Enable verbose logging (DEBUG level) | False |
| `--timeout` | No | Global timeout in seconds | 3600 |

See the [Configuration Reference](configuration.md) for complete details.

## Troubleshooting

### Common Issues

**Authentication Failed**
- Verify OAuth client ID and secret are correct
- Check token endpoint URL format
- Ensure OAuth client has required scopes

**Test Suite Not Found**
- Verify suite ID is correct
- Check suite exists in platform UI
- Verify OAuth client has `api/suite.read` scope

**Execution Timeout**
- Increase timeout with `--timeout` option
- Split large test suites into smaller suites
- Check network connectivity

See the [Troubleshooting Guide](troubleshooting.md) for detailed solutions.

## Security Best Practices

- Never commit OAuth credentials to version control
- Use CI/CD secret management for credentials
- Rotate OAuth client secrets regularly
- Use least-privilege scopes for OAuth clients
- Review CloudWatch logs for suspicious activity

See the [Best Practices Guide](best-practices.md) for comprehensive security guidance.

## Support

- **GitHub Issues**: [Report issues](https://github.com/aws-samples/sample-nova-act-qa-studio/issues)
- **Documentation**: [Full documentation](https://github.com/aws-samples/sample-nova-act-qa-studio)
- **API Reference**: [API documentation](api-reference.md)

## License

This project is licensed under the MIT-0 License. See the LICENSE file for details.
