# Troubleshooting Guide

This guide helps you diagnose and resolve common issues when using the Nova Act QA Studio CI/CD runner.

## Quick Diagnostics

Before diving into specific errors, try these quick checks:

1. **Enable debug mode**: Set `LOG_LEVEL=DEBUG` and use `--verbose` flag
2. **Verify credentials**: Check that OAuth client ID and secret are correct
3. **Check network**: Ensure the runner can reach the API endpoint and Cognito
4. **Validate configuration**: Ensure all required environment variables are set

## Authentication Errors

### OAuth Authentication Failed: 400/401

**Error Message**:
```
OAuth authentication failed: 401 - {"error":"invalid_client"}
```

or

```
OAuth authentication failed: 400 - {"error":"invalid_grant"}
```

**Causes**:
- Invalid OAuth client ID or secret
- Client credentials not properly encoded
- OAuth client has been deleted or disabled
- Incorrect token endpoint URL
- Client secret has been rotated but old secret is still in use
- Wrong grant type configured in Cognito

**Solutions**:

1. **Verify credentials are correct**:
   ```bash
   # Check environment variables are set
   echo $OAUTH_CLIENT_ID
   echo $OAUTH_CLIENT_SECRET
   ```

2. **Regenerate OAuth client credentials**:
   - Log into the Nova Act QA Studio web UI
   - Navigate to Settings → OAuth Clients
   - Delete the old client and create a new one
   - Update your CI/CD secrets with the new credentials

3. **Verify token endpoint URL format**:
   ```
   https://{domain}.auth.{region}.amazoncognito.com/oauth2/token
   ```
   Example: `https://myapp.auth.us-east-1.amazoncognito.com/oauth2/token`

4. **Check OAuth client still exists**:
   - Use the web UI to verify the client hasn't been deleted
   - If deleted, create a new OAuth client

5. **Verify grant type**:
   - Ensure the OAuth client is configured for "Client Credentials" grant type
   - The runner uses client credentials flow, not authorization code flow

**Prevention**:
- Store credentials securely in your CI/CD platform's secret management
- Use descriptive names for OAuth clients to track their usage
- Document which client is used by which pipeline
- After rotating secrets, update all pipelines immediately

---

### OAuth Token Request Failed: Network Error

**Error Message**:
```
OAuth token request failed due to network error: Connection timeout
```

**Causes**:
- Network connectivity issues
- Firewall blocking outbound HTTPS requests
- Incorrect token endpoint URL
- DNS resolution failure

**Solutions**:

1. **Test network connectivity**:
   ```bash
   # Test if you can reach Cognito
   curl -v https://{domain}.auth.{region}.amazoncognito.com/oauth2/token
   ```

2. **Check firewall rules**:
   - Ensure outbound HTTPS (port 443) is allowed
   - Whitelist `*.amazoncognito.com` if using allowlist

3. **Verify DNS resolution**:
   ```bash
   nslookup {domain}.auth.{region}.amazoncognito.com
   ```

4. **Check proxy settings**:
   - If behind a corporate proxy, configure Docker to use it
   - Set `HTTP_PROXY` and `HTTPS_PROXY` environment variables

**Prevention**:
- Test network connectivity before deploying to production
- Document network requirements for your infrastructure team
- Use health checks in your CI/CD pipeline

---

### Insufficient OAuth Scopes

**Error Message**:
```
API request failed: 403 - {"error":"Forbidden","message":"Missing required scopes: api/suite.write"}
```

**Causes**:
- OAuth client doesn't have required scopes
- Scopes not requested during token acquisition
- User who created client didn't have permission to grant scopes

**Solutions**:

1. **Verify OAuth client has required scopes**:
   - Log into the web UI
   - Navigate to Settings → OAuth Clients
   - Check the scopes listed for your client

2. **Create new OAuth client with correct scopes**:
   ```json
   {
     "name": "CI/CD Runner",
     "scopes": [
       "api/suite.read",
       "api/suite.write",
       "api/usecases.read",
       "api/usecases.execute",
       "api/executions.read",
       "api/executions.write"
     ]
   }
   ```

