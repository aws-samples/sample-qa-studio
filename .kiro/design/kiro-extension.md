# Kiro IDE Extension - Product Design Document

## Overview

Bring QA Studio test creation and execution capabilities directly into the Kiro IDE development workflow, enabling the Kiro AI agent to autonomously create, manage, and execute UI tests during development.

## Problem Statement

Developers currently must:
1. Switch context from IDE to QA Studio web interface to create tests
2. Manually create test cases after writing code
3. Wait for CI/CD to discover issues that could be caught during development

**Goal:** Enable Kiro agent to create and execute tests as part of the development process, catching issues before commit.

## User Personas

### Primary: Developer using Kiro IDE
- Writes application code
- Wants automated test coverage without context switching
- Needs immediate feedback on code changes

### Secondary: Kiro AI Agent
- Analyzes code changes
- Creates appropriate test cases
- Executes tests and reports results

## Core Capabilities

### 1. Authentication
**User Action:** Run "QA Studio: Login" command in IDE
**Flow:**
- Opens Cognito hosted UI in browser
- User authenticates with existing QA Studio credentials
- Extension stores token securely
- MCP server gains access to QA Studio API

**Technical:**
- OAuth 2.0 with Cognito
- Token stored in VS Code secrets API
- Shared with MCP via file (`~/.qa-studio-token`)

### 2. Test Case Management

**Kiro Agent Actions:**

**Creating Tests (Two Approaches):**

**A. AI-Generated (Recommended):**
```
Developer: "Create a test for the login flow"
Kiro: [writes user journey description]
→ Calls generate_usecase_from_journey with:
  - userJourney: "User navigates to login page, enters credentials, clicks login, verifies dashboard loads"
  - startUrl: "https://app.com/login"
→ Platform uses Bedrock to generate complete test with steps
→ Returns complete test case
→ "Created login test with 4 steps"
```

**B. Manual Step-by-Step:**
```
Developer: "Create a blank test for checkout"
Kiro:
→ Calls create_usecase(name="Checkout Flow", startUrl="https://app.com/cart")
→ Calls create_step(instruction="Click checkout button")
→ Calls create_step(instruction="Enter shipping address")
→ "Created checkout test with 2 steps"
```

**Managing Tests:**
- `list_usecases` - Browse available tests
- `get_usecase` - View test details
- `update_usecase` - Modify test properties (name, startUrl, description)
- `delete_usecase` - Remove test
- `clone_usecase` - Duplicate existing test

**Managing Steps:**
- `list_steps` - View steps in a test
- `create_step` - Add step to test
- `update_step` - Modify step instruction
- `delete_step` - Remove step
- `reorder_steps` - Change step order

**Executing Tests:**
- `execute_usecase_local` - Run test locally with optional baseUrl override

**Why use generate_usecase?**
- Leverages existing Bedrock integration
- No duplicate AI logic
- Proven to work in web UI
- Generates complete, valid test structure
- Kiro just needs to write good user journey descriptions

### 3. Local Test Execution
**Kiro Agent Actions:**
- `execute_usecase_local` - Run single test case locally

**Implementation:**
- Extension bundles CI/CD runner (Python package)
- Runner extended to support single use case execution
- `--local-only` flag reads directly from use case definition
- `--base-url` flag overrides starting URL for local testing
- `--var` flag overrides variables (repeatable)
- Executes using local Nova Act SDK + AWS credentials
- Artifacts stored locally, paths returned to agent

**Flow:**
1. Agent calls execute_usecase_local with optional baseUrl and variables
2. MCP spawns CI/CD runner: `cicd-runner --usecase-id <id> --local-only [--base-url <url>] [--var key=value]`
3. Runner authenticates with OAuth (using extension token)
4. Runner fetches use case definition:
   - `GET /usecase/{id}` - Get use case (name, startUrl)
   - `GET /usecase/{id}/steps` - Get steps to execute
   - `GET /usecase/{id}/variables` - Get variables (merged with overrides)
   - `GET /usecase/{id}/secrets` - Get secrets (from platform)
5. Runner overrides startUrl with baseUrl if provided
6. Runner merges variable overrides with use case variables
7. Runner executes using Nova Act SDK with merged configuration
8. Runner stores artifacts locally (/tmp/qa-studio-artifacts/)
9. Returns JSON with results and local artifact paths
10. Agent shows results to developer

**Use cases for overrides:**

**Base URL:**
- Test against localhost: `baseUrl: "http://localhost:3000"`
- Test against staging: `baseUrl: "https://staging.example.com"`
- Test against feature branch: `baseUrl: "https://feature-123.preview.example.com"`

**Variables:**
- Override test data: `variables: { username: "testuser", environment: "local" }`
- Change configuration: `variables: { timeout: "30", retries: "3" }`
- Test different scenarios: `variables: { userType: "admin" }`

**Secrets:**
- Secrets are always fetched from platform (secure, not overridable via CLI)
- Use case must have secrets configured in platform

**Example:**
```
Developer: "Test the login flow against my local server with a test user"
Kiro:
→ Calls execute_usecase_local(
    usecaseId="login-test",
    baseUrl="http://localhost:3000",
    variables={ username: "testuser", environment: "local" }
  )
→ Runner executes: cicd-runner --usecase-id login-test --local-only --base-url http://localhost:3000 --var username=testuser --var environment=local
→ "Test passed! Login works on localhost with testuser"
```

**Key difference from normal execution:**
- **Local-only:** Reads use case definition directly, no `/execute` call, no execution records
- **Normal:** Calls `POST /usecase/{id}/execute`, creates execution records, uploads artifacts

**Local artifacts:**
- Screenshots: `/tmp/qa-studio-artifacts/<usecase-id>/step-<n>-screenshot.png`
- Video: `/tmp/qa-studio-artifacts/<usecase-id>/recording.webm`
- Logs: `/tmp/qa-studio-artifacts/<usecase-id>/execution.log`

**Requirements:**
- Python 3.11+ installed
- AWS credentials configured
- CI/CD runner bundled with extension

### 4. Test Suite Management
**Kiro Agent Actions:**
- `create_test_suite` - Group related tests
- `add_tests_to_suite` - Build suite
- `execute_test_suite` - Run all tests in suite

## Architecture

### Components

```
┌─────────────────────────────────────────┐
│         Kiro IDE (VS Code)              │
│  ┌───────────────────────────────────┐  │
│  │  Extension                        │  │
│  │  - Cognito OAuth                  │  │
│  │  - Login UI Command               │  │
│  │  - Token Management               │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  MCP Server (embedded)            │  │
│  │  - Reads shared token             │  │
│  │  - Exposes tools to Kiro agent    │  │
│  │  - Calls QA Studio API            │  │
│  │  - Executes tests locally         │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
                    ↓
        ┌───────────────────────┐
        │  QA Studio REST API   │
        │  (existing)           │
        └───────────────────────┘
```

### Data Flow

**Authentication:**
```
User → Extension → Cognito → Token → File → MCP Server
```

**Test Creation:**
```
Kiro Agent → MCP Tool → QA Studio API → DynamoDB
```

**Test Execution:**
```
Kiro Agent → MCP Tool → Download Test → Local Python → Nova Act → Results
```

## MCP Tools Specification

### Use Cases (Test Cases)

