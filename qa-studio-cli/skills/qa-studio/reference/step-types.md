# Step Types

## Overview

QA Studio supports 9 step types for building tests. Each step type serves a specific purpose in test automation.
QA Studio supports 8 step types for building tests. Each step type serves a specific purpose in test automation.

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

**Value types:** `string` (default), `number`, `bool`, `date`.

When `value_type: "date"`, the AI-extracted string is parsed on QA Studio's side and the **canonical UTC ISO 8601** representation is stored in the capture variable — ready to feed directly into `validation_type: "date"` assertions or any of the date transform ops without an intermediate `parse_date` step. The optional `value_format` field on the step holds a Python `strptime` pattern (e.g. `%d/%m/%Y`); when empty, the parser auto-detects ISO 8601 and Unix epoch only. Pass an explicit format whenever the page renders a regional date — the parser deliberately rejects ambiguous input like `01/02/2024` so tests don't silently produce wrong dates depending on locale.

**Storage:** `step_type='retrieve_value'`, `value_type=<type>`, `capture_variable=<var_name>`, plus `value_format=<strptime>` when `value_type='date'`.

**Example (date capture with explicit format):**
```json
{
  "step_type": "retrieve_value",
  "instruction": "Return the order date shown on the page",
  "value_type": "date",
  "value_format": "%d/%m/%Y",
  "capture_variable": "order_date"
}
```

**When to use:** Need to use a value from one step in a later step.

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

**Operations (24):**

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
| `parse_date` | Parse a date string into canonical UTC ISO 8601 | `{"value": "02/01/2024", "format": "%d/%m/%Y"}` |
| `format_date` | Render a canonical date in a target format | `{"iso_value": "{{order_iso}}", "format": "%d %B %Y"}` |
| `add_duration` | Add a signed duration to a date | `{"iso_value": "{{start_date}}", "amount": 30, "unit": "days"}` |
| `date_diff` | Compute the signed difference `a − b` in a unit | `{"a": "{{end}}", "b": "{{start}}", "unit": "days"}` |
| `to_epoch` | Convert a date to Unix epoch seconds or millis | `{"value": "{{order_date_iso}}", "unit": "seconds"}` |

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

**Date operations (`parse_date`, `format_date`, `add_duration`, `date_diff`, `to_epoch`):**

All five operations work on dates and produce canonical UTC ISO 8601 strings (or, in the case of `to_epoch`, integer epoch values). Date inputs are auto-detected as ISO 8601 or Unix epoch when no `format` is provided. For regional human-readable formats (`02/01/2024`, `January 2, 2024`, etc.), pass an explicit `format` argument using Python `strptime` syntax — auto-detection deliberately rejects ambiguous formats like `01/02/2024` so tests don't silently pass with wrong dates depending on locale.

The frontend transform editor exposes a curated dropdown of common formats (ISO, US slash/long-month/short-month, EU slash/dot/dash, with-time variants) plus a "Custom…" option for free-form strptime patterns; each curated entry shows an example and a regional-convention note. See `docs/user-guide.md`'s "Working with dates" section for guidance.

Months and years are deliberately excluded from `add_duration` and `date_diff` units in v1 because their arithmetic is policy-dependent (e.g., `Jan 31 + 1 month` has multiple valid answers). Only `seconds`, `minutes`, `hours`, `days`, `weeks` are supported.

Parse a regional date into canonical UTC:
```json
{
  "step_type": "transform",
  "transform_operation": "parse_date",
  "transform_args": "{\"value\": \"02/01/2024\", \"format\": \"%d/%m/%Y\"}",
  "capture_variable": "order_date_iso"
}
```

Render a canonical date as `dd MMMM yyyy`:
```json
{
  "step_type": "transform",
  "transform_operation": "format_date",
  "transform_args": "{\"iso_value\": \"{{order_date_iso}}\", \"format\": \"%d %B %Y\"}",
  "capture_variable": "order_date_display"
}
```

