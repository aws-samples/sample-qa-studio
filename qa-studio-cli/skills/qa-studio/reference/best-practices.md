# Best Practices

## Writing Reliable Tests

### 1. Be Specific in Instructions

**Bad:**
```
"Log in"
```

**Good:**
```
"Enter 'admin@example.com' into the email field"
"Enter password from secret 'admin_password'"
"Click the button labeled 'Sign In'"
```

**Why:** Specific instructions reduce ambiguity and improve test reliability.

---

### 2. Use Visible Element Descriptions

**Bad:**
```
"Click #submit-btn"
"Find element with class .login-form"
```

**Good:**
```
"Click the Submit button"
"Find the login form"
```

**Why:** Nova Act works with natural language, not CSS selectors.

---

### 3. Include Validation Steps

**Bad:**
```
1. Click Login
2. Enter credentials
3. Click Submit
```

**Good:**
```
1. Click Login
2. Enter credentials
3. Click Submit
4. Verify dashboard heading is visible
5. Verify URL contains '/dashboard'
```

**Why:** Validation confirms expected outcomes and catches failures early.

---

### 4. Use Secrets for Sensitive Data

**Bad:**
```
"Enter 'MyPassword123' into password field"
```

**Good:**
```
"Enter password from secret 'admin_password'"
```

**Why:** Secrets are never logged or recorded, protecting sensitive data.

---

### 5. Parameterize with Variables

**Bad:**
```
"Navigate to https://app.example.com/login"
```

**Good:**
```
"Navigate to {{base_url}}/login"
```

**Why:** Variables enable testing across environments (localhost, staging, production).

---

## Test Organization

### 1. Group Related Tests into Suites

```bash
# Create feature-specific suites
qa-studio suites create --name "Auth Tests" --tags auth
qa-studio suites create --name "Checkout Tests" --tags checkout

# Add tests to suites
qa-studio suites add-tests <auth-suite-id> <login-test> <signup-test>
```

**Why:** Suites enable batch execution and better organization.

---

### 2. Use Descriptive Names and Tags

**Bad:**
```
Name: "Test 1"
Tags: none
```

**Good:**
```
Name: "Login with valid credentials"
Tags: auth, login, smoke
```

**Why:** Clear names and tags improve discoverability and filtering.

---

### 3. Keep Tests Independent

**Bad:**
```
Test 1: Create user account
Test 2: Log in with account from Test 1  ❌ Depends on Test 1
```

**Good:**
```
Test 1: Create user account
Test 2: Log in with existing test account  ✅ Independent
```

**Why:** Independent tests can run in any order and in parallel.

---

## Execution Best Practices

### 1. Test Locally First

```bash
# Always test locally before CI/CD
qa-studio run --usecase-id <id> \
  --base-url http://localhost:3000 \
  --verbose \
  --keep-artifacts
```

**Why:** Faster feedback, easier debugging, no remote execution records.

---

### 2. Use Variable Overrides

```bash
# Override for different environments
qa-studio run --suite-id <id> \
  --base-url https://staging.example.com \
  --var environment=staging \
  --var username=staging_user
```

**Why:** Same tests work across environments without modification.

---

### 3. Review Artifacts on Failure

```bash
# Keep artifacts for debugging
qa-studio run --usecase-id <id> --keep-artifacts

# Review video
open ./artifacts/<id>/recording.webm

# Review logs
cat ./artifacts/<id>/execution.log
```

**Why:** Artifacts show exactly what happened during execution.

---

## CI/CD Best Practices

### 1. Use Suite IDs, Not Individual Tests

**Bad:**
```yaml
- qa-studio run --usecase-id <test-1>
- qa-studio run --usecase-id <test-2>
- qa-studio run --usecase-id <test-3>
```

**Good:**
```yaml
- qa-studio run --suite-id <regression-suite>
```

**Why:** Easier to manage, update, and execute.

---

### 2. Store Credentials as Secrets

**Bad:**
```yaml
env:
  OAUTH_CLIENT_ID: "abc123"  ❌ Hardcoded
```

**Good:**
```yaml
env:
  OAUTH_CLIENT_ID: ${{ secrets.OAUTH_CLIENT_ID }}  ✅ Secret
```

**Why:** Protects credentials from exposure in logs and version control.

---

### 3. Set Appropriate Timeouts

```bash
# Long-running suites need higher timeouts
qa-studio run --suite-id <id> --timeout 7200
```

**Why:** Prevents premature timeout failures.

---

## Maintenance Best Practices

### 1. Update Tests When UI Changes

When UI changes:
1. Run test locally to identify failures
2. Update test steps to match new UI
3. Re-run to verify
4. Commit changes

**Why:** Keeps tests in sync with application changes.

---

### 2. Remove Obsolete Tests

Regularly review and delete:
- Tests for removed features
- Duplicate tests
- Flaky tests that can't be fixed

**Why:** Reduces maintenance burden and execution time.

---

### 3. Use Templates for Common Patterns

Create templates for:
- Login flows
- Form submissions
- Navigation patterns

**Why:** Speeds up test creation and ensures consistency.

---

## Prompting Tips for AI Generation

### 1. Use Sequential Language

**Bad:**
```
"Test the checkout"
```

**Good:**
```
"First add a product to cart, then click cart icon, then proceed to checkout, then fill shipping address, finally verify order confirmation"
```

---

### 2. Specify Expected Outcomes

**Bad:**
```
"Submit the form"
```

**Good:**
```
"Click Submit button, verify success message 'Form submitted' appears"
```

---

### 3. Include Element Types

**Bad:**
```
"Enter email"
```

**Good:**
```
"Enter 'user@example.com' into the email input field"
```

---

### 4. Reference Visible Text

**Bad:**
```
"Click the button with id submit-btn"
```

**Good:**
```
"Click the button labeled 'Submit Order'"
```

---

## Performance Tips

### 1. Minimize Unnecessary Steps

**Bad:**
```
1. Navigate to homepage
2. Wait 5 seconds
3. Click Login
4. Wait 3 seconds
5. Enter credentials
```

**Good:**
```
1. Navigate to /login
2. Enter credentials
3. Click Sign In
```

**Why:** Fewer steps = faster execution.

---

### 2. Use Direct URLs

**Bad:**
```
1. Navigate to homepage
2. Click Products
3. Click First Product
```

**Good:**
```
1. Navigate to /products/123
```

**Why:** Direct navigation is faster and more reliable.

---

### 3. Avoid Redundant Validations

**Bad:**
```
1. Click Submit
2. Verify success message appears
3. Verify success message contains "Success"
4. Verify success message is visible
```

**Good:**
```
1. Click Submit
2. Verify success message contains "Success"
```

**Why:** One validation is sufficient.

---

## Next Steps

- **Create your first test:** [📝 Creating Tests](./creating-tests.md)
- **Run tests locally:** [▶️ Local Execution](./local-execution.md)
- **Set up CI/CD:** [🔄 CI/CD Integration](./ci-cd-integration.md)
