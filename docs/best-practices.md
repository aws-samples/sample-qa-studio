# Best Practices Guide

This guide provides recommendations for optimal usage of QA Studio, covering test organization, test creation, security, and performance optimization.

## Test Organization

### Test Suite Structure

Organize test suites by functional area, user journey, or testing purpose:

**By Functional Area**:
```
- Authentication Suite (login, logout, password reset)
- Checkout Suite (cart, payment, order confirmation)
- Search Suite (basic search, filters, sorting)
- Admin Suite (user management, settings, reports)
```

**By User Journey**:
```
- New User Onboarding Suite
- Power User Workflow Suite
- Guest Checkout Suite
- Mobile User Experience Suite
```

**By Testing Purpose**:
```
- Smoke Tests (critical paths)
- Regression Tests (comprehensive coverage)
- Integration Tests (cross-feature workflows)
- Edge Cases (error handling, boundary conditions)
```

### Naming Conventions

Use clear, descriptive names:

**Good Examples**:
- `smoke-tests-critical-paths`
- `regression-checkout-flow`
- `authentication-tests`
- `api-integration-tests`

**Poor Examples**:
- `tests` (too generic)
- `suite1` (not descriptive)
- `my-tests` (unclear ownership)

### Suite Size

**Recommendations**:
- Keep suites under 30 tests for manageable execution time
- Split large suites into logical groups
- Create focused suites for specific features

**Example**:
```
Instead of:
- All Tests (100 tests)

Use:
- Smoke Tests (10 tests)
- Authentication Tests (15 tests)
- Checkout Tests (20 tests)
- Search Tests (15 tests)
- Admin Tests (20 tests)
```

---

## Test Creation

### Writing Effective Instructions

**Be Specific**:
```
✅ Good: "Click the blue 'Sign In' button in the top right corner"
❌ Poor: "Click the button"

✅ Good: "Enter 'test@example.com' in the email field"
❌ Poor: "Enter email"

✅ Good: "Verify the success message says 'Order placed successfully'"
❌ Poor: "Check if it worked"
```

**Use Natural Language**:
```
✅ Good: "Navigate to the login page"
❌ Poor: "goto('/login')"

✅ Good: "Fill in the username field with 'testuser'"
❌ Poor: "input#username.value = 'testuser'"
```

**One Action Per Step**:
```
✅ Good:
- Step 1: "Click the 'Add to Cart' button"
- Step 2: "Click the 'Checkout' button"

❌ Poor:
- Step 1: "Click 'Add to Cart' and then click 'Checkout'"
```

### Using Variables

**When to Use Variables**:
- Credentials (username, password)
- Environment-specific values (URLs, API keys)
- Test data that changes between runs
- Sensitive information

**Variable Naming**:
```
✅ Good: username, password, api_key, base_url
❌ Poor: var1, x, temp, data
```

**Example**:
```
Step: "Enter {{username}} in the username field"
Step: "Enter {{password}} in the password field"
Step: "Navigate to {{base_url}}/login"
```

### Using Secrets

**Store Sensitive Data in Secrets Manager**:
- Passwords
- API keys
- Tokens
- Credit card numbers (test data)

**Reference Secrets in Steps**:
```
Step: "Enter the password from secret 'test-user-password'"
```

**Benefits**:
- Secrets never appear in logs
- Centralized secret management
- Easy rotation without updating tests

### When to Use Network Assertion vs Validation

Both step types verify behaviour, but they look at different layers of the app:

- **Validation** reads from the live DOM. Use it to check what the user sees on the page.
- **Network Assertion** reads from the outgoing HTTP request. Use it to verify the contract between the UI and the backend.

Use `network_assertion` when:
- A button click must trigger a specific API call with specific data.
- You need to test the UI against an error or edge-case response the real backend doesn't produce.
- Your test depends on a downstream system that isn't reliable in your test environment — mock it.

Cautions:
- Avoid mocking endpoints that transmit secrets (login, token refresh). The mock response bodies you define live in the test definition and are visible to anyone with access to the use case.
- The step type is not cached. If your test suite is slow, cache the navigation steps around it rather than trying to cache the network observation.
- The 15 s default timeout fits most click-then-request flows. Raise it only when the underlying call is known to take longer.

### When to Use `subset` vs `schema` for Body Matching

Network assertions support three body-match modes. The right one depends on what you're actually testing:

- **`exact`** — the parsed JSON equals the expected body exactly. Extra keys fail. Good for small, stable payloads where every key matters. **Request side only** — response bodies frequently contain non-deterministic values and are rejected as `exact` targets by design.
- **`subset`** — every key/value in the template must be in the captured body; extra keys are ignored. Use this when you know the specific values you expect for the keys you care about (e.g. `{"status": "active"}`). Arrays match element-by-element, so lengths must align.
- **`schema`** — a JSON Schema Draft 2020-12 document validates the captured body structurally. Use this when you care about types and required keys but not specific values, especially for variable-length responses (lists, paginated data). A schema with `"items": {...}` checks every element of a list against the same shape, decoupling the test from the list length.

