# Nova Act QA Studio - Web Automation Platform

Nova Act QA Studio is a cloud-native web automation platform that enables users to create, manage, and execute browser-based workflows without writing code. Built on AWS with a modern serverless architecture, it combines the power of AI-driven browser automation through Nova Act with an intuitive web interface for creating complex automation scenarios.

## What is Nova Act QA Studio?

Nova Act QA Studio transforms web automation from a developer-only task into an accessible tool for anyone. Users can:

- **Create Automation Workflows**: Define step-by-step browser interactions through a visual interface
- **Execute with AI**: Leverage Nova Act's AI-powered browser automation for intelligent web interactions
- **Schedule Executions**: Set up recurring automation tasks with flexible scheduling
- **Monitor & Debug**: Track execution progress with video recordings, screenshots, and detailed logs
- **Template Variables**: Create dynamic workflows with customizable parameters
- **Scale Automatically**: Cloud-native architecture handles concurrent executions seamlessly

The platform is perfect for web scraping, automated testing, data collection, form filling, and any repetitive browser-based tasks that traditionally required custom scripting.

## Architecture Overview

Nova Act QA Studio follows a modern serverless architecture pattern:

- **Frontend**: React application with AWS Cloudscape Design System hosted on S3 and CloudFront
- **API Layer**: AWS API Gateway with Lambda functions (Go)
- **Authentication**: AWS Cognito with AWS Amplify SDK for secure user management
- **Data Storage**: DynamoDB with single-table design
- **Execution Engine**: ECS Fargate containers running Python workers
- **Artifact Storage**: S3 for videos, screenshots, and logs
- **Scheduling**: EventBridge Scheduler for automated executions
- **Queue System**: SQS for reliable execution orchestration
- **Browser**: Bedrock AgentCore Browser Tool for a running Nova Act on a fully managed remote browser

## Prerequisites

Before deploying Nova Act QA Studio, ensure you have:

- AWS CLI configured with appropriate permissions
- Node.js 18+ and npm
- Go 1.22+
- Docker or Podman
- AWS CDK CLI (`npm install -g aws-cdk`)
- Python 3.11+ (for worker development)

## Deployment Instructions

### 1. Environment Setup

```bash
# Clone the repository
git clone git@github.com:aws-samples/sample-nova-act-qa-studio.git
cd sample-nova-act-qa-studio

# Install dependencies
npm install
cd frontend && npm install && cd ..
cd lambda && go mod download && cd ..
```

### 2. Configure Your Deployment

Copy the sample configuration file and update with your settings:

```bash
cp configuration.json.sample configuration.json
```

Edit `configuration.json` with your specific values. The configuration is loaded and validated by `lib/config.ts`, which provides sensible defaults for optional fields.

#### Configuration Properties

| Property | Description | Required | Default |
|----------|-------------|----------|---------|
| `adminEmail` | Email address for the initial admin user. After deployment, this email will receive a temporary password from Cognito. Must be a valid email format. | **Yes** | - |
| `baseName` | Unique name prefix for all AWS resources (DynamoDB tables, S3 buckets, Lambda functions, etc.). Must contain only lowercase letters, numbers, and hyphens. | **Yes** | - |
| `enabledRegions` | List of AWS regions where browser automation can run, e.g. `["us-east-1"]`. | **Yes** | - |
| `defaultRegion` | Primary region for deployment and default browser execution, e.g. `us-east-1`. Must be included in `enabledRegions`. | **Yes** | - |
| `apiEndpoint` | API Gateway endpoint path prefix. | No | `api` |
| `apiDeploymentStage` | API Gateway deployment stage name. | No | `api` |
| `userAgentString` | Custom User-Agent string for browser automation requests. | No | `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36` |
| `bedrockModelId` | Amazon Bedrock model ID used to generate test cases in the User Journey feature. See [available models](https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html). | No | `anthropic.claude-3-5-sonnet-20240620-v1:0` |
| `dcvRelease` | URL to the NICE DCV Web Client SDK archive. Used for remote browser session viewing. | No | `https://d1uj6qtbmh3dt5.cloudfront.net/webclientsdk/nice-dcv-web-client-sdk-1.9.100-952.zip` |
| `vpcId` | Existing VPC ID to use instead of creating a new one. Must start with `vpc-`. Set to `null` to create a new VPC. | No | `null` (creates new VPC) |
| `workerSecurityGroupId` | Existing security group ID for ECS tasks. Must start with `sg-`. Set to `null` to create a new security group. | No | `null` (creates new) |
| `createVpcEndpoints` | Whether to create VPC endpoints when using an existing VPC. | No | `false` |

#### Example Configuration

