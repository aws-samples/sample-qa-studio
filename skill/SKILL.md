---
name: qa-studio
description: >
  Create, edit, and execute browser-based UI tests using QA Studio and Amazon Nova Act.
  Use when the developer wants to build a test case (in JSON or via the CLI), modify
  an existing test, or run an existing test case locally. Covers test authoring,
  editing, importing test cases, reusing templates (shared login / setup steps),
  finding existing tests and suites, and running them with variable / header / secret
  overrides. Also trigger when the user asks about
  browser regression testing, UI test coverage, verifying user flows after a code change,
  or anything that sounds like "make sure this page still works" or "write me a
  regression test for this flow." NOT for unit tests, API tests, or CI/CD pipeline
  configuration — only browser-based UI test authoring and execution.
---

# QA Studio — Browser Test Automation

## Overview

QA Studio drives browser-based UI tests using Amazon Nova Act. A test (called a "use case") is a sequence of steps with a starting URL, optional variables, and optional secrets. Steps cover navigation, value retrieval, validation, assertions, transforms, secret injection, file downloads, browser controls, and network-request matching.

**This skill covers two flows:**

- **Building a test case** — authoring the JSON shape, choosing step types, wiring variables, importing existing test JSON.
- **Executing a test case** — finding tests/suites, running them locally, overriding variables / headers / secrets, reading the output.

Out of scope here: CI/CD pipeline setup, cloud deployment, the web interface, scheduled runs, and the interactive TUI (`qa-studio tui` is for humans).

---

## Decision Tree

### The user wants to build a test

→ See [📝 Building Tests](./reference/building-tests.md) for the full guide. Quick paths:

