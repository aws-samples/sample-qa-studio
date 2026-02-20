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

For the full architecture diagram and how the worker integrates with the API layer, SQS queue, and other services, see the [Architecture](../README.md#architecture) section.

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
| `SESSION_ID` | Conditional | Session identifier (wizard mode) |
| `WIZARD_QUEUE_URL` | Conditional | SQS queue URL for wizard commands (wizard mode) |

## Project Structure

```
worker/
├── worker.py                # Entry point, routes to batch or wizard mode
├── wizard_worker.py         # Wizard mode: persistent session with command loop
├── nova_act_workflow.py     # Nova Act GA workflow definition management
├── browser.py               # Bedrock AgentCore browser lifecycle (create/start/delete)
├── navigation_step.py       # Navigation step execution
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
