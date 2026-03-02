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
