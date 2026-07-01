# url *(deprecated)*

> ⚠️ **Deprecated.** Soft-deprecated in favour of [`browser`](./browser.md) with `browser_action: "navigate"`. Existing `url` steps still execute correctly, but the agent should not author new ones.

## When to use

Only when reading or editing an existing test that already contains `url` steps. Workers and the CLI runner continue to support them for backward compatibility.

## When NOT to use

- **New tests.** Always use `browser` with `navigate` for any new test the agent authors.
- **Migrating an existing test.** When an old `url` step needs editing, also consider replacing it with the equivalent `browser` step.

## Inputs

| Field | Type | Required | Purpose |
|---|---|---|---|
| `step_type` | string | yes | `"url"`. |
| `instruction` | string | yes | The target URL or a directive like `"Go to /dashboard"`. |

## Migration

Equivalent in the modern shape:

```json
{
  "step_type": "browser",
  "browser_action": "navigate",
  "browser_args": "{\"url\": \"https://example.com/dashboard\"}"
}
```

See [`browser`](./browser.md) for the full options on the navigate action (relative paths, hard reload behaviour, etc.).

## Common pitfalls

- **Authoring new `url` steps.** Don't. Use `browser` + `navigate`.
- **Assuming the deprecation will be lifted.** It won't. The `url` type is read-only territory at this point.