```typescript
{
  name: "generate_usecase_from_journey",
  description: "Generate complete test case from natural language user journey description (uses Bedrock AI)",
  inputSchema: {
    title: string,
    startingUrl: string,
    userJourney: string,
    region: "us-east-1" | "us-west-2" | "ap-southeast-2" | "eu-central-1"
  }
}

{
  name: "list_usecases",
  description: "List all test cases",
  inputSchema: {}
}

{
  name: "get_usecase",
  description: "Get test case details",
  inputSchema: { usecaseId: string }
}

{
  name: "create_usecase",
  description: "Create blank test case (for manual step-by-step creation)",
  inputSchema: {
    name: string,
    starting_url: string,
    description?: string,
    active?: boolean,
    tags?: string[],
    executing_region?: string,  // Defaults to us-east-1
    model_id?: string  // Defaults to nova-act-v1.0
  }
}

{
  name: "update_usecase",
  description: "Update test case (all fields required)",
  inputSchema: {
    usecaseId: string,
    name: string,
    description: string,
    starting_url: string,
    active: boolean,
    executing_region: string,
    model_id: string,
    tags: string[]
  }
}

{
  name: "delete_usecase",
  description: "Delete test case",
  inputSchema: { usecaseId: string }
}

{
  name: "clone_usecase",
  description: "Clone existing test case",
  inputSchema: {
    usecaseId: string,
    name: string  // Name for the cloned use case
  }
}

{
  name: "get_usecase_variables",
  description: "Get use case variables",
  inputSchema: { usecaseId: string }
}

{
  name: "create_usecase_variables",
  description: "Create/update use case variables",
  inputSchema: {
    usecaseId: string,
    variables: Array<{ key: string, value: string, description?: string }>
  }
}

{
  name: "get_usecase_secrets",
  description: "Get use case secrets (values not included)",
  inputSchema: { usecaseId: string }
}

{
  name: "create_usecase_secrets",
  description: "Create/update use case secrets",
  inputSchema: {
    usecaseId: string,
    secrets: Array<{ key: string, value: string, description?: string }>
  }
}

{
  name: "delete_usecase_secrets",
  description: "Delete use case secret",
  inputSchema: {
    usecaseId: string,
    secretKey: string
  }
}
```

### Steps

```typescript
{
  name: "list_steps",
  description: "List steps in test case",
  inputSchema: { usecaseId: string }
}

{
  name: "create_step",
  description: "Add step to test case",
  inputSchema: {
    usecaseId: string,
    instruction: string,  // Not required for assertion steps
    step_type: "navigation" | "validation" | "secret" | "retrieve_value" | "assertion" | "url" | "download",
    
    // Common optional fields
    secret_key?: string,              // Required for secret steps
    capture_variable?: string,        // Required for retrieve_value steps
    value_type?: string,              // Required for retrieve_value steps: "string" | "number" | "bool"
    validation_type?: string,         // Required for validation/assertion steps: "string" | "number" | "bool"
    validation_operator?: string,     // Required for validation/assertion steps
    validation_value?: string,        // Required for validation/assertion steps
    assertion_variable?: string,      // Required for assertion steps
    enable_advanced_click_types?: boolean  // Optional for navigation steps
  }
}

// Step type requirements:
// - navigation: instruction
// - url: instruction (must be valid URL)
// - secret: instruction, secret_key
// - validation: instruction, validation_type, validation_operator, validation_value
// - retrieve_value: instruction, capture_variable, value_type
// - assertion: assertion_variable, validation_type, validation_operator, validation_value (no instruction)
// - download: instruction

// Validation operators by type:
// - string: exact, exact_case_insensitive, contains, contains_case_insensitive, not_equal
// - number: equals, less_then, greater_then, greater_or_equal_then, less_or_equal_then
// - bool: exact (validation_value must be "true" or "false")

{
  name: "update_step",
  description: "Update test step",
  inputSchema: {
    usecaseId: string,
    stepId: string,
    instruction?: string,
    step_type?: string,
    secret_key?: string,
    capture_variable?: string,
    value_type?: string,
    validation_type?: string,
    validation_operator?: string,
    validation_value?: string,
    assertion_variable?: string,
    enable_advanced_click_types?: boolean
  }
}

{
  name: "delete_step",
  description: "Delete test step",
  inputSchema: {
    usecaseId: string,
    stepId: string
  }
}

{
  name: "reorder_steps",
  description: "Reorder test steps",
  inputSchema: {
    usecaseId: string,
    step_orders: Array<{ step_id: string, sort: number }>
  }
}
```

### Execution

```typescript
{
  name: "execute_usecase_local",
  description: "Execute test case locally (no execution record, artifacts stored locally). Use baseUrl to test against localhost or staging environments.",
  inputSchema: {
    usecaseId: string,
    baseUrl?: string,  // Override starting URL (e.g., "http://localhost:3000")
    variables?: Record<string, string>
  }
}
```

### Test Suites

```typescript
{
  name: "list_test_suites",
  description: "List all test suites",
  inputSchema: {}
}

{
  name: "get_test_suite",
  description: "Get test suite details",
  inputSchema: { suiteId: string }
}

{
  name: "create_test_suite",
  description: "Create test suite",
  inputSchema: {
    name: string,
    description?: string
  }
}

{
  name: "update_test_suite",
  description: "Update test suite",
  inputSchema: {
    suiteId: string,
    name?: string,
    description?: string
  }
}

{
  name: "delete_test_suite",
  description: "Delete test suite",
  inputSchema: { suiteId: string }
}

{
  name: "add_usecases_to_suite",
  description: "Add test cases to suite",
  inputSchema: {
    suiteId: string,
    usecaseIds: string[]
  }
}

{
  name: "remove_usecase_from_suite",
  description: "Remove test case from suite",
  inputSchema: {
    suiteId: string,
    usecaseId: string
  }
}

{
  name: "list_suite_usecases",
  description: "List test cases in suite",
  inputSchema: { suiteId: string }
}

{
  name: "execute_test_suite",
  description: "Execute all tests in suite",
  inputSchema: { suiteId: string }
}

{
  name: "list_suite_executions",
  description: "List suite execution history",
  inputSchema: { suiteId: string }
}

{
  name: "get_suite_execution",
  description: "Get suite execution details",
  inputSchema: {
    suiteId: string,
    executionId: string
  }
}
```

### Templates

```typescript
{
  name: "list_templates",
  description: "List all templates",
  inputSchema: {}
}

{
  name: "get_template",
  description: "Get template details",
  inputSchema: { templateId: string }
}

{
  name: "create_template",
  description: "Create reusable template",
  inputSchema: {
    name: string,
    description?: string,
    category?: string,
    tags?: string[]
  }
}

{
  name: "update_template",
  description: "Update template (all fields required)",
  inputSchema: {
    templateId: string,
    name: string,
    description: string,
    category: string,
    tags: string[]
  }
}

{
  name: "delete_template",
  description: "Delete template",
  inputSchema: { templateId: string }
}

{
  name: "import_template",
  description: "Import template from JSON",
  inputSchema: { json: object }
}

{
  name: "apply_template",
  description: "Create use case from template",
  inputSchema: {
    templateId: string,
    name: string,
    description?: string,
    starting_url?: string
  }
}

{
  name: "list_template_steps",
  description: "List steps in template",
  inputSchema: { templateId: string }
}

{
  name: "create_template_step",
  description: "Add step to template",
  inputSchema: {
    templateId: string,
    sort: number,
    instruction: string,
    step_type: string,
    secret_key?: string,
    capture_variable?: string,
    validation_type?: string,
    validation_operator?: string,
    validation_value?: string,
    assertion_variable?: string,
    value_type?: string
  }
}

{
  name: "update_template_step",
  description: "Update template step",
  inputSchema: {
    templateId: string,
    stepId: string,
    // Any step fields to update
  }
}

{
  name: "delete_template_step",
  description: "Delete template step",
  inputSchema: {
    templateId: string,
    stepId: string
  }
}

{
  name: "reorder_template_steps",
  description: "Reorder template steps",
  inputSchema: {
    templateId: string,
    step_orders: Array<{ step_id: string, sort: number }>
  }
}

{
  name: "get_template_variables",
  description: "Get template variables",
  inputSchema: { templateId: string }
}

{
  name: "create_template_variables",
  description: "Create/update template variables",
  inputSchema: {
    templateId: string,
    variables: Array<{ key: string, value: string, description?: string }>
  }
}
```



