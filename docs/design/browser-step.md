# Browser Step Type

## Summary

Add a `browser` step type that executes direct Playwright browser actions (reload, go_back, go_forward) without going through the Nova Act AI agent. The specific action is selected via a new `browser_action` field.

## User Journey

1. User opens the step creation dialog (either in the use case editor or the interactive wizard).
2. User selects "Browser" from the step type dropdown.
3. The instruction field is hidden. A "Browser Action" dropdown appears with options: Reload, Go Back, Go Forward.
4. User selects an action and saves the step.
5. During execution, the step calls the corresponding Playwright method directly (`page.reload()`, `page.go_back()`, `page.go_forward()`), bypassing Nova Act entirely.
6. The step returns success/failure like a `url` step — no `act_id` is produced.

## Design Decisions

### Why a new step type instead of extending `url`?

The `url` step uses `nova.go_to_url()` (Nova Act API). Browser steps use `nova.page.*` (Playwright direct). These are different execution boundaries. Keeping them separate preserves the semantic distinction: `url` = Nova-managed navigation, `browser` = raw browser control.

### Why `browser_action` as a sub-field instead of separate step types per action?

A single `browser` step type with a `browser_action` selector:
- Provides one place to toggle visibility (e.g., hide for mobile workflows).
- Avoids polluting the step type list with many small entries.
- All actions share the same execution pattern (no instruction, no act_id, Playwright direct).

### Instruction field

Unused for browser steps. The frontend hides it when `step_type === 'browser'`. The backend stores a generated description (e.g., "Browser: reload") for display in execution history and logs.

## Scope

### Actions (initial)

| `browser_action` | Playwright API | Description |
|---|---|---|
| `reload` | `page.reload()` | Refresh the current page |
| `go_back` | `page.go_back()` | Browser back button |
| `go_forward` | `page.go_forward()` | Browser forward button |

### Future actions (not in this change)

`clear_cookies`, `clear_storage`, `wait`, `screenshot`, `scroll_to_top`, `scroll_to_bottom`

## Data Model

New field on step records:

| Field | Type | Default | Description |
|---|---|---|---|
| `browser_action` | string | `""` | One of: `reload`, `go_back`, `go_forward`. Only used when `step_type === 'browser'`. |

No DynamoDB schema migration needed — DynamoDB is schemaless. The field is simply added to step items.

## Changes

### Backend Worker
- `models.py` — add `browser_action: str` field to `ExecutionStep`
- `browser_step.py` — new file with `execute_browser_step()` function
- `worker.py` — add `case 'browser':` to step dispatch
- `wizard_worker.py` — add `case 'browser':` to step dispatch
- `dynamodb_client.py` — read `browser_action` when constructing `ExecutionStep`

### CLI
- `step_executor.py` — add `case 'browser':` to dispatch
- `import_schema.py` — add `'browser'` to `VALID_STEP_TYPES`, add `browser_action` field to `ExportStep`

### Lambdas
- `create_step.py` — extract and store `browser_action`
- `update_step.py` — add `browser_action` to optional update fields

### Frontend
- `StepFormModal.tsx` — add Browser to step type options, show browser_action dropdown, hide instruction
- `StepForm.tsx` (wizard) — same changes
- `WizardStepBuilder.tsx` — include `browser_action` in step data

### Docs & Tests
- `step-types.md` — add browser section
- `test_skill_content.py` — update step type count from 7 to 8
