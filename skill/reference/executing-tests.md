# Executing Tests

How to run a QA Studio test from the CLI — finding the test, running it, overriding values at runtime, choosing a browser provisioner, and reading the output.

## Table of contents

- [Finding tests and suites](#finding-tests-and-suites)
- [Running a single test](#running-a-single-test)
- [Running a suite](#running-a-suite)
- [Runtime overrides](#runtime-overrides)
- [Browser provisioner choice](#browser-provisioner-choice)
- [Mobile execution](#mobile-execution)
- [Electron execution](#electron-execution)
- [Output and artifacts](#output-and-artifacts)
- [Common execution pitfalls](#common-execution-pitfalls)

---

## Finding tests and suites

Before running, the agent often needs to look up the right ID. Four list/get commands exist:

```bash
# List all tests in the cloud account.
qa-studio tests list

# Show the steps and metadata of a single test.
qa-studio tests get <id>

# List all suites in the cloud account.
qa-studio suites list

# Show metadata + member tests of a single suite.
qa-studio suites get <id>
```

Use the listing commands to disambiguate when the user refers to a test by name ("run the login test"). If multiple tests match by name, ask the user which ID to use rather than guessing.

`tests get` prints a numbered list of steps in the order they execute — useful for the agent to reason about what a test does before running it.

---

## Running a single test

```bash
qa-studio run --usecase-id <id>
```

The default flow:

1. Reads the test from the cloud.
2. Resolves any secrets the test references (against the configured secret resolver).
3. Spins up a browser via the local provisioner (default).
4. Executes each step in order. On any failure, the run stops and returns non-zero.
5. Stores artifacts (video, screenshots, logs) under `~/.qa-studio/artifacts/<usecase-id>/` locally.
6. Posts the execution record back to the cloud (unless `--local-only`).

### Single-test flags worth knowing

- `--local-only` — skip cloud-side execution records. Useful for fast local iteration; nothing is persisted in the cloud.
- `--keep-artifacts` — keep the local artifact files after the run completes (default behaviour deletes them after upload in cloud mode).
- `--verbose` — show full runner logging: API calls, engine internals and the Nova Act think/act trace. Default output is one line per test and per step.
- `--timeout <seconds>` — limit for the whole run (integer ≥ 1). Default: no limit. On expiry the running test fails with `Run timed out after Ns (--timeout)`, the remaining tests are `skipped`, and the exit code is `3`; a hanging step is hard-stopped 30 s after the deadline.
- `--format json` — machine-readable run output (status, IDs, durations) instead of human prose. Useful when piping to another tool. Progress lines go to stderr, so capturing stdout yields only the JSON document (`qa-studio run … --format json 2>/dev/null | jq .status`).

---

## Running several tests at once

```bash
qa-studio run --usecase-id "<id-a> <id-b> <id-c>" --format human
```

`--usecase-id` takes one or more IDs separated by whitespace — quote the value. A single ID (quoted or not) behaves exactly as before.

What happens:

1. Every definition is fetched first. An unknown ID exits with code 2 before any browser is launched.
2. The tests run sequentially, in the order given, each with a fresh browser (or Electron app). In cloud mode each test gets its own execution record; there is no suite grouping.
3. In `--format human` each test's detail is printed as it finishes; `--format json` prints nothing **on stdout** until the end; step progress still streams on stderr.
4. A summary closes the run:

   ```
   QA Studio - Run Summary

   Passed: 2/3

   ✓ Login
   ✗ Checkout
   ○ Search (skipped)
   ```

   In JSON mode the same information is one document: `{total, passed, failed, skipped, results: [{usecaseId, usecaseName, status, executionId, duration, error}]}`.

Flags:

- `--fail-fast` — stop after the first failed test; the remaining tests are not started and appear as `skipped`. Default is to continue.
- All overrides (`--var`, `--base-url`, `--app-path`, `--region`, `--model-id`) apply to every test in the list, as they do for suites.
- `--execution-id` is only valid with exactly one ID (it is the cloud worker's attach path).

Exit codes: `0` all passed, `1` any test failed or skipped, `2` runner error before execution (bad ID, no AWS session, API unreachable), `3` stopped by `--timeout`.

Use this when verifying a fix that touches several tests, or to run an ad-hoc set without creating a suite.

---

## Running a suite

```bash
qa-studio run --suite-id <id>
```

Runs every test in the suite in order. Same artifact and override semantics as a single test — overrides apply to every test in the suite. If any test fails, the suite continues to the end (subsequent tests still run); the final exit code is non-zero if any test failed.

The same `--local-only`, `--keep-artifacts`, `--verbose`, `--timeout`, `--format` flags work for suite runs.

In suite runs every step progress line is prefixed with `[<test name>]` (e.g. `[09:00:05] [Login with valid credentials] Step 1: Open the login page`), because in cloud mode the suite's tests run in parallel and their lines interleave.

---

## Runtime overrides

The `qa-studio run` command supports a focused set of per-run overrides. Variables, base URL, and a few environment toggles. **Secrets and headers cannot be overridden per-run today** — see the limitations note below.

### Variables — `--var KEY=VALUE` (repeatable)

Override values from the test's `variables` array, or inject new ones not declared in the test. Repeatable.

```bash
qa-studio run --usecase-id abc123 \
  --var environment=staging \
  --var feature_flag=on \
  --var test_email=qa@example.com
```

A `--var` reference takes precedence over the test's `variables` array. Inside the test, `{{ environment }}` resolves to `"staging"` for this run.

### Repeat datasets — `--dataset-file [LABEL=]PATH` (repeatable)

A test with a [`repeat`](./step-types/repeat.md) step carries its own rows. Replace them for one run with a CSV whose header row names exactly the repeat's columns:

```csv
email,role
alice@staging.example,Administrator
bob@staging.example,Viewer
```

```bash
# LABEL is the repeat step's instruction text; omit it when the test has exactly one repeat
qa-studio run --usecase-id <test-id> --dataset-file "Login as each user=users-staging.csv"
qa-studio run --usecase-id <test-id> --dataset-file users-staging.csv
```

Works in remote and `--local-only` mode. Usage errors (exit 2, before any browser starts): used with `--suite-id` or `--execution-id`, file not found, empty CSV, header ≠ repeat columns, unknown label, more than 100 rows / 20 columns. Expanded steps show as `[row i/n]` in human output and carry `repeat_row_index` / `repeat_row_total` / `repeat_label` in JSON output.

A repeat step may also reference an **application dataset** (`dataset_id`) instead of carrying inline rows; the rows are then resolved from the application at execution time, and `--dataset-file` still replaces them by label for one run. Manage those datasets with `qa-studio apps datasets …`:

| Command | What it does |
|---|---|
| `qa-studio apps datasets list <app-id> [--output table\|json]` | List datasets (ID, name, column/row counts) |
| `qa-studio apps datasets get <app-id> <dataset-id> [--output table\|json\|csv]` | Show one dataset; `csv` output is a valid `--file` / `--dataset-file` input |
| `qa-studio apps datasets create <app-id> NAME --file rows.csv\|rows.json [--description TEXT]` | Create from a CSV (header row = columns, same parser as `--dataset-file`) or JSON `{"columns", "rows"}` file; validated client-side with the server's rules (exit 2) |
| `qa-studio apps datasets update <app-id> <dataset-id> [--name NAME] [--description TEXT] [--file PATH]` | Change only the given fields (the current dataset is read first) |
| `qa-studio apps datasets delete <app-id> <dataset-id> [--yes]` | Delete; a `409` lists the tests whose repeat steps still reference it |

| Command | Option | Type | Default | Description |
|---|---|---|---|---|
| `apps datasets list` | `--output` | `table` \| `json` | `table` | JSON: `{"datasets": [{"dataset_id", "name", "description", "column_count", "row_count", "updated_at"}]}` |
| `apps datasets get` | `--output` | `table` \| `json` \| `csv` | `table` | `json`: the full dataset incl. `columns` / `rows`; `csv`: header + rows |
| `apps datasets create <app-id> NAME` | `--file` | `.csv` \| `.json` path | required | Rows; `.json` is `{"columns": [...], "rows": [[...]]}` |
| | `--description` | text | `""` | Optional |
| | `--output` | `table` \| `json` | `table` | The created dataset (take `dataset_id` from here for the test JSON) |
| `apps datasets update <app-id> <dataset-id>` | `--name` / `--description` / `--file` | text / text / path | unchanged | Only the given fields change; `--description ''` clears it |
| | `--output` | `table` \| `json` | `table` | The updated dataset |
| `apps datasets delete <app-id> <dataset-id>` | `--yes`, `-y` | flag | `false` | Skip the confirmation prompt |

Scopes: `api/applications.read` for `list`/`get`, `api/applications.write` for `create`/`update`/`delete`. Running a test with a dataset reference in `--local-only` mode also needs `api/applications.read` (the CLI fetches the dataset); remote runs resolve it server-side. User tokens from `qa-studio login` carry both scopes (Viewer+ reads, Editor+ writes); OAuth-client tokens do **not** carry them today (the CLI requests a fixed scope list for client credentials), so under `OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` run such tests in remote mode. Errors: exit 2 `dataset <id> not found in application <app>` (dangling reference — fix the step or re-create the dataset) and `cannot read dataset …: 403 … --local-only with application datasets needs the api/applications.read scope`.

Precedence for repeat rows (lowest → highest): application dataset (`dataset_id`) → inline rows on the step (a step has one *or* the other) → `--dataset-file` for this run.

### Base URL — `--base-url`

Replaces the test's `usecase.starting_url` for this run. Lets the same test run against localhost, a staging URL, a production URL, etc.

```bash
qa-studio run --usecase-id abc123 --base-url http://localhost:3000
```

When the test contains `browser` steps with `navigate` actions using relative URLs, those URLs resolve against the override.

### Other environment overrides

- `--region <aws-region>` — AWS region for the run's regional AWS calls (local mode: browser provisioner and the S3 app-binary download; suite runs: the executions' region). Default: `AWS_REGION` / AWS profile. Nova Act stays in `us-east-1`, Device Farm in `us-west-2`.
- `--model-id <id>` — override the Nova Act model used for AI-driven steps.
- `--token-file <path>` — explicit path to a JSON token file (default uses the user's stored login).

### Limitations: secrets, headers, cookies

QA Studio does NOT currently support per-run secret, header, or cookie overrides on `qa-studio run`. The available mechanisms:

- **Secrets** are configured on the use case in the cloud (via the web UI or via the JSON's `secrets` array at import time). The interactive prompt during `qa-studio tests import` is where the agent or user provides values. If a secret needs to change, re-import or update via the web UI.
- **Headers** are configured per use case. There is no `--headers-file` option on `qa-studio run`.
- **Cookies** cannot be injected per-run. The closest available mechanism is `--local-browser=chrome-profile`, which uses the user's real Chrome profile and inherits whatever cookies are already in it (e.g., an existing logged-in session). Useful for development; not useful for CI.

If the user expects per-run secret or cookie injection, tell them this isn't supported today and ask whether they want to update the use case in the cloud or pursue another workaround.

### Application-level variables and secrets — `qa-studio apps …`

Values shared by every test of an application live on the application, not on each test. A test's own variable/secret of the same key overrides the application's; `--var` overrides both for one run. Rotating `admin_password` once with `apps secrets set` changes it for every test of the application.

| Command | What it does |
|---|---|
| `qa-studio apps variables list <app-id> [--output table\|json]` | List application variables |
| `qa-studio apps variables set <app-id> KEY=VALUE...` | Merge keys into the list and write the whole list back |
| `qa-studio apps variables unset <app-id> KEY...` | Remove keys (fails before writing when a key is not set) |
| `qa-studio apps secrets list <app-id> [--output table\|json]` | List secret keys — values are never returned |
| `qa-studio apps secrets set <app-id> KEY [--value-file PATH]` | Create/update one secret; hidden prompt unless `--value-file` (one trailing newline dropped) |
| `qa-studio apps secrets delete <app-id> KEY [--yes]` | Delete one secret |

| Command | Option | Type | Default | Description |
|---|---|---|---|---|
| `apps variables list` / `apps secrets list` | `--output` | `table` \| `json` | `table` | JSON: `{"variables": [{"key", "value"}]}` / `{"secrets": [{"key", "secret_name", "description", "created_at"}]}` |
| `apps variables set <app-id> KEY=VALUE...` | — | — | — | Key `^[A-Za-z_][A-Za-z0-9_]*$`; value may contain `=` |
| `apps variables unset <app-id> KEY...` | — | — | — | Every key must exist, otherwise nothing is written |
| `apps secrets set <app-id> KEY` | `--value-file` | path | hidden prompt | Read the value from a file (one trailing newline dropped). Key `^[A-Za-z0-9_.-]{1,128}$`; empty value → exit 2 |
| `apps secrets delete <app-id> KEY` | `--yes`, `-y` | flag | `false` | Skip the confirmation prompt (no recovery window) |

Scopes: `api/applications.read` for `list`, `api/applications.write` for `set`/`unset`/`delete`; a `403` prints which one is missing. Exit `2` for malformed `KEY=VALUE`, invalid keys or an empty secret value; exit `1` for API errors. Same token caveat as for datasets: user tokens carry the scopes, OAuth-client tokens do not.

Precedence (lowest → highest): application → test (use case) → `--var` for this run. Variables and secrets merge per key: `GET /usecase/{id}/variables` and `GET /usecase/{id}/secrets` return the effective list with `source: "application" | "usecase"` (the runner reads `key`/`value` only), and a secret step's `secret_key` resolves to the test's own secret first, then the application's. A test without an application resolves exactly as before.

---

## Browser provisioner choice

`--browser` selects how the runner gets a browser:

| Provisioner | Flag | When to use |
|---|---|---|
| Local Playwright | `--browser local` *(default)* | Most cases. Spins up a Playwright-controlled browser on the developer's machine. |
| AgentCore (managed cloud browser) | `--browser agentcore` | When the test must run from a managed cloud-side browser (e.g., for IP allow-listed targets, or to match production execution conditions). Requires the `[agentcore]` extra. |
| External CDP endpoint | `--browser cdp-external` | When the user has their own browser running with a CDP endpoint (e.g., a remote desktop, a docker container). Requires `--cdp-endpoint-url`. |

### Local browser flavours (`--browser local`)

Three flavours; pick based on what the test needs:

- `--local-browser chromium` *(default)* — NovaAct's bundled Chromium with a fresh profile. The cleanest, most predictable option. Use for any new test.
- `--local-browser chrome` — your system Chrome with a fresh profile. Use when the test depends on Chrome-specific behaviour not in Chromium.
- `--local-browser chrome-profile` — your system Chrome with your **real** user profile. Inherits cookies, sessions, extensions. Useful when the test needs to be already logged in. Side effect: any state changes the test makes (cookies set, settings changed) persist in your real profile.

### Headful vs headless

- Default is headless (browser runs invisibly).
- `--headful` makes the window visible. Useful when debugging interactively.
- The `HEADLESS` env var can also drive this — set it to `false` to default to headful even without the flag.

### CDP-external mode

```bash
qa-studio run --usecase-id <id> \
  --browser cdp-external \
  --cdp-endpoint-url ws://localhost:9222/devtools/browser/abc123 \
  --cdp-headers-file ./cdp-headers.json
```

`--cdp-headers-file` is a JSON file with HTTP headers used during the CDP handshake. Delivered via file rather than argv to avoid leaking secrets into the process listing. The file is read once at connect time.

---

## Mobile execution

Mobile tests run via AWS Device Farm, not a local browser. Two flags:

- `--device-arn <arn>` — pick the Device Farm device to run on. Overrides whatever's configured on the use case.
- `--app-path <path>` — path to a local `.apk` or `.ipa` file. The CLI uploads it to Device Farm before the run starts, so each invocation can test a different build of the app.

```bash
qa-studio run --usecase-id <mobile-test-id> \
  --device-arn arn:aws:devicefarm:us-west-2::device:GALAXY-S22 \
  --app-path ./builds/app-debug.apk
```

If neither flag is set, the runner uses whatever device/app is configured on the use case in the cloud.

---

## Electron execution

Electron tests (`usecase.test_platform == "electron"`) are detected from the use case; `--browser` is **not** involved and must stay at its default. The runner launches the desktop app itself, attaches Nova Act over CDP, runs the steps and kills the app. They cannot be started from the web UI — only `qa-studio run` can execute them, on a machine with a display (macOS host with a GUI session; `HEADLESS` has no effect).

| Flag | Meaning |
|---|---|
| `--app-path <path>` | **Required.** The `.app` bundle or executable to launch. |
| `--app-arg <value>` | Extra argv for the app, repeatable. Use it for the app directory when `--app-path` is the bare `electron` binary. Never put secrets here — values are logged. |
| `--app-user-data-dir <dir>` | Reuse a profile (e.g. an already signed-in session). Default: a fresh temp dir per run, deleted afterwards. |

```bash
# Packaged build, remote execution record
qa-studio run --usecase-id <desktop-test-id> --app-path "/Applications/My App.app"

# Unpackaged dev build, local only
qa-studio run --usecase-id <desktop-test-id> --local-only \
  --app-path node_modules/electron/dist/Electron.app --app-arg ./packages/app

# Whole suite — one --app-path applies to every electron test in it
qa-studio run --suite-id <suite-id> --app-path "/Applications/My App.app"
```

Pitfalls:
- "Electron usecases require --app-path" → the test is electron but no app was given.
- "Electron did not print 'DevTools listening on …'" → wrong binary, or the app crashed at start; the error includes the app's stderr tail. `QA_STUDIO_ELECTRON_START_TIMEOUT` (seconds, default 30) lengthens the wait for slow builds.
- "Bundle id mismatch: the usecase expects X but …/App.app is Y" → wrong `--app-path` for this usecase (or a stale `bundle_id` on it). The app was not launched.
- "Electron usecases can only be executed by the CI runner" from the API → someone tried to trigger it from the UI or a schedule; that is by design.
- No video in the artifacts is expected (Nova Act cannot record over CDP); screenshots and traces are present.

---

## Output and artifacts

### Where artifacts land

- **Local mode** (`--local-only` or any local run): `~/.qa-studio/artifacts/<usecase-id>/`
  - `recording.webm` — full screen recording of the run.
  - `screenshots/` — per-step screenshots.
  - `logs/` — runner and step logs.
- **Cloud mode** (default): same files, uploaded to S3 with the execution record. Local copies are removed after upload unless `--keep-artifacts` is set.

### Reading the output

By default the runner prints one line when the test starts and one line when each step starts — on **stderr**. There is no per-step completion line; the verdict is the summary (or the JSON document) printed on **stdout** at the end.

| Line | Format |
|---|---|
| Test start | `[HH:MM:SS] Executing Test "{name}"` — cloud runs append ` (execution {execution_id})` |
| Step start | `[HH:MM:SS] Step {n}: {instruction}` — validation steps append ` ({validation_value})`; repeat rows render as `Step {n} (row {i}/{total})` |
| Step start in a suite | `[HH:MM:SS] [{test name}] Step {n}: {instruction}` |

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

Warnings and errors (`[14:02:35] WARNING …`) are always shown. The `instruction` in a step line is the resolved one (variables expanded).

**What you will *not* see by default:** the API calls (`→ GET https://…`), the engine internals (`ExecutionEngine initialized`, `Trajectory recording enabled`, …) and Nova Act's think/act trace. Add `--verbose` to get all of them on the console. The runner's full DEBUG log is always written to the log artifact regardless of the flag — for local runs its path is the `artifacts.logs` field of the JSON result (`logs.txt` under the artifact directory); in cloud mode it is uploaded with the execution record. There is no `--debug` or `--log-level` flag.

When debugging a failure, check artifacts in this order:

1. **The recording** (`recording.webm`) — shows what the AI actually did. Was the click on the right element? Did the page render before the next step ran?
2. **The screenshots** — quicker than scrubbing the recording. Each step's "before" and "after" frame.
3. **The runner logs** — tells you what the AI was reasoning, what XPath/element the AI found, and exactly what response came back from Nova Act. Always full detail, even when the console was quiet.
4. **The cloud execution record** (if not `--local-only`) — has the same data plus richer context (variable values resolved at each step, captured response shapes for `network_assertion`).

### `--format json` output

For piping into another tool — remember the document is on stdout and the progress lines on stderr. Field names are camelCase:

```json
{
  "status": "success",
  "usecaseId": "uc-def456",
  "usecaseName": "Login with valid credentials",
  "executionId": "0190abc…",
  "duration": 24.3,
  "steps": [
    {
      "stepId": "step-1",
      "stepType": "navigation",
      "instruction": "Open the login page",
      "status": "success",
      "duration": 3.1,
      "error": null
    }
  ],
  "artifacts": { "video": "/…/recording.webm", "logs": "/…/logs.txt" }
}
```

- `status` is `success` or `failed`; `duration` is seconds (float), on the run and on each step.
- `executionId` is **cloud mode only** (`RemoteExecutionResult`); `artifacts` is **local mode only** (`LocalExecutionResult`). Cloud results currently return `steps: []` — read step detail from the execution record.
- Steps unrolled from a `repeat` step also carry `repeat_row_index`, `repeat_row_total`, `repeat_label`.
- With several `--usecase-id` values the document is the summary described above (`{total, passed, failed, skipped, results: [...]}`) instead.

The schema is stable; agents can parse `status` to programmatically determine pass/fail.

---

## Common execution pitfalls

- **Running without finding the ID first.** When the user says "run the login test", the agent should `qa-studio tests list`, find the matching ID, and confirm before running. Hardcoding an ID guess is a foot-gun.
- **Forgetting `--base-url` when running against a non-default environment.** If the test was authored against production but the user wants to run against staging, `--base-url https://staging.example.com` is required. Without it the test runs against whatever's in `usecase.starting_url`.
- **Trying to use `--secrets-file` or `--headers-file`.** These don't exist on `qa-studio run`. Configure secrets per use case at import time or via the web UI.
- **Running with `--browser agentcore` without the extra installed.** Fails with a missing-dependency error. Ensure `pip install qa-studio[agentcore]` first, or use `--browser local` as a fallback.
- **`--local-browser chrome-profile` for CI runs.** The chrome-profile flavour inherits the developer's real profile. Don't use it in shared environments — it leaks user state into the test.
- **`--local-only` when the user expects to see results in the cloud UI.** `--local-only` skips the cloud execution record entirely. The artifacts are on the developer's disk only.
- **Runs stopped by `--timeout` (exit 3).** There is no default limit; a pipeline that passes `--timeout` and hits it either needs a higher value (soak tests, slow builds) or has a hanging step — debug with `--headful --verbose`.
- **Suite runs that take longer than `--timeout`.** The timeout applies to the whole run, not per-test. For long suites, raise the timeout proportionally or split into smaller suites.
- **`--var KEY=VALUE` syntax mistakes.** Must be `KEY=VALUE` exactly, no spaces around the `=`. Repeat `--var` for each variable, don't try to space-separate them.
