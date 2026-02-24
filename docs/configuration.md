# Configuration Reference

This document provides a complete reference for all configuration options available in the Nova Act QA Studio CI/CD Runner. Configuration is provided through environment variables and CLI arguments.

## Configuration Overview

The runner uses a two-layer configuration approach:

1. **Environment Variables**: Provide authentication credentials and base settings
2. **CLI Arguments**: Control execution behavior and override test suite settings

**Configuration Precedence** (highest to lowest):
1. CLI arguments (highest priority)
2. Environment variables
3. Default values (lowest priority)

## Environment Variables

Environment variables configure authentication, API endpoints, and logging behavior. These are typically set in your CI/CD platform's secret management system.

### Required Environment Variables

These variables MUST be set for the runner to function:

| Variable | Description | Example | Validation |
|----------|-------------|---------|------------|
| `OAUTH_CLIENT_ID` | OAuth client ID from Nova Act QA Studio platform | `7abc123def456` | Required, non-empty string |
| `OAUTH_CLIENT_SECRET` | OAuth client secret from platform | `secret_xyz789abcdef...` | Required, non-empty string |
| `OAUTH_TOKEN_ENDPOINT` | AWS Cognito token endpoint URL | `https://domain.auth.us-east-1.amazoncognito.com/oauth2/token` | Required, must be HTTPS URL |
| `API_ENDPOINT` | Platform API base URL | `https://abc123.execute-api.us-east-1.amazonaws.com/api` | Required, must be HTTPS URL |

**Notes**:
- All URLs must use HTTPS protocol for security
- OAuth credentials are obtained from the platform's OAuth client management interface
- See [Installation Guide](installation.md) for instructions on creating OAuth clients

### Optional Environment Variables

These variables have default values and can be omitted:

| Variable | Description | Default | Valid Values |
|----------|-------------|---------|--------------|
| `LOG_LEVEL` | Logging verbosity level | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

**Logging Levels**:
- `DEBUG`: Detailed diagnostic information (includes HTTP requests/responses)
- `INFO`: General informational messages (recommended for production)
- `WARNING`: Warning messages for potential issues
- `ERROR`: Error messages only

## CLI Arguments

CLI arguments control test execution behavior and can override test suite settings.

### Required Arguments

| Argument | Description | Example | Format |
|----------|-------------|---------|--------|
| `--suite-id` | Test suite UUID to execute | `--suite-id 01234567-89ab-cdef-0123-456789abcdef` | UUID format |

**Notes**:
- Suite ID can be found in the platform UI or via API
- Must be a valid UUID of an existing test suite
- OAuth client must have `api/suite.read` and `api/suite.write` scopes

### Optional Arguments

| Argument | Description | Default | Example |
|----------|-------------|---------|---------|
| `--base-url` | Override base URL for all use cases in the suite | None (uses suite default) | `--base-url https://staging.example.com` |
| `--var` | Override a variable (repeatable for multiple variables) | None (uses suite defaults) | `--var username=testuser` |
| `--region` | Override AWS region for browser execution | None (uses suite default) | `--region us-west-2` |
| `--model-id` | Override Nova Act model ID | None (uses suite default) | `--model-id nova-act-v2` |
| `--verbose` | Enable verbose logging (sets LOG_LEVEL=DEBUG) | `false` | `--verbose` (flag, no value) |
| `--timeout` | Global timeout in seconds for entire execution | `3600` (1 hour) | `--timeout 7200` |

### Argument Details

#### `--base-url`

Overrides the base URL for all use cases in the test suite. Useful for testing against different environments (staging, production, etc.).

**Behavior**:
- Replaces the base URL configured in each use case
- Applied to all use cases in the suite
- Must be a valid HTTP or HTTPS URL
- Does not modify the test suite definition (temporary override)

**Example**:
```bash
--base-url https://staging.example.com
```

#### `--var`

Overrides a variable value for the execution. Can be specified multiple times to override multiple variables.

**Format**: `--var key=value`

**Behavior**:
- Overrides variables defined in the test suite
- Can override multiple variables by repeating the argument
- Variable names are case-sensitive
- Values are treated as strings
- Does not modify the test suite definition (temporary override)

**Examples**:
```bash
# Single variable
--var username=testuser

# Multiple variables
--var username=testuser --var password=testpass123 --var environment=staging
```

#### `--region`

