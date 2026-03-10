# Test Suites

## Overview

Test suites group related tests for batch execution. Use suites for:
- Regression testing
- Feature-specific test collections
- CI/CD pipelines
- Scheduled test runs

---

## Creating Suites

```bash
qa-studio suites create \
  --name "Login Regression" \
  --description "All login and authentication tests" \
  --tags regression,auth
```

**Parameters:**
- `--name`: Suite name (required)
- `--description`: Suite description (required)
- `--tags`: Comma-separated tags (optional, repeatable)

---

## Adding Tests to Suites

### Add Single Test

```bash
qa-studio suites add-tests <suite-id> <test-id>
```

### Add Multiple Tests

```bash
qa-studio suites add-tests <suite-id> <test-1> <test-2> <test-3>
```

### Remove Test from Suite

```bash
qa-studio suites remove-test <suite-id> <test-id>
```

---

## Managing Suites

### List All Suites

```bash
qa-studio suites list
```

**Output:**
```
ID                                       Tests  Name
──────────────────────────────────────── ─────  ──────────────────
abc12345-def6-7890-ghij-klmnopqrstuv        5  Login Regression
def67890-abcd-1234-efgh-ijklmnopqrst        3  Checkout Flow
```

### Get Suite Details

```bash
qa-studio suites get <suite-id>
```

**Output:**
```
Name:           Login Regression
Description:    All login and authentication tests
Tags:           regression, auth
Total Usecases: 5
Created By:     admin@example.com
Created At:     2025-07-01T14:00:00Z

Usecases (5):
  abc123  Login with valid credentials
  def456  Login with invalid password
  ghi789  Password reset flow
  jkl012  Two-factor authentication
  mno345  Session timeout handling
```

---

## Executing Suites

### Basic Execution

```bash
qa-studio run --suite-id <id>
```

### With Overrides

```bash
qa-studio run --suite-id <id> \
  --base-url http://localhost:3000 \
  --var username=testuser \
  --var environment=local
```

### Via API (Remote Execution)

```bash
qa-studio suites run <suite-id> \
  --base-url https://staging.example.com \
  --var environment=staging \
  --region us-east-1
```

---

## Common Workflows

### Workflow 1: Build Regression Suite

```bash
# 1. Create suite
qa-studio suites create \
  --name "Core Regression" \
  --description "Critical user flows" \
  --tags regression,critical

# 2. Find tests to add
qa-studio tests list

# 3. Add tests
qa-studio suites add-tests <suite-id> <test-1> <test-2> <test-3>

# 4. Execute locally
qa-studio run --suite-id <suite-id> --base-url http://localhost:3000
```

### Workflow 2: Feature-Specific Suite

```bash
# Create suite for a specific feature
qa-studio suites create \
  --name "Checkout Feature" \
  --description "All checkout-related tests" \
  --tags checkout,e-commerce

# Add feature tests
qa-studio suites add-tests <suite-id> <checkout-test-1> <checkout-test-2>

# Run against staging
qa-studio run --suite-id <suite-id> \
  --base-url https://staging.example.com
```

---

## Next Steps

- **Run suites locally:** [▶️ Local Execution](./local-execution.md)
- **Set up CI/CD:** [🔄 CI/CD Integration](./ci-cd-integration.md)
- **Manage tests:** [🗂️ Managing Tests](./managing-tests.md)
