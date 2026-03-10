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
| `bedrockModelId` | string | No | `"us.anthropic.claude-3-5-sonnet-20241022-v2:0"` | Bedrock model ID for AI-powered test generation |
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
  "bedrockModelId": "eu.anthropic.claude-sonnet-4-6",
  "enabledRegions": ["eu-central-1"],
  "defaultRegion": "eu-central-1",
  "useNovaActGa": true,
  "lambdaConcurrency": 5,
  "enableExtensionAuthentication": true,
  "cliCallbackUrl": "http://localhost:19847/callback"
}
```

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
