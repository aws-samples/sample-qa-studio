# transform

Compute or reshape a value between steps. Always reads from existing variables (or literals) and writes the result to `capture_variable`. No browser interaction. The transform step is what stitches captured values together: math, string manipulation, format coercion, regex extraction, date arithmetic.

## When to use

- **Compute a derived value** from one or more captured variables (e.g., total = subtotal + tax).
- **Reshape a string** before using it elsewhere (uppercase, trim, replace, regex-extract).
- **Coerce types** (string→number, string→int).
- **Work with dates** — parse a regional format into canonical UTC, format a date for display, add/subtract durations, compute differences.
- **Build a formatted string** from variables (the `format` op).

## When NOT to use

- **The data needs to come from the page.** Use [`retrieve_value`](./retrieve_value.md) — `transform` only reshapes existing variables.
- **You need to verify the result.** `transform` produces a variable; a follow-up [`assertion`](./assertion.md) or [`validation`](./validation.md) does the verification.
- **The "computation" is just retrieval.** If you're tempted to use `transform` to "get a value", you actually want `retrieve_value`.

## Inputs

| Field | Type | Required | Purpose |
|---|---|---|---|
| `step_type` | string | yes | `"transform"`. |
| `transform_operation` | string | yes | Operation name (see table below). |
| `transform_args` | string (JSON) | yes | Operation-specific args, JSON-encoded. |
| `capture_variable` | string | yes | Where to store the result. |

## Operations

24 operations across 5 categories.

### Numeric

| Operation | Args | Returns | Notes |
|---|---|---|---|
| `math` | `{"expression": "..."}` | number | Safe AST evaluator. Allows `+ - * / % **`, parens, numeric literals, `{{ var }}` references. No function calls, no attribute access. |
| `round` | `{"value": "...", "digits": 2}` | number | `digits` defaults to 0. |
| `floor` | `{"value": "..."}` | int | |
| `ceil` | `{"value": "..."}` | int | |
| `abs` | `{"value": "..."}` | number | |
| `min` | `{"values": ["...", "..."]}` | number | List of numbers. |
| `max` | `{"values": ["...", "..."]}` | number | |

### String

| Operation | Args | Returns |
|---|---|---|
| `concat` | `{"values": ["a", "b", "c"]}` | string |
| `upper` | `{"value": "..."}` | string |
| `lower` | `{"value": "..."}` | string |
| `trim` | `{"value": "..."}` | string |
| `replace` | `{"value": "...", "old": "...", "new": "..."}` | string |
| `substring` | `{"value": "...", "start": 0, "end": 5}` | string. `end` is optional. |
| `length` | `{"value": "..."}` | int |

### Coercion

| Operation | Args | Returns |
|---|---|---|
| `to_number` | `{"value": "..."}` | float |
| `to_string` | `{"value": "..."}` | string |
| `to_int` | `{"value": "..."}` | int (truncates) |

### Pattern

| Operation | Args | Returns |
|---|---|---|
| `regex_extract` | `{"value": "...", "pattern": "...", "group": 0}` | string. `group` defaults to 0 (full match). |
| `format` | `{"template": "Order #{}", "args": ["..."]}` | string. Python `str.format` with positional `{}` placeholders. |

### Date

All five date ops produce canonical UTC ISO 8601 strings (or, for `to_epoch`, integer epoch). Date inputs auto-detect ISO 8601 and Unix epoch; for regional formats, pass an explicit `format`. The parser deliberately rejects ambiguous input like `01/02/2024` — author tests with explicit formats when the page uses regional dates.

