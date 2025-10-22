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

Update `configuration.json` with your settings:

```json
{
  "baseName": "nova-act-qa-studio",
  "adminEmail": "your-email@example.com",
  "userAgentString": null
}
```

### 3. Deploy Everything

```bash
npm run deploy
```

This single command will:
- Build all Lambda functions for ARM64 architecture
- Deploy all infrastructure stacks (storage, auth, API, notification, worker, routes, frontend)
- Generate frontend configuration files automatically
- Build and deploy the React frontend to S3/CloudFront
- Clean up build artifacts

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
  --secret-id nova-act-qa-studio-nova-api-key \
  --secret-string "your-nova-act-api-key"
```

That's it! Your Nova Act QA Studio is now deployed and ready to use. Access the application through the CloudFront distribution URL from the deployment outputs.

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

- `npm run deploy` - Complete deployment of all stacks and frontend

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
- Pre-built Lambda functions (no Go compiler needed)
- Built frontend application
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
cd frontend && npm install && cd ..

# Compile CDK TypeScript
npm run build

# Configure
cp configuration.json.sample configuration.json
# Edit configuration.json with your settings

# Deploy (Lambdas already built!)
npm run deploy
```

Users need Node.js and npm, but not Go (Lambdas are pre-built).

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