**Minimal configuration (using defaults):**
```json
{
  "adminEmail": "your-email@example.com",
  "baseName": "nova-act-qa-studio"
}
```

**Full configuration with custom values:**
```json
{
  "adminEmail": "your-email@example.com",
  "baseName": "my-qa-studio",
  "apiEndpoint": "api",
  "apiDeploymentStage": "prod",
  "enabledRegions": ["us-east-1", "us-west-2", "eu-central-1"],
  "defaultRegion": "us-east-1",
  "userAgentString": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
  "bedrockModelId": "anthropic.claude-3-5-sonnet-20240620-v1:0",
  "dcvRelease": "https://d1uj6qtbmh3dt5.cloudfront.net/webclientsdk/nice-dcv-web-client-sdk-1.9.100-952.zip",
  "vpcId": null,
  "workerSecurityGroupId": null,
  "createVpcEndpoints": false
}
```

#### Using an Existing VPC

By default, Nova Act QA Studio creates a new VPC with NAT Gateways and VPC endpoints. To use an existing VPC:

1. Set `vpcId` to your existing VPC ID (e.g., `"vpc-0123456789abcdef0"`)
2. The VPC must have at least one public subnet (workers run with public IP assignment)
3. Public subnets are automatically discovered based on route table configuration
4. Optionally provide `workerSecurityGroupId` to use an existing security group
5. Set `createVpcEndpoints: true` if you want to create VPC endpoints in the existing VPC

**Example with existing VPC:**
```json
{
  "adminEmail": "your-email@example.com",
  "baseName": "nova-act-qa-studio",
  "vpcId": "vpc-0123456789abcdef0",
  "workerSecurityGroupId": "sg-0123456789abcdef0",
  "createVpcEndpoints": false
}
```

**Note:** When using an existing VPC, all CDK stacks are deployed with explicit account/region environment configuration. This is required for VPC lookup and ensures proper cross-stack resource references.

**Benefits of using existing VPC:**
- Reduce costs by sharing VPC infrastructure
- Integrate with existing network architecture
- Use existing security group configurations
- Avoid VPC limits in your AWS account

### 3. Deploy Everything

```bash
npm run deploy
```

This single command will:
- Build all Lambda functions for ARM64 architecture
- Deploy all infrastructure stacks (storage, auth, API, notification, worker, routes, frontend)
- Generate frontend configuration files automatically
- **Download the NICE DCV Web Client SDK** (automatically downloads ~2.7MB SDK for remote browser viewing)
- Build and deploy the React frontend to S3/CloudFront
- Send a temporary password to the `adminEmail` configuration to access the frontend
- Clean up build artifacts

> **Note:** During deployment, the NICE DCV Web Client SDK will be automatically downloaded from AWS CloudFront. This SDK enables remote browser session viewing in the web interface. The download is cached and only re-downloads when the SDK version changes.

> Take note of the `frontend.CloudFrontDistributionDomain` CloudFormation Output printed to the console after the frontend stack is deployed. You'll use this in a later step to access the web application.

### 4. Configure Secrets

Upload your Nova Act API Key to Secrets Manager:

```bash
# Via AWS Console
# Go to Secrets Manager → nova-act-qa-studio-nova-api-key
# Click "Retrieve secret value" → "Edit"
# Replace placeholder with your actual Nova Act API key
# Click "Save"

# Or via AWS CLI
aws secretsmanager update-secret \
  --secret-id nova-act-qa-studio-nova-api_key \
  --secret-string "your-nova-act-api-key"
```

> This API Key is used at runtime to authenticate with the Nova Act SDK.

### 5. Access the Web Application

1. Check the email inbox for the admin email address configured in `configuration.json` for a temporary password from no-reply@verificationemail.com
2. Navigate to the CloudFront distribution URL from the `frontend` stack
3. Login using your admin email and the temporary password
5. Complete the password setup step

That's it! Your Nova Act QA Studio is now deployed and ready to use.

### Advanced: Individual Stack Deployment

If you need to deploy or update individual stacks:

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

## Usage

1. **Access the Web Interface**: Navigate to the CloudFront distribution URL
2. **Create Account**: Sign up through the Cognito-powered authentication
3. **Create Usecase**: Define your automation workflow with a starting URL
4. **Add Steps**: Define browser actions using natural language instructions
5. **Configure Secrets**: Store sensitive data (passwords, API keys) securely
6. **Execute**: Run your automation and monitor progress in real-time
7. **Review Results**: Access video recordings and execution logs

### Step Types

Nova Act QA Studio supports two types of workflow steps:

**Plain Text Steps**: Regular automation instructions

- Example: "Click on the login button"
- Example: "Navigate to the dashboard"
- Example: "Wait for page to load"

**Secret Steps**: Secure steps that reference predefined secrets

