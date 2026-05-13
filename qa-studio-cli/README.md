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

### With Bedrock AgentCore Browser Support

Use this when you want to provision remote browsers via Amazon Bedrock AgentCore — either locally against your own AgentCore setup, or inside the cloud worker image (which installs this extra at build time).

```bash
pip install -e "./qa-studio-cli[runner,agentcore]"
```

The `[agentcore]` extra pulls in `bedrock_agentcore`. Without it, `--browser=agentcore` raises a clear install-hint error at runtime.

### With Interactive Terminal UI

Adds the `textual` dependency so `qa-studio tui` launches an interactive browser for use cases and test suites. Safe to combine with the runner extra.

```bash
pip install -e "./qa-studio-cli[runner,tui]"
```

Without this extra, `qa-studio tui` prints an install hint and exits non-zero.

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

# Launch the interactive terminal UI (requires the [tui] extra)
qa-studio tui

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
- `qa-studio tests import <path>` - Import test cases from a JSON file or folder

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

## Importing Test Cases

The `qa-studio tests import` command imports test case JSON files (QA Studio export format) from a file or folder.

### Import Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `path` | positional | required | File or directory path to import |
| `--dry-run` | flag | `false` | Validate only, do not import |
| `--yes` / `-y` | flag | `false` | Skip confirmation prompt |
| `--base-url` | string | `None` | Override `starting_url` for all imports |
| `--skip-secrets` | flag | `false` | Skip interactive secret prompts |
| `--format` | choice | `human` | Output format: `human` or `json` |

### Examples

```bash
# Import a single test file
qa-studio tests import ./login_test.json

# Import all tests from a folder (recursive)
qa-studio tests import ./testcases/

# Dry-run: validate files without importing
qa-studio tests import ./testcases/ --dry-run

# Import with base URL override (e.g. staging)
qa-studio tests import ./testcases/ --base-url https://staging.example.com --yes

# CI pipeline: JSON output, skip secrets, no prompts
qa-studio tests import ./testcases/ --format json --skip-secrets

# Skip secrets and configure them later in the UI
qa-studio tests import ./login_test.json --skip-secrets
```

### Two-Phase Flow

1. **Scan & Validate**: All JSON files are discovered and validated against the export schema. A summary table shows valid/invalid files.
2. **Import**: After confirmation, valid files are sent to the API. Results are displayed per file.

In `--format json` mode, all prompts are suppressed and output is a single JSON object suitable for CI parsing.

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

### Runtime Header & Secret Overrides (local-only)

For iterating locally with a different bearer token, a rotated
secret, or a one-off feature-flag header — without editing the use
case. These flags apply **only** with `--local-only`; using them on
the remote path produces an error.

```bash
# Single inline header (non-sensitive values)
qa-studio run --usecase-id test-123 --local-only \
  --header X-Feature-Flag=debug

# Sensitive headers via file (Bearer tokens, cookie headers) —
# argv-safe so the value isn't visible in `ps` or shell history
cat > /tmp/headers.json <<EOF
{ "Authorization": "Bearer my-dev-token" }
EOF
qa-studio run --usecase-id test-123 --local-only \
  --headers-file /tmp/headers.json

# Secret overrides — file-only, never argv
cat > /tmp/secrets.json <<EOF
{ "admin_password": "newly-rotated-value" }
EOF
qa-studio run --usecase-id test-123 --local-only \
  --secrets-file /tmp/secrets.json
```

**Precedence on header collisions:** `API stored headers ← --headers-file ← --header flags`. The
right-most source wins. Secret overrides short-circuit the API
secret lookup by key — keys not listed in `--secrets-file` fall
through to the normal `GET /usecase/{id}/secrets/{key}/value` path.

## Interactive Terminal UI

`qa-studio tui` launches a [Textual](https://github.com/Textualize/textual)-based terminal UI for browsing use cases and test suites, inspecting their detail, and triggering **local** runs with a live log tail. It reuses the same API client and authentication chain as every other subcommand; existing CLI commands stay unchanged.

### Requirements

Install the `[tui]` extra (see Installation above). Without it the subcommand prints a pip-install hint and exits non-zero.

The TUI requires a valid token — run `qa-studio login` first. An expired token surfaces as a clear `Authentication required` message, not a stack trace.

### Launch

```bash
qa-studio tui
```

### Navigation

| Key      | Scope          | Action                                  |
|----------|----------------|-----------------------------------------|
| `q`      | Global         | Quit                                    |
| `1`      | Global         | Jump to Use cases list                  |
| `2`      | Global         | Jump to Test suites list                |
| `?`      | Global         | Help overlay (placeholder)              |
| `/`      | List screens   | Focus the client-side filter input      |
| `Enter`  | List screens   | Open the selected item's detail         |
| `r`      | List & detail  | Refresh from the API                    |
| `R`      | Use case detail| Open the Run form                       |
| `e`      | Use case detail| Open the use case in the web app        |
| `Esc`    | Detail / form  | Go back (confirm when a run is active)  |
| `k`/`^C` | Live tail      | Terminate the subprocess                |

### Features

| Feature                       | Notes                                                                                       |
|-------------------------------|---------------------------------------------------------------------------------------------|
| Use-case + suite lists        | Full lists with client-side substring filter on name + id (instant, no extra HTTP)          |
| Use-case detail header        | Name, active status, platform, region, model, URL, description, tags, creator, timestamps  |
| Steps tab                     | Vertical split (60/40): table left, live detail pane right. Cursor moves update the pane   |
| Step detail pane              | Empty fields hidden; nested `dict`/`list` values pretty-printed as JSON                    |
| Suite detail                  | Metadata + member use-cases table, Enter drills into the corresponding use case             |
| Run form                      | Pre-filled from the API; variables, headers, and secrets rendered as inputs (secrets masked)|
| Runtime overrides             | Changed fields become overrides; secrets delivered via `0600` tempfile, never argv          |
| Local-only / remote toggle    | Default **on**. Untick to create a remote execution record visible in the web app           |
| Verbose toggle                | Off by default — runner logs at INFO. Tick for DEBUG                                        |
| Live tail                     | Streams stdout/stderr line-by-line with `[stderr]` prefix; final status shows exit code     |
| Terminate                     | SIGTERM to the process group (kills Chromium/Playwright descendants); SIGKILL after 5 s     |
| Edit in browser               | `e` on the use case detail opens `{web_url}/usecase/{id}` via the default browser           |

### Configuring "Edit in browser"

The Edit action opens `{web_url}/usecase/<id>` in your default browser. Set `web_url` in `~/.qa-studio/config.json` — the interactive `qa-studio configure` prompt asks for it, or you can edit the JSON directly.

If `web_url` is unset, pressing `e` shows a notification pointing at `qa-studio configure` rather than silently failing.

### Out of scope for the POC

- In-TUI editing of use cases / suites / steps — use the web app via `e`
- Templates list / detail
- Live monitor for cloud-worker executions
- Pagination or server-side search (filter is client-side over the full result)
- Header / secret overrides with `Local only` unticked — enforced at submit time with a clear error

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
r qa-studio-cli/requirements-dev.txt
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
