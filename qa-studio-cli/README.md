# QA Studio CLI

A command-line tool for authenticating, managing, and executing QA Studio tests from the terminal. Uses browser-based OAuth (PKCE) against AWS Cognito for secure authentication.

## Prerequisites

- Python >= 3.11

## Installation

### Basic Installation (Authentication & Management)

```bash
pip install -e ./qa-studio-cli
```

### Full Installation (with Local Test Execution)

```bash
pip install -e "./qa-studio-cli[runner]"
```

## Quick Start

```bash
# Configure the CLI with your environment settings
qa-studio configure

# Authenticate via browser-based OAuth
qa-studio login

# Check authentication status
qa-studio status

# Run a test locally
qa-studio run --usecase-id test-123

# Run a test suite
qa-studio run --suite-id suite-456

# Log out (delete stored tokens)
qa-studio logout
```

## Commands

### Authentication

- `qa-studio configure` - Interactive setup for API URL, Cognito domain, and client ID
- `qa-studio login` - Start browser-based OAuth flow and store tokens
- `qa-studio logout` - Delete stored tokens
- `qa-studio status` - Show current authentication status

### Test Management

- `qa-studio tests list` - List all tests
- `qa-studio tests create` - Create a new test
- `qa-studio tests get <id>` - Get test details
- `qa-studio tests update <id>` - Update a test
- `qa-studio tests delete <id>` - Delete a test

### Suite Management

- `qa-studio suites list` - List all test suites
- `qa-studio suites create` - Create a new suite
- `qa-studio suites get <id>` - Get suite details
- `qa-studio suites update <id>` - Update a suite
- `qa-studio suites delete <id>` - Delete a suite

### Test Execution

```bash
# Run a single test
qa-studio run --usecase-id test-123

# Run a test suite
qa-studio run --suite-id suite-456

# Run with base URL override
qa-studio run --usecase-id test-123 --base-url https://staging.example.com

# Run with variable overrides
qa-studio run --usecase-id test-123 --var username=testuser --var password=testpass

# Run in local-only mode (no remote records)
qa-studio run --usecase-id test-123 --local-only

# Run with verbose logging
qa-studio run --usecase-id test-123 --verbose
```

### Kiro IDE Skill Installation

