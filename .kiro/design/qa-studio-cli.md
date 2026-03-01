# QA Studio CLI with Kiro Skills - Product Design Document

## Overview

Bring QA Studio test creation and execution capabilities directly into the Kiro IDE development workflow through a standalone CLI tool and Agent Skills, enabling the Kiro AI agent to autonomously create, manage, and execute UI tests during development.

## Problem Statement

Developers currently must:
1. Switch context from IDE to QA Studio web interface to create tests
2. Manually create test cases after writing code
3. Wait for CI/CD to discover issues that could be caught during development

**Goal:** Enable Kiro agent to create and execute tests as part of the development process, catching issues before commit.

## Architecture

**Approach:** Standalone CLI tool with Agent Skills

**Components:**
1. **CLI Tool** - Handles authentication, wraps API, executes tests
2. **Agent Skills** - Markdown files that guide Kiro on using the CLI
3. **CI/CD Runner** - Existing runner enhanced with token file support

**Why this approach:**
- Simple implementation - No VS Code extension, no MCP server
- Works standalone - Not tied to any IDE
- Token efficient - Skills use progressive disclosure
- Easy iteration - Edit markdown, not code
- Better for agents - Skills designed for AI workflows
- Reuses existing runner - Minimal changes needed

## User Personas

### Primary: Developer using Kiro IDE
- Writes application code
- Wants automated test coverage without context switching
- Needs immediate feedback on code changes

### Secondary: Kiro AI Agent
- Analyzes code changes
- Creates appropriate test cases
- Executes tests and reports results

## Core Components

### 1. QA Studio CLI Tool

**Installation:**
```bash
pip install qa-studio-cli
```

**Commands:**
```bash
# Setup
qa-studio setup          # Install skills to ~/.kiro/skills/
qa-studio login          # OAuth authentication
qa-studio status         # Check auth + skills status
qa-studio uninstall      # Remove skills

# Test Management
qa-studio tests list
qa-studio tests get <id>
qa-studio tests create --from-journey "User logs in..."
qa-studio tests delete <id>

# Local Execution
qa-studio run <usecase-id> \
  --base-url http://localhost:3000 \
  --var username=testuser

# Suite Management
qa-studio suites list
qa-studio run-suite <suite-id>
```

**Project Structure:**
```
qa-studio-cli/
├── src/
│   ├── auth/
│   │   ├── oauth.py          # Browser-based OAuth flow
│   │   └── token_manager.py  # Token storage/refresh
│   ├── api/
│   │   └── client.py         # API wrapper (uses token file)
│   ├── runner/
│   │   └── executor.py       # Wraps qa-studio-ci-runner
│   ├── setup/
│   │   └── skills.py         # Skill installation
│   └── cli.py                # Main CLI entry point
├── skills/
│   ├── qa-studio-tests/
│   │   ├── SKILL.md
│   │   ├── reference/
│   │   │   ├── step-types.md
│   │   │   └── validation-operators.md
│   │   └── scripts/
│   │       └── execute_local.py
│   └── qa-studio-suites/
│       └── SKILL.md
├── qa-studio-ci-runner/      # Existing runner (bundled)
└── setup.py
```

### 2. Authentication

**OAuth Flow:**
1. User runs `qa-studio login`
2. CLI opens browser to Cognito hosted UI
3. User authenticates with existing QA Studio credentials
4. CLI receives callback with authorization code
5. CLI exchanges code for tokens
6. Tokens stored in `~/.qa-studio/token.json`

**Token Storage:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_at": 1234567890,
  "token_type": "Bearer"
}
```

**Token Usage:**
- CLI reads token from file for API calls
- CI/CD runner reads token from file (new `--token-file` flag)
- Auto-refresh when expired

### 3. Agent Skills

**Skills installed to:** `~/.kiro/skills/` (via symlinks)

**Available Skills:**
- `qa-studio-tests` - Create and manage tests
- `qa-studio-suites` - Manage test suites

**How Kiro loads skills:**
1. User runs `qa-studio setup`
2. CLI creates symlinks in `~/.kiro/skills/`
3. Kiro IDE automatically loads skills from this directory
4. Skills reference CLI commands

### 4. CI/CD Runner Integration

**Existing runner enhanced with:**
- `--token-file` flag - Read token from file instead of client credentials
- `--usecase-id` flag - Execute single use case
- `--local-only` flag - Skip execution records and S3 uploads

**CLI wraps runner:**
```python
# qa-studio-cli/src/runner/executor.py
def execute_local(usecase_id, base_url=None, variables=None):
    cmd = [
        'python', '-m', 'qa_studio_ci_runner',
        '--usecase-id', usecase_id,
        '--local-only',
        '--token-file', '~/.qa-studio/token.json'
    ]
    
    if base_url:
        cmd.extend(['--base-url', base_url])
    
    for key, value in (variables or {}).items():
        cmd.extend(['--var', f'{key}={value}'])
    
    subprocess.run(cmd)
