# CLI Reference

<<<<<<< HEAD
This guide provides detailed information about the Nova Act QA Studio CI/CD Runner command-line interface, including all available options, usage patterns, exit codes, and output format.
=======
This guide provides detailed information about the QA Studio CI/CD Runner command-line interface, including all available options, usage patterns, exit codes, and output format.
>>>>>>> 781b54a (finish mergin main)

## Basic Usage

The basic usage pattern for the CI/CD runner is:

```bash
cicd-runner --suite-id <suite-id> [OPTIONS]
```

The runner requires authentication via environment variables (see [Configuration Reference](configuration.md)) and at minimum a test suite ID to execute.

## Quick Examples

### Simple Execution

Execute a test suite with default settings:

```bash
cicd-runner --suite-id 01234567-89ab-cdef-0123-456789abcdef
```

### With Base URL Override

Override the base URL for all use cases in the suite:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com
```

### With Variable Overrides

Override specific test variables:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --var username=testuser \
  --var password=testpass \
  --var environment=staging
```

### With Verbose Logging

Enable detailed debug logging:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --verbose
```

### Complete Example

Combine all options for maximum control:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com \
  --var username=testuser \
  --var password=testpass \
<<<<<<< HEAD
  --var api_key=test_key_123 \
  --region us-west-2 \
  --model-id anthropic.claude-3-5-sonnet-20240620-v1:0 \
=======
  --model-id nova-act-v1.0 \
>>>>>>> 781b54a (finish mergin main)
  --timeout 7200 \
  --verbose
```

## CLI Options Reference

### Required Options

#### `--suite-id <uuid>`

<<<<<<< HEAD
**Description**: The UUID of the test suite to execute. This is the unique identifier for the test suite in the Nova Act QA Studio platform.
=======
**Description**: The UUID of the test suite to execute. This is the unique identifier for the test suite in the QA Studio platform.
>>>>>>> 781b54a (finish mergin main)

**Required**: Yes

**Format**: UUID (e.g., `01234567-89ab-cdef-0123-456789abcdef`)

**Example**:
```bash
cicd-runner --suite-id 01234567-89ab-cdef-0123-456789abcdef
```

**Notes**:
- The suite must exist in the platform and be accessible with your OAuth credentials
- You can find suite IDs in the platform UI or via the API

### Optional Options

#### `--base-url <url>`

**Description**: Override the base URL for all use cases in the test suite. This is useful for testing against different environments (staging, production, etc.) without modifying the test suite definition.

**Required**: No

**Format**: Full URL including protocol (e.g., `https://staging.example.com`)

**Example**:
```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com
```

**Notes**:
- Must include protocol (`https://` or `http://`)
- Overrides the base URL for all use cases in the suite
- Does not affect absolute URLs in test steps

#### `--var <key>=<value>`

**Description**: Override a test variable. Variables are key-value pairs that can be referenced in test steps. This option can be specified multiple times to override multiple variables.

**Required**: No (repeatable)

**Format**: `key=value` where key is the variable name and value is the variable value

**Example**:
```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --var username=testuser \
  --var password=testpass \
  --var environment=staging
```

**Notes**:
- Can be specified multiple times for multiple variables
- Overrides variables defined in the test suite
- Values can contain spaces if quoted in the shell: `--var "full_name=John Doe"`
- Variable names are case-sensitive

<<<<<<< HEAD
#### `--region <aws-region>`

**Description**: Override the AWS region for browser execution. This determines which AWS region the Nova Act browser instances will run in.

**Required**: No

**Format**: AWS region code (e.g., `us-west-2`, `eu-west-1`)

**Example**:
```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --region us-west-2
```

**Notes**:
- Must be a valid AWS region code
- Affects browser execution latency based on geographic location
- Overrides the region specified in the test suite

#### `--model-id <model-id>`

**Description**: Override the Amazon Bedrock model ID used for Nova Act AI-powered testing. This allows you to test with different AI models.

**Required**: No