## Steering Document

The extension includes a steering document that will be automatically loaded by Kiro CLI to provide context about when and how to use QA Studio tools effectively.

**File Location:** `kiro-extension/steering/qa-studio-guide.md`

**Purpose:**
- Guide Kiro on when to use QA Studio tools
- Provide step type requirements and examples
- Document common patterns and workflows
- Explain local execution and overrides

**Content:**

```markdown
# QA Studio Testing Guide for Kiro

## When to Use QA Studio

Use QA Studio tools when the developer:
- Asks to create tests, test cases, or automated tests
- Mentions testing, QA, quality assurance, or automation
- Wants to verify functionality or behavior
- Is working on UI features and wants to test them
- Says "test this", "create a test for", "verify that"

## Creating Tests

### Option 1: AI-Generated (Recommended)

Use `generate_usecase_from_journey` for complete test generation from natural language:

**When to use:**
- Developer describes what they want to test in plain English
- Creating a new test from scratch
- Testing a complete user flow or journey

**Required fields:**
- `title`: Short name for the test
- `starting_url`: URL where test starts
- `userJourney`: Natural language description of what user does
- `region`: AWS region (us-east-1, us-west-2, ap-southeast-2, eu-central-1)

**Example:**
```
Developer: "Create a test for the login flow"
Kiro calls:
generate_usecase_from_journey({
  title: "Login Flow Test",
  starting_url: "https://app.example.com/login",
  userJourney: "User navigates to login page, enters username 'testuser' and password, clicks the login button, verifies the dashboard loads with a welcome message",
  region: "us-east-1"
})
```

**Tips for good user journeys:**
- Be specific about actions (click, type, select)
- Include expected outcomes (verify, check, ensure)
- Mention element descriptions (login button, username field)
- Include test data when relevant

### Option 2: Manual Step-by-Step

Use `create_usecase` + `create_step` for manual test creation:

**When to use:**
- Adding steps to existing test
- Need precise control over step configuration
- Building complex tests with variables and assertions

**Step Types and Required Fields:**

#### 1. navigation
Click buttons, fill forms, interact with page elements.

**Required:** `instruction`, `step_type: "navigation"`

**Examples:**
```javascript
{ instruction: "Click the login button", step_type: "navigation" }
{ instruction: "Type 'testuser' in the username field", step_type: "navigation" }
{ instruction: "Select 'Premium' from the plan dropdown", step_type: "navigation" }
```

#### 2. url
Navigate directly to a specific URL.

**Required:** `instruction` (must be valid URL), `step_type: "url"`

**Example:**
```javascript
{ instruction: "https://app.example.com/dashboard", step_type: "url" }
```

#### 3. secret
Use a stored credential (password, API key, token).

**Required:** `instruction`, `step_type: "secret"`, `secret_key`

**Example:**
```javascript
{ 
  instruction: "Enter the admin password", 
  step_type: "secret", 
  secret_key: "admin_password" 
}
```

**Note:** Secrets must be created first using `create_usecase_secrets`.

#### 4. validation
Read a value from the page and compare it against expected value.

**Required:** `instruction`, `step_type: "validation"`, `validation_type`, `validation_operator`, `validation_value`

**Examples:**
```javascript
// Check number of items
{ 
  instruction: "Return the number of products on the page", 
  step_type: "validation", 
  validation_type: "number", 
  validation_operator: "greater_then", 
  validation_value: "0" 
}

// Check text content
{ 
  instruction: "Return the welcome message text", 
  step_type: "validation", 
  validation_type: "string", 
  validation_operator: "contains", 
  validation_value: "Welcome" 
}

// Check boolean state
{ 
  instruction: "Return whether the submit button is enabled", 
  step_type: "validation", 
  validation_type: "bool", 
  validation_operator: "exact", 
  validation_value: "true" 
}
```

#### 5. retrieve_value
Capture a value from the page into a runtime variable for later use.

**Required:** `instruction`, `step_type: "retrieve_value"`, `capture_variable`, `value_type`

**Examples:**
```javascript
{ 
  instruction: "Get the order ID from the confirmation page", 
  step_type: "retrieve_value", 
  capture_variable: "orderId", 
  value_type: "string" 
}

{ 
  instruction: "Get the total price", 
  step_type: "retrieve_value", 
  capture_variable: "totalPrice", 
  value_type: "number" 
}
```

#### 6. assertion
Compare a previously captured runtime variable against expected value (no browser interaction).

**Required:** `step_type: "assertion"`, `assertion_variable`, `validation_type`, `validation_operator`, `validation_value`

**NO instruction field!**

**Example:**
```javascript
// After capturing orderId with retrieve_value
{ 
  step_type: "assertion", 
  assertion_variable: "orderId", 
  validation_type: "string", 
  validation_operator: "contains", 
  validation_value: "ORD-" 
}
```

#### 7. download
Download a file from the page.

**Required:** `instruction`, `step_type: "download"`

**Example:**
```javascript
{ instruction: "Click the download report button", step_type: "download" }
```

### Validation Operators Reference

**String operators:**
- `exact` - Exact match (case sensitive)
- `exact_case_insensitive` - Exact match (ignore case)
- `contains` - Contains substring (case sensitive)
- `contains_case_insensitive` - Contains substring (ignore case)
- `not_equal` - Not equal to

**Number operators:**
- `equals` - Equal to
- `less_then` - Less than
- `greater_then` - Greater than
- `less_or_equal_then` - Less than or equal to
- `greater_or_equal_then` - Greater than or equal to

**Boolean operators:**
- `exact` - Exact match (validation_value must be "true" or "false")

## Executing Tests Locally

**IMPORTANT:** Only local execution is available from Kiro. Use `execute_usecase_local` for all test runs.

### Local Execution Behavior

- Reads test definition directly from API
- Executes using local Nova Act SDK
- Stores artifacts locally in `/tmp/qa-studio-artifacts/<usecase-id>/`
- Does NOT create execution records in platform
- Does NOT upload artifacts to S3
- Returns results with local artifact paths

### Base URL Override

Use `baseUrl` parameter to test against different environments:

**Common patterns:**
- Developer says "test against localhost" → `baseUrl: "http://localhost:3000"`
- Developer says "test on staging" → `baseUrl: "https://staging.example.com"`
- Developer says "test my local server" → Ask for port, use `baseUrl: "http://localhost:{port}"`
- Developer says "test feature branch" → `baseUrl: "https://feature-123.preview.example.com"`

**Example:**
```javascript
execute_usecase_local({
  usecaseId: "login-test-id",
  baseUrl: "http://localhost:3000"
})
```

### Variable Overrides

Use `variables` parameter to override test data:

**Common use cases:**
- Different user: `variables: { username: "testuser" }`
- Different environment: `variables: { environment: "local" }`
- Different configuration: `variables: { timeout: "30", retries: "3" }`
- Multiple overrides: `variables: { username: "admin", userType: "premium" }`

**Example:**
```javascript
execute_usecase_local({
  usecaseId: "checkout-test-id",
  baseUrl: "http://localhost:3000",
  variables: { 
    username: "testuser", 
    environment: "local",
    paymentMethod: "test-card"
  }
})
```

**Note:** Secrets are always fetched from the platform (secure, not overridable via CLI).

## Common Workflows

### Creating and Testing a Login Flow

```
Developer: "Create a test for login and run it against localhost"

