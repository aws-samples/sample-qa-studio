# QA Studio

An AI-powered automated testing platform built on Amazon Nova Act. QA Studio enables teams to create, manage, and execute web application tests using natural language instructions.

## What is QA Studio?

QA Studio is a complete testing solution that combines:

- **Web Application**: A full-featured platform for defining tests in natural language, executing them with AI-powered browser automation, and reviewing results with video recordings, screenshots, and detailed logs
- **CLI Tool**: Command-line interface for authentication, test management, and local test execution

Tests are written as plain English instructions (e.g., "Click the Login button", "Verify the dashboard loads"), making test creation accessible to both technical and non-technical team members.

> **Note:** This reference solution is provided for demonstration purposes. Ensure it meets your organization's operational and security requirements before production use.



## Key Features

### Web Application
- **Natural Language Testing**: Define test steps in plain English through an intuitive web interface
- **AI-Powered Execution**: Amazon Nova Act performs browser automation and validates test outcomes
- **Network Assertion**: Intercept HTTP requests triggered by UI actions to verify API contracts and mock responses on the fly, without a separate integration-test harness. Supports `exact`, `subset`, and JSON Schema (Draft 2020-12) body matching for requests; `subset` and schema matching for responses; plus optional response status assertion.
- **Interactive Wizard**: Build tests step-by-step with a live browser, watching each action execute in real-time
- **AI Test Generation**: Describe user journeys in plain language and let AI generate complete test cases
- **Rich Artifacts**: Review video recordings, screenshots, traces, and logs for every test execution
- **Test Suites**: Group related tests for batch execution and comprehensive coverage
- **Templates**: Create reusable test blueprints with configurable variables
- **User Management**: Control access with Amazon Cognito authentication and role-based permissions
- **OAuth Integration**: Generate API credentials for programmatic access and automation

### CLI Tool
- **Browser-Based Authentication**: Secure OAuth (PKCE) flow against AWS Cognito
- **Test Management**: Create, update, and execute tests from the command line
- **Configuration Management**: Store and manage environment-specific settings
- **Local Execution**: Run tests locally during development with full artifact capture
- **Suite Execution**: Run entire test suites with parallel execution support

## Architecture

![QA Studio Architecture](docs/architecture.png)

QA Studio is built on AWS serverless architecture:

- **Frontend**: React application with AWS Cloudscape Design System (CloudFront + S3)
- **API Layer**: Amazon API Gateway with AWS Lambda functions
- **Authentication**: Amazon Cognito for user and machine-to-machine authentication
- **Data Storage**: Amazon DynamoDB with single-table design
- **Test Execution**: Amazon ECS with AWS Fargate, running the `qa-studio` CLI as the container entrypoint
- **Browser Automation**: Amazon Bedrock AgentCore Browser Tool for managed remote browsers
- **Queue System**: Amazon SQS for reliable execution orchestration
- **Artifact Storage**: Amazon S3 for videos, screenshots, logs, and traces

The `qa-studio` CLI is the single execution runtime: developer-run tests, CI-run tests, and cloud-triggered ECS worker tasks all invoke the same code path. The cloud worker container is a thin shell around the CLI — `entrypoint.sh` translates ECS environment variables into CLI flags and execs `qa-studio run`. Wizard-mode tasks (interactive step-by-step execution) still use the legacy path until that migration lands separately.

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
├── qa-studio-cli/        # Command-line tool
│   ├── qa_studio_cli/    # CLI implementation
│   ├── tests/            # Unit tests
│   └── README.md         # CLI installation and usage guide
│
├── docs/                 # Comprehensive documentation
│   ├── architecture.md   # System architecture and design
│   ├── user-guide.md     # Web interface walkthrough
│   ├── api-reference.md  # Complete API documentation
│   └── best-practices.md # Testing and security guidance
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
cd sample-qa-studio/web-app
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

### CLI Tool Installation

Install the command-line tool for local development and test management:

**Prerequisites**:
- Python 3.11+
- pip (Python package manager)
- Node.js 18+ (for skill installation via `npx`)

**Installation**:
```bash
cd sample-qa-studio

# Install CLI tool
pip install -e ./qa-studio-cli

# For local test execution, install with runner dependencies
pip install -e "./qa-studio-cli[runner]"

# Configure with your environment
qa-studio configure

# Authenticate via browser
qa-studio login

# Run tests locally
qa-studio run --usecase-id test-123
```

### Agent Skill Installation

QA Studio includes an agent skill for Kiro IDE and other coding agents. Install it using the open [skills CLI](https://github.com/vercel-labs/skills):

```bash
# Install the QA Studio skill for Kiro
npx skills add <repository-url> --skill qa-studio -a kiro-cli

# Or install for all detected agents
npx skills add <repository-url> --skill qa-studio
```

See the [CLI README →](qa-studio-cli/README.md) for detailed skill setup instructions.

**Detailed Guide**: See [CLI README →](qa-studio-cli/README.md) for complete installation, configuration, and usage instructions.

## Documentation

### Getting Started
- [Web App Setup →](web-app/README.md) - Deploy the full platform to AWS
- [CLI Installation →](qa-studio-cli/README.md) - Install command-line tool

### Using QA Studio
- [User Guide →](docs/user-guide.md) - Complete walkthrough of the web interface
- [Prompting Best Practices →](docs/prompting-best-practices.md) - Writing effective test steps
- [Best Practices →](docs/best-practices.md) - Test organization, security, and performance

### Reference
- [Architecture →](docs/architecture.md) - System design and data flows
- [API Reference →](docs/api-reference.md) - Complete API documentation
- [CLI Reference →](qa-studio-cli/README.md) - Command-line usage

### Troubleshooting
- [Troubleshooting Guide →](docs/troubleshooting.md) - Common issues and solutions
- [Development Guide →](docs/development.md) - Development workflows and commands

## Use Cases

### Manual Testing Teams
Create and execute tests through the web interface without writing code. Use the interactive wizard to build tests step-by-step, or describe user journeys in plain language and let AI generate the tests.

### QA Automation Engineers
Build comprehensive test suites with variables, templates, and reusable components. Execute tests locally with the CLI during development for rapid feedback.

### DevOps Teams
Execute tests locally or in CI/CD pipelines using the CLI tool. Run smoke tests on every commit, regression tests on every PR, and full test suites on nightly schedules.

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

Copyright 2010-2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.

This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
either express or implied. See the License for the specific language governing permissions and
limitations under the License.

---

**Built with Amazon Nova Act** - AI-powered browser automation for reliable, maintainable web application testing.