Overrides the AWS region for browser execution.

**Behavior**:
- Specifies which AWS region to use for Nova Act browser execution
- Affects latency and compliance requirements
- Must be a valid AWS region identifier

**Valid Regions**:
- `us-east-1` (US East - N. Virginia)
- `us-west-2` (US West - Oregon)
- `eu-west-1` (Europe - Ireland)
- Other regions as supported by Nova Act

**Example**:
```bash
--region us-west-2
```

#### `--model-id`

Overrides the Nova Act model ID for execution.

**Behavior**:
- Specifies which Nova Act model version to use
- Allows testing with different model versions
- Must be a valid model ID available in your account

**Example**:
```bash
--model-id nova-act-v2
```

#### `--verbose`

Enables verbose logging output.

**Behavior**:
- Sets `LOG_LEVEL` to `DEBUG` (overrides environment variable)
- Outputs detailed diagnostic information
- Includes HTTP request/response details
- Useful for troubleshooting

**Example**:
```bash
--verbose
```

#### `--timeout`

Sets the global timeout for the entire execution.

**Behavior**:
- Maximum time (in seconds) for the entire test suite execution
- Execution is terminated if timeout is exceeded
- Default is 3600 seconds (1 hour)
- Set to 0 to disable timeout (not recommended)

**Example**:
```bash
--timeout 7200  # 2 hours
```

## Configuration Precedence Rules

When the same setting can be configured in multiple ways, the following precedence applies (highest to lowest):

### 1. CLI Arguments Override Everything

CLI arguments have the highest priority and override all other configuration sources.

**Example**:
```bash
# Environment: LOG_LEVEL=INFO
# CLI: --verbose
# Result: DEBUG logging (CLI wins)
```

### 2. Environment Variables Provide Defaults

Environment variables provide base configuration and defaults.

**Example**:
```bash
# Environment: LOG_LEVEL=WARNING
# CLI: (no --verbose flag)
# Result: WARNING logging (environment variable used)
```

### 3. Built-in Defaults

If neither CLI arguments nor environment variables are provided, built-in defaults are used.

**Example**:
```bash
# Environment: (LOG_LEVEL not set)
# CLI: (no --verbose flag)
# Result: INFO logging (built-in default)
```

## Configuration Examples

### Example 1: Basic Execution

Minimal configuration using only required settings:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="7abc123def456" \
  -e OAUTH_CLIENT_SECRET="secret_xyz789..." \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://abc123.execute-api.us-east-1.amazonaws.com/api" \
  nova-act-cicd-runner:latest \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef
```

### Example 2: Environment-Specific Testing

Override base URL to test against staging environment:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="7abc123def456" \
  -e OAUTH_CLIENT_SECRET="secret_xyz789..." \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://abc123.execute-api.us-east-1.amazonaws.com/api" \
  nova-act-cicd-runner:latest \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com
```

### Example 3: Variable Overrides

Override multiple variables for parameterized testing:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="7abc123def456" \
  -e OAUTH_CLIENT_SECRET="secret_xyz789..." \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://abc123.execute-api.us-east-1.amazonaws.com/api" \
  nova-act-cicd-runner:latest \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --var username=testuser \
  --var password=testpass123 \
  --var environment=staging
```

### Example 4: Debug Mode

Enable verbose logging for troubleshooting:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="7abc123def456" \
  -e OAUTH_CLIENT_SECRET="secret_xyz789..." \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://abc123.execute-api.us-east-1.amazonaws.com/api" \
  -e LOG_LEVEL="DEBUG" \
  nova-act-cicd-runner:latest \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --verbose
```

### Example 5: Extended Timeout

Increase timeout for long-running test suites:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="7abc123def456" \
  -e OAUTH_CLIENT_SECRET="secret_xyz789..." \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://abc123.execute-api.us-east-1.amazonaws.com/api" \
  nova-act-cicd-runner:latest \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --timeout 7200
```

### Example 6: Complete Configuration

Combine all configuration options:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="7abc123def456" \
  -e OAUTH_CLIENT_SECRET="secret_xyz789..." \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://abc123.execute-api.us-east-1.amazonaws.com/api" \
  -e LOG_LEVEL="INFO" \
  nova-act-cicd-runner:latest \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com \
  --var username=testuser \
  --var password=testpass123 \
  --region us-west-2 \
  --model-id nova-act-v2 \
  --verbose \
  --timeout 7200
```