Rule of thumb: if your assertion would break whenever the real response adds a valid field or timestamp, you're using `exact` or over-specified `subset` — reach for `schema` instead.

### Cautions for Response-Side Assertions

- Response bodies are captured after any mock/passthrough merge runs, not before. If your mock replaces the response, you are asserting against the merged response.
- Non-JSON response bodies (HTML, binary downloads) cannot be verified with `subset` or `schema`. Use a `download` step or a DOM-level `validation` step instead.
- A captured response larger than the configured cap fails the step even when no body assertion is configured. Use `network_response_body_match_type: schema` with a schema that ignores large fields, or narrow the URL pattern to a smaller endpoint.
- External `$ref` (`http://`, `https://`, `file://`) in schemas is rejected at submit time. Keep schemas self-contained or use local `#/$defs/...` references.

---

## Test Maintenance

### Keep Tests Independent

Each test should:
- Set up its own data
- Clean up after itself
- Not depend on other tests
- Be runnable in any order

**Example**:
```
❌ Poor:
Test 1: Create user account
Test 2: Login with that account (depends on Test 1)

✅ Good:
Test 1: Create user account, then delete it
Test 2: Login with pre-existing test account
```

### Handle Dynamic Content

**Use Appropriate Waits**:
```
✅ Good: "Wait for the loading spinner to disappear"
✅ Good: "Wait for the 'Welcome' message to appear"

❌ Poor: "Wait 5 seconds" (brittle, slow)
```

**Use Stable Selectors**:
```
✅ Good: "Click the button with text 'Submit'"
✅ Good: "Click the button with aria-label 'Submit form'"

❌ Poor: "Click the third button" (fragile)
```

### Regular Review

- Review test results weekly
- Update tests when UI changes
- Remove obsolete tests
- Refactor duplicate logic into templates

---

## Security Best Practices

### Authentication

**User Credentials**:
- Store in AWS Secrets Manager
- Never hardcode in test steps
- Use separate test accounts
- Rotate credentials regularly

**OAuth Clients**:
- Create separate clients for different purposes
- Use descriptive names
- Grant minimum required scopes
- Rotate secrets regularly
- Delete unused clients

### Access Control

**User Management**:
- Use Cognito groups for role-based access
- Grant minimum required permissions
- Review user access regularly
- Remove inactive users

**API Access**:
- Use OAuth clients for programmatic access
- Never share client secrets
- Store secrets in secure secret management
- Monitor API usage

### Data Protection

**Test Data**:
- Use synthetic test data
- Never use production data
- Anonymize any real data
- Delete test data after use

**Artifacts**:
- Configure S3 lifecycle policies
- Delete old artifacts regularly
- Restrict access to artifacts
- Use presigned URLs (expire after 1 hour)

---

## Performance Optimization

### Test Execution

**Optimize Test Steps**:
- Remove unnecessary waits
- Use specific selectors
- Minimize navigation between pages
- Combine related actions

**Example**:
```
❌ Slow:
- Navigate to homepage
- Click login link
- Wait 2 seconds
- Enter username
- Wait 1 second
- Enter password
- Wait 1 second
- Click submit

✅ Fast:
- Navigate to login page directly
- Enter username
- Enter password
- Click submit
```

**Parallel Execution**:
- Group independent tests into suites
- Suites execute tests in parallel automatically
- Split large suites for faster execution

### Resource Usage

**Artifact Management**:
- Configure S3 lifecycle policies
- Transition old artifacts to Glacier
- Delete artifacts after retention period
- Only capture necessary artifacts

**Example Lifecycle Policy**:
```
- Keep artifacts for 30 days (Standard)
- Move to Glacier after 30 days
- Delete after 90 days
```

**DynamoDB Optimization**:
- Use on-demand capacity mode
- Archive old execution records
- Delete test executions after analysis

---

## Monitoring & Observability

### CloudWatch Logs

**What to Monitor**:
- Lambda function errors
- ECS task failures
- API Gateway errors
- Worker execution logs

**Set Up Alarms**:
- High error rate
- Execution timeouts
- Failed authentications
- Resource exhaustion

### Execution History

**Review Regularly**:
- Test success rates
- Execution times
- Failure patterns
- Resource usage

**Identify Issues**:
- Flaky tests (intermittent failures)
- Slow tests (optimization opportunities)
- Failing tests (bugs or test issues)

---

## Cost Optimization

### Compute Costs

**Lambda**:
- Functions are billed per invocation
- Optimize function memory allocation
- Reduce cold starts with provisioned concurrency (if needed)

**ECS Fargate**:
- Tasks are billed per second
- Optimize test execution time
- Use appropriate task size (CPU/memory)

**Bedrock (Nova Act)**:
- Billed per API call
- Optimize test steps to reduce calls
- Use caching when available

### Storage Costs

**S3**:
- Configure lifecycle policies
- Delete old artifacts
- Use Intelligent-Tiering for variable access patterns

**DynamoDB**:
- Use on-demand pricing for variable workloads
- Archive old execution records
- Delete unnecessary data

