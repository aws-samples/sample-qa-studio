# Product Design Document: Local Development Environment with Local Web Services

**Document Version:** 1.0  
**Date:** March 5, 2026  
**Author:** Jan
**Status:** Draft for Review

---

## Executive Summary

This document proposes integrating **Local Web Services (LWS)** into the QA Studio development workflow to dramatically reduce the development cycle time from 8-10 minutes per deployment to under 30 seconds for full stack restarts and under 5 seconds for Lambda code changes.

**Current Problem**: The QA Studio serverless architecture (API Gateway, Lambda, DynamoDB, S3, Cognito) requires full CDK deployments for every code change, taking 8-10 minutes. With 2 developers making ~10 deploys per day, this results in approximately 3.3 hours per day lost to waiting, plus significant context switching costs.

**Proposed Solution**: Local Web Services is an open-source tool that emulates AWS services locally, enabling developers to run the entire stack on their laptop. It parses CDK CloudFormation templates and creates local endpoints for all AWS services, with hot reload for Lambda functions and instant feedback loops.

**Key Benefits**:
- **Speed**: 8-10 minutes → <30 seconds for full stack restart, <5 seconds for Lambda changes
- **Productivity**: Eliminate 3+ hours/day of waiting time
- **Developer Experience**: Enable rapid iteration on UI/API integration with local CORS support
- **Cost**: Zero AWS costs during local development
- **Testing**: Enable local integration testing before deployment

**Scope**: This implementation covers API Gateway, Lambda (Python 3.11), DynamoDB, S3, Cognito, and Secrets Manager. Nova Act and Bedrock calls will continue to hit real AWS services as they require remote execution.

---

## 1. Current State Analysis

### 1.1 Architecture Overview

QA Studio is built on AWS serverless architecture with the following components:

- **Frontend**: React application with AWS Cloudscape Design System (CloudFront + S3)
- **API Layer**: Amazon API Gateway (REST API) with Lambda authorizers
- **Compute**: AWS Lambda functions (Python 3.11+)
- **Data Storage**: Amazon DynamoDB with 2 Global Secondary Indexes
- **Authentication**: Amazon Cognito with JWT token validation
- **Artifact Storage**: Amazon S3 for test recordings, screenshots, and logs
- **Test Execution**: Amazon ECS with Fargate running Nova Act SDK
- **Queue System**: Amazon SQS for execution orchestration
- **Secrets**: AWS Secrets Manager (primarily for worker)

### 1.2 CDK Stack Structure

The infrastructure is organized into multiple interdependent CDK stacks:

- `auth-stack`: Cognito User Pool and authentication configuration
- `storage-stack`: DynamoDB tables and S3 buckets
- `lambda-stack`: Lambda function definitions and IAM roles
- `api-stack`: API Gateway with routes and Lambda integrations
- `worker-stack`: ECS cluster, task definitions, and Fargate services
- `frontend-stack`: CloudFront distribution and S3 bucket for React app

**Critical Constraint**: All stacks have dependencies on each other, requiring full deployment of all stacks on every change.

### 1.3 Current Development Workflow

**Typical Development Cycle**:
1. Developer makes code change (Lambda, frontend, or infrastructure)
2. Run `npm run deploy`
3. Wait 8-10 minutes for:
   - CDK synthesis
   - CloudFormation stack updates
   - Lambda function packaging and upload
   - Asset deployment to S3
   - CloudFront cache invalidation (for frontend changes)
4. Test the change in deployed environment
5. Repeat

**Frequency**: Each developer performs approximately 10 deploys per day during active development.

### 1.4 Pain Points

#### 1.4.1 Deployment Time
- **8-10 minutes per deployment** creates significant friction
- Full stack deployment required even for single Lambda function changes
- No incremental deployment option due to stack interdependencies

#### 1.4.2 Frontend Development Blocked
- **No local CORS support**: Frontend developers cannot run React dev server against local API
- Frontend changes require full CDK deploy to test with real API Gateway
- Cannot rapidly iterate on UI/API interactions
- Vite dev server exists but cannot connect to backend

#### 1.4.3 Integration Testing Gaps
- **No local API Gateway + Lambda testing**: Cannot test request/response flows locally
- **No local Cognito testing**: Cannot test authentication flows without deploying
- **No local DynamoDB testing**: Cannot test queries and GSI access patterns locally
- Unit tests exist but no local integration tests

#### 1.4.4 Developer Experience
- **Context switching**: Developers lose focus during 10-minute waits
- **Productivity loss**: Common activities during deployment waits:
  - Check Slack/email
  - Start unrelated tasks
  - Lose context on the problem being solved
- **No hot reload**: Every Lambda code change requires full redeploy

### 1.5 Productivity Impact

**Quantified Cost**:
- 2 developers × 10 deploys/day × 10 minutes = **200 minutes/day** (3.3 hours)
- **~16.5 hours per week** of pure waiting time
- Does not account for context switching overhead

**Additional Impacts**:
- Slower onboarding for new developers (cannot experiment locally)
- Higher AWS costs for development deployments
- Delayed feedback loops reduce code quality
- Upcoming CI/CD pipeline will compound deployment time issues

### 1.6 Current Testing Approach

- **Unit tests**: Python unit tests for Lambda functions
- **No integration tests**: Cannot test full request flows locally
- **Manual testing**: All integration testing happens post-deployment
- **No CI/CD yet**: Pipeline planned but not implemented

### 1.7 Worker Considerations

The ECS/Fargate worker running Nova Act SDK:
- Changes less frequently than API/frontend code
- Still requires full deployment when modified
- Ideally should be testable locally for development
- Nova Act and Bedrock calls must remain remote (no local emulation possible)

---

## 2. Proposed Solution

### 2.1 Solution Overview

Integrate **Local Web Services (LWS)** to enable local development and testing of the entire QA Studio stack without AWS deployments.

**What is Local Web Services?**

Local Web Services is an open-source tool that emulates AWS services locally for development and testing. It parses CDK CloudFormation templates from `cdk.out/` and recreates the entire stack locally with AWS-compatible API endpoints.

**Key Capabilities**:
- Reads CDK synthesis output automatically
- Starts local providers for all AWS services used
- Provides AWS SDK-compatible endpoints
- Supports hot reload for Lambda functions
- Includes web dashboard for observability
- Zero AWS credentials or costs required

**Project**: https://local-web-services.github.io  
**License**: MIT (Open Source)

### 2.2 Service Coverage

LWS supports all critical QA Studio services:

| Service | Support Level | Notes |
|---------|--------------|-------|
| **API Gateway** | ✅ Full | REST API, Lambda authorizers, CORS |
| **Lambda** | ✅ Full | Python 3.11, hot reload, timeout enforcement |
| **DynamoDB** | ✅ Full | Query, GSI, transactions (SQLite backend) |
| **S3** | ✅ Full | Object storage, presigned URLs |
| **Cognito** | ⚠️ Real AWS | Use real Cognito for authentication |
| **Secrets Manager** | ✅ Full | In-memory secret storage |
| **CloudFront** | ⚠️ Not needed | Direct API access locally |
| **SQS** | ✅ Supported | Can be ignored per requirements |
| **ECS/Fargate** | ⚠️ Subprocess | Worker runs as local process |
| **Nova Act** | ❌ Remote only | Must call real AWS Bedrock |
| **Bedrock** | ❌ Remote only | AI services require remote execution |

### 2.3 How It Works

#### CDK Mode Operation

1. **Parse**: LWS reads `cdk.out/` CloudFormation templates generated by `cdk synth`
2. **Graph**: Builds dependency graph of resources (tables, functions, APIs)
3. **Start**: Spins up local service providers in topological order
4. **Redirect**: Sets `AWS_ENDPOINT_URL_*` environment variables so Lambda handlers call local services
5. **Execute**: Lambda functions run in official AWS Lambda Docker images with hot reload

#### Developer Workflow

```bash
# Terminal 1: Start local AWS services
uvx --from local-web-services ldk dev

# Terminal 2: Start React dev server
cd frontend && npm run dev

# Edit Lambda code → hot reload picks up changes in <5 seconds
# Edit React code → Vite hot reload + local API with CORS
```

### 2.4 Architecture Integration

