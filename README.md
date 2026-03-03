# QA Studio

An AI-powered automated testing platform built on Amazon Nova Act. QA Studio enables teams to create, manage, and execute web application tests using natural language instructions, with comprehensive CI/CD integration capabilities.

## What is QA Studio?

QA Studio is a complete testing solution that combines:

- **Web Application**: A full-featured platform for defining tests in natural language, executing them with AI-powered browser automation, and reviewing results with video recordings, screenshots, and detailed logs
- **CLI Tools**: Command-line interfaces for authentication, test management, and CI/CD integration
- **CI/CD Runner**: Docker-based test execution for seamless integration into any CI/CD pipeline

Tests are written as plain English instructions (e.g., "Click the Login button", "Verify the dashboard loads"), making test creation accessible to both technical and non-technical team members.

## Key Features

### Web Application
- **Natural Language Testing**: Define test steps in plain English through an intuitive web interface
- **AI-Powered Execution**: Amazon Nova Act performs browser automation and validates test outcomes
- **Interactive Wizard**: Build tests step-by-step with a live browser, watching each action execute in real-time
- **AI Test Generation**: Describe user journeys in plain language and let AI generate complete test cases
- **Rich Artifacts**: Review video recordings, screenshots, traces, and logs for every test execution
- **Test Suites**: Group related tests for batch execution and comprehensive coverage
- **Templates**: Create reusable test blueprints with configurable variables
- **User Management**: Control access with Amazon Cognito authentication and role-based permissions
- **OAuth Integration**: Generate API credentials for programmatic access and automation

### CLI Tools
- **Browser-Based Authentication**: Secure OAuth (PKCE) flow against AWS Cognito
- **Test Management**: Create, update, and execute tests from the command line
- **Configuration Management**: Store and manage environment-specific settings
- **Local Development**: Run tests locally during development with full artifact capture

### CI/CD Integration
- **Docker Container**: Pre-built container for easy integration into any CI/CD platform
- **OAuth Authentication**: Machine-to-machine authentication with client credentials flow
- **Parallel Execution**: Run multiple tests simultaneously for faster feedback
- **Environment Overrides**: Test against different environments (staging, production) with base URL substitution
- **Variable Overrides**: Customize test behavior with runtime variable injection
- **Comprehensive Reporting**: Detailed execution summaries with exit codes for workflow control
- **Artifact Capture**: Automatic collection of videos, logs, traces, and screenshots

## Architecture

QA Studio is built on AWS serverless architecture:

- **Frontend**: React application with AWS Cloudscape Design System (CloudFront + S3)
- **API Layer**: Amazon API Gateway with AWS Lambda functions
- **Authentication**: Amazon Cognito for user and machine-to-machine authentication
- **Data Storage**: Amazon DynamoDB with single-table design
- **Test Execution**: Amazon ECS with AWS Fargate running Nova Act SDK
- **Browser Automation**: Amazon Bedrock AgentCore Browser Tool for managed remote browsers
- **Queue System**: Amazon SQS for reliable execution orchestration
- **Artifact Storage**: Amazon S3 for videos, screenshots, logs, and traces

For detailed architecture information, see [Architecture Documentation →](docs/architecture.md)

## Repository Structure

```
├── web-app/              # Web application and infrastructure
│   ├── bin/              # CDK app entry point
│   ├── lib/              # CDK stack definitions
│   ├── lambdas/          # Python Lambda function handlers
│   ├── frontend/         # React web application
│   ├── worker/           # Nova Act test execution engine
│   └── README.md         # Web app setup and deployment guide
│
├── qa-studio-cli/        # Command-line tools
│   ├── qa_studio_cli/    # CLI implementation
│   ├── tests/            # Unit tests
│   └── README.md         # CLI installation and usage guide
│
├── docs/                 # Comprehensive documentation
│   ├── README.md         # CI/CD runner documentation hub
│   ├── architecture.md   # System architecture and design
│   ├── user-guide.md     # Web interface walkthrough
│   ├── installation.md   # CI/CD runner setup guide
│   ├── configuration.md  # Configuration reference
│   ├── api-reference.md  # Complete API documentation
│   ├── best-practices.md # Testing and security guidance
│   └── ci-cd-integration/ # Platform-specific CI/CD guides
│
└── testcases/            # Sample test case definitions
```

## Getting Started

### Web Application Deployment

Deploy the full QA Studio platform to AWS:

**Prerequisites**:
- AWS CLI configured with appropriate permissions
- Node.js 18+ and npm
- Python 3.11+
- Docker or Podman

**Quick Start**:
```bash
# Clone and install dependencies
git clone <repository-url>
cd sample-nova-act-qa-studio/web-app
npm install

# Configure (set your admin email)
cp configuration.json.sample configuration.json
# Edit configuration.json with your email

# Deploy to AWS
npm run deploy
```

The deployment will:
1. Build all Lambda functions and infrastructure
2. Deploy CDK stacks to AWS
3. Build and deploy the React frontend
4. Send temporary password to your admin email

Access the web interface using the CloudFront URL from the deployment output.

**Detailed Guide**: See [Web App README →](web-app/README.md) for complete setup instructions, configuration options, and development workflows.

### CLI Tools Installation

Install command-line tools for local development and test management:

**Prerequisites**:
- Python 3.11+
- pip (Python package manager)

**Installation**:
```bash
cd sample-nova-act-qa-studio

# Install CLI tools
pip install -e ./qa-studio-cli

# Configure with your environment
qa-studio configure

# Authenticate via browser
qa-studio login
```

