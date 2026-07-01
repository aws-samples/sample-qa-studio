# retrieve_value

Captures a value from the page into a runtime variable. The value can then be referenced in any subsequent step's string fields with `{{ variable_name }}` — assertions, transforms, network bodies, navigation instructions, etc.

## When to use

- **Save a page value for a later assertion** ("capture the order ID, then assert it's not empty").
- **Pass a value across pages** ("capture the cart total on the cart page, verify the same value on the checkout page").
- **Build dynamic content** ("capture the user ID from the URL, use it in a network request body").
- **Capture a date in canonical UTC form** for downstream date math or comparisons (`value_type: "date"` + `value_format`).
- **Pull a value out of the URL** without going through the AI (`value_source: "url"` with an optional regex).

## When NOT to use

- **You only need a one-shot comparison.** Use [`validation`](./validation.md) — it extracts and compares in one step.
- **You're capturing a credential.** Don't. Credentials should never be captured into variables. Use [`secret`](./secret.md) on the input side.
- **You're capturing a downloaded file.** Use [`download`](./download.md) instead.

## Inputs

| Field | Type | Required | Purpose |
|---|---|---|---|
| `step_type` | string | yes | `"retrieve_value"`. |
| `instruction` | string | yes (when `value_source` is `screen`) | Natural-language description of what to read from the page. With `value_source: "url"`, this is a regex pattern instead. |
| `capture_variable` | string | yes | Name to store the value under. Reference later as `{{ capture_variable }}`. |
| `value_type` | string | no | One of `"string"` (default), `"number"`, `"bool"`, `"date"`. |
| `value_source` | string | no | `"screen"` (default — Nova reads the page) or `"url"` (programmatic regex over `page.url`, no AI involved). |
| `value_format` | string | no | strptime format, used only when `value_type: "date"`. Empty = auto-detect ISO 8601 / Unix epoch. |

## Output

The captured value is stored under `capture_variable` as a string in runtime variables.

For `value_type: "date"`, the AI-extracted string is parsed and **the canonical UTC ISO 8601 form** is what's stored. Downstream `validation_type: date` assertions and date transform ops can consume the variable directly without an intermediate `parse_date` step.

## Examples

Capture a string value:

```json
{
  "step_type": "retrieve_value",
  "instruction": "Get the order ID shown on the confirmation page",
  "capture_variable": "order_id"
}
```

Capture a number:

```json
{
  "step_type": "retrieve_value",
  "instruction": "Get the cart total as a number",
  "capture_variable": "cart_total",
  "value_type": "number"
}
```

Capture a date in EU format and canonicalize:

```json
{
  "step_type": "retrieve_value",
  "instruction": "Get the order date shown on the receipt",
  "capture_variable": "order_date",
  "value_type": "date",
  "value_format": "%d/%m/%Y"
}
```

Capture from the URL with a regex (no AI):

```json
{
  "step_type": "retrieve_value",
  "instruction": "/users/(\\d+)",
  "capture_variable": "user_id",
  "value_source": "url"
}
```

Capture the full URL:

```json
{
  "step_type": "retrieve_value",
  "instruction": "",
  "capture_variable": "current_url",
  "value_source": "url"
}
```

## Common pitfalls

- **Forgetting `capture_variable`.** Without it, the step is functionally a no-op — the value is extracted then discarded. Validators reject this case.
- **Variable name typos.** A test that captures `order_id` but later references `{{ orderid }}` will silently fail (the substitution is a literal `{{ orderid }}` string). Match exactly.
- **Date capture without `value_format` for ambiguous formats.** If the page renders `01/02/2024`, the date parser refuses to guess US vs EU. Set `value_format` to the matching strptime pattern (`"%m/%d/%Y"` for US, `"%d/%m/%Y"` for EU). Auto-detect (empty `value_format`) only handles ISO 8601 and Unix epoch.
- **Number type when the page has currency or units.** `value_type: number` uses Nova's number schema, which rejects strings like `"$99.99"`. Capture as `string` and use [`transform`](./transform.md) `to_number` (after stripping the symbol with `regex_extract` or `replace`).
- **URL extraction with no regex match.** With `value_source: "url"`, if the regex doesn't match anything in the URL, the step fails. Test the regex against the expected URL shape first.
- **Re-using the same `capture_variable` name.** Later captures overwrite earlier ones. If both values are needed, use distinct names.
