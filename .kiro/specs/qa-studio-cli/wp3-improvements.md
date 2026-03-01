# WP3 Agent Skills - Improvements Based on Anthropic Best Practices

## Summary

The current wp3-agent-skills.md spec is well-structured and follows most best practices. This document outlines specific improvements to align with Anthropic's Agent Skills guidelines.

## Critical Improvements

### 1. Enhanced Description Field

**Current:**
```yaml
description: Create and manage QA Studio UI tests. Use when developer asks to create tests, mentions testing/QA, or wants to verify functionality. Supports AI-generated tests from user journeys and manual step-by-step creation.
```

**Improved (add key terms and specific triggers):**
```yaml
description: Create and manage QA Studio UI tests using Nova Act browser automation. Use when developer asks to create tests, mentions testing/QA, UI automation, browser testing, end-to-end tests, E2E testing, web application testing, or wants to verify functionality. Supports AI-generated tests from natural language user journeys and manual step-by-step creation.
```

**Why:** More specific terms help Claude discover the skill in relevant contexts.

### 2. Add Concrete Examples Section

Add to SKILL.md after "Creating Tests":

```markdown
## Examples

**Example 1: Login flow test**

Input:
```bash
qa-studio tests create --from-journey \
  --title "User Login" \
  --url "https://app.example.com/login" \
  --journey "User enters 'admin@example.com' in email field, enters password, clicks 'Sign In' button, verifies 'Dashboard' heading appears"
```

Output: Test created with ID `test-abc123`

**Example 2: Form submission with validation**

Input:
```bash
qa-studio tests create --from-journey \
  --title "Contact Form" \
  --url "https://app.example.com/contact" \
  --journey "User fills 'John Doe' in name field, fills 'john@example.com' in email, types 'Hello' in message box, clicks submit button, verifies 'Thank you' message appears"
```

Output: Test created with validation steps

**Example 3: Local execution with overrides**

Input:
```bash
qa-studio run test-abc123 \
  --base-url http://localhost:3000 \
  --var email=test@example.com \
  --var password=testpass123
```

Output: Test executes against local environment
```

### 3. Add Conditional Workflow Pattern

Add to SKILL.md:

```markdown
## Choosing the Right Approach

**Decision tree:**

1. **Do you have a clear description of what to test?**
   - YES → Use AI-generated creation (recommended)
   - NO → Start with manual creation

2. **Is this a simple linear flow?**
   - YES → AI-generated will work well
   - NO (complex branching) → Consider manual creation

3. **Do you need to modify an existing test?**
   - Get test → Edit steps → Update test

**When to use AI-generated:**
- Testing user journeys (login, checkout, forms)
- Creating tests from requirements
- Quick test creation

**When to use manual creation:**
- Complex conditional logic
- Precise control over each step
- Advanced validation scenarios
```

### 4. Add Feedback Loop Section

Add to SKILL.md:

```markdown
## Test Creation Workflow

Follow this iterative process:

1. **Create test** with `--from-journey`
2. **Review generated steps** with `qa-studio tests get <id>`
3. **Test locally** with `qa-studio run <id> --base-url http://localhost:3000`
4. **If test fails:**
   - Review error message
   - Refine journey description (be more specific about elements)
   - Update test or recreate
5. **Repeat** until test passes consistently
6. **Deploy** to QA Studio for CI/CD integration

**Tips for refining journeys:**
- Be specific about button text: "clicks 'Sign In' button" not "clicks login"
- Include expected outcomes: "verifies 'Dashboard' heading appears"
- Mention element types: "fills email field" not just "enters email"
```

### 5. Add Prerequisites Section

Add at the beginning of SKILL.md:

```markdown
## Prerequisites

**Check authentication:**
```bash
qa-studio status
```

Expected output:
```
✓ Authenticated as user@example.com
✓ Region: us-east-1

Skills:
  ✓ qa-studio-tests
  ✓ qa-studio-suites
```

**If not authenticated:**
```bash
qa-studio login
```

**If skills not installed:**
```bash
qa-studio setup
```
```

### 6. Add Error Handling Section

Add to SKILL.md:

```markdown
## Common Issues

**Authentication failed:**
```bash
# Re-authenticate
qa-studio login

# Verify status
qa-studio status
```

**Test not found:**
```bash
# List all tests
qa-studio tests list

# Verify test ID is correct
qa-studio tests get <test-id>
```

**Local execution fails:**
```bash
# Check base URL is accessible
curl http://localhost:3000

# Verify variables are correct
qa-studio run <test-id> --base-url http://localhost:3000 --var key=value
```

**Journey generation produces wrong steps:**
- Be more specific in journey description
- Mention exact button text and field labels
- Include expected outcomes
- Break complex flows into multiple tests
```

### 7. Reference Files - Add Table of Contents

For `reference/step-types.md`:

```markdown
# Step Types Reference

## Contents
- [Navigation Steps](#navigation-steps) - Click, type, select elements
- [URL Steps](#url-steps) - Navigate to pages
- [Secret Steps](#secret-steps) - Use stored credentials
- [Validation Steps](#validation-steps) - Check page values
- [Retrieve Value Steps](#retrieve-value-steps) - Capture data into variables
- [Assertion Steps](#assertion-steps) - Compare captured values
- [Download Steps](#download-steps) - Download and verify files

## Navigation Steps

**Description:** Interact with page elements using natural language.

**Required fields:**
- `instruction`: Natural language description of action

**Examples:**
```bash
# Click button
"Click the 'Sign In' button"

# Fill form field
"Type 'john@example.com' in the email field"

# Select dropdown
"Select 'United States' from country dropdown"
```

**When to use:**
- Most common step type
- Any UI interaction (click, type, select)
- Nova Act determines element automatically

[Continue with other step types...]
```

### 8. Update Validation Checklist

Add to the existing checklist:

```markdown
### Validation Checklist

**SKILL.md Quality:**
- [ ] YAML frontmatter valid (name, description)
- [ ] Description in third person
- [ ] Description includes what AND when (with key terms)
- [ ] Main content under 500 lines
- [ ] Examples are concrete with input/output pairs
- [ ] References are one level deep
- [ ] No Windows-style paths
- [ ] Prerequisites section included
- [ ] Error handling guidance included
- [ ] Feedback loop documented

**Progressive Disclosure:**
- [ ] Main SKILL.md is concise overview
- [ ] Detailed content in reference files
- [ ] Clear links to reference files
- [ ] Reference files have table of contents (if >100 lines)
- [ ] Conditional workflow pattern included

**Kiro Integration:**
- [ ] Skills discoverable by Kiro
- [ ] Skills reference correct CLI commands
- [ ] Examples match actual CLI syntax
- [ ] Common issues documented
- [ ] Decision trees for choosing approaches
```

## Implementation Priority

1. **High Priority** (do first):
   - Enhanced description with key terms
   - Concrete examples section
   - Prerequisites section
   - Error handling section

2. **Medium Priority**:
   - Conditional workflow pattern
   - Feedback loop section
   - Table of contents for reference files

3. **Nice to Have**:
   - Additional examples
   - More detailed troubleshooting

## Testing After Changes

```bash
# Install updated skills
qa-studio setup

# Test with Kiro
kiro chat

# Test queries:
> "Create a test for the login flow"
> "I need to test a form submission"
> "Run this test against localhost"
> "Create a test suite with these tests"
```

Verify Claude:
- Discovers the skill appropriately
- Uses correct CLI commands
- Follows workflows
- Handles errors gracefully
