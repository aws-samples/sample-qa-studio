# Local Execution

## Overview

Execute tests locally using Nova Act to test against localhost, staging, or any accessible URL. Local execution provides:

- Fast feedback during development
- Variable and base URL overrides
- Local artifact storage (videos, screenshots, logs)
- No remote execution records (optional)

---

## Prerequisites

### 1. Install Runner Dependencies

```bash
pip install qa-studio[runner]
```

### 2. Verify AWS Credentials

Nova Act requires AWS credentials for Bedrock access:

```bash
aws sts get-caller-identity
```

If not configured:

```bash
# Option 1: AWS SSO
aws sso login --profile your-profile

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."  # if using temporary credentials

# Option 3: AWS CLI configure
aws configure
```

### 3. Authenticate with QA Studio

```bash
qa-studio login
```

---

## Running a Single Test

### Basic Execution

```bash
qa-studio run --usecase-id <id>
```

### Against Localhost

```bash
qa-studio run --usecase-id <id> --base-url http://localhost:3000
```

### With Variable Overrides

```bash
qa-studio run --usecase-id <id> \
  --base-url http://localhost:3000 \
  --var username=testuser \
  --var environment=local
```

### With Verbose Logging

```bash
qa-studio run --usecase-id <id> \
  --base-url http://localhost:3000 \
  --verbose
```

### Local-Only Mode (No Remote Records)

```bash
qa-studio run --usecase-id <id> \
  --local-only \
  --base-url http://localhost:3000
```

**Use local-only when:**
- Testing during development
- You don't want execution history in QA Studio
- Running quick validation checks

---

## Running a Test Suite

### Basic Suite Execution

```bash
qa-studio run --suite-id <id>
```

### With Overrides

```bash
qa-studio run --suite-id <id> \
  --base-url http://localhost:3000 \
  --var username=testuser \
  --var environment=staging \
  --region us-east-1 \
  --model-id nova-act-v1.0
```

### Keep Artifacts Locally

By default, artifacts are cleaned up after upload. Keep them for debugging:

```bash
qa-studio run --suite-id <id> --keep-artifacts
```

Artifacts stored in: `~/.qa-studio/artifacts/<usecase-id>/`

---

## Command Reference

### Required Parameters

**One of:**
- `--usecase-id <id>` - Run a single test
- `--suite-id <id>` - Run a test suite

### Optional Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--base-url <url>` | Override starting URL for all tests | Test's configured URL |
| `--var <key>=<value>` | Override variable (repeatable) | Test's default values |
| `--region <region>` | AWS region for browser | us-east-1 |
| `--model-id <id>` | Nova Act model ID | nova-act-v1.0 |
| `--timeout <seconds>` | Global timeout | 3600 |
| `--verbose` | Enable debug logging | false |
| `--local-only` | Skip remote execution records | false |
| `--keep-artifacts` | Keep local artifacts after upload | false |
| `--format <json\|human>` | Output format | json |
| `--token-file <path>` | Custom token file path | ~/.qa-studio/token.json |

---

## Output Formats

### JSON (Default)

Structured output for programmatic parsing:

```bash
qa-studio run --usecase-id <id> --format json
```

**Output:**
```json
{
  "status": "success",
  "usecase_id": "abc123",
  "usecase_name": "Login Flow",
  "duration": 12.5,
  "steps": [
    {
      "step_number": 1,
      "step_type": "navigation",
      "instruction": "Navigate to login page",
      "status": "success",
      "duration": 2.3
    }
  ]
}
```

### Human-Readable

Formatted for terminal viewing:

```bash
qa-studio run --usecase-id <id> --format human
```

**Output:**
```
Test: Login Flow
  Status:   success
  Duration: 12.5s

Steps:
  ✔ Step 1: Navigate to login page (2.3s)
  ✔ Step 2: Enter credentials (3.1s)
  ✔ Step 3: Click Sign In (4.2s)
  ✔ Step 4: Verify dashboard (2.9s)

Artifacts: ~/.qa-studio/artifacts/abc123/
```

---

## Artifacts

After execution, artifacts are stored locally:

```
~/.qa-studio/artifacts/<execution-id>/
├── recording.webm          # Full browser session video
├── screenshot_step_1.png   # Screenshot at step 1
├── screenshot_step_2.png   # Screenshot at step 2
└── execution.log           # Detailed execution log
```

**Reviewing artifacts:**
1. Open `recording.webm` to watch the full test execution
2. Check `execution.log` for detailed step-by-step logs
3. Review screenshots to see the browser state at each step

---

## Common Patterns

### Pattern 1: Test Against Localhost

```bash
# Start your local server first
npm run dev  # or your local server command

# Run test against localhost
qa-studio run --usecase-id <id> \
  --base-url http://localhost:3000 \
  --verbose
```

### Pattern 2: Test Against Staging

```bash
qa-studio run --usecase-id <id> \
  --base-url https://staging.example.com \
  --var environment=staging
```

### Pattern 3: Quick Validation (No Remote Records)

```bash
qa-studio run --usecase-id <id> \
  --local-only \
  --base-url http://localhost:3000 \
  --keep-artifacts
```

### Pattern 4: Debug Failed Test

```bash
qa-studio run --usecase-id <id> \
  --base-url http://localhost:3000 \
  --verbose \
  --keep-artifacts \
  --format human
```

Then review:
1. Terminal output for step-by-step status
2. `~/.qa-studio/artifacts/<id>/recording.webm` for visual debugging
3. `~/.qa-studio/artifacts/<id>/execution.log` for detailed logs

---

## Exit Codes

Use exit codes in scripts:

- **0**: All tests passed
- **1**: One or more tests failed
- **2**: Runner error (authentication, configuration, execution failure)

**Example:**
```bash
if qa-studio run --usecase-id <id>; then
  echo "Test passed"
else
  echo "Test failed with exit code $?"
  exit 1
fi
```

---

## Troubleshooting

### Authentication Failure

**Error:**
```
Error: Not authenticated
```

**Fix:**
```bash
qa-studio login
```

### AWS Credentials Missing

**Error:**
```
RunnerError: No valid AWS session found
```

**Fix:**
```bash
aws sts get-caller-identity  # Verify credentials
aws sso login --profile your-profile  # Re-authenticate if needed
```

### Test Not Found

**Error:**
```
Error: Use case not found
```

**Fix:**
```bash
qa-studio tests list  # Verify test ID
```

### Step Execution Failure

**Error:**
```
✘ Step 3/6 failed: Element not found
```

**Fix:**
1. Verify base URL is correct and accessible
2. Review video: `~/.qa-studio/artifacts/<id>/recording.webm`
3. Check if UI has changed since test was created
4. Re-run with `--verbose` for detailed logs

### Runner Dependencies Missing

**Error:**
```
Runner dependencies not installed
```

**Fix:**
```bash
pip install qa-studio[runner]
```

---

## Next Steps

- **Organize tests into suites:** [📦 Test Suites](./test-suites.md)
- **Set up CI/CD:** [🔄 CI/CD Integration](./ci-cd-integration.md)
- **Troubleshoot issues:** [🔧 Troubleshooting](./troubleshooting.md)
