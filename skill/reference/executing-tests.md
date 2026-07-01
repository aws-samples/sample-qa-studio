# Executing Tests

How to run a QA Studio test from the CLI — finding the test, running it, overriding values at runtime, choosing a browser provisioner, and reading the output.

## Table of contents

- [Finding tests and suites](#finding-tests-and-suites)
- [Running a single test](#running-a-single-test)
- [Running a suite](#running-a-suite)
- [Runtime overrides](#runtime-overrides)
- [Browser provisioner choice](#browser-provisioner-choice)
- [Mobile execution](#mobile-execution)
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
- `--verbose` — verbose runner logging, useful when debugging a step that's failing for unclear reasons.
- `--timeout <seconds>` — global timeout for the whole run. Default is 3600 (1 hour). The runner aborts if the run exceeds this.
- `--format json` — machine-readable run output (status, IDs, durations) instead of human prose. Useful when piping to another tool.

---

## Running a suite

```bash
qa-studio run --suite-id <id>
```

Runs every test in the suite in order. Same artifact and override semantics as a single test — overrides apply to every test in the suite. If any test fails, the suite continues to the end (subsequent tests still run); the final exit code is non-zero if any test failed.

The same `--local-only`, `--keep-artifacts`, `--verbose`, `--timeout`, `--format` flags work for suite runs.

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

### Base URL — `--base-url`

Replaces the test's `usecase.starting_url` for this run. Lets the same test run against localhost, a staging URL, a production URL, etc.

```bash
qa-studio run --usecase-id abc123 --base-url http://localhost:3000
```

When the test contains `browser` steps with `navigate` actions using relative URLs, those URLs resolve against the override.

### Other environment overrides

- `--region <aws-region>` — override the AWS region for the browser session (useful when running cross-region).
- `--model-id <id>` — override the Nova Act model used for AI-driven steps.
- `--token-file <path>` — explicit path to a JSON token file (default uses the user's stored login).

### Limitations: secrets, headers, cookies

QA Studio does NOT currently support per-run secret, header, or cookie overrides on `qa-studio run`. The available mechanisms:

- **Secrets** are configured on the use case in the cloud (via the web UI or via the JSON's `secrets` array at import time). The interactive prompt during `qa-studio tests import` is where the agent or user provides values. If a secret needs to change, re-import or update via the web UI.
- **Headers** are configured per use case. There is no `--headers-file` option on `qa-studio run`.
- **Cookies** cannot be injected per-run. The closest available mechanism is `--local-browser=chrome-profile`, which uses the user's real Chrome profile and inherits whatever cookies are already in it (e.g., an existing logged-in session). Useful for development; not useful for CI.

If the user expects per-run secret or cookie injection, tell them this isn't supported today and ask whether they want to update the use case in the cloud or pursue another workaround.

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

## Output and artifacts

### Where artifacts land

- **Local mode** (`--local-only` or any local run): `~/.qa-studio/artifacts/<usecase-id>/`
  - `recording.webm` — full screen recording of the run.
  - `screenshots/` — per-step screenshots.
  - `logs/` — runner and step logs.
- **Cloud mode** (default): same files, uploaded to S3 with the execution record. Local copies are removed after upload unless `--keep-artifacts` is set.

### Reading the output

The runner prints a per-step status line as it goes:

```
✓ Step 1/4: navigation — "Click the Sign In button"
✓ Step 2/4: secret — "Focus the password input field"
✓ Step 3/4: navigation — "Click the 'Sign In' button"
✘ Step 4/4: validation — "Get the heading text after sign-in"
   Expected: "Dashboard"
   Got:      "Welcome back!"
```

When debugging a failure, check artifacts in this order:

1. **The recording** (`recording.webm`) — shows what the AI actually did. Was the click on the right element? Did the page render before the next step ran?
2. **The screenshots** — quicker than scrubbing the recording. Each step's "before" and "after" frame.
3. **The runner logs** — tells you what the AI was reasoning, what XPath/element the AI found, and exactly what response came back from Nova Act.
4. **The cloud execution record** (if not `--local-only`) — has the same data plus richer context (variable values resolved at each step, captured response shapes for `network_assertion`).

### `--format json` output

For piping into another tool:

```json
{
  "execution_id": "exec-abc123",
  "usecase_id": "uc-def456",
  "status": "success",
  "duration_ms": 12456,
  "steps": [...]
}
```

The schema is stable; agents can parse this output to programmatically determine pass/fail.

---

## Common execution pitfalls

- **Running without finding the ID first.** When the user says "run the login test", the agent should `qa-studio tests list`, find the matching ID, and confirm before running. Hardcoding an ID guess is a foot-gun.
- **Forgetting `--base-url` when running against a non-default environment.** If the test was authored against production but the user wants to run against staging, `--base-url https://staging.example.com` is required. Without it the test runs against whatever's in `usecase.starting_url`.
- **Trying to use `--secrets-file` or `--headers-file`.** These don't exist on `qa-studio run`. Configure secrets per use case at import time or via the web UI.
- **Running with `--browser agentcore` without the extra installed.** Fails with a missing-dependency error. Ensure `pip install qa-studio[agentcore]` first, or use `--browser local` as a fallback.
- **`--local-browser chrome-profile` for CI runs.** The chrome-profile flavour inherits the developer's real profile. Don't use it in shared environments — it leaks user state into the test.
- **`--local-only` when the user expects to see results in the cloud UI.** `--local-only` skips the cloud execution record entirely. The artifacts are on the developer's disk only.
- **Long-running tests timing out at the default 3600s.** If a test legitimately takes longer (e.g., a soak test, or one that waits for a slow build), set `--timeout` higher. If it's hitting that timeout unexpectedly, that's usually a step that's hanging — debug with `--headful --verbose`.
- **Suite runs that take longer than `--timeout`.** The timeout applies to the whole run, not per-test. For long suites, raise the timeout proportionally or split into smaller suites.
- **`--var KEY=VALUE` syntax mistakes.** Must be `KEY=VALUE` exactly, no spaces around the `=`. Repeat `--var` for each variable, don't try to space-separate them.