```
┌─────────────────────────────────────────────────────────┐
│                    Developer Laptop                      │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐         ┌─────────────────────────┐  │
│  │ React Dev    │  HTTP   │  Local Web Services     │  │
│  │ Server       │────────▶│  (ldk dev)              │  │
│  │ (Vite)       │         │                         │  │
│  │ :5173        │         │  ┌──────────────────┐   │  │
│  └──────────────┘         │  │ API Gateway      │   │  │
│                            │  │ :3000            │   │  │
│                            │  └────────┬─────────┘   │  │
│                            │           │             │  │
│                            │  ┌────────▼─────────┐   │  │
│                            │  │ Lambda Functions │   │  │
│                            │  │ (hot reload)     │   │  │
│                            │  └────────┬─────────┘   │  │
│                            │           │             │  │
│                            │  ┌────────▼─────────┐   │  │
│                            │  │ DynamoDB (SQLite)│   │  │
│                            │  │ S3 (filesystem)  │   │  │
│                            │  │ Cognito (memory) │   │  │
│                            │  └──────────────────┘   │  │
│                            └─────────────────────────┘  │
│                                                           │
└─────────────────────────────────────────────────────────┘
                              │
                              │ (Only for Nova Act/Bedrock)
                              ▼
                    ┌──────────────────┐
                    │   Real AWS       │
                    │   - Bedrock      │
                    │   - Nova Act     │
                    └──────────────────┘
```

### 2.5 Benefits

#### Speed Improvements
- **Full stack restart**: 8-10 minutes → <30 seconds
- **Lambda code changes**: 8-10 minutes → <5 seconds (hot reload)
- **Frontend changes**: Instant (Vite hot reload + local API)

#### Developer Experience
- **CORS enabled**: React dev server can call local API Gateway
- **Rapid iteration**: Edit code → see results immediately
- **No context switching**: No 10-minute waits
- **Local integration testing**: Test full request flows before deployment

#### Cost & Security
- **Zero AWS costs**: No development deployments
- **Zero credentials**: No AWS access keys needed locally
- **Isolated environments**: Each developer has their own stack

#### Team Productivity
- **3.3 hours/day saved**: Eliminate deployment waiting time
- **Better code quality**: Faster feedback loops
- **Easier onboarding**: New developers can run stack locally
- **CI/CD ready**: Fast integration tests in pipeline

---

## 3. Technical Architecture

### 3.1 Local Web Services Components

#### 3.1.1 Core Components

**ldk (Local Development Kit)**
- CLI tool: `uvx --from local-web-services ldk dev`
- Parses `cdk.out/` directory
- Starts all service providers
- Manages hot reload and file watching
- Provides web dashboard at `http://localhost:3000/_ldk/gui`

**Service Providers**
- Each AWS service gets its own HTTP endpoint
- Speaks AWS SDK-compatible API
- Backed by appropriate storage (SQLite for DynamoDB, filesystem for S3, memory for Cognito)

**Lambda Runtime**
- Uses official AWS Lambda Docker images
- Mounts Lambda code as volumes
- Watches for file changes and reloads
- Sets environment variables to point to local services

#### 3.1.2 Service Endpoints

When `ldk dev` runs, it creates local endpoints:

```
API Gateway:     http://localhost:3000
DynamoDB:        http://localhost:8000
S3:              http://localhost:4566
Cognito:         http://localhost:9229
Secrets Manager: http://localhost:4584
Lambda:          (invoked internally)
```

### 3.2 Integration with QA Studio CDK

#### 3.2.1 CDK Synthesis

LWS requires CDK synthesis output:

```bash
# Generate CloudFormation templates
npm run cdk synth

# This creates cdk.out/ directory with:
# - CloudFormation templates for each stack
# - Asset manifests
# - Construct tree metadata
```

LWS reads this output to understand:
- DynamoDB table schemas and GSI definitions
- Lambda function handlers and runtimes
- API Gateway routes and integrations
- Cognito user pool configuration
- S3 bucket names
- IAM roles and policies

#### 3.2.2 Lambda Function Discovery

LWS automatically discovers Lambda functions from CDK:

```typescript
// From lambda-stack.ts
new lambda.Function(this, 'GetUseCasesFunction', {
  runtime: lambda.Runtime.PYTHON_3_11,
  handler: 'get_usecases.handler',
  code: lambda.Code.fromAsset('lambdas/endpoints'),
  environment: {
    TABLE_NAME: props.table.tableName,
  },
});
```

LWS extracts:
- Handler path: `lambdas/endpoints/get_usecases.py`
- Runtime: Python 3.11
- Environment variables: `TABLE_NAME`
- IAM permissions (for local IAM emulation)

#### 3.2.3 API Gateway Route Mapping

LWS parses API Gateway definitions:

```typescript
// From api-stack.ts
const useCasesResource = api.root.addResource('usecases');
useCasesResource.addMethod('GET', 
  new apigateway.LambdaIntegration(getUseCasesFunction),
  {
    authorizer: cognitoAuthorizer,
  }
);
```

LWS creates local route:
- `GET /usecases` → invokes local Lambda
- Validates JWT token via local Cognito
- Returns response with proper CORS headers

### 3.3 Authentication Flow

#### 3.3.1 Cognito Integration (Real AWS)

**Decision**: Use real AWS Cognito instead of local emulation

**Rationale**:
- Lambda authorizers require proper JWT token validation
- Local Cognito emulation has limitations with token format
- Ensures authentication works identically locally and in production
- Minimal impact since Cognito calls are infrequent

**Configuration**:
```json
// frontend/src/api-config.local.json (CREATE THIS for local dev)
{
  "apiUrl": "http://localhost:3000/",  // Local API Gateway
  "region": "eu-central-1"              // Your AWS region
}
```

**Cognito Configuration**: Use the existing `frontend/src/amplifyconfiguration.json` from your AWS deployment (no changes needed).

#### 3.3.2 Authentication Flow

1. User logs in via frontend
2. Frontend calls **real AWS Cognito** for authentication
3. Cognito returns JWT tokens (ID, access, refresh)
4. Frontend includes JWT in API requests to **local API Gateway**
5. Local API Gateway Lambda authorizer validates JWT against **real Cognito**
6. Request proceeds to local Lambda functions

**Hybrid Approach**:
- Authentication: Real AWS Cognito
- API calls: Local API Gateway
- Business logic: Local Lambda functions
- Data storage: Local DynamoDB

### 3.4 Data Persistence

#### 3.4.1 DynamoDB (SQLite Backend)

- Tables created from CDK schema
- GSI definitions preserved
- Data persists in `.ldk/dynamodb.db`
- Can be reset with `ldk reset`

#### 3.4.2 S3 (Filesystem Backend)

- Buckets map to directories in `.ldk/s3/`
- Object metadata stored alongside files
- Presigned URLs work locally

#### 3.4.3 Secrets Manager (In-Memory)

- Secrets defined in CDK are pre-seeded
- Additional secrets can be added via AWS CLI commands
- Data lost on restart (acceptable for development)

### 3.5 Hot Reload Mechanism

#### 3.5.1 Lambda Hot Reload

1. LWS watches Lambda source directories
2. On file change detected:
   - Reloads Python module
   - Clears import cache
   - Next invocation uses new code
3. Reload time: <5 seconds

#### 3.5.2 Frontend Hot Reload

- Vite dev server provides instant HMR
- API calls go to local LWS endpoint
- CORS configured automatically

### 3.6 Worker Execution

#### 3.6.1 Local Worker Process

The ECS worker can run as a local subprocess:

```bash
# Worker runs locally but calls real AWS for Nova Act
cd worker
python worker.py
```

Environment variables point to:
- Local DynamoDB for test case data
- Local S3 for artifact storage
- Real AWS Bedrock for Nova Act execution

#### 3.6.2 Hybrid Approach

- Worker orchestration logic runs locally
- Nova Act SDK calls hit real AWS Bedrock
- Test artifacts stored in local S3
- Execution status updated in local DynamoDB

---

## 4. Implementation Plan

### 4.1 Prerequisites

#### 4.1.1 Initial AWS Deployment (Required)

**Before starting local development, you must deploy QA Studio to AWS once:**

```bash
# From web-app directory
npm run deploy
```

**Why this is required**:
- Creates the Cognito User Pool needed for authentication
- Generates the `amplifyconfiguration.json` with real Cognito credentials
- Sets up DynamoDB table schema that LWS will replicate locally
- Establishes the CDK infrastructure that LWS will parse

**This is a one-time setup**. After initial deployment, all development can happen locally.

**Reference**: See [web-app/README.md](../web-app/README.md) for complete deployment instructions.

#### 4.1.2 System Requirements

