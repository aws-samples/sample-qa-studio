# NovaAct QA Studio - Web Automation Platform

Is a cloud-native web automation platform that enables users to create, manage, and execute browser-based workflows without writing code. Built on AWS with a modern serverless architecture, it combines the power of AI-driven browser automation through Nova Act with an intuitive web interface for creating complex automation scenarios.

## What is NovaAct QA Studio?

NovaAct QA Studio transforms web automation from a developer-only task into an accessible tool for anyone. Users can:

- **Create Automation Workflows**: Define step-by-step browser interactions through a visual interface
- **Execute with AI**: Leverage Nova Act's AI-powered browser automation for intelligent web interactions
- **Schedule Executions**: Set up recurring automation tasks with flexible scheduling
- **Monitor & Debug**: Track execution progress with video recordings, screenshots, and detailed logs
- **Template Variables**: Create dynamic workflows with customizable parameters
- **Scale Automatically**: Cloud-native architecture handles concurrent executions seamlessly

The platform is perfect for web scraping, automated testing, data collection, form filling, and any repetitive browser-based tasks that traditionally required custom scripting.

## Architecture Overview

NovaAct QA Studio follows a modern serverless architecture pattern:

- **Frontend**: React application with AWS Cloudscape Design System
- **API Layer**: AWS API Gateway with Lambda functions (Go)
- **Authentication**: AWS Cognito for secure user management  
- **Data Storage**: DynamoDB with single-table design
- **Execution Engine**: ECS Fargate containers running Python workers
- **Artifact Storage**: S3 for videos, screenshots, and logs
- **Scheduling**: EventBridge Scheduler for automated executions
- **Queue System**: SQS for reliable execution orchestration

## Prerequisites

Before deploying Accept AI, ensure you have:

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
git clone <repository-url>
cd accept-ai

# Install dependencies
npm install
cd frontend && npm install && cd ..
cd lambda && go mod download && cd ..
```

### 2. Build and Deploy

This section will explain how to install and deploy the tool.
We're going to use the Makefile sample to customize it to your own needs

**1. Basic Setup** 

```bash
git clone git@github.com:aws-samples/sample-nova-act-qa-studio.git
cd sample-nova-act-qa-studio
cp Makefile-sample Makefile
cp frontend/src/amplifyconfiguration-sample.json frontend/src/amplifyconfiguration.json
cp frontend/.env-sample frontend/.env
make
```

**2. Adjusting information** 

```json
// Add cognito data to the frontend
// frontend/src/amplifyconfiguration.json
{
  "Auth": {
    "Cognito": {
      "userPoolId": "{'user pool id' from the terminal output}",
      "userPoolClientId": "{'user pool client id' from the terminal output}",
      "region": "{your region}"
    }
  }
}
```

```bash
; update api gateway endpoint for frontend
; frontend/.env
VITE_API_ENDPOINT={'apigateway domain' from the terminal output}
```

```bash
# Update the Makefile
# find the section "cdk.deploy"
cdk.deploy:
	AWS_REGION=eu-central-1 npx cdk deploy --context baseName={your base name}

# find the section "docker.build" and "docker.upload"
docker.build:
	cd worker/ && podman build --platform linux/arm64 -t {your base name}-images .
	podman tag {your base name}:latest {your aws account id}.dkr.ecr.{your region}.amazonaws.com/{your base name}:latest

docker.upload:
	aws ecr get-login-password --region {your region} | podman login --username AWS --password-stdin {your aws account id}.dkr.ecr.eu-central-1.amazonaws.com
	podman push {your aws account id}.dkr.ecr.{your region}.amazonaws.com/{your base name}:latest
```

**3. Deploy again**

```
make
```

This command will:
- Build all Lambda functions for ARM64 architecture
- Build the React frontend
- Deploy the CDK stack to AWS

### 4. Manual Deployment Steps

If you prefer to run each step individually:

```bash
# Build Lambda functions
make lambdas.build

# Build frontend
make frontend.build

# Deploy CDK stack
make cdk.deploy
```

### 5. Worker Container Setup

Build and push the worker container to ECR:

```bash
# Build worker Docker image
make docker.build

# Push to ECR (requires AWS authentication)
make docker.upload
```

### 6. Post-Deployment Configuration

After deployment, you'll need to:

1. **Configure Cognito**: Set up user pool domain and OAuth settings
2. **Update Frontend Config**: Configure the frontend with API Gateway and Cognito endpoints
3. **Test Worker**: Verify ECS task definition can pull and run the worker container

## Development

### Local Development

For local development of individual components:

```bash
# Frontend development server
cd frontend
npm run dev

# Run tests for Lambda functions
make test_all

# Local worker testing (requires AWS credentials)
cd worker
python worker.py
```

### Environment Variables

Key environment variables for different components:

**Worker Container:**
- `NOVA_ACT_API_KEY`: Your Nova Act API key
- `DYNAMODB_TABLE_NAME`: DynamoDB table name (default: accept-ai)
- `S3_BUCKET`: S3 bucket for artifacts
- `AWS_REGION`: AWS region (default: eu-central-1)

**Lambda Functions:**
- `TABLE_NAME`: DynamoDB table name
- `QUEUE_URL`: SQS queue URL
- `BUCKET_NAME`: S3 bucket name

## Usage

1. **Access the Web Interface**: Navigate to the CloudFront distribution URL
2. **Create Account**: Sign up through the Cognito-powered authentication
3. **Create Usecase**: Define your automation workflow with a starting URL
4. **Add Steps**: Define browser actions using natural language instructions
5. **Configure Secrets**: Store sensitive data (passwords, API keys) securely
6. **Execute**: Run your automation and monitor progress in real-time
7. **Review Results**: Access video recordings and execution logs

### Step Types

Accept AI supports two types of workflow steps:

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

### CDK Commands
- `npm run build`: Compile TypeScript to JavaScript
- `npm run watch`: Watch for changes and compile
- `npx cdk deploy`: Deploy stack to AWS
- `npx cdk diff`: Compare deployed stack with current state
- `npx cdk synth`: Generate CloudFormation template

### Development Commands
- `make test_all`: Run all Go tests with coverage
- `make docker.build`: Build worker container
- `make docker.upload`: Push container to ECR
- `make deploy`: Full build and deployment

## Monitoring and Troubleshooting

- **CloudWatch Logs**: Monitor Lambda function and ECS task logs
- **DynamoDB**: Check execution status and step progress
- **S3**: Access execution artifacts (videos, screenshots, logs)
- **SQS**: Monitor queue depth and message processing

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `make test_all`
5. Submit a pull request

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

## Support

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.