3. **Required scopes for CI/CD runner**:
   - `api/suite.read` - Read test suite definitions
   - `api/suite.write` - Manage test suites
   - `api/usecases.read` - Read use case definitions
   - `api/usecases.execute` - Execute use cases
   - `api/executions.read` - Read execution data
   - `api/executions.write` - Create and update execution records

**Prevention**:
- Always grant all six required scopes when creating OAuth clients
- Use the principle of least privilege (don't grant unnecessary scopes)
- Document which scopes are required for each use case

---

## Configuration Errors

### Missing Required Environment Variable

**Error Message**:
```
Missing required environment variable: OAUTH_CLIENT_ID
```

**Causes**:
- Environment variable not set in CI/CD configuration
- Typo in variable name
- Variable not exported in shell script

**Solutions**:

1. **Verify all required variables are set**:
   ```bash
   # Check each required variable
   echo $OAUTH_CLIENT_ID
   echo $OAUTH_CLIENT_SECRET
   echo $OAUTH_TOKEN_ENDPOINT
   echo $API_ENDPOINT
   ```

2. **Set missing variables**:
   ```bash
   export OAUTH_CLIENT_ID="your-client-id"
   export OAUTH_CLIENT_SECRET="your-client-secret"
   export OAUTH_TOKEN_ENDPOINT="https://domain.auth.region.amazoncognito.com/oauth2/token"
   export API_ENDPOINT="https://api.example.com"
   ```

3. **Check CI/CD platform configuration**:
   - **GitHub Actions**: Settings → Secrets and variables → Actions
   - **GitLab CI**: Settings → CI/CD → Variables
   - **Jenkins**: Credentials management
   - **CircleCI**: Project Settings → Environment Variables

**Required Environment Variables**:
- `OAUTH_CLIENT_ID` - OAuth client ID
- `OAUTH_CLIENT_SECRET` - OAuth client secret
- `OAUTH_TOKEN_ENDPOINT` - Cognito token endpoint URL
- `API_ENDPOINT` - Platform API base URL

**Optional Environment Variables**:
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)

**Prevention**:
- Use a checklist when setting up new pipelines
- Create a template with all required variables
- Add validation step to verify variables are set

---

### Configuration Validation Failed: Invalid URL

**Error Message**:
```
Configuration validation failed: oauth_token_endpoint: must be an HTTPS URL
```

**Causes**:
- URL uses HTTP instead of HTTPS
- URL is malformed or incomplete
- Extra whitespace in URL

**Solutions**:

1. **Verify URL format**:
   ```bash
   # Correct format
   https://domain.auth.region.amazoncognito.com/oauth2/token
   
   # Incorrect formats
   http://domain.auth.region.amazoncognito.com/oauth2/token  # HTTP not allowed
   domain.auth.region.amazoncognito.com/oauth2/token         # Missing protocol
   ```

2. **Check for whitespace**:
   ```bash
   # Trim whitespace
   export OAUTH_TOKEN_ENDPOINT=$(echo "$OAUTH_TOKEN_ENDPOINT" | xargs)
   ```

3. **Validate API endpoint URL**:
   ```bash
   # Must start with https://
   export API_ENDPOINT="https://api.example.com"
   ```

**Prevention**:
- Always use HTTPS for security
- Copy URLs directly from deployment outputs
- Validate URLs before storing in CI/CD secrets

---

### Python Version Compatibility Error

**Error Message**:
```
ImportError: cannot import name 'formatargspec' from 'inspect'
```

or

```
error: metadata-generation-failed
× Encountered error while generating package metadata.
╰─> wrapt
```

**Causes**:
- Using Python 3.13 or later, which is not yet supported
- The `wrapt` dependency (used by Nova Act SDK) requires Python 3.12 or earlier

**Solutions**:

1. **Use Python 3.9 to 3.12**:
   ```bash
   # Check your Python version
   python3 --version
   
   # If using pyenv, switch to a compatible version
   pyenv install 3.12.0
   pyenv local 3.12.0
   
   # Verify the version
   python3 --version
   ```

