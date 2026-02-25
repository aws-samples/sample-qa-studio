# Work Package 5: Docker Container

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP5 - Docker Container
- **Estimated Duration**: 3 days
- **Dependencies**: WP4 (Artifact Management)
- **Status**: Not Started

---

## Overview

Package the CI/CD runner as a Docker container with Python 3.11, Nova Act SDK, bundled Chromium browser, and all dependencies. Optimize container size and configure for headless browser execution in CI/CD environments.

---

## User Stories

### US1: As a DevOps engineer, I need a Docker container to run tests in CI/CD
**Acceptance Criteria**:
- Container includes Python 3.11+
- Container includes Nova Act SDK with bundled browser
- Container includes all Python dependencies
- Container runs in headless mode
- Container size is optimized (target: ~500MB)

### US2: As a CI/CD pipeline, I need to pass configuration via environment variables
**Acceptance Criteria**:
- Container accepts OAuth credentials via env vars
- Container accepts API endpoint via env var
- Container accepts CLI arguments
- Container exits with appropriate exit codes

### US3: As a developer, I need to build and test the container locally
**Acceptance Criteria**:
- Dockerfile builds successfully
- Container runs locally with Docker
- Build instructions are documented
- Container can be tested without CI/CD platform

---

## Technical Requirements

### Base Image

Use official Python slim image for smaller size:
```dockerfile
FROM python:3.11-slim
```

### System Dependencies

Required for Chromium and Playwright:
- `wget`
- `gnupg`
- `ca-certificates`
- `fonts-liberation`
- `libasound2`
- `libatk-bridge2.0-0`
- `libatk1.0-0`
- `libatspi2.0-0`
- `libcups2`
- `libdbus-1-3`
- `libdrm2`
- `libgbm1`
- `libgtk-3-0`
- `libnspr4`
- `libnss3`
- `libwayland-client0`
- `libxcomposite1`
- `libxdamage1`
- `libxfixes3`
- `libxkbcommon0`
- `libxrandr2`
- `xdg-utils`

---

## Implementation Details

### Dockerfile

**File**: `Dockerfile`

```dockerfile
# Use Python 3.11 slim base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies for Chromium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements first (for layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium)
RUN playwright install chromium

# Copy application code
COPY src/ ./src/
COPY setup.py .

# Install the runner package
RUN pip install -e .

# Create directory for temporary artifacts
RUN mkdir -p /tmp/artifacts

# Set entrypoint
ENTRYPOINT ["python", "-m", "src.cli.parser"]

# Default command (shows help)
CMD ["--help"]
```

### Multi-Stage Build (Optimized)

**File**: `Dockerfile.optimized`

```dockerfile
# Stage 1: Build stage
FROM python:3.11-slim as builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime stage
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/root/.local/bin:$PATH

# Install runtime dependencies for Chromium
RUN apt-get update && apt-get install -y \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Install Playwright browsers
RUN playwright install chromium

# Copy application code
COPY src/ ./src/
COPY setup.py .

# Install the runner package
RUN pip install -e .

# Create directory for temporary artifacts
RUN mkdir -p /tmp/artifacts

# Set entrypoint
ENTRYPOINT ["python", "-m", "src.cli.parser"]

CMD ["--help"]
```

### Docker Compose (for local testing)

**File**: `docker-compose.yml`

```yaml
version: '3.8'

services:
  runner:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - OAUTH_CLIENT_ID=${OAUTH_CLIENT_ID}
      - OAUTH_CLIENT_SECRET=${OAUTH_CLIENT_SECRET}
      - OAUTH_TOKEN_ENDPOINT=${OAUTH_TOKEN_ENDPOINT}
      - API_ENDPOINT=${API_ENDPOINT}
      - LOG_LEVEL=INFO
    command: >
      --suite-id ${TEST_SUITE_ID}
      --base-url ${BASE_URL}
      --verbose
    volumes:
      - ./artifacts:/tmp/artifacts
```

### .dockerignore

**File**: `.dockerignore`

```
.git
.gitignore
.pytest_cache
__pycache__
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/
pip-log.txt
pip-delete-this-directory.txt
.tox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.log
.mypy_cache/
.dmypy.json
dmypy.json
.idea/
.vscode/
*.swp
*.swo
*~
.DS_Store
README.md
docs/
tests/
*.md
```

