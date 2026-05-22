# Validation Operators

`validation` and `assertion` steps both use the same operator vocabulary, parameterized by `validation_type`. This file is the per-type operator reference.

The two step types differ in *what* they compare, not *how*:

- **`validation`** — Nova extracts a value from the page and the runtime compares it against `validation_value` in one step.
- **`assertion`** — the runtime compares an already-captured variable (set by an earlier `retrieve_value` or `transform`) against `validation_value`. No browser interaction.

Everything below applies to both step types unless noted. For step-type details, see [`step-types/validation.md`](./step-types/validation.md) and [`step-types/assertion.md`](./step-types/assertion.md).

## Table of contents

- [Quick lookup: which operator for which type?](#quick-lookup-which-operator-for-which-type)
- [Boolean operators](#boolean-operators)
- [String operators](#string-operators)
- [Number operators](#number-operators)
- [Date operators](#date-operators)
- [How `validation_value` is interpreted](#how-validation_value-is-interpreted)
- [Common pitfalls](#common-pitfalls)

---

## Quick lookup: which operator for which type?

| `validation_type` | Operators |
|---|---|
| `bool` | (no `validation_operator` needed — always exact equality) |
| `string` | `exact`, `exact_case_insensitive`, `contains`, `contains_case_insensitive`, `not_equal` |
| `number` | `equals`, `less_then`, `greater_then`, `less_or_equal_then`, `greater_or_equal_then` |
| `date` | `before`, `after`, `equals`, `not_equals`, `equals_within` |

Note the spelling quirks: number operators use `_then` (not `_than`); the date `not_equals` operator includes the trailing `s` (string `not_equal` does not). The runtime is strict about these names.

---

## Boolean operators

Boolean is the only `validation_type` that does not take a `validation_operator` field — comparison is always exact equality.

| Operator | Behavior |
|---|---|
| *(none)* | Compare actual to `validation_value` cast as a boolean. `"true"`/`"True"` → `true`, anything else → `false`. |

`validation_value` accepts `"true"` or `"false"` as strings (the JSON serialization of the test stores them that way). It can also be a `{{ var }}` reference to a captured variable.

### Example: validation step (extract + compare)

```json
{
  "step_type": "validation",
  "instruction": "Is the 'Welcome' banner visible?",
  "validation_type": "bool",
  "validation_value": "true"
}
```

### Example: assertion step (compare a captured variable)

```json
{
  "step_type": "assertion",
  "assertion_variable": "is_logged_in",
  "validation_type": "bool",
  "validation_value": "true"
}
```

---

## String operators

| Operator | Behavior |
|---|---|
| `exact` | Case-sensitive equality. Both sides are trimmed of leading/trailing whitespace and surrounding `"` / `'` quotes before comparing. |
| `exact_case_insensitive` | Same as `exact`, but case-insensitive. |
| `contains` | Case-sensitive substring search. Passes when `validation_value` appears anywhere in the actual value. |
| `contains_case_insensitive` | Same as `contains`, but case-insensitive. |
| `not_equal` | Inverse of `exact`. Passes when the trimmed strings differ. |

`validation_value` is the literal expected string (or a `{{ var }}` reference). Use `contains*` when the page may surround the relevant text with formatting, IDs, or other variation. Use `exact*` only when the rendered value is fully under your control.

### Example: validation step with `contains`

```json
{
  "step_type": "validation",
  "instruction": "Get the success banner text",
  "validation_type": "string",
  "validation_operator": "contains",
  "validation_value": "Order placed"
}
```

### Example: assertion step with `exact`

```json
{
  "step_type": "assertion",
  "assertion_variable": "order_id",
  "validation_type": "string",
  "validation_operator": "exact",
  "validation_value": "ORD-12345"
}
```

### Example: assertion comparing two captured variables

```json
{
  "step_type": "assertion",
  "assertion_variable": "displayed_email",
  "validation_type": "string",
  "validation_operator": "exact_case_insensitive",
  "validation_value": "{{ submitted_email }}"
}
```

---

## Number operators

| Operator | Behavior |
|---|---|
| `equals` | `actual == expected` (numeric equality after `float()` cast). |
| `less_then` | `actual < expected`. |
| `greater_then` | `actual > expected`. |
| `less_or_equal_then` | `actual <= expected`. |
| `greater_or_equal_then` | `actual >= expected`. |

Both sides are cast to `float` before comparison. The cast fails the step (with a clear error) if the actual value isn't parseable as a number — e.g., the page renders `"$99.99"` and the operator can't strip the currency symbol. Strip non-numeric content via `transform.regex_extract` or `transform.replace` before asserting if needed.

### Example: validation step with `greater_then`

```json
{
  "step_type": "validation",
  "instruction": "Get the cart total as a number",
  "validation_type": "number",
  "validation_operator": "greater_then",
  "validation_value": "0"
}
```

### Example: assertion comparing a captured number to a literal

```json
{
  "step_type": "assertion",
  "assertion_variable": "cart_count",
  "validation_type": "number",
  "validation_operator": "equals",
  "validation_value": "3"
}
```

### Example: chaining transform → assertion

```json
{
  "step_type": "transform",
  "transform_operation": "math",
  "transform_args": "{\"expression\": \"{{ subtotal }} * 1.08\"}",
  "capture_variable": "expected_total"
}
```

```json
{
  "step_type": "assertion",
  "assertion_variable": "displayed_total",
  "validation_type": "number",
  "validation_operator": "equals",
  "validation_value": "{{ expected_total }}"
}
```

---

## Date operators

Date validation uses the centralized parser. Both `validation_value` and the actual value are parsed via `transform.date_parser.parse_to_utc` before comparison. Inputs may be:

- ISO 8601 / RFC 3339 (auto-detected: `2024-01-02`, `2024-01-02T15:04:05Z`, `2024-01-02T15:04:05+02:00`).
- Unix epoch seconds (10-digit) or milliseconds (13-digit).
- A regional date if it was already canonicalized upstream via `retrieve_value` with `value_type: date` and a `value_format`, or via `transform.parse_date`. The `validation_type: date` operators do NOT accept regional formats directly — they auto-detect ISO and epoch only. See [`step-types/retrieve_value.md`](./step-types/retrieve_value.md) for the canonicalization pattern.

| Operator | Behavior |
|---|---|
| `before` | `actual < expected`. Strict inequality (equal dates fail). |
| `after` | `actual > expected`. Strict inequality. |
| `equals` | `actual == expected` (millisecond precision). |
| `not_equals` | Inverse of `equals`. |
| `equals_within` | `abs(actual − expected) <= tolerance`. **Different `validation_value` shape — see below.** |

### Naive vs TZ-aware

A naive datetime (no offset in the string) is treated as a UTC anchor for comparison. When one side is naive and the other carries an offset, the step still succeeds or fails normally but the runner emits a warning in the step logs:

```
Comparing naive datetime (assumed UTC) with TZ-aware datetime. If this is unintended, ensure both values use the same TZ convention.
```

To eliminate the warning, ensure both sides came from the same source (both naive or both TZ-aware). The cleanest way is to canonicalize via `retrieve_value` with `value_type: date` upstream, then both the captured variable and any literal in `validation_value` agree on the convention.

### Example: assertion with `before`

```json
{
  "step_type": "assertion",
  "assertion_variable": "order_date",
  "validation_type": "date",
  "validation_operator": "before",
  "validation_value": "{{ cutoff_date }}"
}
```

### Example: validation step with `equals` against a literal

```json
{
  "step_type": "validation",
  "instruction": "Get the published-on date",
  "validation_type": "date",
  "validation_operator": "equals",
  "validation_value": "2024-01-02"
}
```

### Example: assertion comparing two captured dates

```json
{
  "step_type": "assertion",
  "assertion_variable": "latest_order_date",
  "validation_type": "date",
  "validation_operator": "after",
  "validation_value": "{{ previous_latest_order_date }}"
}
```

### `equals_within` — JSON-encoded validation_value

`equals_within` is the only operator where `validation_value` is **not** a plain string. It's a JSON-encoded payload with three fields:

| Field | Type | Required | Purpose |
|---|---|---|---|
| `date` | string | yes | The comparison date (literal or `{{ var }}`). |
| `tolerance` | int | yes | Non-negative integer. |
| `unit` | string | yes | One of `seconds`, `minutes`, `hours`, `days`, `weeks`. Months and years are not supported (their arithmetic is policy-dependent). |

The shape:

```json
{
  "date": "2024-01-02T15:00:00+00:00",
  "tolerance": 5,
  "unit": "minutes"
}
```

In the test JSON, `validation_value` holds this object as a JSON-encoded string (escaped quotes). The frontend builder writes this automatically; agents authoring JSON by hand must too.

### Example: `equals_within` with a tolerance of 5 minutes

```json
{
  "step_type": "assertion",
  "assertion_variable": "displayed_created_at",
  "validation_type": "date",
  "validation_operator": "equals_within",
  "validation_value": "{\"date\": \"{{ server_created_at }}\", \"tolerance\": 5, \"unit\": \"minutes\"}"
}
```

### Example: `equals_within` with a literal date and `seconds` unit

```json
{
  "step_type": "validation",
  "instruction": "Get the order timestamp",
  "validation_type": "date",
  "validation_operator": "equals_within",
  "validation_value": "{\"date\": \"2024-01-02T15:00:00Z\", \"tolerance\": 30, \"unit\": \"seconds\"}"
}
```

---

## How `validation_value` is interpreted

The same string field carries different shapes depending on the operator:

| Operator family | Shape of `validation_value` |
|---|---|
| All bool, string, number operators | Plain string (literal or `{{ var }}` reference). |
| Date `before`, `after`, `equals`, `not_equals` | Plain string (date literal in ISO 8601 / epoch, or a `{{ var }}` to a previously canonicalized date). |
| Date `equals_within` | JSON-encoded object: `{"date": str, "tolerance": int, "unit": str}`. |

Variable references resolve at runtime via the same `{{ name }}` template syntax as everywhere else in the test. Variables come from the test's `variables` array, prior `retrieve_value` / `transform` outputs, or runtime `--var KEY=VALUE` overrides.

---

## Common pitfalls

- **Number operator spelling**: it's `_then`, not `_than`. The runtime rejects `less_than` / `greater_than` with an "unknown operator" failure.
- **Date `not_equals` vs string `not_equal`**: dates use the trailing `s` (`not_equals`); strings don't (`not_equal`). Different vocabulary, easy to mix up.
- **Number value rendered with currency or units**: `"$99.99"` won't `float()`. Use a `transform` step to strip the prefix first (`regex_extract` or `replace`), then assert on the cleaned value.
- **Date `before` / `after` are strict**: equal dates fail. If equality should pass, use `equals_within` with a small tolerance, or split into two assertions (`before OR equals`).
- **`equals_within` payload as a plain string**: a common authoring mistake is writing `validation_value: "5 minutes"` for `equals_within`. The runtime will fail with a JSON parse error. The shape is the JSON object above.
- **Auto-detect rejects regional dates**: `validation_value: "01/02/2024"` will fail with "ambiguous; provide a format argument or use ISO 8601" because the date operators don't accept format hints. Canonicalize upstream via `retrieve_value` with `value_type: date` + `value_format`, or via `transform.parse_date`.
- **`validation_value` for boolean is `"true"` / `"false"`, not `true` / `false`**: every `validation_value` is a string, even for boolean. The runtime parses `"true"` as boolean true.
- **Mixing naive and TZ-aware dates**: the comparison still runs but the warning in the step log is easy to overlook. If you don't want the warning, make both sides naive or both TZ-aware (typically by canonicalizing via `retrieve_value` with `value_type: date`).
