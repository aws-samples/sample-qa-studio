# QA Studio Prompting Best Practices

This guide covers how to write effective test steps in QA Studio. Before reading this, start with the [Nova Act SDK prompting best practices](https://github.com/aws/nova-act#how-to-prompt-act), which covers the core do's and don'ts with detailed examples. This page builds on that foundation with guidance specific to QA test cases.

## How Test Steps Work

Test steps should be written the same way you'd write a traditional QA test case: clear, sequential instructions where each step describes a single action or verification. The agent reads each step and performs browser actions (clicks, keystrokes, navigations) to carry it out.

QA Studio supports several step types including navigation, validation, secrets, and more. For the full list and descriptions, see the [Workflow Steps](user-guide.md#workflow-steps) section of the User Guide.

Keeping steps concise and focused is better practice because:

- Execution recordings and logs are easier to review when each step maps to one action or one verification
- When a test fails, you can pinpoint exactly which step broke without rewatching an entire sequence
- Smaller steps are easier to reorder, reuse across test cases, and maintain as the application changes
- Retry and debugging cycles are faster when you only need to re-run a single focused step

Each step works most reliably when it can be accomplished in fewer than 30 browser actions. If a step needs more than that, break it into smaller steps.

Here's what a typical login test looks like, mixing all three step types:

| Step | Type | Instruction |
|------|------|-------------|
| 1 | Navigation | Click the "Sign In" button |
| 2 | Navigation | Enter "testuser" in the username field |
| 3 | Secret | Focus the password field |
| 4 | Navigation | Click "Login" |
| 5 | Validation | Verify that the welcome banner displays the text "Hello, Test User" |
| 6 | Validation | Verify that the navigation menu shows Dashboard, Settings, and Profile links |
| 7 | Retrieve Value | Return the number of unread notifications shown in the header |
| 8 | Assertion | Assert the captured notification count is greater than 0 |

## User Journey Wizard

The "Create from User Journey" wizard generates test steps automatically from a plain-language description of what you want to test. It uses a language model to convert your description into structured steps. See the [User Guide](user-guide.md#create-from-user-journey) for a walkthrough of how to use it.

To understand how the wizard interprets your input and what rules it follows when generating steps, see the [wizard system prompt](../lambdas/endpoints/generate_usecase.py) in the `create_prompt` function.

### Browser Recording with Variable Capture

When you use the optional browser recording feature, the recorded interaction sequence is included as supplementary context alongside your text description. The recording captures each action you performed (clicks, typing, navigation) and annotates variable operations automatically:

- **Extract variable** (Ctrl+C in the recorder): Highlighted text is captured with a variable name. The prompt annotates these as `[captures → {{var_1}}, value: "..."]` and instructs the model to generate a `retrieve_value` step with the corresponding `capture_variable`.
- **Paste variable** (Ctrl+V in the recorder): Pasting a previously extracted variable is annotated as `[uses → {{var_1}}]`. The model generates a step that references the variable using `{{VariableName}}` syntax. This is typically a `navigation` step (e.g., "type {{var_1}} into the search field"), but the model uses its judgment when the UI requires a different interaction — for example, selecting a value from a date picker or dropdown rather than typing directly.

This means you can extract a value on one page (e.g., a product price), navigate elsewhere, and use it in a form field — the generated test case will automatically include the correct `retrieve_value` and variable-referencing steps without manual editing.

The model can also proactively generate additional `retrieve_value` steps beyond what you explicitly recorded, when it identifies values in the journey that benefit from capture and reuse (e.g., a generated ID or a computed total that needs verification after a state change).

When variable actions are present in the recording, the prompt also includes explicit mapping instructions that tell the model to:
1. Map each `extract_variable` to a `retrieve_value` step
2. Map each `paste` with a source variable to a step using `{{VariableName}}`, adapting the interaction to the UI context
3. Ensure every captured variable is used in at least one later step
4. Keep captured variables separate from the static `variables` array (captured variables are runtime-resolved)

## Quick Reference

| Principle | Rule of Thumb |
|---|---|
| Be direct | State the action, not the reason |
| Be complete | Specify every value, choice, and stop condition |
| Add hints | Coach the agent past tricky UI elements |
| Use secrets | Never put sensitive data directly in step text |
| Step budget | Keep each step under 30 browser actions |

## Further Reading

- [Nova Act SDK: How to Prompt](https://github.com/aws/nova-act#how-to-prompt-act): detailed prompting do's and don'ts with examples
- [Wizard System Prompt](../lambdas/endpoints/generate_usecase.py): how the user journey wizard generates test steps