Add 30 days to a captured start date:
```json
{
  "step_type": "transform",
  "transform_operation": "add_duration",
  "transform_args": "{\"iso_value\": \"{{start_date}}\", \"amount\": 30, \"unit\": \"days\"}",
  "capture_variable": "expected_expiry"
}
```

Compute days between two captured dates (`a − b`):
```json
{
  "step_type": "transform",
  "transform_operation": "date_diff",
  "transform_args": "{\"a\": \"{{expiry_date}}\", \"b\": \"{{start_date}}\", \"unit\": \"days\"}",
  "capture_variable": "subscription_length_days"
}
```

Convert a date to Unix epoch seconds (so it can be compared via the existing number assertion operators):
```json
{
  "step_type": "transform",
  "transform_operation": "to_epoch",
  "transform_args": "{\"value\": \"{{order_date_iso}}\"}",
  "capture_variable": "order_epoch"
}
```

**When to use:** Manipulate or compute values from captured variables without browser interaction. Useful for data preparation, formatting, and arithmetic between steps.
### 8. network_assertion

**Purpose:** Intercept an HTTP request triggered by a UI action, optionally assert its shape, optionally mock the response, and optionally assert on the response status and body.

**Examples:**
- "Click Submit and verify POST **/api/users carries {name: 'John'}"
- "Click Save and mock the response with status 500 to test the error state"
- "Click Refresh and verify GET **/api/config was called"
- "Click Users and verify the response is an array where every item has id, name, email"
- "Click Checkout and verify POST **/api/orders returns 201 with a valid order schema"

**When to use:**
- Verify that a button click triggers the expected API call (URL, method, body)
- Drive the UI into specific states (loading, error, empty) via mock responses
- Test against edge-case backend payloads without touching the real backend
- Verify response structure against a JSON Schema (great for list endpoints where only "every item has these keys" matters, not the array length)
- Assert the response status code explicitly (e.g. `201` after a create)

**Fields:**

| Field | Type | Required | Purpose |
|---|---|---|---|
| `network_url_pattern` | string | **yes** | Playwright glob pattern (e.g. `**/api/users`) |
| `network_method` | string | no | Expected HTTP verb (`GET`/`POST`/…). Empty = no method check. |
| `network_request_body` | string (JSON) | no | Expected request body, interpreted per `network_body_match_type` |
| `network_body_match_type` | string | no | `exact` (default), `subset`, or `schema` |
| `network_mock_response` | string (JSON) | no | `{"status": …, "body": …, "headers": …}` |
| `network_mock_passthrough` | boolean | no | If `true`, fetch real response and merge overrides |
| `network_timeout` | integer | no | Seconds (1–120). Default **15**. |
| `network_response_body` | string (JSON) | no | Expected response body, interpreted per `network_response_body_match_type` |
| `network_response_body_match_type` | string | no | `subset` (default) or `schema` — **`exact` is not permitted on the response side** |
| `network_response_status` | integer | no | Exact-match expected HTTP status (100–599) |

**Match types:**

- **`exact`** — the captured body parsed as JSON must equal the expected body exactly. Extra keys fail.
- **`subset`** — every key/value in the expected template must be present in the captured body. Extra keys are ignored. For arrays: lengths must match, element-by-element.
- **`schema`** — the expected body is a [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) document. The captured body is validated against the schema. External `$ref` (http/https/file) is rejected; only local-pointer refs (`#/...`) are allowed. Schema mode is the right choice when you care about structure, not specific values — for example "the response is an array where every item has these fields."

**Operating modes:**

1. **Assert-only** — configure URL (+ optional method/request body/response status/response body). The request passes through to the real server and every configured field is verified.
2. **Mock-only** — configure URL + `network_mock_response`. The real server is never called.
3. **Mock + assert** — both: return a mock AND verify the request and/or the (mocked) response.

