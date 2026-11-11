# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Features

- **Delete selected use cases from the application page.** The **Usecases** tab dropdown of an application has **Delete selected (n)** after **Remove selected (n)**: same typed confirmation, `DELETE usecase/{id}` batching and result notices as the **Use Cases** page (shared `hooks/useBatchDelete.ts`), then the tab reloads. No API, scope or config change; the server still requires `api/usecases.write` and full access.
- **Cost allocation per use case, application and overall.** A daily `cost_collector` Lambda (worker stack, `${baseName}-costcollector`, EventBridge schedule `costAllocation.scheduleUtc`, default 06:00 UTC) splits the real Cost Explorer bill (`UnblendedCost`) of Nova Act (by `ListActs` agent seconds) and Lambda MicroVM compute (by VM seconds from `microvm_started_at` / `microvm_terminated_at`, launches for the snapshot usage types) over the use cases that used them, rolls up to applications and overall, writes one NDJSON ledger per dimension under `cost_allocation/` in the artefacts bucket and a `USAGE#… / SUMMARY` item per dimension (1 / 7 / 30-day windows, trend with a ±5 % dead band, list price as a secondary figure, `unassigned` / `unallocated` / `unmetered` buckets). Re-process or backfill with `aws lambda invoke --function-name <baseName>-costcollector --cli-binary-format raw-in-base64-out --payload '{"days":["YYYY-MM-DD"]}'` or `'{"from":"…","to":"…"}'` (self-continues past the 15-minute budget). New config block `costAllocation` (`enabled`, `scheduleUtc`, `lookbackDays`, `novaActServiceName`, `compute.*`). Alarms `${baseName}-cost-collector-errors` and `${baseName}-cost-collector-unmetered` (`UnmeteredUsd > 0.5 × BilledUsd`, namespace `QAStudio/CostAllocation`) on the notification topic. Execution records gain `microvm_started_at` / `microvm_terminated_at`, written at the terminal transition.
- New read routes `GET /applications/{id}/costs`, `GET /usecase/{id}/costs`, `GET /dashboard/costs` (existing scopes `api/applications.read` / `api/usecases.read` plus view on the resource; `overall` for studio admins only; `api` stack 489 / 500 resources). UI: **Cost (30d)** on every dashboard application card and **Overall cost · 30d** for admins, a **Cost** tab on the application detail page (windows, 30-day bar chart, per-use-case table), the **Cost** card next to **Use Case Information** on the use case page. New UI test case `testcases/app/uj17_cost_views.json`.
- `qa-studio` API client: transient responses (`429`, `500`, `502`, `503`, `504`, connection errors) are retried 7× with exponential-jitter backoff (1 → 16 s, +3 s jitter, ≈ 1 min) instead of 3× within ~3 s, so a suite fan-out on MicroVMs survives the API-throttling burst of its first seconds; retries are logged as `API retry n/7 in Ns`.
- **Lambda MicroVM worker (replaces ECS Fargate).** Every cloud execution and every wizard session now runs on its own Lambda MicroVM cloned from one `AWS::Lambda::MicrovmImage`; `execute_usecase` and `start_wizard_session` call `RunMicrovm` (`NO_INGRESS`, `maximumDurationInSeconds`, log stream = execution / session id, per-run input in the ≤ 4096-byte `runHookPayload`). Measured on dev: `PENDING → RUNNING` 6–16 s (Fargate: 30–60 s), a single web use case `success` ~90 s after the API call, a 20-use-case suite fully started in 15.7 s, stop → VM gone in ~22 s.
- `configuration.json`: `maxExecutionDurationMinutes` (default 60, max 480) caps a batch execution, `maxWizardSessionMinutes` (default 240, max 480) caps a wizard session; both become the VM's `maximumDurationInSeconds`. A run that exceeds its cap is marked `failed` with `timeout: run exceeded the configured ceiling of Ns`.
- Worker image: `supervisor.py` is the image `ENTRYPOINT`; it serves the MicroVM lifecycle hooks on :8080, spawns `qa-studio run` (batch) or `wizard_worker.py` (wizard) from a validated `RunPayload`, enforces a soft timeout 180 s before the ceiling and terminates its own VM when the child exits. The worker stack builds the image from an S3 zip of the `.dockerignore`-filtered repo root — **no Docker or Podman on the deploying machine** — and logs to `/qa-studio/<baseName>/microvm`.
- `qa-studio run` handles SIGTERM: tears down the browser and live view, marks in-flight executions `failed` with `terminated: …` (exit `143`) or `timeout: …` (exit `3`, `QA_STUDIO_TERMINATION_REASON=timeout`, ceiling from `QA_STUDIO_MAX_DURATION_SECONDS`). `wizard_worker.py` turns SIGTERM into `SystemExit(143)` so its browser cleanup runs.
- `POST /usecase/{id}/executions/{executionId}/stop` writes `stopped` first, then `TerminateMicrovm`; response carries `microvmId`. `POST /wizard/start` returns `201 {sessionId, usecaseId, status, microvmId}`; `POST /wizard/{sessionId}/terminate/{usecaseId}` writes `success` before terminating the VM and returns `{status: terminated, microvmId}`.
- `PATCH /usecase/{id}/executions/{executionId}/status` returns `409 {"error": "execution already terminal"}` for a different status on a terminal record and `200` (no-op) for the same one; the terminal transition (event, suite counters, cache wipe, tracking record) lives in `execution_transitions.finalize_terminal_transition`.
- New `RUNNING_EXECUTIONS` / `EXECUTION#{execution_id}` tracking record (`mode` = `batch` | `wizard`) for in-flight VMs, deleted on every terminal transition; `reconcile_executions` Lambda (every 5 min) marks executions whose VM is `TERMINATED`/missing or past deadline as `failed` (`reconciler: …`), publishes `QAStudio/Worker` `RunningMicrovms` / `ReconciledExecutions`, alarm on `ReconciledExecutions > 0` → notification topic. It replaces the ECS task-state-change handler.
- Execute response for `Scheduled`/`OnDemandHeadless`: `{"status": "microvm started", "microvmId", "cloudWatchLogsUrl", …}`.
- **AgentCore browsers in an imported VPC**, to test websites that are only reachable inside a VPC: setting `vpcId` attaches every batch and wizard browser to that VPC (`networkMode: VPC`). The worker stack looks the VPC up, checks the subnets against the AgentCore-supported AZs at synth, uses `workerSecurityGroupId` or creates one security group (all outbound, no inbound) and sets `AGENT_CORE_VPC` / `AC_VPC_ID` / `AC_SUBNET_IDS` / `AC_SECURITY_GROUP_ID` on the worker image. The customer's VPC is otherwise never changed: no subnets, routes, NAT gateways or endpoints. Without `vpcId` nothing changes (PUBLIC browsers, no EC2 resource).
- New optional `vpcSubnetIds` (subnets for the browser ENIs, in order); default: every private and isolated subnet of `vpcId` in a supported AZ. The browser now receives all of them (`AC_SUBNET_IDS`, comma-separated) instead of one (`AC_SUBNET_ID`).