- **Hand-author the JSON** *(preferred when an agent is helping)* — write the JSON to a file under `./tests/`, then push to the cloud via Importing tests. The agent IS the AI; calling Nova Act through the CLI to generate steps adds an unnecessary layer. **One action or one check per step** — never bundle several verifications into one instruction (see [One action or one check per step](./reference/building-tests.md#one-action-or-one-check-per-step)).
- **Generate from a user-journey description** *(fallback)* — `qa-studio tests create --from-journey ... --export-to ./tests/`. Use when the user explicitly wants the CLI's draft, or when the agent's context isn't enough to author the test directly.
- **Import an existing JSON or push edits to the cloud** — `qa-studio tests import <path> --application-id <app-id>`. Validates and uploads. Same command for both authoring paths above. See [Importing tests](./reference/building-tests.md#importing-tests) for flags (`--application-id` (required unless `--dry-run`), `--dry-run`, `--base-url`, `--skip-secrets`, `--format json`) and the secret-prompt behavior.
- **Import end-to-end through chat (ready-to-run)** — `qa-studio tests import <path> --application-id <app-id> --non-interactive --secret KEY=VALUE [--secret KEY=VALUE]...`. Use only for non-prod / dev / dummy credentials. **Mandatory caveat:** whenever you import with values inline (whether the user volunteers them or you ask), you MUST warn the user that credentials will appear in the **chat transcript**, the **model context**, and the **shell command line** — all three keywords are required. Use this template: "Heads up: anything you paste in this chat lands in the **chat transcript**, the **model context**, and the **shell command line** I'll execute. That's fine for dev or local accounts, but don't paste production credentials — for those, I'll use `--skip-secrets` and you can set them in the QA Studio UI." See [Agent flow: ready-to-run import](./reference/building-tests.md#agent-flow-ready-to-run-import) for the full decision logic.
- **Reuse steps across tests (templates)** — *before* hand-authoring login / setup steps, run `qa-studio templates list`. Reuse by putting `{ "sort": N, "step_type": "template", "template_id": "<uuid>" }` in the test's `steps` (expanded by the cloud at import; template secrets are prompted with the file's own). Create a template with `qa-studio templates create <file>` when the same sequence appears in ≥ 2 tests. Add one to a test that already lives in the cloud with `qa-studio tests insert-template <usecase-id> --template-id <uuid> [--position N]`. See [🧩 Templates](./reference/templates.md).
- **Change an existing template** — `qa-studio templates export <id> --output <file>` → edit the file (keep the step `id`s) → `qa-studio templates update <id> <file> --dry-run` → `qa-studio templates update <id> <file>`. **Never recreate a template to change it**: `templates create` makes a new UUID and every placeholder / inserted reference to the old one breaks. Delete a throwaway template with `qa-studio templates delete <id> [--yes]` (tests that used it keep their steps; only the template link is removed). See [Change a template](./reference/templates.md#change-a-template-export--edit--update).
- **Same rows for several tests of one application (customers, products, accounts)** — reference an application dataset from the `repeat` step (`"dataset_id": "<id>"` instead of `repeat_columns` / `repeat_rows`; `qa-studio apps datasets list|create <app-id>`), so editing the rows once changes every test. Shared values and credentials go on the application too (`qa-studio apps variables set`, `qa-studio apps secrets set`) and are inherited by its tests. See [Rows shared by several tests](./reference/building-tests.md#rows-shared-by-several-tests--an-application-dataset-dataset_id) and [repeat](./reference/step-types/repeat.md).
- **Pick the right step type for a goal** — see [🎯 Step Types](./reference/step-types/) (one file per type).
- **Choose a validation operator** — see [✅ Validation Operators](./reference/validation-operators.md).

### The user wants to run a test

→ See [▶️ Executing Tests](./reference/executing-tests.md) for the full guide. Quick paths:

- **Find an existing test or suite** — `qa-studio tests list` / `qa-studio suites list` / `qa-studio tests get <id>`
- **Run one or more tests locally** — `qa-studio run --usecase-id <id>` or `qa-studio run --usecase-id "<id> <id> <id>"` (quoted, whitespace-separated; sequential with one summary at the end; `--fail-fast` stops at the first failure). See [Running several tests at once](./reference/executing-tests.md#running-several-tests-at-once).
- **Run a suite locally** — `qa-studio run --suite-id <id>`
- **Override variables, base URL and repeat datasets at runtime** — `--var KEY=VALUE` (repeatable), `--base-url <url>`, `--dataset-file [LABEL=]file.csv` (feeds a `repeat` step from CSV). Per-run secret/header/cookie overrides are NOT supported on `qa-studio run` today; secrets are configured per-use-case at import time. See [▶️ Executing Tests](./reference/executing-tests.md#runtime-overrides) for the full surface.
- **Choose the browser provisioner** — `--browser local|agentcore|cdp-external`
- **Run an Electron desktop test** — `qa-studio run --usecase-id <id> --app-path <App.app>`; the runner launches the app itself. See [Electron execution](./reference/executing-tests.md#electron-execution).

### The user wants to edit an existing test

When the UI changed, a step is broken, or the user wants to add/remove steps from an already-imported test:

1. **Get the test JSON locally.** If the file is already on disk under `./tests/`, edit it there. If not, use `qa-studio tests get <id>` to inspect the current steps, then recreate the JSON on disk (there is no `qa-studio tests export` command yet — the local file is the source of truth).
2. **Edit the steps.** Apply the fix — update instructions, change step types, add/remove steps, renumber `sort` values. Use the [🎯 Step Types](./reference/step-types/) reference for per-step guidance.
3. **Re-import.** `qa-studio tests import <path>` pushes the updated version to the cloud as a **new use case** (a new ID; the old one is not overwritten or deleted). Delete the superseded test with `qa-studio tests delete <old-id>` once the new one passes, and point suites at the new ID. To add shared steps to the existing cloud test instead, use `qa-studio tests insert-template <id> --template-id <uuid>`.
4. **Re-run.** `qa-studio run --usecase-id <id>` to verify the fix. If the change touches several tests (a shared variable, a renamed page element), re-run all of them in one call: `qa-studio run --usecase-id "<id> <id>" --format human`.

Common edit scenarios: tightening a vague step instruction, replacing a hardcoded value with a variable, converting a `navigation` step to a `secret` step for a credential field, updating a `validation_value` after a UI text change.

### The test is failing

→ See [🔧 Troubleshooting](./reference/troubleshooting.md) for build-time and execute-time failure recovery.

---

## Common Workflows

### Workflow 1: Hand-author a test, import it, run it locally

The default agent flow. The agent reads the user's description, drafts the JSON directly using [📝 Building Tests](./reference/building-tests.md) and the [🎯 Step Types](./reference/step-types/), saves the file, and imports it. No CLI-side AI generation involved.

```bash
# (Agent writes ./tests/checkout-flow.json based on the user's description.)

# Validate the JSON before uploading.
qa-studio tests import ./tests/checkout-flow.json --dry-run

# Import for real.
qa-studio tests import ./tests/checkout-flow.json --application-id <app-id>

# Run it against a local dev server.
qa-studio run --usecase-id <id> --base-url http://localhost:3000

# Artifacts (video, screenshots, logs) land in ~/.qa-studio/artifacts/<usecase-id>/
```

### Workflow 2: Find an existing test, run it with overrides

```bash
# Find the test by listing.
qa-studio tests list

# Inspect its steps before running.
qa-studio tests get <id>

# Run with variable overrides and a different base URL.
qa-studio run --usecase-id <id> \
  --base-url https://staging.example.com \
  --var environment=staging \
  --var feature_flag=on
```

### Workflow 3: Reuse a login template in a new test

```bash
# Is there a login template already?
qa-studio templates list
qa-studio templates get <template-id>      # steps + "Required secrets: shop_username, shop_password"

# (Agent writes ./tests/checkout.json with
#  { "sort": 1, "step_type": "template", "template_id": "<template-id>" } as the first step.)

qa-studio tests import ./tests/checkout.json --dry-run   # checks the template exists, lists required secrets
qa-studio tests import ./tests/checkout.json             # prompts for shop_username / shop_password
qa-studio run --usecase-id <id>

# No fitting template? Write ./templates/login-shop.json (see Templates reference) and
qa-studio templates create ./templates/login-shop.json   # → ID to reference
```

### Workflow 4: Import a test from JSON, then run a suite

```bash
# Validate the JSON shape without importing.
qa-studio tests import ./tests/login.json --dry-run

# Import for real.
qa-studio tests import ./tests/login.json --application-id <app-id>

# Find the suite and run it.
qa-studio suites list
qa-studio run --suite-id <suite-id> --base-url http://localhost:3000
```

---

## Reference Documentation

Load these as needed for detailed guidance:

- [📝 Building Tests](./reference/building-tests.md) — test case JSON shape, step decision tree, variable wiring, import flow, worked examples
- [▶️ Executing Tests](./reference/executing-tests.md) — finding tests/suites, running locally, runtime overrides, application-level variables/secrets/datasets (`qa-studio apps …`), browser provisioner, mobile execution, output reading
- [🎯 Step Types](./reference/step-types/) — one file per step type with when-to-use, when-not-to-use, inputs, examples, pitfalls
- [🧩 Templates](./reference/templates.md) — reuse step sequences: list/inspect, placeholder step, template file format, export → edit → update an existing template, delete (linked tests keep their steps), insert into an existing test, UUID-per-environment caveat
- [✅ Validation Operators](./reference/validation-operators.md) — string, number, boolean, date operators
- [🔧 Troubleshooting](./reference/troubleshooting.md) — build- and execute-time failures

---

## Key Concepts

### Test (Use Case)
A test defines a starting URL, an ordered list of steps, optional variables, and optional secrets. Stored as JSON; the same shape is what the import command consumes and what the CLI writes when generating a test.

### Step
The atomic unit of a test. Each step has a `step_type` plus type-specific fields. The 10 active step types are: `navigation`, `browser`, `secret`, `validation`, `retrieve_value`, `assertion`, `download`, `transform`, `network_assertion`, `repeat` (a data-driven loop whose nested `steps` run once per dataset row). (`url` is deprecated — use `browser` with `browser_action: navigate`.)

**One step does exactly one thing: one UI action, or one check of one value.** An instruction like "Verify the panel shows a 'Name' field, a 'Description' field and 'Save' and 'Cancel' buttons" is four checks and must become four `validation` steps. Lists, "and", colons followed by enumerations, or several verbs in an instruction are the signal to split. See [One action or one check per step](./reference/building-tests.md#one-action-or-one-check-per-step).

### Variable
A named value that flows between steps. Variables come from three sources: the test's `variables` array (defined at authoring time), `retrieve_value` and `transform` step outputs (`capture_variable`), and runtime overrides (`--var KEY=VALUE`). Reference them in any string field with `{{ variable_name }}`.

### Secret
A named credential resolved at execution time. Authored steps reference secrets by `secret_key`; the actual values come from the configured secret resolver (typically AWS Secrets Manager) or are entered at import time via the interactive secret prompt. **Every field on a login or authentication form is a secret — usernames, emails, passwords, MFA codes, OTP codes, security-question answers — not just the password.** There is no per-run `--secrets-file` override on `qa-studio run`; if a secret value needs to change, re-import the test or update via the web UI.

### Template
A named, reusable step sequence (plus variables) such as "Login – Shop", identified by a UUID that is specific to one QA Studio environment. A test references it with a placeholder step `{ "sort", "step_type": "template", "template_id" }`; `tests import` checks the template exists and the cloud expands it into linked steps (so template edits later surface as "update available"). Templates cannot nest, cannot contain `repeat` steps, and declare no secrets — their `secret` steps' `secret_key`s are prompted at import. Manage with `qa-studio templates list|get|create|export|update|delete` and `qa-studio tests insert-template`; change an existing template with `export` → edit → `update` (never recreate it — the UUID would change).

### Test Suite
A collection of tests that execute together. Use suites when several tests share the same starting URL, variables, or run cadence. Authored separately; the skill covers running suites but not authoring them (suite *authoring* is out of scope).

---

## Examples

### Example 1: Hand-author a test as JSON, then import it

The agent's preferred path. The agent writes the JSON file based on the user's description, using [📝 Building Tests](./reference/building-tests.md) for the shape and the [🎯 Step Types](./reference/step-types/) for per-step authoring details.

```bash
# After writing ./tests/user-registration.json:
qa-studio tests import ./tests/user-registration.json --application-id <app-id>
```

If the agent's context isn't enough to author the test directly, fall back to `qa-studio tests create --from-journey ... --export-to ./tests/` which delegates the drafting to Nova Act and writes the result to disk.

### Example 2: Run a single test locally with overrides

```bash
qa-studio run --usecase-id abc123 \
  --base-url http://localhost:3000 \
  --var username=testuser \
  --var environment=local \
  --verbose
```

Secrets are resolved per use case (configured at import time or in the web UI), not via a per-run flag — see [▶️ Executing Tests](./reference/executing-tests.md#runtime-overrides) for the full override surface.

### Example 3: Run a suite without remote execution records

```bash
qa-studio run --suite-id def456 \
  --base-url https://staging.example.com \
  --var environment=staging \
  --local-only
```

---

## Error Handling

### Test Not Found

```
Error: Use case not found
```

The ID does not exist. Confirm with `qa-studio tests list` and check the user passed the right value.

### Step Failed During Execution

```
✘ Step 3/6 failed: Element not found
```

Common causes: page hadn't loaded yet, wrong base URL, UI changed since the test was written. Review the recording at `~/.qa-studio/artifacts/<usecase-id>/recording.webm`. For systematic recovery patterns, see [🔧 Troubleshooting](./reference/troubleshooting.md).

### Date Parse Failure on retrieve_value

```
Date parse failed for retrieve_value: Date string '01/02/2024' is ambiguous; provide a format argument or use ISO 8601.
```

The agent must set `value_format` on the step to a strptime pattern matching what the page renders (e.g. `%d/%m/%Y` for EU, `%m/%d/%Y` for US). See [🎯 retrieve_value step](./reference/step-types/retrieve_value.md).

### Auth Errors

```
Error: Not authenticated
```

The user needs to authenticate; the agent should not attempt to do this automatically. Tell the user to run `qa-studio login`. Authentication setup is a one-time human action and out of this skill's scope.
