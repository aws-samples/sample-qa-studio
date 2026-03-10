# Managing Tests

## Overview

List, view, update, and delete tests using the CLI and web interface.

---

## Listing Tests

```bash
qa-studio tests list
```

**Output:**
```
ID:          abc12345-def6-7890-ghij-klmnopqrstuv
Name:        Login Flow
Description: Test user login with valid credentials

ID:          def67890-abcd-1234-efgh-ijklmnopqrst
Name:        Checkout Flow
Description: Complete checkout process
```

---

## Viewing Test Details

```bash
qa-studio tests get <id>
```

**Output:**
```
Name:         Login Flow
Description:  Test user login with valid credentials
Starting URL: https://app.example.com/login
Active:       true
Region:       us-east-1
Model:        nova-act-v1.0
Tags:         auth, login
Created At:   2025-07-01T14:00:00Z

Steps (4):
  1. [navigation] Navigate to login page
  2. [navigation] Enter username into email field
  3. [navigation] Enter password and click Sign In
  4. [validation] Verify dashboard heading is visible
```

---

## Deleting Tests

```bash
qa-studio tests delete <id>
```

**With confirmation prompt:**
```bash
qa-studio tests delete <id>
# Prompts: Delete test abc123? [y/N]
```

**Skip confirmation:**
```bash
qa-studio tests delete <id> --yes
```

---

## Updating Tests

Test updates are done via the web interface:

1. Navigate to the test in QA Studio
2. Click "Edit" or navigate to the "Steps" tab
3. Modify steps, variables, or configuration
4. Save changes

---

## Exporting Tests

Export tests as JSON for sharing or backup:

1. Open test in web interface
2. Click "Export" button
3. Save JSON file

---

## Importing Tests

```bash
# Via web interface:
# 1. Click "Create Use Case" → "Import Use Case"
# 2. Upload JSON file
# 3. Review and save
```

---

## Next Steps

- **Create new tests:** [📝 Creating Tests](./creating-tests.md)
- **Run tests locally:** [▶️ Local Execution](./local-execution.md)
- **Organize into suites:** [📦 Test Suites](./test-suites.md)
