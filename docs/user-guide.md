# QA Studio User Guide

This guide walks you through every feature of the QA Studio web interface.

## Table of Contents

- [Getting Started](#getting-started)
- [Use Cases](#use-cases)
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

Click **Create Use Case** to see six creation options:

#### Interactive Wizard
Build your test step-by-step with a live browser. You enter a step, watch it execute in real time, and accept it when it looks right. This is the most hands-on way to build a test.

1. Enter a name, description, and the starting URL of the website you want to test.
2. Select a browser region (where the remote browser runs).
3. Click **Start Wizard** to launch a live browser session.
4. Type a step instruction (e.g., "Click the Login button"), then watch the browser perform it.
5. If the step looks correct, accept it. If not, modify and retry.
6. Repeat until your test is complete, then finish the wizard.

#### Create Blank
Start from scratch. You provide a name, starting URL, and description, then manually add steps afterward.

#### Start from Template
Pick a pre-built template from the template library. Templates come with predefined steps and variables that you can customize for your specific scenario.

#### Create from User Journey
Describe what you want to test in plain English, and AI generates the test steps for you. For example:

> "Log in to the application, navigate to the settings page, change the display name, and verify the change was saved."

You provide a title, starting URL, and your description. The system generates a complete use case that you can review and edit before saving.

#### Clone from Use Case
Duplicate an existing use case. Useful when you want a variation of a test you've already built.

#### Import Use Case
Upload a previously exported JSON file to recreate a use case. Useful for sharing tests between environments or team members.

### Inside a Use Case

When you open a use case, you'll see its details organized into tabs:

#### Execution History
A list of every time this test has been run, showing:
- Status (pending, executing, completed, failed, stopped)
- When it started and finished
- How it was triggered (manual or scheduled)
- A link to view full execution details

Click **Execute** to run the test immediately.

#### Workflow Steps
The ordered list of instructions the AI browser will follow. Each step has:
- A sort order (the sequence)
- The instruction text (what to do)
- An optional secret reference (for sensitive data like passwords)

You can add, edit, reorder, and delete steps here.

**Types of steps:**
- **Navigation**: Plain language instructions like "Click the Submit button" or "Navigate to the Dashboard page". This is the default step type.
- **Validation**: Reads a value from the live page and compares it against an expected value. Supports `string`, `bool`, and `number` types with operators like `exact`, `contains`, `not_equal`, `greater_then`, `less_then`, etc. The instruction should describe what value to retrieve (e.g., "return the text of the welcome banner").
- **Secret**: Steps that reference a stored secret. The action describes what to do (e.g., "Type the password in the password field") and the secret provides the sensitive value at runtime. The secret value never appears in logs.
- **Retrieve Value**: Extracts a value from the page and stores it as a runtime variable for use in later steps. You specify a variable name and a value type (`string`, `number`, or `bool`). The captured value can be referenced in subsequent steps using `{{VariableName}}` template syntax.
- **Assertion**: Compares a previously captured runtime variable against an expected value. Does not interact with the browser. Use this after a Retrieve Value step to verify the captured data matches expectations. Supports the same type and operator combinations as Validation.
- **URL**: Navigates the browser directly to a specific URL. The instruction is the URL itself.
- **Download**: Downloads a file from the page and uploads it to S3 for later retrieval.

#### Schedule
Set up automatic recurring runs. You can:
- Choose from preset schedules (daily, weekdays, weekly, hourly, etc.)
- Enter a custom cron expression for advanced scheduling
- Select a timezone
- Enable or disable the schedule

#### Variables
Define key-value pairs that can be referenced in your test steps. Variables make tests reusable across different environments or configurations (e.g., different URLs, usernames, or settings).

#### Secrets
Store sensitive values like passwords, API keys, or tokens. Secrets are:
- Encrypted and stored securely
- Never shown in logs or execution history
- Referenced by name in secure steps

To add a secret, provide a key name and the secret value. You can delete secrets you no longer need.

#### Headers
Configure custom HTTP headers that should be sent with requests during test execution. Useful for authentication tokens, custom identifiers, or API keys that your application requires.

#### Hooks
Set up scripts that run before or after test execution:
- **Before script**: Runs before the test starts (e.g., set up test data)
- **After script**: Runs after the test completes (e.g., clean up resources)

### Exporting a Use Case

From the use case detail page, you can export the use case as a JSON file. This file contains all steps, configuration, and metadata (secrets are excluded for security). Use this to share tests with colleagues or back them up.

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
If a test is currently running, a live view panel appears showing the browser session in real time. You can watch the AI navigate your application as it follows each step.

### Step Results
A detailed breakdown of each step showing:
- Whether it passed or failed
- Screenshots captured during execution
- Logs from the browser session
- Any error messages if the step failed

Click on screenshots or log files to view them in a full-screen modal.

### Session Recording
Click **View Recording** to watch a video replay of the entire browser session. The recording player lets you scrub through the session to see exactly what happened at each point.

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

When creating a new use case, choose **Start from Template**:
1. Browse the template library and select a template.
2. The template's steps are copied into your new use case.
3. Customize the steps, variables, and configuration for your specific scenario.

### Managing Templates

From the template detail page, you can:
- Edit the template name, description, and tags
- Add, edit, reorder, and delete steps
- Delete the template

---

## Writing Good Test Steps

The quality of your test steps directly affects how reliably your tests run. For detailed guidance on step types, structuring steps, and a quick reference, see [Prompting Best Practices](prompting-best-practices.md).

---

## User Management (Admin Only)

If you have admin access, the Users section lets you manage who can access QA Studio.

### Viewing Users

The Users page shows all registered users with:
- Email address
- Group memberships (which determine permissions)
- Account status (Active, Unconfirmed, Password Change Required, Disabled)
- When the account was created

### Creating a User

1. Click **Create User**.
2. Enter the new user's email address.
3. Select which groups to add them to (groups control what they can access).
4. Click Create.

The new user will receive a temporary password via email and must change it on first login.

### Deleting a User

Click the Delete button next to a user and confirm. This permanently removes their access. This action cannot be undone.

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