### Example 7: Using Environment File

Load configuration from a `.env` file (local development):

```bash
# Create .env file
cat > .env << 'EOF'
OAUTH_CLIENT_ID=7abc123def456
OAUTH_CLIENT_SECRET=secret_xyz789...
OAUTH_TOKEN_ENDPOINT=https://domain.auth.us-east-1.amazoncognito.com/oauth2/token
API_ENDPOINT=https://abc123.execute-api.us-east-1.amazonaws.com/api
LOG_LEVEL=INFO
EOF

# Run with environment file
docker run --rm \
  --env-file .env \
  nova-act-cicd-runner:latest \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --verbose
```

## Configuration Validation

The runner validates all configuration at startup before executing tests.

### Validation Rules

**Environment Variables**:
- Required variables must be present and non-empty
- URLs must use HTTPS protocol
- LOG_LEVEL must be a valid level (DEBUG, INFO, WARNING, ERROR)

**CLI Arguments**:
- `--suite-id` must be a valid UUID format
- `--var` must be in `key=value` format
- `--timeout` must be a positive integer
- `--base-url` must be a valid URL (if provided)

### Validation Errors

**Missing Required Variable**:
```
ERROR - Missing required environment variable: OAUTH_CLIENT_ID
```

**Invalid URL Protocol**:
```
ERROR - Configuration validation failed: oauth_token_endpoint: oauth_token_endpoint must be an HTTPS URL
```

**Invalid Variable Format**:
```
ERROR - Variable must be in key=value format: invalidformat
```

## Security Considerations

### Credential Storage

- **Never commit** credentials to version control
- **Use secret management** provided by your CI/CD platform
- **Rotate credentials** regularly (every 90 days recommended)
- **Use least-privilege scopes** - only grant required permissions

### Token Caching

The runner caches OAuth tokens to avoid unnecessary authentication requests:

- Cache file: `.token_cache.json` (created in working directory)
- Contains: Access token and expiration time
- Automatically refreshed when token expires
- Should be added to `.gitignore`
- Can be safely deleted to force re-authentication

### Environment Variable Security

- Use CI/CD platform secret management (GitHub Secrets, GitLab CI/CD Variables, etc.)
- Mark secrets as "masked" or "protected" in your CI/CD platform
- Avoid logging environment variables in CI/CD output
- Use separate OAuth clients for different environments (dev, staging, prod)

## Troubleshooting Configuration

### Common Configuration Errors

**Authentication Failed**:
```
ERROR - OAuth authentication failed: 401
```
- Verify `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET` are correct
- Check token endpoint URL format
- Ensure OAuth client exists and is active

**Invalid URL Format**:
```
ERROR - Configuration validation failed: api_endpoint: api_endpoint must be an HTTPS URL
```
- Ensure URLs start with `https://`
- Check for typos in URL
- Verify URL is complete (no missing parts)

**Test Suite Not Found**:
```
ERROR - API request failed: 404 - Test suite not found
```
- Verify `--suite-id` is correct (UUID format)
- Check suite exists in platform UI
- Ensure OAuth client has `api/suite.read` scope

### Debug Configuration

Enable verbose logging to see configuration details:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="..." \
  -e OAUTH_CLIENT_SECRET="..." \
  -e OAUTH_TOKEN_ENDPOINT="..." \
  -e API_ENDPOINT="..." \
  nova-act-cicd-runner:latest \
  --suite-id ... \
  --verbose
```

This will output:
- Configuration loading process
- Environment variable values (secrets are masked)
- Validation results
- Authentication flow details

## Related Documentation

- [Installation Guide](installation.md) - Setting up OAuth clients and environment
- [CLI Reference](cli-reference.md) - Detailed CLI usage examples
- [CI/CD Integration](ci-cd-integration/) - Platform-specific configuration examples
- [Troubleshooting Guide](troubleshooting.md) - Common configuration issues
- [Best Practices](best-practices.md) - Security and optimization guidance

## Support

For configuration assistance:

1. Check the [Troubleshooting Guide](troubleshooting.md)
2. Review [GitHub Issues](https://github.com/aws-samples/sample-nova-act-qa-studio/issues)
3. Contact your platform administrator
4. Enable verbose logging (`--verbose`) for detailed diagnostics