2. **Update virtual environment**:
   ```bash
   # Remove old virtual environment
   rm -rf venv
   
   # Create new one with compatible Python version
   python3.12 -m venv venv
   source venv/bin/activate
   
   # Reinstall dependencies
   pip install -r requirements.txt
   ```

3. **For CI/CD pipelines**, specify Python version:
   
   **GitHub Actions**:
   ```yaml
   - uses: actions/setup-python@v4
     with:
       python-version: '3.12'
   ```
   
   **GitLab CI**:
   ```yaml
   image: python:3.12
   ```

**Prevention**:
- Pin Python version in CI/CD configuration
- Document Python version requirements in README
- Use Docker image with compatible Python version

---

## API Errors

### Test Suite Not Found: 404

**Error Message**:
```
API request failed: 404 - {"error":"Test suite not found"}
```

**Causes**:
- Invalid suite ID
- Suite has been deleted
- Suite belongs to different account/organization
- Typo in suite ID

**Solutions**:

1. **Verify suite ID is correct**:
   - Log into the web UI
   - Navigate to Test Suites
   - Copy the suite ID from the URL or suite details

2. **Check suite exists**:
   ```bash
   # Use API to verify suite exists
   curl -X GET \
     "https://api.example.com/test-suites/{suite-id}" \
     -H "Authorization: Bearer $TOKEN"
   ```

3. **Verify OAuth client has access**:
   - Ensure the OAuth client was created by a user with access to the suite
   - Check that the suite hasn't been moved to a different organization

**Prevention**:
- Store suite IDs as CI/CD variables, not hardcoded
- Use descriptive variable names (e.g., `SMOKE_TEST_SUITE_ID`)
- Document which suite IDs are used in which pipelines

---

### Unresolved Variables: 400

**Error Message**:
```
API request failed: 400 - {"error":"Unresolved variables","message":"Unresolved variables: username, password"}
```

**Causes**:
- Test suite uses variables that weren't provided
- Typo in variable name
- Variable not passed via `--var` flag

**Solutions**:

1. **Check which variables are required**:
   - Log into the web UI
   - Open the test suite
   - Review the use cases to see which variables are used

2. **Provide missing variables**:
   ```bash
   docker run --rm \
     -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID" \
     -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
     -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT" \
     -e API_ENDPOINT="$API_ENDPOINT" \
     nova-act-cicd-runner:latest \
     --suite-id suite-123 \
     --var username=testuser \
     --var password=testpass \
     --var api_key=secret123
   ```

3. **Check variable names match exactly**:
   - Variable names are case-sensitive
   - Use the exact names from the test suite

**Prevention**:
- Document required variables for each test suite
- Create environment-specific variable sets
- Use CI/CD variables for sensitive values

---

### API Request Failed: 500

**Error Message**:
```
API request failed: 500 - {"error":"Internal server error"}
```

**Causes**:
- Platform backend issue
- Database connectivity problem
- Temporary service disruption

**Solutions**:

1. **Retry the request**:
   - Wait a few minutes and try again
   - Temporary issues often resolve automatically

2. **Check platform status**:
   - Contact support to verify platform health
   - Check if there's scheduled maintenance

3. **Review request payload**:
   - Ensure request is well-formed
   - Check for invalid characters in variables

4. **Contact support**:
   - Provide the full error message
   - Include the suite execution ID if available
   - Share relevant logs (with sensitive data redacted)

**Prevention**:
- Implement retry logic in CI/CD pipelines
- Set up monitoring and alerts
- Have a fallback plan for critical pipelines

---

## Network Errors

### Connection Timeout

**Error Message**:
```
API request failed due to network error: Connection timeout
```

**Causes**:
- Network connectivity issues
- API endpoint unreachable
- Firewall blocking requests
- DNS resolution failure

**Solutions**:

1. **Test API connectivity**:
   ```bash
   # Test if you can reach the API
   curl -v https://api.example.com/health
   ```

2. **Check firewall rules**:
   - Ensure outbound HTTPS (port 443) is allowed
   - Whitelist the API endpoint domain