### Bug Fixes

- `GET /usecase/{id}/costs` and `GET /applications/{id}/costs` returned `500` (`AccessDenied … s3:ListBucket`) for a use case or application without a ledger file yet, and the UI showed an error instead of *No cost data yet*. The application router role now has `s3:ListBucket` on the artefacts bucket, limited to `s3:prefix = cost_allocation/*`, so S3 answers a missing ledger with `NoSuchKey` and the routes return `200 {summary: null, days: []}`. Needs `npm run deploy:lambdas`.

### Removed

- ECS cluster, task definition, task/execution roles, ECR repository, `cdk-ecr-deployment`, `DockerImageAsset`, `entrypoint.sh`, `WORKER_MODE`, the `workerRuntime` feature flag of phase 1.
- The worker VPC (two NAT gateways, five VPC endpoints) and the ECS worker security group. A deploy without `vpcId` creates no VPC any more; VPC-attached browsers need an existing VPC (`vpcId`).
- `handle_task_state_change` Lambda and its `TaskStateChangeRule` (table scan by `task_arn`).
- Configuration keys `workerRuntime`, `dockerImageVersion` — `loadConfig()` now rejects them (see Release notes).

### Deprecated

- `agentCoreVPC` (`vpcId` alone attaches the browsers) and `createVpcEndpoints` (no endpoints are created): accepted, ignored, one `Configuration warning: <key> is deprecated and ignored (…)` line each. `vpcId` with `agentCoreVPC: false` fails the synth.
- Use-case-level `OnDemand` (SQS) trigger on `POST /usecase/{id}/execute` (`400`); the suite-level `OnDemand` trigger is unchanged.
- `ECS_*`, `SUBNET_ID`, `SECURITY_GROUP_ID`, `LOG_GROUP_NAME`, `LOG_STREAM_PREFIX`, `WORKER_RUNTIME` Lambda env vars; `task_arn` / `task_id` are no longer written on execution records.

### Other Changes

- `aws-cdk-lib` 2.275.0 / `aws-cdk` 2.1146.1 (`CfnMicrovmImage`); Lambda and worker `boto3`/`botocore` pinned ≥ 1.43.35 (`lambda-microvms` client). `execute_usecase` / `start_wizard_session` need `lambda:PassNetworkConnector` on the managed connector ARNs.
- Stack sizes after the removal: worker 118 resources, lambdas 399 / 500.
- Docs: architecture (MicroVM-only component and sequence diagrams, stop/timeout paths, reconciler, data model, quotas, monitoring, cost), worker README (supervisor lifecycle, hooks, `RunPayload`, image env, local repro, wizard termination), development (deploy without a container tool, image build time, local supervisor run), configuration (removed keys, MicroVM worker environment), troubleshooting (MicroVM runbook), CI/CD (exit codes 143 / 3, termination env vars; nothing changes for CI runners), API reference (execute/stop/wizard responses, status 409).