Step 1: Generate test
generate_usecase_from_journey({
  title: "Login Flow",
  starting_url: "https://app.example.com/login",
  userJourney: "User enters username 'testuser' and password, clicks login, verifies dashboard loads",
  region: "us-east-1"
})

Step 2: Execute locally
execute_usecase_local({
  usecaseId: "<generated-id>",
  baseUrl: "http://localhost:3000"
})
```

### Adding Steps to Existing Test

```
Developer: "Add a step to verify the user profile loads"

create_step({
  usecaseId: "existing-test-id",
  instruction: "Click the profile link",
  step_type: "navigation"
})

create_step({
  usecaseId: "existing-test-id",
  instruction: "Return the profile name text",
  step_type: "validation",
  validation_type: "string",
  validation_operator: "contains",
  validation_value: "testuser"
})
```

### Testing with Captured Variables

```
Developer: "Test the order flow and verify the order ID format"

Step 1: Create test with retrieve_value
create_step({
  usecaseId: "order-test-id",
  instruction: "Get the order ID from the confirmation",
  step_type: "retrieve_value",
  capture_variable: "orderId",
  value_type: "string"
})

Step 2: Add assertion to verify format
create_step({
  usecaseId: "order-test-id",
  step_type: "assertion",
  assertion_variable: "orderId",
  validation_type: "string",
  validation_operator: "contains",
  validation_value: "ORD-"
})
```

## Managing Tests

### Variables and Secrets

**Variables** - Non-sensitive test data:
```javascript
create_usecase_variables({
  usecaseId: "test-id",
  variables: [
    { key: "username", value: "testuser", description: "Test username" },
    { key: "timeout", value: "30", description: "Timeout in seconds" }
  ]
})
```

**Secrets** - Sensitive credentials:
```javascript
create_usecase_secrets({
  usecaseId: "test-id",
  secrets: [
    { key: "admin_password", value: "secret123", description: "Admin password" }
  ]
})
```

### Cloning Tests

```javascript
clone_usecase({
  usecaseId: "original-test-id",
  name: "Login Flow - Staging"
})
```

### Templates

Create reusable test templates:
```javascript
// Create template
create_template({
  name: "Login Template",
  description: "Standard login flow",
  category: "Authentication"
})

// Add steps to template
create_template_step({
  templateId: "template-id",
  sort: 1,
  instruction: "Click login button",
  step_type: "navigation"
})

// Apply template to create new test
apply_template({
  templateId: "template-id",
  name: "Login Test - Production",
  starting_url: "https://app.example.com/login"
})
```

## Important Notes

- **Local execution only** - No remote execution from Kiro
- **Execution history** - View in web UI, not available in Kiro
- **Artifacts** - Stored locally during development, uploaded when running from web UI
- **Authentication** - User must login first (`QA Studio: Login` command)
- **AWS credentials** - Required for local execution (Nova Act SDK)

## Error Handling

If execution fails:
1. Check AWS credentials are configured
2. Verify test definition is valid (all required fields present)
3. Check baseUrl is accessible
4. Review local artifacts in `/tmp/qa-studio-artifacts/` for details
```

**Implementation Notes:**
- This file will be created in `kiro-extension/steering/` during Week 1-2
- Kiro CLI automatically loads steering docs from MCP server packages
- Content will be included in Kiro's context when extension is active


## User Experience

### Installation
1. Install extension from VS Code marketplace
2. Extension activates on Kiro IDE startup
3. MCP server starts automatically

### First Use
1. Developer opens project
2. Kiro prompts: "QA Studio extension detected. Login to enable test capabilities?"
3. Developer runs "QA Studio: Login"
4. Browser opens → Cognito login
5. Success notification
6. Kiro agent now has test tools available

### Steering Documentation for Kiro

The extension includes a steering document that teaches Kiro how to use QA Studio effectively:

**Location:** `kiro-extension/steering/qa-studio-guide.md`

**Content:**
```markdown
# QA Studio Testing Guide

## When to Use QA Studio

Use QA Studio tools when the developer:
- Asks to create tests
- Mentions testing, QA, or automation
- Wants to verify functionality
- Is working on UI features

## Creating Tests

### Option 1: AI-Generated (Recommended)
Use `generate_usecase_from_journey` for complete test generation:
- Write a clear user journey description
- Include all steps the user would take
- Mention expected outcomes

Example:
"User navigates to login page, enters username 'testuser' and password, clicks login button, verifies dashboard loads with welcome message"

### Option 2: Manual
Use `create_usecase` + `create_step` for step-by-step creation

**Step Types & Required Fields:**

1. **navigation** - Click buttons, fill forms, interact with page
   - Required: `instruction`, `step_type: "navigation"`
   - Example: `{ instruction: "Click the login button", step_type: "navigation" }`

2. **url** - Navigate to specific URL
   - Required: `instruction` (must be valid URL), `step_type: "url"`
   - Example: `{ instruction: "https://app.com/dashboard", step_type: "url" }`

3. **secret** - Use stored credential
   - Required: `instruction`, `step_type: "secret"`, `secret_key`
   - Example: `{ instruction: "Enter password", step_type: "secret", secret_key: "admin_password" }`

4. **validation** - Read value from page and compare
   - Required: `instruction`, `step_type: "validation"`, `validation_type`, `validation_operator`, `validation_value`
   - Example: `{ instruction: "Return the number of products on the page", step_type: "validation", validation_type: "number", validation_operator: "greater_then", validation_value: "0" }`

5. **retrieve_value** - Capture value from page into variable
   - Required: `instruction`, `step_type: "retrieve_value"`, `capture_variable`, `value_type`
   - Example: `{ instruction: "Get the order ID", step_type: "retrieve_value", capture_variable: "orderId", value_type: "string" }`

6. **assertion** - Compare previously captured variable (no browser interaction)
   - Required: `step_type: "assertion"`, `assertion_variable`, `validation_type`, `validation_operator`, `validation_value`
   - NO instruction field
   - Example: `{ step_type: "assertion", assertion_variable: "orderId", validation_type: "string", validation_operator: "contains", validation_value: "ORD-" }`

7. **download** - Download file from page
   - Required: `instruction`, `step_type: "download"`
   - Example: `{ instruction: "Click the download button", step_type: "download" }`

**Validation Operators:**
- String: exact, exact_case_insensitive, contains, contains_case_insensitive, not_equal
- Number: equals, less_then, greater_then, greater_or_equal_then, less_or_equal_then
- Bool: exact (validation_value must be "true" or "false")

## Executing Tests

### Local Testing Only
Use `execute_usecase_local` with `baseUrl` parameter:
- Against localhost: `baseUrl: "http://localhost:3000"`
- Against staging: `baseUrl: "https://staging.example.com"`
- Against feature branch: `baseUrl: "https://feature-123.preview.example.com"`

**Important:** 
- Local execution does NOT create execution records in the platform
- Artifacts are stored locally in /tmp/qa-studio-artifacts/
- Use this for development and testing
- View execution history in the web UI

## Base URL Override

When developer says:
- "Test against localhost" → Use `baseUrl: "http://localhost:3000"`
- "Test on staging" → Use `baseUrl: "https://staging.example.com"`
- "Test my local server" → Ask for port, use `baseUrl: "http://localhost:{port}"`

## Variable Overrides

Use `variables` parameter to override test data:
- Different user: `variables: { username: "testuser" }`
- Different environment: `variables: { environment: "local" }`
- Multiple overrides: `variables: { username: "admin", timeout: "30" }`

**Note:** Secrets are always fetched from platform (secure, not overridable).

## Common Patterns

**Creating login test:**
```
generate_usecase_from_journey({
  title: "Login Flow",
  startingUrl: "https://app.com/login",
  userJourney: "User enters credentials, clicks login, verifies dashboard loads",
  region: "us-east-1"
})
```

**Testing locally:**
```
execute_usecase_local({
  usecaseId: "login-test-id",
  baseUrl: "http://localhost:3000"
})
```

**Testing with different user:**
```
execute_usecase_local({
  usecaseId: "login-test-id",
  baseUrl: "http://localhost:3000",
  variables: { username: "testuser", environment: "local" }
})
```
```