3. **Verify DNS resolution**:
   ```bash
   nslookup api.example.com
   ```

4. **Check proxy configuration**:
   - Configure Docker to use corporate proxy if needed
   - Set `HTTP_PROXY` and `HTTPS_PROXY` environment variables

**Prevention**:
- Test network connectivity before deploying
- Document network requirements
- Use health checks in CI/CD pipelines

---

### SSL Certificate Verification Failed

**Error Message**:
```
SSL certificate verification failed
```

**Causes**:
- Self-signed certificate
- Expired certificate
- Certificate chain issue
- Corporate proxy intercepting SSL

**Solutions**:

1. **Verify certificate is valid**:
   ```bash
   openssl s_client -connect api.example.com:443 -showcerts
   ```

2. **Update CA certificates** (if using custom CA):
   ```dockerfile
   # In Dockerfile
   COPY custom-ca.crt /usr/local/share/ca-certificates/
   RUN update-ca-certificates
   ```

3. **Check for proxy interference**:
   - Corporate proxies may intercept SSL
   - Install proxy's CA certificate in the container

**Prevention**:
- Use valid SSL certificates from trusted CAs
- Keep certificates up to date
- Document certificate requirements

---

## Timeout Errors

### Execution Timeout

**Error Message**:
```
Execution timed out after 3600 seconds
```

**Causes**:
- Test suite takes longer than default timeout (1 hour)
- Slow network or API responses
- Browser automation issues
- Infinite loops in test logic

**Solutions**:

1. **Increase timeout**:
   ```bash
   docker run --rm \
     -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID" \
     -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
     -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT" \
     -e API_ENDPOINT="$API_ENDPOINT" \
     nova-act-cicd-runner:latest \
     --suite-id suite-123 \
     --timeout 7200  # 2 hours
   ```

2. **Split large test suites**:
   - Break into smaller, focused suites
   - Run suites in parallel in separate jobs

3. **Optimize test steps**:
   - Review test steps for inefficiencies
   - Remove unnecessary waits
   - Optimize selectors and assertions

4. **Check for hanging steps**:
   - Review logs to identify which step is hanging
   - Fix or skip problematic steps

**Prevention**:
- Set realistic timeouts based on suite size
- Monitor execution times and optimize slow tests
- Use parallel execution when possible

---

### Step Timeout

**Error Message**:
```
Step execution timed out: Click button
```

**Causes**:
- Element not found or not clickable
- Page load too slow
- Network latency
- JavaScript not fully loaded

**Solutions**:

1. **Review step configuration**:
   - Check if selector is correct
   - Verify element exists on the page

2. **Increase step timeout** (in test suite configuration):
   - Edit the use case in the web UI
   - Increase timeout for specific steps

3. **Optimize page load**:
   - Check if target application is slow
   - Review network performance

4. **Fix test logic**:
   - Add explicit waits for dynamic content
   - Improve element selectors

**Prevention**:
- Use reliable selectors (data-testid, aria-label)
- Add appropriate waits for dynamic content
- Test against realistic environments

---

## Container Errors

### Container Out of Memory (OOMKilled)

**Error Message**:
```
Container killed: OOMKilled
```

**Causes**:
- Insufficient container memory
- Memory leak in browser or runner
- Too many parallel executions
- Large artifacts consuming memory

**Solutions**:

1. **Increase container memory limit**:
   ```bash
   docker run --rm \
     --memory=4g \
     -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID" \
     -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
     -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT" \
     -e API_ENDPOINT="$API_ENDPOINT" \
     nova-act-cicd-runner:latest \
     --suite-id suite-123
   ```

2. **Reduce test suite size**:
   - Split into smaller suites
   - Run fewer use cases per execution

3. **Monitor memory usage**:
   ```bash
   docker stats
   ```

4. **Check for memory leaks**:
   - Review logs for unusual patterns
   - Update to latest runner version

**Prevention**:
- Allocate sufficient memory (recommended: 2-4GB)
- Monitor resource usage
- Keep runner updated

