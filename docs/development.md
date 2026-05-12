# Development

This guide covers the commands and workflows for developing, deploying, and monitoring QA Studio. Make sure you've completed the [Getting Started](../README.md#getting-started) setup before diving in.

## Deploying Individual Components

If you need to update specific parts of the solution:

```bash
# Individual stack deployments
npm run deploy:storage
npm run deploy:auth
npm run deploy:api
npm run deploy:frontend
npm run deploy:notification
npm run deploy:worker
npm run deploy:routes
npm run deploy:frontend-deployment

# Utility commands
npm run build:lambdas        # Build Lambda functions
npm run clean:lambdas        # Clean build artifacts
npm run config:write         # Generate frontend config
npm run deploy:frontend-build # Build React app
```

## Commands Reference

### Main Deployment

- `npm run deploy`: Complete deployment (builds Lambdas + frontend, then deploys)
- `npm run deploy:release`: Deploy from release archive (skips builds, uses pre-built artifacts)

### Individual Stack Deployment

- `npm run deploy:storage`: Deploy storage stack (DynamoDB, S3, ECR)
- `npm run deploy:auth`: Deploy authentication stack (Cognito)
- `npm run deploy:api`: Deploy API Gateway stack
- `npm run deploy:frontend`: Deploy frontend infrastructure (CloudFront, S3)
- `npm run deploy:notification`: Deploy notification stack (SNS, SQS)
- `npm run deploy:worker`: Deploy worker stack (ECS Fargate)
- `npm run deploy:routes`: Deploy API routes and Lambda integrations
- `npm run deploy:frontend-deployment`: Deploy frontend assets to S3

### Utility Commands

- `npm run build:lambdas`: Build all Lambda functions for ARM64
- `npm run clean:lambdas`: Remove Lambda build artifacts
- `npm run config:write`: Generate frontend config from CloudFormation outputs
- `npm run dcv:download`: Download NICE DCV Web Client SDK (runs automatically during deployment)
- `npm run deploy:frontend-build`: Build React frontend application
- `npm run build`: Compile TypeScript CDK code
- `npm run watch`: Watch TypeScript files for changes

### CDK Commands

- `npx cdk diff`: Compare deployed stack with current state
- `npx cdk synth`: Generate CloudFormation templates
- `npx cdk destroy --all`: Delete all stacks (⚠️ deletes all data)

### Security & Compliance

- `npm run nag`: Run cdk-nag AwsSolutions checks against all stacks and generate a consolidated report

  This command:
  1. Compiles the CDK TypeScript code
  2. Runs `cdk synth` which triggers cdk-nag checks on all stacks (storage, auth, worker, lambdas, api, frontend)
  3. Collects per-stack JSON reports from `cdk.out/`
  4. Writes a consolidated report to `reports/cdk-nag-report.json`
  5. Prints a summary to stdout with per-stack breakdown
  6. Exits with code 1 if there are unsuppressed non-compliant findings

  Suppressions are managed in `lib/cdk-nag-suppressions.ts`. Each suppression requires a documented reason.

### Release Commands

- `npm run release:patch`: Create patch release (1.0.0 → 1.0.1)
- `npm run release:minor`: Create minor release (1.0.0 → 1.1.0)
- `npm run release:major`: Create major release (1.0.0 → 2.0.0)
- `npm run release:prerelease`: Create pre-release (1.0.0 → 1.0.1-beta.0)
- `npm run changelog`: Generate changelog from git commits


## Running the Unified Runner Locally

The cloud worker and the `qa-studio` CLI share a single execution runtime. In batch mode, ECS tasks invoke `qa-studio run` as their entrypoint (see `web-app/worker/entrypoint.sh`). That means you can reproduce a cloud execution on your laptop by running the same command with the right env.

### Against a deployed stack

```bash
# 1. Install the CLI with the remote-execution extras
pip install -e './qa-studio-cli[runner,agentcore]'

# 2. Configure the CLI (interactive; uses the user-facing Cognito client)
qa-studio configure

# 3. Run a use case remotely (execution record created server-side)
qa-studio run --usecase-id <uc-id>
```

### Attaching to a pre-created execution

This is the shape the cloud worker uses: another actor (the web UI or the `execute_usecase` Lambda) creates the execution record first, then the runner attaches.

```bash
# Create the execution via the API however you normally would, then:
qa-studio run \
  --usecase-id <uc-id> \
  --execution-id <exec-id> \
  --browser agentcore          # or `local` / `cdp-external`
```

### Browser selection

| `--browser` | When to use | Extras required |
|---|---|---|
| `local` (default) | Developer laptop runs against a locally launched Chromium | `[runner]` |
| `agentcore` | Cloud worker, or developer with Bedrock AgentCore access | `[runner,agentcore]` |
| `cdp-external` | Advanced: connect to a browser someone else provisioned via `--cdp-endpoint-url` / `--cdp-headers-file` | `[runner]` |

### Reproducing the worker container locally

```bash
# Build the worker image the same way CDK does (context = repo root)
docker build -f web-app/worker/Dockerfile -t qa-studio-worker .

# Run it with the same env the task definition injects
docker run --rm \
  -e WORKER_MODE=batch \
  -e USECASE_ID=<uc-id> \
  -e EXECUTION_ID=<exec-id> \
  -e QA_STUDIO_API_URL=https://<api>.execute-api.<region>.amazonaws.com/api/ \
  -e OAUTH_TOKEN_ENDPOINT=https://<domain>.auth.<region>.amazoncognito.com/oauth2/token \
  -e OAUTH_CLIENT_ID=<worker-m2m-client-id> \
  -e OAUTH_CLIENT_SECRET=<worker-m2m-client-secret> \
  -e BEDROCK_EXECUTION_ROLE=<role-arn> \
  -e S3_BUCKET=<artifact-bucket> \
  -e AWS_REGION=<region> \
  qa-studio-worker
```

The CDK-deployed worker resolves `QA_STUDIO_API_URL` and `OAUTH_TOKEN_ENDPOINT` from SSM automatically (via `QA_STUDIO_API_URL_SSM` / `QA_STUDIO_TOKEN_ENDPOINT_SSM`). For a local run you can either set them explicitly as shown above, or point at the SSM parameters directly if your local AWS creds allow it.