**Format**: Bedrock model ID (e.g., `anthropic.claude-3-5-sonnet-20240620-v1:0`)
=======
#### `--model-id <model-id>`

**Description**: Override the Nova Act model ID used for AI-powered browser automation.

**Required**: No

**Format**: Nova Act model ID (e.g., `nova-act-v1.0`)
>>>>>>> 781b54a (finish mergin main)

**Example**:
```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
<<<<<<< HEAD
  --model-id anthropic.claude-3-5-sonnet-20240620-v1:0
```

**Notes**:
- Must be a valid Bedrock model ID available in your AWS account
=======
  --model-id nova-act-v1.0
```

**Notes**:
- Must be a valid Nova Act model ID
>>>>>>> 781b54a (finish mergin main)
- Different models may have different capabilities and performance characteristics
- Overrides the model specified in the test suite

#### `--timeout <seconds>`

**Description**: Set the global timeout for the entire test suite execution in seconds. If the execution exceeds this timeout, it will be terminated.

**Required**: No

**Default**: `3600` (1 hour)

**Format**: Integer number of seconds

**Example**:
```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --timeout 7200
```

**Notes**:
- Applies to the entire suite execution, not individual test cases
- Set higher for large test suites or slow environments
- Minimum recommended: 300 seconds (5 minutes)
- Maximum recommended: 14400 seconds (4 hours)

#### `--verbose`

**Description**: Enable verbose logging output. This sets the log level to DEBUG and provides detailed information about the runner's execution, including API requests, authentication details, and internal operations.

**Required**: No

**Default**: `false` (INFO level logging)

**Format**: Flag (no value required)

**Example**:
```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --verbose
```

**Notes**:
- Useful for troubleshooting authentication, API, or execution issues
- Generates significantly more log output
- May include sensitive information in logs (use with caution in CI/CD)
- Can also be controlled via `LOG_LEVEL` environment variable

#### `--help`

**Description**: Display help information about the CLI and exit.

**Required**: No

**Format**: Flag (no value required)

**Example**:
```bash
cicd-runner --help
```

## Exit Codes

The runner uses exit codes to indicate the result of the execution. These codes can be used in CI/CD pipelines to determine whether to proceed with subsequent steps or fail the build.

| Exit Code | Meaning | Description |
|-----------|---------|-------------|
| `0` | Success | All test cases in the suite passed successfully |
| `1` | Test Failure | One or more test cases failed |
| `2` | Runner Error | The runner encountered an error (authentication, configuration, API, network, etc.) |

### Exit Code Usage in CI/CD

Most CI/CD platforms automatically fail the build when a command exits with a non-zero code. You can use this behavior to control your pipeline:

**Example: Fail build on test failure**
```bash
# This will fail the build if tests fail (exit code 1 or 2)
cicd-runner --suite-id $SUITE_ID
```

**Example: Continue on test failure**
```bash
# This will continue even if tests fail
cicd-runner --suite-id $SUITE_ID || true
```

**Example: Custom handling based on exit code**
```bash
cicd-runner --suite-id $SUITE_ID
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
  echo "All tests passed!"
elif [ $EXIT_CODE -eq 1 ]; then
  echo "Some tests failed, but runner executed successfully"
  # Could send notification, create issue, etc.
elif [ $EXIT_CODE -eq 2 ]; then
  echo "Runner error occurred"
  # Could alert ops team, retry, etc.
fi

