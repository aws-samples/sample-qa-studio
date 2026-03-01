# Installation Guide

This guide walks you through setting up the Nova Act QA Studio CI/CD Runner for executing test suites in your CI/CD pipelines.

## Prerequisites

Before installing the runner, ensure you have:

- **Docker** installed and running (version 20.10 or later)
  - [Install Docker](https://docs.docker.com/get-docker/)
  - Verify: `docker --version`
- **Network access** to:
  - Nova Act QA Studio API endpoint
  - AWS Cognito token endpoint
- **OAuth client credentials** from Nova Act QA Studio platform (see setup below)

## Step 1: Create OAuth Client

The runner requires OAuth client credentials for authentication. Create an OAuth client through the Nova Act QA Studio web interface:

### 1.1 Access OAuth Client Management

1. Login to the Nova Act QA Studio web interface
2. Navigate to **Settings** → **OAuth Clients**
3. Click **Create New Client**

### 1.2 Configure OAuth Client

Provide the following information:

- **Name**: `CI/CD Runner - Production` (or your preferred name)
- **Scopes**: Select the following required scopes:
  - `api/suite.read` - Read test suite definitions
  - `api/suite.write` - Manage test suites
  - `api/usecases.read` - Read use case definitions
  - `api/usecases.execute` - Execute use cases
  - `api/executions.read` - Read execution data
  - `api/executions.write` - Create and update execution records

### 1.3 Save Credentials

After creating the client, you'll receive:

- **Client ID**: A unique identifier (e.g., `7abc123def456`)
- **Client Secret**: A secret key (e.g., `secret_xyz789...`)

**IMPORTANT**: The client secret is shown only once. Save it securely immediately.

### 1.4 Store Credentials Securely

Store credentials using your CI/CD platform's secret management:

- **GitHub Actions**: Repository Secrets
- **GitLab CI**: CI/CD Variables (masked)
- **Jenkins**: Credentials Manager
- **CircleCI**: Contexts or Environment Variables

**Never commit credentials to version control.**

## Step 2: Gather Configuration Details

You'll need the following information from your Nova Act QA Studio deployment:

### 2.1 OAuth Token Endpoint

The Cognito token endpoint URL follows this format:

```
https://{cognito-domain}.auth.{region}.amazoncognito.com/oauth2/token
```

**Example**:
```
https://nova-act-prod.auth.us-east-1.amazoncognito.com/oauth2/token
```

Contact your platform administrator if you don't have this URL.

### 2.2 API Endpoint

The Platform API base URL follows this format:

```
https://{api-gateway-id}.execute-api.{region}.amazonaws.com/{stage}
```

**Example**:
```
https://abc123def4.execute-api.us-east-1.amazonaws.com/api
```

This URL is typically provided by your platform administrator or visible in the web interface.

## Step 3: Set Environment Variables

The runner requires four environment variables for configuration.

### 3.1 Environment Variable Template

Create a template for your credentials:

```bash
# OAuth credentials from Cognito
export OAUTH_CLIENT_ID="your-client-id"
export OAUTH_CLIENT_SECRET="your-client-secret"

# Cognito token endpoint
export OAUTH_TOKEN_ENDPOINT="https://your-domain.auth.region.amazoncognito.com/oauth2/token"

# Platform API endpoint
export API_ENDPOINT="https://your-api-id.execute-api.region.amazonaws.com/api"
```

### 3.2 Optional Environment Variables

```bash
# Logging level (default: INFO)
export LOG_LEVEL="DEBUG"
```

### 3.3 Local Development Setup

For local testing, create a `.env` file:

```bash
# Create .env file
cat > .env << 'EOF'
OAUTH_CLIENT_ID=7abc123def456
OAUTH_CLIENT_SECRET=secret_xyz789...
OAUTH_TOKEN_ENDPOINT=https://nova-act-prod.auth.us-east-1.amazoncognito.com/oauth2/token
API_ENDPOINT=https://abc123def4.execute-api.us-east-1.amazonaws.com/api
LOG_LEVEL=INFO
EOF

# Secure the file
chmod 600 .env
```

**IMPORTANT**: Add `.env` to your `.gitignore` to prevent committing secrets.

## Step 4: Acquire Container

Choose one of the following methods to acquire the runner container:

### Option A: Pull from Container Registry (Recommended)

Pull the pre-built container image:

```bash
docker pull nova-act-cicd-runner:latest
```

If using a private registry:

```bash
# Login to registry
docker login registry.example.com

# Pull image
docker pull registry.example.com/nova-act-cicd-runner:latest

# Tag for convenience
docker tag registry.example.com/nova-act-cicd-runner:latest nova-act-cicd-runner:latest
```

### Option B: Build from Source

Build the container locally from source:

```bash
# Clone repository
git clone https://github.com/aws-samples/sample-nova-act-qa-studio.git
cd sample-nova-act-qa-studio

# Build container
docker build -t nova-act-cicd-runner:latest -f qa-studio-ci-runner/Dockerfile qa-studio-ci-runner/

# Verify build
docker images nova-act-cicd-runner
```

## Step 5: Verify Installation

Test your installation with a simple execution:

### 5.1 Run Verification Command

```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="your-client-id" \
  -e OAUTH_CLIENT_SECRET="your-client-secret" \
  -e OAUTH_TOKEN_ENDPOINT="https://your-domain.auth.region.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://your-api-id.execute-api.region.amazonaws.com/api" \
  nova-act-cicd-runner:latest \
  --suite-id YOUR_TEST_SUITE_ID \
  --verbose
```

Replace:
- `your-client-id` with your OAuth client ID
- `your-client-secret` with your OAuth client secret
- `your-domain.auth.region.amazoncognito.com` with your Cognito domain
- `your-api-id.execute-api.region.amazonaws.com/api` with your API endpoint
- `YOUR_TEST_SUITE_ID` with a valid test suite UUID from your platform

### 5.2 Expected Output

Successful execution should produce output similar to:

```
INFO - Authenticating with OAuth client credentials...
INFO - OAuth authentication successful
INFO - Fetching test suite: 01234567-89ab-cdef-0123-456789abcdef
INFO - Test suite: Login Tests (3 use cases)
INFO - Creating suite execution...
INFO - Suite execution created: 01234567-89ab-cdef-0123-456789abcdef
INFO - Created 3 execution records
INFO - Execution 1/3: Login with valid credentials (execution-id-1)
INFO - Execution 2/3: Login with invalid password (execution-id-2)
INFO - Execution 3/3: Logout (execution-id-3)
INFO - Suite execution completed successfully
```

### 5.3 Troubleshooting Verification

**Authentication Failed**:
```
ERROR - OAuth authentication failed: 401
```
- Verify client ID and secret are correct
- Check token endpoint URL format
- Ensure OAuth client exists in platform

**Test Suite Not Found**:
```
ERROR - API request failed: 404 - Test suite not found
```
- Verify suite ID is correct (UUID format)
- Check suite exists in platform UI
- Ensure OAuth client has `api/suite.read` scope

**Connection Timeout**:
```
ERROR - OAuth authentication failed: Connection timeout
```
- Check network connectivity
- Verify firewall allows HTTPS connections
- Confirm endpoint URLs are accessible

## Alternative: Running Without Docker

If you prefer to run the CLI directly without Docker (for local development or environments where Docker is not available), you can install and run the runner using Python.

### Prerequisites for Direct Installation

- **Python 3.9 to 3.12** installed (Python 3.13+ not yet supported)
  - Verify: `python3 --version`
  - [Install Python](https://www.python.org/downloads/)
- **pip** (Python package manager)
  - Usually included with Python
  - Verify: `pip3 --version`
- **Network access** to:
  - Nova Act QA Studio API endpoint
  - AWS Cognito token endpoint
- **OAuth client credentials** from Nova Act QA Studio platform

### Installation Steps

#### 1. Clone or Download the Repository

```bash
# Clone the repository
git clone https://github.com/aws-samples/sample-nova-act-qa-studio.git
cd sample-nova-act-qa-studio/qa-studio-ci-runner
```

Or download and extract the `qa-studio-ci-runner` directory from the repository.

#### 2. Create a Virtual Environment (Recommended)

Using a virtual environment isolates the runner's dependencies from your system Python:

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
# venv\Scripts\activate
```

#### 3. Install Dependencies

```bash
# Install the runner and its dependencies
pip install -e .

# Or install from requirements.txt
pip install -r requirements.txt
```

#### 4. Configure Environment Variables

Create a `.env` file in the `qa-studio-ci-runner` directory:

```bash
cat > .env << 'EOF'
OAUTH_CLIENT_ID=your-client-id
OAUTH_CLIENT_SECRET=your-client-secret
OAUTH_TOKEN_ENDPOINT=https://your-domain.auth.region.amazoncognito.com/oauth2/token
API_ENDPOINT=https://your-api-id.execute-api.region.amazonaws.com/api
LOG_LEVEL=INFO
EOF

# Secure the file
chmod 600 .env
```

Or export environment variables directly:

```bash
export OAUTH_CLIENT_ID="your-client-id"
export OAUTH_CLIENT_SECRET="your-client-secret"
export OAUTH_TOKEN_ENDPOINT="https://your-domain.auth.region.amazoncognito.com/oauth2/token"
export API_ENDPOINT="https://your-api-id.execute-api.region.amazonaws.com/api"
```

#### 5. Verify Installation

Test the installation by running a simple command:

```bash
# If installed with pip install -e .
qa-studio-ci-runner --suite-id YOUR_TEST_SUITE_ID --verbose

# Or run directly with Python
python -m src.main --suite-id YOUR_TEST_SUITE_ID --verbose
```

Replace `YOUR_TEST_SUITE_ID` with a valid test suite UUID from your platform.

### Usage Without Docker

Once installed, you can use the runner directly:

```bash
# Basic usage
qa-studio-ci-runner --suite-id 01234567-89ab-cdef-0123-456789abcdef

# With variable overrides
qa-studio-ci-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --var username=testuser \
  --var password=testpass

# With base URL override
qa-studio-ci-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com

# With verbose logging
qa-studio-ci-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --verbose
```

### Deactivating Virtual Environment

When you're done, deactivate the virtual environment:

```bash
deactivate
```

### Updating the Runner

To update to the latest version:

```bash
# Activate virtual environment
source venv/bin/activate

# Pull latest changes
git pull

# Reinstall
pip install -e .
```

### Troubleshooting Direct Installation

**Import Errors**:
```
ModuleNotFoundError: No module named 'requests'
```
- Ensure virtual environment is activated
- Reinstall dependencies: `pip install -r requirements.txt`

**Command Not Found**:
```
qa-studio-ci-runner: command not found
```
- Ensure virtual environment is activated
- Use direct Python invocation: `python -m src.main`
- Verify installation: `pip list | grep qa-studio-ci-runner`

**Permission Errors**:
```
PermissionError: [Errno 13] Permission denied
```
- Don't use `sudo` with pip in virtual environment
- Ensure virtual environment is activated
- Check file permissions on `.env` file

## Step 6: Configure CI/CD Integration

Now that installation is verified, integrate the runner into your CI/CD platform:

- [GitHub Actions](ci-cd-integration/github-actions.md)
- [GitLab CI](ci-cd-integration/gitlab-ci.md)
- [Jenkins](ci-cd-integration/jenkins.md)
- [CircleCI](ci-cd-integration/circleci.md)
- [Generic Docker](ci-cd-integration/generic-docker.md)

## Security Best Practices

### Credential Management

- **Never commit** OAuth credentials to version control
- **Use secret management** provided by your CI/CD platform
- **Rotate secrets** regularly (every 90 days recommended)
- **Use least-privilege scopes** - only grant required permissions
- **Monitor access** via CloudWatch logs for suspicious activity

### Token Caching

The runner caches OAuth tokens to `.token_cache.json` to avoid unnecessary authentication requests:

- Cache file contains access token and expiration time
- Automatically refreshed when token expires
- Should be added to `.gitignore`
- Can be safely deleted to force re-authentication

### Network Security

- Ensure HTTPS is used for all API communication
- Verify SSL certificates are valid
- Use private networks when possible
- Restrict outbound network access to required endpoints only

## Next Steps

- Review [Configuration Reference](configuration.md) for all available options
- Explore [CLI Reference](cli-reference.md) for detailed usage examples
- Read [Best Practices](best-practices.md) for optimization and security guidance
- Check [Troubleshooting Guide](troubleshooting.md) for common issues

## Support

If you encounter issues during installation:

1. Check the [Troubleshooting Guide](troubleshooting.md)
2. Review [GitHub Issues](https://github.com/aws-samples/sample-nova-act-qa-studio/issues)
3. Contact your platform administrator
4. Enable verbose logging (`--verbose`) for detailed diagnostics
