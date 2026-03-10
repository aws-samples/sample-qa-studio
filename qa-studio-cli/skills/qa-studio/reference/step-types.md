# Step Types

## Overview

QA Studio supports 7 step types for building tests. Each step type serves a specific purpose in test automation.

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

**Purpose:** Navigate the browser to a specific URL

**Examples:**
- "Navigate to https://example.com/login"
- "Go to /dashboard"
- "Open the settings page"

**When to use:** Explicit navigation to a URL (not clicking a link)

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

## Step Type Selection Guide

| Goal | Step Type |
|------|-----------|
| Click a button | `navigation` |
| Fill a form field | `navigation` |
| Navigate to a URL | `url` |
| Enter a password | `secret` |
| Check page content | `validation` |
| Save a value for later | `retrieve_value` |
| Verify a saved value | `assertion` |
| Download a file | `download` |

---

## Examples by Scenario

### Login Flow

```
1. [url] Navigate to https://app.example.com/login
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
