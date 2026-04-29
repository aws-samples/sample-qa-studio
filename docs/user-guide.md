# QA Studio User Guide

This guide walks you through every feature of the QA Studio web interface.

## Table of Contents

- [Getting Started](#getting-started)
- [Use Cases](#use-cases)
- [Mobile Testing](#mobile-testing)
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
Build your test step-by-step with a live browser. This option is only available for web tests. You enter a step, watch it execute in real time, and accept it when it looks right.

1. Enter a name, description, and the starting URL of the website you want to test.
2. Select a browser region (where the remote browser runs).
3. Click **Start Wizard** to launch a live browser session.
4. Type a step instruction (e.g., "Click the Login button"), then watch the browser perform it.
5. If the step looks correct, accept it. If not, modify and retry.
6. Repeat until your test is complete, then finish the wizard.

#### Create Blank
Start from scratch. Choose between **Web** or **Mobile** as the test platform. For web tests, provide a starting URL. For mobile tests, select the mobile platform (Android or iOS), provide app identifiers, choose a Device Farm device, and upload your app binary. Optionally upload a browser policy to control permission dialogs. Then manually add steps afterward.

#### Start from Template
Pick a pre-built template from the template library. Templates come with predefined steps and variables that you can customize for your specific scenario.

#### Create from User Journey
Describe what you want to test in plain English, and AI generates the test steps for you. You can choose between Web and Mobile platforms. For example:

> "Log in to the application, navigate to the settings page, change the display name, and verify the change was saved."

You provide a title, starting URL (for web) or app identifiers (for mobile), and your description. The system generates a complete use case that you can review and edit before saving.

Optionally, you can start a browser recording session to capture your interactions with the target application. The recording is sent alongside your text description to produce more accurate test steps. During recording, you can use Ctrl+C to extract a value into a variable and Ctrl+V to paste it elsewhere — the generated test case will automatically include the correct `retrieve_value` and variable-referencing steps. See [Prompting Best Practices](prompting-best-practices.md#browser-recording-with-variable-capture) for details.

#### Clone from Use Case
Duplicate an existing use case, including all mobile configuration if applicable. Useful when you want a variation of a test you've already built.

#### Import Use Case
Upload a previously exported JSON file to recreate a use case, including mobile configuration. Useful for sharing tests between environments or team members. Note that app binaries are not included in exports and must be re-uploaded after import.

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
- **URL**: Navigates the browser directly to a specific URL. The instruction is the URL itself. ⚠️ *Deprecated — use Browser → Navigate instead. Existing URL steps continue to work.*
- **Browser**: Performs browser-level actions without interacting with page elements. Choose an action: **Reload** (optionally hard reload to bypass cache), **Back** (navigate back in history), **Forward** (navigate forward in history), or **Navigate** (go to a specific URL). This replaces the URL step type for new tests.
- **Transform**: Computes or manipulates a value using a built-in operation and stores the result in a variable. Supports 19 operations: math, round, floor, ceil, abs, min, max, concat, upper, lower, trim, replace, substring, length, to_number, to_string, to_int, regex_extract, and format. Always requires a capture variable for the output.
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
qa-studio tests import ./login_test.json

# Import all JSON files from a folder (recursive)
qa-studio tests import ./testcases/ --yes

# Validate files without importing (dry-run)
qa-studio tests import ./testcases/ --dry-run

# Override the starting URL for a different environment
qa-studio tests import ./testcases/ --base-url https://staging.example.com --yes

# CI pipeline usage: JSON output, no prompts
qa-studio tests import ./testcases/ --format json --skip-secrets
```

The import follows a two-phase flow:

1. **Scan & Validate** — All JSON files are discovered and validated against the export schema. A summary table shows which files are valid.
2. **Import** — After confirmation, valid files are sent to the API. If any file contains secrets, you'll be prompted to enter values (use `--skip-secrets` to configure them later in the UI).

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `path` | positional | required | File or directory path to import |
| `--dry-run` | flag | `false` | Validate only, do not import |
| `--yes` / `-y` | flag | `false` | Skip confirmation prompt |
| `--base-url` | string | `None` | Override `starting_url` for all imports |
| `--skip-secrets` | flag | `false` | Skip interactive secret prompts |
| `--format` | choice | `human` | Output format: `human` or `json` |

See the [CLI README](../qa-studio-cli/README.md#importing-test-cases) for the full reference.

---

## Mobile Testing

QA Studio supports testing mobile applications on real devices via AWS Device Farm. Mobile tests use the same step-based approach as web tests, but run on physical Android or iOS devices instead of a browser.

> ⚠️ **Experimental:** Mobile support is currently experimental. Nova Act's model was trained on browser interactions, and its actuation stack is limited to browser primitives (click, type, scroll). For mobile tests, these actions are translated to Appium gestures on the device. This additional translation layer means mobile tests may be less reliable than web tests, and complex mobile-specific interactions (long-press, pinch-to-zoom, multi-touch) are not yet supported.

### Prerequisites

- An app binary (`.apk` for Android, `.ipa` for iOS) uploaded through the use case configuration
- AWS Device Farm access (Device Farm operates in `us-west-2` regardless of your deployment region)

### Creating a Mobile Use Case

1. Click **Create Use Case** and choose **Create Blank** or **Create from User Journey**.
2. Select **Mobile** as the test platform.
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

## Step Caching

Step caching is a performance optimization feature that reduces test execution time by 40-60%. When enabled, QA Studio caches the browser actions from successful test executions and replays them directly using Playwright API instead of calling Nova Act for every execution.

### How It Works

1. **First Execution**: Your test runs normally using Nova Act. After successful completion, the system automatically analyzes the Nova Act responses and builds a cache of the browser actions (clicks, typing, navigation, etc.).

2. **Subsequent Executions**: When you run the test again, cached navigation steps execute directly using Playwright, bypassing Nova Act entirely. This eliminates AI inference latency (typically 2-5 seconds per step).

3. **Automatic Fallback**: If a cached step fails (e.g., the page changed), the system automatically falls back to Nova Act, ensuring your tests remain reliable.

### Benefits

- **40-60% faster execution**: Cached steps execute in 200-400ms vs 2-5 seconds with Nova Act
- **Cost savings**: Reduced Nova Act API calls
- **Same reliability**: Automatic fallback ensures tests don't break
- **Zero maintenance**: Cache updates automatically when steps change

### Which Steps Are Cached?

Only **navigation steps** are cacheable. These include:
- Clicking buttons and links
- Typing text into fields
- Hovering over elements
- Scrolling
- Navigating to URLs

Other step types (validation, assertion, retrieve value) always execute normally since they need to read current page state.

### Enabling Cache for New Use Cases

When creating a new use case:

1. Fill in the use case details (name, URL, description)
2. Look for the **"Enable Step Caching"** toggle
3. Enable the toggle
4. Complete use case creation as normal

![Cache toggle in use case creation form](images/cache-toggle-creation.png)

### Enabling Cache for Existing Use Cases

To enable caching on an existing use case:

1. Open the use case in the UI
2. Click the **Settings** or **Edit** button
3. Find the **"Enable Step Caching"** toggle
4. Enable the toggle
5. Click **Save**

![Cache toggle in use case settings](images/cache-toggle-settings.png)

The cache will build automatically after the next successful execution.

### Understanding Cache Status

In the step list, you'll see cache indicators:

- **Green cache icon**: Step has cached actions available
- **Gray cache icon**: Step is cacheable but no cache yet
- **No icon**: Step type is not cacheable

![Cache indicators in step list](images/cache-indicators-steps.png)

In execution logs, you'll see messages like:
- `Cache hit for step 3 (executed in 250ms)` - Step used cache
- `Cache miss for step 3: no cached steps available` - First execution, cache building
- `Cache execution failed for step 3: ..., falling back to Nova Act` - Cache failed, used fallback

![Cache status in execution logs](images/cache-execution-logs.png)

### When Cache Is Built

Cache builds automatically after **successful test execution**. The process is asynchronous and typically completes within 30 seconds. You don't need to do anything - just run your test again and the cache will be used.

### Cache Invalidation

Cache automatically invalidates when:
- You change the step instruction
- You reorder steps
- You delete and recreate a step

The system detects these changes and rebuilds the cache on the next successful execution.

### Troubleshooting

**Cache not building after execution**:
- Verify the execution completed successfully (failed executions don't build cache)
- Check that caching is enabled in use case settings
- Wait 30-60 seconds for asynchronous cache building to complete

**Cache execution fails repeatedly**:
- The page may have changed since cache was built
- Disable cache temporarily to verify test works with Nova Act
- If test works without cache, the cache will rebuild on next successful execution

**Test slower with cache enabled**:
- First execution is always slower (cache building overhead)
- Subsequent executions should be 40-60% faster
- Check execution logs to verify cache hits

For more troubleshooting guidance, see [Troubleshooting Guide](troubleshooting.md#step-cache-troubleshooting).

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