This steering doc is automatically included in Kiro's context when the extension is active.

### Daily Workflow
```
Developer: "Add user registration feature"
→ Developer writes code
→ Developer: "Create tests for this and run them against localhost"
→ Kiro: "I'll create registration tests and run them locally"
  - Calls generate_usecase_from_journey
  - Calls execute_usecase_local with baseUrl="http://localhost:3000"
  - Shows results with artifact paths
  - "Test passed! Registration works on localhost. Screenshots saved to /tmp/qa-studio-artifacts/"
```

### Error Handling
- **Not authenticated:** Kiro prompts user to login
- **API error:** Kiro reports error, suggests retry
- **Local execution fails:** Kiro shows logs, suggests fixes
- **Python not found:** Extension shows setup instructions

## Technical Requirements

### Prerequisites
- Python 3.11+ installed locally
- AWS credentials configured (for Nova Act)
- Valid QA Studio account
- Kiro IDE (VS Code)

### Dependencies
- `@modelcontextprotocol/sdk` - MCP server
- `vscode` - Extension API
- `node-fetch` - HTTP client
- Python `boto3` - AWS SDK (local execution)

### Configuration
Extension settings:
```json
{
  "qaStudio.apiUrl": "https://api.your-qa-studio.com",
  "qaStudio.cognitoDomain": "https://auth.your-qa-studio.com",
  "qaStudio.clientId": "your-client-id",
  "qaStudio.pythonPath": "python3"
}
```

## Security Considerations

### Token Storage
- Stored in VS Code secrets API (encrypted)
- Never logged or exposed
- Shared via file with restricted permissions (600)

### API Access
- All requests use Bearer token
- Token expires per Cognito configuration
- Refresh handled automatically

### Local Execution
- Uses developer's AWS credentials
- No credentials stored by extension
- Inherits IAM permissions from environment

## Success Metrics

### Adoption
- Extension installs
- Active users (DAU/MAU)
- Tests created via extension vs web UI

### Efficiency
- Time from code change to test creation
- Tests executed during development
- Issues caught before commit

### Quality
- Test execution success rate
- False positive rate
- Developer satisfaction score

## Open Questions

1. **Token refresh:** Auto-refresh or require re-login?
   - **Decision:** Auto-refresh using refresh token
   
2. **Local vs remote execution:** Default behavior?
   - **Decision:** Local for development (no execution records), remote for CI/CD
   
3. **Test artifacts:** Store locally or upload to S3?
   - **Decision:** Local execution stores artifacts locally, remote execution uploads to S3

4. **Multi-workspace:** Support multiple QA Studio instances?
   - **Decision:** Phase 2 feature

5. **Artifact cleanup:** Auto-delete local artifacts?
   - **Decision:** Keep artifacts in /tmp (OS handles cleanup), or add --keep-artifacts flag

## CI/CD Runner Enhancement Required

The existing CI/CD runner needs to be extended to support single use case execution for local testing.

**Current capabilities:**
- ✅ Executes test suites (`--suite-id`)
- ✅ Base URL override (`--base-url`)
- ✅ Variable overrides (`--var key=value`, repeatable)
- ✅ Region override (`--region`)
- ✅ Model override (`--model-id`)

**Required enhancements:**
```bash
# New capability needed
cicd-runner --usecase-id <usecase-id> --local-only [--base-url <url>] [--var key=value]
```

**Implementation changes needed:**

### 1. Add CLI Arguments (parser.py)

Add to `cicd-runner/src/cli/parser.py`:
```python
@click.option('--suite-id', help='Test suite ID to execute')  # Make optional
@click.option('--usecase-id', help='Single use case ID to execute')  # NEW
@click.option('--local-only', is_flag=True, help='Local execution only (no execution records)')  # NEW
```

**Validation:** Require either `--suite-id` OR `--usecase-id` (mutually exclusive)

### 2. Local-Only Mode Behavior

When `--local-only` flag is set:

**Fetch use case definition directly:**
- `GET /usecase/{id}` - Fetch use case (name, starting_url, executing_region, model_id)
- `GET /usecase/{id}/steps` - Fetch steps
- `GET /usecase/{id}/variables` - Fetch variables
- `GET /usecase/{id}/secrets` - Fetch secret keys (values from Secrets Manager)

**Execute locally:**
- Override starting_url with `--base-url` if provided
- Merge variables with `--var` overrides
- Execute with Nova Act SDK
- Store artifacts in `/tmp/qa-studio-artifacts/<usecase-id>/`

**Skip remote operations:**
- ❌ NO `POST /usecase/{id}/execute` call
- ❌ NO execution record creation in DynamoDB
- ❌ NO artifact uploads to S3
- ❌ NO status updates to API

**Return results to stdout (JSON):**
```json
{
  "status": "success" | "failed",
  "usecaseId": "usecase-123",
  "usecaseName": "Login Flow Test",
  "duration": 45.2,
  "steps": [
    {
      "stepId": "step-1",
      "instruction": "Navigate to login page",
      "status": "success",
      "duration": 2.1,
      "screenshot": "/tmp/qa-studio-artifacts/usecase-123/step-1-screenshot.png"
    }
  ],
  "artifacts": {
    "video": "/tmp/qa-studio-artifacts/usecase-123/recording.webm",
    "logs": "/tmp/qa-studio-artifacts/usecase-123/execution.log"
  }
}
```

### 3. Normal Mode (without --local-only)

Existing behavior for suite execution:
- `POST /test-suites/{id}/execute` - Creates execution records
- Fetches execution steps from API
- Uploads artifacts to S3
- Updates execution status

**New:** Single use case execution without `--local-only`:
- `POST /usecase/{id}/execute?trigger-type=ci_runner` - Creates execution record
- `GET /usecase/{id}/executions/{executionId}/steps` - Fetch execution steps
- Execute with Nova Act
- Upload artifacts to S3
- Update execution status

