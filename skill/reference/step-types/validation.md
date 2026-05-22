# validation

Compares an AI-extracted page value against an expected value, in one step. Nova Act extracts the value (using the `instruction` and a type-specific schema), and the runtime applies the configured operator. If the comparison fails, the step fails.

## When to use

- **Verify the page contains an expected value** without storing it for later (e.g., "the dashboard heading is 'Welcome'").
- **Quick assertions inline** during a flow (after a click, after a form submit, etc.).
- **Type-aware comparisons** — boolean checks ("is the cart empty?"), number checks ("is the cart count > 0?"), date checks ("is the order date in the future?"), and string checks (exact, contains, case-insensitive).

## When NOT to use

- **You need the value for a later step.** Use [`retrieve_value`](./retrieve_value.md) to capture it, then [`assertion`](./assertion.md) to compare. `validation` discards the value after comparing.
- **You're comparing two captured variables.** Use [`assertion`](./assertion.md). `validation` extracts from the page, not from variables.
- **You're verifying an HTTP call.** Use [`network_assertion`](./network_assertion.md).
- **You want to verify a file was downloaded.** Use [`download`](./download.md).

## Inputs

| Field | Type | Required | Purpose |
|---|---|---|---|
| `step_type` | string | yes | `"validation"`. |
| `instruction` | string | yes | Natural-language description of what to extract from the page (e.g. `"Get the dashboard heading text"`). |
| `validation_type` | string | yes | One of `"bool"`, `"string"`, `"number"`, `"date"`. Determines the schema Nova uses to extract and the operator set available. |
| `validation_operator` | string | yes for non-bool | Operator from the chosen type's set. See [Validation Operators](../validation-operators.md). For `bool`, leave empty (always exact match). |
| `validation_value` | string | yes | Expected value. Can be a literal, a `{{ variable }}` reference, or — for `equals_within` on dates — a JSON-encoded payload. |

## Output

No capture variable. Step succeeds if the comparison passes, fails otherwise.

## Examples

Boolean check ("is this true?"):

```json
{
  "step_type": "validation",
  "instruction": "Is the 'Welcome' banner visible?",
  "validation_type": "bool",
  "validation_value": "true"
}
```

String contains check:

```json
{
  "step_type": "validation",
  "instruction": "Get the success message text",
  "validation_type": "string",
  "validation_operator": "contains",
  "validation_value": "Order placed"
}
```

Number greater-than check:

```json
{
  "step_type": "validation",
  "instruction": "Get the total in the cart",
  "validation_type": "number",
  "validation_operator": "greater_then",
  "validation_value": "0"
}
```

Date check (auto-detect ISO from the page):

```json
{
  "step_type": "validation",
  "instruction": "Get the publish date",
  "validation_type": "date",
  "validation_operator": "equals",
  "validation_value": "2024-01-02"
}
```

Date check with a captured baseline:

```json
{
  "step_type": "validation",
  "instruction": "Get the latest order date",
  "validation_type": "date",
  "validation_operator": "after",
  "validation_value": "{{ previous_order_date }}"
}
```

## Common pitfalls

- **Vague extraction instructions.** "Verify the page is correct" — the AI doesn't know what to look at. Describe the specific element ("the H1 heading", "the price next to 'Total'").
- **Type mismatch.** Setting `validation_type: "number"` when the page renders `"$99.99"` won't extract `99.99` — the AI's number schema rejects strings with currency symbols. Use `string` + `contains`, or use [`retrieve_value`](./retrieve_value.md) (string) + [`transform`](./transform.md) (`to_number`) + [`assertion`](./assertion.md).
- **Date validation without an explicit format.** If the page renders `01/02/2024` (ambiguous), validation will fail with a clear error. Either ensure the page is rendering in ISO 8601, or capture via `retrieve_value` with `value_type: date` and `value_format`, then assert.
- **Combining extract+compare for values you'll need later.** Run a `retrieve_value` instead so the value is reusable; you can still assert the same thing in a follow-up `assertion` step.