QA Studio ships an agent skill for Kiro IDE (and other supported agents). Install it using the open [skills CLI](https://github.com/vercel-labs/skills):

**Prerequisites:**
- Node.js 18+ (for `npx`)

```bash
# Install the QA Studio skill into Kiro
npx skills add <repository-url> --skill qa-studio -a kiro-cli

# Or install globally (available across all projects)
npx skills add <repository-url> --skill qa-studio -a kiro-cli -g

# Verify installation
npx skills list
```

After installation, add the skill to your Kiro agent resources in `.kiro/agents/<agent>.json`:

```json
{
  "resources": ["skill://.kiro/skills/**/SKILL.md"]
}
```

To remove the skill:

```bash
npx skills remove qa-studio
```

The skill is also compatible with other agents (Claude Code, Cursor, Codex, etc.). See the [skills CLI docs](https://github.com/vercel-labs/skills) for the full list of supported agents.

## Configuration

Running `qa-studio configure` stores settings in `~/.qa-studio/config.json`.

You can override any config value with environment variables:

| Environment Variable         | Overrides              | Description |
|------------------------------|------------------------|-------------|
| `QA_STUDIO_API_URL`         | `api_url`              | API base URL |
| `QA_STUDIO_COGNITO_DOMAIN`  | `cognito_domain`       | Cognito domain |
| `QA_STUDIO_CLIENT_ID`       | `client_id`            | Cognito client ID |
| `OAUTH_CLIENT_ID`           | `oauth_client_id`      | OAuth M2M client ID |
| `OAUTH_CLIENT_SECRET`       | `oauth_client_secret`  | OAuth M2M client secret |
| `OAUTH_TOKEN_ENDPOINT`      | `oauth_token_endpoint` | Cognito token endpoint URL |

Environment variables take precedence over file values.

## Authentication

The CLI supports multiple authentication methods, resolved in this priority order:

1. **Token file** (`--token-file` flag) — pre-generated token JSON
2. **Environment variables** (`OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` / `OAUTH_TOKEN_ENDPOINT`) — M2M client credentials
3. **Config file M2M credentials** (`oauth_client_id` / `oauth_client_secret` / `oauth_token_endpoint` in `~/.qa-studio/config.json`)
4. **Stored user token** from `qa-studio login` (with auto-refresh)

### Interactive Login (Development)

```bash
qa-studio login    # Opens browser for Cognito hosted UI login
qa-studio status   # Check current auth status
qa-studio logout   # Delete stored tokens
```

### OAuth Client Credentials (CI/CD, Headless)

No browser login required. Set all three environment variables:

```bash
export OAUTH_CLIENT_ID="your-m2m-client-id"
export OAUTH_CLIENT_SECRET="your-m2m-client-secret"
export OAUTH_TOKEN_ENDPOINT="https://your-cognito-domain.auth.region.amazoncognito.com/oauth2/token"

qa-studio run --suite-id suite-456
```

Or add them to `~/.qa-studio/config.json`:

```json
{
  "api_url": "https://your-api-url",
  "cognito_domain": "https://your-cognito-domain.auth.region.amazoncognito.com",
  "client_id": "your-public-client-id",
  "oauth_client_id": "your-m2m-client-id",
  "oauth_client_secret": "your-m2m-client-secret",
  "oauth_token_endpoint": "https://your-cognito-domain.auth.region.amazoncognito.com/oauth2/token"
}
```

M2M tokens are cached in memory and automatically refreshed before expiry (5-minute buffer).

Granted scopes: `api/suite.read`, `api/suite.write`, `api/usecases.read`, `api/usecases.execute`, `api/executions.read`, `api/executions.write`.

### Token File

```bash
qa-studio run --token-file /path/to/token.json --usecase-id test-123
```

See [CI/CD Integration Guide](../docs/ci-cd-integration.md) for detailed pipeline examples.

## Local Test Execution

The `qa-studio run` command requires the runner dependencies:

```bash
pip install -e "./qa-studio-cli[runner]"
```

### Execution Options

| Option | Description |
|--------|-------------|
| `--usecase-id` | Single test ID to execute |
| `--suite-id` | Test suite ID to execute |
| `--local-only` | Local-only execution (no remote records) |
| `--base-url` | Override base URL for all tests |
| `--var` | Override variable (key=value, repeatable) |
| `--header` | Set HTTP header (key=value, repeatable, each key allowed once) |
| `--region` | Override AWS region for browser |
| `--model-id` | Override Nova Act model ID |
| `--user-agent` | Override browser User-Agent string |
| `--verbose` | Enable verbose logging |
| `--timeout` | Global timeout in seconds |
| `--keep-artifacts` | Keep local artifact files after upload |
| `--format` | Output format (json or human) |

### Examples

```bash
# Run test against staging environment
qa-studio run --usecase-id test-123 --base-url https://staging.example.com

# Run suite with variable overrides
qa-studio run --suite-id suite-456 --var env=staging --var user=testuser

# Run locally without creating remote execution records
qa-studio run --usecase-id test-123 --local-only

# Run with custom region and model
qa-studio run --usecase-id test-123 --region us-west-2 --model-id us.amazon.nova-2-lite-v1:0

# Run with custom HTTP headers
qa-studio run --usecase-id test-123 --header "X-Api-Key=my-key" --header "X-Custom-Header=value"

# Run with custom User-Agent
qa-studio run --usecase-id test-123 --user-agent "MyBot/1.0"
```

## Development

Install dev dependencies:

```bash
pip install -e ./qa-studio-cli
pip install -r qa-studio-cli/requirements-dev.txt
```

Run tests:

```bash
cd qa-studio-cli
pytest tests/
```

Run tests with coverage:

```bash
cd qa-studio-cli
pytest --cov=qa_studio_cli tests/
```
