# Generic Docker Usage

This guide shows how to use the Nova Act QA Studio CI/CD Runner with Docker in any environment, including local development, custom CI/CD platforms, or manual test execution.

## Overview

The CI/CD runner is distributed as a Docker container that can be run on any system with Docker installed. This guide provides platform-agnostic examples for running the runner using Docker CLI commands and Docker Compose.

## Prerequisites

Before using the runner, ensure you have:

1. **Docker**: Docker Engine 20.10 or later installed
   - [Install Docker](https://docs.docker.com/get-docker/)
   - Verify installation: `docker --version`
2. **OAuth Client**: Created via the Nova Act QA Studio platform with required scopes:
   - `api/suite.read` - Read test suite definitions
   - `api/suite.write` - Execute test suites
   - `api/execution.write` - Create and update execution records
3. **Test Suite ID**: UUID of the test suite to execute (found in platform UI)

## Quick Start

Basic Docker run command to execute a test suite:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="your-client-id" \
  -e OAUTH_CLIENT_SECRET="your-client-secret" \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.region.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://api.example.com" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --verbose
```

## Setup Instructions

### Step 1: Install Docker

Install Docker on your system:

**Linux**:
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

**macOS**:
- Download and install [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)

**Windows**:
- Download and install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)

**Verify Installation**:
```bash
docker --version
docker ps
```

### Step 2: Create OAuth Client

Create an OAuth client in the Nova Act QA Studio platform:

1. Navigate to **Settings** → **OAuth Clients**
2. Click **Create OAuth Client**
3. Enter a name: `Docker Runner - <Environment>`
4. Select scopes:
   - `api/suite.read`
   - `api/suite.write`
   - `api/execution.write`
5. Click **Create**
6. **Save the client secret** - it will only be shown once!

### Step 3: Set Environment Variables

Store OAuth credentials as environment variables:

**Linux/macOS**:
```bash
export OAUTH_CLIENT_ID="7abc123def456"
export OAUTH_CLIENT_SECRET="secret_xyz789..."
export OAUTH_TOKEN_ENDPOINT="https://domain.auth.us-east-1.amazoncognito.com/oauth2/token"
export API_ENDPOINT="https://abc123.execute-api.us-east-1.amazonaws.com/api"
export TEST_SUITE_ID="01234567-89ab-cdef-0123-456789abcdef"
```

**Windows (PowerShell)**:
```powershell
$env:OAUTH_CLIENT_ID="7abc123def456"
$env:OAUTH_CLIENT_SECRET="secret_xyz789..."
$env:OAUTH_TOKEN_ENDPOINT="https://domain.auth.us-east-1.amazoncognito.com/oauth2/token"
$env:API_ENDPOINT="https://abc123.execute-api.us-east-1.amazonaws.com/api"
$env:TEST_SUITE_ID="01234567-89ab-cdef-0123-456789abcdef"
```

**Windows (Command Prompt)**:
```cmd
set OAUTH_CLIENT_ID=7abc123def456
set OAUTH_CLIENT_SECRET=secret_xyz789...
set OAUTH_TOKEN_ENDPOINT=https://domain.auth.us-east-1.amazoncognito.com/oauth2/token
set API_ENDPOINT=https://abc123.execute-api.us-east-1.amazonaws.com/api
set TEST_SUITE_ID=01234567-89ab-cdef-0123-456789abcdef
```

**Security Notes**:
- Never commit credentials to version control
- Use environment-specific credentials
- Consider using a `.env` file (see Docker Compose section)
- Rotate OAuth client secrets regularly (every 90 days)

### Step 4: Pull Docker Image

Pull the runner image from the registry:

```bash
docker pull nova-act-cicd-runner:latest
```

**For private registries**:
```bash
docker login registry.example.com
docker pull registry.example.com/nova-act-cicd-runner:latest
```

### Step 5: Run Tests

Execute a test suite:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  --suite-id ${TEST_SUITE_ID} \
  --verbose
```

## Docker Run Examples

### Example 1: Basic Execution

Run tests with minimal configuration:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="your-client-id" \
  -e OAUTH_CLIENT_SECRET="your-client-secret" \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.region.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://api.example.com" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123
```

### Example 2: Environment-Specific Testing

Test against staging environment with base URL override:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --base-url https://staging.example.com \
  --verbose
```

### Example 3: Variable Overrides

Override test variables for different test scenarios:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --base-url https://staging.example.com \
  --var username=testuser \
  --var environment=staging \
  --var api_key=test-key-123 \
  --verbose
```

### Example 4: Extended Timeout

Increase timeout for long-running test suites:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --timeout 7200 \
  --verbose
```

### Example 5: Custom Logging Level

Control logging verbosity:

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  -e LOG_LEVEL=DEBUG \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --verbose
```

### Example 6: Named Container

Run with a named container for easier management:

```bash
docker run --rm \
  --name qa-test-run \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --verbose
```

### Example 7: Detached Mode (Background)

Run tests in the background:

```bash
docker run -d \
  --name qa-test-background \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --verbose

# View logs
docker logs -f qa-test-background

# Check status
docker ps -a | grep qa-test-background

# Stop container
docker stop qa-test-background

# Remove container
docker rm qa-test-background
```

### Example 8: Using Environment File

Store credentials in a file and load them:

**Create `.env` file**:
```bash
OAUTH_CLIENT_ID=7abc123def456
OAUTH_CLIENT_SECRET=secret_xyz789...
OAUTH_TOKEN_ENDPOINT=https://domain.auth.us-east-1.amazoncognito.com/oauth2/token
API_ENDPOINT=https://abc123.execute-api.us-east-1.amazonaws.com/api
```

**Run with environment file**:
```bash
docker run --rm \
  --env-file .env \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --verbose
```

**Security Warning**: Add `.env` to `.gitignore` to prevent committing secrets!

### Example 9: Resource Limits

Limit container resources:

```bash
docker run --rm \
  --memory="2g" \
  --cpus="2.0" \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --verbose
```

### Example 10: Network Configuration

Run on a specific Docker network:

```bash
# Create network
docker network create qa-network

# Run container on network
docker run --rm \
  --network qa-network \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --verbose

# Cleanup
docker network rm qa-network
```

## Docker Compose

Docker Compose provides a declarative way to configure and run the runner.

### Basic Docker Compose Configuration

**Create `docker-compose.yml`**:
```yaml
version: '3.8'

services:
  qa-runner:
    image: nova-act-cicd-runner:latest
    environment:
      OAUTH_CLIENT_ID: ${OAUTH_CLIENT_ID}
      OAUTH_CLIENT_SECRET: ${OAUTH_CLIENT_SECRET}
      OAUTH_TOKEN_ENDPOINT: ${OAUTH_TOKEN_ENDPOINT}
      API_ENDPOINT: ${API_ENDPOINT}
    command:
      - --suite-id
      - suite-123
      - --verbose
```

**Create `.env` file**:
```bash
OAUTH_CLIENT_ID=7abc123def456
OAUTH_CLIENT_SECRET=secret_xyz789...
OAUTH_TOKEN_ENDPOINT=https://domain.auth.us-east-1.amazoncognito.com/oauth2/token
API_ENDPOINT=https://abc123.execute-api.us-east-1.amazonaws.com/api
```

**Run with Docker Compose**:
```bash
docker-compose up
```

**Run in detached mode**:
```bash
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Environment-Specific Configurations

**Create `docker-compose.staging.yml`**:
```yaml
version: '3.8'

services:
  qa-runner:
    image: nova-act-cicd-runner:latest
    environment:
      OAUTH_CLIENT_ID: ${OAUTH_CLIENT_ID}
      OAUTH_CLIENT_SECRET: ${OAUTH_CLIENT_SECRET}
      OAUTH_TOKEN_ENDPOINT: ${OAUTH_TOKEN_ENDPOINT}
      API_ENDPOINT: ${API_ENDPOINT}
    command:
      - --suite-id
      - ${TEST_SUITE_ID}
      - --base-url
      - https://staging.example.com
      - --var
      - environment=staging
      - --verbose
```

**Create `docker-compose.production.yml`**:
```yaml
version: '3.8'

services:
  qa-runner:
    image: nova-act-cicd-runner:latest
    environment:
      OAUTH_CLIENT_ID: ${OAUTH_CLIENT_ID}
      OAUTH_CLIENT_SECRET: ${OAUTH_CLIENT_SECRET}
      OAUTH_TOKEN_ENDPOINT: ${OAUTH_TOKEN_ENDPOINT}
      API_ENDPOINT: ${API_ENDPOINT}
    command:
      - --suite-id
      - ${TEST_SUITE_ID}
      - --base-url
      - https://production.example.com
      - --var
      - environment=production
      - --verbose
```

**Run environment-specific configuration**:
```bash
# Staging
docker-compose -f docker-compose.staging.yml up

# Production
docker-compose -f docker-compose.production.yml up
```

### Multiple Test Suites

**Create `docker-compose.yml`**:
```yaml
version: '3.8'

services:
  smoke-tests:
    image: nova-act-cicd-runner:latest
    environment:
      OAUTH_CLIENT_ID: ${OAUTH_CLIENT_ID}
      OAUTH_CLIENT_SECRET: ${OAUTH_CLIENT_SECRET}
      OAUTH_TOKEN_ENDPOINT: ${OAUTH_TOKEN_ENDPOINT}
      API_ENDPOINT: ${API_ENDPOINT}
    command:
      - --suite-id
      - ${SMOKE_SUITE_ID}
      - --verbose

  integration-tests:
    image: nova-act-cicd-runner:latest
    environment:
      OAUTH_CLIENT_ID: ${OAUTH_CLIENT_ID}
      OAUTH_CLIENT_SECRET: ${OAUTH_CLIENT_SECRET}
      OAUTH_TOKEN_ENDPOINT: ${OAUTH_TOKEN_ENDPOINT}
      API_ENDPOINT: ${API_ENDPOINT}
    command:
      - --suite-id
      - ${INTEGRATION_SUITE_ID}
      - --verbose
    depends_on:
      - smoke-tests

  e2e-tests:
    image: nova-act-cicd-runner:latest
    environment:
      OAUTH_CLIENT_ID: ${OAUTH_CLIENT_ID}
      OAUTH_CLIENT_SECRET: ${OAUTH_CLIENT_SECRET}
      OAUTH_TOKEN_ENDPOINT: ${OAUTH_TOKEN_ENDPOINT}
      API_ENDPOINT: ${API_ENDPOINT}
    command:
      - --suite-id
      - ${E2E_SUITE_ID}
      - --timeout
      - "7200"
      - --verbose
    depends_on:
      - integration-tests
```

**Run all test suites**:
```bash
docker-compose up
```

**Run specific service**:
```bash
docker-compose up smoke-tests
```

### Resource Limits in Docker Compose

**Create `docker-compose.yml`**:
```yaml
version: '3.8'

services:
  qa-runner:
    image: nova-act-cicd-runner:latest
    environment:
      OAUTH_CLIENT_ID: ${OAUTH_CLIENT_ID}
      OAUTH_CLIENT_SECRET: ${OAUTH_CLIENT_SECRET}
      OAUTH_TOKEN_ENDPOINT: ${OAUTH_TOKEN_ENDPOINT}
      API_ENDPOINT: ${API_ENDPOINT}
    command:
      - --suite-id
      - ${TEST_SUITE_ID}
      - --verbose
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

### Health Checks (Advanced)

**Create `docker-compose.yml`**:
```yaml
version: '3.8'

services:
  qa-runner:
    image: nova-act-cicd-runner:latest
    environment:
      OAUTH_CLIENT_ID: ${OAUTH_CLIENT_ID}
      OAUTH_CLIENT_SECRET: ${OAUTH_CLIENT_SECRET}
      OAUTH_TOKEN_ENDPOINT: ${OAUTH_TOKEN_ENDPOINT}
      API_ENDPOINT: ${API_ENDPOINT}
    command:
      - --suite-id
      - ${TEST_SUITE_ID}
      - --verbose
    restart: on-failure
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## Container Lifecycle Management

### Starting Containers

**Run once and remove**:
```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123
```

**Run in background**:
```bash
docker run -d \
  --name qa-test \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123
```

### Monitoring Containers

**List running containers**:
```bash
docker ps
```

**List all containers (including stopped)**:
```bash
docker ps -a
```

**View container logs**:
```bash
# Follow logs in real-time
docker logs -f qa-test

# View last 100 lines
docker logs --tail 100 qa-test

# View logs with timestamps
docker logs -t qa-test
```

**Inspect container**:
```bash
docker inspect qa-test
```

**View container resource usage**:
```bash
docker stats qa-test
```

### Stopping Containers

**Stop running container**:
```bash
docker stop qa-test
```

**Stop with timeout**:
```bash
docker stop -t 30 qa-test
```

**Force stop (kill)**:
```bash
docker kill qa-test
```

### Removing Containers

**Remove stopped container**:
```bash
docker rm qa-test
```

**Force remove running container**:
```bash
docker rm -f qa-test
```

**Remove all stopped containers**:
```bash
docker container prune
```

### Restarting Containers

**Restart container**:
```bash
docker restart qa-test
```

**Auto-restart on failure**:
```bash
docker run -d \
  --name qa-test \
  --restart on-failure:3 \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123
```

**Restart policies**:
- `no` - Never restart (default)
- `on-failure[:max-retries]` - Restart on non-zero exit code
- `always` - Always restart
- `unless-stopped` - Always restart unless manually stopped

## Exit Codes and Error Handling

The runner uses exit codes to indicate test results:

| Exit Code | Meaning | Description |
|-----------|---------|-------------|
| `0` | Success | All tests passed |
| `1` | Test failure | One or more tests failed |
| `2` | Runner error | Authentication, configuration, or API error |

### Checking Exit Codes

**Bash/Linux/macOS**:
```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
  echo "✅ All tests passed!"
elif [ $EXIT_CODE -eq 1 ]; then
  echo "❌ Tests failed!"
  exit 1
elif [ $EXIT_CODE -eq 2 ]; then
  echo "⚠️ Runner error - check configuration"
  exit 2
fi
```

**PowerShell**:
```powershell
docker run --rm `
  -e OAUTH_CLIENT_ID="$env:OAUTH_CLIENT_ID" `
  -e OAUTH_CLIENT_SECRET="$env:OAUTH_CLIENT_SECRET" `
  -e OAUTH_TOKEN_ENDPOINT="$env:OAUTH_TOKEN_ENDPOINT" `
  -e API_ENDPOINT="$env:API_ENDPOINT" `
  nova-act-cicd-runner:latest `
  --suite-id suite-123

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
  Write-Host "✅ All tests passed!" -ForegroundColor Green
} elseif ($exitCode -eq 1) {
  Write-Host "❌ Tests failed!" -ForegroundColor Red
  exit 1
} elseif ($exitCode -eq 2) {
  Write-Host "⚠️ Runner error - check configuration" -ForegroundColor Yellow
  exit 2
}
```

### Retry Logic

**Bash script with retry**:
```bash
#!/bin/bash

MAX_RETRIES=3
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  echo "Attempt $((RETRY_COUNT + 1)) of $MAX_RETRIES"
  
  docker run --rm \
    -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
    -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
    -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
    -e API_ENDPOINT="${API_ENDPOINT}" \
    nova-act-cicd-runner:latest \
    --suite-id suite-123 \
    --verbose
  
  EXIT_CODE=$?
  
  if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Tests passed!"
    exit 0
  elif [ $EXIT_CODE -eq 2 ]; then
    echo "⚠️ Runner error - not retrying"
    exit 2
  fi
  
  RETRY_COUNT=$((RETRY_COUNT + 1))
  
  if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
    echo "Retrying in 10 seconds..."
    sleep 10
  fi
done

echo "❌ Tests failed after $MAX_RETRIES attempts"
exit 1
```

## Best Practices

### Security

1. **Never Commit Secrets**: Use environment variables or `.env` files (add to `.gitignore`)
2. **Use Environment Files**: Store credentials in `.env` files for local development
3. **Rotate Credentials**: Rotate OAuth client secrets regularly (every 90 days)
4. **Minimal Scopes**: Grant only required scopes to OAuth clients
5. **Separate Credentials**: Use different OAuth clients for different environments

### Performance

1. **Resource Limits**: Set appropriate CPU and memory limits
2. **Image Caching**: Pull images once and reuse
3. **Network Optimization**: Use Docker networks for container communication
4. **Cleanup**: Remove stopped containers and unused images regularly

### Reliability

1. **Verbose Logging**: Use `--verbose` flag for troubleshooting
2. **Timeout Configuration**: Set appropriate timeouts for large test suites
3. **Retry Logic**: Implement retry logic for transient failures
4. **Health Checks**: Monitor container health and resource usage
5. **Log Management**: Configure log rotation to prevent disk space issues

### Organization

1. **Named Containers**: Use `--name` for easier container management
2. **Docker Compose**: Use Docker Compose for complex configurations
3. **Environment-Specific Configs**: Maintain separate configs for each environment
4. **Documentation**: Document custom configurations and scripts
5. **Version Pinning**: Pin specific image versions for reproducibility

## Troubleshooting

### Docker Not Installed

**Problem**: `docker: command not found`

**Solutions**:
1. Install Docker following the [official installation guide](https://docs.docker.com/get-docker/)
2. Verify installation: `docker --version`
3. Ensure Docker daemon is running: `docker ps`

### Permission Denied

**Problem**: `permission denied while trying to connect to the Docker daemon socket`

**Solutions (Linux)**:
1. Add user to docker group: `sudo usermod -aG docker $USER`
2. Log out and log back in
3. Verify: `docker ps`

**Alternative**: Run with sudo (not recommended for production)

### Image Not Found

**Problem**: `Unable to find image 'nova-act-cicd-runner:latest' locally`

**Solutions**:
1. Pull image: `docker pull nova-act-cicd-runner:latest`
2. Check image name and tag are correct
3. For private registries, login first: `docker login registry.example.com`
4. Verify image exists: `docker images`

### Authentication Failures

**Problem**: `OAuth authentication failed: 401`

**Solutions**:
1. Verify environment variables are set: `echo $OAUTH_CLIENT_ID`
2. Check OAuth client exists and is active in platform
3. Ensure OAuth client has required scopes
4. Verify token endpoint URL is correct
5. Check for typos in credentials

### Container Exits Immediately

**Problem**: Container starts and exits immediately

**Solutions**:
1. View logs: `docker logs <container-name>`
2. Check exit code: `docker inspect <container-name> --format='{{.State.ExitCode}}'`
3. Verify all required environment variables are set
4. Run with `--verbose` flag for detailed output
5. Check for configuration errors in command arguments

### Out of Memory

**Problem**: Container killed due to out of memory

**Solutions**:
1. Increase memory limit: `docker run --memory="4g" ...`
2. Check available system memory: `docker stats`
3. Split large test suites into smaller suites
4. Monitor memory usage during execution

### Network Issues

**Problem**: Cannot connect to API endpoint

**Solutions**:
1. Verify API endpoint URL is correct
2. Check network connectivity: `docker run --rm alpine ping api.example.com`
3. Ensure firewall allows outbound connections
4. Check DNS resolution: `docker run --rm alpine nslookup api.example.com`
5. Try using `--network host` for debugging (Linux only)

### Timeout Issues

**Problem**: Tests timeout before completion

**Solutions**:
1. Increase runner timeout: `--timeout 7200`
2. Split large test suites into smaller suites
3. Check network latency to API endpoint
4. Review test steps for inefficiencies
5. Monitor container resource usage

## Advanced Usage

### Custom Entrypoint

Override the default entrypoint:

```bash
docker run --rm \
  --entrypoint /bin/sh \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  -c "python -m cicd_runner --suite-id suite-123 --verbose"
```

### Interactive Shell

Run an interactive shell inside the container:

```bash
docker run -it --rm \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  /bin/bash
```

### Volume Mounting (If Needed)

Mount local directories into the container:

```bash
docker run --rm \
  -v $(pwd)/config:/app/config:ro \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123
```

### Building from Source

Build the Docker image from source:

```bash
# Clone repository
git clone https://github.com/org/repo.git
cd repo

# Build image
docker build -t nova-act-cicd-runner:local -f cicd-runner/Dockerfile .

# Run locally built image
docker run --rm \
  -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
  -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
  -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
  -e API_ENDPOINT="${API_ENDPOINT}" \
  nova-act-cicd-runner:local \
  --suite-id suite-123
```

## Related Documentation

- [Configuration Reference](../configuration.md) - Environment variables and CLI arguments
- [CLI Reference](../cli-reference.md) - Detailed CLI usage
- [Troubleshooting Guide](../troubleshooting.md) - Common errors and solutions
- [Best Practices](../best-practices.md) - Security and optimization guidance
- [GitHub Actions Integration](github-actions.md) - GitHub Actions examples
- [GitLab CI Integration](gitlab-ci.md) - GitLab CI examples
- [Jenkins Integration](jenkins.md) - Jenkins pipeline examples
- [CircleCI Integration](circleci.md) - CircleCI workflow examples

## Support

For Docker usage assistance:

1. Check the [Docker documentation](https://docs.docker.com/)
2. Review [Troubleshooting Guide](../troubleshooting.md)
3. Enable verbose logging (`--verbose`) for detailed diagnostics
4. Check container logs: `docker logs <container-name>`
5. Contact your platform administrator

