# Validation Operators

## Overview

Validation and assertion steps use operators to compare values. Choose the right operator based on the data type and comparison logic.

---

## String Operators

### exact

**Description:** Exact string match (case-sensitive)

**Example:**
```
Verify heading text exact "Dashboard"
```

**Use when:** Exact match required, case matters

---

### exact_case_insensitive

**Description:** Exact string match (case-insensitive)

**Example:**
```
Verify heading text exact_case_insensitive "dashboard"
```

**Use when:** Exact match required, case doesn't matter

---

### contains

**Description:** String contains substring (case-sensitive)

**Example:**
```
Verify error message contains "Email is required"
```

**Use when:** Partial match, case matters

---

### contains_case_insensitive

**Description:** String contains substring (case-insensitive)

**Example:**
```
Verify page title contains_case_insensitive "welcome"
```

**Use when:** Partial match, case doesn't matter

---

### not_equal

**Description:** String does not match

**Example:**
```
Verify status not_equal "pending"
```

**Use when:** Negative assertion

---

## Number Operators

### equals

**Description:** Numeric equality

**Example:**
```
Verify cart count equals 3
```

**Use when:** Exact numeric match

---

### less_then

**Description:** Less than (note: `_then` not `_than`)

**Example:**
```
Verify price less_then 100
```

**Use when:** Upper bound check

---

### greater_then

**Description:** Greater than (note: `_then` not `_than`)

**Example:**
```
Verify stock greater_then 0
```

**Use when:** Lower bound check

---

### less_or_equal_then

**Description:** Less than or equal to

**Example:**
```
Verify discount less_or_equal_then 50
```

**Use when:** Upper bound with equality

---

### greater_or_equal_then

**Description:** Greater than or equal to

**Example:**
```
Verify minimum_order greater_or_equal_then 10
```

**Use when:** Lower bound with equality

---

## Boolean Operators

### exact

**Description:** Boolean equality (true/false)

**Example:**
```
Verify checkbox_state exact true
```

**Use when:** Boolean value comparison

---

## Date Operators

Use these with `validation_type: "date"` on `validation` and `assertion` steps. Both sides of the comparison are parsed by QA Studio (Nova returns the page text as a string; we parse it on our side). Inputs may be:

- ISO 8601 / RFC 3339 (auto-detected, e.g. `2024-01-02`, `2024-01-02T15:04:05Z`, `2024-01-02T15:04:05+02:00`)
- Unix epoch seconds (10-digit) or milliseconds (13-digit)
- A regional format if you ran `parse_date` upstream and reference the canonical capture variable

A naive datetime (no offset) is treated as a UTC anchor for comparison. When one side is naive and the other is TZ-aware, the step succeeds (or fails normally) but logs a warning so the mismatch is visible.

### before

**Description:** actual date is strictly before expected

**Example:**
```
Verify order_date before {{cutoff_date}}
```

**Use when:** Time-ordering checks (e.g. "was this created before the deadline")

---

### after

**Description:** actual date is strictly after expected

**Example:**
```
Verify last_login_date after {{first_login_date}}
```

**Use when:** Time-ordering checks (e.g. "was this updated after the previous version")

---

### equals

**Description:** actual date equals expected (millisecond precision)

**Example:**
```
Verify published_on equals 2024-01-02
```

**Use when:** Exact-match against a known date literal or another captured date.

---

### not_equals

**Description:** actual date is not equal to expected

**Example:**
```
Verify last_modified not_equals {{snapshot_modified}}
```

**Use when:** Confirming a mutation occurred without depending on a specific new value.

---

### equals_within

**Description:** absolute difference between actual and expected is within a tolerance

`validation_value` for this operator is **JSON-encoded** with three fields. The form builder in the web UI handles this automatically; if you author tests by hand, the shape is:

```json
{
  "date": "2024-01-02T15:00:00+00:00",
  "tolerance": 5,
  "unit": "minutes"
}
```

`unit` accepts `seconds`, `minutes`, `hours`, `days`, or `weeks`. `tolerance` must be a non-negative integer.

**Example (raw step JSON):**
```json
{
  "step_type": "assertion",
  "validation_type": "date",
  "validation_operator": "equals_within",
  "assertion_variable": "displayed_created_at",
  "validation_value": "{\"date\": \"{{server_created_at}}\", \"tolerance\": 5, \"unit\": \"minutes\"}"
}
```

**Use when:** Comparing dates with small expected drift (e.g. server-recorded vs client-displayed timestamp).

---

## Operator Selection Guide

| Data Type | Comparison | Operator |
|-----------|------------|----------|
| String | Exact match (case-sensitive) | `exact` |
| String | Exact match (case-insensitive) | `exact_case_insensitive` |
| String | Contains (case-sensitive) | `contains` |
| String | Contains (case-insensitive) | `contains_case_insensitive` |
| String | Not equal | `not_equal` |
| Number | Equal | `equals` |
| Number | Less than | `less_then` |
| Number | Greater than | `greater_then` |
| Number | Less than or equal | `less_or_equal_then` |
| Number | Greater than or equal | `greater_or_equal_then` |
| Boolean | Equal | `exact` |
| Date | Strictly before | `before` |
| Date | Strictly after | `after` |
| Date | Exact match | `equals` |
| Date | Not equal | `not_equals` |
| Date | Within a tolerance | `equals_within` |

---

## Common Patterns

### Pattern 1: Verify Page Title

```
[validation] Verify page title exact "Dashboard - QA Studio"
```

### Pattern 2: Check Error Message

```
[validation] Verify error message contains "required"
```

### Pattern 3: Validate Cart Count

```
[retrieve_value] Capture cart count into variable 'count'
[assertion] Verify variable 'count' greater_then 0
```

### Pattern 4: Check Price Range

```
[validation] Verify price greater_or_equal_then 10
[validation] Verify price less_or_equal_then 100
```

### Pattern 5: Verify Status Not Pending

```
[validation] Verify status not_equal "pending"
```

---

## Important Notes

1. **Number operators use `_then` not `_than`** - This matches the API specification
2. **String operators are case-sensitive by default** - Use `_case_insensitive` variants when needed
3. **Boolean values use `exact` operator** - Same as string exact match
4. **Variables from `retrieve_value` use `assertion` steps** - Not `validation` steps

---

## Next Steps

- **Learn step types:** [🎯 Step Types](./step-types.md)
- **Create tests:** [📝 Creating Tests](./creating-tests.md)
- **Best practices:** [📚 Best Practices](./best-practices.md)
