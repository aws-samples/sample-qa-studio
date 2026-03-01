# WP1: CLI Foundation & Auth

## Objective

Create standalone CLI tool with OAuth authentication and token management.

## Duration

Week 1-2 (7-10 days)

## Requirements

### 1. CLI Project Scaffold

**Create Python package structure:**
```
qa-studio-cli/
├── setup.py
├── README.md
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── cli.py
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── oauth.py
│   │   └── token_manager.py
│   └── utils/
│       ├── __init__.py
│       └── config.py
└── tests/
    └── __init__.py
```

**setup.py requirements:**
- Package name: `qa-studio-cli`
- Entry point: `qa-studio` command
- Dependencies: click, requests, boto3
- Python version: >=3.11

### 2. OAuth Authentication Flow

**Implementation: `src/auth/oauth.py`**

**Flow:**
1. User runs `qa-studio login`
2. CLI starts local HTTP server on `http://localhost:19847`
3. CLI opens browser to Cognito hosted UI with callback URL
4. User authenticates with QA Studio credentials
5. Cognito redirects to `http://localhost:19847/callback?code=...`
6. CLI exchanges authorization code for tokens
7. CLI stores tokens and shuts down local server

**Cognito Configuration:**
- App Client Type: Public
- OAuth Flows: Authorization code grant
- Scopes: openid, profile, email
- Callback URL: `http://localhost:19847/callback`

**Required Functions:**
```python
def start_oauth_flow() -> dict:
    """
    Start OAuth flow and return tokens.
    
    Returns:
        dict: {
            'access_token': str,
            'refresh_token': str,
            'expires_at': int,
            'token_type': str
        }
    """
    
def exchange_code_for_tokens(code: str) -> dict:
    """Exchange authorization code for tokens."""
    
def open_browser(auth_url: str) -> None:
    """Open browser to Cognito hosted UI."""
```

### 3. Token Management

**Implementation: `src/auth/token_manager.py`**

**Token Storage:**
- Location: `~/.qa-studio/token.json`
- Permissions: 600 (owner read/write only)
- Format:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_at": 1234567890,
  "token_type": "Bearer"
}
```

**Required Functions:**
```python
def save_token(token_data: dict) -> None:
    """Save token to file with correct permissions (600)."""
    
def load_token() -> dict | None:
    """Load token from file. Returns None if file doesn't exist."""
    
def is_token_expired(token_data: dict) -> bool:
    """Check if token is expired (compares expires_at against current time)."""
    
def refresh_access_token(refresh_token: str) -> dict:
    """
    Refresh access token using refresh token via Cognito token endpoint.
    Reads cognito_domain and client_id from config.
    Returns new token data dict.
    Raises AuthError if refresh token is also expired/revoked.
    """
    
def delete_token() -> None:
    """Delete token file."""

def get_valid_token() -> str:
    """
    Single entry point for all token consumers.
    
    1. Load token from file
    2. If not expired → return access_token
    3. If expired → attempt refresh using refresh_token
    4. If refresh succeeds → save new token, return new access_token
    5. If refresh fails (revoked/expired refresh token) → raise AuthError
       with message: "Session expired. Run 'qa-studio login' to re-authenticate."
    
    This is the ONLY function other modules should call to get a token.
    The OAuth flow, CLI commands, and future API client all use this.
    """
```

**Token refresh flow detail:**
- `get_valid_token()` adds a 30-second buffer to `expires_at` to avoid edge-case expiry during a request
- On successful refresh, the full token dict (including new `expires_at`) is saved back to disk
- If the refresh token itself is expired, Cognito returns a 400 with `invalid_grant` — this triggers the `AuthError`
- The `status` command calls `get_valid_token()` and catches `AuthError` to show the appropriate message

### 4. CLI Commands

**Implementation: `src/cli.py`**

**Commands to implement:**

#### `qa-studio login`
```bash
qa-studio login
```
- Start OAuth flow
- Save tokens
- Show success message

**Output:**
```
Opening browser for authentication...
✓ Logged in successfully
Token saved to ~/.qa-studio/token.json
```

#### `qa-studio logout`
```bash
qa-studio logout
```
- Delete token file
- Show confirmation

**Output:**
```
✓ Logged out successfully
```

#### `qa-studio status`
```bash
qa-studio status
```
- Check if token exists
- Check if token is expired
- Show authentication status

**Output (authenticated):**
```
✓ Authenticated
Token expires: 2026-03-01 14:30:00
```

**Output (not authenticated):**
```
✗ Not authenticated
Run 'qa-studio login' to authenticate
```

**Output (expired):**
```
✗ Token expired
Run 'qa-studio login' to re-authenticate
```

### 5. CI/CD Runner Dependency

The `qa-studio-ci-runner` already lives in this repository at `qa-studio-ci-runner/` (renamed from `cicd-runner/`). Rather than bundling or copying it, the CLI treats it as a system-level dependency that must be installed separately.

**Approach:**
- The `qa-studio-ci-runner` is installed into the Python environment via `pip install -e ./qa-studio-ci-runner` (or `pip install ./qa-studio-ci-runner`)
- The `qa-studio-cli` declares `qa-studio-ci-runner` as a dependency in `setup.py` but does NOT bundle the source
- The CLI invokes the runner via `python -m qa_studio_ci_runner` (subprocess) or imports it directly
- The README documents the installation steps clearly

**README must include:**
1. Install the runner first: `pip install -e ./qa-studio-ci-runner`
2. Install the CLI: `pip install -e ./qa-studio-cli`
3. Run initial setup: `qa-studio configure`

**Why this approach:**
- No code duplication
- Runner can be updated independently
- Both packages share the same Python environment
- Simple for developers who already have the repo cloned

## Files to Create

### Core Files
- `setup.py` - Package configuration
- `README.md` - Installation and usage instructions
- `requirements.txt` - Python dependencies
- `src/__init__.py` - Package initialization
- `src/cli.py` - CLI entry point with commands
- `src/auth/oauth.py` - OAuth flow implementation
- `src/auth/token_manager.py` - Token storage and refresh
- `src/utils/config.py` - Configuration management

### Test Files
- `tests/test_oauth.py` - OAuth flow tests
- `tests/test_token_manager.py` - Token management tests
- `tests/test_cli.py` - CLI command tests

### 6. Initial Configuration (`qa-studio configure`)

**Implementation: `src/cli.py` + `src/utils/config.py`**

On first use (or when running `qa-studio configure`), the CLI must collect and persist the environment-specific settings needed for OAuth and API calls.

**Interactive setup flow:**
```bash
$ qa-studio configure