**Security limits (enforced client + server + runtime):**
- Request body, response body, mock response, and schema documents are each capped at **1 MiB** (configurable per deployment via `networkAssertionBodyMaxBytes` in `configuration.json`).
- Subset matcher refuses nested JSON deeper than 20 levels.
- Schema mode rejects `$ref` entries targeting external URIs (`http://`, `https://`, `file://`) to prevent SSRF and file-read attacks from the runner.
- Captured bodies are truncated to 500 chars in logs; only a match summary is stored in execution records.
- Captured response body size is always checked even when no body assertion is configured — an oversized response fails the step early rather than silently.
- Route handlers are always cleaned up after the step (no interception leaks into later steps).

**Response side constraints:**
- `network_response_body_match_type` accepts only `subset` or `schema`. **`exact` is deliberately rejected** because response payloads commonly contain non-deterministic values (server timestamps, generated IDs, ordering). Users needing strict comparisons should express them via a schema with `const` values or narrow to a `subset` template over the stable keys.
- Non-JSON response bodies cannot be asserted on with `subset` or `schema`. If a response is binary or non-JSON, omit the body assertion; use a `download` step or DOM-level `validation` step instead.

**Caching:** this step type is **not cached**. An API contract change must never be masked by a cache hit.

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
| Verify an HTTP call happened / mock an API response | `network_assertion` |

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

### API Contract Verification

```
1. [url] Navigate to https://app.example.com/users/new
2. [navigation] Fill the name field with 'John'
3. [network_assertion]
   instruction: Click Save
   network_url_pattern: **/api/users
   network_method: POST
   network_request_body: {"user": {"name": "John"}}
   network_body_match_type: subset
4. [validation] Verify success banner contains 'User created'
```

### Error State via Mock

```
1. [url] Navigate to https://app.example.com/users
2. [network_assertion]
   instruction: Click Refresh
   network_url_pattern: **/api/users
   network_method: GET
   network_mock_response: {"status": 503, "body": {"error": "unavailable"}}
3. [validation] Verify the page shows 'Service temporarily unavailable'
```

### Response Schema Validation (list endpoint)

Verify every item in a variable-length response carries the required fields, without coupling to how many items the list has:

```
1. [url] Navigate to https://app.example.com/test-suites
2. [network_assertion]
   instruction: Click Refresh
   network_url_pattern: **/api/suites
   network_method: GET
   network_response_status: 200
   network_response_body_match_type: schema
   network_response_body: {
     "type": "object",
     "required": ["suites"],
     "properties": {
       "suites": {
         "type": "array",
         "items": {
           "type": "object",
           "required": ["id", "name", "created_by"],
           "properties": {
             "id":         { "type": "string" },
             "name":       { "type": "string" },
             "created_by": { "type": "string" }
           }
         }
       }
     }
   }
```

This is the flagship use case for schema mode: `subset` can't express "every item has these keys" without coupling to array length, but a schema `items` clause can.

### Create Flow with Status + Body Assertions

Assert the request AND the response in one step — useful for POST/PUT flows where both sides matter:

```
1. [url] Navigate to https://app.example.com/users/new
2. [navigation] Fill the name field with 'John'
3. [network_assertion]
   instruction: Click Save
   network_url_pattern: **/api/users
   network_method: POST
   network_request_body: {"name": "John"}
   network_body_match_type: subset
   network_response_status: 201
   network_response_body_match_type: schema
   network_response_body: {
     "type": "object",
     "required": ["id", "name"],
     "properties": {
       "id":   { "type": "string" },
       "name": { "type": "string", "const": "John" }
     }
   }
4. [validation] Verify success banner contains 'User created'
```

Notice the use of `"const": "John"` inside the schema to pin a value without losing schema-style structural checking on the rest of the object.

---

## Next Steps

- **Learn validation operators:** [✅ Validation Operators](./validation-operators.md)
- **Create tests:** [📝 Creating Tests](./creating-tests.md)
- **Best practices:** [📚 Best Practices](./best-practices.md)
