# Configuration

Copy the sample configuration file and update with your settings:

```bash
cp configuration.json.sample configuration.json
```

Edit `configuration.json` with your specific values. The configuration is loaded and validated by `lib/config.ts`, which provides sensible defaults for optional fields.

## Configuration Properties

| Property | Description | Required | Default |
|----------|-------------|----------|---------|
| `adminEmail` | Email address for the initial admin user. After deployment, this email will receive a temporary password from Cognito. Must be a valid email format. | **Yes** | - |
| `baseName` | Unique name prefix for all AWS resources (DynamoDB tables, S3 buckets, Lambda functions, etc.). Must contain only lowercase letters, numbers, and hyphens. | **Yes** | - |
| `enabledRegions` | List of AWS regions where browser automation can run. Users can select from these regions when creating tests. The solution creates S3 buckets in each region for artifact storage with automatic replication to the default region. | No | `["us-east-1", "us-west-2", "ap-southeast-2", "eu-central-1"]` |
| `defaultRegion` | Default region for browser execution when users don't specify one, and the region where the main S3 artifacts bucket is created. Must be included in `enabledRegions`. Note: This does NOT control where infrastructure is deployed. That is determined by your AWS CLI configuration or CDK_DEFAULT_REGION. | No | `us-east-1` |
| `apiEndpoint` | API Gateway endpoint path prefix. | No | `api` |
| `apiDeploymentStage` | API Gateway deployment stage name. | No | `api` |
| `bedrockModelId` | Amazon Bedrock model ID used to generate test cases in the User Journey feature. See [available models](https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html). | No | `amazon.nova-2-lite-v1:0` |
| `dcvRelease` | URL to the NICE DCV Web Client SDK archive. Used for remote browser session viewing. | No | `https://d1uj6qtbmh3dt5.cloudfront.net/webclientsdk/nice-dcv-web-client-sdk-1.10.1-1011.zip` (see https://www.amazondcv.com/webclientsdk.html for the latest download URL) |
| `useNovaActGa` | When `true`, uses the Amazon Nova Act AWS service (recommended). When `false`, uses the Research Preview. | No | `true` |
| `vpcId` | Existing VPC ID to use instead of creating a new one. Must start with `vpc-`. Set to `null` to create a new VPC. | No | `null` (creates new VPC) |
| `workerSecurityGroupId` | Existing security group ID for ECS tasks. Must start with `sg-`. Set to `null` to create a new security group. | No | `null` (creates new) |
| `createVpcEndpoints` | Whether to create VPC endpoints when using an existing VPC. | No | `false` |
| `agentCoreVPC` | Enable VPC support for AgentCore browsers. When `true`, AgentCore browsers run within the VPC (either existing or newly created) for enhanced security and network isolation. Works with both new and existing VPCs. | No | `false` |
| `apiGatewayUrl` | Full API Gateway URL for local frontend development. The Vite dev server proxies `/api/*` requests to this URL. Not used in production (CloudFront handles API routing). | No | `""` |

## Examples

**Minimal configuration (only required fields):**
```json
{
  "adminEmail": "your-email@example.com",
  "baseName": "qa-studio-nova-act"
}
```

**Full configuration with all available options:**
```json
{
  "adminEmail": "your-email@example.com",
  "baseName": "qa-studio",
  "apiEndpoint": "api",
  "apiDeploymentStage": "prod",
  "enabledRegions": ["us-east-1", "us-west-2", "eu-central-1"],
  "defaultRegion": "us-east-1",
  "useNovaActGa": true,
  "vpcId": null,
  "workerSecurityGroupId": null,
  "createVpcEndpoints": false,
  "agentCoreVPC": false,
  "apiGatewayUrl": "https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com"
}
```

## Using an Existing VPC

By default, the solution creates a new VPC. To integrate with your existing network infrastructure:

1. Set `vpcId` to your existing VPC ID (e.g., `"vpc-0123456789abcdef0"`)
2. The VPC must have at least one public subnet with NAT Gateway for internet access (workers run in private subnets for security)
3. Private subnets are automatically discovered based on route table configuration
4. Optionally provide `workerSecurityGroupId` to use an existing security group
5. Set `createVpcEndpoints: true` if you want to create VPC endpoints in the existing VPC for enhanced security
6. Set `agentCoreVPC: true` to enable VPC support for AgentCore Browser Tool (recommended for production)

**Example with existing VPC:**
```json
{
  "adminEmail": "your-email@example.com",
  "baseName": "qa-studio",
  "vpcId": "vpc-0123456789abcdef0",
  "workerSecurityGroupId": "sg-0123456789abcdef0",
  "createVpcEndpoints": true,
  "agentCoreVPC": true
}
```

**Example with new VPC and AgentCore VPC support:**
```json
{
  "adminEmail": "your-email@example.com",
  "baseName": "qa-studio",
  "vpcId": null,
  "agentCoreVPC": true,
  "useNovaActGa": true
}
```

**Note:** When using an existing VPC, all CDK stacks are deployed with explicit account/region environment configuration. This is required for VPC lookup and ensures proper cross-stack resource references.

**Why use your existing VPC:**
- Reduce costs by sharing VPC infrastructure
- Integrate with existing network architecture
- Use existing security group configurations
- Avoid VPC limits in your AWS account

**Why enable AgentCore VPC:**
- Enhanced security: Browser automation runs within your VPC
- Network isolation: AgentCore browsers are isolated from public internet
- Compliance: Meet security requirements for sensitive automation tasks
- Integration: Access internal resources and services directly
- Works with both new and existing VPCs
