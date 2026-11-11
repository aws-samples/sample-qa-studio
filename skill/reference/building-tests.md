# Building Tests

How to author a QA Studio test case. The skill is for an AI agent helping a user, so **hand-authoring the JSON directly is the preferred path** — the agent IS the AI generation; routing through `qa-studio tests create --from-journey` to invoke Nova Act for drafting adds an unnecessary AI hop, latency, and the chance of mismatch with what the user described.

Two authoring paths in order of preference for agent-driven flows:

1. **Hand-author the JSON** with the agent's understanding of the user's description. Save to disk under `./tests/`, then push to the cloud via [Importing tests](#importing-tests). *This is the default.*
2. **Generate from a user-journey description** as a fallback when the agent's context isn't enough to draft the test directly, or when the user explicitly asks for the CLI's generation flow.

Either path produces a JSON file on disk. Pushing that file to the cloud is a separate concern, covered in the [Importing tests](#importing-tests) section below — same command for both paths.

This guide covers both authoring paths plus the variable / secret wiring patterns used to stitch steps together. For per-step-type details, see [`step-types/`](./step-types/) — each step type has its own file with inputs, examples, and pitfalls.

## Table of contents

- [The test case JSON anatomy](#the-test-case-json-anatomy) (incl. the [template placeholder step](#template-placeholder-step))
- [Local-first development](#local-first-development)
- [Hand-author JSON directly (preferred)](#hand-author-json-directly-preferred)
- [One action or one check per step](#one-action-or-one-check-per-step)
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
| `usecase` | Test metadata: name, description, starting_url, region, `test_platform` (`web` default, `mobile`, `electron`), etc. |
| `steps` | Ordered list. Each step has a `sort` (1-based), `step_type`, `instruction`, plus type-specific fields. See [`step-types/`](./step-types/). A [`repeat`](./step-types/repeat.md) step nests its children under its own `steps` array. |
| `variables` | Pre-defined variables available at runtime. Each `{key, value, description}`. Overridable via `--var KEY=VALUE`. |
| `secrets` | Names of secrets the test references. Values are *not* in the JSON; they're configured at import time (via the interactive prompt or `--non-interactive --secret KEY=VALUE`) or in the web UI, then resolved at execution time by the configured resolver. |
| `hooks` | Optional `{beforeScript, afterScript}` for setup/teardown. |

Steps run in `sort` order; gaps are allowed but every `sort` must be a positive integer. `instruction` is required on every step; per-step extra fields are optional and step-type-specific — with one exception, the template placeholder below.

### Template placeholder step

Reusable sequences (login, cookie banner, …) live in **templates**. Instead of copying their steps, put a placeholder in the slot where they belong; `qa-studio tests import` checks the template exists and the cloud expands it (keeping template linkage) when the test is created:

```json
"steps": [
  { "sort": 1, "step_type": "template", "template_id": "3f1c0000-0000-4000-8000-000000000001" },
  { "sort": 2, "step_type": "navigation", "instruction": "Click 'Add to cart' on the first product." }
]
```

A placeholder has exactly `sort`, `step_type: "template"` and a UUID `template_id` (from `qa-studio templates list`) — no `instruction`, nothing else. It may appear several times and only at the top level (not inside a `repeat`). The template's secret keys are prompted at import together with the file's `secrets`; do not repeat them in `secrets`. Before hand-authoring login or setup steps, check `qa-studio templates list`. Full guide: [🧩 Templates](./templates.md).

### Platforms (`usecase.test_platform`)

| Value | What the runner drives | Authoring differences |
|---|---|---|
| `web` *(default)* | A browser, locally, in CI or in the cloud worker | `starting_url` required; every step type available |
| `mobile` | A real device on AWS Device Farm | `platform` + app identifiers required; no `starting_url` |
| `electron` | The real desktop app, launched by the CI runner | **Omit `starting_url`** (the app decides what it opens); optional `bundle_id` (the app's `CFBundleIdentifier`, checked against the launched `.app`); no other mobile fields; avoid `url` steps; runs only via `qa-studio run --app-path …`, never from the UI |

Electron minimal `usecase` block:

```json
"usecase": {
  "name": "Harness — open a project",
  "description": "Signs in and opens the first project.",
  "test_platform": "electron",
  "bundle_id": "com.productharness.desktop",
  "executing_region": "eu-central-1",
  "tags": ["desktop", "smoke"]
}
```

Login in an Electron app goes through the app's own UI: `secret` steps for every credential field, exactly as on the web.

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

## One action or one check per step

**Every step does exactly one thing: one UI action, or one check of one value.** This is the single most important authoring rule and the one most often broken. A step is the unit the runner reports on — one pass/fail, one extracted value, one screenshot. If a step bundles several checks, a failure tells you nothing about *which* check failed, and the model is free to return "true" when most (but not all) of the listed things are present.

### The anti-pattern

This is one step that performs five checks:

```json
{
  "step_type": "validation",
  "instruction": "Verify the blueprint builder is shown: a left panel titled 'New Blueprint' with fields 'Name' (placeholder 'Blueprint name') and 'Description', and 'Save' and 'Cancel' buttons",
  "validation_type": "bool",
  "validation_value": "true"
}
```

Problems: when it fails there is no way to tell whether the title, a field, the placeholder or a button is wrong; the recorded `actual_value` is just `false`; and a model that sees four of the five things will often answer `true` anyway. The step is not debuggable and not strict.

### The fix

One step per element being checked, each extracting a concrete value where possible:

```json
[
  {
    "sort": 2,
    "step_type": "validation",
    "instruction": "Get the title of the left panel",
    "validation_type": "string",
    "validation_operator": "exact",
    "validation_value": "New Blueprint"
  },
  {
    "sort": 3,
    "step_type": "validation",
    "instruction": "Get the placeholder text of the 'Name' field in the 'New Blueprint' panel",
    "validation_type": "string",
    "validation_operator": "exact",
    "validation_value": "Blueprint name"
  },
  {
    "sort": 4,
    "step_type": "validation",
    "instruction": "Is there a 'Description' field in the 'New Blueprint' panel?",
    "validation_type": "bool",
    "validation_value": "true"
  },
  {
    "sort": 5,
    "step_type": "validation",
    "instruction": "Is there a 'Save' button in the 'New Blueprint' panel?",
    "validation_type": "bool",
    "validation_value": "true"
  },
  {
    "sort": 6,
    "step_type": "validation",
    "instruction": "Is there a 'Cancel' button in the 'New Blueprint' panel?",
    "validation_type": "bool",
    "validation_value": "true"
  }
]
```

Five steps instead of one is the correct trade: each one fails independently with a meaningful actual value, and each can be fixed in isolation when the UI changes.

### How to spot a compound step

Split the step if the instruction contains any of these:

- A list — commas, "and", "as well as", "with X and Y": `"fields 'Name' and 'Description'"` → one step per field.
- A colon followed by an enumeration: `"Verify the form is shown: a title, two fields, two buttons"` → one step per item after the colon.
- Several verbs: `"Enter the name, enter the description and click Save"` → three `navigation` steps.
- An action and a check in the same sentence: `"Click Save and verify the success banner"` → one `navigation` step, one `validation` step.
- Several expected values: `"the heading is 'Dashboard' and the badge shows 3"` → one `string` validation, one `number` validation.
- Words like "correctly", "properly", "as expected", "all the fields" — these hide an unspecified list of checks. Spell the checks out, one per step.

Rule of thumb: count the verbs and the expected values, not the nouns. Each verb that acts on the page is one `navigation` step; each expected value is one `validation`/`assertion` step. Nouns that only locate the target (`"the 'Name' field in the 'New Blueprint' panel"`, `"'United States' from the country dropdown"`) don't add steps.

### What this rule does NOT mean

- It does not mean "check everything on the page." Pick the elements that prove the journey succeeded; a form with twelve fields does not need twelve validations if two of them demonstrate the form rendered. Fewer, meaningful checks beat exhaustive ones — but every check you do keep gets its own step.
- Describing context inside an instruction is fine and encouraged: `"Get the placeholder text of the 'Name' field in the 'New Blueprint' panel"` names the panel to disambiguate the field; it still checks exactly one value.
- A single action that inherently involves one gesture with a qualifier is one step: `"Select 'United States' from the country dropdown"` is one action, not two.

The same rule applies to `navigation` (one gesture), `retrieve_value` (one captured value), `assertion` (one comparison) and `network_assertion` (one request pattern). See the per-step files in [`step-types/`](./step-types/).

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
  --application-id <app-id> \
  --export-to ./tests/
```

**Always pass `--export-to`.** The directory is created if needed; the JSON file is named `<safe_title>.json` (spaces → underscores, non-alnum stripped).

### After generation, iterate

Whatever Nova drafts is rarely the final test. The agent should open the file and:

- Tighten vague step instructions ("Click the button" → "Click the 'Place Order' button").
- Split compound steps. Generators love `"Verify the page shows X, Y and Z"` — that is three `validation` steps, not one. See [One action or one check per step](#one-action-or-one-check-per-step).
- Replace hardcoded values with variables or secrets (passwords → `secret` steps, URLs → variables).
- Add `validation` or `assertion` steps for the outcomes the user cares about — Nova rarely guesses these correctly.
- Renumber `sort` if you insert/reorder steps.

After editing, push the updated test to the cloud via [Importing tests](#importing-tests) — same flow as for a hand-authored test.

---

## Importing tests

`qa-studio tests import` validates a local JSON file (or a directory of them) and uploads it to the cloud. This is the only way to push a test to the cloud today, used by both authoring paths above and any time the local file diverges from the cloud copy and you want to push edits.

```bash
# Single file
qa-studio tests import ./tests/login.json --application-id <app-id>

# Whole directory (imports every *.json in it)
qa-studio tests import ./tests/ --application-id <app-id>

# Validate without uploading (useful in CI or pre-commit checks)
qa-studio tests import ./tests/login.json --dry-run

# Override starting_url across all imports (e.g., point at staging)
qa-studio tests import ./tests/ --application-id <app-id> --base-url https://staging.example.com

# Skip the interactive secret prompt (configure values later in the UI)
qa-studio tests import ./tests/ --application-id <app-id> --skip-secrets

# Machine-readable output (JSON), for piping into another tool
qa-studio tests import ./tests/ --application-id <app-id> --format json

# Fully non-interactive (implies -y). Required secret values must be supplied
# inline via --secret KEY=VALUE, otherwise the command fails with exit 2 and
# lists the missing keys.
qa-studio tests import ./tests/auth/login.json --application-id <app-id> \
  --non-interactive \
  --secret admin_email=admin@dev.local \
  --secret admin_password=devpass123

# Non-interactive deferring secret config to the UI
qa-studio tests import ./tests/auth/login.json --application-id <app-id> --non-interactive --skip-secrets
```

Exit codes: `0` on success, `1` if any file failed to import or was invalid (the valid ones are still imported), `2` for input-validation errors (malformed `--secret`, unknown secret key, or `--non-interactive` set with required secrets unsupplied).

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
| Value or credential shared by **every test of the application** (base API URL, shared admin password) | application variable / application secret (`qa-studio apps variables set`, `qa-studio apps secrets set`) | Defined once on the application, inherited by all its tests; a test's own variable/secret of the same key overrides it, `--var` overrides both. Reference it exactly like a test variable (`{{base_api}}`) or secret (`secret_key`); the test JSON does not need to declare it. |
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

### Same actions for several inputs → one `repeat`

When a test runs the *same* steps for several inputs (log in as each user, open each product), do not copy the steps N times. Author one [`repeat`](./step-types/repeat.md) step with the inputs as rows and the steps once as its children:

```json
{
  "sort": 2,
  "step_type": "repeat",
  "instruction": "Login as each user",
  "repeat_columns": ["email", "role"],
  "repeat_rows": [["alice@example.com", "Administrator"], ["bob@example.com", "Viewer"]],
  "steps": [
    { "sort": 3, "step_type": "browser", "instruction": "Open the login page", "browser_action": "navigate", "browser_args": "{\"url\": \"{{BASE_URL}}/login\"}" },
    { "sort": 4, "step_type": "navigation", "instruction": "Type {{email}} into the email field" },
    { "sort": 5, "step_type": "validation", "instruction": "The header shows the role {{role}}", "validation_type": "bool", "validation_operator": "equals", "validation_value": "true" }
  ]
}
```

Rules of thumb:

- Every column is a `{{column}}` variable inside the children; `{{RepeatIndex}}` / `{{RepeatTotal}}` are added automatically. Precedence: test `variables` < columns < runtime captures < built-ins.
- The `instruction` is the repeat's **label**; it must be unique among the test's repeat steps (`qa-studio run --dataset-file "LABEL=file.csv"` targets it).
- Make the first child a `browser` → `navigate` — browser state is not reset between rows.
- One nesting level, no repeats inside templates, fail-fast on the first failing row.

#### Rows shared by several tests → an application dataset (`dataset_id`)

When the same rows (customers, products, accounts) feed repeats in **two or more tests of one application**, or the rows are maintained by someone who should not edit the tests, put them on the application as a **dataset** and reference it instead of inlining:

```bash
qa-studio apps datasets list <app-id>                                  # is there one already?
qa-studio apps datasets create <app-id> customers --file ./customers.csv --output json   # → "dataset_id"
```

```json
{
  "sort": 2,
  "step_type": "repeat",
  "instruction": "Check each customer",
  "dataset_id": "0192b1c4-5d6e-7f80-9a1b-2c3d4e5f6a7b",
  "steps": [
    { "sort": 3, "step_type": "browser", "instruction": "Open the customer search", "browser_action": "navigate", "browser_args": "{\"url\": \"{{BASE_URL}}/customers\"}" },
    { "sort": 4, "step_type": "navigation", "instruction": "Type {{email}} into the search field" },
    { "sort": 5, "step_type": "validation", "instruction": "The first result shows {{first_name}} {{last_name}}", "validation_type": "bool", "validation_operator": "equals", "validation_value": "true" }
  ]
}
```

- `dataset_id` **replaces** `repeat_columns` + `repeat_rows` — a repeat has one or the other, never both (import rejects both and neither). The columns come from the dataset (`qa-studio apps datasets get <app-id> <dataset-id>`), so `{{email}}` etc. must match *its* header.
- The dataset must belong to the application you import into (`--application-id`). Import fails with `dataset not found in this application` otherwise; dataset ids are per application and per environment, like template UUIDs.
- Export keeps `dataset_id` (rows are never inlined), so a file round-trips within the same application. To move a test to another application, inline the rows or create the dataset there and swap the id.
- Prefer inline rows when only one test uses them or the rows *are* the test's point (edge cases for one flow). Prefer a dataset when editing the rows should change every test at once.
- `--dataset-file "Check each customer=rows.csv"` still replaces the rows for one run; in `--local-only` mode the CLI needs `api/applications.read` to fetch the dataset first (see [Executing Tests](./executing-tests.md#repeat-datasets----dataset-file-labelpath-repeatable)).
- Templates cannot reference datasets (they have no application).

### Variable name conventions

- Snake_case: `order_total`, not `orderTotal` or `OrderTotal`.
- Descriptive, not generic: `cart_count`, not `count`. The agent reads variable names months later in test logs and step previews.
- Match the data: `order_date` for a date, `order_id` for a string ID, `total_with_tax` for a computed number.
- Reserved-name avoidance: don't use `__name__` (double-underscore prefix is reserved for runtime-injected variables, even though there are none in v1). Repeat columns may not be named `UniqueID`, `Time`, `ExecutionID`, `CreatedAt`, `RepeatIndex` or `RepeatTotal`.

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
      "instruction": "Type 'laptop' into the search field"
    },
    {
      "sort": 2,
      "step_type": "navigation",
      "instruction": "Press Enter in the search field"
    },
    {
      "sort": 3,
      "step_type": "retrieve_value",
      "instruction": "Get the product name from the first search result card",
      "capture_variable": "first_result_name",
      "value_type": "string"
    },
    {
      "sort": 4,
      "step_type": "navigation",
      "instruction": "Click the first search result"
    },
    {
      "sort": 5,
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
      "instruction": "Click the 'Create Order' button"
    },
    {
      "sort": 3,
      "step_type": "navigation",
      "instruction": "Enter 'Regression test order' into the 'Notes' field"
    },
    {
      "sort": 4,
      "step_type": "navigation",
      "instruction": "Click the 'Submit' button"
    },
    {
      "sort": 5,
      "step_type": "browser",
      "browser_action": "navigate",
      "browser_args": "{\"url\": \"/orders\"}"
    },
    {
      "sort": 6,
      "step_type": "retrieve_value",
      "instruction": "Get the latest order date from the orders table",
      "capture_variable": "new_latest_date",
      "value_type": "date",
      "value_format": "%d/%m/%Y"
    },
    {
      "sort": 7,
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
- **More than one action or check in a step.** `"Click Save and verify the success banner"` — split into two steps: one `navigation` for the click, one `validation` for the verification. `"Verify the panel shows a 'Name' field, a 'Description' field and a 'Save' button"` — split into three `validation` steps, one per element. A compound step cannot tell you which part failed, and a bool validation over a list is routinely answered `true` when only most of the list is present. See [One action or one check per step](#one-action-or-one-check-per-step) for the full rule and the before/after example.
- **Date capture without a format on regional dates.** If the page renders `01/02/2024`, the date parser refuses to guess. Set `value_format` on the `retrieve_value` to the matching strptime pattern (`"%m/%d/%Y"` for US, `"%d/%m/%Y"` for EU). See [step-types/retrieve_value.md](./step-types/retrieve_value.md).
- **`exportVersion` other than `"1.0"`.** Validators reject anything else. Do not invent versions.
- **Skipping the `--dry-run` before bulk imports.** When importing a directory, `--dry-run` validates every file without uploading. Catches typos and missing required fields before they hit the cloud.
- **Re-using the same `capture_variable` name across steps.** Later captures overwrite earlier ones. If both values are needed downstream, use distinct names.
- **Giving an Electron test a `starting_url` or `url` steps.** `test_platform: "electron"` tests attach to the window the app opened; a `url` step navigates that window away from the application. Describe where to go in `navigation` steps instead ("Open the Projects tab"). Mobile-only fields (`platform`, `bundle_id`, …) are rejected on electron tests at import time.
