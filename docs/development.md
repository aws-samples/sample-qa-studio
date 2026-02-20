# Development

This guide covers the commands and workflows for developing, deploying, and monitoring QA Studio. Make sure you've completed the [Getting Started](../README.md#getting-started) setup before diving in.

## Deploying Individual Components

If you need to update specific parts of the solution:

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

## Commands Reference

### Main Deployment

- `npm run deploy`: Complete deployment (builds Lambdas + frontend, then deploys)
- `npm run deploy:release`: Deploy from release archive (skips builds, uses pre-built artifacts)

### Individual Stack Deployment

- `npm run deploy:storage`: Deploy storage stack (DynamoDB, S3, ECR)
- `npm run deploy:auth`: Deploy authentication stack (Cognito)
- `npm run deploy:api`: Deploy API Gateway stack
- `npm run deploy:frontend`: Deploy frontend infrastructure (CloudFront, S3)
- `npm run deploy:notification`: Deploy notification stack (SNS, SQS)
- `npm run deploy:worker`: Deploy worker stack (ECS Fargate)
- `npm run deploy:routes`: Deploy API routes and Lambda integrations
- `npm run deploy:frontend-deployment`: Deploy frontend assets to S3

### Utility Commands

- `npm run build:lambdas`: Build all Lambda functions for ARM64
- `npm run clean:lambdas`: Remove Lambda build artifacts
- `npm run config:write`: Generate frontend config from CloudFormation outputs
- `npm run dcv:download`: Download NICE DCV Web Client SDK (runs automatically during deployment)
- `npm run deploy:frontend-build`: Build React frontend application
- `npm run build`: Compile TypeScript CDK code
- `npm run watch`: Watch TypeScript files for changes

### CDK Commands

- `npx cdk diff`: Compare deployed stack with current state
- `npx cdk synth`: Generate CloudFormation templates
- `npx cdk destroy --all`: Delete all stacks (⚠️ deletes all data)

### Release Commands

- `npm run release:patch`: Create patch release (1.0.0 → 1.0.1)
- `npm run release:minor`: Create minor release (1.0.0 → 1.1.0)
- `npm run release:major`: Create major release (1.0.0 → 2.0.0)
- `npm run release:prerelease`: Create pre-release (1.0.0 → 1.0.1-beta.0)
- `npm run changelog`: Generate changelog from git commits
