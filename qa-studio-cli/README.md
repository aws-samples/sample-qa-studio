# QA Studio CLI

A command-line tool for authenticating, managing, and executing QA Studio tests from the terminal. Uses browser-based OAuth (PKCE) against AWS Cognito for secure authentication.

## Prerequisites

- Python >= 3.11

## Installation

### Basic Installation (Authentication & Management)

```bash
pip install -e ./qa-studio-cli
```

### Full Installation (with Local Test Execution)

```bash
pip install -e "./qa-studio-cli[runner]"
```

### With Bedrock AgentCore Browser Support

Use this when you want to provision remote browsers via Amazon Bedrock AgentCore — either locally against your own AgentCore setup, or inside the cloud worker image (which installs this extra at build time).

```bash
pip install -e "./qa-studio-cli[runner,agentcore]"
```

The `[agentcore]` extra pulls in `bedrock_agentcore`. Without it, `--browser=agentcore` raises a clear install-hint error at runtime.

`--browser agentcore` reads its settings from environment variables — the same ones the worker image carries, so a local run behaves like a cloud run once you export the deployment's values. Nothing is looked up from the deployed configuration.

| Variable | Default | Description |
|---|---|---|
| `BEDROCK_EXECUTION_ROLE` | — (required) | IAM role the AgentCore browser assumes (the stack's `<baseName>-agent_core_execution_role`) |
| `S3_BUCKET` | — (required) | Artefact bucket for the session recording (`{usecase_id}/{execution_id}/recording/`) |
| `AGENT_CORE_VPC` | unset → PUBLIC | `true` puts the browser's network interfaces into a VPC (`networkMode: VPC`), for websites only reachable there |
| `AC_VPC_ID` | — | VPC ID; required when `AGENT_CORE_VPC=true` |
| `AC_SUBNET_IDS` | — | Comma-separated subnet IDs, all passed to the browser in this order; required when `AGENT_CORE_VPC=true` |
| `AC_SECURITY_GROUP_ID` | — | Security group of the browser network interfaces; required when `AGENT_CORE_VPC=true` |

With `AGENT_CORE_VPC=true` a missing `AC_*` value fails the run before any AWS call. For a deployment with `vpcId`, copy the values from the worker image environment (`AC_SUBNET_IDS` = the subnets the stack selected; see [configuration → AgentCore browsers in a VPC](../docs/configuration.md#agentcore-browsers-in-a-vpc)).

### With Interactive Terminal UI

Adds the `textual` dependency so `qa-studio tui` launches an interactive browser for use cases and test suites. Safe to combine with the runner extra.

```bash
pip install -e "./qa-studio-cli[runner,tui]"
```

Without this extra, `qa-studio tui` prints an install hint and exits non-zero.

## Quick Start

```bash
# Configure the CLI with your environment settings
qa-studio configure

# Authenticate via browser-based OAuth
qa-studio login

# Check authentication status
qa-studio status

# Run a test locally
qa-studio run --usecase-id test-123

# Run a test suite
qa-studio run --suite-id suite-456

# Launch the interactive terminal UI (requires the [tui] extra)
qa-studio tui

# Log out (delete stored tokens)
qa-studio logout
```

## Commands

### Authentication

- `qa-studio configure` - Interactive setup for API URL, Cognito domain, and client ID
- `qa-studio login` - Start browser-based OAuth flow and store tokens
- `qa-studio logout` - Delete stored tokens
- `qa-studio status` - Show current authentication status

### Test Management

- `qa-studio tests list` - List all tests
- `qa-studio tests create` - Create a new test
- `qa-studio tests get <id>` - Get test details
- `qa-studio tests update <id>` - Update a test
- `qa-studio tests delete <id>` - Delete a test
- `qa-studio tests run <id> [--trigger-type OnDemandHeadless|ci_runner]` - Start one cloud execution via the API (default `OnDemandHeadless`: the worker runs it; `ci_runner`: record only). The former `OnDemand` choice was removed — the API rejects it
- `qa-studio tests import <path>` - Import test cases from a JSON file or folder (template placeholder steps are expanded by the cloud — see [Templates](#templates))
- `qa-studio tests insert-template <usecase-id> --template-id <uuid> [--position N] [--secret KEY=VALUE]...` - Insert a template's steps into an existing test

### Template Management

- `qa-studio templates list [--format human|json]` - List templates (ID, step count, name, category)
- `qa-studio templates get <id> [--format human|json]` - Show a template's metadata, ordered steps, variables, required secret keys and the tests using it
- `qa-studio templates create <path> [--dry-run] [--format human|json]` - Create a template from a template JSON file; prints the new UUID
- `qa-studio templates export <id> [--output PATH]` - Write a template as a template JSON file (steps carry their `id`) to stdout or a file
- `qa-studio templates update <id> <path> [--dry-run] [--format human|json]` - Replace a template's definition from a (previously exported, edited) template file
- `qa-studio templates delete <id> [--yes]` - Delete a template; tests that used it keep their steps, only the template link is removed

### Suite Management

- `qa-studio suites list` - List all test suites
- `qa-studio suites create --name <name> --description <text> [--tags <tag>]...` - Create a new suite
- `qa-studio suites get <id>` - Get suite details and its use cases
- `qa-studio suites add-tests <suite-id> <usecase-id>...` - Add one or more tests to a suite (idempotent; already-present tests are skipped)
- `qa-studio suites remove-test <suite-id> <usecase-id>` - Remove a test from a suite
- `qa-studio suites run <suite-id> [--base-url <url>] [--var KEY=VALUE]... [--region <region>] [--model-id <id>]` - Start a suite execution via the API (CI runner mode; use `qa-studio run --suite-id` to execute locally)

### Application Configuration

Variables and secrets set on an application are inherited by every use case of that application (precedence: application < use case < `--var` run override). Datasets are named `columns`/`rows` tables a repeat step references by `dataset_id` instead of carrying inline rows (`--dataset-file` still replaces the rows for one run). Reads need the `api/applications.read` scope, writes `api/applications.write`.

| Command | Description |
|---|---|
| `qa-studio apps variables list <app-id> [--output table\|json]` | List the application's variables |
| `qa-studio apps variables set <app-id> KEY=VALUE...` | Set variables; reads the list, merges the keys and writes the whole list back (concurrent writers lose updates) |
| `qa-studio apps variables unset <app-id> KEY...` | Remove variables; fails without writing when a key is not set |
| `qa-studio apps secrets list <app-id> [--output table\|json]` | List the application's secret keys (values are never shown) |
| `qa-studio apps secrets set <app-id> KEY [--value-file PATH]` | Create or update one secret; the value is prompted hidden, or read from `--value-file` (one trailing newline dropped). Never echoed |
| `qa-studio apps secrets delete <app-id> KEY [--yes]` | Delete one secret (no recovery window) |
| `qa-studio apps datasets list <app-id> [--output table\|json]` | List the application's datasets (ID, name, column/row counts) |
| `qa-studio apps datasets get <app-id> <dataset-id> [--output table\|json\|csv]` | Show one dataset with its rows; `csv` round-trips into `--file` |
| `qa-studio apps datasets create <app-id> NAME --file rows.csv\|rows.json [--description TEXT] [--output table\|json]` | Create a dataset. `.csv`: header row names the columns (same parser as `run --dataset-file`); `.json`: `{"columns": [...], "rows": [[...]]}`. Validated client-side with the server's rules before the request |
| `qa-studio apps datasets update <app-id> <dataset-id> [--name NAME] [--description TEXT] [--file PATH] [--output table\|json]` | Change name, description and/or rows (the current dataset is read first; only the given fields change) |
| `qa-studio apps datasets delete <app-id> <dataset-id> [--yes]` | Delete a dataset; a `409` lists the use cases whose repeat steps still reference it |
| `qa-studio apps reassign --app <app-id> --to-team <team-id> [--yes]` | Reassign an application to another team (Admin-only) |

#### Application configuration command options

| Command | Argument / option | Type | Default | Description |
|---------|-------------------|------|---------|-------------|
| `apps variables list <app-id>` | `--output` | `table` \| `json` | `table` | JSON: `{"variables": [{"key", "value"}]}` |
| `apps variables set <app-id> KEY=VALUE...` | `KEY=VALUE` | one or more | required | Key `^[A-Za-z_][A-Za-z0-9_]*$`; the value may contain `=`. Existing keys are updated, others kept |
| `apps variables unset <app-id> KEY...` | `KEY` | one or more | required | Every key must currently exist, otherwise nothing is written (exit 1) |
| `apps secrets list <app-id>` | `--output` | `table` \| `json` | `table` | Keys, Secrets Manager name, description, created-at — never values |
| `apps secrets set <app-id> KEY` | `--value-file` | path | hidden prompt | Read the value from the file (one trailing newline dropped). Key `^[A-Za-z0-9_.-]{1,128}$`; an empty value exits 2 |
| `apps secrets delete <app-id> KEY` | `--yes`, `-y` | flag | `false` | Skip the confirmation prompt. No recovery window |
| `apps datasets list <app-id>` | `--output` | `table` \| `json` | `table` | Summaries only (`dataset_id`, `name`, `column_count`, `row_count`, `updated_at`) |
| `apps datasets get <app-id> <dataset-id>` | `--output` | `table` \| `json` \| `csv` | `table` | `csv` prints the header row + rows and is a valid `--file` / `--dataset-file` input |
| `apps datasets create <app-id> NAME` | `--file` | `.csv` \| `.json` path | required | `.csv`: header row names the columns; `.json`: `{"columns": [...], "rows": [[...]]}`. Validated client-side (1–20 columns, 1–100 rows, 200 KB; exit 2) |
| | `--description` | text | `""` | Optional description |
| | `--output` | `table` \| `json` | `table` | The created dataset |
| `apps datasets update <app-id> <dataset-id>` | `--name` | text | unchanged | New name (unique within the application, case-insensitive; `409` otherwise) |
| | `--description` | text | unchanged | New description; pass `''` to clear |
| | `--file` | `.csv` \| `.json` path | unchanged | New columns + rows (same formats as `create`) |
| | `--output` | `table` \| `json` | `table` | The updated dataset |
| `apps datasets delete <app-id> <dataset-id>` | `--yes`, `-y` | flag | `false` | Skip the confirmation prompt. A `409` lists the referencing use cases under *Referenced by* |

Exit codes: `0` success, `1` API error (a `403` names the missing scope; a `400` lists every failed validation rule; `409` = name conflict or referenced dataset), `2` usage error (malformed `KEY=VALUE`, invalid key, empty secret value, unreadable or invalid dataset file).

Token scopes: `qa-studio login` user tokens carry `api/applications.read` for every team role and `api/applications.write` for Editor+. OAuth client tokens (`OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET`) request a fixed scope list (`qa_studio_cli/auth/client_credentials.py`) that does **not** include the `api/applications.*` scopes, so `apps …` commands and `qa-studio run --local-only` on a use case whose repeat step references an application dataset return 403 under client credentials today; remote runs are unaffected (the server resolves the dataset).

### Test Execution

```bash
# Run a single test
qa-studio run --usecase-id test-123

# Run several tests in one call (sequential, summary at the end)
qa-studio run --usecase-id "test-123 test-456 test-789" --format human

# Stop at the first failure; remaining tests are reported as skipped
qa-studio run --usecase-id "test-123 test-456 test-789" --fail-fast

# Run a test suite
qa-studio run --suite-id suite-456

# Run with base URL override
qa-studio run --usecase-id test-123 --base-url https://staging.example.com

# Run with variable overrides
qa-studio run --usecase-id test-123 --var username=testuser --var password=testpass

# Run in local-only mode (no remote records). A repeat step that references an
# application dataset is fetched by the CLI here (needs api/applications.read)
qa-studio run --usecase-id test-123 --local-only

# Show full runner logging (API calls, engine internals, Nova Act trace)
qa-studio run --usecase-id test-123 --verbose
```

By default a run prints one progress line per test and per step on stderr; stdout carries only the result (JSON document or human summary). See [Execution Output](#execution-output).

### Kiro IDE Integration

- `qa-studio setup` - Install QA Studio skills for Kiro IDE
- `qa-studio uninstall` - Remove QA Studio skills from Kiro IDE

## Importing Test Cases

The `qa-studio tests import` command imports test case JSON files (QA Studio export format) from a file or folder.

### Import Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `path` | positional | required | File or directory path to import |
| `--dry-run` | flag | `false` | Validate only, do not import |
| `--yes` / `-y` | flag | `false` | Skip confirmation prompt |
| `--non-interactive` | flag | `false` | Run without any prompts. Implies `-y`. Exits with code 2 if any secret value is missing — supply via `--secret KEY=VALUE` or use `--skip-secrets` to defer. |
| `--secret` | `KEY=VALUE` (repeatable) | none | Pre-supply a secret value. Suppresses the interactive prompt for that key. Errors if `KEY` is not declared by any imported test. |
| `--base-url` | string | `None` | Override `starting_url` for all imports |
| `--region` | string | `None` | Override `executing_region` for all imports |
| `--application-id` | string | required unless `--dry-run` | Application the tests are imported into. You need edit access (Editor+ of the owning team, or a `full` share) on it. |
| `--skip-secrets` | flag | `false` | Skip interactive secret prompts |
| `--format` | choice | `human` | Output format: `human` or `json` |

### Examples

```bash
# Import a single test file
qa-studio tests import ./login_test.json --application-id <app-id>

# Import all tests from a folder (recursive)
qa-studio tests import ./testcases/ --application-id <app-id>

# Dry-run: validate files without importing
qa-studio tests import ./testcases/ --dry-run

# Import with base URL override (e.g. staging)
qa-studio tests import ./testcases/ --application-id <app-id> --base-url https://staging.example.com --yes

# CI pipeline: JSON output, skip secrets, no prompts
qa-studio tests import ./testcases/ --application-id <app-id> --format json --skip-secrets

# Skip secrets and configure them later in the UI
qa-studio tests import ./login_test.json --application-id <app-id> --skip-secrets

# Fully non-interactive with values supplied (e.g. agent flow, dev/local credentials)
qa-studio tests import ./tests/auth/login.json --application-id <app-id> \
  --non-interactive \
  --secret admin_email=admin@dev.local \
  --secret admin_password="$DEV_ADMIN_PASSWORD"

# Non-interactive deferring secret config to the UI
qa-studio tests import ./tests/auth/login.json --application-id <app-id> --non-interactive --skip-secrets
```

#### Exit codes

- `0` — every file imported successfully.
- `1` — at least one file failed to import or was invalid (valid files in the same run are still imported), or no valid files were found.
- `2` — input validation failure: missing `--application-id`, malformed `--secret KEY=VALUE`, `--secret` referencing an unknown key, or `--non-interactive` set with required secrets unsupplied. The error message lists the missing/unknown keys and the recovery flag.

### Two-Phase Flow

1. **Scan & Validate**: All JSON files are discovered and validated against the export schema. Files that reference templates (see below) have each template fetched once; an unknown template marks the file invalid. A summary table shows valid/invalid files, the referenced template names and the full set of required secrets.
2. **Import**: After confirmation, valid files are sent to the API. Results are displayed per file.

In `--format json` mode, all prompts are suppressed and output is a single JSON object suitable for CI parsing. Each file entry carries `templates: [{id, name}]` and `secretKeys` (file secrets + template secrets).

## Templates

Templates are reusable step sequences (e.g. "Login – Shop") stored in the cloud and identified by a UUID. From the CLI you can list and inspect them, create one from a file, reference one inside a test JSON, and insert one into an existing test. Expansion always happens **server-side**, so inserted steps keep their template linkage (`template_id`, `template_step_id`, `template_version`) and the web UI can offer "update from template" later. Template UUIDs are specific to one QA Studio environment.

### Reference a template in a test JSON

Put a placeholder step where the template's steps belong:

```json
"steps": [
  { "sort": 1, "step_type": "template", "template_id": "3f1c0000-0000-4000-8000-000000000001" },
  { "sort": 2, "step_type": "navigation", "instruction": "Click 'Add to cart' on the first product." }
]
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `sort` | int > 0 | yes | Slot where the template's steps are inserted |
| `step_type` | `"template"` | yes | Not an executable step type |
| `template_id` | string (UUID) | yes | From `qa-studio templates list` / `templates create` |

Any other field on a placeholder fails validation. Placeholders are allowed at the top level only (not inside a `repeat`). On `tests import` the CLI checks every referenced template exists (`step 1: template <id> not found — run 'qa-studio templates list' or 'qa-studio templates create'`, also in `--dry-run`) and prompts for the template's secret keys together with the file's own `secrets` — `--secret`, `--non-interactive` and `--skip-secrets` apply to both. Do not list template secrets in the file's `secrets`.

### Template file format (`templates create`)

```json
{
  "templateVersion": "1.0",
  "template": { "name": "Login – Shop", "description": "…", "category": "auth", "tags": ["shop"] },
  "steps": [
    { "sort": 1, "step_type": "browser", "instruction": "Open the login page.", "browser_action": "navigate", "browser_args": "{\"url\": \"https://shop.example.com/login\"}" },
    { "sort": 2, "step_type": "secret", "instruction": "Click into the email field.", "secret_key": "shop_username" },
    { "sort": 3, "step_type": "secret", "instruction": "Click into the password field.", "secret_key": "shop_password" },
    { "sort": 4, "step_type": "navigation", "instruction": "Click the 'Sign in' button." }
  ],
  "variables": [ { "key": "shop_base_url", "value": "https://shop.example.com" } ]
}
```

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `templateVersion` | `"1.0"` | yes | — | File format version |
| `template.name` | string, min 1 | yes | — | |
| `template.description` | string | no | `""` | |
| `template.category` | string | no | `""` | |
| `template.tags` | string[] | no | `[]` | |
| `steps` | step[], min 1 | yes | — | Same shape as test JSON steps; `template` and `repeat` steps are rejected |
| `steps[].id` | string (UUID) | no | — | Template step id. Written by `templates export`, matched by `templates update`, ignored by `templates create`. Duplicates fail validation |
| `variables` | `{key, value}[]` | no | `[]` | Merged into a test's variables at import (the test's value wins) |

Secrets are not declared in the file; they are derived from the `secret_key` of `secret` steps.

### Change a template (`templates export` → edit → `templates update`)

Never recreate a template to change it: `templates create` makes a new UUID and every placeholder that referenced the old one breaks. Export, edit, update instead:

```bash
qa-studio templates export 3f1c… --output ./templates/login-shop.json   # every step carries its "id"
# edit the file: change instructions, add steps (no "id"), remove steps, change metadata
qa-studio templates update 3f1c… ./templates/login-shop.json --dry-run
# Plan for "Login – Shop": 4 steps updated, 1 created, 0 deleted; metadata changed: description
qa-studio templates update 3f1c… ./templates/login-shop.json
# ✓ Template updated: Login – Shop (version 7; 4 updated, 1 created, 0 deleted)
```

`PUT /templates/{id}` applies the file atomically with a single version bump. Steps with an `id` that exists in the template are updated in place (tests that imported them keep their link and get an "update available" hint); steps without `id` are created; template steps missing from the file are deleted; an `id` that does not belong to the template is a `400` and nothing is written. `sort` is renumbered `1..n` from file order; metadata and variables are replaced with the file's values.

### Delete a template (`templates delete`)

```bash
qa-studio templates delete 3f1c…
# Template "Login – Shop" is used by 2 tests (steps are kept, template link removed). Delete? [y/N]:
qa-studio templates delete 3f1c… --yes     # scripts / CI
```

Tests that imported the template keep their steps unchanged; only the `template_id` / `template_step_id` / `template_version` attributes are removed from those steps, so they no longer show "From template" or "update available". An unknown id exits 1 before the prompt; declining prints `Aborted.` and exits 0.

### Template command options

| Command | Option | Type | Default | Description |
|---------|--------|------|---------|-------------|
| `templates list` | `--format` | `human` \| `json` | `human` | JSON: list of templates with `stepCount` |
| `templates get <id>` | `--format` | `human` \| `json` | `human` | JSON: `{template, steps, variables, secretKeys, usages}`; human output ends with `Used by (N):` |
| `templates create <path>` | `--dry-run` | flag | `false` | Validate the file locally; print name, step count, required secrets; do not create |
| | `--format` | `human` \| `json` | `human` | JSON: `{"id", "name", "stepsCreated"}` |
| `templates export <id>` | `--output` | path | stdout | Write the template file (`indent=2`, trailing newline) here; without it the JSON is printed so `> file` works |
| `templates update <id> <path>` | `--dry-run` | flag | `false` | Print the plan (updated / created / deleted steps, changed metadata fields) computed against the current template; do not write |
| | `--format` | `human` \| `json` | `human` | JSON dry-run: `{"valid": true, "plan": {"created", "updated", "deleted", "metadataChanged"}}`; JSON update: `{"id", "name", "version", "steps_created", "steps_updated", "steps_deleted"}` |
| `templates delete <id>` | `--yes`, `-y` | flag | `false` | Skip the confirmation prompt |
| `tests insert-template <usecase-id>` | `--template-id` | UUID string | required | Template to insert |
| | `--position` | int ≥ 1 | append | The template's first step becomes step N; following steps shift and all steps are renumbered `1..n` |
| | `--secret` | `KEY=VALUE` (repeatable) | none | Set a template secret value after the insert. A key the template does not use exits with code 2 before anything is inserted. |
| | `--format` | `human` \| `json` | `human` | JSON: `{"usecaseId", "templateId", "position", "stepsCreated", "secretsSet", "missingSecrets"}` |

```bash
qa-studio templates list
qa-studio templates get 3f1c0000-0000-4000-8000-000000000001
qa-studio templates create ./templates/login-shop.json --dry-run
qa-studio templates create ./templates/login-shop.json
# ✓ Template created: Login – Shop (ID: 3f1c0000-0000-4000-8000-000000000001)

qa-studio templates export 3f1c0000-0000-4000-8000-000000000001 --output ./templates/login-shop.json
qa-studio templates update 3f1c0000-0000-4000-8000-000000000001 ./templates/login-shop.json --dry-run
qa-studio templates update 3f1c0000-0000-4000-8000-000000000001 ./templates/login-shop.json
qa-studio templates delete 3f1c0000-0000-4000-8000-000000000001 --yes

qa-studio tests insert-template <usecase-id> --template-id 3f1c… --position 2 \
  --secret shop_username=qa@dev.local --secret shop_password="$DEV_SHOP_PASSWORD"
# ✓ Inserted 4 step(s) from template 3f1c… at position 2
```

#### Exit codes

- `0` — success (also `templates delete` when the prompt is declined — prints `Aborted.`).
- `1` — API error (template or test not found, position out of range, insufficient scopes, `400` from `templates update`), invalid template file, an exported file's step `id` that does not belong to the template, an unwritable `--output` path, or a secret value could not be stored.
- `2` — usage error: `--position` < 1, malformed `--secret`, a `--secret` key the template does not use, or a missing template file.

## Configuration

Running `qa-studio configure` stores settings in `~/.qa-studio/config.json`.

> **Important — `api_url` must include the `/api` base path.** The value must
> point at the API, ending in `/api`. Either host works:
>
> - API Gateway invoke URL: `https://<api-id>.execute-api.<region>.amazonaws.com/api/`
> - CloudFront domain: `https://<cloudfront-domain>/api`
>
> If you leave off `/api` (for example, using the bare CloudFront URL
> `https://<cloudfront-domain>`), requests route to the web-app origin instead
> of the API and fail with a confusing `403` that has no error detail. Verify
> your setting with `qa-studio status`.

You can override any config value with environment variables:

| Environment Variable         | Overrides              | Description |
|------------------------------|------------------------|-------------|
| `QA_STUDIO_API_URL`         | `api_url`              | API base URL |
| `QA_STUDIO_COGNITO_DOMAIN`  | `cognito_domain`       | Cognito domain |
| `QA_STUDIO_CLIENT_ID`       | `client_id`            | Cognito client ID |
| `OAUTH_CLIENT_ID`           | `oauth_client_id`      | OAuth M2M client ID |
| `OAUTH_CLIENT_SECRET`       | `oauth_client_secret`  | OAuth M2M client secret |
| `OAUTH_TOKEN_ENDPOINT`      | `oauth_token_endpoint` | Cognito token endpoint URL |

Environment variables take precedence over file values.

### API retries

Every API call retries transient responses — `429`, `500`, `502`, `503`, `504` and connection errors — up to 7 attempts with exponential backoff (1 s → 16 s, plus up to 3 s of random jitter), about a minute in total. Each retry is logged as `API retry n/7 in Ns: [status] message` (visible with `--verbose`). The schedule is sized for a suite fan-out on the cloud worker, where many runners call the API within the same seconds and the endpoint Lambdas' reserved concurrency makes API Gateway answer 500 for a while. `4xx` client errors other than `429` are never retried.

## Authentication

The CLI supports multiple authentication methods, resolved in this priority order:

1. **Token file** (`--token-file` flag) — pre-generated token JSON
2. **Environment variables** (`OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` / `OAUTH_TOKEN_ENDPOINT`) — M2M client credentials
3. **Config file M2M credentials** (`oauth_client_id` / `oauth_client_secret` / `oauth_token_endpoint` in `~/.qa-studio/config.json`)
4. **Stored user token** from `qa-studio login` (with auto-refresh)

### Interactive Login (Development)

```bash
qa-studio login    # Opens browser for Cognito hosted UI login
qa-studio status   # Check current auth status
qa-studio logout   # Delete stored tokens
```

### OAuth Client Credentials (CI/CD, Headless)

No browser login required. Set all three environment variables:

```bash
export OAUTH_CLIENT_ID="your-m2m-client-id"
export OAUTH_CLIENT_SECRET="your-m2m-client-secret"
export OAUTH_TOKEN_ENDPOINT="https://your-cognito-domain.auth.region.amazoncognito.com/oauth2/token"

qa-studio run --suite-id suite-456
```

Or add them to `~/.qa-studio/config.json`:

```json
{
  "api_url": "https://your-api-host/api",
  "cognito_domain": "https://your-cognito-domain.auth.region.amazoncognito.com",
  "client_id": "your-public-client-id",
  "oauth_client_id": "your-m2m-client-id",
  "oauth_client_secret": "your-m2m-client-secret",
  "oauth_token_endpoint": "https://your-cognito-domain.auth.region.amazoncognito.com/oauth2/token"
}
```

M2M tokens are cached in memory and automatically refreshed before expiry (5-minute buffer).

Granted scopes: `api/suite.read`, `api/suite.write`, `api/usecases.read`, `api/usecases.execute`, `api/executions.read`, `api/executions.write`.

### Token File

```bash
qa-studio run --token-file /path/to/token.json --usecase-id test-123
```

See [CI/CD Integration Guide](../docs/ci-cd-integration.md) for detailed pipeline examples.

## Local Test Execution

The `qa-studio run` command requires the runner dependencies:

```bash
pip install -e "./qa-studio-cli[runner]"
```

### Execution Options

| Option | Description |
|--------|-------------|
| `--usecase-id` | Single test ID to execute |
| `--suite-id` | Test suite ID to execute |
| `--local-only` | Local-only execution (no remote records) |
| `--base-url` | Override base URL for all tests |
| `--var` | Override variable (key=value, repeatable) |
| `--region` | AWS region for the run's regional AWS calls, in local **and** remote mode. Local: the browser provisioner context and the S3 app-binary download (mobile). Suite runs: the region of the created executions. Precedence: `--region` > `AWS_REGION` / `AWS_DEFAULT_REGION` > AWS profile region. Nova Act always runs in `us-east-1` and Device Farm in `us-west-2`; `--region` does not move them |
| `--model-id` | Override Nova Act model ID |
| `--verbose` | Show full runner logging (API calls, engine internals, Nova Act think/act trace). Default output is one progress line per test and per step, on stderr. |
| `--timeout` | Stop the **whole run** after N seconds (integer ≥ 1). Default: no limit. Checked before each test and each step; on expiry the running test fails with `Run timed out after Ns (--timeout)`, remaining tests are `skipped`, browsers are torn down, remote executions are marked failed, and the exit code is `3`. A step that hangs is hard-stopped 30 s after the deadline. The ECS worker passes no `--timeout` |
| `--keep-artifacts` | Keep local artifact files after upload |
| `--format` | Output format (json or human) |

**SIGTERM** (a cancelled CI job, `qa-studio tui` stopping a run, the cloud worker's supervisor) stops the run the same way `--timeout` does: the running test fails, remaining tests are skipped, browsers / AgentCore sessions are torn down and remote executions are PATCHed `failed`. The step that is running gets 10 s to finish; a step that hangs is hard-stopped after that. Two optional environment variables set by the parent process shape the report:

| Variable | Type | Default | Meaning |
|----------|------|---------|---------|
| `QA_STUDIO_TERMINATION_REASON` | `terminated` \| `timeout` | `terminated` | `error_message` of the failed execution starts with `terminated: run stopped by SIGTERM` or `timeout: run exceeded the configured ceiling`; the exit code is `143` or `3` |
| `QA_STUDIO_MAX_DURATION_SECONDS` | integer | unset | With reason `timeout`, the ceiling named in the message (`… ceiling of 3600s`) |

An execution the API already considers terminal (e.g. stopped from the web UI before the signal arrived, `409`/`400`) is logged and not PATCHed again.

Exit codes of `qa-studio run`:

| Code | Meaning |
|------|---------|
| `0` | All tests passed |
| `1` | A test failed or was skipped |
| `2` | Runner error (bad ID, no AWS session, API unreachable) |
| `3` | `--timeout` stopped the run, or SIGTERM with `QA_STUDIO_TERMINATION_REASON=timeout` |
| `143` | SIGTERM stopped the run |

### Execution Output

Default output is one line when the test starts and one line when each step starts — no per-step completion line; the verdict is in the summary at the end:

```
$ qa-studio run --usecase-id 7f3a… --local-only --format human
[14:02:11] Executing Test "Login with valid credentials"
[14:02:14] Step 1: Open the login page
[14:02:19] Step 2: Type the username into the email field
[14:02:23] Step 3: Click into the password field
[14:02:27] Step 4: Click "Sign in"
[14:02:33] Step 5: Check the greeting in the header (Welcome back, Jane)

QA Studio - Local Execution

Test: Login with valid credentials
Duration: 24s
  ✓ [navigation] Open the login page (3s)
  …
✓ PASSED  |  Steps: 5/5 passed  |  Failed: 0
```

- Validation steps append the expected value in parentheses; repeat rows render as `Step 3 (row 2/5)`; in suite runs every step line is prefixed with `[<test name>]`; remote runs append ` (execution <id>)` to the test line.
- Progress lines go to **stderr**, the result (JSON or human summary) to **stdout** — `qa-studio run … 2>/dev/null | jq .status` works. Warnings and errors are always shown.
- `--verbose` adds the runner's DEBUG logging (API calls, engine internals) and the Nova Act think/act trace. The log artifact always has the full DEBUG log: locally `/tmp/qa-studio-artifacts/<usecase-id>/logs.txt` (reported as `artifacts.logs` in the JSON result), in remote mode the uploaded `logs.txt`.

The full line formats are documented in [docs/ci-cd-integration.md](../docs/ci-cd-integration.md#qa-studio-run).

### Examples

```bash
# Run test against staging environment
qa-studio run --usecase-id test-123 --base-url https://staging.example.com

# Run suite with variable overrides
qa-studio run --suite-id suite-456 --var env=staging --var user=testuser

# Run locally without creating remote execution records
qa-studio run --usecase-id test-123 --local-only

# Run an Electron desktop test (the runner launches the app and attaches over CDP)
qa-studio run --usecase-id desktop-test-123 --app-path "/Applications/My App.app"
qa-studio run --usecase-id desktop-test-123 --local-only \
  --app-path node_modules/electron/dist/Electron.app --app-arg ./packages/app

# Run with custom region and model
qa-studio run --usecase-id test-123 --region us-west-2 --model-id anthropic.claude-3-5-sonnet-20240620-v1:0
```

### Runtime Header & Secret Overrides (local-only)

For iterating locally with a different bearer token, a rotated
secret, or a one-off feature-flag header — without editing the use
case. These flags apply **only** with `--local-only`; using them on
the remote path produces an error.

```bash
# Single inline header (non-sensitive values)
qa-studio run --usecase-id test-123 --local-only \
  --header X-Feature-Flag=debug

# Sensitive headers via file (Bearer tokens, cookie headers) —
# argv-safe so the value isn't visible in `ps` or shell history
cat > /tmp/headers.json <<EOF
{ "Authorization": "Bearer my-dev-token" }
EOF
qa-studio run --usecase-id test-123 --local-only \
  --headers-file /tmp/headers.json

# Secret overrides — file-only, never argv
cat > /tmp/secrets.json <<EOF
{ "admin_password": "newly-rotated-value" }
EOF
qa-studio run --usecase-id test-123 --local-only \
  --secrets-file /tmp/secrets.json
```

**Precedence on header collisions:** `API stored headers ← --headers-file ← --header flags`. The
right-most source wins. Secret overrides short-circuit the API
secret lookup by key — keys not listed in `--secrets-file` fall
through to the normal `GET /usecase/{id}/secrets/{key}/value` path.

## Interactive Terminal UI

`qa-studio tui` launches a [Textual](https://github.com/Textualize/textual)-based terminal UI for browsing use cases and test suites, inspecting their detail, and triggering **local** runs with a live log tail. It reuses the same API client and authentication chain as every other subcommand; existing CLI commands stay unchanged.

### Requirements

Install the `[tui]` extra (see Installation above). Without it the subcommand prints a pip-install hint and exits non-zero.

The TUI requires a valid token — run `qa-studio login` first. An expired token surfaces as a clear `Authentication required` message, not a stack trace.

### Launch

```bash
qa-studio tui
```

### Navigation

| Key      | Scope          | Action                                  |
|----------|----------------|-----------------------------------------|
| `q`      | Global         | Quit                                    |
| `1`      | Global         | Jump to Use cases list                  |
| `2`      | Global         | Jump to Test suites list                |
| `?`      | Global         | Help overlay (placeholder)              |
| `/`      | List screens   | Focus the client-side filter input      |
| `Enter`  | List screens   | Open the selected item's detail         |
| `r`      | List & detail  | Refresh from the API                    |
| `R`      | Use case detail| Open the Run form                       |
| `e`      | Use case detail| Open the use case in the web app        |
| `Esc`    | Detail / form  | Go back (confirm when a run is active)  |
| `k`/`^C` | Live tail      | Terminate the subprocess                |

### Features

| Feature                       | Notes                                                                                       |
|-------------------------------|---------------------------------------------------------------------------------------------|
| Use-case + suite lists        | Full lists with client-side substring filter on name + id (instant, no extra HTTP)          |
| Use-case detail header        | Name, active status, platform, region, model, URL, description, tags, creator, timestamps  |
| Steps tab                     | Vertical split (60/40): table left, live detail pane right. Cursor moves update the pane   |
| Step detail pane              | Empty fields hidden; nested `dict`/`list` values pretty-printed as JSON                    |
| Suite detail                  | Metadata + member use-cases table, Enter drills into the corresponding use case             |
| Run form                      | Pre-filled from the API; variables, headers, and secrets rendered as inputs (secrets masked)|
| Runtime overrides             | Changed fields become overrides; secrets delivered via `0600` tempfile, never argv          |
| Local-only / remote toggle    | Default **on**. Untick to create a remote execution record visible in the web app           |
| Verbose toggle                | Off by default — runner logs at INFO. Tick for DEBUG                                        |
| Live tail                     | Streams stdout/stderr line-by-line with `[stderr]` prefix; final status shows exit code     |
| Terminate                     | SIGTERM to the process group (kills Chromium/Playwright descendants); SIGKILL after 5 s     |
| Edit in browser               | `e` on the use case detail opens `{web_url}/usecase/{id}` via the default browser           |

### Configuring "Edit in browser"

The Edit action opens `{web_url}/usecase/<id>` in your default browser. Set `web_url` in `~/.qa-studio/config.json` — the interactive `qa-studio configure` prompt asks for it, or you can edit the JSON directly.

If `web_url` is unset, pressing `e` shows a notification pointing at `qa-studio configure` rather than silently failing.

### Out of scope for the POC

- In-TUI editing of use cases / suites / steps — use the web app via `e`
- Templates list / detail
- Live monitor for cloud-worker executions
- Pagination or server-side search (filter is client-side over the full result)
- Header / secret overrides with `Local only` unticked — enforced at submit time with a clear error

## Development

Install dev dependencies:

```bash
pip install -e ./qa-studio-cli
pip install -r qa-studio-cli/requirements-dev.txt
```

Run tests:

```bash
cd qa-studio-cli
pytest tests/
```

Run tests with coverage:

```bash
cd qa-studio-cli
pytest --cov=qa_studio_cli tests/
```
r qa-studio-cli/requirements-dev.txt
```

Run tests:

```bash
cd qa-studio-cli
pytest tests/
```

Run tests with coverage:

```bash
cd qa-studio-cli
pytest --cov=qa_studio_cli tests/
```