### Entrypoint Script (Alternative)

**File**: `entrypoint.sh`

```bash
#!/bin/bash
set -e

# Validate required environment variables
if [ -z "$OAUTH_CLIENT_ID" ]; then
    echo "Error: OAUTH_CLIENT_ID environment variable is required"
    exit 2
fi

if [ -z "$OAUTH_CLIENT_SECRET" ]; then
    echo "Error: OAUTH_CLIENT_SECRET environment variable is required"
    exit 2
fi

if [ -z "$OAUTH_TOKEN_ENDPOINT" ]; then
    echo "Error: OAUTH_TOKEN_ENDPOINT environment variable is required"
    exit 2
fi

if [ -z "$API_ENDPOINT" ]; then
    echo "Error: API_ENDPOINT environment variable is required"
    exit 2
fi

# Run the runner with all arguments
exec python -m src.cli.parser "$@"
```

---

## Build and Run Instructions

### Build Container

```bash
# Build with default Dockerfile
docker build -t nova-act-cicd-runner:latest .

# Build with optimized Dockerfile
docker build -f Dockerfile.optimized -t nova-act-cicd-runner:latest .

# Build with specific tag
docker build -t nova-act-cicd-runner:v1.0.0 .
```

### Run Container Locally

```bash
# Run with environment variables
docker run --rm \
  -e OAUTH_CLIENT_ID="your-client-id" \
  -e OAUTH_CLIENT_SECRET="your-client-secret" \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.region.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://api.example.com" \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --base-url https://staging.example.com \
  --var username=testuser \
  --verbose

# Run with .env file
docker run --rm \
  --env-file .env \
  nova-act-cicd-runner:latest \
  --suite-id suite-123 \
  --verbose

# Run with docker-compose
docker-compose up
```

### Test Container

```bash
# Test help command
docker run --rm nova-act-cicd-runner:latest --help

# Test with minimal config
docker run --rm \
  --env-file .env \
  nova-act-cicd-runner:latest \
  --suite-id test-suite-id
```

---

## Container Registry

### Push to Docker Hub

```bash
# Tag image
docker tag nova-act-cicd-runner:latest username/nova-act-cicd-runner:latest
docker tag nova-act-cicd-runner:latest username/nova-act-cicd-runner:v1.0.0

# Push to Docker Hub
docker push username/nova-act-cicd-runner:latest
docker push username/nova-act-cicd-runner:v1.0.0
```

### Push to ECR Public

```bash
# Authenticate to ECR Public
aws ecr-public get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin public.ecr.aws

# Tag image
docker tag nova-act-cicd-runner:latest public.ecr.aws/xxx/nova-act-cicd-runner:latest

# Push to ECR Public
docker push public.ecr.aws/xxx/nova-act-cicd-runner:latest
```

---

## Testing Requirements

### Container Tests
- Test container builds successfully
- Test container runs with valid credentials
- Test container exits with code 0 on success
- Test container exits with code 1 on test failure
- Test container exits with code 2 on error
- Test container with missing environment variables
- Test container size is within target (~500MB)

### Integration Tests
- Run full test suite in container
- Verify artifacts are created
- Verify exit codes
- Test in GitHub Actions
- Test in GitLab CI

---

## Size Optimization

**Target**: ~500MB

**Strategies**:
- Use `python:3.11-slim` base image
- Multi-stage build to exclude build dependencies
- Remove apt cache after installing packages
- Use `.dockerignore` to exclude unnecessary files
- Install only required Playwright browser (Chromium)
- Use `--no-cache-dir` for pip installs

---

## Security Considerations

- Run as non-root user (optional, add USER directive)
- No secrets baked into image
- All credentials via environment variables
- Regular base image updates for security patches
- Scan image for vulnerabilities (Trivy, Snyk)

---

## Documentation

### README.md

Include:
- Installation instructions
- Environment variable reference
- CLI argument reference
- Example usage
- Troubleshooting guide
- CI/CD integration examples

---

## Success Criteria

- [ ] Dockerfile builds successfully
- [ ] Container size ≤ 600MB
- [ ] Container runs tests successfully
- [ ] Container exits with correct exit codes
- [ ] Environment variables validated
- [ ] Container tested locally
- [ ] Build instructions documented
- [ ] Container published to registry
- [ ] Integration tests pass in container
