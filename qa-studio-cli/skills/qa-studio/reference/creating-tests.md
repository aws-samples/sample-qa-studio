# Creating Tests

## Overview

QA Studio supports multiple test creation methods. Choose based on your workflow:

| Method | Best For | Command |
|--------|----------|---------|
| AI Generation | Quick test creation from descriptions | `qa-studio tests create --from-journey` |
| Interactive Wizard | Step-by-step visual building | Web interface only |
| Manual Creation | Fine-grained control | Web interface |
| Templates | Reusable test patterns | `qa-studio tests create --from-template` |
| Clone | Variations of existing tests | Web interface |

---

## AI-Generated Tests (Recommended)

Generate complete tests from natural language descriptions.

### Basic Usage

```bash
qa-studio tests create --from-journey \
  --title "Login Flow" \
  --url "https://app.example.com/login" \
  --journey "Navigate to login page, enter username 'demo@example.com', enter password, click Sign In button, verify dashboard heading is visible" \
  --region us-east-1
```

### Parameters

- `--title`: Test name (required)
- `--url`: Starting URL (required)
- `--journey`: Natural language description of the test flow (required)
- `--region`: AWS region for browser execution (default: us-east-1)
- `--export-to`: Export generated test JSON to specified folder (optional)

### Writing Effective Journey Descriptions

**Be specific about actions:**
```
❌ "Log in"
✅ "Enter 'admin@example.com' into the email field, enter password, click the 'Sign In' button"
```

**Include expected outcomes:**
```
❌ "Submit the form"
✅ "Click Submit button, verify success message 'Order placed' appears"
```

**Reference visible elements:**
```
❌ "Click #submit-btn"
✅ "Click the button labeled 'Submit Order'"
```

**Use sequential language:**
```
✅ "First navigate to /products, then click the first product card, then click Add to Cart, finally verify cart count shows 1"
```

### Examples

#### Example 1: E-commerce Checkout

```bash
qa-studio tests create --from-journey \
  --title "Checkout Flow" \
  --url "https://shop.example.com" \
  --journey "Click the first product, click Add to Cart, click cart icon in header, click Proceed to Checkout, fill shipping address with name 'Jane Doe' and zip '12345', click Place Order, verify confirmation message 'Order placed successfully' is visible"
```

#### Example 2: Form Validation

```bash
qa-studio tests create --from-journey \
  --title "Contact Form Validation" \
  --url "https://example.com/contact" \
  --journey "Leave all fields empty, click Submit, verify error message 'Email is required' appears, enter 'invalid-email' into email field, click Submit, verify error message 'Invalid email format' appears"
```

#### Example 3: Multi-Step Workflow

```bash
qa-studio tests create --from-journey \
  --title "Profile Update" \
  --url "https://app.example.com" \
  --journey "Click profile icon in top right, click Settings, click Edit Profile, change display name to 'John Smith', change bio to 'Software Engineer', click Save Changes, verify success toast 'Profile updated' appears, refresh page, verify display name shows 'John Smith'"
```

### Exporting Test JSON

Export the generated test JSON for version control, sharing, or backup:

```bash
qa-studio tests create --from-journey \
  --title "Login Flow" \
  --url "https://app.example.com/login" \
  --journey "Enter credentials and log in" \
  --export-to ./test-exports
```

This creates a JSON file in the specified folder with a sanitized filename based on the test title (e.g., `Login_Flow.json`).

**Use cases:**
- **Version control:** Track test definitions in Git
- **Sharing:** Send test definitions to team members
- **Backup:** Keep local copies of generated tests
- **CI/CD:** Use exported JSON for automated test imports

**Example workflow:**
```bash
# Generate and export test
qa-studio tests create --from-journey \
  --title "Checkout Flow" \
  --url "https://shop.example.com" \
  --journey "Add item to cart and complete checkout" \
  --export-to ./tests

# Later, import the test in another environment
# (Import functionality via API or web interface)
```

---

## Interactive Wizard (Web Interface)

Build tests step-by-step with a live browser. See [🌐 Web Interface](./web-interface.md#interactive-wizard) for details.

**Workflow:**
1. Enter test name, URL, description
2. Launch live browser session
3. Type a step instruction
4. Watch browser execute it in real-time
5. Accept or modify the step
6. Repeat until complete

**Best for:**
- Visual learners
- Complex interactions
- Debugging specific steps

---

## Manual Creation (Web Interface)

Create tests from scratch in the web interface. See [🌐 Web Interface](./web-interface.md#manual-creation) for details.

**Workflow:**
1. Create blank test
2. Add steps one by one
3. Configure step types and parameters
4. Set variables and secrets

**Best for:**
- Fine-grained control
- Using specific step types
- Working with variables and secrets

---

## Templates

Use pre-built test templates with configurable variables. See [🌐 Web Interface](./web-interface.md#templates) for details.

**Available via web interface:**
- Login flows
- Form submissions
- Navigation patterns
- Common workflows

---

## Refining Generated Tests

If AI-generated tests produce incorrect steps:

### Strategy 1: Improve Journey Description

Regenerate with more specific language:

```bash
# Original (too vague)
--journey "Test the login"

# Improved (specific)
--journey "Navigate to /login, type 'admin@example.com' into the email input field, type 'password123' into the password input field, click the button labeled 'Sign In', verify the page heading shows 'Dashboard'"
```

### Strategy 2: Manual Step Editing

1. Get the test details:
   ```bash
   qa-studio tests get <id>
   ```

2. Edit steps in the web interface:
   - Navigate to the test
   - Click "Steps" tab
   - Edit, add, or remove steps
   - Save changes

### Strategy 3: Clone and Modify

1. Clone the test in the web interface
2. Modify the problematic steps
3. Delete the original if needed

---

## Test Creation Checklist

Before finalizing a test:

- [ ] Starting URL is correct and accessible
- [ ] Steps are in logical order
- [ ] Expected outcomes are validated (use `validation` steps)
- [ ] Sensitive data uses `secret` steps (not hardcoded)
- [ ] Variables are defined for parameterization
- [ ] Test has been executed locally at least once
- [ ] Artifacts (video, logs) reviewed for correctness

---

## Next Steps

- **Run your test locally:** [▶️ Local Execution](./local-execution.md)
- **Organize tests into suites:** [📦 Test Suites](./test-suites.md)
- **Learn about step types:** [🎯 Step Types](./step-types.md)
