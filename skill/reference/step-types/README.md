# Step Types

QA Studio has 9 active step types plus one deprecated. Each file in this directory documents a single step type with the same template:

- **When to use** — the scenarios this step is for.
- **When NOT to use** — wrong fits and what to use instead.
- **Inputs** — fields, types, defaults, requiredness.
- **Output** — what gets stored, what side effects occur.
- **Examples** — full inline JSON.
- **Common pitfalls** — mistakes the agent should avoid.

Load only the file(s) you need; each is self-contained.

---

## Decision tree: which step type for which goal?

| The user wants to… | Use |
|---|---|
| Click a button, fill a form field, select a dropdown | [`navigation`](./navigation.md) |
| Navigate to a URL | [`browser`](./browser.md) (action: `navigate`) |
| Reload the page (with or without cache bypass) | [`browser`](./browser.md) (action: `reload`) |
| Go back / forward in browser history | [`browser`](./browser.md) (action: `back` / `forward`) |
| Enter any field on a login or authentication form (username, email, password, MFA code, OTP, security answer) | [`secret`](./secret.md) |
| Enter a programmatic credential (API key, OAuth token, PAT) | [`secret`](./secret.md) |
| Check that a value on the page matches expected (AI extracts) | [`validation`](./validation.md) |
| Capture a page value into a variable for later use | [`retrieve_value`](./retrieve_value.md) |
| Compare a previously captured variable to an expected value | [`assertion`](./assertion.md) |
| Download a file from the page | [`download`](./download.md) |
| Compute or format a value (math, strings, dates) between steps | [`transform`](./transform.md) |
| Verify or mock an HTTP call triggered by a UI action | [`network_assertion`](./network_assertion.md) |

The deprecated [`url`](./url.md) step type is kept for reading existing tests; new tests should use `browser` with `navigate`.

---

## Authoring rule of thumb

The agent's job is usually to glue together a small set of these. A typical end-to-end shape:

```
[browser:navigate]   → get to the right page
[navigation]…       → drive UI actions
[secret]            → for any sensitive entry
[retrieve_value]    → capture data the test will reason about later
[transform]…        → optional data shaping
[validation]…       → AI-extracted assertions on the page
[assertion]…        → comparisons of previously captured variables
```

`network_assertion` and `download` are special-purpose; reach for them only when the test goal is specifically about an HTTP call or file download.

When a test is failing in a way that's not about UI, look at `network_assertion` — most often the bug is "the click triggered the wrong API call" rather than "the UI didn't render."
