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

- `npm run deploy:storage`: Deploy storage stack (DynamoDB, S3, Nova Act API key secret)
- `npm run deploy:auth`: Deploy authentication stack (Cognito)
- `npm run deploy:api`: Deploy API Gateway stack
- `npm run deploy:frontend`: Deploy frontend infrastructure (CloudFront, S3)
- `npm run deploy:notification`: Deploy notification stack (SNS, SQS)
- `npm run deploy:worker`: Deploy worker stack (`AWS::Lambda::MicrovmImage` + its build/execution roles and log group, artefact buckets, SQS queues, scheduler, execute/stop/wizard Lambdas, reconciler + alarm). Rebuilds the MicroVM image (3–5 min, CloudFormation waits) whenever anything under `web-app/worker/` or `qa-studio-cli/` changed — including README edits; otherwise the image is untouched and the deploy is quick. No Docker/Podman involved.
- `npm run deploy:routes`: Deploy API routes and Lambda integrations
- `npm run deploy:frontend-deployment`: Deploy frontend assets to S3

### Utility Commands

- `npm run build:lambdas`: Build all Lambda functions for ARM64
- `npm run clean:lambdas`: Remove Lambda build artifacts
- `npm run config:write`: Generate frontend config from CloudFormation outputs
- `npm run migrate:team-admin`: Migrate legacy `team-{id}-admin` groups to Team Lead (dry run unless `--apply`; runs with `--apply` during `npm run deploy`). See [User Management: Team admin migration](user-management.md#team-admin-migration)
- `npm run dcv:download`: Download NICE DCV Web Client SDK (runs automatically during deployment)
- `npm run deploy:frontend-build`: Build React frontend application
- `npm run build`: Compile TypeScript CDK code
- `npm run watch`: Watch TypeScript files for changes

### Tests

- `npm test` (or `npx jest`) in `web-app`: CDK and deploy-script tests (`lib/**/*.test.ts`, `scripts/**/*.test.ts`)
- `npx vitest run` in `web-app/frontend`: frontend tests
- `python3 -m pytest --ignore=dependencies -p no:cacheprovider` in `web-app/lambdas/endpoints`: Lambda tests
- `python3 -m pytest tests` in `web-app/worker` (after `pip install -e "./qa-studio-cli[runner]"`): wizard modules, the Dockerfile contract and the MicroVM supervisor

#### Structural guards

These tests check how the pieces are wired, not what a handler does. They run with the normal commands above.

| Test | Runs in | Fails when | Protects against |
|------|---------|-----------|------------------|
| `lib/__tests__/lambda-sources.test.ts` | jest | A Python Lambda built from a local `lambdas/*` asset has no `<module>.py` for its `Handler`, or the module does not define the handler function | A Lambda whose source was deleted: it still synthesizes and deploys, then fails every invocation with "Unable to import module" |
| `lib/__tests__/ownership-check-iam.test.ts` | jest | A Lambda whose handler runs the team ownership check lacks `TABLE_NAME` or `dynamodb:GetItem`; or a Lambda that presigns `put_object` / `get_object` URLs lacks `s3:PutObject` / `s3:GetObject` | Prod-only 500 "Authorization check failed"; presigned URLs that S3 rejects with 403 (trajectory upload/download) |
| `test_route_coverage.py::test_every_router_handler_module_is_routed` | pytest | A `handlers/*.py` module is missing from `application_router.ROUTE_MAP`, or a `ROUTE_MAP` entry has no module | Router handlers that are unreachable (dead) or a route that was never wired |
| `test_route_coverage.py` (other tests) | pytest | A routed handler skips `@require_resource_access` without an `ALLOWLIST` entry | Endpoints without the team ownership check |

The jest guards build the stacks with `lib/__tests__/synthStacks.ts` (offline, `configuration.json.sample`). Each run stages assets under `$TMPDIR/cdk.out*`; delete those when disk runs low.

#### Frontend dead-code check

| Script | Run in | Purpose | Default config | Exit code |
|--------|--------|---------|----------------|-----------|
| `npm run lint:dead` | `web-app/frontend` | [knip](https://knip.dev) (exact-pinned devDependency) reports unused files, exports, exported types and dependencies, and imports of packages missing from `package.json` | `knip.json`: project `src/**/*.{ts,tsx}`; entries `src/**/*.test.{ts,tsx}` plus what knip's Vite/Vitest plugins detect (`src/index.tsx`, `src/setupTests.ts`) | `0` clean, `1` findings |

To keep something knip reports, add it to `knip.json` with the reason next to it, e.g. `"ignore": ["src/foo.ts"]` for a file, or `"ignoreDependencies": ["pkg"]` for a package that is only loaded at runtime. Prefer deleting the code, or dropping `export` when only the module itself uses it. The script is not wired into a hook or CI yet.

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

The cloud worker and the `qa-studio` CLI share a single execution runtime. In batch mode the cloud worker — a Lambda MicroVM per execution — invokes `qa-studio run` from `web-app/worker/supervisor.py`. That means you can reproduce a cloud execution on your laptop by running the same command with the right env.

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

### Running the worker locally as the MicroVM supervisor

The VM runs `supervisor.py` (the image `ENTRYPOINT`), which receives the per-execution input as a `RunPayload` JSON string in the platform's `POST /aws/lambda-microvms/runtime/v1/run` hook and spawns `qa-studio run` itself. To reproduce that shape, build the image locally (this is the only place a local Docker/Podman is useful — the deployment does not need one), publish port 8080 on loopback only, and POST the hooks with `curl`:

```bash
docker build -f web-app/worker/Dockerfile -t qa-studio-worker .   # context = repo root

docker run --rm -p 127.0.0.1:8080:8080 \
  -e AWS_REGION=<region> -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e AWS_SESSION_TOKEN \
  -e QA_STUDIO_API_URL_SSM=/qa-studio/<baseName>/api-url \
  -e QA_STUDIO_TOKEN_ENDPOINT_SSM=/qa-studio/<baseName>/cognito-token-endpoint \
  -e WORKER_CREDENTIALS_SECRET_ARN=<worker-m2m-credentials secret ARN> \
  -e DYNAMODB_TABLE_NAME=<table> -e S3_BUCKET_PREFIX=<account>-<baseName>-artefacts -e SECRETS_PREFIX=<baseName> \
  -e NOVA_ACT_API_KEY_NAME=<secret name> -e BEDROCK_EXECUTION_ROLE=<role-arn> \
  qa-studio-worker

curl -XPOST http://127.0.0.1:8080/aws/lambda-microvms/runtime/v1/ready      # {"status":"ready", ...}
curl -XPOST -H 'Content-Type: application/json' \
  -d '{"microvmId":"local","runHookPayload":"{\"mode\":\"batch\",\"usecase_id\":\"<uc-id>\",\"execution_id\":\"<exec-id>\",\"execution_token\":\"<token>\",\"region\":\"<region>\",\"s3_bucket\":\"<account>-<baseName>-artefacts-<region>\",\"max_duration_s\":3600}"}' \
  http://127.0.0.1:8080/aws/lambda-microvms/runtime/v1/run                  # {"status":"started", ...}
curl -XPOST http://127.0.0.1:8080/aws/lambda-microvms/runtime/v1/terminate  # SIGTERM → runner reports failed/timeout
```

`AWS_REGION` must be passed by hand here (the platform injects it in a real VM). The self-`TerminateMicrovm` call fails locally and is only logged. The full hook table, the `RunPayload` fields and the image-level env list are in [`web-app/worker/README.md` → MicroVM supervisor](../web-app/worker/README.md#microvm-supervisor); the design is in `.kiro/docs/microvm-runner/design.md`. Without a container: `cd web-app/worker && WORKER_APP_DIR=$PWD python3 supervisor.py --host 127.0.0.1 --port 8080`.

### Deploying the worker

The MicroVM image is built by Lambda from an S3 zip of the `.dockerignore`-filtered repo root (`web-app/lib/worker-image-asset.ts`, a plain file copy at synth time), so **no Docker or Podman is needed on the deploying machine** — neither for `npm run deploy` nor for `npm run deploy:worker`. Prerequisites are the AWS CLI, Node.js and Python only.

Timing: a worker deploy whose `web-app/worker/` or `qa-studio-cli/` tree changed uploads a new zip and CloudFormation waits for the `AWS::Lambda::MicrovmImage` build — expect **3–5 minutes** on top of the usual stack update (the dev measurement was ~3 min for the full image). Build logs land in `/qa-studio/<baseName>/microvm`, stream `<version>/<build-id>`. A deploy without such changes leaves the image alone. Launches started during the deploy keep running on the previous image version; new launches use `latestActiveImageVersion` once the stack update completes.

Runtime ceilings are config changes (`maxExecutionDurationMinutes`, `maxWizardSessionMinutes` in `configuration.json`, see [Configuration](configuration.md)) followed by `npm run deploy:worker`. The removed ECS keys (`workerRuntime`, `dockerImageVersion`) are listed in [Configuration → Removed keys](configuration.md#removed-keys); `loadConfig()` refuses to synth while one of them is still present. `agentCoreVPC` / `createVpcEndpoints` are deprecated (warning, ignored); `vpcId` attaches the AgentCore browsers to an imported VPC ([Configuration → AgentCore browsers in a VPC](configuration.md#agentcore-browsers-in-a-vpc)).