| Operation | Args | Returns | Notes |
|---|---|---|---|
| `parse_date` | `{"value": "...", "format": "..."}` | UTC ISO 8601 string | `format` is optional (auto-detect). |
| `format_date` | `{"iso_value": "...", "format": "..."}` | string | Renders a canonical date in the target strftime format. Input must be canonical (no `format` arg here). |
| `add_duration` | `{"iso_value": "...", "amount": ±N, "unit": "..."}` | UTC ISO 8601 string | Units: `seconds`, `minutes`, `hours`, `days`, `weeks`. **Months and years are not supported** — their arithmetic is policy-dependent (Jan 31 + 1 month = ?). |
| `date_diff` | `{"a": "...", "b": "...", "unit": "..."}` | int | Returns `a − b` in the requested unit, truncated toward zero. Same unit set as `add_duration`. |
| `to_epoch` | `{"value": "...", "unit": "seconds"}` | int | `unit`: `seconds` (default) or `millis`. Useful for converting dates so they can be compared via the existing number assertion operators. |

## Output

The result is stored in `capture_variable` as a string (numbers are stringified). Reference it later with `{{ capture_variable }}`.

## Examples

Math expression with variables:

```json
{
  "step_type": "transform",
  "transform_operation": "math",
  "transform_args": "{\"expression\": \"{{ subtotal }} * 1.08\"}",
  "capture_variable": "total_with_tax"
}
```

Uppercase a captured value:

```json
{
  "step_type": "transform",
  "transform_operation": "upper",
  "transform_args": "{\"value\": \"{{ username }}\"}",
  "capture_variable": "username_upper"
}
```

Extract digits from a string:

```json
{
  "step_type": "transform",
  "transform_operation": "regex_extract",
  "transform_args": "{\"value\": \"Order #12345\", \"pattern\": \"\\\\d+\"}",
  "capture_variable": "order_number"
}
```

Parse a regional date into canonical UTC:

```json
{
  "step_type": "transform",
  "transform_operation": "parse_date",
  "transform_args": "{\"value\": \"02/01/2024\", \"format\": \"%d/%m/%Y\"}",
  "capture_variable": "order_date_iso"
}
```

Add 30 days to a captured date:

```json
{
  "step_type": "transform",
  "transform_operation": "add_duration",
  "transform_args": "{\"iso_value\": \"{{ start_date }}\", \"amount\": 30, \"unit\": \"days\"}",
  "capture_variable": "expected_expiry"
}
```

Compute days between two captured dates:

```json
{
  "step_type": "transform",
  "transform_operation": "date_diff",
  "transform_args": "{\"a\": \"{{ expiry_date }}\", \"b\": \"{{ start_date }}\", \"unit\": \"days\"}",
  "capture_variable": "subscription_days"
}
```

Convert a date to epoch seconds (for use with number assertion operators):

```json
{
  "step_type": "transform",
  "transform_operation": "to_epoch",
  "transform_args": "{\"value\": \"{{ order_date_iso }}\"}",
  "capture_variable": "order_epoch"
}
```

Format a string template:

```json
{
  "step_type": "transform",
  "transform_operation": "format",
  "transform_args": "{\"template\": \"Order #{} - {}\", \"args\": [\"{{ order_id }}\", \"{{ status }}\"]}",
  "capture_variable": "order_label"
}
```

## Common pitfalls

- **Forgetting `transform_args` is a JSON-encoded string.** It must be a string, not a nested object. Validators reject malformed shapes.
- **Regex escaping.** In JSON, backslashes need doubling: `"pattern": "\\\\d+"` produces the regex `\\d+`. The frontend handles this; agents authoring JSON manually must do it explicitly.
- **Date parsing without `format` for ambiguous formats.** The parser refuses to guess on `01/02/2024` etc. Set `format` to the matching strptime pattern.
- **Months / years in `add_duration` or `date_diff`.** Not supported in v1. Stick to `seconds` / `minutes` / `hours` / `days` / `weeks`.
- **Variable typos in expressions.** `math` evaluates `{{ price }}` against the runtime variable map. A typo like `{{ pric }}` produces "Unknown variable: 'pric'" at execution time, not at authoring time.
- **`format` template injection.** The `format` op deliberately rejects attribute access (`{0.x}`) and index access (`{0[x]}`) inside placeholders to prevent Python format string injection. Use simple positional `{}` only.
- **Negative `tolerance` or unsupported `unit` in date payloads.** Pydantic models on the runtime side reject these. The agent should pass non-negative integers and units from the supported set.
