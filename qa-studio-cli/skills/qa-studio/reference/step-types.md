# Step Types

## Overview

QA Studio supports 9 step types for building tests. Each step type serves a specific purpose in test automation.

---

## Step Types Reference

### 1. navigation

**Purpose:** Interact with UI elements (click, type, select, etc.)

**Examples:**
- "Click the Login button"
- "Enter 'admin@example.com' into the email field"
- "Select 'United States' from the country dropdown"
- "Check the 'I agree to terms' checkbox"

**When to use:** Most common step type for user interactions

---

### 2. url

> ⚠️ **Deprecated:** The `url` step type is soft-deprecated. Use `browser` with action `navigate` instead. Workers still execute existing `url` steps, but the UI now creates `browser → navigate` steps.

**Purpose:** Navigate the browser to a specific URL

**Examples:**
- "Navigate to https://example.com/login"
- "Go to /dashboard"
- "Open the settings page"

**When to use:** Prefer `browser → navigate` for new tests. Existing `url` steps continue to work.

---

### 3. secret

**Purpose:** Use stored credentials (passwords, API keys, tokens)

**Examples:**
- "Enter password from secret 'admin_password'"
- "Use API key from secret 'api_key'"

**When to use:** Any sensitive data that shouldn't be in logs or execution history

**Important:** Secrets are never included in logs, videos, or execution records

---

### 4. validation

**Purpose:** Check a value on the page against an expected value

**Examples:**
- "Verify the heading text equals 'Dashboard'"
- "Check the cart count contains '3'"
- "Verify the price is greater than 100"

**When to use:** Immediate validation of page content

**Operators:** See [✅ Validation Operators](./validation-operators.md)

---

### 5. retrieve_value

**Purpose:** Capture a page value into a variable for later use

**Examples:**
- "Capture the order ID into variable 'order_id'"
- "Store the username into variable 'current_user'"

**When to use:** Need to use a value from one step in a later step

---

### 6. assertion

**Purpose:** Compare a previously captured variable against an expected value

**Examples:**
- "Assert variable 'order_id' is not empty"
- "Verify variable 'total_price' equals '99.99'"

**When to use:** Validate captured variables from `retrieve_value` steps

**Operators:** See [✅ Validation Operators](./validation-operators.md)

---

### 7. download

**Purpose:** Download a file from the page

**Examples:**
- "Download the invoice PDF"
- "Click the export button and download the CSV"

**When to use:** Testing file download functionality

---

### 8. browser

**Purpose:** Perform browser-level actions: reload, navigate back/forward, or navigate to a URL

**Actions:**
- `reload` — Reload the current page. Optional `hard: true` for a hard reload (bypass cache).
- `back` — Navigate back in browser history.
- `forward` — Navigate forward in browser history.
- `navigate` — Navigate to a specific URL (requires `url` argument).

**Storage:** `step_type='browser'`, `browser_action='reload'|'back'|'forward'|'navigate'`, `browser_args=JSON`

**Examples:**

Reload the page:
```json
{
  "step_type": "browser",
  "browser_action": "reload",
  "browser_args": "{}"
}
```

Hard reload (bypass cache):
```json
{
  "step_type": "browser",
  "browser_action": "reload",
  "browser_args": "{\"hard\": true}"
}
```

Navigate back:
```json
{
  "step_type": "browser",
  "browser_action": "back",
  "browser_args": "{}"
}
```

Navigate forward:
```json
{
  "step_type": "browser",
  "browser_action": "forward",
  "browser_args": "{}"
}
```

Navigate to a URL (replaces the deprecated `url` step type):
```json
{
  "step_type": "browser",
  "browser_action": "navigate",
  "browser_args": "{\"url\": \"https://example.com/dashboard\"}"
}
```

**When to use:** Browser-level actions that don't interact with page elements. Use `navigate` instead of the deprecated `url` step type.

---

### 9. transform

**Purpose:** Transform a captured variable value using a built-in operation. Always outputs to `capture_variable`.

**Operations (19):**