```

## Agent Skills Specification

### qa-studio-tests Skill

**File:** `skills/qa-studio-tests/SKILL.md`

```markdown
---
name: qa-studio-tests
description: Create and manage QA Studio UI tests. Use when developer asks to create tests, mentions testing/QA, or wants to verify functionality. Supports AI-generated tests from user journeys and manual step-by-step creation.
---

# QA Studio Test Management

## Prerequisites

Check authentication status:
```bash
qa-studio status
```

If not authenticated, tell user to run: `qa-studio login`

## Creating Tests

### AI-Generated (Recommended)

Generate complete tests from natural language user journeys:

```bash
qa-studio tests create --from-journey \
  --title "Login Flow" \
  --url "https://app.com/login" \
  --journey "User enters credentials, clicks login, verifies dashboard loads" \
  --region us-east-1
```

**When to use:**
- Developer describes what they want to test
- Creating new test from scratch
- Testing complete user flow

**Tips for good user journeys:**
- Be specific about actions (click, type, select)
- Include expected outcomes (verify, check, ensure)
- Mention element descriptions (login button, username field)

### Manual Creation

For step-by-step control, see [reference/manual-creation.md](reference/manual-creation.md)

## Executing Tests Locally

Run tests against localhost or staging:

```bash
# Test against localhost
qa-studio run <usecase-id> --base-url http://localhost:3000

# Test with variable overrides
qa-studio run <usecase-id> \
  --base-url http://localhost:3000 \
  --var username=testuser \
  --var environment=local
```

**Common patterns:**
- Developer says "test against localhost" → Use `--base-url http://localhost:3000`
- Developer says "test on staging" → Use `--base-url https://staging.example.com`
- Developer says "test with different user" → Use `--var username=testuser`

## Managing Tests

```bash
# List all tests
qa-studio tests list

# Get test details
qa-studio tests get <usecase-id>

# Delete test
qa-studio tests delete <usecase-id>
```

## Step Types

See [reference/step-types.md](reference/step-types.md) for complete guide on:
- navigation - Click buttons, fill forms
- validation - Check page values
- secret - Use stored credentials
- retrieve_value - Capture values into variables
- assertion - Compare captured variables
- url - Navigate to URL
- download - Download files

## Validation Operators

See [reference/validation-operators.md](reference/validation-operators.md) for:
- String operators: exact, contains, not_equal
- Number operators: equals, less_then, greater_then
- Boolean operators: exact
```

**Reference files:**

`skills/qa-studio-tests/reference/step-types.md` - Detailed step type documentation
`skills/qa-studio-tests/reference/validation-operators.md` - Complete operator reference
`skills/qa-studio-tests/reference/manual-creation.md` - Manual test creation guide

### qa-studio-suites Skill

**File:** `skills/qa-studio-suites/SKILL.md`

```markdown
---
name: qa-studio-suites
description: Manage QA Studio test suites. Use when developer wants to group tests, run multiple tests together, or organize test collections.
---

# QA Studio Test Suite Management

## Prerequisites

Check authentication: `qa-studio status`

## Creating Suites

```bash
qa-studio suites create \
  --name "Smoke Tests" \
  --description "Critical path tests"
```

## Adding Tests to Suite

```bash
qa-studio suites add-tests <suite-id> \
  --tests <usecase-id-1> <usecase-id-2>
```

## Executing Suites

```bash
# Run entire suite
qa-studio run-suite <suite-id>

# Run with base URL override
qa-studio run-suite <suite-id> --base-url http://localhost:3000
```

## Managing Suites

```bash
# List all suites
qa-studio suites list

# Get suite details
qa-studio suites get <suite-id>

# Remove test from suite
qa-studio suites remove-test <suite-id> <usecase-id>
```
```

## User Experience

### Installation & Setup

```bash
# Install CLI
$ pip install qa-studio-cli

