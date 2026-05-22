# secret

Enters a stored credential into a form field — every field on a login or authentication form (usernames, emails, passwords, MFA codes, OTP codes, security-question answers), as well as programmatic credentials (API keys, OAuth tokens, PATs, license keys). The actual secret value is never written into the test JSON, the execution logs, the recording video, or the execution history — only the secret's name is referenced.

## When to use

- **Every field on a login or authentication form** — usernames, emails, passwords, MFA codes, OTP codes, security-question answers, recovery codes. The whole form is sensitive, not just the password.
- **API keys, OAuth tokens, PATs, license keys** — any programmatic credential.
- Any value the test needs to enter where leaking the value would be a problem.

> **Rule: every login-form field is a secret.** A "dummy" test email like `qa-tester@example.com` still goes through a `secret` step. Test-account identifiers are still credentials — they leak into recordings, screenshots, logs, and version control if they're in a `navigation` instruction. The only way to keep them out is to route them through the secret resolver.

## When NOT to use

- **Non-credential form input** — search queries, message bodies, contact-form fields, comments, profile bios. Use [`navigation`](./navigation.md). Secrets carry resolution and redaction overhead; reserve them for credentials and login fields.
- **Values that change per environment** (URLs, feature flags, region names, non-credential IDs). Use a `variable` — variables are visible and overridable per run, which is exactly what you want for non-credentials.

## Inputs

| Field | Type | Required | Purpose |
|---|---|---|---|
| `step_type` | string | yes | `"secret"`. |
| `instruction` | string | yes | Natural-language description of **where to focus the cursor**. The instruction must NOT describe typing the value — it describes the field, not the action. The runtime types the secret value into whatever field has focus after the AI executes the instruction. |
| `secret_key` | string | yes | The name of the secret. Must already exist in the test's `secrets` array or be resolvable at runtime via `--secrets-file`. |

## Output

No capture variable. The secret value is typed into the field referenced by `instruction` after the AI focuses it.

## Examples

Focus the password field on a login form:

```json
{
  "step_type": "secret",
  "instruction": "Focus the password input field",
  "secret_key": "admin_password"
}
```

Focus a credentials input on a settings page (the click that submits the form is a separate `navigation` step):

```json
{
  "step_type": "secret",
  "instruction": "Click into the API key input",
  "secret_key": "third_party_api_key"
}
```

```json
{
  "step_type": "navigation",
  "instruction": "Click the 'Save' button"
}
```

Login flow — every field is a secret, the submit click is a `navigation` step:

```json
{
  "step_type": "secret",
  "instruction": "Focus the email input field",
  "secret_key": "admin_email"
}
```

```json
{
  "step_type": "secret",
  "instruction": "Focus the password input field",
  "secret_key": "admin_password"
}
```

```json
{
  "step_type": "navigation",
  "instruction": "Click the 'Sign In' button"
}
```

Both `admin_email` and `admin_password` are declared in the test's top-level `secrets` array. Neither value appears in the JSON, the recording, or the logs.

## Resolution at runtime

When the test runs, the `secret_key` is resolved through one of these mechanisms (in priority order):

1. **`--secrets-file <path>`** on the CLI — a JSON file `{"secret_key": "value"}` with mode `0600`.
2. **The use case's `secrets` array** — defined at authoring time, persisted with the test.
3. **The configured secret resolver** for the deployment (e.g., AWS Secrets Manager).

If the secret can't be resolved, the step fails before any value is typed. The error log identifies the missing secret by name only — the value is never echoed.

## Common pitfalls

- **Treating only the password as sensitive on a login form.** Every field on a login or authentication form is a credential — usernames, emails, MFA codes, OTP codes, security-question answers, recovery codes. All go through `secret` steps; none belong as literals in a `navigation` instruction. A login flow has at least two `secret` steps (one per field) plus a `navigation` step for the sign-in click.
- **Suggesting `--secrets-file` on `qa-studio run`.** That flag does NOT exist on the run command. Secrets are configured per use case at import time (the interactive prompt during `qa-studio tests import`) or in the web UI; there is no per-run secret override. If the user asks "how do I pass the secret value at run time?", tell them this isn't supported today and either the secret needs to be configured on the use case or they need to re-import. See [executing-tests.md](../executing-tests.md#runtime-overrides) for the full runtime-override surface.
- **Telling the AI to "type" or "enter" the value in the instruction.** The instruction must describe *where to focus the cursor*, not what to type. Phrasing like `"Enter the password into the password field"` is wrong — it conflates the AI's job (focus the field) with the runtime's job (type the secret). The right pattern is `"Focus the password input field"` or `"Click into the password field"`. This keeps the secret value out of the AI's reasoning loop entirely.
- **Combining secret entry with another action.** `"Click into the password field and click Sign In"` mixes two actions. Split: one `secret` step to focus the field (the runtime types the value), one `navigation` step for the click.
- **`secret_key` typo.** The test will fail with `Secret 'admin_passowrd' not found`. Doublecheck the spelling against the use case's `secrets` array or the secrets file the user is using.
- **Leaving secrets in `variables` instead.** Variables show up in logs and recordings. Anything that's actually sensitive must be a `secret`.
- **Authoring with the literal value as a fallback.** Don't write `"instruction": "Enter 'mypassword123' into the password field"` and call it a day — the literal goes into the test JSON in plain text. Always use `secret`.
- **Forgetting to register the secret.** If the agent adds a `secret` step referencing `admin_password`, it must also ensure `admin_password` exists in the test's secrets list (or instruct the user to provide it via the import-time prompt).