### 4. Implementation Files

**New file:** `cicd-runner/src/api/usecases.py`
```python
class UseCaseAPI:
    def get_usecase(self, usecase_id: str) -> dict:
        """GET /usecase/{id}"""
    
    def get_steps(self, usecase_id: str) -> list:
        """GET /usecase/{id}/steps"""
    
    def get_variables(self, usecase_id: str) -> dict:
        """GET /usecase/{id}/variables"""
    
    def get_secrets(self, usecase_id: str) -> list:
        """GET /usecase/{id}/secrets"""
```

**Modify:** `cicd-runner/src/main.py`
- Add `run_usecase()` function for single use case execution
- Add `local_only` parameter
- Route to appropriate execution path

**Modify:** `cicd-runner/src/execution/engine.py`
- Add `execute_usecase_local()` method
- Skip artifact upload when `local_only=True`
- Skip execution record creation when `local_only=True`

### 5. Example Usage

```bash
# Local execution with base URL override
cicd-runner --usecase-id abc-123 --local-only --base-url http://localhost:3000

# Local execution with variable overrides
cicd-runner --usecase-id abc-123 --local-only \
  --var username=testuser \
  --var environment=local

# Normal execution (creates records, uploads artifacts)
cicd-runner --usecase-id abc-123

# Suite execution (existing functionality)
cicd-runner --suite-id suite-456 --base-url https://staging.example.com
```

## Implementation Timeline

### Phase 1: CI/CD Runner Enhancement (Week 1)
**Goal:** Enable single use case local execution

**Tasks:**
1. Add `--usecase-id` and `--local-only` CLI flags
2. Create `UseCaseAPI` class for direct use case fetching
3. Add local-only execution mode to engine
4. Test local execution with variable/baseUrl overrides

**Deliverable:** Runner can execute single use case locally without creating records

**Estimated effort:** 3-5 days

---

### Phase 2: Extension Foundation (Week 2)
**Goal:** Users can install and authenticate

**Tasks:**
1. VS Code extension scaffold (package.json, tsconfig, entry point)
2. Cognito OAuth implementation
3. Login/logout commands
4. Token management (~/.qa-studio-token)
5. Bundle CI/CD runner with extension
6. Create steering document (qa-studio-guide.md)

**Deliverable:** Extension installed, authentication working, runner bundled

**Estimated effort:** 5-7 days

---

### Phase 3: MCP Server + Core Tools (Week 3-4)
**Goal:** Kiro can browse and create tests

**Tasks:**
1. MCP server implementation
2. API client wrapper (uses token from file)
3. Use case tools: list, get, create, update, delete, clone, generate_usecase_from_journey
4. Step tools: list, create, update, delete, reorder
5. Variable/secret tools: get, create, delete

**Deliverable:** Kiro can manage tests (browse, create, edit)

**Estimated effort:** 7-10 days

---

### Phase 4: Local Execution Integration (Week 5)
**Goal:** Kiro can run tests locally

**Tasks:**
1. Implement execute_usecase_local tool
2. Spawn bundled CI/CD runner with correct flags
3. Parse JSON output and display results
4. Handle artifacts (show paths, optionally open)
5. Error handling and user feedback

**Deliverable:** Complete local testing workflow

**Estimated effort:** 3-5 days

---

### Phase 5: Advanced Features (Week 6-7)
**Goal:** Team collaboration features

**Tasks:**
1. Test suite tools: list, get, create, update, add_usecases
2. Template tools: list, get, create, update, apply, steps, variables
3. Polish error messages
4. Add examples to steering doc
5. Integration testing

**Deliverable:** Full feature parity with design

**Estimated effort:** 7-10 days

---

### Phase 6: Documentation & Release (Week 8)
**Goal:** Production-ready release

**Tasks:**
1. README with setup instructions
2. Extension marketplace listing
3. Demo video/screenshots
4. User documentation
5. Release v1.0.0

**Deliverable:** Published extension

**Estimated effort:** 3-5 days

---

## Work Packages

This section defines the implementation work packages. Each package should have its own specification document created by Kiro IDE.

### Package 1: CI/CD Runner Enhancement ⭐ START HERE
**Duration:** Week 1 (3-5 days)  
**Spec Location:** `.kiro/specs/kiro-extension/wp1-cicd-runner-enhancement.md`

**Objective:**
Enable the CI/CD runner to execute single use cases locally without creating execution records or uploading artifacts.

**Scope:**
- Add `--usecase-id` CLI flag (mutually exclusive with `--suite-id`)
- Add `--local-only` CLI flag (skip execution records and S3 uploads)
- Create `UseCaseAPI` class for fetching use case definitions directly
- Implement local-only execution mode in engine
- Support existing `--base-url` and `--var` flags with use case execution

**Files to Create:**
- `cicd-runner/src/api/usecases.py` - NEW: UseCaseAPI class

**Files to Modify:**
- `cicd-runner/src/cli/parser.py` - Add `--usecase-id` and `--local-only` flags
- `cicd-runner/src/main.py` - Add `run_usecase()` function and routing logic
- `cicd-runner/src/execution/engine.py` - Add `execute_usecase_local()` method

**API Endpoints Used:**
- `GET /usecase/{id}` - Fetch use case metadata
- `GET /usecase/{id}/steps` - Fetch steps
- `GET /usecase/{id}/variables` - Fetch variables
- `GET /usecase/{id}/secrets` - Fetch secret keys

**Testing Requirements:**
```bash
# Test local execution
cicd-runner --usecase-id <id> --local-only

# Test with base URL override
cicd-runner --usecase-id <id> --local-only --base-url http://localhost:3000

# Test with variable overrides
cicd-runner --usecase-id <id> --local-only --var username=testuser --var env=local

# Test normal execution (creates records)
cicd-runner --usecase-id <id>

# Ensure suite execution still works
cicd-runner --suite-id <id> --base-url https://staging.example.com
```

**Success Criteria:**
- ✅ Can execute single use case with `--usecase-id`
- ✅ `--local-only` skips execution records and S3 uploads
- ✅ Artifacts stored in `/tmp/qa-studio-artifacts/<usecase-id>/`
- ✅ JSON output to stdout with results and artifact paths
- ✅ `--base-url` and `--var` work with use case execution
- ✅ Existing suite execution functionality unchanged

**Dependencies:**
- None (standalone enhancement)

**Output Format:**
```json
{
  "status": "success" | "failed",
  "usecaseId": "usecase-123",
  "usecaseName": "Login Flow Test",
  "duration": 45.2,
  "steps": [
    {
      "stepId": "step-1",
      "instruction": "Navigate to login page",
      "status": "success",
      "duration": 2.1,
      "screenshot": "/tmp/qa-studio-artifacts/usecase-123/step-1-screenshot.png"
    }
  ],
  "artifacts": {
    "video": "/tmp/qa-studio-artifacts/usecase-123/recording.webm",
    "logs": "/tmp/qa-studio-artifacts/usecase-123/execution.log"
  }
}
```

---

### Package 2: Extension Foundation
**Duration:** Week 2 (5-7 days)  
**Spec Location:** `.kiro/specs/kiro-extension/wp2-extension-foundation.md`

**Objective:**
Create VS Code extension with OAuth authentication and bundle the CI/CD runner.

**Scope:**
- VS Code extension scaffold (package.json, tsconfig, entry point)
- Cognito OAuth implementation (authorization code flow)
- Login/logout commands
- Token storage (~/.qa-studio-token with 600 permissions)
- Bundle CI/CD runner Python package with extension
- Create steering document (qa-studio-guide.md)

