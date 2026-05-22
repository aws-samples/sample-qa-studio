# assertion

Compares a previously captured runtime variable against an expected value. No browser interaction — pure runtime comparison. The AI is not involved; this step uses the same operator semantics as [`validation`](./validation.md), but the actual value comes from a variable instead of from page extraction.

## When to use

- **Verify a captured value** after a [`retrieve_value`](./retrieve_value.md) or [`transform`](./transform.md).
- **Compare two captured values** (variable to variable) — e.g., "the latest order date is after the previous one".
- **Compare a captured value to a literal** — e.g., "the order ID matches the one we expect".
- **Date-aware comparisons** between captured dates (`validation_type: date`).
- **Tolerance comparisons** for dates/numbers via `equals_within` (with a JSON-encoded tolerance payload).

## When NOT to use

- **Extracting and comparing in one step.** Use [`validation`](./validation.md) — it does the extract and compare together when you don't need to keep the value.
- **Verifying an HTTP call.** Use [`network_assertion`](./network_assertion.md).
- **Verifying file content.** Use [`download`](./download.md).

## Inputs

| Field | Type | Required | Purpose |
|---|---|---|---|
| `step_type` | string | yes | `"assertion"`. |
| `assertion_variable` | string | yes | Name of the captured variable to compare. Must have been set by a prior `retrieve_value` or `transform` step (or by a runtime `--var` override). |
| `validation_type` | string | yes | One of `"bool"`, `"string"`, `"number"`, `"date"`. |
| `validation_operator` | string | yes for non-bool | Operator from the chosen type's set. See [Validation Operators](../validation-operators.md). |
| `validation_value` | string | yes | Expected value. Can be a literal, a `{{ other_variable }}` reference, or a JSON payload for `date`/`equals_within`. |

## Output

No capture variable. The step succeeds if the comparison passes, fails otherwise. The actual and expected values are written into the step logs.

## Examples

Compare a captured value to a literal:

```json
{
  "step_type": "assertion",
  "assertion_variable": "order_id",
  "validation_type": "string",
  "validation_operator": "exact",
  "validation_value": "ORD-12345"
}
```

Compare two captured variables:

```json
{
  "step_type": "assertion",
  "assertion_variable": "latest_order_date",
  "validation_type": "date",
  "validation_operator": "after",
  "validation_value": "{{ previous_latest_order_date }}"
}
```

Number greater-than:

```json
{
  "step_type": "assertion",
  "assertion_variable": "cart_count",
  "validation_type": "number",
  "validation_operator": "greater_then",
  "validation_value": "0"
}
```

Date equals_within (tolerance comparison):

```json
{
  "step_type": "assertion",
  "assertion_variable": "displayed_created_at",
  "validation_type": "date",
  "validation_operator": "equals_within",
  "validation_value": "{\"date\": \"{{ server_created_at }}\", \"tolerance\": 5, \"unit\": \"minutes\"}"
}
```

The `validation_value` for `equals_within` is a JSON-encoded payload with three fields: `date` (the comparison value), `tolerance` (non-negative integer), `unit` (one of `seconds`, `minutes`, `hours`, `days`, `weeks`).

## Common pitfalls

- **Variable name typo in `assertion_variable`.** The step fails with `Runtime variable 'order_id' not found`. Re-check spelling against the upstream `retrieve_value` / `transform` step's `capture_variable`.
- **Asserting on a variable that wasn't captured.** Same error. Make sure a prior step actually set the variable, or that the user is passing it via `--var`.
- **Using `assertion` for one-shot page checks.** If no later step needs the value, [`validation`](./validation.md) is cleaner — one step instead of two.
- **Mixing naive and TZ-aware dates.** A `date` comparison with one side naive (no offset) and the other TZ-aware logs a warning but still runs. The agent should set `value_format` consistently on the upstream `retrieve_value` so both sides come from the same parser convention.
- **Forgetting that `equals_within`'s `validation_value` is JSON.** It's not a plain date string. The frontend builder writes the JSON automatically; agents authoring JSON by hand must too.