**Detailed Guide**: See [CLI README →](qa-studio-cli/README.md) for complete installation, configuration, and usage instructions.

### CI/CD Integration

Execute test suites in your CI/CD pipelines:

**Prerequisites**:
- Docker installed and running
- OAuth client credentials from QA Studio platform
- Network access to API endpoint and Cognito

**Quick Start**:
```bash
# Create OAuth client in QA Studio web interface
# Then run tests with Docker:

docker run --rm \
  -e OAUTH_CLIENT_ID="your-client-id" \
  -e OAUTH_CLIENT_SECRET="your-client-secret" \
  -e OAUTH_TOKEN_ENDPOINT="https://domain.auth.region.amazoncognito.com/oauth2/token" \
  -e API_ENDPOINT="https://api.example.com" \
  qa-studio-runner:latest \
  --suite-id suite-123 \
  --base-url https://staging.example.com
```

**Detailed Guides**:
- [Installation Guide →](docs/installation.md) - OAuth setup and container installation
- [Configuration Reference →](docs/configuration.md) - Environment variables and CLI arguments
- [GitHub Actions →](docs/ci-cd-integration/github-actions.md) - Workflow configuration
- [GitLab CI →](docs/ci-cd-integration/gitlab-ci.md) - Pipeline configuration
- [Jenkins →](docs/ci-cd-integration/jenkins.md) - Declarative pipeline setup
- [CircleCI →](docs/ci-cd-integration/circleci.md) - Configuration with contexts
- [Generic Docker →](docs/ci-cd-integration/generic-docker.md) - Platform-agnostic usage

## Documentation

### Getting Started
- [Web App Setup →](web-app/README.md) - Deploy the full platform to AWS
- [CLI Installation →](qa-studio-cli/README.md) - Install command-line tools
- [CI/CD Installation →](docs/installation.md) - Set up test execution in pipelines

### Using QA Studio
- [User Guide →](docs/user-guide.md) - Complete walkthrough of the web interface
- [Prompting Best Practices →](docs/prompting-best-practices.md) - Writing effective test steps
- [Best Practices →](docs/best-practices.md) - Test organization, security, and performance

### Reference
- [Architecture →](docs/architecture.md) - System design and data flows
- [API Reference →](docs/api-reference.md) - Complete API documentation
- [Configuration →](docs/configuration.md) - Environment variables and settings
- [CLI Reference →](docs/cli-reference.md) - Command-line usage

### CI/CD Integration
- [GitHub Actions →](docs/ci-cd-integration/github-actions.md)
- [GitLab CI →](docs/ci-cd-integration/gitlab-ci.md)
- [Jenkins →](docs/ci-cd-integration/jenkins.md)
- [CircleCI →](docs/ci-cd-integration/circleci.md)
- [Generic Docker →](docs/ci-cd-integration/generic-docker.md)

### Troubleshooting
- [Troubleshooting Guide →](docs/troubleshooting.md) - Common issues and solutions
- [Development Guide →](docs/development.md) - Development workflows and commands

## Use Cases

### Manual Testing Teams
Create and execute tests through the web interface without writing code. Use the interactive wizard to build tests step-by-step, or describe user journeys in plain language and let AI generate the tests.

### QA Automation Engineers
Build comprehensive test suites with variables, templates, and reusable components. Execute tests locally with the CLI during development, then integrate into CI/CD pipelines for continuous testing.

### DevOps Teams
Integrate test execution into deployment pipelines with Docker containers. Run smoke tests on every commit, regression tests on every PR, and full test suites on nightly schedules.

### Product Teams
Review test results with video recordings and screenshots to understand exactly what happened during test execution. Share test cases across teams using JSON import/export.

## Technology Stack

- **Frontend**: React, TypeScript, AWS Cloudscape Design System, Vite
- **Backend**: AWS Lambda (Python 3.11), Amazon API Gateway
- **Authentication**: Amazon Cognito with OAuth 2.0
- **Data**: Amazon DynamoDB (single-table design), Amazon S3
- **Test Execution**: Amazon Nova Act SDK, Amazon Bedrock AgentCore Browser Tool
- **Infrastructure**: AWS CDK (TypeScript), Amazon ECS with Fargate
- **CLI**: Python 3.11+, Click framework

## Security

QA Studio implements comprehensive security measures:

- **Authentication**: OAuth 2.0 with client credentials flow for M2M, PKCE flow for users
- **Authorization**: Scope-based access control with fine-grained permissions
- **Encryption**: Data encrypted at rest (DynamoDB, S3) and in transit (TLS 1.2+)
- **Secret Management**: AWS Secrets Manager for sensitive test data
- **Network Security**: API Gateway with rate limiting, DDoS protection via AWS Shield
- **Audit Logging**: All API requests logged to CloudWatch with user identity

For security best practices and guidelines, see [Best Practices →](docs/best-practices.md)

## Contributing

Contributions are welcome! Please review the following before contributing:

- [Contributing Guidelines](CONTRIBUTING.md) - Development workflow and coding standards
- [Code of Conduct](CODE_OF_CONDUCT.md) - Community guidelines
- [Security Policy](SECURITY.md) - Reporting security vulnerabilities

## Support

- **Documentation**: [Complete documentation](docs/)
- **Issues**: Report bugs and request features via GitHub Issues
- **Architecture**: [System architecture and design](docs/architecture.md)
- **API**: [Complete API reference](docs/api-reference.md)

## License

This project is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file for details.

---

**Built with Amazon Nova Act** - AI-powered browser automation for reliable, maintainable web application testing.
