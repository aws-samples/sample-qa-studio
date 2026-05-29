# Building Tests

How to author a QA Studio test case. The skill is for an AI agent helping a user, so **hand-authoring the JSON directly is the preferred path** — the agent IS the AI generation; routing through `qa-studio tests create --from-journey` to invoke Nova Act for drafting adds an unnecessary AI hop, latency, and the chance of mismatch with what the user described.

Two authoring paths in order of preference for agent-driven flows:

1. **Hand-author the JSON** with the agent's understanding of the user's description. Save to disk under `./tests/`, then push to the cloud via [Importing tests](#importing-tests). *This is the default.*
2. **Generate from a user-journey description** as a fallback when the agent's context isn't enough to draft the test directly, or when the user explicitly asks for the CLI's generation flow.

Either path produces a JSON file on disk. Pushing that file to the cloud is a separate concern, covered in the [Importing tests](#importing-tests) section below — same command for both paths.

This guide covers both authoring paths plus the variable / secret wiring patterns used to stitch steps together. For per-step-type details, see [`step-types/`](./step-types/) — each step type has its own file with inputs, examples, and pitfalls.

## Table of contents

- [The test case JSON anatomy](#the-test-case-json-anatomy)
- [Local-first development](#local-first-development)
- [Hand-author JSON directly (preferred)](#hand-author-json-directly-preferred)
- [User-journey generation (fallback)](#user-journey-generation-fallback)
- [Importing tests](#importing-tests)
- [Variable wiring patterns](#variable-wiring-patterns)
- [Worked examples](#worked-examples)
- [Common authoring pitfalls](#common-authoring-pitfalls)

---

## The test case JSON anatomy

Top-level shape (validated client-side; rejection at submit time if malformed):

```json
{
  "exportVersion": "1.0",
  "exportedAt": "2024-01-02T15:00:00Z",
  "usecase": {
    "name": "Login Flow",
    "description": "Verify the user can sign in with valid credentials.",
    "starting_url": "https://app.example.com/login",
    "active": true,
    "executing_region": "us-east-1",
    "tags": ["auth", "login"]
  },
  "steps": [ /* see step-types/ */ ],
  "variables": [],
  "secrets": [
    {"key": "admin_password", "description": "Admin user password"}
  ]
}
```

### Field reference

| Top-level field | Purpose |
|---|---|
| `exportVersion` | Always `"1.0"`. Forward-compatibility hook. |
| `exportedAt` | ISO 8601 timestamp marking when this JSON was authored / regenerated. |
| `usecase` | Test metadata: name, description, starting_url, region, etc. |
| `steps` | Ordered list. Each step has a `sort` (1-based), `step_type`, `instruction`, plus type-specific fields. See [`step-types/`](./step-types/). |
| `variables` | Pre-defined variables available at runtime. Each `{key, value, description}`. Overridable via `--var KEY=VALUE`. |
| `secrets` | Names of secrets the test references. Values are *not* in the JSON; they're configured at import time (via the interactive prompt or `--non-interactive --secret KEY=VALUE`) or in the web UI, then resolved at execution time by the configured resolver. |
| `hooks` | Optional `{beforeScript, afterScript}` for setup/teardown. |

Steps run in `sort` order; gaps are allowed but every `sort` must be a positive integer. `instruction` is required on every step; per-step extra fields are optional and step-type-specific.

---

## Local-first development

**Always store test JSON on local disk during authoring**, even when you also import it to the cloud. The local file is the source of truth for iteration: edit it, re-import, version-control it.

There is no `qa-studio tests export <id>` command yet, so the round-trip `cloud → local` is asymmetric. The fix is to start local: every test the agent generates or hand-authors lives at a known path on disk first; the cloud is downstream of that.

### Conventions for the local path

- Put test JSON under `./tests/` (or whatever directory the user has configured) at the repo root.
- One file per test, kebab-case filename matching the test's `usecase.name` (e.g., `login-flow.json`).
- Group related tests with subdirectories (e.g., `./tests/auth/`, `./tests/checkout/`).

The CLI's `tests import` accepts either a single file or a directory; importing a directory imports every JSON file in it.

---

## Hand-author JSON directly (preferred)

When an agent is helping a user, hand-authoring is the default path. The agent reads the user's description, picks the right step types using [`step-types/`](./step-types/), wires variables together using the patterns below, and writes the JSON to disk.

```bash
# Create the file at the conventional location:
mkdir -p ./tests/auth/
cat > ./tests/auth/login.json <<'EOF'
{
  "exportVersion": "1.0",
  "exportedAt": "2024-01-02T15:00:00Z",
  "usecase": { ... },
  "steps": [ ... ],
  "secrets": []
}
EOF
```

Hand-authoring is the right path when:

- The user has a precise description of each step.
- The agent has read the user's intent and can map it to the step types directly.
- The test exercises step types Nova doesn't draft well (`network_assertion`, `transform`, complex date workflows).
- The agent is converting a fixture, a manual test plan, or an existing test from another tool into JSON.

See the [worked examples](#worked-examples) section for full importable JSON the agent can use as templates. To push the file to the cloud, see [Importing tests](#importing-tests) — same command for both authoring paths.

---

## User-journey generation (fallback)

`qa-studio tests create --from-journey` invokes Nova Act on the cloud side to draft a test from a natural-language user-journey description, imports it, and (with `--export-to`) writes the JSON to local disk. **Use as a fallback** when:

- The user explicitly asks for the CLI's AI generation.
- The agent's context is genuinely insufficient to draft the steps directly.
- The agent wants to generate a starting draft and then iterate.

Otherwise, hand-author — having two AIs in the loop adds latency and surface area for mismatch with the user's intent.

```bash
qa-studio tests create --from-journey \
  --title "Checkout Flow" \
  --url "https://shop.example.com" \
  --journey "Add a product to cart, proceed to checkout, fill the shipping form, verify the order confirmation page" \
  --region us-east-1 \
  --export-to ./tests/
```

**Always pass `--export-to`.** The directory is created if needed; the JSON file is named `<safe_title>.json` (spaces → underscores, non-alnum stripped).

### After generation, iterate

Whatever Nova drafts is rarely the final test. The agent should open the file and:

- Tighten vague step instructions ("Click the button" → "Click the 'Place Order' button").
- Replace hardcoded values with variables or secrets (passwords → `secret` steps, URLs → variables).
- Add `validation` or `assertion` steps for the outcomes the user cares about — Nova rarely guesses these correctly.
- Renumber `sort` if you insert/reorder steps.

After editing, push the updated test to the cloud via [Importing tests](#importing-tests) — same flow as for a hand-authored test.

---

## Importing tests

`qa-studio tests import` validates a local JSON file (or a directory of them) and uploads it to the cloud. This is the only way to push a test to the cloud today, used by both authoring paths above and any time the local file diverges from the cloud copy and you want to push edits.

```bash
# Single file
qa-studio tests import ./tests/login.json

# Whole directory (imports every *.json in it)
qa-studio tests import ./tests/

# Validate without uploading (useful in CI or pre-commit checks)
qa-studio tests import ./tests/login.json --dry-run

# Override starting_url across all imports (e.g., point at staging)
qa-studio tests import ./tests/ --base-url https://staging.example.com

# Skip the interactive secret prompt (configure values later in the UI)
qa-studio tests import ./tests/ --skip-secrets

# Machine-readable output (JSON), for piping into another tool
qa-studio tests import ./tests/ --format json

# Fully non-interactive (implies -y). Required secret values must be supplied
# inline via --secret KEY=VALUE, otherwise the command fails with exit 2 and
# lists the missing keys.
qa-studio tests import ./tests/auth/login.json \
  --non-interactive \
  --secret admin_email=admin@dev.local \
  --secret admin_password=devpass123

# Non-interactive deferring secret config to the UI
qa-studio tests import ./tests/auth/login.json --non-interactive --skip-secrets
```

Exit codes: `0` on success, `1` if any file failed to import, `2` for input-validation errors (malformed `--secret`, unknown secret key, or `--non-interactive` set with required secrets unsupplied).

### Agent flow: ready-to-run import

The default agent flow is interactive — the agent writes the JSON, runs `qa-studio tests import <path>`, and lets the user fill the hidden-input secret prompts at the terminal. The values never enter the agent's context. This is the safest path and is the right default.

When the user wants to import end-to-end through chat (no terminal context-switch), the agent has to gather secret values and supply them via `--non-interactive --secret KEY=VALUE`. This works but trades safety for convenience: anything the user pastes lands in the chat transcript, the model context, and the shell command line. The agent must surface that tradeoff in its reply — whether it had to ask for values or the user volunteered them up front. Volunteered credentials are still in the chat; the caveat applies just the same.

Decision logic the agent applies:

1. **Clearly non-prod context** (localhost, dev environment, dummy account, throwaway credentials): use `--non-interactive --secret KEY=VALUE` to import ready-to-run with values inline. **Whether the user volunteers credentials proactively or you have to ask for them, the agent's reply MUST surface a transcript caveat that names all three exposure surfaces by name: the chat transcript, the model context, and the shell command line.** The three keywords are load-bearing — paraphrasing the spirit ("local dev so it's fine") loses the safety information. Use this template; rephrasing is fine, the three bolded keywords are not:

   > Heads up: anything you paste in this chat lands in the **chat transcript**, the **model context**, and the **shell command line** I'll execute. That's fine for dev or local accounts, but don't paste production credentials — for those, I'll use `--skip-secrets` and you can set them in the QA Studio UI.

2. **Prod, staging, or unclear context**: import with `--non-interactive --skip-secrets` and tell the user to set values in the QA Studio UI before running.
3. **User explicitly says "let me fill the prompts at the terminal"**: drop `--non-interactive`, use the default interactive flow.

The agent never assumes which path applies — it surfaces the tradeoff and lets the user choose.

### Secret prompting

When the JSON has `secrets`, the import flow prompts (interactively, unless `--skip-secrets` or `--non-interactive`) for each unique secret key, hidden-input. Values are deduplicated across files — the same `admin_password` referenced in 5 tests is prompted once. Pre-supplying a value with `--secret KEY=VALUE` suppresses the prompt for that key only; remaining keys still prompt unless `--non-interactive` or `--skip-secrets` is set.

### Validation errors

The validator checks the JSON shape (top-level fields, step types, required step fields). It does NOT check that step instructions make sense, that referenced variables exist, or that the test will actually pass. Run the test locally (`qa-studio run --usecase-id <id>`) to verify it works.

### On export

There is no `qa-studio tests export <id>` command today — the round-trip from cloud back to local JSON is asymmetric on purpose. The local file under `./tests/` is the source of truth; the cloud is downstream of it. See [Local-first development](#local-first-development) for the implications.

---

## Variable wiring patterns

### Variables vs secrets vs literals

Before wiring values across steps, decide which mechanism each value belongs to. The skill enforces a strict three-way split:

| Kind of value | Mechanism | Why |
|---|---|---|
| Login or auth credential (username, email, password, MFA code, OTP, security answer, recovery code) | `secret` | Routed through the secret resolver; never appears in JSON, recordings, logs, or chat transcripts. The whole login form, not just the password — see [step-types/secret.md](./step-types/secret.md). |
| Programmatic credential (API key, OAuth token, PAT, license key) | `secret` | Same reason. |
| Value reused in 2+ places that varies per environment or per run (base URL, environment name, region, tenant ID, feature flag, generated test ID) | `variable` | Visible in logs and step previews (so debuggable), overridable per run via `--var KEY=VALUE`. |
| One-off literal used in exactly one step (button label, search query, contact-form message, dropdown option) | inline literal in the `navigation` instruction | No reuse, no override, no extraction overhead. |

Common mistakes:

- **Hardcoding a value that's reused.** If `https://example.com` appears in three step instructions, it belongs in a `variable` so the test can run against staging or local without editing every step.
- **Using a `variable` for something sensitive.** Variables show up in logs and step previews — they're the wrong place for credentials. Move it to a `secret`.
- **Using a `secret` for a non-credential reused value.** Secrets are opaque (no preview in logs, no `--var` override). If you want to vary `environment=staging` per run, that's a `variable`, not a secret.

Variables flow between steps via `{{ name }}` references. Three sources:

1. **The `variables` array in the test JSON** — defined at authoring time, persisted with the test.
2. **`retrieve_value` and `transform` step outputs** — written to `capture_variable`.
3. **Runtime overrides via `--var KEY=VALUE`** — passed when running the test, takes precedence over the test's `variables`.

A typical wiring pattern: capture, optionally transform, then assert.

```
┌──────────────────────────────────────────────────────────────────────┐
│ retrieve_value                                                       │
│   instruction: "Get the order total"                                 │
│   capture_variable: "order_total"  ──┐                               │
│   value_type: "number"               │                               │
└──────────────────────────────────────┼───────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│ transform (math)                                                     │
│   transform_args: {"expression": "{{order_total}} * 1.08"}           │
│   capture_variable: "expected_total_with_tax"  ──┐                   │
└──────────────────────────────────────────────────┼───────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ assertion                                                            │
│   assertion_variable: "displayed_total_with_tax"                     │
│   validation_value: "{{expected_total_with_tax}}"                    │
│   validation_operator: "equals"                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Variable name conventions

- Snake_case: `order_total`, not `orderTotal` or `OrderTotal`.
- Descriptive, not generic: `cart_count`, not `count`. The agent reads variable names months later in test logs and step previews.
- Match the data: `order_date` for a date, `order_id` for a string ID, `total_with_tax` for a computed number.
- Reserved-name avoidance: don't use `__name__` (double-underscore prefix is reserved for runtime-injected variables, even though there are none in v1).

---

## Worked examples

Six end-to-end test cases covering the major patterns. Each is full importable JSON — copy, save under `./tests/`, then `qa-studio tests import`.

### Example 1: Login flow

Demonstrates the full login pattern: every field on the login form goes through a `secret` step (email and password), the sign-in click is a `navigation` step, and the post-login state is verified with a `validation` step. Neither the email nor the password value appears in the JSON.

```json
{
  "exportVersion": "1.0",
  "exportedAt": "2024-01-02T15:00:00Z",
  "usecase": {
    "name": "Login Flow",
    "description": "Verify a user can sign in with valid credentials.",
    "starting_url": "https://app.example.com/login",
    "active": true,
    "executing_region": "us-east-1",
    "tags": ["auth", "login"]
  },
  "steps": [
    {
      "sort": 1,
      "step_type": "secret",
      "instruction": "Focus the email input field",
      "secret_key": "admin_email"
    },
    {
      "sort": 2,
      "step_type": "secret",
      "instruction": "Focus the password input field",
      "secret_key": "admin_password"
    },
    {
      "sort": 3,
      "step_type": "navigation",
      "instruction": "Click the 'Sign In' button"
    },
    {
      "sort": 4,
      "step_type": "validation",
      "instruction": "Get the heading text after sign-in",
      "validation_type": "string",
      "validation_operator": "exact",
      "validation_value": "Dashboard"
    }
  ],
  "secrets": [
    {"key": "admin_email", "description": "Admin user email / login identifier"},
    {"key": "admin_password", "description": "Admin user password"}
  ]
}
```

### Example 2: Contact form submission + validation

Multi-step UI flow with form-error handling. Demonstrates that validation steps don't have to come at the end.

```json
{
  "exportVersion": "1.0",
  "exportedAt": "2024-01-02T15:00:00Z",
  "usecase": {
    "name": "Contact Form Submit",
    "description": "Verify the contact form submits successfully and shows a confirmation banner.",
    "starting_url": "https://example.com/contact",
    "active": true,
    "executing_region": "us-east-1",
    "tags": ["forms"]
  },
  "steps": [
    {
      "sort": 1,
      "step_type": "navigation",
      "instruction": "Enter 'Jane Doe' into the name field"
    },
    {
      "sort": 2,
      "step_type": "navigation",
      "instruction": "Enter 'jane@example.com' into the email field"
    },
    {
      "sort": 3,
      "step_type": "navigation",
      "instruction": "Enter 'I would like to learn more about your product.' into the message field"
    },
    {
      "sort": 4,
      "step_type": "navigation",
      "instruction": "Click the 'Send Message' button"
    },
    {
      "sort": 5,
      "step_type": "validation",
      "instruction": "Get the success banner text",
      "validation_type": "string",
      "validation_operator": "contains",
      "validation_value": "Thank you"
    }
  ]
}
```

### Example 3: Search-and-verify with variable wiring

Captures a value from one page, asserts the same value on the next page. Demonstrates `retrieve_value` → `assertion`.

```json
{
  "exportVersion": "1.0",
  "exportedAt": "2024-01-02T15:00:00Z",
  "usecase": {
    "name": "Search Result Detail Match",
    "description": "Search for a product, then verify the detail page heading matches the search result name.",
    "starting_url": "https://shop.example.com",
    "active": true,
    "executing_region": "us-east-1",
    "tags": ["search"]
  },
  "steps": [
    {
      "sort": 1,
      "step_type": "navigation",
      "instruction": "Type 'laptop' into the search field and press Enter"
    },
    {
      "sort": 2,
      "step_type": "retrieve_value",
      "instruction": "Get the product name from the first search result card",
      "capture_variable": "first_result_name",
      "value_type": "string"
    },
    {
      "sort": 3,
      "step_type": "navigation",
      "instruction": "Click the first search result"
    },
    {
      "sort": 4,
      "step_type": "validation",
      "instruction": "Get the product detail page heading",
      "validation_type": "string",
      "validation_operator": "exact",
      "validation_value": "{{ first_result_name }}"
    }
  ]
}
```

### Example 4: Network mock + UI assertion

Forces an error state by mocking a 503 response, then asserts the UI handles it gracefully.

```json
{
  "exportVersion": "1.0",
  "exportedAt": "2024-01-02T15:00:00Z",
  "usecase": {
    "name": "Service Unavailable Banner",
    "description": "Mock a 503 from the users API and verify the UI shows a service-unavailable banner.",
    "starting_url": "https://app.example.com/users",
    "active": true,
    "executing_region": "us-east-1",
    "tags": ["network", "error-state"]
  },
  "steps": [
    {
      "sort": 1,
      "step_type": "network_assertion",
      "instruction": "Click the 'Refresh' button",
      "network_url_pattern": "**/api/users",
      "network_method": "GET",
      "network_mock_response": "{\"status\": 503, \"body\": {\"error\": \"unavailable\"}}",
      "network_timeout": 15
    },
    {
      "sort": 2,
      "step_type": "validation",
      "instruction": "Get the error banner text",
      "validation_type": "string",
      "validation_operator": "contains",
      "validation_value": "Service temporarily unavailable"
    }
  ]
}
```

### Example 5: Date workflow

Captures dates in a regional format, computes a difference and a future date, asserts ordering. The full surface of the date feature.

```json
{
  "exportVersion": "1.0",
  "exportedAt": "2024-01-02T15:00:00Z",
  "usecase": {
    "name": "Order Date is After Previous Order",
    "description": "Verify a newly-created order's date is strictly after the previously-displayed latest order date.",
    "starting_url": "https://shop.example.com/orders",
    "active": true,
    "executing_region": "us-east-1",
    "tags": ["dates"]
  },
  "steps": [
    {
      "sort": 1,
      "step_type": "retrieve_value",
      "instruction": "Get the latest order date from the orders table",
      "capture_variable": "previous_latest_date",
      "value_type": "date",
      "value_format": "%d/%m/%Y"
    },
    {
      "sort": 2,
      "step_type": "navigation",
      "instruction": "Click 'Create Order' and complete the form, then submit"
    },
    {
      "sort": 3,
      "step_type": "browser",
      "browser_action": "navigate",
      "browser_args": "{\"url\": \"/orders\"}"
    },
    {
      "sort": 4,
      "step_type": "retrieve_value",
      "instruction": "Get the latest order date from the orders table",
      "capture_variable": "new_latest_date",
      "value_type": "date",
      "value_format": "%d/%m/%Y"
    },
    {
      "sort": 5,
      "step_type": "assertion",
      "assertion_variable": "new_latest_date",
      "validation_type": "date",
      "validation_operator": "after",
      "validation_value": "{{ previous_latest_date }}"
    }
  ]
}
```

### Example 6: Capture, transform, assert (number)

Captures a displayed price, computes a derived value, asserts it matches another captured value. Demonstrates `transform.math`.

```json
{
  "exportVersion": "1.0",
  "exportedAt": "2024-01-02T15:00:00Z",
  "usecase": {
    "name": "Cart Tax Computation",
    "description": "Verify the displayed total matches the subtotal plus 8% tax.",
    "starting_url": "https://shop.example.com/cart",
    "active": true,
    "executing_region": "us-east-1",
    "tags": ["pricing", "math"]
  },
  "steps": [
    {
      "sort": 1,
      "step_type": "retrieve_value",
      "instruction": "Get the cart subtotal as a number",
      "capture_variable": "subtotal",
      "value_type": "number"
    },
    {
      "sort": 2,
      "step_type": "retrieve_value",
      "instruction": "Get the cart total as a number",
      "capture_variable": "displayed_total",
      "value_type": "number"
    },
    {
      "sort": 3,
      "step_type": "transform",
      "transform_operation": "math",
      "transform_args": "{\"expression\": \"{{ subtotal }} * 1.08\"}",
      "capture_variable": "expected_total"
    },
    {
      "sort": 4,
      "step_type": "assertion",
      "assertion_variable": "displayed_total",
      "validation_type": "number",
      "validation_operator": "equals",
      "validation_value": "{{ expected_total }}"
    }
  ]
}
```

---

## Common authoring pitfalls

Cross-cutting authoring mistakes. Per-step pitfalls (e.g., date format ambiguity for `parse_date`) are documented in the relevant [step-types/](./step-types/) file.

- **Reaching for `tests create --from-journey` when the agent could hand-author.** Hand-authoring is the preferred path when an agent is in the loop. Use AI generation only as a fallback (see [User-journey generation (fallback)](#user-journey-generation-fallback)), and always with `--export-to ./tests/` so the draft lands on disk for iteration.
- **Hardcoding values that should be variables.** URLs, environment names, generated IDs — anything that varies across runs or environments belongs in `variables` (or a `--var` override) and referenced as `{{ name }}`. Hardcoded values lock the test to one environment and one moment in time.
- **Treating only the password as sensitive on a login form.** Every field on a login or authentication form is a credential — usernames, emails, passwords, MFA codes, OTP codes, security-question answers, recovery codes. All of them go through `secret` steps, declared in the `secrets` array, never written as literals in `navigation` instructions. Even an "obviously dummy" `qa-tester@example.com` belongs in a secret: it's still login data and routing it through the secret resolver is the only way to keep test-account identifiers out of recordings, screenshots, logs, and version control. See [step-types/secret.md](./step-types/secret.md) for the full rule and Example 1 above for the worked pattern.
- **Hardcoding secrets.** Passwords, login emails, MFA codes, API keys, OAuth tokens — must use `secret` steps. Never put them in the JSON; they leak into version control, recordings, and execution logs. **And don't tell the user to pass `--secrets-file` to `qa-studio run` — that flag does NOT exist.** Secrets are configured at import time (the prompt during `qa-studio tests import`) or in the web UI. If the user wants to provide a secret value at run time, the answer is to (re-)configure it on the use case, not invent a flag.
- **Variable name typos in `{{ }}` references.** A `{{ frist_result_name }}` typo will substitute as the literal string `{{ frist_result_name }}` rather than the captured value, then the assertion compares two unrelated strings. Match the `capture_variable` exactly.
- **Forgetting `capture_variable` on `retrieve_value` or `transform`.** Validators reject this case for `transform`; for `retrieve_value` the step is functionally a no-op. Always set it.
- **Mixing actions in one step.** `"Click Save and verify the success banner"` — split into two steps: one `navigation` for the click, one `validation` for the verification. Mixed steps are harder to diagnose when they fail.
- **Date capture without a format on regional dates.** If the page renders `01/02/2024`, the date parser refuses to guess. Set `value_format` on the `retrieve_value` to the matching strptime pattern (`"%m/%d/%Y"` for US, `"%d/%m/%Y"` for EU). See [step-types/retrieve_value.md](./step-types/retrieve_value.md).
- **`exportVersion` other than `"1.0"`.** Validators reject anything else. Do not invent versions.
- **Skipping the `--dry-run` before bulk imports.** When importing a directory, `--dry-run` validates every file without uploading. Catches typos and missing required fields before they hit the cloud.
- **Re-using the same `capture_variable` name across steps.** Later captures overwrite earlier ones. If both values are needed downstream, use distinct names.
