# Worker: Nova Act Test Execution Container

The worker is a Fargate container that runs test executions. Since the CLI-unified-runner refactor, the container is a thin shell around the `qa-studio` CLI: `entrypoint.sh` translates ECS environment variables into CLI flags and execs `qa-studio run`. The CLI performs all test execution, talks to the public API for state changes, and uploads artifacts via presigned URLs.

Wizard-mode tasks (interactive step-by-step execution with a persistent browser) still use the legacy `wizard_worker.py` path. That migration is tracked in a separate spec.

See [`docs/architecture.md`](../../docs/architecture.md) for the full cross-stack picture and execution sequence diagrams.

## Container Lifecycle

```
ECS task starts
      │
      ▼
entrypoint.sh reads WORKER_MODE
      │
      ├── WORKER_MODE=batch (default)
      │       resolve API URL + Cognito token endpoint from SSM
      │       ensure OAUTH_CLIENT_ID/SECRET (from ECS secrets:) present
      │       exec qa-studio run --browser agentcore \
      │           --usecase-id $USECASE_ID \
      │           --execution-id $EXECUTION_ID \
      │           --region $AWS_REGION
      │
      └── WORKER_MODE=wizard
              exec python wizard_worker.py        (legacy path, unchanged)
```

## Authentication (Batch Mode)

The CLI authenticates against Cognito using OAuth 2.0 Client Credentials flow. Credentials come from ECS:

- The auth stack provisions a dedicated M2M `UserPoolClient` and stores `{client_id, client_secret}` in Secrets Manager.
- The worker task definition uses ECS `secrets:` to inject those two values as `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET` at container start.
- The Cognito token endpoint and the API URL are published to SSM parameters; the entrypoint reads both at startup.

The CLI's `TokenResolver` picks up `OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` / `OAUTH_TOKEN_ENDPOINT` from env automatically.

## File Layout

```
worker/
├── Dockerfile                # Multi-stage: installs qa-studio[runner,agentcore]
├── entrypoint.sh             # WORKER_MODE branch; env→flag translation
├── wizard_worker.py          # Wizard mode only (legacy)
├── recording_controller.py   # Wizard mode only
├── extension_helper.py       # Wizard mode only
├── requirements.txt          # Python deps for wizard_worker + CLI runtime
└── README.md                 # this file
```

Batch-mode Python (dispatcher, step executors, trajectory manager, browser provisioning) lives in `qa-studio-cli/` and is installed into the container via `pip install -e /build/qa-studio-cli[runner,agentcore]` at image build time. The Docker build context is the **repo root** so the Dockerfile can COPY both `web-app/worker/` and the sibling `qa-studio-cli/` package. A `.dockerignore` at the repo root keeps the build context small.

## Environment Variables

Set by the CDK worker stack task definition:

### Required in batch mode

| Variable | Source | Purpose |
|---|---|---|
| `USECASE_ID` | Execute Lambda → ECS RunTask overrides | Identifies which use case to run |
| `EXECUTION_ID` | Execute Lambda → ECS RunTask overrides | Pre-created execution record the runner attaches to |
| `QA_STUDIO_API_URL_SSM` | worker-stack | SSM parameter name the entrypoint resolves to the real API URL |
| `QA_STUDIO_TOKEN_ENDPOINT_SSM` | worker-stack | SSM parameter name for Cognito's `/oauth2/token` |
| `OAUTH_CLIENT_ID` | ECS `secrets:` → Secrets Manager | M2M client ID |
| `OAUTH_CLIENT_SECRET` | ECS `secrets:` → Secrets Manager | M2M client secret |
| `BEDROCK_EXECUTION_ROLE` | worker-stack | IAM role AgentCore browsers assume |
| `S3_BUCKET` | worker-stack | Artefact bucket the AgentCore browser recording lands in |

### Required in wizard mode

Legacy `wizard_worker.py` still reads `DYNAMO_TABLE`, `S3_BUCKET`, `SESSION_ID`, `WIZARD_QUEUE_URL` etc. as before — unchanged by the refactor.

### Common