---

### Container Permission Denied

**Error Message**:
```
Permission denied: /app/artifacts
```

**Causes**:
- Volume mount permission issues
- SELinux or AppArmor restrictions
- User/group ID mismatch

**Solutions**:

1. **Fix volume permissions**:
   ```bash
   # If mounting volumes
   chmod 777 ./artifacts
   ```

2. **Run with appropriate user**:
   ```bash
   docker run --rm \
     --user $(id -u):$(id -g) \
     ...
   ```

3. **Check SELinux context** (if applicable):
   ```bash
   chcon -Rt svirt_sandbox_file_t ./artifacts
   ```

**Prevention**:
- Avoid mounting volumes unless necessary
- Use appropriate file permissions
- Test in similar environment before production

---

## Debug Mode

### Enabling Debug Logging

Enable verbose logging to diagnose issues:

**Environment Variable**:
```bash
export LOG_LEVEL=DEBUG
```

**CLI Flag**:
```bash
docker run --rm \
  -e LOG_LEVEL=DEBUG \
  -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID" \
  -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
  -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT" \
  -e API_ENDPOINT="$API_ENDPOINT" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --verbose
```

### Debug Output

Debug mode provides:
- Detailed OAuth authentication flow
- API request/response details (with sensitive data redacted)
- Step-by-step execution progress
- Artifact upload details
- Timing information

**Example Debug Output**:
```
DEBUG: Loading configuration from environment variables...
DEBUG: Initializing OAuth client...
DEBUG: Requesting access token from https://domain.auth.region.amazoncognito.com/oauth2/token
DEBUG: Access token obtained, expires in 3600 seconds
DEBUG: Fetching test suite: suite-123
DEBUG: API GET /test-suites/suite-123
DEBUG: Response: 200 OK
DEBUG: Found test suite: Smoke Tests
DEBUG: Creating execution records...
DEBUG: API POST /test-suites/suite-123/execute
DEBUG: Response: 200 OK
DEBUG: Suite execution created: exec-456
DEBUG: Created 5 execution records
DEBUG: Executing use case: Login test (usecase-789)
DEBUG: Fetching execution steps...
DEBUG: Found 3 steps
DEBUG: Executing step 1: Navigate to login page
DEBUG: Updating step status: running
DEBUG: Step completed successfully
...
```

---

## Log Interpretation

### Understanding Log Levels

- **DEBUG**: Detailed diagnostic information (only with `LOG_LEVEL=DEBUG`)
- **INFO**: General informational messages about execution progress
- **WARNING**: Warning messages about potential issues
- **ERROR**: Error messages indicating failures

### Common Log Patterns

**Successful Execution**:
```
INFO: Loading configuration from environment variables...
INFO: Initializing OAuth client...
INFO: Authenticating with OAuth client credentials...
INFO: Successfully authenticated
INFO: Fetching test suite: suite-123
INFO: Found test suite: Smoke Tests
INFO: Creating execution records...
INFO: Suite execution created: exec-456
INFO: Created 5 execution records
INFO: Executing use cases in parallel...
INFO: All executions completed
INFO: Execution completed with exit code: 0
```

**Authentication Failure**:
```
INFO: Loading configuration from environment variables...
INFO: Initializing OAuth client...
INFO: Authenticating with OAuth client credentials...
ERROR: Runner failed: OAuth authentication failed: 401 - {"error":"invalid_client"}
```

**API Error**:
```
INFO: Fetching test suite: suite-123
ERROR: Runner failed: API request failed: 404 - {"error":"Test suite not found"}
```

**Configuration Error**:
```
ERROR: Runner failed: Missing required environment variable: OAUTH_CLIENT_ID
```

### Sensitive Data Redaction

The runner automatically redacts sensitive data from logs:
- OAuth tokens and secrets
- Query parameters in URLs
- Email addresses
- API keys in URLs

**Example**:
```
# Original error
Error: Failed to fetch https://api.example.com/data?token=abc123

# Redacted in logs
Error: Failed to fetch https://api.example.com/data?[REDACTED]
```