### Release notes

**Operator action required before deploying this version.**

1. Delete `workerRuntime` and `dockerImageVersion` from `web-app/configuration.json` — `loadConfig()` fails the synth with `Configuration error: <key> was removed (the worker runs on Lambda MicroVMs, without ECS); see the release notes` while one of them is present. Remove `agentCoreVPC` / `createVpcEndpoints` too (deprecated, ignored). Keep `vpcId` (and `workerSecurityGroupId`) only if the browsers must reach sites inside that VPC; the worker itself no longer runs there. Previously `vpcId` without `agentCoreVPC: true` only placed ECS in the VPC — such a configuration now makes the browsers VPC-attached, so drop `vpcId` if that is not wanted.
2. Optionally set `maxExecutionDurationMinutes` (default 60) and `maxWizardSessionMinutes` (default 240) if your longest test or wizard session needs more.
3. Docker/Podman and `CDK_DOCKER` are no longer needed; the image build happens in AWS Lambda and adds 3–5 minutes to the first worker deploy and to every worker deploy that changes `web-app/worker/` or `qa-studio-cli/`.
4. `cdk.context.json` is a local cache; without `vpcId` its `vpc-provider:…` entries can be deleted. With `vpcId`, synth needs AWS credentials and the AWS CLI (VPC lookup, AgentCore AZ check), see [Configuration → AgentCore browsers in a VPC](../docs/configuration.md#agentcore-browsers-in-a-vpc).
5. The deploy removes the stack-created VPC (NAT gateways, endpoints), the ECS cluster and the ECR repository in one CloudFormation update (~7 min for the VPC); an imported `vpcId` VPC is never deleted. Any execution that is still `running` on ECS at deploy time is orphaned: ECS-era records (`task_arn` only) are all terminal by now; the stop endpoint rejects them with `400 execution has no associated MicroVM`.
6. Check the regional MicroVM quotas once: `L-CD1C0CC4` (ARM64 MicroVM memory, 2048 GB default, 1 GB per concurrent run) and `RunMicrovm` 5/s (burst 5; a suite fan-out retries `ThrottlingException` 5×).
7. New alarm `<baseName>-reconciled-executions` on the notification topic; steady state is 0. Debugging of worker runs is CloudWatch-only (`/qa-studio/<baseName>/microvm`, stream = execution id).

## [0.1.1-27] - 2026-01-13

### Features

- Add AgentCore VPC support, fix configuration validation, and update documentation (38bfa99)

### Bug Fixes

- Replace pre-compiled binaries with Go source code for proper deployment (ecbf634)

### Other Changes

- Merge pull request #84 from aws-samples/feature/vpc-agentcore-support-v26 (4806edd)
- Change AgentCoreVPC to agentCoreVPC in configuration (ce80cef)
- Release, Fix Bucket and Changelog scripts (96952be)
- Remove pre-built Lambda binaries and fix frontend build directory tracking (f688b50)
- Add pre-built Lambda bootstrap binaries for deployment-ready package (8750515)
- Clean up Lambda binaries and fix frontend build directory tracking (4f2eb54)
- Fix build folder inside frontend, so deployment can move forward (fc97a08)
- 76 remove the headless option (b3d65ba)

All notable changes to this project will be documented in this file.

## [0.1.1-26] - 2025-12-18

### Other Changes

- Update README Instructions according to changes made (5499139)

All notable changes to this project will be documented in this file.

## [0.1.1-25] - 2025-12-18

### Other Changes

- Fix config.json.sample (a61220a)

All notable changes to this project will be documented in this file.

## [0.1.1-24] - 2025-12-18

### Bug Fixes

- Skip Lambda build/cleanup in release script - binaries are pre-built (7e54946)

### Chores

- version bump to 0.1.1-23 and changelog update (811ecd2)

### Other Changes

- Initial commit: Nova Act QA Studio v0.1.1-22 with new VPC support (dca15d2)
- Initial commit: Nova Act QA Studio v0.1.1-22 with new VPC support (eb0824c)

All notable changes to this project will be documented in this file.

## [0.1.1-23] - 2025-12-18

### Other Changes

- Initial commit: Nova Act QA Studio v0.1.1-22 with new VPC support (dca15d2)
- Initial commit: Nova Act QA Studio v0.1.1-22 with new VPC support (eb0824c)