exit $EXIT_CODE
```

## Output Format

The runner produces two types of output:

### 1. Log Output (stderr)

Log messages are written to stderr and include:

- Timestamp
- Log level (INFO, WARNING, ERROR, DEBUG)
- Component name
- Message

**Example log output**:
```
2024-01-15 10:30:45,123 INFO [auth.oauth_client] Authenticating with OAuth client credentials...
2024-01-15 10:30:45,456 INFO [auth.oauth_client] Successfully authenticated
2024-01-15 10:30:45,789 INFO [api.test_suites] Fetching test suite: 01234567-89ab-cdef-0123-456789abcdef
2024-01-15 10:30:46,012 INFO [api.test_suites] Found test suite: Smoke Tests
2024-01-15 10:30:46,234 INFO [main] Creating execution records...
```

### 2. Summary Table (stdout)

<<<<<<< HEAD
After execution completes, a formatted ASCII table is printed to stdout with the execution summary:

```
╔════════════════════════════════════════════════════════════╗
║           Nova Act QA Studio - CI/CD Runner                ║
╠════════════════════════════════════════════════════════════╣
║ Suite: Smoke Tests                                         ║
║ Suite Execution ID: 98765432-10ab-cdef-0123-456789abcdef   ║
║ Started: 2024-01-15 10:30:45                               ║
║ Completed: 2024-01-15 10:35:12                             ║
║ Duration: 4m 27s                                           ║
╠════════════════════════════════════════════════════════════╣
║ Use Case                          Status      Duration     ║
╠════════════════════════════════════════════════════════════╣
║ Login Flow                        ✓ PASSED         45s     ║
║ Search Functionality              ✓ PASSED         32s     ║
║ Checkout Process                  ✗ FAILED       1m 15s    ║
║ User Profile Update               ✓ PASSED         28s     ║
╠════════════════════════════════════════════════════════════╣
║ Total: 4  |  Passed: 3  |  Failed: 1  |  Success: 75%     ║
╚════════════════════════════════════════════════════════════╝
```

**Summary Table Fields**:

- **Suite**: Name of the test suite
- **Suite Execution ID**: Unique identifier for this execution (can be used to retrieve artifacts)
- **Started**: Timestamp when execution started (UTC)
- **Completed**: Timestamp when execution completed (UTC)
- **Duration**: Total execution time in human-readable format
- **Use Case**: Name of each test case in the suite
- **Status**: Pass/fail status for each test case
  - `✓ PASSED`: Test case passed all steps
  - `✗ FAILED`: Test case failed one or more steps
- **Duration**: Execution time for each test case
- **Total**: Total number of test cases
- **Passed**: Number of test cases that passed
- **Failed**: Number of test cases that failed
- **Success**: Success rate as a percentage
=======
After execution completes, a plain text summary is printed to stdout:

```
QA Studio - CI/CD Runner

Suite: Smoke Tests
Suite Execution ID: 98765432-10ab-cdef-0123-456789abcdef
Started: 2024-01-15 10:30:45
Completed: 2024-01-15 10:35:12
Duration: 4m 27s

✓ Login Flow (45s)
✓ Search Functionality (32s)
✗ Checkout Process (1m 15s)
✓ User Profile Update (28s)

Total: 4  |  Passed: 3  |  Failed: 1  |  Success: 75%
```

**Summary Fields**:

- **Suite**: Name of the test suite
- **Suite Execution ID**: Unique identifier for this execution (can be used to retrieve artifacts)
- **Started/Completed**: Timestamps in UTC
- **Duration**: Total execution time
- **✓ / ✗**: Pass/fail status per use case with individual duration
- **Total/Passed/Failed/Success**: Aggregate counts and success rate
>>>>>>> 781b54a (finish mergin main)

### Parsing Output

The summary table is designed to be human-readable but can also be parsed programmatically:

**Example: Extract suite execution ID**
```bash
OUTPUT=$(cicd-runner --suite-id $SUITE_ID)
EXECUTION_ID=$(echo "$OUTPUT" | grep "Suite Execution ID:" | awk '{print $4}')
echo "Execution ID: $EXECUTION_ID"
```

**Example: Check for failures**
```bash
OUTPUT=$(cicd-runner --suite-id $SUITE_ID)
if echo "$OUTPUT" | grep -q "✗ FAILED"; then
  echo "Some tests failed"
fi
```

## Progressive Usage Examples

### Level 1: Basic Execution

Start with the simplest possible execution:

```bash
cicd-runner --suite-id 01234567-89ab-cdef-0123-456789abcdef
```

This executes the test suite with all default settings.

### Level 2: Environment-Specific Testing

Test against a specific environment:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com
```

