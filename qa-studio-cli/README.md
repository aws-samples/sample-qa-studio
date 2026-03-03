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

### Kiro IDE Integration

- `qa-studio setup` - Install QA Studio skills for Kiro IDE
- `qa-studio uninstall` - Remove QA Studio skills from Kiro IDE

## Configuration

Running `qa-studio configure` stores settings in `~/.qa-studio/config.json`.

You can override any config value with environment variables:

| Environment Variable         | Overrides       |
|------------------------------|-----------------|
| `QA_STUDIO_API_URL`         | API base URL    |
| `QA_STUDIO_COGNITO_DOMAIN`  | Cognito domain  |
| `QA_STUDIO_CLIENT_ID`       | Cognito client ID |

Environment variables take precedence over file values.

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
| `--region` | Override AWS region for browser |
| `--model-id` | Override Nova Act model ID |
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
qa-studio run --usecase-id test-123 --region us-west-2 --model-id anthropic.claude-3-5-sonnet-20240620-v1:0
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
