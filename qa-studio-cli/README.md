# QA Studio CLI

A command-line tool for authenticating and managing QA Studio from the terminal. Uses browser-based OAuth (PKCE) against AWS Cognito for secure authentication.

## Prerequisites

- Python >= 3.11

## Installation

Install the CI runner first (separate dependency), then the CLI:

```bash
pip install -e ./qa-studio-ci-runner
pip install -e ./qa-studio-cli
```

## Quick Start

```bash
# Configure the CLI with your environment settings
qa-studio configure

# Authenticate via browser-based OAuth
qa-studio login

# Check authentication status
qa-studio status

# Log out (delete stored tokens)
qa-studio logout
```

## Configuration

Running `qa-studio configure` stores settings in `~/.qa-studio/config.json`.

You can override any config value with environment variables:

| Environment Variable         | Overrides       |
|------------------------------|-----------------|
| `QA_STUDIO_API_URL`         | API base URL    |
| `QA_STUDIO_COGNITO_DOMAIN`  | Cognito domain  |
| `QA_STUDIO_CLIENT_ID`       | Cognito client ID |

Environment variables take precedence over file values.

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
pytest --cov=src tests/
```