| Operation | Description | Example args |
|-----------|-------------|-------------|
| `math` | Evaluate a math expression | `{"expression": "{{price}} * 1.1"}` |
| `round` | Round to N decimal places | `{"value": "{{price}}", "decimals": 2}` |
| `floor` | Floor a number | `{"value": "{{price}}"}` |
| `ceil` | Ceiling a number | `{"value": "{{price}}"}` |
| `abs` | Absolute value | `{"value": "{{balance}}"}` |
| `min` | Minimum of values | `{"values": ["{{a}}", "{{b}}"]}` |
| `max` | Maximum of values | `{"values": ["{{a}}", "{{b}}"]}` |
| `concat` | Concatenate strings | `{"values": ["{{first}}", " ", "{{last}}"]}` |
| `upper` | Uppercase a string | `{"value": "{{name}}"}` |
| `lower` | Lowercase a string | `{"value": "{{name}}"}` |
| `trim` | Trim whitespace | `{"value": "{{input}}"}` |
| `replace` | Replace substring | `{"value": "{{text}}", "old": "-", "new": " "}` |
| `substring` | Extract substring | `{"value": "{{text}}", "start": 0, "end": 5}` |
| `length` | String length | `{"value": "{{text}}"}` |
| `to_number` | Convert to number | `{"value": "{{str_val}}"}` |
| `to_string` | Convert to string | `{"value": "{{num_val}}"}` |
| `to_int` | Convert to integer | `{"value": "{{float_val}}"}` |
| `regex_extract` | Extract via regex | `{"value": "{{text}}", "pattern": "\\d+"}` |
| `format` | Format string template | `{"template": "Hello, {{name}}!"}` |

**Storage:** `step_type='transform'`, `transform_operation=<name>`, `transform_args=JSON`, `capture_variable=<output_var>`

**Examples:**

Calculate tax:
```json
{
  "step_type": "transform",
  "transform_operation": "math",
  "transform_args": "{\"expression\": \"{{subtotal}} * 0.08\"}",
  "capture_variable": "tax_amount"
}
```

Uppercase a name:
```json
{
  "step_type": "transform",
  "transform_operation": "upper",
  "transform_args": "{\"value\": \"{{username}}\"}",
  "capture_variable": "upper_name"
}
```

Extract digits from text:
```json
{
  "step_type": "transform",
  "transform_operation": "regex_extract",
  "transform_args": "{\"value\": \"Order #12345\", \"pattern\": \"\\\\d+\"}",
  "capture_variable": "order_number"
}
```

**When to use:** Manipulate or compute values from captured variables without browser interaction. Useful for data preparation, formatting, and arithmetic between steps.

---

## Step Type Selection Guide

| Goal | Step Type |
|------|-----------|
| Click a button | `navigation` |
| Fill a form field | `navigation` |
| Navigate to a URL | `browser` (navigate) |
| Reload the page | `browser` (reload) |
| Go back/forward | `browser` (back/forward) |
| Enter a password | `secret` |
| Check page content | `validation` |
| Save a value for later | `retrieve_value` |
| Verify a saved value | `assertion` |
| Download a file | `download` |
| Compute or format a value | `transform` |

---

## Examples by Scenario

### Login Flow

```
1. [browser→navigate] Navigate to https://app.example.com/login
2. [navigation] Enter 'admin@example.com' into email field
3. [secret] Enter password from secret 'admin_password'
4. [navigation] Click the Sign In button
5. [validation] Verify heading text equals 'Dashboard'
```

### E-commerce Checkout

```
1. [navigation] Click the first product
2. [navigation] Click Add to Cart
3. [retrieve_value] Capture cart count into variable 'cart_count'
4. [assertion] Verify variable 'cart_count' equals '1'
5. [navigation] Click cart icon
6. [navigation] Click Proceed to Checkout
7. [validation] Verify page URL contains '/checkout'
```

### Form Validation

```
1. [navigation] Leave email field empty
2. [navigation] Click Submit
3. [validation] Verify error message contains 'Email is required'
4. [navigation] Enter 'invalid-email' into email field
5. [navigation] Click Submit
6. [validation] Verify error message contains 'Invalid email format'
```

---

## Next Steps

- **Learn validation operators:** [✅ Validation Operators](./validation-operators.md)
- **Create tests:** [📝 Creating Tests](./creating-tests.md)
- **Best practices:** [📚 Best Practices](./best-practices.md)
