# navigation

The most common step type. Drives any user-facing UI action: clicks, form input, dropdown selection, hover, scroll, etc. The natural-language `instruction` is interpreted by Nova Act, which decides what element to interact with on the rendered page.

## When to use

- Clicking buttons, links, or any interactive element.
- Typing into form fields.
- Selecting from dropdowns or radio buttons.
- Toggling checkboxes.
- Scrolling, hovering, drag-and-drop — any general UI gesture.

## When NOT to use

- **Navigating to a URL.** Use [`browser`](./browser.md) with `browser_action: "navigate"` instead. (The deprecated [`url`](./url.md) step still works but should not be used for new tests.)
- **Entering any value into a login or authentication form.** Use [`secret`](./secret.md) for every field — usernames, emails, passwords, MFA codes, OTP codes, security-question answers. Even an "obviously dummy" test email belongs in a `secret` step; routing it through the secret resolver is the only way to keep test-account identifiers out of recordings and logs.
- **Verifying page content.** Use [`validation`](./validation.md) for the comparison; a `navigation` step's only job is the action, not the check.
- **Capturing a value for later use.** Use [`retrieve_value`](./retrieve_value.md).

## Inputs

| Field | Type | Required | Purpose |
|---|---|---|---|
| `step_type` | string | yes | Must be `"navigation"`. |
| `instruction` | string | yes | Natural-language description of the action (e.g. `"Click the Sign In button"`). |

## Output

No capture variable. Side effect is whatever the AI agent does to the page (click, type, etc.).

## Examples

Click a button:

```json
{
  "step_type": "navigation",
  "instruction": "Click the Sign In button"
}
```

Fill a form field:

```json
{
  "step_type": "navigation",
  "instruction": "Enter 'Jane Doe' into the name field"
}
```

Select from a dropdown:

```json
{
  "step_type": "navigation",
  "instruction": "Select 'United States' from the country dropdown"
}
```

Reference a variable in the instruction:

```json
{
  "step_type": "navigation",
  "instruction": "Enter '{{ search_query }}' into the search field"
}
```

## Common pitfalls

- **Vague instructions.** "Click the button" — which button? Be specific: name the visible label, the section, or the role. The AI does best with descriptions a human reader could follow.
- **Mixing actions.** Don't combine "click X and verify Y appears" in one step — the verification belongs in a separate `validation` step. Mixing them makes failures harder to diagnose.
- **Hard-coded values that should be variables.** If the test runs against multiple environments or uses generated data, parameterize via `{{ variable }}` references. Hard-coded values lock the test to one environment.
- **Brittle phrasing.** Describe what the user sees ("Click 'Add to cart'"), not what the DOM looks like ("Click button.btn-primary"). DOM-level descriptions break with cosmetic UI changes.