**Files to Create:**
- `kiro-extension/package.json` - Extension manifest
- `kiro-extension/tsconfig.json` - TypeScript config
- `kiro-extension/src/extension.ts` - Extension entry point
- `kiro-extension/src/cognitoAuth.ts` - OAuth provider
- `kiro-extension/src/tokenManager.ts` - Token storage and refresh
- `kiro-extension/steering/qa-studio-guide.md` - Steering document (content in design doc)
- `kiro-extension/README.md` - User documentation

**VS Code Commands:**
- `qaStudio.login` - Open browser for OAuth login
- `qaStudio.logout` - Clear stored token
- `qaStudio.status` - Show authentication status

**Configuration Settings:**
```json
{
  "qaStudio.apiUrl": "https://api.qa-studio.com",
  "qaStudio.cognitoDomain": "https://auth.qa-studio.com",
  "qaStudio.clientId": "<cognito-client-id>",
  "qaStudio.pythonPath": "python3"
}
```

**Cognito Configuration:**
- App Client Type: Public
- OAuth Flows: Authorization code grant
- Scopes: openid, profile, email
- Callback URL: `vscode://publisher.qa-studio-extension/callback`

**Token Management:**
- Store token in `~/.qa-studio-token` (JSON format)
- File permissions: 600 (owner read/write only)
- Auto-refresh when expired
- Token format: `{ "access_token": "...", "refresh_token": "...", "expires_at": 1234567890 }`

**Bundling CI/CD Runner:**
- Include Python package in extension
- Path: `kiro-extension/bundled/cicd-runner/`
- Extension detects Python installation
- Validates runner can execute

**Success Criteria:**
- ✅ Extension activates in VS Code
- ✅ Login command opens browser and completes OAuth flow
- ✅ Token saved to file with correct permissions
- ✅ Token auto-refreshes before expiration
- ✅ CI/CD runner bundled and accessible
- ✅ Steering document included in extension package

**Dependencies:**
- Package 1 completed (runner with --usecase-id and --local-only)

**Deliverable:** v0.1.0 - Users can install and authenticate

---

### Package 3: MCP Server + Core Tools
**Duration:** Week 3-4 (7-10 days)  
**Spec Location:** `.kiro/specs/kiro-extension/wp3-mcp-server-core-tools.md`

**Objective:**
Implement MCP server with tools for browsing, creating, and managing tests.

**Scope:**
- MCP server implementation (embedded in extension)
- API client wrapper (reads token from ~/.qa-studio-token)
- 30+ MCP tools for use cases, steps, variables, secrets

**Files to Create:**
- `kiro-extension/src/mcpServer.ts` - MCP server implementation
- `kiro-extension/src/apiClient.ts` - QA Studio API wrapper
- `kiro-extension/src/tools/usecases.ts` - Use case tools
- `kiro-extension/src/tools/steps.ts` - Step tools
- `kiro-extension/src/tools/variables.ts` - Variable tools
- `kiro-extension/src/tools/secrets.ts` - Secret tools
- `kiro-extension/src/types.ts` - TypeScript type definitions

**MCP Tools to Implement:**

**Use Case Tools (12 tools):**
- `generate_usecase_from_journey` - AI-generated test from user journey
- `list_usecases` - List all test cases
- `get_usecase` - Get test case details
- `create_usecase` - Create blank test case
- `update_usecase` - Update test case
- `delete_usecase` - Delete test case
- `clone_usecase` - Clone test case
- `get_usecase_variables` - Get variables
- `create_usecase_variables` - Create/update variables
- `get_usecase_secrets` - Get secrets (keys only)
- `create_usecase_secrets` - Create/update secrets
- `delete_usecase_secrets` - Delete secret

**Step Tools (5 tools):**
- `list_steps` - List steps in test case
- `create_step` - Add step to test case
- `update_step` - Update step
- `delete_step` - Delete step
- `reorder_steps` - Reorder steps

**API Client Requirements:**
- Read token from `~/.qa-studio-token`
- Add `Authorization: Bearer <token>` header to all requests
- Handle 401 errors (prompt re-login)
- Handle rate limiting and retries
- Validate responses

**Error Handling:**
- Token expired → Prompt user to login
- API error → Show error message with details
- Network error → Suggest retry
- Validation error → Show field-specific errors

**Success Criteria:**
- ✅ MCP server starts with extension
- ✅ All 17 tools implemented and working
- ✅ Kiro can list and view tests
- ✅ Kiro can generate tests from user journey
- ✅ Kiro can create tests manually
- ✅ Kiro can manage steps, variables, secrets
- ✅ Error messages are helpful

**Dependencies:**
- Package 2 completed (extension with auth)

**Deliverable:** v0.2.0 - Kiro can browse and create tests

---

### Package 4: Local Execution Integration
**Duration:** Week 5 (3-5 days)  
**Spec Location:** `.kiro/specs/kiro-extension/wp4-local-execution.md`

**Objective:**
Enable Kiro to execute tests locally using the bundled CI/CD runner.

**Scope:**
- Implement `execute_usecase_local` MCP tool
- Spawn bundled CI/CD runner as subprocess
- Parse JSON output from runner
- Display results to user
- Handle artifacts (show paths, optionally open)

**Files to Create:**
- `kiro-extension/src/tools/execution.ts` - Execution tool
- `kiro-extension/src/runnerExecutor.ts` - Subprocess management

**MCP Tool:**
```typescript
{
  name: "execute_usecase_local",
  description: "Execute test case locally (no execution record, artifacts stored locally)",
  inputSchema: {
    usecaseId: string,
    baseUrl?: string,
    variables?: Record<string, string>
  }
}
```

**Implementation:**
1. Validate Python installation
2. Locate bundled CI/CD runner
3. Build command: `python3 -m cicd-runner --usecase-id <id> --local-only [--base-url <url>] [--var key=value]`
4. Spawn subprocess with token from file
5. Capture stdout (JSON output)
6. Parse results
7. Return formatted response to Kiro

**Result Display:**
```
Test execution completed: Login Flow Test
Status: ✅ Success
Duration: 45.2s

Steps:
  ✅ Step 1: Navigate to login page (2.1s)
  ✅ Step 2: Enter credentials (3.4s)
  ✅ Step 3: Click login button (1.8s)
  ✅ Step 4: Verify dashboard loads (5.2s)

Artifacts:
  📹 Video: /tmp/qa-studio-artifacts/usecase-123/recording.webm
  📸 Screenshots: /tmp/qa-studio-artifacts/usecase-123/
  📄 Logs: /tmp/qa-studio-artifacts/usecase-123/execution.log
```

**Error Handling:**
- Python not found → Show installation instructions
- Runner fails → Show error logs
- Timeout → Kill process, show partial results
- Invalid use case ID → Show error message

**Success Criteria:**
- ✅ Kiro can execute tests with `execute_usecase_local`
- ✅ Base URL override works
- ✅ Variable overrides work
- ✅ Results displayed clearly
- ✅ Artifacts accessible (paths shown)
- ✅ Errors handled gracefully

**Dependencies:**
- Package 1 completed (runner with local-only mode)
- Package 3 completed (MCP server)

**Deliverable:** v0.3.0 - Kiro can run tests locally

---