### Cost Monitoring

**Set Up Budgets**:
- Create AWS Budgets for QA Studio resources
- Set alerts for unexpected costs
- Review Cost Explorer monthly

**Tag Resources**:
- Tag all resources with project/team
- Use cost allocation tags
- Track costs by environment (dev/staging/prod)

---

## Collaboration

### Team Workflows

**Test Ownership**:
- Assign tests to team members
- Use naming conventions to indicate ownership
- Document test purpose and scope

**Code Reviews**:
- Review test changes before merging
- Ensure tests follow best practices
- Verify tests are maintainable

**Documentation**:
- Document test suites and their purpose
- Maintain a test plan document
- Keep README updated with setup instructions

### Sharing Tests

**Export/Import**:
- Export tests as JSON for sharing
- Version control test definitions
- Import tests into other environments

**Templates**:
- Create templates for common patterns
- Share templates across team
- Document template usage

---

## Continuous Improvement

### Metrics to Track

**Test Quality**:
- Test success rate
- Flaky test count
- Test coverage

**Performance**:
- Average execution time
- Time to detect bugs
- Time to fix failing tests

**Cost**:
- Cost per test execution
- Total monthly cost
- Cost trends over time

### Regular Reviews

**Weekly**:
- Review failed tests
- Update flaky tests
- Check execution times

**Monthly**:
- Review test coverage
- Analyze cost trends
- Update documentation

**Quarterly**:
- Review test strategy
- Evaluate tool effectiveness
- Plan improvements

---

## Mobile Testing Best Practices

### Device Selection

- **Prefer "Highly available" devices**: These have better uptime and faster session provisioning.
- **Use auto-selection for CI/CD**: Let Device Farm pick the newest available device rather than pinning to a specific one, which may become unavailable.
- **Pin devices for reproducibility**: When debugging a specific issue, pin to the exact device and OS version to get consistent results.

### App Binary Management

- **Upload once, reuse many times**: Device Farm retains uploaded binaries. The CLI and worker automatically reuse existing uploads by filename.
- **Use consistent filenames**: The upload lookup matches by filename. If you change the binary, keep the same filename so it gets reused (or use `force_upload` to replace it).
- **Version your binaries**: Include version numbers in filenames (e.g., `myapp-v2.1.0.ipa`) when you need to test specific versions side by side.

### Writing Mobile Test Steps

- **Be explicit about UI elements**: Mobile apps have less text than web pages. Reference buttons by their visible label, not position.
- **Handle pop-ups early**: iOS notification permissions and Android system dialogs appear on first launch. Add a "Close any pop-ups" step at the beginning.
- **Allow time for animations**: Mobile apps often have transitions. If a step fails intermittently, the app may still be animating.
- **Keep steps focused**: One action per step works better on mobile than compound instructions.

### Cost Optimization

- **Device Farm charges per minute**: Minimize session time by keeping tests focused and steps efficient.
- **Reuse app uploads**: Avoid re-uploading the same binary on every run.
- **Use auto-select**: Auto-selected devices are typically more available, reducing failed session provisioning attempts.

---

## Common Pitfalls

### Avoid These Mistakes

**Over-Reliance on Waits**:
```
❌ Poor: "Wait 5 seconds" after every action
✅ Good: "Wait for element to appear" only when needed
```

**Brittle Selectors**:
```
❌ Poor: "Click the third button in the second div"
✅ Good: "Click the button with text 'Submit'"
```

**Test Dependencies**:
```
❌ Poor: Tests that must run in specific order
✅ Good: Independent tests that can run in any order
```

**Hardcoded Values**:
```
❌ Poor: "Navigate to https://staging.example.com/login"
✅ Good: "Navigate to {{base_url}}/login"
```

**Ignoring Failures**:
```
❌ Poor: Marking flaky tests as "known issues"
✅ Good: Fixing or removing flaky tests
```

---

## Getting Started Checklist

### Initial Setup

- [ ] Deploy QA Studio to AWS
- [ ] Create admin user account
- [ ] Configure OAuth clients
- [ ] Set up AWS Secrets Manager for test secrets
- [ ] Configure S3 lifecycle policies
- [ ] Set up CloudWatch alarms

### First Test Suite

- [ ] Create test suite with descriptive name
- [ ] Add 3-5 smoke tests for critical paths
- [ ] Use variables for environment-specific values
- [ ] Store credentials in Secrets Manager
- [ ] Execute suite and verify results
- [ ] Review artifacts (videos, screenshots)

### Team Onboarding

- [ ] Create user accounts for team members
- [ ] Assign appropriate permissions
- [ ] Share documentation and best practices
- [ ] Conduct training session
- [ ] Create example tests for reference
- [ ] Set up regular review meetings

---

## Additional Resources

- [User Guide](user-guide.md) - Complete walkthrough of the web interface
- [Prompting Best Practices](prompting-best-practices.md) - Writing effective test steps
- [Architecture](architecture.md) - System design and data flows
- [API Reference](api-reference.md) - Complete API documentation
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