- **Python**: 3.11+ (already required) - [Download](https://www.python.org/downloads/)
- **Node.js**: 18+ (already required) - [Download](https://nodejs.org/)
- **Podman**: Preferred container runtime (already installed) - [Install Guide](https://podman.io/getting-started/installation)
- **uvx**: Python package runner - Install via `pip install uv` - [Documentation](https://github.com/astral-sh/uv)
- **AWS Credentials**: Required for Cognito authentication - [Configure AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html)

**Verify installations**:
```bash
python --version  # Should be 3.11+
node --version    # Should be 18+
podman --version  # Should be installed
aws --version     # Should be configured
```

#### 4.1.3 Lambda Docker Images

LWS uses official AWS Lambda images. One-time setup:

```bash
# Pull Python 3.11 Lambda image
ldk setup lambda
```

This downloads the `public.ecr.aws/lambda/python:3.11` image (~1GB).

**Troubleshooting**: If using Podman, ensure it's configured correctly:
```bash
# Test Podman
podman run hello-world

# If issues, see: https://podman.io/getting-started/
```

**Reference**: [LWS Lambda Setup Documentation](https://local-web-services.github.io/getting-started.html)

### 4.2 Phase 1: Basic Setup (Week 1)

#### Step 1: Install Local Web Services

```bash
# Install LWS globally
pip install local-web-services-python-sdk

# Verify installation
ldk --version
```

**Expected output**: `ldk version X.X.X`

**Troubleshooting**:
- If `ldk` command not found, ensure Python bin directory is in PATH
- Try `python -m ldk --version` as alternative
- See [LWS Installation Guide](https://local-web-services.github.io/getting-started.html#installation)

#### Step 2: Generate CDK Synthesis

```bash
# From web-app directory
npm run cdk synth

# Verify cdk.out/ directory exists
ls -la cdk.out/
```

#### Step 3: First Local Run

```bash
# Start local services
ldk dev

# Expected output:
# ✓ Parsed CDK cloud assembly
# ✓ Starting DynamoDB on :8000
# ✓ Starting S3 on :4566
# ✓ Starting Cognito on :9229
# ✓ Starting API Gateway on :3000
# ✓ Lambda functions ready
# 
# Dashboard: http://localhost:3000/_ldk/gui
```

#### Step 4: Verify Services

```bash
# In another terminal, test DynamoDB
aws dynamodb list-tables --endpoint-url http://localhost:8000

# Test S3
aws s3 ls --endpoint-url http://localhost:4566

# Test API Gateway
curl http://localhost:3000/health
```

### 4.3 Phase 2: Frontend Integration (Week 1-2)

#### Step 1: Create Local API Configuration

The UI requires only one configuration file change for local development:

**Create `frontend/src/api-config.local.json`** (API endpoint only):

```json
{
  "apiUrl": "http://localhost:3000/",
  "region": "eu-central-1"
}
```

**Important Notes**:
- Only the `apiUrl` changes to point to local API Gateway
- Keep the `region` matching your AWS deployment
- **Do NOT create `amplifyconfiguration.local.json`** - use the existing `amplifyconfiguration.json` from your AWS deployment
- This ensures authentication uses real AWS Cognito with proper JWT tokens

#### Step 2: Update Frontend to Use Local API Config

Modify the config loading logic to use local API config in development.

**Find where `api-config.json` is imported** (likely in `frontend/src/main.tsx` or `frontend/src/App.tsx`):

```typescript
// Update wherever api-config.json is imported
const configFile = import.meta.env.DEV 
  ? './api-config.local.json'  // Local development - points to localhost
  : './api-config.json';        // Deployed - points to AWS API Gateway

const config = await import(configFile);
```

**Alternative approach** (if using dynamic import):
```typescript
// If config is loaded dynamically
const loadConfig = async () => {
  const configPath = import.meta.env.DEV 
    ? '/src/api-config.local.json'
    : '/src/api-config.json';
  
  const response = await fetch(configPath);
  return response.json();
};
```

**Note**: `amplifyconfiguration.json` remains unchanged - it's already configured from your AWS deployment.

**Reference**: Check your current config loading in `frontend/src/` to determine which approach to use.

#### Step 3: Add to .gitignore

Ensure local config file is not committed:

```bash
# Add to frontend/.gitignore or root .gitignore
frontend/src/api-config.local.json
```

**Note**: The existing `amplifyconfiguration.json` (from AWS deployment) is already committed and shared across all environments.

#### Step 4: Start Frontend Dev Server

```bash
cd frontend
npm run dev

# Vite starts on http://localhost:5173
# API calls go to http://localhost:3000 (from api-config.local.json)
```

#### Step 5: Test Login Flow

1. Open `http://localhost:5173`
2. Login with your existing AWS Cognito user credentials
3. Verify JWT token validation works with local API Gateway
4. Test API calls with authentication

**Note**: Use the same credentials you use for the deployed QA Studio application. The Cognito User Pool is shared between local and deployed environments.

### 4.4 Phase 3: Lambda Development Workflow (Week 2)

#### Step 1: Configure Hot Reload

LWS automatically watches Lambda directories. Verify:

```bash
# Check ldk dev output for:
# ✓ Watching lambdas/endpoints for changes
# ✓ Watching lambdas/auth for changes
```

#### Step 2: Test Hot Reload

1. Edit a Lambda function (e.g., `lambdas/endpoints/get_usecases.py`)
2. Add a print statement or change response
3. Save file
4. Observe ldk output: `↻ Reloaded get_usecases.handler`
5. Call API endpoint
6. Verify changes reflected immediately

#### Step 3: Local Debugging

Add breakpoints in Lambda code:

```python
# lambdas/endpoints/get_usecases.py
import pdb

def handler(event, context):
    pdb.set_trace()  # Debugger will pause here
    # ... rest of handler
```

Run ldk in foreground to see debugger output.

#### Step 4: Environment Variables

Verify Lambda environment variables are set:

```python
import os
print(f"TABLE_NAME: {os.environ.get('TABLE_NAME')}")
```

LWS automatically injects environment variables from CDK.

### 4.5 Phase 4: DynamoDB and Data (Week 2-3)

#### Step 1: Verify Table Creation

```bash
# List tables
aws dynamodb list-tables --endpoint-url http://localhost:8000

# Describe table
aws dynamodb describe-table \
  --table-name QAStudioTable \
  --endpoint-url http://localhost:8000
```

#### Step 2: Seed Test Data

Create `scripts/seed-local-data.py`:

```python
import boto3

dynamodb = boto3.resource('dynamodb', 
    endpoint_url='http://localhost:8000')
table = dynamodb.Table('QAStudioTable')

# Insert test use cases
table.put_item(Item={
    'PK': 'USECASE#test-1',
    'SK': 'METADATA',
    'name': 'Test Use Case',
    'description': 'Local test data',
    # ... other fields
})
```

Run: `python scripts/seed-local-data.py`

#### Step 3: Test GSI Queries

Verify GSI queries work locally:

```python
# In Lambda or test script
response = table.query(
    IndexName='GSI1',
    KeyConditionExpression='GSI1PK = :pk',
    ExpressionAttributeValues={':pk': 'USER#testuser'}
)
```

#### Step 4: Data Persistence

Local DynamoDB data persists in `.ldk/dynamodb.db`:

```bash
# Reset data
ldk reset

# Or manually delete
rm -rf .ldk/
```

### 4.6 Phase 5: Worker Integration (Week 3-4)

#### Step 1: Worker Environment Configuration

Create `worker/.env.local`:

```bash
# Local services
DYNAMODB_ENDPOINT=http://localhost:8000
S3_ENDPOINT=http://localhost:4566

# Real AWS for Nova Act
AWS_REGION=us-east-1
# No endpoint override for Bedrock - uses real AWS
```

#### Step 2: Update Worker Code

Modify `worker/dynamodb_client.py`:

```python
import os
import boto3

endpoint_url = os.environ.get('DYNAMODB_ENDPOINT')
dynamodb = boto3.resource('dynamodb', endpoint_url=endpoint_url)
```

#### Step 3: Run Worker Locally

```bash
cd worker
python worker.py

# Worker reads from local DynamoDB
# Stores artifacts in local S3
# Calls real AWS Bedrock for Nova Act
```

#### Step 4: Test End-to-End Flow

1. Create test case via frontend (stored in local DynamoDB)
2. Trigger execution via API
3. Worker picks up from local queue
4. Worker executes with real Nova Act
5. Results stored in local DynamoDB/S3
6. View results in frontend

### 4.7 Phase 6: Documentation and Tooling (Week 4)

#### Step 1: Create Developer Guide

Document in `docs/local-development.md`:
- Setup instructions
- Common workflows
- Troubleshooting
- Tips and tricks

#### Step 2: Add npm Scripts

Update `web-app/package.json`:

```json
{
  "scripts": {
    "dev:local": "ldk dev",
    "dev:frontend": "cd frontend && npm run dev",
    "dev:seed": "python scripts/seed-local-data.py",
    "dev:reset": "ldk reset"
  }
}
```

#### Step 3: Create VS Code Tasks

Add `.vscode/tasks.json`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Start Local Services",
      "type": "shell",
      "command": "ldk dev",
      "isBackground": true
    },
    {
      "label": "Start Frontend",
      "type": "shell",
      "command": "cd frontend && npm run dev",
      "isBackground": true
    }
  ]
}
```

#### Step 4: Update README

Add local development section to main README:

```markdown
## Local Development

For rapid development without AWS deployments:

1. Start local services: `npm run dev:local`
2. Start frontend: `npm run dev:frontend`
3. Access app at http://localhost:5173

See [Local Development Guide](docs/local-development.md) for details.
```

### 4.8 Phase 7: Team Rollout (Week 5)

#### Step 1: Team Training

- Schedule 1-hour walkthrough session
- Demo the workflow
- Answer questions
- Pair program with each developer

#### Step 2: Gradual Adoption

- Week 1: Use for frontend development
- Week 2: Use for Lambda development
- Week 3: Use for full-stack features
- Week 4: Primary development mode

#### Step 3: Feedback Collection

- Daily standup check-ins
- Document pain points
- Iterate on tooling
- Update documentation

### 4.9 Timeline Summary

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 1. Basic Setup | Week 1 | LWS running locally |
| 2. Frontend Integration | Week 1-2 | React dev server + local API |
| 3. Lambda Workflow | Week 2 | Hot reload working |
| 4. DynamoDB & Data | Week 2-3 | Local data seeding |
| 5. Worker Integration | Week 3-4 | End-to-end local testing |
| 6. Documentation | Week 4 | Developer guide complete |
| 7. Team Rollout | Week 5 | Full team adoption |

**Total Timeline**: 5 weeks to full adoption

---

## 5. Developer Workflow

### 5.1 Current Workflow (Before LWS)

#### Typical Feature Development

**Scenario**: Add a new API endpoint to list test suites

```
┌─────────────────────────────────────────────────────┐
│ 1. Write Lambda function                            │
│    Time: 15 minutes                                  │
│    File: lambdas/endpoints/list_suites.py           │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 2. Update CDK stack                                  │
│    Time: 5 minutes                                   │
│    File: lib/lambda-stack.ts, lib/api-stack.ts      │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 3. Deploy to AWS                                     │
│    Command: npm run deploy                           │
│    Time: 8-10 minutes ⏰                             │
│    Status: ☕ Context switch, check Slack           │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 4. Test in deployed environment                      │
│    Time: 5 minutes                                   │
│    Action: Use Postman or deployed frontend          │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 5. Find bug in Lambda logic                         │
│    Time: 2 minutes                                   │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 6. Fix Lambda code                                   │
│    Time: 3 minutes                                   │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 7. Deploy again                                      │
│    Time: 8-10 minutes ⏰                             │
│    Status: ☕ More context switching                │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 8. Test again                                        │
│    Time: 5 minutes                                   │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 9. Update frontend to call new endpoint             │
│    Time: 10 minutes                                  │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 10. Deploy frontend                                  │
│     Time: 8-10 minutes ⏰                            │
│     Status: ☕ Lost in Slack threads                │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 11. Test full integration                            │
│     Time: 5 minutes                                  │
└─────────────────────────────────────────────────────┘

Total Time: ~70 minutes
Waiting Time: ~30 minutes (43%)
Context Switches: 3
```

#### Frontend-Only Changes

**Scenario**: Update UI component styling

```
┌─────────────────────────────────────────────────────┐
│ 1. Update React component                           │
│    Time: 10 minutes                                  │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 2. Deploy to see changes                             │
│    Command: npm run deploy                           │
│    Time: 8-10 minutes ⏰                             │
│    Problem: No local dev server with API access      │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 3. Test in deployed environment                      │
│    Time: 2 minutes                                   │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 4. Find CSS issue                                    │
│    Time: 1 minute                                    │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 5. Fix CSS                                           │
│    Time: 2 minutes                                   │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 6. Deploy again                                      │
│    Time: 8-10 minutes ⏰                             │
└─────────────────────────────────────────────────────┘

Total Time: ~33 minutes
Waiting Time: ~20 minutes (61%)
```

### 5.2 New Workflow (With LWS)

#### Same Feature Development

**Scenario**: Add a new API endpoint to list test suites

```
┌─────────────────────────────────────────────────────┐
│ 1. Start local services (one time)                  │
│    Command: npm run dev:local                        │
│    Time: 20 seconds (first start)                    │
│    Status: ✓ All services running                   │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 2. Start frontend (one time)                        │
│    Command: npm run dev:frontend                     │
│    Time: 5 seconds                                   │
│    Status: ✓ Vite dev server on :5173               │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 3. Write Lambda function                            │
│    Time: 15 minutes                                  │
│    File: lambdas/endpoints/list_suites.py           │
│    Status: ✓ Hot reload picks up changes            │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 4. Update CDK stack                                  │
│    Time: 5 minutes                                   │
│    File: lib/lambda-stack.ts, lib/api-stack.ts      │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 5. Re-synth CDK                                      │
│    Command: npm run cdk synth                        │
│    Time: 10 seconds                                  │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 6. Restart ldk (picks up new route)                 │
│    Command: Ctrl+C, npm run dev:local                │
│    Time: 20 seconds                                  │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 7. Test immediately                                  │
│    Time: 2 minutes                                   │
│    Action: Call API from frontend or curl           │
│    Status: ✓ Instant feedback                       │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 8. Find bug in Lambda logic                         │
│    Time: 2 minutes                                   │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 9. Fix Lambda code                                   │
│    Time: 3 minutes                                   │
│    Status: ✓ Hot reload in <5 seconds               │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 10. Test again immediately                           │
│     Time: 2 minutes                                  │
│     Status: ✓ No deployment needed                  │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 11. Update frontend to call new endpoint            │
│     Time: 10 minutes                                 │
│     Status: ✓ Vite HMR updates instantly            │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 12. Test full integration immediately                │
│     Time: 5 minutes                                  │
│     Status: ✓ Frontend + API working together       │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 13. Deploy to AWS (when ready)                       │
│     Time: 8-10 minutes                               │
│     Status: ✓ Confident it works                    │
└─────────────────────────────────────────────────────┘

Total Time: ~45 minutes (vs 70 minutes)
Waiting Time: ~1 minute (vs 30 minutes)
Context Switches: 0 (vs 3)
Time Saved: 25 minutes (36% faster)
```

#### Frontend-Only Changes

**Scenario**: Update UI component styling

```
┌─────────────────────────────────────────────────────┐
│ 1. Update React component                           │
│    Time: 10 minutes                                  │
│    Status: ✓ Vite HMR updates instantly             │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 2. See changes immediately                           │
│    Time: <1 second                                   │
│    Status: ✓ Hot module replacement                 │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 3. Find CSS issue                                    │
│    Time: 1 minute                                    │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 4. Fix CSS                                           │
│    Time: 2 minutes                                   │
│    Status: ✓ See changes instantly                  │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ 5. Deploy to AWS (when ready)                       │
│    Time: 8-10 minutes                                │
└─────────────────────────────────────────────────────┘

Total Time: ~23 minutes (vs 33 minutes)
Waiting Time: 0 (vs 20 minutes)
Time Saved: 10 minutes (30% faster)
```

### 5.3 Daily Development Patterns

#### Morning Startup

```bash
# Terminal 1: Start local AWS services
cd web-app
npm run dev:local

# Terminal 2: Start frontend dev server
npm run dev:frontend

# Terminal 3: Available for commands
# - Run tests
# - Seed data
# - Check logs
```

**Startup Time**: ~30 seconds (vs 0 for current workflow, but saves hours later)

#### Iterative Development

**Lambda Changes**:
1. Edit Python file
2. Save
3. Wait <5 seconds for hot reload
4. Test immediately

**Frontend Changes**:
1. Edit React component
2. Save
3. See changes instantly (Vite HMR)
4. Test with real API

**Infrastructure Changes**:
1. Edit CDK stack
2. Run `npm run cdk synth` (10 seconds)
3. Restart `ldk dev` (20 seconds)
4. Test new infrastructure

#### Testing Workflows

**Unit Tests** (unchanged):
```bash
cd web-app/lambdas
pytest
```

**Integration Tests** (new capability):
```bash
# With local services running
cd web-app
pytest tests/integration/

# Tests can call local API Gateway
# No AWS credentials needed
# Fast execution
```

**Manual Testing**:
- Open `http://localhost:5173`
- Login with test user
- Test features end-to-end
- Check local DynamoDB data
- View local S3 artifacts

### 5.4 Common Tasks

#### Task: Add New Lambda Function

**Before LWS**:
1. Write function (15 min)
2. Update CDK (5 min)
3. Deploy (10 min) ⏰
4. Test (5 min)
5. Fix bugs (5 min)
6. Deploy again (10 min) ⏰
**Total**: 50 minutes

**With LWS**:
1. Write function (15 min)
2. Update CDK (5 min)
3. Synth + restart (30 sec)
4. Test (5 min)
5. Fix bugs (5 min)
6. Hot reload (5 sec)
7. Test again (5 min)
**Total**: 35 minutes (30% faster)

#### Task: Debug DynamoDB Query

**Before LWS**:
1. Add logging (2 min)
2. Deploy (10 min) ⏰
3. Trigger query (2 min)
4. Check CloudWatch logs (3 min)
5. Fix query (3 min)
6. Deploy (10 min) ⏰
7. Test (2 min)
**Total**: 32 minutes

**With LWS**:
1. Add logging (2 min)
2. Hot reload (5 sec)
3. Trigger query (2 min)
4. Check terminal logs (instant)
5. Fix query (3 min)
6. Hot reload (5 sec)
7. Test (2 min)
**Total**: 9 minutes (72% faster)

#### Task: Update Frontend Component

**Before LWS**:
1. Edit component (10 min)
2. Deploy (10 min) ⏰
3. Test (2 min)
4. Fix styling (3 min)
5. Deploy (10 min) ⏰
6. Test (2 min)
**Total**: 37 minutes

**With LWS**:
1. Edit component (10 min)
2. See changes instantly
3. Test (2 min)
4. Fix styling (3 min)
5. See changes instantly
6. Test (2 min)
**Total**: 17 minutes (54% faster)

### 5.5 Documentation Updates

As part of this implementation, the following documentation will be created/updated:

#### New Documentation

**`docs/local-development.md`**:
- Complete setup guide
- Prerequisites and installation
- Starting local services
- Common workflows
- Troubleshooting
- Tips and tricks

**`docs/local-development-troubleshooting.md`**:
- Common errors and solutions
- Port conflicts
- Container issues
- Data reset procedures

#### Updated Documentation

**`README.md`**:
- Add "Local Development" section
- Link to detailed guide
- Quick start commands

**`web-app/README.md`**:
- Update "Getting Started" section
- Add local development option
- Update deployment instructions

**`docs/development.md`**:
- Add local development workflow
- Update testing instructions
- Add debugging tips

### 5.6 Team Adoption Strategy

#### Week 1: Introduction
- Team meeting: Demo local development
- Share documentation
- Pair programming sessions
- Use for frontend work only

#### Week 2: Expansion
- Use for Lambda development
- Share tips and tricks
- Document pain points
- Iterate on tooling

#### Week 3: Primary Mode
- Local development becomes default
- Deploy only for testing in AWS
- Collect feedback
- Update documentation

#### Week 4: Full Adoption
- All development starts locally
- Deploy only for staging/production
- Measure productivity gains
- Celebrate wins 🎉

---

## 6. Limitations & Trade-offs

### 6.1 Services Requiring Real AWS

#### 6.1.1 AI Services (Expected)

**Amazon Bedrock**:
- Cannot be emulated locally
- Nova Act SDK requires real Bedrock endpoints
- All AI-powered test generation and execution hits AWS
- **Impact**: Worker execution still incurs AWS costs
- **Mitigation**: This is acceptable and expected

**Amazon Nova Act**:
- Browser automation requires Bedrock AgentCore
- No local alternative available
- **Impact**: Test execution requires AWS connectivity
- **Mitigation**: Development of orchestration logic can still be done locally

#### 6.1.2 Amazon Cognito (Keep Real AWS)

**Cognito User Pool**:
- Lambda authorizers require real Cognito for token validation
- Local Cognito emulation has limitations with JWT token format
- **Decision**: Keep using real AWS Cognito even in local development
- **Impact**: Requires AWS credentials and internet connectivity
- **Benefit**: Ensures authentication works identically locally and in production
- **Configuration**: `api-config.local.json` points to real Cognito User Pool

#### 6.1.3 CloudFront (Not Needed)

- CloudFront is not emulated locally
- **Impact**: None - frontend served directly by Vite
- Local development doesn't need CDN

### 6.2 Local Web Services Limitations

#### 6.2.1 DynamoDB Differences

**SQLite Backend**:
- Local DynamoDB uses SQLite instead of real DynamoDB
- **Differences**:
  - Performance characteristics differ
  - Some advanced features may behave differently
  - Capacity units and throttling not simulated
- **Impact**: Edge cases might behave differently in production
- **Mitigation**: 
  - Test critical queries in real AWS before deployment
  - Use local for development, AWS for final validation

**GSI Limitations**:
- GSI queries work but projection types may differ slightly
- **Impact**: Minimal for simple queries
- **Mitigation**: Document any observed differences

#### 6.2.2 Lambda Runtime Differences

**Container vs. Real Lambda**:
- Local Lambda runs in Docker containers
- Real Lambda uses Firecracker microVMs
- **Differences**:
  - Cold start behavior differs
  - Memory and CPU allocation differs
  - Network latency differs
- **Impact**: Performance testing not accurate locally
- **Mitigation**: Performance testing must be done in AWS

**Timeout Enforcement**:
- Local timeout enforcement is approximate
- **Impact**: Edge cases near timeout limits may differ
- **Mitigation**: Test timeout-sensitive code in AWS

#### 6.2.3 API Gateway Differences

**Request/Response Handling**:
- Local API Gateway emulates most features
- Some edge cases may differ:
  - Binary payload handling
  - Multi-value headers
  - Request validation
- **Impact**: Most requests work identically
- **Mitigation**: Test edge cases in AWS

**Lambda Authorizers**:
- Local Cognito provides JWT tokens
- Token validation works locally
- **Differences**: Token format may differ slightly
- **Impact**: Minimal for standard use cases
- **Mitigation**: Test auth edge cases in AWS

#### 6.2.4 S3 Differences

**Filesystem Backend**:
- Local S3 uses filesystem instead of object storage
- **Differences**:
  - No eventual consistency simulation
  - No S3 event notifications (unless configured)
  - Presigned URL format differs
- **Impact**: Basic operations work identically
- **Mitigation**: Test S3 events and edge cases in AWS

### 6.3 Development Workflow Trade-offs

#### 6.3.1 Additional Setup Required

**Initial Setup Time**:
- Developers must install LWS and pull Lambda images
- One-time setup: ~15 minutes
- **Impact**: Small upfront cost
- **Benefit**: Saves hours over time

**Learning Curve**:
- Team must learn new workflow
- Documentation and training required
- **Impact**: 1-2 days to become comfortable
- **Benefit**: Faster development long-term

#### 6.3.2 CDK Synth Requirement

**Infrastructure Changes**:
- CDK changes require `cdk synth` + restart
- Takes ~30 seconds vs instant hot reload
- **Impact**: Infrastructure changes slightly slower than Lambda changes
- **Mitigation**: Infrastructure changes are less frequent

**Synth Errors**:
- CDK synth errors must be fixed before local testing
- **Impact**: Same as current workflow
- **Mitigation**: None needed

#### 6.3.3 Data Management

**Local Data Persistence**:
- Local DynamoDB data persists in `.ldk/` directory
- Can become stale or inconsistent
- **Impact**: May need to reset data occasionally
- **Mitigation**: 
  - Document reset procedure
  - Provide seed data scripts
  - Add to `.gitignore`

**Data Seeding**:
- Developers must seed test data locally
- **Impact**: Extra step for new developers
- **Mitigation**: Provide seed scripts and documentation

#### 6.3.4 Resource Consumption

**Local Resources**:
- LWS and Lambda containers consume CPU/memory
- **Requirements**:
  - ~2GB RAM for LWS services
  - ~1GB RAM per Lambda container
  - ~5GB disk for Lambda images
- **Impact**: Requires decent development machine
- **Mitigation**: Most modern laptops can handle this

**Podman/Docker**:
- Requires container runtime
- **Impact**: Already required for current workflow
- **Mitigation**: None needed

### 6.4 Testing Limitations

#### 6.4.1 Integration Testing Scope

**What Can Be Tested Locally**:
- ✅ API Gateway → Lambda → DynamoDB flows
- ✅ Cognito authentication
- ✅ S3 artifact storage
- ✅ Lambda business logic
- ✅ Frontend → API integration

**What Cannot Be Tested Locally**:
- ❌ Nova Act test execution (requires real Bedrock)
- ❌ ECS/Fargate scaling behavior
- ❌ CloudWatch metrics and alarms
- ❌ IAM permission edge cases
- ❌ Cross-region behavior
- ❌ Production performance characteristics

#### 6.4.2 End-to-End Testing

**Hybrid Approach Required**:
- Local testing for development
- AWS testing for final validation
- **Impact**: Still need AWS for complete testing
- **Mitigation**: This is expected and acceptable

### 6.5 Team Collaboration

#### 6.5.1 Shared State

**No Shared Local Environment**:
- Each developer has isolated local stack
- Cannot share data between developers locally
- **Impact**: Testing multi-user scenarios requires AWS
- **Mitigation**: Use AWS for integration testing

**Data Synchronization**:
- No automatic sync between local and AWS
- **Impact**: Developers must manually sync if needed
- **Mitigation**: Document sync procedures

#### 6.5.2 Configuration Drift

**Local vs. AWS Configuration**:
- Local configuration may drift from AWS
- **Impact**: Potential for "works locally but not in AWS"
- **Mitigation**:
  - Regular AWS deployments
  - CI/CD pipeline catches issues
  - Document configuration differences

### 6.6 Operational Considerations

#### 6.6.1 Debugging Differences

**Local Debugging**:
- Can use debuggers and print statements locally
- CloudWatch logs not available locally
- **Impact**: Different debugging experience
- **Mitigation**: Terminal logs provide similar visibility

**Error Messages**:
- Local error messages may differ from AWS
- **Impact**: Some errors only appear in AWS
- **Mitigation**: Test error handling in AWS

#### 6.6.2 Monitoring and Observability

**No CloudWatch Locally**:
- No metrics, logs, or alarms locally
- **Impact**: Cannot test monitoring setup locally
- **Mitigation**: Test monitoring in AWS

**LWS Dashboard**:
- LWS provides web dashboard for local observability
- Shows requests, responses, and logs
- **Impact**: Different from CloudWatch but sufficient for development
- **Benefit**: Real-time visibility during development

### 6.7 Cost Considerations

#### 6.7.1 Development Costs

**Reduced AWS Costs**:
- No development deployments = no Lambda invocations
- No DynamoDB read/write units
- No S3 storage costs for development
- **Benefit**: Significant cost savings

**Remaining AWS Costs**:
- Nova Act/Bedrock calls still hit AWS
- Final testing in AWS still required
- **Impact**: Some AWS costs remain
- **Mitigation**: This is expected and acceptable

#### 6.7.2 Infrastructure Costs

**No Additional Infrastructure**:
- LWS runs on developer laptops
- No additional AWS resources needed
- **Benefit**: Zero infrastructure cost

### 6.8 Risk Assessment

#### 6.8.1 Low Risk

- ✅ LWS is open source and actively maintained
- ✅ Can fall back to current workflow if needed
- ✅ No changes to production infrastructure
- ✅ Gradual adoption possible

#### 6.8.2 Medium Risk

- ⚠️ Local/AWS behavior differences could cause bugs
- ⚠️ Team learning curve could slow initial adoption
- ⚠️ Additional tooling to maintain

**Mitigation**:
- Thorough testing in AWS before production
- Good documentation and training
- Regular AWS deployments to catch issues early

#### 6.8.3 Acceptable Trade-offs

The limitations are acceptable because:
1. **Speed gains outweigh limitations**: 8-10 min → <30 sec
2. **Most development work can be done locally**: 80%+ of changes
3. **AWS testing still available**: For final validation
4. **Gradual adoption**: Can use for some workflows first
5. **Fallback available**: Can always deploy to AWS if needed

---

## 7. Success Metrics

### 7.1 Primary Metrics

#### 7.1.1 Development Cycle Time

**Target**: Reduce deployment wait time by 95%

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Full stack restart | 8-10 minutes | <30 seconds | Time from code change to testable |
| Lambda code change | 8-10 minutes | <5 seconds | Hot reload time |
| Frontend change | 8-10 minutes | <1 second | Vite HMR time |
| Infrastructure change | 8-10 minutes | <30 seconds | CDK synth + restart |

**Measurement Method**:
- Track time from save to testable for 10 typical changes
- Average the results
- Compare before/after

#### 7.1.2 Developer Productivity

**Target**: Recover 3+ hours per developer per day

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Deployments per day | ~10 | ~1-2 | Track deployment frequency |
| Wait time per day | ~100 minutes | <10 minutes | Sum of all wait times |
| Context switches per day | ~10 | ~1-2 | Count of focus interruptions |
| Features completed per week | Baseline | +30% | Track feature velocity |

**Measurement Method**:
- Survey developers weekly
- Track deployment logs
- Measure feature completion rate

#### 7.1.3 Developer Satisfaction

**Target**: Improve developer experience significantly

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Satisfaction score | Baseline | +2 points | 1-5 scale survey |
| "Would recommend" | Baseline | 100% | Yes/No survey |
| Frustration level | High | Low | Qualitative feedback |

**Measurement Method**:
- Weekly developer survey
- Monthly retrospective
- Collect qualitative feedback

### 7.2 Secondary Metrics

#### 7.2.1 Code Quality

**Target**: Improve code quality through faster feedback

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Bugs found in development | Baseline | +50% | Track bug discovery timing |
| Bugs found in production | Baseline | -30% | Track production incidents |
| Test coverage | Baseline | +20% | Code coverage reports |

**Hypothesis**: Faster feedback loops lead to:
- More experimentation
- Earlier bug detection
- Better test coverage

#### 7.2.2 Onboarding Time

**Target**: Reduce new developer onboarding time

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Time to first contribution | ~2 days | ~4 hours | Track from setup to first PR |
| Setup complexity | High | Low | Qualitative feedback |
| Documentation clarity | Baseline | Excellent | Survey new developers |

**Measurement Method**:
- Track onboarding time for next new hire
- Survey new developers after 1 week

#### 7.2.3 AWS Costs

**Target**: Reduce development AWS costs

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Development deployments | ~20/day | ~2-4/day | CloudFormation stack updates |
| Lambda invocations | High | -80% | CloudWatch metrics |
| DynamoDB read/write units | High | -80% | CloudWatch metrics |

**Note**: Nova Act/Bedrock costs will remain unchanged (expected)

### 7.3 Adoption Metrics

#### 7.3.1 Usage Tracking

**Target**: 100% team adoption within 5 weeks

| Week | Target Adoption | Measurement |
|------|----------------|-------------|
| Week 1 | 50% (frontend only) | Survey + observation |
| Week 2 | 75% (frontend + Lambda) | Survey + observation |
| Week 3 | 90% (full stack) | Survey + observation |
| Week 4 | 100% (primary mode) | Survey + observation |
| Week 5 | 100% (default mode) | Survey + observation |

**Measurement Method**:
- Daily standup check-ins
- Track deployment frequency
- Developer self-reporting

#### 7.3.2 Workflow Patterns

**Target**: Establish efficient local-first workflow

| Pattern | Target | Measurement |
|---------|--------|-------------|
| Local development first | 100% of changes | Developer survey |
| AWS deployment for validation | Final step only | Deployment logs |
| Local integration testing | Standard practice | Test execution logs |

### 7.4 Technical Metrics

#### 7.4.1 System Performance

**Target**: Ensure local environment is performant

| Metric | Target | Measurement |
|--------|--------|-------------|
| LWS startup time | <30 seconds | Time from `ldk dev` to ready |
| Lambda hot reload time | <5 seconds | Time from save to ready |
| API response time | <100ms | Local API latency |
| Memory usage | <4GB total | System monitor |

**Measurement Method**:
- Automated timing scripts
- System resource monitoring
- Developer feedback

#### 7.4.2 Reliability

**Target**: Local environment is stable and reliable

| Metric | Target | Measurement |
|--------|--------|-------------|
| LWS crashes per day | <1 | Error logs |
| Data corruption incidents | 0 | Developer reports |
| Port conflicts | <1 per week | Developer reports |

**Measurement Method**:
- Error logging
- Developer incident reports
- Weekly retrospectives

### 7.5 Validation Criteria

#### 7.5.1 Phase 1 Success (Week 1)

**Criteria**:
- ✅ LWS successfully running on both developer machines
- ✅ Frontend dev server connecting to local API
- ✅ Basic API calls working (GET /usecases)
- ✅ Cognito authentication working locally
- ✅ No major blockers identified

**Validation Method**:
- Hands-on testing by both developers
- Checklist completion
- Team meeting review

#### 7.5.2 Phase 2 Success (Week 2)

**Criteria**:
- ✅ Lambda hot reload working reliably
- ✅ DynamoDB queries working (including GSI)
- ✅ S3 operations working
- ✅ At least 5 successful feature developments using local workflow
- ✅ Developer satisfaction positive

**Validation Method**:
- Feature completion tracking
- Developer survey
- Technical validation

#### 7.5.3 Phase 3 Success (Week 3-4)

**Criteria**:
- ✅ Worker integration working
- ✅ End-to-end flows testable locally
- ✅ Documentation complete
- ✅ Both developers using local workflow as primary mode
- ✅ Measurable productivity improvement

**Validation Method**:
- End-to-end testing
- Documentation review
- Productivity metrics comparison

#### 7.5.4 Full Success (Week 5)

**Criteria**:
- ✅ 100% team adoption
- ✅ Development cycle time reduced by 90%+
- ✅ Developer satisfaction significantly improved
- ✅ No critical issues or blockers
- ✅ Workflow documented and repeatable

**Validation Method**:
- All metrics reviewed
- Team retrospective
- Success celebration 🎉

### 7.6 Measurement Schedule

#### Weekly Check-ins

**Every Monday**:
- Review adoption progress
- Collect developer feedback
- Identify blockers
- Update metrics dashboard

**Every Friday**:
- Review week's productivity
- Measure cycle times
- Document learnings
- Plan next week

#### Monthly Review

**End of Month 1**:
- Comprehensive metrics review
- ROI calculation
- Team retrospective
- Adjust approach if needed

### 7.7 Success Dashboard

Create a simple dashboard to track progress:

```markdown
## Local Development Adoption Dashboard

### Week 1 Progress
- [ ] LWS installed on all machines
- [ ] Frontend integration complete
- [ ] First successful local development session
- [ ] Developer satisfaction: ⭐⭐⭐⭐⭐

### Key Metrics
- Average deployment time: 8 min → 25 sec ✅
- Deployments per day: 10 → 2 ✅
- Developer happiness: 😊😊

### Blockers
- None

### Next Steps
- Lambda hot reload testing
- DynamoDB integration
```

### 7.8 ROI Calculation

#### Time Savings

**Per Developer**:
- Current: 100 minutes/day waiting
- Target: <10 minutes/day waiting
- **Savings**: 90 minutes/day per developer

**Team Total**:
- 2 developers × 90 minutes/day = 180 minutes/day
- 180 minutes/day × 5 days/week = 900 minutes/week
- **15 hours per week saved**

#### Cost Savings

**Developer Time**:
- 15 hours/week × $100/hour (estimated) = $1,500/week
- $1,500/week × 52 weeks = **$78,000/year**

**AWS Costs**:
- Estimated 80% reduction in development AWS costs
- Current: ~$500/month (estimated)
- Savings: ~$400/month = **$4,800/year**

**Total Annual Savings**: ~$82,800

**Implementation Cost**:
- 5 weeks × 2 developers × 20% time = 2 developer-weeks
- ~$8,000 investment

**ROI**: 10x return in first year

### 7.9 Continuous Improvement

#### Feedback Loop

**Weekly**:
- Collect developer feedback
- Identify pain points
- Make small improvements
- Update documentation

**Monthly**:
- Review all metrics
- Identify trends
- Plan larger improvements
- Share learnings

#### Iteration Plan

**Month 2**:
- Optimize hot reload performance
- Add more seed data scripts
- Improve documentation
- Add troubleshooting guides

**Month 3**:
- Integrate with CI/CD pipeline
- Add automated integration tests
- Create video tutorials
- Share with broader team

**Month 6**:
- Review long-term impact
- Document best practices
- Consider expanding to other projects
- Publish case study

---

## 8. Rollout Plan

### 8.1 Pre-Rollout Preparation

#### 8.1.1 Technical Preparation (Week 0)

**Infrastructure Setup**:
- [ ] Install LWS on development machines
- [ ] Pull Lambda Docker images
- [ ] Verify Podman configuration
- [ ] Test basic LWS functionality

**Documentation Preparation**:
- [ ] Create `docs/local-development.md`
- [ ] Create `docs/local-development-troubleshooting.md`
- [ ] Update main README
- [ ] Create quick reference guide

**Testing**:
- [ ] Test LWS with current CDK setup
- [ ] Verify all services start correctly
- [ ] Test basic API calls
- [ ] Identify any blockers

#### 8.1.2 Team Preparation

**Communication**:
- [ ] Schedule kickoff meeting
- [ ] Share design document
- [ ] Explain benefits and timeline
- [ ] Address concerns and questions

**Training Materials**:
- [ ] Create setup walkthrough video
- [ ] Prepare demo scenarios
- [ ] Create troubleshooting FAQ
- [ ] Prepare pair programming schedule

### 8.2 Phase 1: Pilot (Week 1)

#### 8.2.1 Goals

- Get LWS running on both developer machines
- Validate basic functionality
- Identify and resolve blockers
- Build confidence in the approach

#### 8.2.2 Activities

**Monday**:
- [ ] Kickoff meeting (1 hour)
  - Demo local development workflow
  - Walk through setup steps
  - Answer questions
- [ ] Both developers install LWS
- [ ] Verify installation success

**Tuesday-Wednesday**:
- [ ] Developer 1: Set up frontend integration
- [ ] Developer 2: Set up Lambda hot reload
- [ ] Daily sync: Share progress and blockers
- [ ] Document any issues encountered

**Thursday-Friday**:
- [ ] Both developers: Try local workflow for real tasks
- [ ] Use for frontend development only (low risk)
- [ ] Collect feedback
- [ ] End-of-week retrospective

#### 8.2.3 Success Criteria

- ✅ LWS running on both machines
- ✅ Frontend dev server working with local API
- ✅ At least 2 successful feature developments
- ✅ No critical blockers
- ✅ Positive developer feedback

#### 8.2.4 Risk Mitigation

**If issues arise**:
- Fall back to current workflow immediately
- Document the issue
- Investigate and resolve
- Retry when ready

### 8.3 Phase 2: Expansion (Week 2)

#### 8.3.1 Goals

- Expand usage to Lambda development
- Test DynamoDB integration
- Establish hot reload workflow
- Build muscle memory

#### 8.3.2 Activities

**Monday**:
- [ ] Week 1 retrospective
- [ ] Address any issues from Week 1
- [ ] Plan Week 2 focus areas

**Tuesday-Thursday**:
- [ ] Use local workflow for Lambda changes
- [ ] Test DynamoDB queries and GSI
- [ ] Practice hot reload workflow
- [ ] Seed local test data
- [ ] Daily sync: Share learnings

**Friday**:
- [ ] Week 2 retrospective
- [ ] Update documentation based on learnings
- [ ] Measure productivity improvements
- [ ] Plan Week 3

#### 8.3.3 Success Criteria

- ✅ Lambda hot reload working reliably
- ✅ DynamoDB operations working
- ✅ At least 5 features developed locally
- ✅ Measurable time savings
- ✅ Continued positive feedback

### 8.4 Phase 3: Full Stack (Week 3)

#### 8.4.1 Goals

- Use local workflow for all development
- Integrate worker testing
- Establish best practices
- Deploy to AWS only for validation

#### 8.4.2 Activities

**Monday**:
- [ ] Week 2 retrospective
- [ ] Set goal: All development starts locally

**Tuesday-Thursday**:
- [ ] Develop full-stack features locally
- [ ] Test worker integration
- [ ] Practice end-to-end workflows
- [ ] Deploy to AWS only for final validation

**Friday**:
- [ ] Week 3 retrospective
- [ ] Document best practices
- [ ] Measure productivity gains
- [ ] Celebrate wins

#### 8.4.3 Success Criteria

- ✅ All development starts locally
- ✅ Worker integration working
- ✅ End-to-end testing possible locally
- ✅ Significant productivity improvement measured
- ✅ Team confident in workflow

### 8.5 Phase 4: Optimization (Week 4)

#### 8.5.1 Goals

- Optimize workflow based on learnings
- Complete documentation
- Establish standard practices
- Prepare for long-term use

#### 8.5.2 Activities

**Monday**:
- [ ] Review all feedback from Weeks 1-3
- [ ] Identify optimization opportunities

**Tuesday-Wednesday**:
- [ ] Implement workflow improvements
- [ ] Create seed data scripts
- [ ] Add npm scripts for common tasks
- [ ] Update documentation

**Thursday-Friday**:
- [ ] Final documentation review
- [ ] Create troubleshooting guide
- [ ] Record demo videos
- [ ] Week 4 retrospective

#### 8.5.3 Success Criteria

- ✅ Documentation complete and accurate
- ✅ Workflow optimized and efficient
- ✅ Common tasks scripted
- ✅ Team fully comfortable with workflow

### 8.6 Phase 5: Adoption (Week 5)

#### 8.6.1 Goals

- Make local development the default
- Measure final success metrics
- Document lessons learned
- Plan future improvements

#### 8.6.2 Activities

**Monday**:
- [ ] Declare local development as primary mode
- [ ] Update team practices

**Tuesday-Thursday**:
- [ ] Use local workflow exclusively
- [ ] Deploy to AWS only for staging/production
- [ ] Collect final metrics

**Friday**:
- [ ] Final retrospective
- [ ] Calculate ROI
- [ ] Celebrate success 🎉
- [ ] Plan continuous improvement

#### 8.6.3 Success Criteria

- ✅ 100% team adoption
- ✅ All success metrics met
- ✅ Workflow documented and repeatable
- ✅ Team satisfaction high
- ✅ Measurable productivity improvement

### 8.7 Communication Plan

#### 8.7.1 Weekly Updates

**Format**: Slack message every Friday

**Template**:
```
📊 Local Development Update - Week X

✅ Wins:
- [Achievement 1]
- [Achievement 2]

📈 Metrics:
- Deployment time: X min → Y sec
- Features completed: X
- Developer happiness: ⭐⭐⭐⭐⭐

🚧 Challenges:
- [Challenge 1 and how we addressed it]

🎯 Next Week:
- [Goal 1]
- [Goal 2]
```

#### 8.7.2 Stakeholder Updates

**Audience**: Engineering leadership, product team

**Frequency**: Bi-weekly

**Content**:
- Progress summary
- Productivity metrics
- ROI calculation
- Next steps

### 8.8 Risk Management

#### 8.8.1 Identified Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| LWS doesn't work with our stack | Low | High | Tested in pre-rollout |
| Team resistance to change | Low | Medium | Clear communication, gradual adoption |
| Local/AWS behavior differences | Medium | Medium | Test in AWS before production |
| Performance issues on laptops | Low | Medium | Monitor resource usage |
| Documentation gaps | Medium | Low | Continuous documentation updates |

#### 8.8.2 Contingency Plans

**If LWS doesn't work**:
- Fall back to current workflow
- Investigate alternatives (LocalStack, SAM Local)
- Continue with current process

**If adoption is slow**:
- Extend timeline
- Provide more training
- Address specific concerns
- Make it optional initially

**If productivity doesn't improve**:
- Analyze why
- Adjust workflow
- Consider hybrid approach
- Document learnings

### 8.9 Success Celebration

#### 8.9.1 Week 5 Celebration

**Activities**:
- Team lunch or dinner
- Share success metrics
- Thank team for effort
- Discuss future improvements

**Recognition**:
- Acknowledge individual contributions
- Share learnings with broader team
- Document case study
- Consider blog post or presentation

### 8.10 Post-Rollout

#### 8.10.1 Continuous Improvement (Month 2+)

**Monthly Reviews**:
- Review metrics
- Collect feedback
- Identify improvements
- Update documentation

**Quarterly Goals**:
- Optimize performance
- Add new capabilities
- Expand to CI/CD
- Share with other teams

#### 8.10.2 Long-Term Maintenance

**Responsibilities**:
- Keep LWS updated
- Maintain documentation
- Support new team members
- Share best practices

**Knowledge Sharing**:
- Document lessons learned
- Create training materials
- Present at team meetings
- Mentor other teams

### 8.11 Rollout Checklist

#### Pre-Rollout
- [ ] LWS installed and tested
- [ ] Documentation created
- [ ] Team trained
- [ ] Kickoff meeting scheduled

#### Week 1
- [ ] LWS running on all machines
- [ ] Frontend integration working
- [ ] First features developed locally
- [ ] Week 1 retrospective completed

#### Week 2
- [ ] Lambda hot reload working
- [ ] DynamoDB integration working
- [ ] Multiple features developed locally
- [ ] Week 2 retrospective completed

#### Week 3
- [ ] Full-stack development locally
- [ ] Worker integration tested
- [ ] End-to-end flows working
- [ ] Week 3 retrospective completed

#### Week 4
- [ ] Workflow optimized
- [ ] Documentation complete
- [ ] Scripts and tools created
- [ ] Week 4 retrospective completed

#### Week 5
- [ ] 100% team adoption
- [ ] Success metrics measured
- [ ] Final retrospective completed
- [ ] Success celebrated 🎉

### 8.12 Timeline Visualization

```
Week 0: Preparation
├── Install LWS
├── Create documentation
└── Test basic functionality

Week 1: Pilot
├── Kickoff meeting
├── Setup on all machines
├── Frontend integration
└── First local development

Week 2: Expansion
├── Lambda hot reload
├── DynamoDB integration
├── Multiple features
└── Measure improvements

Week 3: Full Stack
├── All development local
├── Worker integration
├── End-to-end testing
└── Best practices

Week 4: Optimization
├── Workflow improvements
├── Complete documentation
├── Create scripts
└── Final polish

Week 5: Adoption
├── Primary development mode
├── Measure success
├── Final retrospective
└── Celebrate! 🎉

Month 2+: Continuous Improvement
├── Monthly reviews
├── Ongoing optimization
├── CI/CD integration
└── Knowledge sharing
```

---

## Appendix A: Quick Reference

### Common Commands

```bash
# Start local services
npm run dev:local

# Start frontend
npm run dev:frontend

# Seed test data
npm run dev:seed

# Reset local data
npm run dev:reset

# Re-synth CDK
npm run cdk synth

# Deploy to AWS (when ready)
npm run deploy
```

### Useful URLs

- **Local API**: http://localhost:3000
- **Frontend**: http://localhost:5173
- **LWS Dashboard**: http://localhost:3000/_ldk/gui
- **DynamoDB Local**: http://localhost:8000
- **S3 Local**: http://localhost:4566
- **Deployed QA Studio**: Check CloudFormation outputs for your CloudFront URL

### Useful AWS CLI Commands

```bash
# List local DynamoDB tables
aws dynamodb list-tables --endpoint-url http://localhost:8000

# Query local DynamoDB
aws dynamodb scan --table-name QAStudioTable --endpoint-url http://localhost:8000

# List local S3 buckets
aws s3 ls --endpoint-url http://localhost:4566

# Upload to local S3
aws s3 cp file.txt s3://bucket-name/ --endpoint-url http://localhost:4566
```

### Troubleshooting

**Port already in use**:
```bash
# Find and kill process on port 3000
lsof -ti:3000 | xargs kill -9

# Or find what's using the port
lsof -i :3000
```

**Lambda not reloading**:
```bash
# Restart ldk
Ctrl+C
npm run dev:local

# Or check ldk logs for errors
```

**Data issues**:
```bash
# Reset all local data
npm run dev:reset
npm run dev:seed

# Or manually
rm -rf .ldk/
ldk dev
```

**Cognito authentication fails**:
- Verify you've deployed to AWS at least once
- Check `frontend/src/amplifyconfiguration.json` exists
- Ensure AWS credentials are configured: `aws sts get-caller-identity`
- Check you're using correct user credentials from deployed environment

**Frontend can't reach API**:
- Verify `api-config.local.json` exists in `frontend/src/`
- Check LWS is running: `curl http://localhost:3000/health`
- Verify CORS is enabled in LWS (should be automatic)

**For more help**:
- Check `docs/local-development-troubleshooting.md` (to be created)
- LWS Documentation: https://local-web-services.github.io
- LWS GitHub Issues: https://github.com/local-web-services/local-web-services/issues

---

## Appendix B: Resources

### Documentation
- **Local Web Services**: https://local-web-services.github.io
- **LWS GitHub**: https://github.com/local-web-services/local-web-services
- **LWS Getting Started**: https://local-web-services.github.io/getting-started.html
- **LWS Services Documentation**: https://local-web-services.github.io/services.html
- **CDK Documentation**: https://docs.aws.amazon.com/cdk/
- **AWS CLI Configuration**: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html
- **Podman Installation**: https://podman.io/getting-started/installation

### Internal Documentation
- `docs/local-development.md`: Complete setup guide (to be created in Phase 6)
- `docs/local-development-troubleshooting.md`: Common issues (to be created in Phase 6)
- `README.md`: Quick start (to be updated in Phase 6)
- `web-app/README.md`: Deployment guide (existing)

### Project Files
- `web-app/frontend/src/api-config.json`: Deployed API configuration
- `web-app/frontend/src/amplifyconfiguration.json`: Cognito configuration (from deployment)
- `web-app/cdk.out/`: CDK synthesis output (generated by `cdk synth`)
- `.ldk/`: Local Web Services data directory (created automatically)

### Support
- **Team Slack channel**: #qa-studio-dev (or your team channel)
- **LWS GitHub Issues**: https://github.com/local-web-services/local-web-services/issues
- **This Design Doc**: `.kiro/design/local-development-environment-design.md`