QA Studio CLI Configuration
───────────────────────────
API URL [https://api.qa-studio.com]: https://my-api.example.com
Cognito Domain [https://auth.qa-studio.com]: https://my-auth.example.com
Cognito Client ID: abc123def456

✓ Configuration saved to ~/.qa-studio/config.json
```

**Behavior:**
- Prompts for each value with sensible defaults (shown in brackets)
- Cognito Client ID has no default and is required
- Validates URL format before saving
- Creates `~/.qa-studio/` directory if it doesn't exist
- Stores config with permissions 600

**Config file:** `~/.qa-studio/config.json`
```json
{
  "api_url": "https://my-api.example.com",
  "cognito_domain": "https://my-auth.example.com",
  "client_id": "abc123def456"
}
```

**Config resolution order (highest priority first):**
1. Environment variables (`QA_STUDIO_API_URL`, `QA_STUDIO_COGNITO_DOMAIN`, `QA_STUDIO_CLIENT_ID`)
2. Config file (`~/.qa-studio/config.json`)

**Guard on other commands:**
- `login`, `status`, `logout`, and all future commands must check that config exists
- If config is missing, print: `Configuration not found. Run 'qa-studio configure' first.`
- The `configure` command itself must always work without existing config

**Required Functions in `src/utils/config.py`:**
```python
def load_config() -> dict:
    """Load config from file, overlaid with env vars."""

def save_config(config: dict) -> None:
    """Save config to ~/.qa-studio/config.json with 600 permissions."""

def config_exists() -> bool:
    """Check if config file exists."""

def get_config_value(key: str) -> str:
    """Get a single config value (env var takes precedence over file)."""
```

## Testing

### Manual Testing

```bash
# Install in development mode
pip install -e .

# Test login
qa-studio login
# Should open browser, complete OAuth, save token

# Test status
qa-studio status
# Should show authenticated

# Test logout
qa-studio logout
# Should delete token

# Test status after logout
qa-studio status
# Should show not authenticated
```

### Automated Testing

```bash
# Run tests
pytest tests/

# Test coverage
pytest --cov=src tests/
```

### Test Cases

1. **OAuth Flow**
   - Local server starts successfully
   - Browser opens to correct URL
   - Authorization code is captured
   - Tokens are exchanged successfully
   - Server shuts down after callback

2. **Token Management**
   - Token saved with correct permissions (600)
   - Token loaded correctly
   - Expired token detected
   - Token refresh works
   - Token deletion works

3. **CLI Commands**
   - `login` command completes successfully
   - `logout` command removes token
   - `status` command shows correct state
   - Error messages are helpful

## Success Criteria

- ✅ CLI installable via `pip install -e .`
- ✅ `qa-studio configure` collects and persists API URL, Cognito domain, and client ID
- ✅ All commands (except `configure`) guard on config existence
- ✅ `qa-studio login` opens browser and completes OAuth flow
- ✅ Token saved to `~/.qa-studio/token.json` with permissions 600
- ✅ `get_valid_token()` transparently refreshes expired tokens
- ✅ `get_valid_token()` raises `AuthError` when refresh token is revoked/expired
- ✅ `qa-studio status` shows authentication state correctly (uses `get_valid_token()`)
- ✅ `qa-studio logout` removes token
- ✅ `qa-studio-ci-runner` installed as a separate pip dependency (documented in README)
- ✅ All tests passing (≥70% coverage)
- ✅ Error messages are clear and helpful

## Dependencies

### Prerequisite: Rename `cicd-runner` → `qa-studio-ci-runner` (COMPLETED)

The `cicd-runner/` directory has been renamed to `qa-studio-ci-runner/`. This included:
- Renamed directory `cicd-runner/` → `qa-studio-ci-runner/`
- Updated `setup.py` package name to `qa-studio-ci-runner`
- Renamed Python module `cicd_runner` → `qa_studio_ci_runner` (all internal imports)
- Updated `python -m cicd_runner` → `python -m qa_studio_ci_runner`
- Updated Dockerfile, Docker Compose references
- Updated any CI/CD pipeline configs
- Update root README and docs references
- Update `.kiro/specs/` references
- Run all existing tests to confirm nothing breaks

This rename should be completed and merged before WP1 implementation begins.

## Deliverable

Installable CLI package with working authentication:
```bash
# 1. Install qa-studio-ci-runner (from repo)
pip install -e ./qa-studio-ci-runner

# 2. Install CLI
pip install -e ./qa-studio-cli

# 3. Configure
qa-studio configure

# 4. Authenticate
qa-studio login
qa-studio status
```

## Next Steps

After completion, proceed to Package 2 (Runner Integration) to add test execution capabilities.
