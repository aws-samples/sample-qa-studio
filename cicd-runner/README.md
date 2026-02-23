# Nova Act QA Studio - CI/CD Runner

Python CLI application for executing Nova Act QA Studio test suites in CI/CD pipelines. The runner authenticates with OAuth client credentials, fetches test suite definitions, creates execution records, and prepares for automated test execution.

## Features

- OAuth 2.0 client credentials authentication with token caching
- Automatic token refresh on expiration
- Test suite execution via Platform API
- CLI argument parsing with variable overrides
- Comprehensive error handling and logging
- Secure credential management via environment variables

## Installation

### Prerequisites

- Python 3.9 to 3.12 (Python 3.13+ is not yet supported due to dependency compatibility)
- pip

### Setting Up a Virtual Environment

If you have multiple Python versions installed (e.g. via pyenv), make sure the venv is created with a compatible version:

```bash
cd cicd-runner

# Option A: If pyenv is configured and 3.12 is your local version
pyenv local 3.12.0
python -m venv venv

# Option B: Use the explicit pyenv path (avoids shell shim issues)
~/.pyenv/versions/3.12.0/bin/python -m venv venv

# Activate
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Verify
python --version  # Should show 3.12.x

# Install dependencies
pip install -r requirements.txt
```

### From Source (editable install)

```bash
cd cicd-runner
pip install -e .
```

### From Package

```bash
pip install cicd-runner
```

## Configuration

### Required Environment Variables

The runner requires the following environment variables to be set:

```bash
# OAuth credentials from Cognito
export OAUTH_CLIENT_ID="your-client-id"
export OAUTH_CLIENT_SECRET="your-client-secret"

# Cognito token endpoint
export OAUTH_TOKEN_ENDPOINT="https://your-domain.auth.us-east-1.amazoncognito.com/oauth2/token"

# Platform API endpoint
export API_ENDPOINT="https://your-api-id.execute-api.us-east-1.amazonaws.com/api"
```

### Optional Environment Variables

```bash
# Logging level (default: INFO)
export LOG_LEVEL="DEBUG"
```

### Using .env File

Create a `.env` file in your working directory:

```bash
cp .env.example .env
# Edit .env with your credentials
```

The runner will automatically load environment variables from `.env` if present.

## OAuth Client Setup

Before using the runner, you need to create an OAuth client in the Nova Act QA Studio platform:

1. **Login to Nova Act QA Studio** web interface
2. **Navigate to Settings** → OAuth Clients
3. **Create New Client**:
   - Name: "CI/CD Runner"
   - Grant Type: Client Credentials
   - Scopes: `api/suite.read`, `api/suite.write`, `api/usecases.read`, `api/usecases.execute`, `api/executions.read`, `api/executions.write`
4. **Save credentials**:
   - Copy the Client ID
   - Copy the Client Secret (shown only once)
5. **Set environment variables** with the credentials

## Usage

### Basic Usage

Execute a test suite by ID:

```bash
cicd-runner --suite-id 01234567-89ab-cdef-0123-456789abcdef
```

### With Variable Overrides

Override test suite variables:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --var username=testuser \
  --var password=testpass \
  --var environment=staging
```

### With Base URL Override

Override the base URL for all use cases:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com
```

### With Region and Model Overrides

Override AWS region and Bedrock model:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --region us-west-2 \
  --model-id anthropic.claude-3-5-sonnet-20240620-v1:0
```

### With Verbose Logging

Enable detailed debug logging:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --verbose
```

### With Custom Timeout

Set global timeout in seconds (default: 3600):

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --timeout 7200
```

### Complete Example

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com \
  --var username=testuser \
  --var password=testpass \
  --region us-west-2 \
  --model-id anthropic.claude-3-5-sonnet-20240620-v1:0 \
  --timeout 7200 \
  --verbose
```

## CLI Options

| Option | Required | Description | Default |
|--------|----------|-------------|---------|
| `--suite-id` | Yes | Test suite UUID to execute | - |
| `--base-url` | No | Override base URL for all use cases | - |
| `--var` | No | Override variable (key=value, repeatable) | - |
| `--region` | No | Override AWS region for browser | - |
| `--model-id` | No | Override Nova Act model ID | - |
| `--verbose` | No | Enable verbose logging (DEBUG level) | False |
| `--timeout` | No | Global timeout in seconds | 3600 |
| `--help` | No | Show help message and exit | - |

## Exit Codes

- `0`: Success - test suite execution created successfully
- `2`: Failure - authentication, API, or configuration error

## Token Caching

The runner caches OAuth tokens to `.token_cache.json` in the current directory to avoid unnecessary authentication requests. The cache file:

- Contains the access token and expiration time
- Is automatically refreshed when the token expires
- Should be added to `.gitignore` (already included)
- Can be safely deleted to force re-authentication

## Troubleshooting

### Authentication Errors

**Error**: `AuthenticationError: OAuth authentication failed: 401`

**Solution**:
- Verify `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET` are correct
- Check that the OAuth client exists in the platform
- Ensure the client has the required scopes

### Configuration Errors

**Error**: `ConfigurationError: Missing required environment variables`

**Solution**:
- Verify all required environment variables are set
- Check for typos in variable names
- Ensure `.env` file is in the current directory (if using)

### API Errors

**Error**: `APIError: API request failed: 403 - Missing required scopes`

**Solution**:
- Verify OAuth client has scopes: `api/suite.read`, `api/suite.write`, `api/usecases.read`, `api/usecases.execute`, `api/executions.read`, `api/executions.write`
- Recreate the OAuth client with correct scopes

**Error**: `APIError: API request failed: 404 - Test suite not found`

**Solution**:
- Verify the suite ID is correct
- Check that the test suite exists in the platform
- Ensure you have access to the test suite

### Network Errors

**Error**: `AuthenticationError: OAuth authentication failed: Connection timeout`

**Solution**:
- Check network connectivity
- Verify the `OAUTH_TOKEN_ENDPOINT` URL is correct
- Check firewall rules allow HTTPS connections

## Development

### Running Tests

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run property-based tests
pytest -k property
```

### Project Structure

```
cicd-runner/
├── src/
│   ├── auth/          # OAuth authentication
│   ├── api/           # API client
│   ├── cli/           # CLI argument parsing
│   ├── config/        # Configuration management
│   └── utils/         # Utilities and errors
├── tests/             # Unit and property tests
├── requirements.txt   # Runtime dependencies
├── requirements-dev.txt  # Development dependencies
├── setup.py          # Package setup
└── README.md         # This file
```

## Security

- Never commit `.token_cache.json` or `.env` files to version control
- Store OAuth credentials securely (use secrets management in CI/CD)
- Rotate OAuth client secrets regularly
- Use least-privilege scopes for OAuth clients
- Review CloudWatch logs for suspicious activity

## License

This project is licensed under the MIT-0 License. See the LICENSE file for details.
