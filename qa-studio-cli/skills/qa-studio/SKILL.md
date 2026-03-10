---
name: qa-studio
description: >
  Create, manage, and execute browser-based UI tests using QA Studio and Amazon Nova Act.
  Use when the developer wants to test web applications, create automated browser tests,
  run UI tests locally or in CI/CD, or verify frontend functionality.
  Covers test creation (AI-generated or manual), test suites, local execution with Nova Act,
  and CI/CD integration. NOT for unit tests or API tests — only browser-based UI automation.
---

# QA Studio — Browser Test Automation

## Overview

QA Studio enables AI-powered browser testing using Amazon Nova Act. Create tests in natural language, execute them locally or remotely, and organize them into suites for CI/CD integration.

**Core capabilities:**
- Create tests from natural language descriptions
- Execute tests locally with Nova Act
- Organize tests into suites
- Run tests in CI/CD pipelines
- Review execution results with videos and logs

---

## Quick Start

### Prerequisites Check

Before any operation, verify authentication:

```bash
qa-studio status
```

**Ready state:**
```
✓ Authenticated (token valid until 2025-07-01T12:00:00Z)
```

**Not ready:**
```bash
# First time setup
qa-studio configure  # Set API URL, Cognito domain, client ID
qa-studio login      # Authenticate via browser
```

---

## Decision Tree: What Do You Want To Do?

### 1. Create a New Test

**You have a clear description of what to test?**
→ Use AI generation: [📝 Creating Tests](./reference/creating-tests.md)

```bash
qa-studio tests create --from-journey \
  --title "Login Flow" \
  --url "https://app.example.com" \
  --journey "Navigate to login, enter credentials, verify dashboard loads" \
  --region us-east-1
```

**You want to build step-by-step interactively?**
→ Use the web interface's Interactive Wizard (see [🌐 Web Interface](./reference/web-interface.md))

### 2. Run Tests

**Run a single test locally?**
→ [▶️ Local Execution](./reference/local-execution.md)

```bash
qa-studio run --usecase-id <id> --base-url http://localhost:3000
```

**Run multiple tests together?**
→ Create a suite first: [📦 Test Suites](./reference/test-suites.md)

```bash
qa-studio suites create --name "Regression" --description "Core flows"
qa-studio suites add-tests <suite-id> <test-id-1> <test-id-2>
qa-studio run --suite-id <suite-id>
```

**Run tests in CI/CD?**
→ [🔄 CI/CD Integration](./reference/ci-cd-integration.md)

### 3. Manage Tests

**List, view, or delete tests?**
→ [🗂️ Managing Tests](./reference/managing-tests.md)

```bash
qa-studio tests list
qa-studio tests get <id>
qa-studio tests delete <id>
```

---

## Common Workflows

### Workflow 1: Create and Test Locally

```bash
# 1. Create test from description
qa-studio tests create --from-journey \
  --title "Checkout Flow" \
  --url "https://shop.example.com" \
  --journey "Add product to cart, proceed to checkout, verify order confirmation"

# 2. Run locally against localhost
qa-studio run --usecase-id <id> --base-url http://localhost:3000

# 3. Review artifacts (video, logs) in ~/.qa-studio/artifacts/<usecase-id>/
```

### Workflow 2: Build a Regression Suite

```bash
# 1. Create suite
qa-studio suites create \
  --name "Login Regression" \
  --description "All login and auth tests" \
  --tags regression,auth

# 2. Add existing tests
qa-studio suites add-tests <suite-id> <test-1> <test-2> <test-3>

# 3. Execute suite
qa-studio run --suite-id <suite-id>
```

### Workflow 3: CI/CD Integration

See [🔄 CI/CD Integration](./reference/ci-cd-integration.md) for complete setup with GitHub Actions, GitLab CI, and Jenkins.

---

## Reference Documentation

Load these as needed for detailed guidance:

### Core Operations
- [📝 Creating Tests](./reference/creating-tests.md) - AI generation, manual creation, templates
- [▶️ Local Execution](./reference/local-execution.md) - Run tests with Nova Act locally
- [📦 Test Suites](./reference/test-suites.md) - Group and batch execute tests
- [🗂️ Managing Tests](./reference/managing-tests.md) - List, view, update, delete

### Advanced Topics
- [🌐 Web Interface](./reference/web-interface.md) - Interactive Wizard, templates, execution history
- [🔄 CI/CD Integration](./reference/ci-cd-integration.md) - GitHub Actions, GitLab, Jenkins
- [🎯 Step Types](./reference/step-types.md) - Navigation, validation, secrets, assertions
- [✅ Validation Operators](./reference/validation-operators.md) - String, number, boolean comparisons
- [🔧 Troubleshooting](./reference/troubleshooting.md) - Common errors and solutions
- [📚 Best Practices](./reference/best-practices.md) - Writing reliable tests, prompting tips

---

## Key Concepts

### Tests (Use Cases)
A test defines:
- Starting URL
- Sequence of steps (in natural language)
- Expected outcomes
- Variables for parameterization

### Test Suites
Collections of tests that execute together. Used for:
- Regression testing
- Feature-specific test groups
- CI/CD pipelines

### Local Execution
Run tests on your machine using Nova Act:
- Test against localhost or staging
- Override variables and base URLs
- Review artifacts (videos, screenshots, logs)

### Remote Execution
Execute tests in AWS infrastructure:
- Scheduled runs
- CI/CD triggered
- Execution history and artifacts stored in S3

---

## Authentication Models

### User Authentication (Interactive)
For CLI and web interface:
```bash
qa-studio login  # Browser-based OAuth flow
```

### Machine-to-Machine (CI/CD)
For automated pipelines:
```bash
# Set environment variables
export OAUTH_CLIENT_ID="..."
export OAUTH_CLIENT_SECRET="..."
export OAUTH_TOKEN_ENDPOINT="..."
export API_ENDPOINT="..."

# Run without interactive login
qa-studio run --suite-id <id>
```

See [🔄 CI/CD Integration](./reference/ci-cd-integration.md) for complete setup.

---

## Error Handling

### Authentication Errors
```
Error: Not authenticated
```
**Fix:** Run `qa-studio login`

### Test Not Found
```
Error: Use case not found
```
**Fix:** Verify ID with `qa-studio tests list`

### Execution Failures
```
✘ Step 3/6 failed: Element not found
```
**Fix:** 
1. Review video in `~/.qa-studio/artifacts/<usecase-id>/recording.webm`
2. Verify base URL is correct
3. Check test steps match current UI

See [🔧 Troubleshooting](./reference/troubleshooting.md) for comprehensive error recovery.

---

## Examples

### Example 1: AI-Generated Test

```bash
qa-studio tests create --from-journey \
  --title "User Registration" \
  --url "https://app.example.com/signup" \
  --journey "Fill registration form with name 'John Doe', email 'john@example.com', password, click Submit, verify welcome message appears"
```

### Example 2: Local Execution with Overrides

```bash
qa-studio run --usecase-id abc123 \
  --base-url http://localhost:3000 \
  --var username=testuser \
  --var environment=local \
  --header "X-Api-Key=my-key" \
  --verbose
```

### Example 3: Suite Execution

```bash
qa-studio run --suite-id def456 \
  --base-url https://staging.example.com \
  --var environment=staging
```

---

## Next Steps

1. **First time?** Run `qa-studio configure` and `qa-studio login`
2. **Create your first test:** See [📝 Creating Tests](./reference/creating-tests.md)
3. **Run locally:** See [▶️ Local Execution](./reference/local-execution.md)
4. **Set up CI/CD:** See [🔄 CI/CD Integration](./reference/ci-cd-integration.md)