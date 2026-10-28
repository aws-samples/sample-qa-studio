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
| `enabledRegions` | string[] | No | `["us-east-1", "us-west-2", "ap-southeast-2", "eu-central-1"]` | AWS regions enabled for S3 replication |
| `defaultRegion` | string | No | `"us-east-1"` | Default AWS region (must be in `enabledRegions`) |
| `bedrockModelId` | string | No | `"us.amazon.nova-2-lite-v1:0"` | Bedrock model ID for AI-powered test generation. See [Bedrock Model Selection](#bedrock-model-selection). |
| `vpcId` | string \| null | No | `null` | Existing VPC ID to deploy into (e.g. `"vpc-abc123"`) |
| `workerSecurityGroupId` | string \| null | No | `null` | Existing security group for ECS workers (e.g. `"sg-abc123"`) |
| `createVpcEndpoints` | boolean | No | `false` | Create VPC endpoints for AWS services when using existing VPC |
| `useNovaActGa` | boolean | No | `true` | Use Nova Act GA API (vs preview) |
| `agentCoreVPC` | boolean | No | `false` | Enable AgentCore VPC integration |
| `lambdaConcurrency` | number | No | `5` | Reserved concurrent executions per Lambda function. Controls max parallel invocations per function to prevent account concurrency exhaustion. Set to `0` to disable the limit. |
| `dockerImageVersion` | string | No | (from package.json) | Override Docker image version tag for worker container |
| `apiGatewayUrl` | string | No | — | Full API Gateway URL for local development proxy |
| `enableExtensionAuthentication` | boolean | No | — | Enable Kiro extension OAuth callback authentication |
| `cliCallbackUrl` | string | No | — | Callback URL for CLI OAuth flow (e.g. `"http://localhost:19847/callback"`) |
| `deviceFarmRegion` | string | No | `"us-west-2"` | AWS region for Device Farm mobile testing. Device Farm is only available in `us-west-2`. |

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
  "deviceFarmRegion": "us-west-2"
}
```

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

## VPC Configuration

To deploy into an existing VPC:

```json
{
  "adminEmail": "your-email@example.com",
  "baseName": "qa-studio",
  "vpcId": "vpc-0123456789abcdef0",
  "workerSecurityGroupId": "sg-0123456789abcdef0",
  "createVpcEndpoints": true
}
```

When `vpcId` is set, CDK uses explicit account/region from your AWS environment. The security group must allow outbound HTTPS (443) for AWS API access.

### AgentCore browsers in a VPC (`agentCoreVPC: true`)

When `agentCoreVPC` is enabled, AgentCore browsers are attached to the VPC. AgentCore only supports VPC connectivity in **specific Availability Zones per region**, identified by **AZ ID** (e.g. `use1-az1`), not AZ name (e.g. `us-east-1a`) — and the AZ ID→name mapping differs per AWS account. To prevent browser-creation failures in unsupported zones, the worker stack resolves supported AZs at synth time and:

- **Created VPC** (`vpcId` unset): pins the VPC's subnets to two supported AZs (two NAT Gateways). Because this sets the VPC's Availability Zones, it should be enabled on a **fresh** deployment — turning it on for an already-created VPC forces CloudFormation to re-lay-out (replace) existing subnets, which fails with CIDR conflicts. For an existing VPC, either deploy a fresh stack or use an imported VPC (`vpcId`).
- **Existing VPC** (`vpcId` set): validates that at least one private subnet is in a supported AZ and fails the deploy with an actionable message otherwise.

Because `agentCoreVPC: true` triggers an `ec2:DescribeAvailabilityZones` call during `cdk synth`, synth then requires AWS credentials for the target account/region (your deploy pipeline already provides these). Non-VPC deploys are unaffected.

> **Maintainer note — keep the supported-AZ table current.** AWS publishes the AgentCore-supported AZ IDs only in documentation (there is no API for the list), so they are hardcoded per region in [`web-app/lib/agentcore-az.ts`](../web-app/lib/agentcore-az.ts) (`AGENTCORE_SUPPORTED_AZ_IDS`). If AWS adds a region or changes the supported zones, update that table from the [AgentCore VPC documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html). Deploying `agentCoreVPC: true` into a region that is missing from the table fails synth with a clear error pointing back to the doc.

To find the AZ ID of a subnet:

```bash
aws ec2 describe-subnets --subnet-ids subnet-12345678 --query 'Subnets[0].AvailabilityZoneId'
```


## Mobile Testing (Device Farm)

Mobile testing uses AWS Device Farm to run tests on real Android and iOS devices. Device Farm is only available in `us-west-2`, regardless of where QA Studio is deployed.

### IAM Requirements

The ECS worker task role and the recording download Lambda require the following Device Farm permissions:

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


## Worker Runtime Environment

Since the CLI-unified-runner refactor, the ECS worker container invokes the `qa-studio` CLI (via `web-app/worker/entrypoint.sh`) instead of a standalone Python script. The container receives its configuration through two channels:

- **ECS `secrets:` injection** — OAuth M2M credentials are pulled from Secrets Manager at task start and exposed as env vars. The secret itself is created by the auth stack.
- **SSM parameters** — the API URL and Cognito token endpoint are published by the API / auth stacks and read by `entrypoint.sh` at container start. Keeps the image deployment-agnostic.

### Env vars consumed by `entrypoint.sh`

| Variable | Source | Purpose |
|---|---|---|
| `WORKER_MODE` | ECS task definition (optional) | `batch` (default) → invokes `qa-studio run`. `wizard` → defers to `wizard_worker.py`. |
| `USECASE_ID` | ECS task definition | Required in batch mode; passed as `--usecase-id`. |
| `EXECUTION_ID` | ECS task definition | Required in batch mode; passed as `--execution-id` so the CLI attaches to the pre-created record. |
| `EXECUTION_TOKEN` | ECS container override set by `execute_usecase` | Worker execution token (see [below](#worker-execution-token)). Exported as `QA_STUDIO_EXECUTION_TOKEN`, then unset. |
| `QA_STUDIO_API_URL_SSM` | CDK worker stack | SSM parameter name the entrypoint reads to discover the API URL. Written as `QA_STUDIO_API_URL` for the CLI. |
| `QA_STUDIO_TOKEN_ENDPOINT_SSM` | CDK worker stack | SSM parameter name for the Cognito `/oauth2/token` endpoint. Written as `OAUTH_TOKEN_ENDPOINT` for the CLI. |
| `OAUTH_CLIENT_ID` | ECS `secrets:` → Secrets Manager | M2M client ID (JSON field `client_id` of the `${baseName}-worker-m2m-credentials` secret). |
| `OAUTH_CLIENT_SECRET` | ECS `secrets:` → Secrets Manager | M2M client secret (JSON field `client_secret`). |
| `AWS_REGION` | ECS task definition | Forwarded to `qa-studio run --region`. |
| `ENABLE_TRAJECTORY_REPLAY` | ECS task definition (optional) | `true` (default) or `false`. Read directly by the CLI; no flag. |
| `QA_STUDIO_VERBOSE` | ECS task definition (optional) | `true` to add `--verbose` to the invocation. |
| `BEDROCK_EXECUTION_ROLE` | ECS task definition | IAM role assumed by AgentCore browsers. |
| `AGENT_CORE_VPC` + `AC_VPC_ID` / `AC_SUBNET_ID` / `AC_SECURITY_GROUP_ID` | ECS task definition (when `agentCoreVPC: true` in `configuration.json`) | Put AgentCore browsers in a VPC. |
| `S3_BUCKET` | ECS task definition | Artefact bucket the AgentCore provisioner writes recordings to. |

### Worker execution token

Binds the worker to the one execution it runs. Set automatically; there's nothing to configure. See [architecture](architecture.md#worker-execution-capability).

| Variable | Type | Default | Description |
|---|---|---|---|
| `EXECUTION_TOKEN` | string (43-char URL-safe random) | unset | Minted per execution by `execute_usecase` for `Scheduled` and `OnDemandHeadless` runs and passed to the ECS task. Only its SHA-256 is stored (`worker_token_hash`). When unset, the entrypoint logs a warning (without the value) and the run's API calls are denied. |
| `QA_STUDIO_EXECUTION_TOKEN` | string `{usecase_id}:{execution_id}:{token}` | unset | Read by the `qa-studio` CLI. When set and non-empty, every API request carries it as the `X-QA-Execution-Token` header; it's never logged. Leave it unset for local runs. |

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
| `/qa-studio/{baseName}/api-url` | API stack | Worker entrypoint (batch mode) |
| `/qa-studio/{baseName}/cognito-token-endpoint` | Auth stack | Worker entrypoint (batch mode) |

Both are `String` parameters (non-sensitive — the URLs themselves grant no access). The worker task role has `ssm:GetParameter` on both exact names.

### Secrets Manager secrets

| Secret name | Contents | Used by |
|---|---|---|
| `${baseName}-nova-act-api-key` (existing) | Nova Act API key | Worker (preview API only) |
| `${baseName}-worker-m2m-credentials` (new) | JSON `{"client_id": "...", "client_secret": "..."}` | ECS task `secrets:` injection |

The M2M credentials secret is populated by a CDK `AwsCustomResource` that calls `cognito-idp:DescribeUserPoolClient` post-deploy to resolve the generated client secret. Rotation is deploy-driven: re-running `npm run deploy` mints fresh credentials through the same custom resource.