- Action: "Type username in login field" + Secret: "username"
- Action: "Type password in password field" + Secret: "password"
- Action: "Enter API key in settings" + Secret: "api_key"

Secret steps ensure sensitive data never appears in logs or execution history, providing enhanced security for your automation workflows.

## Useful Commands

### Main Deployment

- `npm run deploy` - Complete deployment (builds Lambdas + frontend, then deploys)
- `npm run deploy:release` - Deploy from release archive (skips builds, uses pre-built artifacts)

### Individual Stack Deployment

- `npm run deploy:storage` - Deploy storage stack (DynamoDB, S3, ECR)
- `npm run deploy:auth` - Deploy authentication stack (Cognito)
- `npm run deploy:api` - Deploy API Gateway stack
- `npm run deploy:frontend` - Deploy frontend infrastructure (CloudFront, S3)
- `npm run deploy:notification` - Deploy notification stack (SNS, SQS)
- `npm run deploy:worker` - Deploy worker stack (ECS Fargate)
- `npm run deploy:routes` - Deploy API routes and Lambda integrations
- `npm run deploy:frontend-deployment` - Deploy frontend assets to S3

### Utility Commands

- `npm run build:lambdas` - Build all Lambda functions for ARM64
- `npm run clean:lambdas` - Remove Lambda build artifacts
- `npm run config:write` - Generate frontend config from CloudFormation outputs
- `npm run dcv:download` - Download NICE DCV Web Client SDK (runs automatically during deployment)
- `npm run deploy:frontend-build` - Build React frontend application
- `npm run build` - Compile TypeScript CDK code
- `npm run watch` - Watch TypeScript files for changes

### CDK Commands

- `npx cdk diff` - Compare deployed stack with current state
- `npx cdk synth` - Generate CloudFormation templates
- `npx cdk destroy --all` - Delete all stacks (⚠️ deletes all data)

### Development Commands

- `make test_all` - Run all Go Lambda tests with coverage
- `make docker.build` - Build worker Docker container
- `make docker.upload` - Push worker container to ECR

### Release Commands

- `npm run release:patch` - Create patch release (1.0.0 → 1.0.1)
- `npm run release:minor` - Create minor release (1.0.0 → 1.1.0)
- `npm run release:major` - Create major release (1.0.0 → 2.0.0)
- `npm run release:prerelease` - Create pre-release (1.0.0 → 1.0.1-beta.0)
- `npm run changelog` - Generate changelog from git commits

## Monitoring and Troubleshooting

- **CloudWatch Logs**: Monitor Lambda function and ECS task logs
- **DynamoDB**: Check execution status and step progress
- **S3**: Access execution artifacts (videos, screenshots, logs)
- **SQS**: Monitor queue depth and message processing

## Creating a Release

The project includes an automated release system that creates distributable packages:

```bash
# Create a patch release (bug fixes)
npm run release:patch

# Create a minor release (new features)
npm run release:minor

# Create a major release (breaking changes)
npm run release:major

# Create a pre-release (beta/rc)
npm run release:prerelease
```

The release process automatically:
- Bumps the version in `package.json`
- Generates a changelog from git commits
- Builds Lambda functions and frontend
- Creates a release archive in `/release/`
- Commits changes and creates a git tag
- Pushes to remote repository

### Release Archive Contents

The generated zip file (`nova-act-qa-studio-vX.Y.Z.zip`) contains:
- Pre-built Lambda functions in `lambda/cmd/*/bootstrap` (no Go compiler needed)
- Frontend source code (will be built during deployment)
- Worker source code and Dockerfile
- CDK TypeScript source code
- Configuration templates
- Documentation

### Deploying from Release Archive

```bash
# Extract release
unzip nova-act-qa-studio-v1.2.3.zip
cd nova-act-qa-studio-v1.2.3

# Install dependencies
npm install

# Compile CDK TypeScript
npm run build

# Configure
cp configuration.json.sample configuration.json
# Edit configuration.json with your settings

# Deploy (includes frontend install and build)
npm run deploy:release
```

**How it works:**
1. Installs frontend dependencies
2. Deploys backend stacks (storage, auth, API, etc.)
3. Automatically generates `amplifyconfiguration.json` with Cognito pool IDs
4. Downloads the NICE DCV Web Client SDK (~2.7MB)
5. Builds and deploys the frontend

Users need Node.js and npm, but not Go (Lambdas are pre-built).

**Note:** The DCV SDK download requires `curl` and `unzip` (pre-installed on macOS/Linux).

## Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details on:
- How to submit issues and feature requests
- Development workflow and coding standards
- Pull request process

Please also review our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## Security

See [SECURITY.md](SECURITY.md) for information on reporting security vulnerabilities.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file for details.
