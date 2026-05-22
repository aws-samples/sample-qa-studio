# Troubleshooting

Build-time and execute-time failures the agent will see when helping a user. Setup, authentication onboarding, and CI/CD pipeline issues are out of scope here — those are one-time human actions; this guide covers what goes wrong during normal test work.

## Table of contents

- [Test or suite not found](#test-or-suite-not-found)
- [Step failed during execution](#step-failed-during-execution)
- [Execution timeout](#execution-timeout)
- [Date parse failed](#date-parse-failed)
- [Import validation failed](#import-validation-failed)
- [Variable not found](#variable-not-found)
- [Secret not found](#secret-not-found)
- [Authentication errors](#authentication-errors)
- [Debugging Workflow](#debugging-workflow)
- [Reading the artifacts](#reading-the-artifacts)

---

## Test or suite not found

```
Error: Use case not found
Error: Suite not found
```

The ID was wrong, or the test/suite was deleted. The agent should:

```bash
qa-studio tests list      # find the right ID
qa-studio suites list
```

If the user named the test (e.g., "the login test"), `tests list` shows names alongside IDs — disambiguate by name, then confirm the ID with the user before running.

---

## Step failed during execution

```
✘ Step 3/6: navigation — "Click the Sign In button"
```

The most common runtime failure. Five common causes, in roughly the order to investigate:

1. **Page hadn't fully loaded.** Add a `validation` step earlier in the flow that gates on a known element being present, then re-run.
2. **Wrong base URL.** If the test was authored against production but is running against staging, an element name or layout may have shifted. Re-run with the correct `--base-url`.
3. **UI changed since the test was written.** Look at the screenshot for the failing step — does the page look like what the instruction expects? If not, update the test.
4. **Vague step instruction.** "Click the button" is ambiguous; "Click the 'Sign In' button at the top right" is not. Rewrite the instruction more specifically.
5. **Timing-sensitive interaction.** The step ran before the previous action's effect was visible. Insert a `validation` step (or a wait) that confirms the previous action took effect.

For each, the recovery loop is: investigate the artifact, fix the test, re-run.

---

## Execution timeout

```
Error: Execution timed out after 3600 seconds
```

Default global timeout is 1 hour. Two paths:

- **The test legitimately takes longer.** Bump the timeout: `qa-studio run --usecase-id <id> --timeout 7200`.
- **A step is hanging unexpectedly.** Re-run with `--headful --verbose` to watch what the AI is doing. A common cause is the AI looping looking for an element that isn't there — fix by tightening the step instruction or breaking the step into smaller pieces.

If the timeout fires during a suite run, raise the timeout for the whole run; the timeout is global, not per-test.

---

## Date parse failed

```
Date parse failed for retrieve_value: Date string '01/02/2024' is ambiguous;
provide a format argument or use ISO 8601.
```

The page is rendering a regional date format (US `01/02/2024` could be Jan 2 or Feb 1). The parser deliberately refuses to guess. Set `value_format` on the `retrieve_value` step (or the `format` arg on a `transform.parse_date`) to a Python `strptime` pattern matching what the page renders:

- US slash: `%m/%d/%Y`
- EU slash: `%d/%m/%Y`
- US long month (`January 2, 2024`): `%B %d, %Y`
- EU dot (`02.01.2024`): `%d.%m.%Y`

For ISO 8601 dates (`2024-01-02`) and Unix epoch values, leave `value_format` empty — the parser auto-detects those. See [step-types/retrieve_value.md](./step-types/retrieve_value.md) for full guidance.

---

## Import validation failed

```
ValidationError: 1 validation error for ExportPayload
steps.0.step_type
  Value error, must be one of: navigation, url, browser, secret, ...
```

The JSON file failed client-side validation in `qa-studio tests import`. Common causes:

- **Unknown step type.** Check spelling against the [step-types/](./step-types/) list. Note `url` is deprecated; use `browser` with `browser_action: "navigate"` for new tests.
- **Missing `instruction` or `step_type`.** Both required on every step.
- **Missing `sort` or non-positive `sort`.** Each step needs a positive integer.
- **`exportVersion` not `"1.0"`.** Validators reject other values.
- **Empty `steps` array.** A test must have at least one step.

Run `qa-studio tests import <path> --dry-run` to validate without uploading. The error message identifies the failing step by index (`steps.0`, `steps.3`, etc.).

---

## Variable not found

```
Error: Runtime variable 'order_id' not found
```

A step references `{{ order_id }}` but no upstream step set it. Causes:

- **Variable name typo.** The capturing step set `order_idd` (typo); the assertion references `order_id`. Match exactly.
- **Capturing step ran but produced no value.** Earlier steps failed silently; the variable was never written. Check the per-step status before the failing step.
- **Wrong execution order.** The `assertion_variable` references something captured later in the flow. `sort` order matters; `assertion` can only see variables captured by earlier steps.

---

## Secret not found

```
Error: Secret 'admin_password' not found
```

The `secret` step references `secret_key: admin_password` but no such secret exists for the use case. Causes:

- **Typo on `secret_key`.** Doublecheck spelling against the test's `secrets` array.
- **Secret never registered.** When importing the test, the agent or user must provide a value at the interactive prompt (or via `--skip-secrets` if configured separately). If `--skip-secrets` was used, configure the secret in the web UI.
- **Re-imported test with new secret name.** If the agent added a secret to a test but didn't re-import, the cloud doesn't know about it yet. Re-import with the secret value at the prompt.

Per-run secret overrides on `qa-studio run` are not supported today (no `--secrets-file` flag) — see [executing-tests.md](./executing-tests.md#runtime-overrides).

---

## Authentication errors

```
Error: Not authenticated
```

The user's CLI session has expired or was never set up. Tell the user to run `qa-studio login`. The agent should not try to drive the login flow — it's an interactive browser handshake the human owns.

---

## Debugging Workflow

When a test fails for a reason that isn't obvious from the error message:

1. **Re-run with verbose logging and kept artifacts.**

   ```bash
   qa-studio run --usecase-id <id> \
     --keep-artifacts \
     --verbose
   ```

2. **Watch the recording.** `~/.qa-studio/artifacts/<id>/recording.webm`. The fastest way to see what the AI actually did. Often the failure is visible directly: a wrong element clicked, a popup blocking the click, the wrong page loaded.

3. **Read the screenshots.** Per-step "before" frames in `~/.qa-studio/artifacts/<id>/screenshots/`. If the recording is long, screenshots are faster to scan.

4. **Read the runner logs.** `~/.qa-studio/artifacts/<id>/logs/`. Show what Nova Act was reasoning, what element it picked, exactly what came back. Useful when the failure is "the AI did the wrong thing" rather than "the page broke".

5. **Try `--headful`.** Watch the browser interactively. Useful for timing issues and pop-up dialogs.

6. **Run against localhost.** If the failure only happens against staging or production, run the same test with `--base-url http://localhost:3000` to confirm the test logic works locally. Differences point at environment-specific issues (different data, different feature flags, etc.).

---

## Reading the artifacts

Every run produces (in this priority order for debugging):

| Artifact | Location | Use for |
|---|---|---|
| `recording.webm` | `~/.qa-studio/artifacts/<id>/` | What did the AI actually do? Watch the failing step. |
| Per-step screenshots | `~/.qa-studio/artifacts/<id>/screenshots/` | Faster than recordings for visual inspection. |
| Runner logs | `~/.qa-studio/artifacts/<id>/logs/` | What did the AI think? What came back from Nova Act? |
| Cloud execution record | Web UI / `qa-studio` API | Full step-by-step state, variable values at each step, captured network bodies. |

In `--local-only` mode there's no cloud execution record — only the local artifacts. Use `--keep-artifacts` to preserve them after the run; without it, cloud-mode runs delete local copies after upload.
