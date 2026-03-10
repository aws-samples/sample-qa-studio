# Worker: Nova Act Test Execution Engine

The worker is a containerized Python application that executes browser-based test cases using [Amazon Nova Act](https://aws.amazon.com/nova/act/). It runs on AWS Fargate as part of the serverless architecture. See the [Architecture](../README.md#architecture) section in the project root README for how it fits into the overall system.

It receives execution parameters via environment variables and orchestrates a remote browser session through [Amazon Bedrock AgentCore Browser Tool](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-browser.html) to carry out each test step.

## How It Works

1. An ECS Fargate task is launched with execution context passed in as environment variables (`USECASE_ID`, `EXECUTION_ID`, etc.)
2. The worker loads the execution definition, steps, variables, and headers from DynamoDB
3. A remote browser is created via Bedrock AgentCore (either in PUBLIC or VPC network mode)
4. Nova Act connects to the browser over CDP (Chrome DevTools Protocol) and navigates to the starting URL
5. Each step is executed sequentially. The worker stops on the first failure.
6. Artifacts (video recordings, screenshots, logs) are written to S3 via the Nova Act `S3Writer`
7. Step results and execution status are persisted back to DynamoDB
8. An EventBridge event is emitted after execution completes (success or failure) to trigger downstream processes

For the full architecture diagram and how the worker integrates with the API layer, SQS queue, and other services, see the [Architecture](../README.md#architecture) section.

## Event Emission

After each test execution completes, the worker emits a `usecase.execution.completed` event to EventBridge. This event triggers downstream processes such as cache building for step optimization.

### Event Structure

```json
{
  "Source": "qa-studio.worker",
  "DetailType": "usecase.execution.completed",
  "Detail": {
    "usecase_id": "uc_abc123",
    "execution_id": "exec_xyz789",
    "execution_status": "success",
    "timestamp": "2025-01-15T14:32:45.123456Z"
  }
}
```

### Fire-and-Forget Pattern

Event emission follows a fire-and-forget pattern:
- Failures are logged but do not affect test execution outcomes
- The worker continues normally even if EventBridge is unavailable
- No retries are attempted if event emission fails
- Test execution status is always updated before event emission

This ensures that adding event emission doesn't introduce new failure modes or impact test reliability.

## Cache Execution

The worker supports cached step execution to accelerate test runs by 40-60%. When a test case has caching enabled and navigation steps have cached actions available, the worker executes those actions directly using the Playwright API instead of calling Nova Act. This eliminates LLM inference latency (typically 2-5 seconds per step) while maintaining test reliability through automatic fallback.

### How Cache Execution Works

1. **Cache Eligibility Check**: Before executing a navigation step, the worker checks if:
   - The test case has `enable_cache=True` in its configuration
   - The step has `cached_steps` data available (populated by the cache builder after successful executions)

2. **Cache Hit Path** (Fast):
   - Parse the cached steps JSON (list of Playwright actions)
   - Execute each action sequentially using the Playwright API
   - Complete in 200-500ms (vs 2-5 seconds for Nova Act)
   - Return a cache result with `metadata.act_id="cached"`

3. **Cache Miss Path** (Normal):
   - No cached steps available or caching disabled
   - Execute step using Nova Act as usual
   - Log the reason for cache miss

4. **Cache Failure Path** (Automatic Fallback):
   - Cache execution fails (e.g., page structure changed)
   - Worker logs a warning with error details
   - Automatically falls back to Nova Act execution
   - Test continues normally without failure

### Cache Result Structure

When cache execution succeeds, the worker returns a result object compatible with Nova Act results:

```python
result.metadata.act_id = "cached"  # Identifies result as from cache
result.logs = ""                    # No Nova Act logs for cached execution
```

This structure ensures downstream validation logic works correctly regardless of whether cache or Nova Act was used.

### Cache Eligibility Criteria

Cache execution is attempted when **all** of the following conditions are met:

| Condition | Description |
|-----------|-------------|
| `enable_cache=True` | Test case has caching enabled in configuration |
| `cached_steps` exists | Step has cached actions available from previous execution |
| `cached_steps` non-empty | Cached steps JSON is not null or empty string |

If any condition is not met, the worker skips cache execution and calls Nova Act.

### Fallback Behavior

The worker automatically falls back to Nova Act in these scenarios:

| Scenario | Exception Type | Behavior |
|----------|---------------|----------|
| Invalid JSON | `JSONDecodeError` | Log warning, execute with Nova Act |
| Cache execution failure | `CacheExecutionError` | Log warning, execute with Nova Act |
| Unexpected error | `Exception` | Log warning, execute with Nova Act |

Fallback execution is identical to normal execution - the same instruction is used (including advanced click types if enabled), and the Nova Act result is returned unchanged. This ensures test reliability is never compromised by cache issues.

### Observability

The worker logs detailed information about cache execution:

| Event | Log Level | Message Format |
|-------|-----------|----------------|
| Cache hit | INFO | `Cache hit for step {sort} (executed in {duration_ms}ms)` |
| Cache miss (disabled) | INFO | `Cache miss for step {sort}: caching disabled` |
| Cache miss (no data) | INFO | `Cache miss for step {sort}: no cached steps available` |
| Cache failure | WARNING | `Cache execution failed for step {sort}: {error}, falling back to Nova Act` |
| JSON parse error | WARNING | `Failed to parse cached_steps for step {sort}: {error}, falling back to Nova Act` |

Use these logs to monitor cache effectiveness and debug issues.

### Cached Action Types

The cache executor supports these Playwright action types:

| Action | Description | Parameters |
|--------|-------------|------------|
| `click` | Click at element center | `bbox` (coordinates) |
| `hover` | Hover at element center | `bbox` (coordinates) |
| `type` | Click to focus, type text, optionally press Enter | `bbox`, `text`, `press_enter` |
| `scroll` | Scroll in direction by amount | `direction` (up/down/left/right), `value` (pixels) |
| `navigate` | Navigate to URL | `url` |

### Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `CACHE_ACTION_DELAY_MS` | `100` | Delay in milliseconds between cached actions. Increase for slower pages, decrease for faster execution. |

Example: Set `CACHE_ACTION_DELAY_MS=200` for pages that need more time to respond to interactions.

### Performance

Typical cache execution performance:

- **Cache eligibility check**: < 1ms
- **JSON parsing**: 1-5ms
- **Cache execution**: 200-400ms (5-10 actions with 100ms delays)
- **Total cache path**: 200-500ms
- **Nova Act execution**: 2-5 seconds per step
- **Speedup**: 5-10x faster with cache

### Integration with Cache Builder

Cache execution integrates with the cache builder system:

1. **First Execution**: Test runs normally using Nova Act, cache builder processes the execution and stores cached steps
2. **Subsequent Executions**: Worker detects cached steps and executes them directly
3. **Cache Updates**: Cache builder updates cached steps after each successful execution to adapt to page changes

For more details on the cache builder, see the [Cache Builder Lambda documentation](../lambdas/endpoints/README.md#cache-builder).

## Execution Modes

The `WORKER_MODE` environment variable controls which mode the worker runs in:

### Batch Mode (default)

Runs all steps in a test case sequentially and exits. Used for standard test execution triggered by the API or scheduler.

### Wizard Mode

Maintains a persistent browser session and listens for commands (via DynamoDB polling or SQS). Used by the interactive wizard in the frontend, where users build test cases step-by-step with a live browser preview. Supports `execute_step`, `restart`, and `terminate` commands. Sessions time out after 30 minutes of inactivity.

## Step Types

The worker supports multiple step types, including navigation, validation, secret handling, and more. Each has a dedicated handler module in the project structure below. For the full list and usage guidance, see the [Workflow Steps](../docs/user-guide.md#workflow-steps) section of the User Guide.

## Template Variables

Step instructions support `{{VariableName}}` template syntax. Variables are resolved at runtime from:

- User-defined variables passed with the execution
- Runtime variables captured by `retrieve_value` steps during execution
- Built-in variables: `{{UniqueID}}`, `{{Time}}`, `{{ExecutionID}}`, `{{CreatedAt}}`

## Nova Act Backend

The worker supports two Nova Act backends, controlled by the `USE_NOVA_ACT_GA` environment variable:

- **GA Service** (`true`): Uses the Nova Act managed service via `Workflow` and `boto3`. Requires `NOVA_ACT_S3_BUCKET`. No API key needed.
- **Preview API** (`false`, default): Uses the Nova Act SDK directly with an API key stored in Secrets Manager (`NOVA_ACT_API_KEY_NAME`).

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `USECASE_ID` | Yes | Test case identifier |
| `EXECUTION_ID` | Yes | Execution identifier |
| `S3_BUCKET` | Yes | S3 bucket for artifacts |
| `DYNAMO_TABLE` | Yes | DynamoDB table name |
| `AWS_REGION` | No | AWS region (default: `us-east-1`) |
| `WORKER_MODE` | No | `batch` (default) or `wizard` |
| `USE_NOVA_ACT_GA` | No | `true` to use GA service, `false` for Preview API |
| `NOVA_ACT_API_KEY_NAME` | Conditional | Secrets Manager secret name for the Nova Act API key (required when `USE_NOVA_ACT_GA` is `false`) |
| `NOVA_ACT_S3_BUCKET` | Conditional | S3 bucket for Nova Act workflow exports (required when `USE_NOVA_ACT_GA` is `true`) |
| `BEDROCK_EXECUTION_ROLE` | Yes | IAM role ARN for Bedrock AgentCore browser |
| `AGENT_CORE_VPC` | No | `true` to create browsers in VPC mode |
| `AC_VPC_ID` | Conditional | VPC ID (required when `AGENT_CORE_VPC` is `true`) |
| `AC_SUBNET_ID` | Conditional | Subnet ID (required when `AGENT_CORE_VPC` is `true`) |
| `AC_SECURITY_GROUP_ID` | Conditional | Security group ID (required when `AGENT_CORE_VPC` is `true`) |
| `LOGS_DIRECTORY` | No | Local log directory (default: `/app/logs`) |
| `CACHE_ACTION_DELAY_MS` | No | Delay in milliseconds between cached actions (default: `100`) |
| `SESSION_ID` | Conditional | Session identifier (wizard mode) |
| `WIZARD_QUEUE_URL` | Conditional | SQS queue URL for wizard commands (wizard mode) |

## Project Structure

```
worker/
├── worker.py                # Entry point, routes to batch or wizard mode
├── wizard_worker.py         # Wizard mode: persistent session with command loop
├── event_emitter.py         # EventBridge event emission for execution completion
├── cache_executor.py        # Cache execution: replay cached steps via Playwright API
├── nova_act_workflow.py     # Nova Act GA workflow definition management
├── browser.py               # Bedrock AgentCore browser lifecycle (create/start/delete)
├── navigation_step.py       # Navigation step execution with cache support
├── validation_step.py       # Validation step execution with type/operator matching
├── secret_step.py           # Secret step execution with Secrets Manager integration
├── retrieve_value_step.py   # Value retrieval and runtime variable capture
├── assertion_step.py        # Runtime variable assertion (no browser interaction)
├── url_step.py              # URL navigation step
├── download_step.py         # File download step with S3 upload
├── dynamodb_client.py       # DynamoDB operations for executions, steps, and status
├── secrets_client.py        # AWS Secrets Manager client
├── sqs_client.py            # SQS notification client
├── template_parser.py       # {{Variable}} template resolution
├── models.py                # Data models (Execution, ExecutionStep, etc.)
├── utils.py                 # Helpers (region, time, VPC config validation)
├── Dockerfile               # Multi-stage build: Python 3.13-slim
└── requirements.txt         # boto3, nova-act, bedrock_agentcore
```

## Docker

The worker uses a multi-stage Docker build based on `python:3.13.10-slim`. Playwright browser installation is skipped (`NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true`) since the browser runs remotely via Bedrock AgentCore.

Build the image:

```bash
docker build -t nova-act-worker ./worker
```

In production, the image is built and deployed automatically by the CDK stack.

## Dependencies

- `boto3`: AWS SDK
- `nova-act`: Amazon Nova Act SDK for browser automation
- `bedrock_agentcore`: Amazon Bedrock AgentCore Browser Tool client
