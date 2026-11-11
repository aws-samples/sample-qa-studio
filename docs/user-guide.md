# QA Studio User Guide

This guide walks you through every feature of the QA Studio web interface.

## Table of Contents

- [Getting Started](#getting-started)
- [Use Cases](#use-cases)
- [Applications: Shared Variables, Secrets and Datasets](#applications-shared-variables-secrets-and-datasets)
- [Cost per Use Case, Application and Overall](#cost-per-use-case-application-and-overall)
- [Mobile Testing](#mobile-testing)
- [Electron Testing](#electron-testing)
- [Viewing Execution Results](#viewing-execution-results)
- [Test Suites](#test-suites)
- [Templates](#templates)
- [Writing Good Test Steps](#writing-good-test-steps)
- [User Management (Admin Only)](#user-management-admin-only)
- [OAuth Client Management (Admin Only)](#oauth-client-management-admin-only)
- [Tips and Tricks](#tips-and-tricks)

---

## Getting Started

### Signing In

1. Open the QA Studio URL provided by your administrator.
2. Enter your email address and the temporary password you received via email.
3. On first login, you'll be prompted to set a permanent password. Passwords must be at least 8 characters and include uppercase, lowercase, numbers, and symbols.

Once signed in, you'll land on the home screen with the Use Cases dashboard.

### Navigating the Interface

The left sidebar contains the main sections:

- **Use Cases**: Your test definitions and execution history (home page)
- **Applications**: The applications under test. While you are on an application's page the group expands to that application's **Variables**, **Secrets** and **Datasets** pages (see [Applications: Shared Variables, Secrets and Datasets](#applications-shared-variables-secrets-and-datasets))
- **Test Suites**: Groups of use cases that run together
- **Templates**: Reusable test blueprints with configurable variables

If you have admin access, you'll also see:

- **Users**: Manage who can access QA Studio
- **OAuth Clients**: Manage API credentials for automation tools

---

## Use Cases

A use case is a single test scenario. It defines what website to test, what steps to perform, and what to expect. Think of it as a checklist that an AI-powered browser follows automatically.

### The Use Cases Dashboard

The home screen shows all your use cases in a table with:

- Name and description
- Tags for organization
- Last execution status (success, failed, etc.)
- When it was last run

You can:

- **Search** use cases using the filter bar at the top
- **Select multiple** use cases using the checkboxes
- **Run selected** use cases in batch by clicking the execute button
- **Delete selected** use cases in batch

### Creating a Use Case

Click **Create Use Case** (on the Use Cases page, or **Create usecase** on an application) to open the creation
wizard at `/create/new`. Every creation method runs through this one wizard. Old links such as `/create`,
`/create/blank` or `/create/clone?sourceId=…` redirect into it with the matching choice preselected.

**Step 1 — How to start**: create a new use case, clone an existing one, or import an exported JSON file.

**Create new** continues with:

1. **Platform selection** — Web, Mobile (Android/iOS via Device Farm) or Electron.
2. **Basic info** — name, description, tags, application, execution region and model.
3. **Creation method**:
   - **Blank** — start empty and add steps afterwards. The next step configures the browser (starting URL,
     optional browser policy, step caching), the mobile app (identifiers, device, app binary) or the Electron app
     (optional bundle ID).
   - **Interactive wizard** (web only) — start a live browser, type a step, watch it run and accept it; repeat until
     the test is complete.
   - **Template** (web only) — pick a template; its steps and variables are copied, and its secrets are asked for
     on the review step.
   - **User journey** — describe the test in plain English (optionally with a browser recording) and let AI
     generate the steps, for example:

     > "Log in to the application, navigate to the settings page, change the display name, and verify the change was saved."

     During recording, Ctrl+C extracts a value into a variable and Ctrl+V pastes it elsewhere — see
     [Prompting Best Practices](prompting-best-practices.md#browser-recording-with-variable-capture).

**Clone** — select the source use case (its summary is shown) and name the copy. Mobile configuration is copied.
**Clone Use Case** in a use case's action menu opens this path with the source preselected.

**Import** — upload a previously exported JSON file. Secrets the file needs are asked for before creating. App
binaries are not part of exports and must be re-uploaded.

**Last step — Review & create**: check the summary and click **Create**; you land on the new use case.

#### Linking into the creation wizard

The creation wizard lives at `/create/new`. Query parameters preselect choices, so docs, runbooks and other pages
can link straight to a method:

| Parameter | Values | Effect |
|-----------|--------|--------|
| `path` | `create-new`, `clone`, `import` | Selects how to start and opens the next step |
| `method` | `blank`, `interactive-wizard`, `template`, `user-journey` | Preselects the creation method. Only with `path=create-new` (platform selection and basic info still come first) |
| `sourceId` | use case ID | Preselects the use case to clone and loads its summary. Only with `path=clone` |
| `applicationId` | application ID | Preselects the application |

Examples: `/create/new?path=clone&sourceId=<id>`, `/create/new?path=create-new&method=template`. An unknown value or a
combination that does not fit (for example `path=import&method=blank`) is ignored and the wizard starts at
**How to start**. The parameters apply once, when the page opens.

### Inside a Use Case

When you open a use case, you'll see its details organized into tabs:

#### Execution History
A table of every time this test has been run, newest first, showing:
- Status (pending, executing, completed, failed, stopped)
- When it started and finished
- How it was triggered (manual or scheduled)

Select a run (radio button) to open its details in a panel at the bottom of the page. The panel header reads
**Execution `<id>`** and shows the execution information, the timeline, the variables, the **Execution Steps** table with
screenshots, downloaded files and, for CI runner executions, the logs. Selecting another row switches the panel to that
run. The gear icon in the panel header moves the panel to the **side** or back to the **bottom**; the choice is remembered
in the browser for your next visit. The panel stays open while you switch tabs, so you can read the **Workflow Steps**
next to the execution's steps. Closing the panel (X) clears the selection.

- A **running** execution shows the live view and a **Stop Execution** button in the panel; the panel refreshes every
  10 seconds until the run finishes.
- **Delete** above the table removes the selected run after you type `permanently delete`; the panel closes.

The selected run is part of the URL: `/usecase/<usecase-id>?tab=history&execution=<execution-id>` opens the use case
with that run's panel already open, so you can bookmark or share it. Old links of the form
`/usecase/<usecase-id>/execution/<execution-id>` redirect to the new URL.

Click **Trigger Execution** to run the test immediately.

##### The Execution Steps table

The table is laid out for the narrow side panel too:

| Column | Shows |
|--------|-------|
| `#` | The step's position, centred |
| Status | The step status as an icon only, centred; hover it to see the status (`success`, `failed`, `executing`, `pending`, …) |
| Instruction | From top to bottom: a heading line with the step type badge (the same badge as in the use case's **Workflow Steps**, e.g. *Value*, *Network*) and, on steps unrolled from a **Repeat**, the **Row i/n** badge on the left, and the small **Trace** link and **Act ID** copy control (or *Executed from cache*) plus the details toggle on the right; then the instruction, for validation steps a grey validation box and for capturing steps a grey capture box (see below), then error logs |

Before the first step of each dataset row of a **Repeat**, the table has a row of its own with a **Repeat** badge and
the row header (*Login as each user — row 1 of 10*). It has no step number and no status.

There is no separate Validation column. Steps the runner has not reached yet (status `pending`) are greyed out in the
Instruction column, and so is the repeat group row of a dataset row that has not started. Validation and capture steps have details (the grey boxes below). They are
shown for failed steps and hidden for all other steps; the small arrow button at the right end of the step's first line
(**Show details** / **Hide details**) opens or closes them. Your choice stays while the panel refreshes; a running step
that fails opens its details by itself unless you toggled it. Error logs are always shown.

The validation box of a validation step shows:

| Line | Content |
|------|---------|
| Top (small) | **Type** and **Operator** of the validation, e.g. `Type string  Operator contains` |
| **Expected** | The validation value, with variables shown as badges |
| **Actual** | The value the runner recorded; `—` until the step has run |

Long expected or actual values wrap inside the box. Steps without a validation have no box.

Steps that capture a runtime variable (`retrieve_value`, `transform`) show a grey capture box under the instruction:

| Line | Content |
|------|---------|
| Top (small) | **Variable**: the captured variable name; **Type**: the value type of a `retrieve_value` step (`string` when not set), or **Operation**: the transform operation of a `transform` step |
| **Value** | The value this step captured; `—` until the step has run. A later step that overwrites the variable does not change it (unlike the badges, which show the run's final value) |

##### Variables in the Execution Steps table

Steps are stored with their templates (`Search for {{product}}`); the runner substitutes the values only in memory.
The table therefore resolves every `{{name}}` in the instruction and in the validation value itself, with the same
rules as the runner, and shows it as a dark blue badge: a small `VAR` label followed by the value in its original casing.
`Search for {{product}}` reads `Search for` **VAR Laptop**. Text around the badge is unchanged. All variable badges are
dark blue, so they stand apart from the step type badges; a
label in uppercase italics (`UNIQUE_ID`, `EMPTY_VALUE`, `UNDEFINED_VALUE`, …) means the badge shows no literal value.

| Kind | Applies to (first match wins) | The badge shows |
|------|-------------------------------|-----------------|
| Predefined | `{{UniqueID}}`, `{{Time}}`, `{{ExecutionID}}`, `{{CreatedAt}}` | The uppercase name in italics: `UNIQUE_ID`, `TIMESTAMP`, `EXECUTION_ID`, `CREATED_AT`. The runner fills these in itself; the badge never shows their value |
| Runtime | A variable captured by a `retrieve_value` or `transform` step of this run | The captured value |
| Predefined | `{{RepeatIndex}}`, `{{RepeatTotal}}` on a step unrolled from a **Repeat** | `REPEAT_INDEX` / `REPEAT_TOTAL` in italics (the row is shown by the **Row i/n** badge above the instruction) |
| Regular | A dataset column on a step unrolled from a **Repeat** | That row's cell |
| Regular | A variable defined when the run started (application, use case or run override) | The value |
| Runtime | A name that a later step of this run captures, but which has not been captured yet | The variable name in italics; it switches to the value within 10 seconds of the capture while the panel refreshes |
| Undefined | Anything else: an unknown name, a typo, or whitespace inside the braces (`{{ product }}`) | `UNDEFINED_VALUE` in italics. The runner left this text unresolved, which is a likely cause of a failed step (see [Troubleshooting](./troubleshooting.md#a-step-shows-a-var-undefined_value-badge)) |

- A regular or runtime variable whose value is the empty string shows `EMPTY_VALUE` in italics. The runner
  substituted an empty string there.
- Long values (a URL, a JSON blob) are cut off with an ellipsis after about 240 px; hover the badge to see the full
  value. Hovering does not show the variable name.
- The **Variables** container of the panel lists the same snapshot as **Defined Variables**: the merged variables the
  run started with, not the use case's current variables. Edits made after the run do not change an old run's badges.
- A runtime variable shows its **final** value on every step. If a capture overwrites a variable later in the run, or
  a capture shares its name with a defined variable, steps that ran before the capture used a different value than the
  badge shows.
- The Live View "current step" line still shows the raw template.

#### Workflow Steps
The ordered list of instructions the AI browser will follow. Each step has:
- A sort order (the sequence)
- The instruction text (what to do)
- An optional secret reference (for sensitive data like passwords)

You can add, edit, reorder, and delete steps here. Every step is shown as a card. To reorder, grab the card's drag
handle (the dotted icon on the left) and drop the card at its new position. The keyboard works too: focus the handle
with Tab, press Space or Enter to pick the card up, move it with the arrow keys, and press Space or Enter again to drop
it (Escape cancels).

**Types of steps:**
- **Navigation**: Plain language instructions like "Click the Submit button" or "Navigate to the Dashboard page". This is the default step type.
- **Validation**: Reads a value from the live page and compares it against an expected value. Supports `string`, `bool`, and `number` types with operators like `exact`, `contains`, `not_equal`, `greater_then`, `less_then`, etc. The instruction should describe what value to retrieve (e.g., "return the text of the welcome banner").
- **Secret**: Steps that reference a stored secret. The action describes what to do (e.g., "Type the password in the password field") and the secret provides the sensitive value at runtime. The secret value never appears in logs.
- **Retrieve Value**: Extracts a value from the page and stores it as a runtime variable for use in later steps. You specify a variable name and a value type (`string`, `number`, or `bool`). The captured value can be referenced in subsequent steps using `{{VariableName}}` template syntax.
- **Assertion**: Compares a previously captured runtime variable against an expected value. Does not interact with the browser. Use this after a Retrieve Value step to verify the captured data matches expectations. Supports the same type and operator combinations as Validation.
- **URL**: Navigates the browser directly to a specific URL. The instruction is the URL itself. ⚠️ *Deprecated — use Browser → Navigate instead. Existing URL steps continue to work.*
- **Browser**: Performs browser-level actions without interacting with page elements. Choose an action: **Reload** (optionally hard reload to bypass cache), **Back** (navigate back in history), **Forward** (navigate forward in history), or **Navigate** (go to a specific URL). This replaces the URL step type for new tests.
- **Transform**: Computes or manipulates a value using a built-in operation and stores the result in a variable. Supports 24 operations: math, round, floor, ceil, abs, min, max, concat, upper, lower, trim, replace, substring, length, to_number, to_string, to_int, regex_extract, format, parse_date, format_date, add_duration, date_diff, and to_epoch. See "Working with dates" below for the date-specific operations. Always requires a capture variable for the output.
- **Download**: Downloads a file from the page and uploads it to S3 for later retrieval.
- **Repeat**: A data-driven loop. The step carries a small table (columns + rows); the steps you add *inside* it run once per row, and every column is available to them as `{{column}}`. Use it when the same flow must be checked for several inputs (log in as each user, open each product) instead of copying the steps. See [Repeat steps (data-driven loops)](#repeat-steps-data-driven-loops) below.
- **Network Assertion**: Couples a UI action with an HTTP observation. When the step's instruction triggers an outgoing request matching the configured URL pattern, QA Studio can (optionally) verify the HTTP method and request body, (optionally) mock the response so the UI receives a fixed status/body/headers, and (optionally) assert the response status code and response body. Use this to verify API contracts without a separate integration-test harness, or to drive the UI into specific states (loading, error, empty) without a live backend. Body-matching supports full equality (`exact`), partial/template (`subset`), and structural (`schema` — JSON Schema Draft 2020-12) modes. The schema mode is especially useful for list endpoints where only "every item has these fields" matters, not the array length. Response-side assertions accept only `subset` and `schema` because response payloads frequently contain non-deterministic values (timestamps, generated ids). Request, response, and mock body sizes are each capped at 1 MiB by default (configurable per deployment via `networkAssertionBodyMaxBytes`), and the wait timeout is capped at 120 seconds.

#### Repeat steps (data-driven loops)

A **Repeat** step runs the steps nested inside it once per dataset row.

**Authoring walkthrough**

1. Open the use case, click **Add Step**, pick step type **Repeat**.
2. Enter a **Label** (e.g. `Login as each user`). Labels must be unique among the repeat steps of the use case — the CLI's `--dataset-file` addresses the dataset by this label.
3. Choose the **Dataset source** (shown only when the use case belongs to an application):
   - **Inline** — build the dataset in the grid: rename the column headers (e.g. `email`, `role`), add rows with **Row**, add columns with **Column**. Or expand **Paste CSV**, paste `email,role` + one line per row and confirm **Replace** — the first line becomes the columns.
   - **Application dataset** — pick one of the application's datasets from the **Application dataset** dropdown (each option shows `N columns × M rows`). The rows live on the application and are shared by every use case that picks the dataset; see [Datasets](#datasets). A repeat step uses one source or the other, never both.
4. Save. The repeat appears in the step list with a summary (`3 rows · email, role` for inline rows, `Application dataset: customers · 5 rows · 3 columns` for a dataset), an empty indented body ("No steps inside yet") and an **Add step inside** action.
5. Click **Add step inside** and create the loop body: typically a **Browser → Navigate** step to the entry page first (browser state is *not* reset between rows), then the actions and checks. Use `{{email}}`, `{{role}}`, … in instructions; `{{RepeatIndex}}` and `{{RepeatTotal}}` are available too. Children are shown indented under the repeat.
6. For an **Assertion** child, the variable dropdown lists the repeat's columns under *From dataset: &lt;label&gt;* next to captured runtime variables, so you can compare a captured value against a column (e.g. `displayed_price` equals `{{expected_price}}`).

Rules and limits:

| Rule | Value |
|---|---|
| Columns | 1–20, identifiers (`letters, digits, _`, not starting with a digit), unique, not `UniqueID` / `Time` / `ExecutionID` / `CreatedAt` / `RepeatIndex` / `RepeatTotal` |
| Rows | 1–100, every row has one cell per column, cells are text |
| Dataset size | ≤ 200 KB |
| Nesting | One level — a repeat cannot contain a repeat |
| Variable precedence | use case variables < dataset columns < runtime captures < built-ins |
| Reordering | Dragging a repeat moves its whole block; children can only be reordered inside their block |
| Deleting | Deleting a repeat deletes its children (the confirmation names how many) |
| Dataset source | Inline rows **or** one application dataset per repeat step; the dataset must belong to the use case's application. Switching the source in the step form replaces the previous one. Templates never offer the application source |
| Templates | Repeat steps are not available in templates |
| Wizard | The interactive wizard does not offer the Repeat step |

**In executions.** The repeat itself does not appear in an execution. Each inner step appears once per row, tagged **Row i/n**, and each row starts with a group row like *Login as each user — row 2 of 3* (with a **Repeat** badge). Execution is fail-fast: the first failing step fails the execution and the steps of later rows stay `pending`. Trajectory replay (step caching) is not used inside a repeat.

**In CI.** `qa-studio run --usecase-id <id> --dataset-file "Login as each user=users-staging.csv"` replaces the stored rows — inline or from an application dataset — with a CSV for that run (header row = the columns; the label may be omitted when the use case has exactly one repeat). See [CI/CD Integration](./ci-cd-integration.md#using-dataset-overrides-repeat-steps).

#### Working with dates

Date-aware testing in QA Studio uses two surfaces: the **Transform** step type provides five date operations (`parse_date`, `format_date`, `add_duration`, `date_diff`, `to_epoch`), and **Validation** / **Assertion** steps support a "Date" comparison type with operators `before`, `after`, `equals`, `not_equals`, and `equals_within`.

**Format selection.** Most user-facing pages render dates in regional formats like `01/02/2024` (which is ambiguous between US "Jan 2" and EU "Feb 1") or `Jan 2, 2024`. QA Studio deliberately rejects ambiguous input rather than guessing, so a test that runs in a different region won't silently produce the wrong date. The transform step editor exposes a curated dropdown of common formats grouped by region (ISO, US, EU) — pick the one that matches what the page renders. For unusual formats, the dropdown's "Custom…" option accepts a free-form Python `strptime` pattern; a link to the Python reference is provided in the form. Auto-detection still works for ISO 8601 (`2024-01-02`, `2024-01-02T15:04:05Z`) and Unix epoch values (10-digit seconds or 13-digit milliseconds) — those formats are unambiguous and need no explicit format.

**Comparing two dates from the page.** The most common pattern. Capture each date with a `retrieve_value` step using `value_type: "date"` and the format that matches what the page renders — the worker parses the AI-extracted string on its side and stores the canonical UTC ISO 8601 form in your capture variable, ready to compare directly. Add an `assertion` step with `validation_type: "date"` and the appropriate operator. Both sides are parsed with the same logic, so timezone is consistent.

If you can't or don't want to set the format on `retrieve_value` (for example, the page renders ISO 8601 already and auto-detect is enough), leave the format empty. If the format is something `retrieve_value` doesn't support directly or you want to compute the date through a transform, capture as a plain string with `value_type: "string"` and run a follow-up `transform.parse_date` to canonicalize.

**Comparing against a known date.** Put the literal date in the `validation_value` field. ISO format is recommended (`2024-01-02`); regional literals require running `parse_date` upstream and referencing the canonical capture variable.

**Tolerance comparisons (`equals_within`).** When testing that a displayed timestamp is close to a server-recorded value, use `equals_within` and specify a tolerance amount + unit (e.g. 5 minutes). The form builder writes the JSON shape into the `validation_value` field automatically.

**Canonical UTC.** All five date transform ops produce UTC ISO 8601 strings. A naive datetime (no offset) is treated as a UTC anchor — comparisons stay consistent as long as both sides use the same convention. If you mix a naive value with a TZ-aware value in a comparison, the step succeeds normally but logs a warning so you can spot the mismatch.

**No clock semantics in v1.** There is no built-in "now" — both sides of a date comparison must come from the page or from a literal you provide. If you need freshness checks against the wall clock, raise the request and we can extend the spec.

**Months and years are not supported in `add_duration` / `date_diff`.** Their arithmetic is policy-dependent (e.g., `Jan 31 + 1 month` has multiple valid answers). Only `seconds`, `minutes`, `hours`, `days`, and `weeks` are supported. If you need calendar-month or year arithmetic, parse the date, do the math in `transform.math`, and re-format.

#### Schedule
Set up automatic recurring runs. You can:
- Choose from preset schedules (daily, weekdays, weekly, hourly, etc.)
- Enter a custom cron expression for advanced scheduling
- Select a timezone
- Enable or disable the schedule

#### Variables
Define key-value pairs that can be referenced in your test steps. Variables make tests reusable across different environments or configurations (e.g., different URLs, usernames, or settings).

If the use case belongs to an application that defines [application variables](#variables-1), they are listed first under **Inherited from application** with an **Application** badge. Those rows are read-only here; to change one for this use case only, add a use-case variable with the same key — the key field shows *Overrides application value* and the use-case value wins. Saving never copies inherited rows into the use case.

#### Secrets
Store sensitive values like passwords, API keys, or tokens. Secrets are:
- Encrypted and stored securely
- Never shown in logs or execution history
- Referenced by name in secure steps

To add a secret, provide a key name and the secret value. You can delete secrets you no longer need.

Secrets defined on the owning application appear in the **Current Secrets** table with an **Application** badge and no Delete action. A use-case secret with the same key shadows the application secret (the editor shows an info hint before you save). In the secret-step dropdown inherited keys are labelled `key (application)`.

**Using a secret in a step.** A secret step runs in two phases. First, the agent performs the step's instruction (it never sees the secret). Then the secret value is typed into whichever element has keyboard focus. It does not press Enter. Write the instruction so it only focuses the target field:

| Instruction | Result |
|---|---|
| `Click into the password field.` | Works: the field is focused, then the secret is typed into it |
| `Search` | Fails: the agent reads the appended success prompt as text to search for, then the secret is typed after the page has changed |
| `Type the password and press Enter` | Fails: the agent types its own text and submits before the secret is typed |

To submit the form, add a separate navigation step after the secret step (for example `Press Enter.` or `Click the Sign in button.`).

Secret values are masked as `***` in execution logs and are never written to CloudWatch.

#### Headers
Configure custom HTTP headers that should be sent with requests during test execution. Useful for authentication tokens, custom identifiers, or API keys that your application requires.

#### Hooks
Set up scripts that run before or after test execution:
- **Before script**: Runs before the test starts (e.g., set up test data)
- **After script**: Runs after the test completes (e.g., clean up resources)

#### Browser Policy
Upload a Chromium enterprise policy JSON file to control browser behavior during test execution. This is useful for automatically handling permission dialogs (geolocation, notifications, camera access, local network access, etc.) that would otherwise block test execution.

To configure a browser policy:
1. Create a JSON file following the [Chrome Enterprise Policy List](https://chromeenterprise.google/policies/)
2. Upload it via the **Browser policy** section in the use case settings
3. The policy is applied as a managed Chromium enterprise policy when the AgentCore browser is created for each execution

Common policy values:
- `1` = Allow without prompting
- `2` = Block without prompting

Example policy that blocks all permission dialogs:
```json
{
  "DefaultGeolocationSetting": 2,
  "DefaultNotificationsSetting": 2,
  "DefaultWebBluetoothGuardSetting": 2,
  "InsecurePrivateNetworkRequestsAllowed": true
}
```

> **Note:** Browser policies only apply to web tests running on AgentCore Browser. They do not apply to mobile tests or CLI local execution.

### Exporting a Use Case

From the use case detail page, you can export the use case as a JSON file. This file contains all steps, configuration, mobile settings, and metadata (secrets and app binaries are excluded for security). Use this to share tests with colleagues or back them up.

### Importing via CLI

In addition to importing a single use case through the UI, the QA Studio CLI supports batch importing exported JSON files from a file or folder:

```bash
# Import a single file
qa-studio tests import ./login_test.json --application-id <app-id>

# Import all JSON files from a folder (recursive)
qa-studio tests import ./testcases/ --application-id <app-id> --yes

# Validate files without importing (dry-run)
qa-studio tests import ./testcases/ --dry-run

# Override the starting URL for a different environment
qa-studio tests import ./testcases/ --application-id <app-id> --base-url https://staging.example.com --yes

# CI pipeline usage: JSON output, no prompts
qa-studio tests import ./testcases/ --application-id <app-id> --format json --skip-secrets

# Fully non-interactive with values supplied (dev/local credentials only)
qa-studio tests import ./tests/auth/login.json --application-id <app-id> \
  --non-interactive \
  --secret admin_email=admin@dev.local \
  --secret admin_password="$DEV_ADMIN_PASSWORD"

# Non-interactive deferring secret config to the UI
qa-studio tests import ./tests/auth/login.json --application-id <app-id> --non-interactive --skip-secrets
```

The import follows a two-phase flow:

1. **Scan & Validate** — All JSON files are discovered and validated against the export schema. A summary table shows which files are valid.
2. **Import** — After confirmation, valid files are sent to the API. If any file contains secrets, you'll be prompted to enter values (use `--skip-secrets` to configure them later in the UI, or `--secret KEY=VALUE` to supply values inline).

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `path` | positional | required | File or directory path to import |
| `--dry-run` | flag | `false` | Validate only, do not import |
| `--yes` / `-y` | flag | `false` | Skip confirmation prompt |
| `--non-interactive` | flag | `false` | Run without any prompts. Implies `-y`. Exits with code 2 if any secret value is missing — supply via `--secret KEY=VALUE` or use `--skip-secrets` to defer. |
| `--secret` | `KEY=VALUE` (repeatable) | none | Pre-supply a secret value. Suppresses the interactive prompt for that key. Errors if `KEY` is not declared by any imported test. |
| `--base-url` | string | `None` | Override `starting_url` for all imports |
| `--skip-secrets` | flag | `false` | Skip interactive secret prompts |
| `--format` | choice | `human` | Output format: `human` or `json` |

To *run* a use case from the CLI see [CI/CD Integration → `qa-studio run`](./ci-cd-integration.md#qa-studio-run). Flag worth knowing for data-driven tests:

| Flag | Type | Default | Description |
|---|---|---|---|
| `--dataset-file` | `[LABEL=]PATH` (repeatable) | none | CSV replacing the stored rows of the repeat step `LABEL` for this run; header row = the repeat's columns. `LABEL` may be omitted when the use case has exactly one repeat. Only with `--usecase-id`. |

Exit codes: `0` on success, `1` if any file failed to import, `2` for input-validation errors (malformed `--secret KEY=VALUE`, `--secret` referencing an unknown key, or `--non-interactive` set with required secrets unsupplied).

See the [CLI README](../qa-studio-cli/README.md#importing-test-cases) for the full reference.

---

## The Applications page

The **Applications** page is the home of QA Studio: `/` redirects here and the first entry of the left navigation opens it. It is both the health dashboard and the management page for your applications.

Each application appears as a card in a grid, worst performers first:

- **Pass rate**, **Executions** and **Failures** as large numbers (pass rate is green ≥ 90 %, yellow ≥ 70 %, red below), with **Cost (30d)** on the right.
- A sparkline of daily successes and failures; the **7 days / 30 days** toggle in the page header switches the window.
- **Last run** status under the application name.
- A footer with quick links: the use-case and test-suite counts open the matching tab of the application's page, the team name links to the team page (admins only), and the base URL opens the application itself in a new tab.

The **Actions** menu on each card manages the application without leaving the page: **Edit**, **Add use cases**, **Add test suites**, the configuration pages (**Variables**, **Secrets**, **Datasets**) and **Delete**. Deleting asks you to type `permanently delete`; use cases and test suites survive — only their association with the application is removed. **Edit** and **Delete** are restricted to admins and the team lead of the owning team; **Create application** (page header) is available to admins and team leads.

Reloading never blanks the page: the **Reload** button and the automatic refresh every 60 seconds update the cards in place, and the header shows the time of the last update.

---

## Applications: Shared Variables, Secrets and Datasets

An **application** groups the use cases and test suites of one system under test and already carries its base URL. It can also hold the configuration that every use case of the application needs: variables, secrets and datasets. Define them once on the application; use cases inherit them and only keep what makes them different. Rotating a password or changing a staging URL then happens in one place.

**Precedence (lowest → highest): Application → Use case → CLI run override.**

| Kind | Defined on the application | Overridden by | Merged how |
|---|---|---|---|
| Variables | **Variables** page | a use-case variable with the same key; `qa-studio run --var KEY=VALUE` | per key |
| Secrets | **Secrets** page | a use-case secret with the same key | per key |
| Datasets | **Datasets** page | a repeat step's own inline rows (each repeat step picks *one* source); `qa-studio run --dataset-file LABEL=file.csv` for one run | whole table |

Headers and cookies stay per use case.

### Who can change them

Everyone who can view the application sees the three pages read-only. In the web UI the pages are editable for the **team lead of the owning team** and for **admins** (the same people who can edit the application itself). The API is slightly looser — Editors of the owning team may write through the CLI (`qa-studio apps …`) or the API. See [User Management → Application management](./user-management.md#application-management).

### Opening the pages

1. Go to **Applications** and click the application.
2. Either expand the **Applications** group in the left navigation — while you are on an application's page it lists **Variables**, **Secrets** and **Datasets** — or open the **Actions** dropdown in the page header and pick one of them under **Configuration**. (**Edit** and **Assign to team** live in the same dropdown.)
3. Every page shows the breadcrumb *Applications → \<application\> → \<page\>*.

### Variables

Key/value pairs available as `{{key}}` in every use case of the application.

1. Click **Add new variable**, fill **Key** (letters, digits, `_`; not starting with a digit) and **Value**.
2. Click **Save Changes**; a *Variables saved* message confirms. **Reset Changes** discards unsaved edits.
3. Up to 100 variables; the list is saved as a whole.

On a use case the inherited rows appear read-only under **Inherited from application** with an **Application** badge. Adding a use-case variable with the same key overrides the value for that use case only.

### Secrets

Passwords, API keys and tokens shared by the application's use cases.

1. Click **Add new secret**, enter the **Secret Key** and the **Secret Value** (masked), then **Save Secrets**.
2. The key appears in **Current Secrets**; the value is stored in AWS Secrets Manager and is never shown again — not on this page, not in logs.
3. **Delete** removes a secret immediately (no recovery window). Setting an existing key again rotates its value for every use case of the application.

On a use case the inherited keys are listed with an **Application** badge and can be picked in a secret step's dropdown (shown as `key (application)`). A use-case secret with the same key shadows the application's. Executors read secret values only at run time, through the use case — there is no way to display an application secret's value.

### Datasets

Named tables (columns + rows) that **Repeat** steps reference instead of carrying their own rows, so several use cases share one list of customers, products or accounts.

1. Click **Create dataset**. Give it a **Name** (unique within the application; letters, digits, spaces, `_`, `-`) and an optional **Description**.
2. Build the table in the grid exactly as for an inline repeat step (rename columns, **Row** / **Column**, or **Paste CSV**). The same limits apply: 1–20 columns, 1–100 rows, 200 KB.
3. Click **Create**. The table lists the dataset with its column and row counts and last update time.
4. Select a dataset to **View** it, **Edit** it (name, description, rows — every use case that references it sees the change on its next execution) or **Delete** it.

A dataset that repeat steps still reference cannot be deleted: a **Dataset is still in use** notice names the use cases (with links). Switch those repeat steps to inline rows or another dataset first. Likewise, a use case whose repeat steps reference datasets cannot be moved to another application until those steps are switched; the error lists the steps.

To use a dataset, open a repeat step on a use case of the application, set **Dataset source** to **Application dataset** and pick it (see [Repeat steps](#repeat-steps-data-driven-loops)). In executions the rows look exactly like inline rows (**Row i/n** badges). Exported use cases keep the dataset reference; importing such a file into another application fails until a dataset with that id exists there (datasets are not copied).

### From the CLI

The same configuration is scriptable:

```bash
qa-studio apps variables set <app-id> base_api=https://api.staging.example.com
qa-studio apps secrets set <app-id> admin_password          # value prompted, never echoed
qa-studio apps datasets create <app-id> customers --file customers.csv
qa-studio run --usecase-id <id> --var base_api=https://api.pr-42.example.com   # wins over both layers
```

See [CI/CD Integration → Application-level configuration](./ci-cd-integration.md#application-level-configuration-variables-secrets-datasets) and the [CLI README](../qa-studio-cli/README.md#application-configuration).

### The application's Usecases tab

The **Usecases** tab of an application's page lists the use cases that belong to it. Select rows with the checkboxes, then use the button next to the table:

- **Execute selected (n)** starts one execution per selected use case.
- **Remove selected (n)** only unlinks the use cases from the application. They stay on the **Use Cases** page.
- **Delete selected (n)** deletes the use cases permanently, with their steps, executions and configuration. It opens the same dialog as on the **Use Cases** page: **Delete** stays disabled until you type `permanently delete`. A notice reports the result, e.g. *Successfully deleted 2 use case(s)*, and the table and the tab count update. The item is shown to everyone; the server checks the permission (admin, or team lead or editor of the owning team). A use case you may not delete is named in a red *Failed to delete n use case(s): …* notice and stays in the table.
- **Add existing usecases** links use cases that already exist to the application.

**Execute**, **Remove** and **Delete** are disabled while nothing is selected.

---

## Cost per Use Case, Application and Overall

QA Studio runs tests on paid AWS services — Nova Act (the agent that drives the browser) and the Lambda MicroVMs the cloud runs execute on. Once a day QA Studio takes the **real bill** for those services from AWS Cost Explorer and splits it over the use cases that used them, in proportion to their measured usage (agent seconds for Nova Act; VM seconds and VM launches for compute). Use-case costs roll up to their application and to a studio-wide total. The figures answer "what did this test cost, and is it getting more expensive?" with the amounts that appear on the AWS invoice, not with an estimate.

The compute figure is the account's whole Lambda MicroVM bill split over QA Studio's use cases: MicroVMs cannot be tagged per run, so it equals QA Studio's own spend only when QA Studio is the sole MicroVM user in the account. The worker image carries the tag `application = qa-studio`; if you share the account with other MicroVM workloads, activate `application` as a cost allocation tag in the payer account so the spend can be told apart in Cost Explorer.

### Where the numbers appear

| Page | What you see |
|---|---|
| **Applications** (home page) | Every application card shows **Cost (30d)**: the application's allocated bill over the last 30 days with a trend arrow and percentage against the 30 days before. **—** means no cost data exists for the application yet (hover shows *No cost data yet*). |
| **Application detail → Cost tab** (`?tab=costs`) | The **Cost** card: **Last day**, **Last 7 days** and **Last 30 days** with trend arrows, the list-price figure as smaller text under each amount, a 30-day bar chart of daily cost, and a table of the application's use cases sorted by 30-day cost (highest first) linking to each use case. |
| **Use case detail** | The same **Cost** card (without the table) in the right-hand column next to **Use Case Information**. |

Until the first collection has run, the cards read *No cost data yet. Costs are collected once per day.* and the application cards show **—**.

### Reading the figures

- **Billed amount** (large figure): the share of the Cost Explorer bill allocated to this use case / application for the window. Summing all use cases of an application gives the application's figure; summing all applications plus the unassigned use cases gives the overall figure.
- **"$x.xx at list price"** (small text): the same usage priced at the public list price ($4.75 per Nova Act agent hour). It matters in accounts where the billed amount is $0 or discounted; for compute it is always $0.00 because MicroVM list prices depend on a VM size the collector does not know.
- **Windows**: *Last day* is yesterday (UTC); *Last 7 days* and *Last 30 days* end yesterday. Today is never included — a day is only billed once it is over.
- **Trend arrow and percentage**: the window compared with the window of the same length right before it (yesterday vs. the day before; last 7 days vs. the 7 days before; last 30 vs. the previous 30). Up (orange) means the cost rose by more than 5 %, down (green) means it fell by more than 5 %, a right arrow means it stayed within ±5 % — small changes are deliberately shown as unchanged so cents do not flap. No percentage next to the arrow means the previous window was $0.
- **"not enough data"**: a trend needs twice the window length in days. After deployment the 1-day trend appears on the second day, the 7-day trend after 14 days and the 30-day trend after 60 days.
- **Footer** *Source: Nova Act, Compute · Cost Explorer as of 2026-11-04 (estimated)*: which services are included, the newest day in the figures and whether Cost Explorer still marks any day in the 30-day window as estimated. Cost Explorer revises the last few days for up to about four days; the collector re-processes the last three days (configurable) every night, so yesterday's number can still move a little.
- **Bar chart**: one bar per day for the last 30 days, allocated bill; days Cost Explorer still marks as estimated are drawn in a lighter blue. Hover a bar for the exact amount.

### What is not shown per use case

Three amounts cannot be pinned to a use case and are kept out of the use-case and application figures so the sums stay honest. They are visible to operators in the daily ledger files (see [Troubleshooting → Cost allocation](./troubleshooting.md#cost-allocation)), not in the UI:

- **Unassigned**: use cases that do not belong to any application (counted in the overall total, in no application).
- **Unallocated**: usage of Nova Act workflow definitions that are not a use case any more, e.g. deleted use cases.
- **Unmetered**: bill without measured usage — rounding, executions that were still running when the bill was collected, or a cloud session that started a VM but never ran a test step.

### Who can see cost

No extra permission is needed. Whoever can view an application sees its cost (team members, viewers and anyone it is shared with); a use case's cost follows the use case's view permission. The overall total on the dashboard is shown to admins only. If you cannot view the application, the Cost tab's card simply does not render.

### Timing after deployment

Costs are collected once a day (06:00 UTC by default). The first numbers appear the morning after the deployment; there is no backfill of earlier days unless an operator runs one (see [Troubleshooting → Cost allocation](./troubleshooting.md#cost-allocation)). Trends follow the schedule above: 7-day trends after 14 days, 30-day trends after 60 days.

---

## Mobile Testing

QA Studio supports testing mobile applications on real devices via AWS Device Farm. Mobile tests use the same step-based approach as web tests, but run on physical Android or iOS devices instead of a browser.

> ⚠️ **Experimental:** Mobile support is currently experimental. Nova Act's model was trained on browser interactions, and its actuation stack is limited to browser primitives (click, type, scroll). For mobile tests, these actions are translated to Appium gestures on the device. This additional translation layer means mobile tests may be less reliable than web tests, and complex mobile-specific interactions (long-press, pinch-to-zoom, multi-touch) are not yet supported.

### Prerequisites

- An app binary (`.apk` for Android, `.ipa` for iOS) uploaded through the use case configuration
- AWS Device Farm access (Device Farm operates in `us-west-2` regardless of your deployment region)

### Creating a Mobile Use Case

1. Click **Create Use Case**, choose **Create new** and select **Mobile** as the test platform.
2. Fill in the basic info, then choose **Blank** or **User journey** as the creation method.
3. Choose the mobile platform: **Android** or **iOS**.
4. For Android, provide the **App package** (e.g., `com.example.myapp`) and **App activity** (e.g., `com.example.myapp.MainActivity`). For iOS, provide the **Bundle ID** (e.g., `com.example.myapp`).
5. Optionally select a specific **Device** from the dropdown. Devices are filtered by platform and show availability status. If left empty, the system auto-selects the newest available device.
6. Upload your app binary (`.apk` or `.ipa`).
7. Add test steps as you would for a web test.

### Device Selection

The device picker shows all Device Farm devices with remote access enabled, filtered by your selected platform. Each device shows:
- Device name and OS version
- Manufacturer and form factor
- Availability status (prefer "Highly available" devices for reliability)

You can search/filter the device list by typing in the dropdown.

### Running Mobile Tests

Mobile tests run the same way as web tests — click **Execute** or trigger via schedule/CLI. The key differences:
- No live browser view is available during execution (Device Farm doesn't support embeddable live streams)
- Session provisioning takes 1-2 minutes as Device Farm allocates a physical device
- The session recording is downloaded asynchronously after the test completes (typically available within 5-10 minutes)

### Mobile Recordings

Device Farm automatically records the device screen during test execution. After the session finalizes, the recording is downloaded and made available in the execution details under **Recording**. This process is asynchronous — the recording may not appear immediately after the test completes.

### Writing Steps for Mobile Tests

Mobile test steps use the same natural language format as web tests. Nova Act controls the device through Appium, so you can reference UI elements the same way.

> **Important:** Mobile test steps should use the same language as web tests. Use terms like "click", "select", and "scroll" rather than mobile-specific terms like "tap" or "swipe". Nova Act interprets web-style language and translates it to the appropriate mobile actions via Appium.

**Examples:**
- "Click the Login button" (not "Tap the Login button")
- "Enter 'JFK' in the search field"
- "Scroll down and select the first result" (not "Swipe up and tap the first result")
- "Close any pop-up dialogs"

### Limitations

- The Interactive Wizard is not available for mobile tests (it requires a live browser session)
- Step caching is not supported for mobile tests
- Live view during execution is not available
- Device Farm session provisioning can occasionally time out if the selected device is unavailable
- Steps should use web-style language (click, scroll, type), mobile-specific terms (tap, swipe) may not be reliably recognized by the model
- Complex mobile gestures (long-press, pinch-to-zoom, multi-touch) are not supported,  they have no browser-action equivalent

---

## Electron Testing

QA Studio can test Electron desktop applications. The test launches the real application (main process included — authentication, realtime connections and IPC all run as in production), attaches Nova Act to its window over the Chrome DevTools Protocol, executes the steps, and closes the app again.

Electron usecases run **only through the CI runner** (`qa-studio run`) on a machine that can show a window — a developer's Mac or a macOS CI host with a logged-in GUI session. The cloud worker has no display and cannot launch desktop apps, so the **Trigger Execution** button in the UI is disabled for them.

### Prerequisites

- A build of the application: a packaged `.app` bundle, or the bare `electron` binary plus the app directory
- `qa-studio[runner]` installed (`pip install -e ./qa-studio-cli[runner]`) with Nova Act credentials
- macOS host with a GUI session (CI runners must not be headless; `HEADLESS` has no effect)

### Creating an Electron Use Case

1. Click **Create Use Case**. In the wizard, choose **Create new** and select the **Electron** platform tile. The Starting URL and browser-policy fields disappear — the app decides what it opens.
2. Choose **Blank** or **User Journey** as the creation method (interactive wizard and templates need a cloud browser and are web-only).
3. Optionally enter the app's **Bundle ID** (`CFBundleIdentifier`, e.g. `com.example.desktop`). When set, the runner refuses to launch a packaged `.app` whose identifier differs, so a suite can never run against the wrong application. Unpackaged dev builds launched through the bare `electron` binary cannot be verified; the runner logs that and continues.
4. Add test steps as you would for a web test.

The use case list shows an **Electron** badge; the use case page shows "Execution: CI runner only".

### Running Electron Tests

```bash
# Packaged app, results recorded in QA Studio
qa-studio run --usecase-id <id> --app-path "/Applications/My App.app"

# Unpackaged build during development, no remote records
qa-studio run --usecase-id <id> --local-only \
  --app-path node_modules/electron/dist/Electron.app \
  --app-arg ./packages/app

# Reuse a pre-seeded profile (e.g. an already signed-in session)
qa-studio run --usecase-id <id> --app-path "/Applications/My App.app" \
  --app-user-data-dir ~/qa-profiles/my-app
```

What happens:
1. The runner launches the app with an ephemeral, loopback-only DevTools port and (by default) a fresh temporary `--user-data-dir`.
2. Nova Act attaches to the window the app opened.
3. Steps execute; step status and Nova Act traces are posted to QA Studio (unless `--local-only`).
4. The app is terminated and the temporary profile deleted.

### Writing Steps for Electron Tests

- `navigation`, `validation`, `assertion`, `secret`, `retrieve_value` and `transform` steps work as for web tests.
- `browser` steps support `reload`; `go_back`/`go_forward` depend on the app's own history.
- Avoid `url` steps: they navigate the app's window away from the application.
- Log in through the app's UI with `secret` steps, or supply a pre-seeded profile via `--app-user-data-dir`.

### Limitations

- No execution from the UI, schedules or suites triggered from the UI (CI runner only)
- No live view and no video recording (Nova Act cannot record video over CDP); per-step screenshots and action traces are captured
- Step caching / trajectory replay is disabled for Electron usecases
- The Interactive Wizard and browser recording are not available
- Nova Act attaches to the most recently opened window; apps that restore several windows from a persisted profile should be tested with a fresh profile

---

## Viewing Execution Results

When you click on an execution from the history, you'll see a detailed results page with:

### Execution Information
- Status, start time, completion time, and duration
- How it was triggered (manual or scheduled)
- The browser region where it ran

### Execution Timeline
A visual timeline showing when the execution moved through each phase (pending, executing, completed/failed).

### Live View
If a web test is currently running, a live view panel appears showing the browser session in real time. You can watch the AI navigate your application as it follows each step. Live view is not available for mobile tests.

### Step Results
A detailed breakdown of each step showing:
- Whether it passed or failed
- Screenshots captured during execution
- Logs from the browser session
- Any error messages if the step failed
- For steps inside a **Repeat**: a **Row i/n** badge, and a group row (**Repeat** badge, *&lt;label&gt; — row i of n*) before each row. A failed row stops the execution; later rows stay `pending` (fail-fast).
- Every `{{variable}}` in an instruction or validation value as a dark blue `VAR` badge with the value the run used. See [Variables in the Execution Steps table](#variables-in-the-execution-steps-table).

Click on screenshots or log files to view them in a full-screen modal.

### Session Recording
Click **View Recording** to watch a video replay of the entire session. For web tests, the recording is available immediately. For mobile tests, the Device Farm recording is downloaded asynchronously and typically becomes available within 5-10 minutes after the test completes.

### Downloaded Files
Any files downloaded during the test execution are listed here with links to download them.

### Stopping a Running Test
If a test is currently executing, you can click **Stop Execution** to terminate it. This stops the remote browser session and marks the execution as stopped.

---

## Test Suites

Test suites let you group multiple use cases together and run them as a batch. This is useful for regression testing, smoke tests, or any scenario where you want to run several tests at once.

### Viewing Test Suites

The Test Suites page shows all suites with:
- Name and description
- Tags
- Number of use cases in the suite
- Last run time and status (completed, partial, failed, never run)

Use the search bar to filter by name, description, or tags.

### Creating a Test Suite

1. Click **Create Test Suite**.
2. Enter a name, description, and optional tags.
3. Save the suite.
4. Add use cases to the suite from the suite detail page.

### Managing a Test Suite

From the suite detail page, you can:
- **Add use cases**: Browse and select existing use cases to include
- **Remove use cases**: Remove individual use cases from the suite
- **Edit** the suite name, description, and tags
- **Execute** the entire suite. All use cases run in parallel.
- **View execution history**: See results from previous suite runs

### Suite Execution Results

When you view a suite execution, you'll see:
- Overall status (completed, partial, failed)
- How many use cases succeeded, failed, or are still running
- Individual results for each use case with links to their detailed execution pages

### Scheduling a Test Suite

1. From the suite detail page, click **Configure Schedule**.
2. Choose a preset schedule or enter a custom cron expression.
3. Select your timezone.
4. Enable the schedule.

The suite will automatically run at the configured times. You can disable the schedule at any time without deleting it.

---

## Templates

Templates are reusable blueprints for creating use cases. They define a set of steps and variables that can be applied to create new use cases quickly.

### Viewing Templates

The Templates page shows all available templates with:
- Name and description
- Tags for categorization
- Who created it
- Version number

### Creating a Template

1. Click **Create Template**.
2. Enter a name, description, category, and optional tags.
3. Save the template.
4. Add steps to the template from the template detail page.

Template steps work the same as use case steps: plain language instructions that the AI browser will follow.

### Using a Template

When creating a new use case, choose **Create new**, then **Template** as the creation method:
1. Browse the template library and select a template.
2. The template's steps are copied into your new use case — including browser actions, transform arguments, date formats and network assertion settings.
3. Customize the steps, variables, and configuration for your specific scenario.

You can also insert a template into an existing use case: open the use case, click **Import Template**, pick the template and the position. Inserted steps remember which template (and template version) they came from.

**Secret steps.** If the template contains secret steps (for example `username` and `password` for a login template), the template form shows one password field per secret. Values you enter are stored in AWS Secrets Manager as soon as the use case is created or the template is inserted — the same way the JSON import asks for its secrets. Fields you leave empty can be set later in the use case's **Secrets** tab; until then a run fails at that step with "secret not found". When inserting into an existing use case, secrets it already has are not asked for again.

**Positioning.** "Import Template" inserts the template's steps as a block at the chosen position and renumbers all steps `1..n` afterwards, so step numbers stay contiguous even if the use case had gaps before.

### Templates from the CLI and from agents

One login definition, many tests: instead of re-typing the same sign-in steps in every test JSON, a test references the template and the cloud expands it at import time. Template UUIDs belong to one QA Studio environment (dev, prod, …) — a test JSON that references a dev template must point at the corresponding prod template before it is imported there.

```bash
# What templates exist, and what does one need?
qa-studio templates list
qa-studio templates get <template-id>        # steps, variables, "Required secrets: shop_username, shop_password"

# Reference it from a test JSON: { "sort": 1, "step_type": "template", "template_id": "<template-id>" }
qa-studio tests import ./tests/checkout.json --dry-run   # checks the template exists, lists all required secrets
qa-studio tests import ./tests/checkout.json             # prompts for the template's secrets as well

# No fitting template yet? Create one from a file.
qa-studio templates create ./templates/login-shop.json   # → ✓ Template created: Login – Shop (ID: …)

# Add a template to a test that already exists in the cloud
qa-studio tests insert-template <usecase-id> --template-id <template-id> --position 2

# Change an existing template — never recreate it (the UUID would change and every reference breaks)
qa-studio templates export <template-id> --output ./templates/login-shop.json   # steps carry their "id"
#   … edit the file: fix an instruction, add a step (no "id"), remove a step …
qa-studio templates update <template-id> ./templates/login-shop.json --dry-run  # Plan: 4 steps updated, 1 created, 0 deleted; …
qa-studio templates update <template-id> ./templates/login-shop.json            # ✓ Template updated: Login – Shop (version 7; …)

# Delete a throwaway template — tests that used it keep their steps, only the template link is removed
qa-studio templates delete <template-id>          # prompts: Template "…" is used by 2 tests (…). Delete? [y/N]
qa-studio templates delete <template-id> --yes    # scripts / CI
```

Expanded steps remember their template, so editing the template later shows the familiar "update available" hint on those steps. Templates cannot contain other templates or repeat steps. The `qa-studio` agent skill checks `templates list` before hand-authoring login or setup steps and creates a template when the same sequence appears in two or more tests. Full option tables: [CLI README → Templates](../qa-studio-cli/README.md#templates).

Exported template files have one optional field per step beyond the normal step fields: `steps[].id`, the template step id. `templates update` matches steps on it (updated in place → linked tests get the "update available" hint), creates steps without an `id`, and deletes template steps missing from the file. Keep the ids when editing.

**Deleting a template** (CLI or web UI) keeps every test that imported it intact: the steps stay as they are and only lose their link to the template (no more "From template" / "update available"). The web UI's delete dialog and `templates get` / `templates delete` list the affected tests beforehand ("Used by N tests: …").

**Event messages:** none — every template operation is a synchronous API call.

**Template updates.** Every change to a template (its details, or adding, editing, reordering or deleting a step) raises the template's version. Steps that were inserted from an older version show the template differences in the step editor together with an **Update from Template** button, which replaces the step's instruction and settings with the template's current ones.

### Managing Templates

From the template detail page, you can:
- Edit the template name, description, and tags
- Add, edit, reorder, and delete steps
- Delete the template — the dialog lists the tests that use it (`"Login" is used by 2 tests: Checkout, Refund`) and reminds you that their steps are kept; only the template link is removed. From the Templates library several templates can be deleted at once; the dialog shows the usages of each.

**Limitation:** Repeat steps (data-driven loops) are not supported in templates in this version. The template step form does not offer the Repeat type, and the API rejects `step_type: "repeat"` or a `parent_step_id` on template steps with `400 "repeat steps are not supported in templates"`. Add repeats directly in the use case after applying the template.

---

## Writing Good Test Steps

The quality of your test steps directly affects how reliably your tests run. For detailed guidance on step types, structuring steps, and a quick reference, see [Prompting Best Practices](prompting-best-practices.md).

---

## Step Caching (Trajectory Replay)

Step caching makes repeat runs faster by replaying what Nova Act did last time instead of asking the model again.

### How It Works

1. **First run**: a navigation step runs through Nova Act as usual. When it succeeds, the runner records the
   step's **trajectory** (the browser actions Nova Act took) and uploads it; the step gets a `trajectory_s3_key`
   and `trajectory_last_updated`.
2. **Later runs**: the runner downloads the trajectory and replays it without calling the model.
3. **Automatic fallback**: if the replay fails (for example the page changed), the step runs through Nova Act
   again and the stale trajectory is cleared, so a fresh one is recorded on success.

### Which Steps Are Cached?

Only **navigation steps** record and replay trajectories (clicks, typing, hovering, scrolling). Validation,
assertion, retrieve-value and the other step types always run normally because they must read the current page.
Steps inside a `repeat` and Electron use cases do not use replay.

### Turning It On and Off

Replay is done by the runner (`qa-studio run`, also in the cloud worker). It is on by default when the installed
Nova Act SDK supports `replayable`; set `ENABLE_TRAJECTORY_REPLAY=false` to switch it off for a run. The
**Step caching** toggle in the creation wizard is stored on the use case and copied to its executions.

### The "Cached" Badge

On the use case's **Workflow Steps** tab the card of a navigation step shows a green **Cached** badge next to its
step type badge when it has a recorded trajectory: *this step will replay from a recorded trajectory*. The card's
details end with **Cached &lt;time ago&gt;**, when the trajectory was recorded: `Cached just now`, `Cached 5m ago`,
`Cached 3h ago`, `Cached 2d ago`, and the date from 7 days on. Steps without a trajectory and non-navigation steps
show no badge. (Older bbox-cache data —
`cached_steps` — no longer produces the badge; nothing writes it any more.)

### Cache Invalidation

All trajectories of a use case (and so every badge) are cleared when:
- an execution of the use case **fails** (the next run starts from a clean slate), or
- the use case's **Step caching** setting is switched from on to off.

A trajectory whose replay fails is cleared for that step alone. The next successful run records new ones.

### Troubleshooting

**No badge after a successful run**:
- Only navigation steps get one.
- Check the run's log for `Trajectory upload failed` — the recording could not be stored.
- Check that `ENABLE_TRAJECTORY_REPLAY` is not `false` for the runner.

**A cached step keeps falling back to Nova Act**:
- The page has changed since the trajectory was recorded; the next successful run replaces it.

Trajectory replay internals are described in [Trajectory Replay](design/trajectory-replay.md).

---

## User Management (Admin Only)

Admins manage users under **Administration → Users** (`/admin/users`). Roles and teams are described in
[User Management](user-management.md).

### Viewing Users

The table shows each user's email, team(s) and role. Filter by email, team (including *Administrators* and
*Unassigned*) or role.

### Creating a User

1. Click **Create User**.
2. Enter the email address and, optionally, a team and role.
3. Click **Create**. The user receives a temporary password by email and changes it on first login.

### Editing a User

Click **Edit** next to the user to change their team and role.

### Deleting a User

Click **Delete** next to the user and confirm. The user is removed from Cognito **and from every team**, and the
deletion is written to the audit log. The last administrator cannot be deleted. This cannot be undone.

---

## OAuth Client Management (Admin Only)

OAuth clients allow external applications and CI/CD pipelines to interact with QA Studio's API programmatically, without a human logging in through the web interface.

### Viewing OAuth Clients

The OAuth Clients page shows all registered clients with:
- Client name and ID
- Status (Enabled/Disabled)
- When it was created and by whom

### Creating an OAuth Client

1. Click **Create OAuth Client**.
2. Enter a name for the client.
3. Select which API scopes (permissions) the client should have.
4. Click Create.

You'll receive a client ID and client secret. **Save the client secret immediately.** It is only shown once and cannot be retrieved later.

### Deleting an OAuth Client

Click the delete icon next to a client and confirm. This immediately revokes access for any application using that client's credentials.

---

## Tips and Tricks

- **Batch operations**: Select multiple use cases on the home screen to execute or delete them all at once.
- **Search everywhere**: Use the search/filter bars on the Use Cases, Test Suites, and Templates pages to quickly find what you need.
- **Watch recordings**: When a test fails, the session recording is the fastest way to understand what went wrong.
- **Use the live view**: For tests that are currently running, the live view lets you watch the browser in real time.
- **Clone before editing**: If you want to experiment with changes to a test, clone it first so you always have the original.
- **Tag consistently**: Use consistent tags across use cases and suites to make filtering easier.
- **Schedule off-hours**: Schedule regression suites to run overnight or on weekends so results are ready when you start work.
- **Export regularly**: Export important use cases as JSON backups, especially before making significant changes.