---

## Exit Codes

The runner uses exit codes to indicate execution status:

| Exit Code | Meaning | Description |
|-----------|---------|-------------|
| `0` | Success | All tests passed |
| `1` | Failure | One or more tests failed |
| `2` | Error | Runner error (authentication, configuration, API error) |

**CI/CD Integration**:
- Exit code `0`: Continue pipeline (tests passed)
- Exit code `1`: Fail pipeline (tests failed)
- Exit code `2`: Fail pipeline (runner error)

**Example Usage**:
```bash
# Run tests and capture exit code
docker run --rm \
  -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID" \
  -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
  -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT" \
  -e API_ENDPOINT="$API_ENDPOINT" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
  echo "All tests passed!"
elif [ $EXIT_CODE -eq 1 ]; then
  echo "Some tests failed"
  exit 1
elif [ $EXIT_CODE -eq 2 ]; then
  echo "Runner error occurred"
  exit 2
fi
```

---

## Getting Help

If you're still experiencing issues after trying these solutions:

### Support Channels

- **GitHub Issues**: [https://github.com/org/nova-act-cicd-runner/issues](https://github.com/org/nova-act-cicd-runner/issues)
- **Email Support**: support@novaact.example.com
- **Slack Community**: #qa-studio-support

### Information to Provide

When requesting support, please include:

1. **Error message**: Full error message from logs
2. **Configuration**: Environment variables used (redact secrets!)
3. **Steps to reproduce**: What you were trying to do
4. **Debug logs**: Output with `LOG_LEVEL=DEBUG` and `--verbose`
5. **Environment**: CI/CD platform, Docker version, OS
6. **Suite execution ID**: If available from the output

**Example Support Request**:
```
Subject: OAuth authentication failing with 401 error

Description:
I'm getting a 401 error when trying to authenticate with OAuth client credentials.

Error message:
OAuth authentication failed: 401 - {"error":"invalid_client"}

Configuration:
- OAUTH_TOKEN_ENDPOINT: https://myapp.auth.us-east-1.amazoncognito.com/oauth2/token
- API_ENDPOINT: https://api.example.com
- CI/CD Platform: GitHub Actions
- Docker version: 24.0.5

Steps to reproduce:
1. Set environment variables in GitHub Actions secrets
2. Run docker command with OAuth credentials
3. Authentication fails immediately

Debug logs:
[Attach debug logs with sensitive data redacted]

I've verified:
- OAuth client exists in the web UI
- Client ID and secret are correct
- Token endpoint URL is correct
- Network connectivity is working
```

### Self-Service Resources

- **Documentation**: [docs/](.)
- **API Reference**: [docs/api-reference.md](api-reference.md)
- **Configuration Guide**: [docs/configuration.md](configuration.md)
- **CI/CD Examples**: [docs/ci-cd-integration/](ci-cd-integration/)

---

## Frequently Asked Questions

### How do I rotate OAuth client credentials?

See [OAuth Client Management](API.md#rotate-client-secret) in the API documentation.

### Can I run multiple test suites in parallel?

Yes, run multiple Docker containers with different suite IDs. Each container is independent.

### How do I handle flaky tests?

- Review test logic for race conditions
- Add appropriate waits for dynamic content
- Use reliable selectors
- Consider retry logic in your CI/CD pipeline

### What's the maximum test suite size?

There's no hard limit, but we recommend:
- Keep suites under 50 use cases for reasonable execution time
- Split large suites into logical groups
- Use parallel execution for faster results

### How do I debug artifact upload failures?

1. Enable debug logging (`LOG_LEVEL=DEBUG`)
2. Check network connectivity to S3
3. Verify artifact file exists and is readable
4. Check file size (presigned URLs expire after 1 hour)

### Can I use the runner without Docker?

The runner is designed to run in Docker for consistency and isolation. Running outside Docker is not officially supported.

### How do I handle rate limiting?

The platform doesn't currently enforce rate limits, but if you encounter issues:
- Add delays between requests
- Reduce parallel execution
- Contact support to discuss your use case
