# browser

Browser-level controls that don't interact with page elements: navigation, history movement, and reloading. Replaces the deprecated [`url`](./url.md) step type as the way to navigate to a URL.

## When to use

- **Navigate to a URL** at the start of a test or to switch pages mid-flow.
- **Reload the page** after a state change (e.g., after a config update should take effect).
- **Hard reload** to bypass the browser cache when verifying a fresh load.
- **Go back / forward** in browser history to test multi-page flows or breadcrumb navigation.

## When NOT to use

- **Clicking links rendered on the page.** Use [`navigation`](./navigation.md) — it's a UI action, not a browser-level one.
- **Closing tabs, opening new windows.** Not supported.
- **Setting cookies or local storage.** Not supported as a step. Use the `--local-browser=chrome-profile` runtime option if the test needs the user's existing browser session.

## Inputs

| Field | Type | Required | Purpose |
|---|---|---|---|
| `step_type` | string | yes | `"browser"`. |
| `browser_action` | string | yes | One of `"navigate"`, `"reload"`, `"back"`, `"forward"`. |
| `browser_args` | string (JSON) | yes | JSON object with action-specific args. May be `"{}"` when no args are needed. |

### `browser_args` per action

| Action | Args | Notes |
|---|---|---|
| `navigate` | `{"url": "<target>"}` | URL is required. Can be absolute or relative; relative URLs resolve against the test's `starting_url`. |
| `reload` | `{}` or `{"hard": true}` | `hard: true` bypasses the cache. Default soft reload re-renders from cache. |
| `back` | `{}` | Fails if there's no history to go back to. |
| `forward` | `{}` | Fails if there's no history to go forward to. |

## Output

No capture variable. The browser ends up at a different URL or with a refreshed page state.

## Examples

Navigate to a URL (the modern replacement for the `url` step):

```json
{
  "step_type": "browser",
  "browser_action": "navigate",
  "browser_args": "{\"url\": \"https://example.com/dashboard\"}"
}
```

Soft reload:

```json
{
  "step_type": "browser",
  "browser_action": "reload",
  "browser_args": "{}"
}
```

Hard reload (bypass cache):

```json
{
  "step_type": "browser",
  "browser_action": "reload",
  "browser_args": "{\"hard\": true}"
}
```

Browser history:

```json
{
  "step_type": "browser",
  "browser_action": "back",
  "browser_args": "{}"
}
```

```json
{
  "step_type": "browser",
  "browser_action": "forward",
  "browser_args": "{}"
}
```

## Common pitfalls

- **Authoring `url` steps for new tests.** Use `browser` with `navigate`. The `url` step type is deprecated.
- **Forgetting `browser_args` is a JSON-encoded string.** It must be a string, not a nested object. Validators will reject malformed shapes.
- **Soft reload vs hard reload confusion.** If the test cares about a fresh fetch (e.g., asserting a config-changed banner appears), use `hard: true`. Otherwise the browser may serve a cached page.
- **Using `back` / `forward` without a history.** A fresh page load has no history; `back` will fail. Sequence the test so navigation has happened first.