### Level 3: Variable Overrides

Customize test behavior with variables:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com \
  --var username=staging_user \
  --var password=staging_pass
```

<<<<<<< HEAD
### Level 4: Regional Testing

Test from different geographic regions:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com \
  --var username=staging_user \
  --var password=staging_pass \
  --region eu-west-1
```

### Level 5: Advanced Configuration
=======
### Level 4: Advanced Configuration
>>>>>>> 781b54a (finish mergin main)

Full control with all options:

```bash
cicd-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com \
  --var username=staging_user \
  --var password=staging_pass \
<<<<<<< HEAD
  --var api_key=test_key_123 \
  --region eu-west-1 \
  --model-id anthropic.claude-3-5-sonnet-20240620-v1:0 \
=======
  --model-id nova-act-v1.0 \
>>>>>>> 781b54a (finish mergin main)
  --timeout 7200 \
  --verbose
```

## Common Patterns

### Testing Multiple Environments

Use shell variables to test the same suite against multiple environments:

```bash
for ENV in staging production; do
  echo "Testing $ENV environment..."
  cicd-runner \
    --suite-id $SUITE_ID \
    --base-url https://$ENV.example.com \
    --var environment=$ENV
done
```

### Conditional Execution

Execute different suites based on conditions:

```bash
if [ "$BRANCH" = "main" ]; then
  SUITE_ID="production-suite-id"
else
  SUITE_ID="staging-suite-id"
fi

cicd-runner --suite-id $SUITE_ID
```

### Retry on Failure

Retry failed executions with exponential backoff:

```bash
MAX_RETRIES=3
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  cicd-runner --suite-id $SUITE_ID && break
  
  RETRY_COUNT=$((RETRY_COUNT + 1))
  if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
    WAIT_TIME=$((2 ** RETRY_COUNT))
    echo "Retry $RETRY_COUNT/$MAX_RETRIES after ${WAIT_TIME}s..."
    sleep $WAIT_TIME
  fi
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
  echo "Failed after $MAX_RETRIES retries"
  exit 1
fi
```

### Parallel Execution

Execute multiple suites in parallel:

```bash
# Start multiple runners in background
cicd-runner --suite-id $SUITE_ID_1 &
PID1=$!

cicd-runner --suite-id $SUITE_ID_2 &
PID2=$!

cicd-runner --suite-id $SUITE_ID_3 &
PID3=$!

# Wait for all to complete
wait $PID1
EXIT1=$?

wait $PID2
EXIT2=$?

wait $PID3
EXIT3=$?

# Check if any failed
if [ $EXIT1 -ne 0 ] || [ $EXIT2 -ne 0 ] || [ $EXIT3 -ne 0 ]; then
  echo "One or more suites failed"
  exit 1
fi
```

## Troubleshooting

### Command Not Found

**Error**: `cicd-runner: command not found`

**Solution**: Ensure the runner is installed and in your PATH:
```bash
pip install cicd-runner
# or
pip install -e /path/to/cicd-runner
```

### Invalid Suite ID

**Error**: `API request failed: 404 - Test suite not found`

**Solution**: Verify the suite ID is correct and exists in the platform:
```bash
# Check suite ID format (should be a UUID)
echo $SUITE_ID

# Verify suite exists via API or platform UI
```

### Variable Format Error

**Error**: `Variable must be in key=value format`

**Solution**: Ensure variables use the correct format:
```bash
# Correct
--var username=testuser

# Incorrect
--var username testuser
--var "username: testuser"
```

### Timeout Issues

**Error**: `Execution timed out after 3600 seconds`

**Solution**: Increase the timeout for large test suites:
```bash
cicd-runner --suite-id $SUITE_ID --timeout 7200
```

## See Also

- [Configuration Reference](configuration.md) - Environment variables and configuration
- [Installation Guide](installation.md) - Setup and prerequisites
- [Troubleshooting Guide](troubleshooting.md) - Common errors and solutions
- [CI/CD Integration](ci-cd-integration/) - Platform-specific examples