# Setup skills (creates symlinks)
$ qa-studio setup
✓ Installed qa-studio-tests
✓ Installed qa-studio-suites

✓ Installed 2 skill(s) to ~/.kiro/skills/

Next steps:
  1. Run 'qa-studio login' to authenticate
  2. Use Kiro IDE to create and run tests

# Authenticate
$ qa-studio login
Opening browser for authentication...
✓ Logged in successfully

# Check status
$ qa-studio status
✓ Authenticated

Skills:
  ✓ qa-studio-tests
  ✓ qa-studio-suites
```

### Daily Workflow with Kiro

```
Developer: "Create a test for the login flow"

Kiro: [Loads qa-studio-tests skill]
      [Reads SKILL.md to understand capabilities]
      [Calls: qa-studio tests create --from-journey ...]
      
      "I've created a login test. Would you like to run it?"

Developer: "Yes, test it against localhost"

Kiro: [Calls: qa-studio run <id> --base-url http://localhost:3000]
      
      "Test passed! ✓
       - Step 1: Navigate to login (2.1s)
       - Step 2: Enter credentials (3.4s)
       - Step 3: Click login (1.8s)
       - Step 4: Verify dashboard (5.2s)
       
       Artifacts: /tmp/qa-studio-artifacts/<id>/"
```

### Error Handling

**Not authenticated:**
```
Developer: "Create a test"
Kiro: [Tries to call qa-studio tests create]
      [Gets error: Not authenticated]
      
      "You need to authenticate first. Run: qa-studio login"
```

**Skills not installed:**
```
Developer: "Create a test"
Kiro: [No qa-studio-tests skill found]
      
      "QA Studio skills not found. Run: qa-studio setup"
```

## Technical Requirements

### Prerequisites
- Python 3.11+ installed locally
- AWS credentials configured (for Nova Act)
- Valid QA Studio account
- Kiro IDE installed

### Dependencies
- `click` - CLI framework
- `requests` - HTTP client
- `boto3` - AWS SDK (for runner)
- Existing `qa-studio-ci-runner` package (bundled)

### Configuration

**Cognito OAuth:**
- App Client Type: Public
- OAuth Flows: Authorization code grant
- Scopes: openid, profile, email
- Callback URL: `http://localhost:8080/callback` (CLI local server)

**Token Storage:**
- Location: `~/.qa-studio/token.json`
- Permissions: 600 (owner read/write only)
- Format: JSON with access_token, refresh_token, expires_at

**Skills Installation:**
- Location: `~/.kiro/skills/` (symlinks)
- Created by: `qa-studio setup` command
- Removed by: `qa-studio uninstall` command

## CI/CD Runner Enhancement

### Required Changes

**Add to `qa-studio-ci-runner/src/cli/parser.py`:**
```python
@click.option('--token-file', help='Path to token file (alternative to client credentials)')
```

**Modify `qa-studio-ci-runner/src/auth/oauth_client.py`:**
```python
def __init__(self, client_id=None, client_secret=None, token_file=None):
    if token_file:
        self.token = self._load_token_from_file(token_file)
    else:
        self.client_id = client_id
        self.client_secret = client_secret

def _load_token_from_file(self, token_file):
    with open(Path(token_file).expanduser()) as f:
        data = json.load(f)
        return data['access_token']
```

**Existing flags (already implemented):**
- ✅ `--base-url` - Override starting URL
- ✅ `--var` - Variable overrides (repeatable)
- ✅ `--region` - AWS region override
- ✅ `--model-id` - Model override

**New flags (to be added):**
- `--usecase-id` - Execute single use case
- `--local-only` - Skip execution records and S3 uploads
- `--token-file` - Read token from file

## Implementation Timeline

### Phase 1: CLI Foundation (Week 1-2)
**Goal:** Working CLI with authentication

**Tasks:**
1. CLI project scaffold (setup.py, entry points)
2. OAuth flow implementation (browser-based)
3. Token storage and refresh
4. Basic commands: login, logout, status
5. Bundle existing CI/CD runner

**Deliverable:** `qa-studio-cli` installable via pip, authentication working

**Success Criteria:**
- ✅ `pip install qa-studio-cli` works
- ✅ `qa-studio login` opens browser and completes OAuth
- ✅ Token stored in `~/.qa-studio/token.json`
- ✅ `qa-studio status` shows auth status

---

### Phase 2: Runner Integration (Week 2-3)
**Goal:** Local test execution working

**Tasks:**
1. Add `--token-file` flag to runner
2. Add `--usecase-id` flag to runner
3. Add `--local-only` flag to runner
4. Modify runner auth client to support token file
5. CLI wrapper for runner execution
6. Test local execution end-to-end

**Deliverable:** `qa-studio run` executes tests locally

**Success Criteria:**
- ✅ `qa-studio run <id>` executes test
- ✅ `--base-url` override works
- ✅ `--var` overrides work
- ✅ Artifacts stored locally
- ✅ Results displayed to user

---

### Phase 3: Skills Creation (Week 3-4)
**Goal:** Kiro can use QA Studio via skills

**Tasks:**
1. Create `qa-studio-tests` skill
   - SKILL.md with concise instructions
   - Reference files for step types, operators
   - Examples and common patterns
2. Create `qa-studio-suites` skill
   - Suite management instructions
   - Execution patterns
3. Implement `qa-studio setup` command
4. Implement `qa-studio uninstall` command
5. Test skills with Kiro IDE

**Deliverable:** Skills working with Kiro IDE

**Success Criteria:**
- ✅ `qa-studio setup` creates symlinks
- ✅ Kiro loads skills automatically
- ✅ Kiro can create tests via skills
- ✅ Kiro can execute tests via skills
- ✅ Skills use progressive disclosure effectively

---

### Phase 4: API Wrapper Commands (Week 4-5)
**Goal:** Complete CLI functionality

**Tasks:**
1. Implement `qa-studio tests` commands
   - list, get, create, delete
2. Implement `qa-studio suites` commands
   - list, get, create, add-tests, remove-test
3. Error handling and user feedback
4. Documentation and examples

**Deliverable:** Full CLI functionality

**Success Criteria:**
- ✅ All test management commands work
- ✅ All suite management commands work
- ✅ Error messages are helpful
- ✅ Documentation complete

---

### Phase 5: Polish & Release (Week 5-6)
**Goal:** Production-ready release

**Tasks:**
1. Comprehensive testing
2. README and user guide
3. PyPI package preparation
4. Demo video/screenshots
5. Release v1.0.0

**Deliverable:** Published to PyPI

**Success Criteria:**
- ✅ Published to PyPI
- ✅ Documentation complete
- ✅ Demo materials available
- ✅ All tests passing

## Work Packages

### Package 1: CLI Foundation & Auth
**Duration:** Week 1-2 (7-10 days)  
**Spec Location:** `.kiro/specs/qa-studio-cli/wp1-cli-foundation.md`

**Objective:**
Create standalone CLI tool with OAuth authentication and token management.

**Scope:**
- CLI project scaffold with setup.py
- OAuth flow (browser-based with local callback server)
- Token storage in `~/.qa-studio/token.json`
- Commands: login, logout, status
- Bundle existing CI/CD runner

**Files to Create:**
- `qa-studio-cli/setup.py`
- `qa-studio-cli/src/cli.py`
- `qa-studio-cli/src/auth/oauth.py`
- `qa-studio-cli/src/auth/token_manager.py`
- `qa-studio-cli/README.md`

**Success Criteria:**
- ✅ Installable via pip
- ✅ OAuth flow completes successfully
- ✅ Token stored with correct permissions (600)
- ✅ Token auto-refreshes when expired
- ✅ Status command shows auth state

**Dependencies:** None

---

### Package 2: Runner Integration
**Duration:** Week 2-3 (5-7 days)  
**Spec Location:** `.kiro/specs/qa-studio-cli/wp2-runner-integration.md`

**Objective:**
Enhance CI/CD runner to support single use case execution with both local-only and remote modes, and add token file authentication.

**Current State:**
- ✅ `--base-url` - Override starting URL
- ✅ `--var` - Variable overrides (repeatable)
- ✅ `--region` - AWS region override
- ✅ `--model-id` - Model override
- ✅ `--suite-id` - Test suite execution only
- ❌ No single use case execution
- ❌ No token file authentication

**Scope:**
- Add `--usecase-id` flag (mutually exclusive with `--suite-id`)
- Add `--local-only` flag (optional, works with `--usecase-id`)
- Add `--token-file` flag (alternative to client credentials)
- Implement single use case execution with two modes:
  - **Local-only mode** (`--local-only`): No execution records, no S3 uploads
  - **Remote mode** (default): Creates execution records, uploads artifacts
- CLI wrapper for runner execution

**Implementation Details:**

**1. Single Use Case Execution Modes:**

**Local-only mode** (`--usecase-id <id> --local-only`):
- Fetch use case definition directly:
  - `GET /usecase/{id}` - Get use case metadata
  - `GET /usecase/{id}/steps` - Get steps
  - `GET /usecase/{id}/variables` - Get variables
  - `GET /usecase/{id}/secrets` - Get secrets
- Execute with Nova Act locally
- Store artifacts in `/tmp/qa-studio-artifacts/<usecase-id>/`
- Skip: POST /execute, DynamoDB records, S3 uploads
- Return JSON with local artifact paths

**Remote mode** (`--usecase-id <id>` without `--local-only`):
- Call `POST /usecase/{id}/execute?trigger-type=ci_runner`
- Creates execution record in DynamoDB
- Fetch execution steps from API
- Execute with Nova Act
- Upload artifacts to S3
- Update execution status via API

**2. Token File Authentication:**

Add support for reading token from file instead of client credentials:
```python
# Current: Client credentials
--client-id <id> --client-secret <secret>

# New: Token file
--token-file ~/.qa-studio/token.json
```

**Files to Modify:**
- `qa-studio-ci-runner/src/cli/parser.py` - Add flags, make suite-id optional
- `qa-studio-ci-runner/src/auth/oauth_client.py` - Add token file support
- `qa-studio-ci-runner/src/main.py` - Add `run_usecase()` function
- `qa-studio-ci-runner/src/execution/engine.py` - Add local-only mode

**Files to Create:**
- `qa-studio-ci-runner/src/api/usecases.py` - UseCaseAPI class for direct fetching
- `qa-studio-cli/src/runner/executor.py` - CLI wrapper

**Testing:**
```bash
# Local-only execution
qa-studio-ci-runner --usecase-id <id> --local-only --token-file ~/.qa-studio/token.json

# Local-only with overrides
qa-studio-ci-runner --usecase-id <id> --local-only \
  --token-file ~/.qa-studio/token.json \
  --base-url http://localhost:3000 \
  --var username=testuser

# Remote execution (creates records)
qa-studio-ci-runner --usecase-id <id> --token-file ~/.qa-studio/token.json

# Suite execution (existing, should still work)
qa-studio-ci-runner --suite-id <id> --token-file ~/.qa-studio/token.json
```

**Success Criteria:**
- ✅ Runner accepts `--token-file` flag
- ✅ Runner can execute single use case with `--usecase-id`
- ✅ `--local-only` skips execution records and S3 uploads
- ✅ Without `--local-only`, creates execution records and uploads artifacts
- ✅ CLI can spawn runner and capture output
- ✅ Base URL and variable overrides work with use case execution
- ✅ Existing suite execution still works

**Dependencies:** Package 1 (auth working)

---

### Package 3: Agent Skills
**Duration:** Week 3-4 (7-10 days)  
**Spec Location:** `.kiro/specs/qa-studio-cli/wp3-agent-skills.md`

**Objective:**
Create Agent Skills for Kiro IDE integration.

**Scope:**
- Create `qa-studio-tests` skill
- Create `qa-studio-suites` skill
- Implement `qa-studio setup` command
- Implement `qa-studio uninstall` command
- Reference documentation files

**Files to Create:**
- `qa-studio-cli/skills/qa-studio-tests/SKILL.md`
- `qa-studio-cli/skills/qa-studio-tests/reference/step-types.md`
- `qa-studio-cli/skills/qa-studio-tests/reference/validation-operators.md`
- `qa-studio-cli/skills/qa-studio-tests/reference/manual-creation.md`
- `qa-studio-cli/skills/qa-studio-suites/SKILL.md`
- `qa-studio-cli/src/setup/skills.py`

**Success Criteria:**
- ✅ `qa-studio setup` creates symlinks in `~/.kiro/skills/`
- ✅ Skills follow Agent Skills best practices
- ✅ Skills use progressive disclosure
- ✅ Kiro can discover and use skills
- ✅ Skills reference CLI commands correctly

**Dependencies:** Package 2 (runner working)

---

### Package 4: API Wrapper Commands
**Duration:** Week 4-5 (5-7 days)  
**Spec Location:** `.kiro/specs/qa-studio-cli/wp4-api-commands.md`

**Objective:**
Implement CLI commands for test and suite management.

**Scope:**
- Test management commands
- Suite management commands
- API client wrapper
- Error handling

**Files to Create:**
- `qa-studio-cli/src/api/client.py`
- `qa-studio-cli/src/commands/tests.py`
- `qa-studio-cli/src/commands/suites.py`

**Commands to Implement:**
- `qa-studio tests list`
- `qa-studio tests get <id>`
- `qa-studio tests create --from-journey`
- `qa-studio tests delete <id>`
- `qa-studio suites list`
- `qa-studio suites get <id>`
- `qa-studio suites create`
- `qa-studio suites add-tests`
- `qa-studio suites remove-test`
- `qa-studio run-suite <id>`

**Success Criteria:**
- ✅ All commands work correctly
- ✅ API client handles authentication
- ✅ Error messages are helpful
- ✅ Commands follow CLI best practices

**Dependencies:** Package 1 (auth working)

---

### Package 5: Polish & Release
**Duration:** Week 5-6 (5-7 days)  
**Spec Location:** `.kiro/specs/qa-studio-cli/wp5-polish-release.md`

**Objective:**
Prepare for production release.

**Scope:**
- Comprehensive testing
- Documentation
- PyPI packaging
- Demo materials
- Release v1.0.0

**Deliverables:**
- README with installation and usage
- User guide with examples
- Demo video showing workflow
- PyPI package published

**Success Criteria:**
- ✅ All tests passing
- ✅ Documentation complete
- ✅ Published to PyPI
- ✅ Demo materials available
- ✅ No critical bugs

**Dependencies:** Packages 1-4 (all features complete)

## Release Strategy

```
v0.1.0 - CLI + Auth (Week 2)
v0.2.0 - Runner Integration (Week 3)
v0.3.0 - Skills (Week 4)
v0.9.0 - API Commands (Week 5)
v1.0.0 - Production Release (Week 6)
```



## Success Metrics

### Adoption
- CLI installs (PyPI downloads)
- Active users (daily/monthly)
- Skills usage in Kiro IDE

### Efficiency
- Time from code change to test creation
- Tests executed during development
- Issues caught before commit

### Quality
- Test execution success rate
- False positive rate
- Developer satisfaction score

## Appendix

### API Endpoints Used

**Use Cases:**
- `POST /usecase/generate` - Generate test from user journey (Bedrock AI)
- `GET /usecases` - List all test cases
- `POST /usecase` - Create blank test case
- `GET /usecase/{id}` - Get test case
- `PATCH /usecase/{id}` - Update test case
- `DELETE /usecase/{id}` - Delete test case
- `POST /usecase/{id}/clone` - Clone test case
- `GET /usecase/{id}/steps` - Get steps (for local execution)
- `GET /usecase/{id}/variables` - Get variables (for local execution)
- `GET /usecase/{id}/secrets` - Get secrets (for local execution)

**Test Suites:**
- `GET /test-suites` - List suites
- `POST /test-suites` - Create suite
- `GET /test-suites/{id}` - Get suite
- `POST /test-suites/{id}/usecases` - Add tests to suite
- `DELETE /test-suites/{id}/usecases/{usecaseId}` - Remove test from suite
- `POST /test-suites/{id}/execute` - Execute suite

### Cognito Configuration
- App Client Type: Public
- OAuth Flows: Authorization code grant
- Scopes: openid, profile, email
- Callback URL: `http://localhost:8080/callback` (CLI local server)

### File Structure
```
qa-studio-cli/
├── src/
│   ├── auth/
│   │   ├── oauth.py
│   │   └── token_manager.py
│   ├── api/
│   │   └── client.py
│   ├── runner/
│   │   └── executor.py
│   ├── setup/
│   │   └── skills.py
│   ├── commands/
│   │   ├── tests.py
│   │   └── suites.py
│   └── cli.py
├── skills/
│   ├── qa-studio-tests/
│   │   ├── SKILL.md
│   │   └── reference/
│   └── qa-studio-suites/
│       └── SKILL.md
├── qa-studio-ci-runner/
├── setup.py
└── README.md
```
