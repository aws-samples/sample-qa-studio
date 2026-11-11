# Configuration

QA Studio is configured via `configuration.json` in the `web-app/` directory. Copy the sample file and edit it:

```bash
cp configuration.json.sample configuration.json
```

## Configuration Options

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `adminEmail` | string | Yes | — | Admin email for initial Cognito user pool setup |
| `baseName` | string | Yes | — | Base name for all AWS resources (lowercase, alphanumeric, hyphens only) |
| `apiEndpoint` | string | No | `"api"` | API Gateway endpoint path prefix |
| `apiDeploymentStage` | string | No | `"api"` | API Gateway deployment stage name |
| `enabledRegions` | string[] | No | `["us-east-1", "us-west-2", "ap-southeast-2", "eu-central-1"]` | AWS regions a use case can run in: a cross-region artefact bucket is created for each (it replicates into the default-region bucket; the recorder extension is uploaded to each), and runs and wizard sessions create their AgentCore browser in the use case's region and record into that region's bucket |
| `defaultRegion` | string | No | `"us-east-1"` | Default AWS region (must be in `enabledRegions`) |
| `bedrockModelId` | string | No | `"us.amazon.nova-2-lite-v1:0"` | Bedrock model ID for AI-powered test generation. See [Bedrock Model Selection](#bedrock-model-selection). |
| `useNovaActGa` | boolean | No | `true` | Use Nova Act GA API (vs preview) |
| `lambdaConcurrency` | number | No | `5` | Reserved concurrent executions per Lambda function. Controls max parallel invocations per function to prevent account concurrency exhaustion. Set to `0` to disable the limit. |
| `apiGatewayUrl` | string | No | — | Full API Gateway URL for local development proxy |
| `enableExtensionAuthentication` | boolean | No | — | Enable Kiro extension OAuth callback authentication |
| `cliCallbackUrl` | string | No | — | Callback URL for CLI OAuth flow (e.g. `"http://localhost:19847/callback"`) |
| `deviceFarmRegion` | string | No | `"us-west-2"` | AWS region for Device Farm mobile testing. Device Farm is only available in `us-west-2`. |
| `maxExecutionDurationMinutes` | number | No | `60` | Hard ceiling for a single batch execution, in minutes. Integer from `1` to `480` (480 = MicroVM platform limit, 8 h including suspended time). A run that exceeds it is marked `failed` with reason `timeout`. |
| `maxWizardSessionMinutes` | number | No | `240` | Hard ceiling for a single wizard session, in minutes. Integer from `1` to `480` (480 = MicroVM platform limit). Sessions still end after 30 min of inactivity; this cap bounds the total session length. |
| `vpcId` | string \| null | No | `null` | Existing VPC (`"vpc-…"`) the AgentCore browsers attach to (`networkMode: VPC`), to test websites that are only reachable inside it. `null` = PUBLIC browsers, no EC2 resources. See [AgentCore browsers in a VPC](#agentcore-browsers-in-a-vpc). |
| `vpcSubnetIds` | string[] \| null | No | `null` | Subnets of `vpcId` for the browser network interfaces, in this order (each `"subnet-…"`, unique, any subnet type). `null` = every private and isolated subnet of `vpcId` in an AgentCore-supported AZ. Requires `vpcId`. |
| `workerSecurityGroupId` | string \| null | No | `null` | Existing security group (`"sg-…"`) for the browser network interfaces. `null` = the stack creates one in `vpcId` (all outbound, no inbound). Requires `vpcId`. |
| `costAllocation` | object | No | see [Cost allocation](#cost-allocation) | Daily allocation of the Cost Explorer bill per use case, application and overall. Every key is optional; unknown keys fail `loadConfig()`. |

## Minimal Example

```json
{
  "adminEmail": "your-email@example.com",
  "baseName": "qa-studio"
}
```

## Full Example

```json
{
  "adminEmail": "your-email@example.com",
  "baseName": "qa-studio",
  "apiEndpoint": "api",
  "apiDeploymentStage": "api",
  "bedrockModelId": "us.amazon.nova-2-lite-v1:0",
  "enabledRegions": ["eu-central-1"],
  "defaultRegion": "eu-central-1",
  "useNovaActGa": true,
  "lambdaConcurrency": 5,
  "enableExtensionAuthentication": true,
  "cliCallbackUrl": "http://localhost:19847/callback",
  "deviceFarmRegion": "us-west-2",
  "maxExecutionDurationMinutes": 60,
  "maxWizardSessionMinutes": 240,
  "costAllocation": {
    "enabled": true,
    "scheduleUtc": "cron(0 6 * * ? *)",
    "lookbackDays": 3,
    "novaActServiceName": "NovaAct",
    "compute": {
      "enabled": true,
      "ceService": "AWS Lambda",
      "ceComputeUsageTypePrefixes": ["Lambda-MicroVM-vCPU-Second", "Lambda-MicroVM-Memory-GB-Second"],
      "ceSnapshotUsageTypePrefixes": ["Lambda-MicroVM-Snapshot-Read-GB", "Lambda-MicroVM-Snapshot-Storage-GB-Hour", "Lambda-MicroVM-Snapshot-Write-GB"]
    }
  }
}
```

## Cost allocation

The worker stack runs one Lambda, `cost_collector` (`${baseName}-costcollector`, 15 min, 1024 MB), on the `costAllocation.scheduleUtc` schedule. It reads the Cost Explorer bill (`UnblendedCost`) of the last `lookbackDays` days, splits it per use case by metered usage (Nova Act `ListActs` seconds; MicroVM seconds and launches for compute), rolls use cases up to their application and to an overall total, and writes one NDJSON ledger per dimension under `cost_allocation/` in the artefacts bucket plus a `USAGE#… / SUMMARY` item per dimension (design: [`.kiro/docs/cost-allocation/design.md`](../.kiro/docs/cost-allocation/design.md)). Re-processing a day: `aws lambda invoke --function-name <baseName>-costcollector --cli-binary-format raw-in-base64-out --payload '{"days":["2026-11-03"]}' out.json`; a range: `{"from":"2026-10-01","to":"2026-10-31"}` (continues in a second invocation when 15 minutes are not enough).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `costAllocation.enabled` | boolean | `true` | Deploy the collector Lambda, its EventBridge schedule, IAM policy and alarms. `false` removes all of them; the cost API routes then return `summary: null`, the dashboard cards show `—` and the Cost cards show "No cost data yet". |
| `costAllocation.scheduleUtc` | string | `"cron(0 6 * * ? *)"` | EventBridge schedule expression of the daily run, UTC. Must start with `cron(` or `rate(`. Cost Explorer data for D-1 is usually available by 06:00 UTC. |
| `costAllocation.lookbackDays` | number | `3` | Days re-processed per scheduled run (D-1 … D-`lookbackDays`). Integer `1`–`14`. Cost Explorer marks a day `Estimated` and may revise it for about 4 days; raise to `5` to pick up late revisions. Each day costs one Cost Explorer call per source ($0.01). |
| `costAllocation.novaActServiceName` | string | `"NovaAct"` | Cost Explorer `SERVICE` dimension value of Nova Act. CE groups Nova Act under the literal `NovaAct` (same as the Pricing `ServiceCode`), **not** "Amazon Nova Act". |
| `costAllocation.compute.enabled` | boolean | `true` | Also allocate MicroVM compute (the worker VMs), billed under `compute.ceService`. |
| `costAllocation.compute.ceService` | string | `"AWS Lambda"` | Cost Explorer `SERVICE` value the MicroVMs bill under. |
| `costAllocation.compute.ceComputeUsageTypePrefixes` | string[] | `["Lambda-MicroVM-vCPU-Second", "Lambda-MicroVM-Memory-GB-Second"]` | `USAGE_TYPE` stems whose cost is split by VM seconds. Non-empty, unique, non-empty strings. See the matching rule below. |
| `costAllocation.compute.ceSnapshotUsageTypePrefixes` | string[] | `["Lambda-MicroVM-Snapshot-Read-GB", "Lambda-MicroVM-Snapshot-Storage-GB-Hour", "Lambda-MicroVM-Snapshot-Write-GB"]` | `USAGE_TYPE` stems whose cost is split by VM launch count. Only `Snapshot-Read-GB` is billed per launch; `Storage-GB-Hour` (daily, per image) and `Write-GB` (per image build) are fixed per deployment and allocated by launch share as a heuristic. |

**Usage-type matching.** Cost Explorer `GetCostAndUsage` has no `STARTS_WITH` filter (only `EQUALS`, `CASE_SENSITIVE`, `ABSENT`), so the collector makes one call with `Filter SERVICE = ceService` and `GroupBy USAGE_TYPE` and classifies the returned groups itself: it strips the CE region prefix from the usage type (`EUC1-Lambda-MicroVM-vCPU-Second-ARM` → `Lambda-MicroVM-vCPU-Second-ARM`; the prefix is `EUC1-` in eu-central-1, `EU-` in eu-west-1 and absent in us-east-1) and then tests whether the stripped value **starts with** one of the configured prefixes. The `-ARM` suffix variants therefore match the defaults; other Lambda usage types (`Lambda-GB-Second`, `Request`, …) do not and are not allocated.

### Collector Lambda environment

Set by the worker stack from the `costAllocation` block; no further configuration.

| Variable | Type | Value | Read by |
|----------|------|-------|---------|
| `TABLE_NAME` | string | storage stack table name | `cost_collector.py` (BatchGetItem on use-case metadata, PutItem on `SUMMARY`), compute source (Query on executions) |
| `S3_BUCKET` | string | artefacts bucket of the default region | `cost_ledger.py` (ledgers under `cost_allocation/`) |
| `LOOKBACK_DAYS` | string (integer) | `costAllocation.lookbackDays` | `cost_collector.py` |
| `NOVA_ACT_CE_SERVICE_NAME` | string | `costAllocation.novaActServiceName` | `cost_sources/nova_act.py` (CE filter) |
| `NOVA_ACT_LIST_WORKERS` | string (integer ≥ 1) | not set → `8` | `cost_sources/nova_act.py`: workflow definitions paged concurrently by this many threads. Not a `configuration.json` key; set it on the function only to tune a run. |
| `COMPUTE_COST_ENABLED` | `"true"` \| `"false"` | `costAllocation.compute.enabled` | `cost_sources/compute.py` |
| `COMPUTE_CE_SERVICE` | string | `costAllocation.compute.ceService` | `cost_sources/compute.py` |
| `COMPUTE_CE_COMPUTE_USAGE_TYPE_PREFIXES` | string, comma-separated | `costAllocation.compute.ceComputeUsageTypePrefixes` | `cost_sources/compute.py` |
| `COMPUTE_CE_SNAPSHOT_USAGE_TYPE_PREFIXES` | string, comma-separated | `costAllocation.compute.ceSnapshotUsageTypePrefixes` | `cost_sources/compute.py` |

### IAM, schedule and alarms

- IAM (one inline policy plus the table read and write managed policies): `ce:GetCostAndUsage`, `pricing:GetProducts`, `nova-act:ListWorkflowDefinitions`, `nova-act:ListActs` on `*` (these APIs have no resource ARNs); `s3:GetObject` + `s3:PutObject` on `cost_allocation/*` of the artefacts bucket; `s3:ListBucket` on the bucket limited to `s3:prefix = cost_allocation/*`; `lambda:InvokeFunction` on its own ARN (backfill continuation).
- Schedule: EventBridge rule `${baseName}-cost-collector` with `scheduleUtc`.
- Both alarms notify the worker stack's notification topic (`${baseName}-notifications`, the topic the reconciled-executions alarm uses), evaluate one 1-day period and treat missing data as not breaching:
  - `${baseName}-cost-collector-errors`: Lambda `Errors` sum ≥ 1. The run did not finish, so the ledgers of that day were not written. Read the function's log, fix the cause, then re-run the day: `aws lambda invoke --function-name ${baseName}-costcollector --cli-binary-format raw-in-base64-out --payload '{"days":["YYYY-MM-DD"]}'`.
  - `${baseName}-cost-collector-unmetered`: `unmetered_usd > 0.5 × billed_usd` of the run report (math expression `IF(unmetered > 0.5 * billed, 1, 0)` ≥ 1). The run finished, but more than half of the Cost Explorer bill had no usage to attribute it to (`unmetered = billed − Σ cost`): the bill and the usage data disagree. Typical causes are Nova Act `ListActs` or the execution records returning no usage for a day that was billed (metering outage, acts without `endedAt`), or a usage type that bills under the source's prefixes without a metered counterpart. Compare `billed_usd`, `allocated_usd`, `unallocated_usd` and `unmetered_usd` in the `cost_collector.run` log line, check the sources, and re-run the affected days with the command above once usage is available.
- How the unmetered alarm gets its numbers: the collector logs with the Lambda JSON log format and passes the run report dict to the logger, so it is the `message` object of the log event. Two metric filters on the function's log group (`{ $.message.event = "cost_collector.run" }`) publish `$.message.unmetered_usd` and `$.message.billed_usd` as `UnmeteredUsd` / `BilledUsd` into the CloudWatch namespace `QAStudio/CostAllocation` (Sum per day).
- Account prerequisite: Cost Explorer must be enabled in the payer account; in a member account of an Organization the payer must have enabled member access to CE, otherwise every run skips its days with `cost_explorer_unavailable` (see [Troubleshooting](troubleshooting.md)).

## Bedrock Model Selection

The `bedrockModelId` setting controls which Amazon Bedrock model is used by the "Create from User Journey" wizard to generate test steps from natural language descriptions. The default is `us.amazon.nova-2-lite-v1:0` (Amazon Nova 2 Lite).

Any Bedrock model that supports the [Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference-supported-models-features.html) with tool use can be used. The model must be enabled in your AWS account and available in your deployment region.

To change the model, set `bedrockModelId` in your `configuration.json`:

```json
{
  "bedrockModelId": "us.amazon.nova-2-lite-v1:0"
}
```

For Nova 2 models, extended thinking is automatically enabled with low reasoning effort to improve generation quality.

## AgentCore browsers in a VPC

Set `vpcId` when the websites under test are **not public** — dev/staging apps behind private load balancers or on internal DNS. The AgentCore browser then puts its network interfaces (ENIs) into subnets of that VPC and reaches the sites like any other client in the VPC. The worker MicroVM itself is never in a VPC; it keeps talking to AgentCore over its public API. The setting is per deployment: every run, suite, schedule, CI run and wizard session of the deployment uses the VPC browser.

```json
{
  "adminEmail": "your-email@example.com",
  "baseName": "qa-studio",
  "vpcId": "vpc-0123456789abcdef0",
  "vpcSubnetIds": ["subnet-0123456789abcdef0", "subnet-0fedcba9876543210"],
  "workerSecurityGroupId": "sg-0123456789abcdef0"
}
```

Only `vpcId` is required; `vpcSubnetIds` and `workerSecurityGroupId` are optional.

**The stack never changes your VPC.** It only looks it up (`Vpc.fromLookup`). No subnets, route tables, NAT gateways, VPC endpoints or rules on existing security groups are created or modified. The one exception: without `workerSecurityGroupId` the stack adds a single security group (`QA Studio AgentCore browser ENIs`, all outbound, no inbound) to the VPC. With `workerSecurityGroupId` it adds nothing.

| What | Subnets passed to the browser |
|---|---|
| `vpcSubnetIds` unset / `null` | Every private and isolated subnet of `vpcId` in an AgentCore-supported AZ. Public subnets are never picked automatically. |
| `vpcSubnetIds: ["subnet-…", …]` | Exactly these, in this order. Synth fails if one is not a subnet of `vpcId` or is in an unsupported AZ. Listing a public subnet is allowed. |

### What you provide

- **Subnets in AgentCore-supported Availability Zones.** AgentCore supports VPC browsers only in specific AZs per region, identified by AZ **ID** (e.g. `use1-az1`), not AZ name — the ID→name mapping differs per account. List your subnets and their AZ IDs and compare them with the [AgentCore VPC documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html):

  ```bash
  aws ec2 describe-subnets --filters Name=vpc-id,Values=vpc-0123456789abcdef0 \
    --query 'Subnets[].[SubnetId,AvailabilityZoneId]' --output table
  ```

- **Inbound rule on the target.** The security group of the website under test (load balancer, instance) must allow inbound HTTPS/HTTP from the browser security group (the created one — see the `worker` stack resources — or your `workerSecurityGroupId`). Using an existing `workerSecurityGroupId` that the target already allows avoids this step.
- **Routes and DNS.** The selected subnets must route to the target, and the target's host name must resolve inside the VPC (Route 53 private hosted zone associated with the VPC, or VPC DNS resolution).
- **Optional: a NAT gateway for public URLs.** A VPC browser has no internet access of its own (a public subnet does not give it one). Without a NAT route in the selected subnets, any public URL the test touches — an external identity provider's login page, CDNs, third-party scripts — is unreachable. That is a supported setup: VPC browsers exist to test non-public sites, and the stack never adds NAT.
- **Not yet verified without NAT:** whether session control, live view, the session recording upload to S3 and the enterprise browser policy (S3) work from an isolated subnet (no route out) is not documented by AWS and has not been tested for QA Studio yet (design task 0). Prefer subnets with a NAT route until this is confirmed.

### Deploy

- Synth needs **AWS credentials for the target account/region and the AWS CLI**: with `vpcId` set, every stack gets an explicit account/region, CDK looks the VPC up (cached in the gitignored `web-app/cdk.context.json`) and `ec2:DescribeAvailabilityZones` maps the supported AZ IDs to your account's AZ names. Deploys without `vpcId` stay environment-agnostic.
- Changing `vpcId`, `vpcSubnetIds` or `workerSecurityGroupId` changes the worker image environment (`AGENT_CORE_VPC`, `AC_VPC_ID`, `AC_SUBNET_IDS`, `AC_SECURITY_GROUP_ID`), so the next `npm run deploy` rebuilds the MicroVM image (3–5 min).
- AgentCore creates the ENIs through its service-linked role `AWSServiceRoleForBedrockAgentCoreNetwork`; the worker roles get no `ec2:*` permission.
- To go back to public browsers, remove `vpcId` and deploy. AgentCore releases browser ENIs up to 8 h after a browser is deleted; until then CloudFormation cannot delete a created security group — retry the deploy later (see [Troubleshooting](troubleshooting.md#agentcore-browser-in-a-vpc)).

Local runs (`qa-studio run --browser agentcore`) read the same environment variables; see the [CLI README](../qa-studio-cli/README.md).

> **Maintainer note — keep the supported-AZ table current.** AWS publishes the AgentCore-supported AZ IDs only in documentation (there is no API for the list), so they are hardcoded per region in [`web-app/lib/agentcore-az.ts`](../web-app/lib/agentcore-az.ts) (`AGENTCORE_SUPPORTED_AZ_IDS`). If AWS adds a region or changes the supported zones, update that table from the [AgentCore VPC documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html). Setting `vpcId` in a region that is missing from the table fails synth with an error pointing back to the doc.

## Deprecated keys

Accepted but ignored. `loadConfig()` logs one line per key — `Configuration warning: <key> is deprecated and ignored (<reason>); see docs/configuration.md` — and the stacks never read them. Remove them from `configuration.json`.

| Key | Type | Reason |
|-----|------|--------|
| `agentCoreVPC` | boolean | `vpcId` alone attaches the AgentCore browsers to the VPC. `vpcId` together with `agentCoreVPC: false` is a contradiction and fails: `Configuration error: agentCoreVPC is deprecated; vpcId now attaches browsers to the VPC. Remove agentCoreVPC`. |
| `createVpcEndpoints` | boolean | The stack creates no VPC endpoints; browsers use the routing of the `vpcId` subnets. |

## Removed keys

### Removed in the release after 0.1.1-40 (`[Unreleased]`)

The worker runs on Lambda MicroVMs without ECS (see [CHANGELOG → Release notes](../web-app/CHANGELOG.md)). The keys below are rejected by `loadConfig()` with `Configuration error: <key> was removed (the worker runs on Lambda MicroVMs, without ECS); see the release notes`; delete them from `configuration.json` before deploying:

| Key | Was |
|-----|-----|
| `workerRuntime` | `ecs` / `microvm` switch of the phase-1 migration |
| `dockerImageVersion` | Tag of the locally built ECS worker image |

The deployment no longer needs Docker or Podman.

## Mobile Testing (Device Farm)

Mobile testing uses AWS Device Farm to run tests on real Android and iOS devices. Device Farm is only available in `us-west-2`, regardless of where QA Studio is deployed.

### IAM Requirements

The MicroVM execution role (the worker) and the recording download Lambda require the following Device Farm permissions:

- `devicefarm:CreateRemoteAccessSession`
- `devicefarm:GetRemoteAccessSession`
- `devicefarm:StopRemoteAccessSession`
- `devicefarm:DeleteRemoteAccessSession`
- `devicefarm:ListProjects`
- `devicefarm:CreateProject`
- `devicefarm:ListDevices`
- `devicefarm:GetDevice`
- `devicefarm:CreateUpload`
- `devicefarm:GetUpload`
- `devicefarm:ListUploads`
- `devicefarm:ListArtifacts`

These permissions are automatically configured by the CDK worker stack.

### How It Works

1. The user creates a mobile use case with platform, app identifiers, and an app binary
2. When executed, the worker provisions a Device Farm remote access session on a real device
3. The app binary is uploaded to Device Farm (or reused from a previous upload)
4. Nova Act controls the device via Appium through the Device Farm endpoint
5. After execution, the session recording is downloaded asynchronously via an SQS-triggered Lambda


## Electron Testing (CI runner)

Electron usecases are executed exclusively by `qa-studio run` on a host with a display; nothing in the cloud stack changes for them (no IAM, SQS, MicroVM or GSI additions). The API refuses non-`ci_runner` triggers for `test_platform: "electron"`.

### CLI flags

| Flag | Type | Default | Platforms | Description |
|---|---|---|---|---|
| `--app-path` | path | — | mobile, electron | Mobile: `.apk`/`.ipa` uploaded to Device Farm. Electron: `.app` bundle or executable to launch. Required for electron usecases. |
| `--app-arg` | string, repeatable | `[]` | electron | Extra argv appended after QA Studio's own switches (e.g. the app directory when `--app-path` is the bare `electron` binary). Requires `--app-path`. |
| `--app-user-data-dir` | path | fresh temp dir per run | electron | Electron `--user-data-dir` to reuse (pre-seeded profile). The default temp dir is removed at teardown. Requires `--app-path`. |

### Usecase attributes

| Field | Type | Default | Description |
|---|---|---|---|
| `test_platform` | string | `web` | `web` \| `mobile` \| `electron`. |
| `bundle_id` | string | — | Optional for electron (shared with iOS mobile). The app's `CFBundleIdentifier`; copied onto each execution record and compared with the launched `.app` by the runner. Mismatch → the run fails before the app starts. Skipped for bare executables and the generic `com.github.Electron` dev shell. |

### Environment variables

| Variable | Type | Default | Description |
|---|---|---|---|
| `QA_STUDIO_ELECTRON_START_TIMEOUT` | number (seconds) | `30` | How long the runner waits for the `DevTools listening on …` line and the first page target. |
| `HEADLESS` | — | — | **No effect** for electron usecases; the app needs a display. |

### Security

- The app is started with `--remote-debugging-port=0`: an ephemeral port bound to `127.0.0.1` only. `--remote-debugging-address` and `--remote-allow-origins` are never passed.
- The port is unauthenticated for the lifetime of the test; run Electron tests on single-tenant hosts.
- `--app-arg` values are logged at INFO. Secrets go through `secret` steps, never argv.

## Worker Runtime Environment

The worker is a Lambda MicroVM image whose entrypoint, `web-app/worker/supervisor.py`, spawns the `qa-studio` CLI (batch) or `wizard_worker.py` (wizard). It receives its configuration through three channels:

- **Run-hook payload** — per-execution values (`usecase_id`, `execution_id`, `execution_token`, `region`, `s3_bucket`, `max_duration_s`, mobile fields) arrive as a `RunPayload` JSON string (≤ 4096 bytes) in the platform's `POST /run` hook. Nothing per-execution is ever an env var of the image.
- **Image-level env** — stack constants baked into the image snapshot by the worker stack (`lib/worker-stack.ts` `microvmEnvironment`). Changing one rebuilds the image (3–5 min). `AWS_REGION` is reserved and injected by the platform; the supervisor derives `AWS_DEFAULT_REGION` from it.
- **SSM parameters and Secrets Manager** — the API URL, the Cognito token endpoint and the M2M `{client_id, client_secret}` are read inside `/run` under the VM execution role. Keeps the image deployment-agnostic and keeps secrets out of the snapshot.

The supervisor always invokes `qa-studio run … --format json --verbose`: the CLI's console output is quiet by default (progress lines only), but the VM console is the CloudWatch log stream, so the worker needs the full runner logging there. There is no env var to turn this off.

The authoritative tables — `RunPayload` fields, the child env the supervisor builds, and every image-level variable with its value and reader — are in [`web-app/worker/README.md` → MicroVM supervisor](../web-app/worker/README.md#microvm-supervisor). Supervisor-only settings:

| Variable | Default | Purpose |
|---|---|---|
| `SUPERVISOR_BIND_HOST` | `0.0.0.0` | Hook server bind address (the VM runs with `NO_INGRESS`; the only client is the platform) |
| `SUPERVISOR_PORT` | `8080` | Hook server port (must match the image's `hooks.port`) |
| `SUPERVISOR_LOG_LEVEL` | `INFO` | `DEBUG` prints the child env with `OAUTH_CLIENT_SECRET` and `QA_STUDIO_EXECUTION_TOKEN` masked |
| `WORKER_APP_DIR` | `/app` | Working directory of the child processes |
| `MICROVM_ID` | unset | Fallback VM id when the `/run` body carries no `microvmId` (local runs) |

### Worker execution token

Binds the worker to the one execution it runs. Set automatically; there's nothing to configure. See [architecture](architecture.md#worker-execution-capability).

| Variable | Type | Default | Description |
|---|---|---|---|
| `RunPayload.execution_token` | string (43-char URL-safe random) | — | Minted per execution by `execute_usecase` for `Scheduled` and `OnDemandHeadless` runs and passed in the run-hook payload. Only its SHA-256 is stored (`worker_token_hash`); the payload field is a pydantic `SecretStr` and is never logged. |
| `QA_STUDIO_EXECUTION_TOKEN` | string `{usecase_id}:{execution_id}:{token}` | unset | Exported by the supervisor to the child; read by the `qa-studio` CLI. When set and non-empty, every API request carries it as the `X-QA-Execution-Token` header; it's never logged. Leave it unset for local runs. |

### Lambda authorizer environment

Set by the API stack (`lib/authorizer-client-binding.ts`); no `configuration.json` option.

| Variable | Type | Default | Description |
|---|---|---|---|
| `TABLE_NAME` | string | storage stack table name | DynamoDB table holding `OAUTH_CLIENTS` records. The authorizer reads the client's `team_id` / `team_role` with `GetItem` (IAM limited to `dynamodb:LeadingKeys = OAUTH_CLIENTS`). |
| `WORKER_CLIENT_ID` | string | auth stack worker M2M client ID | Tokens from this client get `identityType=worker` and no team roles; they only work with a valid execution token. |
| — (constant) `CLIENT_BINDING_TTL_SECONDS` | int | `60` | In-memory cache lifetime of a client binding in a warm authorizer container. API Gateway also caches the authorizer result for 5 minutes. |

No new `configuration.json` options were added for team-bound authorization.

### SSM parameters written by the stacks

| Parameter | Written by | Read by |
|---|---|---|
| `/qa-studio/{baseName}/api-url` | API stack | Worker supervisor (`/run`, batch mode) |
| `/qa-studio/{baseName}/cognito-token-endpoint` | Auth stack | Worker supervisor (`/run`, batch mode) |

Both are `String` parameters (non-sensitive — the URLs themselves grant no access). The MicroVM execution role has `ssm:GetParameter` on both exact names.

### Secrets Manager secrets

| Secret name | Contents | Used by |
|---|---|---|
| `${baseName}-nova-act-api-key` (existing) | Nova Act API key | Worker (preview API only) |
| `${baseName}-worker-m2m-credentials` | JSON `{"client_id": "...", "client_secret": "..."}` | Worker supervisor (`GetSecretValue` inside `/run` under the MicroVM execution role) |

The M2M credentials secret is populated by a CDK `AwsCustomResource` that calls `cognito-idp:DescribeUserPoolClient` post-deploy to resolve the generated client secret. Rotation is deploy-driven: re-running `npm run deploy` mints fresh credentials through the same custom resource.