### Package 5: Advanced Features
**Duration:** Week 6-7 (7-10 days)  
**Spec Location:** `.kiro/specs/kiro-extension/wp5-advanced-features.md`

**Objective:**
Add test suite and template management capabilities.

**Scope:**
- Test suite tools (11 tools)
- Template tools (13 tools)
- Error handling improvements
- Integration testing

**Files to Create:**
- `kiro-extension/src/tools/testSuites.ts` - Test suite tools
- `kiro-extension/src/tools/templates.ts` - Template tools

**Test Suite Tools (11 tools):**
- `list_test_suites` - List all suites
- `get_test_suite` - Get suite details
- `create_test_suite` - Create suite
- `update_test_suite` - Update suite
- `delete_test_suite` - Delete suite
- `add_usecases_to_suite` - Add tests to suite
- `remove_usecase_from_suite` - Remove test from suite
- `list_suite_usecases` - List tests in suite
- `execute_test_suite` - Execute suite
- `list_suite_executions` - List execution history
- `get_suite_execution` - Get execution details

**Template Tools (13 tools):**
- `list_templates` - List all templates
- `get_template` - Get template details
- `create_template` - Create template
- `update_template` - Update template
- `delete_template` - Delete template
- `import_template` - Import from JSON
- `apply_template` - Create use case from template
- `list_template_steps` - List steps in template
- `create_template_step` - Add step to template
- `update_template_step` - Update template step
- `delete_template_step` - Delete template step
- `reorder_template_steps` - Reorder template steps
- `get_template_variables` - Get template variables
- `create_template_variables` - Create/update template variables

**Error Handling Improvements:**
- Better error messages for common issues
- Validation before API calls
- Helpful suggestions for fixes
- Retry logic for transient failures

**Integration Testing:**
- End-to-end test: Create test → Execute locally → Verify results
- Test suite workflow: Create suite → Add tests → Execute
- Template workflow: Create template → Apply → Execute

**Success Criteria:**
- ✅ All 24 tools implemented and working
- ✅ Test suite management working
- ✅ Template management working
- ✅ Error messages helpful
- ✅ Integration tests passing

**Dependencies:**
- Package 4 completed (local execution)

**Deliverable:** v0.9.0 - Feature complete

---

### Package 6: Documentation & Release
**Duration:** Week 8 (3-5 days)  
**Spec Location:** `.kiro/specs/kiro-extension/wp6-documentation-release.md`

**Objective:**
Prepare extension for production release.

**Scope:**
- User documentation
- VS Code marketplace listing
- Demo materials
- Final testing
- Release v1.0.0

**Documentation to Create:**
- `kiro-extension/README.md` - User guide
- `kiro-extension/CHANGELOG.md` - Version history
- `kiro-extension/docs/setup.md` - Setup instructions
- `kiro-extension/docs/usage.md` - Usage examples
- `kiro-extension/docs/troubleshooting.md` - Common issues

**Marketplace Listing:**
- Extension name: "QA Studio for Kiro IDE"
- Description: "Bring QA Studio test creation and execution directly into Kiro IDE"
- Categories: Testing, Automation
- Keywords: testing, qa, automation, nova-act, ui-testing
- Screenshots: 3-5 screenshots showing key features
- Demo video: 2-3 minute walkthrough

**Demo Materials:**
- Video: Create test → Execute locally → View results
- Screenshots: Login, test creation, execution results
- GIF: Quick workflow demonstration

**Final Testing:**
- Fresh install test
- Authentication flow test
- Test creation and execution
- Error handling verification
- Performance testing

**Release Checklist:**
- [ ] All tests passing
- [ ] Documentation complete
- [ ] Marketplace listing ready
- [ ] Demo video uploaded
- [ ] Version bumped to 1.0.0
- [ ] CHANGELOG updated
- [ ] Extension packaged (.vsix)
- [ ] Published to marketplace

**Success Criteria:**
- ✅ Published to VS Code marketplace
- ✅ Documentation complete and accurate
- ✅ Demo video available
- ✅ All tests passing
- ✅ No critical bugs

**Dependencies:**
- Package 5 completed (all features)

**Deliverable:** v1.0.0 - Production release

---

## Work Package Dependencies

```
Package 1 (Runner)
    ↓
Package 2 (Extension + Auth)
    ↓
Package 3 (MCP Server + Core Tools)
    ↓
Package 4 (Local Execution)
    ↓
Package 5 (Advanced Features)
    ↓
Package 6 (Documentation + Release)
```

## Specification Creation Guide for Kiro IDE

When creating specifications for each work package:

1. **Use the package scope as requirements**
2. **Reference the design document** for context
3. **Include all files to create/modify** from the package definition
4. **Add detailed acceptance criteria** based on success criteria
5. **Include testing requirements** from the package
6. **Reference API endpoints** used (from Appendix)
7. **Add implementation notes** for complex logic

**Example spec structure:**
```markdown
# WP1: CI/CD Runner Enhancement

## Objective
[From package definition]

## Requirements
[Detailed requirements from scope]

## Files to Modify
[List from package]

## Implementation Details
[Technical approach]

## Testing
[Test cases from package]

## Acceptance Criteria
[Success criteria from package]
```

---

## Release Strategy

```
v0.1.0 - Extension + Auth (Week 2)
v0.2.0 - Browse & Create Tests (Week 4)
v0.3.0 - Local Execution (Week 5)
v0.9.0 - Feature Complete (Week 7)
v1.0.0 - Production Release (Week 8)
```

## Next Steps

**Start with Package 1:**
1. Create feature branch: `feature/cicd-runner-local-execution`
2. Implement `--usecase-id` and `--local-only` flags
3. Test thoroughly with existing test cases
4. Merge to main
5. Move to Package 2 (extension foundation)

---

## Timeline

## Appendix

### API Endpoints Used

**Use Cases:**
- `POST /usecase/generate` - Generate test from user journey (Bedrock AI)
- `GET /usecases` - List all test cases
- `POST /usecase` - Create blank test case
- `GET /usecase/{id}` - Get test case
- `PATCH /usecase/{id}` - Update test case
- `DELETE /usecase/{id}` - Delete test case
- `POST /usecase/{id}/clone` - Clone test case
- `GET /usecase/{id}/steps` - Get steps (for local execution)
- `GET /usecase/{id}/variables` - Get variables (for local execution)
- `GET /usecase/{id}/secrets` - Get secrets (for local execution)

**Test Suites:**
- `GET /test-suites` - List suites
- `POST /test-suites` - Create suite
- `GET /test-suites/{id}` - Get suite
- `POST /test-suites/{id}/usecases` - Add tests to suite
- `POST /test-suites/{id}/execute` - Execute suite

**Templates:**
- `GET /templates` - List templates
- `POST /templates` - Create template
- `GET /templates/{id}` - Get template
- `POST /usecase/{id}/apply-template` - Apply template

### Cognito Configuration
- App Client Type: Public
- OAuth Flows: Authorization code grant
- Scopes: openid, profile, email
- Callback URL: `vscode://publisher.qa-studio-extension/callback`

### File Structure
```
kiro-extension/
├── src/
│   ├── extension.ts           # Entry point
│   ├── cognitoAuth.ts         # OAuth provider
│   ├── mcpServer.ts           # MCP server
│   ├── apiClient.ts           # API wrapper
│   ├── pythonExecutor.ts      # Local execution
│   └── types.ts               # TypeScript types
├── package.json
├── tsconfig.json
└── README.md
```
