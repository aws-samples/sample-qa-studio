# Web Interface

## Overview

The QA Studio web interface provides visual tools for creating, managing, and reviewing tests. Access via the CloudFront URL provided during deployment.

---

## Getting Started

### Sign In

1. Open the QA Studio URL
2. Enter email and temporary password (from deployment email)
3. Set permanent password on first login

**Password requirements:**
- At least 8 characters
- Uppercase and lowercase letters
- Numbers and symbols

---

## Navigation

### Main Sections

- **Use Cases** - Test definitions and execution history (home)
- **Test Suites** - Groups of tests for batch execution
- **Templates** - Reusable test blueprints
- **Users** - User management (admin only)
- **OAuth Clients** - API credentials (admin only)

---

## Creating Tests

### Interactive Wizard

**Best for:** Visual, step-by-step test building

**Workflow:**
1. Click **Create Use Case** → **Interactive Wizard**
2. Enter name, starting URL, description
3. Select browser region
4. Click **Start Wizard** to launch live browser
5. Type step instruction (e.g., "Click Login button")
6. Watch browser execute in real-time
7. Accept step if correct, or modify and retry
8. Repeat until complete
9. Click **Finish** to save test

**Tips:**
- Watch the browser carefully to verify each step
- Use specific language: "Click the button labeled 'Submit'"
- Add validation steps to verify outcomes

---

### Create from User Journey

**Best for:** Quick test generation from descriptions

**Workflow:**
1. Click **Create Use Case** → **Create from User Journey**
2. Enter title and starting URL
3. Describe the test flow in natural language
4. Click **Generate**
5. Review generated steps
6. Edit if needed
7. Save test

**Example journey:**
```
Navigate to login page, enter username 'admin@example.com', 
enter password, click Sign In button, verify dashboard heading 
is visible
```

---

### Create Blank

**Best for:** Manual step-by-step control

**Workflow:**
1. Click **Create Use Case** → **Create Blank**
2. Enter name, starting URL, description
3. Click **Create**
4. Navigate to **Steps** tab
5. Click **Add Step**
6. Select step type and configure
7. Repeat for all steps
8. Save test

---

### Start from Template

**Best for:** Common patterns and workflows

**Workflow:**
1. Click **Create Use Case** → **Start from Template**
2. Browse template library
3. Select template
4. Customize variables and steps
5. Save test

**Common templates:**
- Login flows
- Form submissions
- Navigation patterns
- E-commerce workflows

---

### Clone from Use Case

**Best for:** Variations of existing tests

**Workflow:**
1. Open existing test
2. Click **Clone**
3. Enter new name
4. Modify steps as needed
5. Save test

---

### Import Use Case

**Best for:** Sharing tests between environments

**Workflow:**
1. Click **Create Use Case** → **Import Use Case**
2. Upload JSON file
3. Review imported test
4. Save test

---

## Managing Tests

### Use Cases Dashboard

**Features:**
- Search and filter tests
- View execution status
- Select multiple tests for batch operations
- Execute tests individually or in batch
- Delete tests

**Columns:**
- Name and description
- Tags
- Last execution status
- Last run timestamp

---

### Test Details

Click a test to view:

#### Overview Tab
- Name, description, starting URL
- Tags, region, model
- Created/updated timestamps
- Active status

#### Steps Tab
- Ordered list of test steps
- Step type and instruction
- Edit, reorder, or delete steps
- Add new steps

#### Variables Tab
- Define test variables
- Set default values
- Override at execution time

#### Executions Tab
- Execution history
- Status, timestamp, duration
- View artifacts (video, logs, screenshots)

---

## Viewing Execution Results

### Execution Details

Click an execution to view:

#### Summary
- Status (success, failed, running)
- Start/end time
- Duration
- Trigger type

#### Steps
- Per-step status
- Step duration
- Error messages (if failed)

#### Artifacts
- **Video recording** - Full browser session
- **Screenshots** - Per-step screenshots
- **Logs** - Detailed execution logs

**Reviewing artifacts:**
1. Click **View Video** to watch full execution
2. Click **Download Logs** for detailed logs
3. Review screenshots to see browser state at each step

---

## Test Suites

### Creating Suites

1. Navigate to **Test Suites**
2. Click **Create Suite**
3. Enter name, description, tags
4. Click **Create**

### Adding Tests to Suites

1. Open suite
2. Click **Add Tests**
3. Select tests from list
4. Click **Add**

### Executing Suites

1. Open suite
2. Click **Execute**
3. Configure overrides (optional):
   - Base URL
   - Variables
   - Region
   - Model
4. Click **Start Execution**

### Viewing Suite Results

1. Open suite
2. Navigate to **Executions** tab
3. Click execution to view details
4. Review per-test results

---

## Templates

### Using Templates

1. Navigate to **Templates**
2. Browse available templates
3. Click template to preview
4. Click **Use Template**
5. Customize variables and steps
6. Save as new test

### Creating Templates

1. Create a test with variables
2. Export as JSON
3. Share with team
4. Import as template

---

## User Management (Admin Only)

### Adding Users

1. Navigate to **Users**
2. Click **Add User**
3. Enter email address
4. Select role (admin or user)
5. Click **Create**
6. User receives email with temporary password

### Managing Users

- View all users
- Edit user roles
- Disable/enable users
- Delete users

---

## OAuth Client Management (Admin Only)

### Creating OAuth Clients

1. Navigate to **OAuth Clients**
2. Click **Create Client**
3. Enter name and description
4. Select scopes:
   - `api/usecases.read` - Read tests
   - `api/usecases.write` - Create/update tests
   - `api/test-suites.read` - Read suites
   - `api/test-suites.write` - Create/update suites
5. Click **Create**
6. Copy client ID and secret (shown once)

### Managing OAuth Clients

- View all clients
- Regenerate secrets
- Update scopes
- Delete clients

**Use cases:**
- CI/CD integration
- API automation
- Third-party integrations

---

## Tips and Tricks

### Keyboard Shortcuts

- `Ctrl/Cmd + K` - Quick search
- `Ctrl/Cmd + N` - New test
- `Ctrl/Cmd + S` - Save test

### Filtering Tests

Use search bar to filter by:
- Name
- Description
- Tags
- Status

### Batch Operations

1. Select multiple tests using checkboxes
2. Click **Execute** to run all selected
3. Click **Delete** to remove all selected

### Exporting Tests

1. Open test
2. Click **Export**
3. Save JSON file
4. Share with team or import to another environment

---

## Next Steps

- **Create tests via CLI:** [📝 Creating Tests](./creating-tests.md)
- **Run tests locally:** [▶️ Local Execution](./local-execution.md)
- **Set up CI/CD:** [🔄 CI/CD Integration](./ci-cd-integration.md)
