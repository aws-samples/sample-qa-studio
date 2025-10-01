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

### 2. Build and Deploy

This section will explain how to install and deploy the tool.
We're going to use the Makefile sample to customize it to your own needs

**1. Initial deployment**

```bash
cp Makefile-sample Makefile
cp frontend/src/amplifyconfiguration-sample.json frontend/src/amplifyconfiguration.json
cp frontend/.env-sample frontend/.env
make deploy
```

This command will:

- Build all Lambda functions for ARM64 architecture
- Build the React frontend
- Build and deploy the CDK Stack to AWS

> Note the CloudFormation outputs printed in the terminal at the end of the `make deploy` execution - you'll need these values for the next steps.

**2. Adjusting information**

Make the following changes to your local project and AWS resources:

- Update the Amplify config at [frontend/src/amplifyconfiguration.json](frontend/src/amplifyconfiguration.json) with the Cognito User Pool:

```json
{
  "Auth": {
    "Cognito": {
      "userPoolId": "{'user pool id' from the terminal output}",
      "userPoolClientId": "{'user pool client id' from the terminal output}",
      "region": "{your user pool region}"
    }
  }
}
```

- Update [frontend/.env](frontend/.env) with the API Gateway invoke URL;

```bash
VITE_API_ENDPOINT={'apigateway domain' from the terminal output}
```

- Update the [Makefile](./Makefile) with your ECR Repository details from the CDK outputs:
  - Replace `{repository-name}` with the `EcrName` output
  - Replace `{repository-uri}` with the `EcrUri` output  
  - Replace `{registry-hostname}` with the `EcrHostname` output
  - Replace `{region}` with your AWS region

- Upload your Nova Act API Key to the `nova-act-qa-studio-nova-api-key` Secrets Manager Secret:
  - Go to AWS Console → Secrets Manager → `nova-act-qa-studio-nova-api-key`
  - Click "Retrieve secret value" → "Edit"
  - Replace the placeholder value with your actual Nova Act API key
  - Click "Save"

**3. Deploy again**

```
make deploy
```

### 4. Worker Container Setup

Build and push the worker container to ECR:

```bash
# Build worker Docker image
make docker.build

# Push to ECR (requires AWS authentication)
make docker.upload
```

### 5. Post-Deployment

After deployment, you'll need to:

1. **Create First User**: Go to AWS Console → Cognito → User Pools → nova-act-qa-studio-user-pool → Users → Create user with your email address
2. **Access Application**: Navigate to the CloudFront distribution URL from the deployment outputs
3. **First Login**: Sign in with the user credentials you created in step 1

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
- `DYNAMODB_TABLE_NAME`: DynamoDB table name (default: nova-act-qa-studio)
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