| Variable | Default | Purpose |
|---|---|---|
| `WORKER_MODE` | `batch` | `batch` (CLI) or `wizard` (legacy) |
| `AWS_REGION` | task definition | Forwarded to `qa-studio run --region` in batch mode |
| `ENABLE_TRAJECTORY_REPLAY` | `true` | Set to `false` to skip trajectory replay for navigation steps |
| `AGENT_CORE_VPC` | `false` | When `true`, AgentCore browsers are VPC-attached |
| `AC_VPC_ID` / `AC_SUBNET_ID` / `AC_SECURITY_GROUP_ID` | — | Required when `AGENT_CORE_VPC=true` |
| `USE_NOVA_ACT_GA` | `true` | Selects Nova Act GA Workflow (`true`) vs preview API (`false`) |
| `NOVA_ACT_API_KEY_NAME` | — | Secrets Manager secret name, required when `USE_NOVA_ACT_GA=false` |
| `NOVA_ACT_S3_BUCKET` | — | S3 bucket used by Nova Act Workflow storage |
| `QA_STUDIO_VERBOSE` | `false` | Adds `--verbose` to the CLI invocation for log-level debugging |

## Build and Deploy

The CDK `worker-stack.ts` builds the image using a `DockerImageAsset` with `directory: '..'` (repo root) and `file: 'web-app/worker/Dockerfile'`. Deploy with:

```bash
cd web-app
npm run deploy:worker
```

For a fresh build of everything:

```bash
npm run deploy
```

See [`docs/development.md`](../../docs/development.md) for the full list of `npm run deploy:*` targets.

## Running Locally

The unified runner means you can drive an execution from your laptop without the container. See [`docs/development.md` → Running the Unified Runner Locally](../../docs/development.md#running-the-unified-runner-locally) for:

- Running against a deployed stack with `qa-studio run`.
- Attaching to a pre-created execution with `--execution-id`.
- Reproducing the worker container locally with `docker run`.

## Event Emission

After the CLI finishes a batch execution, it PATCHes the final execution status through the API. The existing `update_execution_status` Lambda emits the `usecase.execution.completed` EventBridge event (`Source=qa-studio.api`). The container no longer talks to EventBridge directly.

Event payload is unchanged:

```json
{
  "Source": "qa-studio.api",
  "DetailType": "usecase.execution.completed",
  "Detail": {
    "usecase_id": "uc_abc123",
    "execution_id": "exec_xyz789",
    "execution_status": "success",
    "timestamp": "2026-04-30T14:32:45.123456Z"
  }
}
```

## Trajectory Replay

When NovaAct is built with `replayable=True` support, the CLI records a trajectory JSON for each successful navigation step and persists it via the API's trajectory-upload-URL endpoint. On subsequent runs, the runner requests the download URL, replays the trajectory via NovaAct's internal `ProgramRunner`, and skips the LLM call. Typical speedup: 5–10×.

Replay failures fall through to a fresh Nova Act call and clear the stale pointer via the `clear_cache_fields` extension on the step-status endpoint.

Controlled by `ENABLE_TRAJECTORY_REPLAY` (default `true`).

## Troubleshooting

### "QA_STUDIO_API_URL not set and QA_STUDIO_API_URL_SSM not provided"

The entrypoint couldn't resolve the API URL. Check:
1. The `QA_STUDIO_API_URL_SSM` env var is set by worker-stack.ts and points at a parameter path like `/qa-studio/{baseName}/api-url`.
2. The api-stack has been deployed (it writes the parameter).
3. The task role has `ssm:GetParameter` on that parameter ARN.

### "OAUTH_CLIENT_ID must be injected by ECS secrets"

The ECS `secrets:` injection failed to populate the env var. Check:
1. The `${baseName}-worker-m2m-credentials` secret exists in Secrets Manager.
2. The secret value is valid JSON with `client_id` and `client_secret` fields.
3. The ECS execution role has `secretsmanager:GetSecretValue` on the secret ARN.

### CLI authentication errors

Look for the token endpoint in the container log output; the entrypoint logs the resolved URL before invoking the CLI. Confirm the Cognito app client is configured with `clientCredentials` flow and has the `api/executions.read` + `api/executions.write` scopes.

### Wizard mode

Wizard mode is unchanged. If wizard-mode tests fail, follow the legacy debugging flow: CloudWatch logs for the ECS task, DynamoDB items under `EXECUTION#{sessionId}`, SQS wizard command queue state.
