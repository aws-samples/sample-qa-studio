# Quick Start Deployment

## Prerequisites

- AWS CLI configured with credentials
- Node.js and npm installed
- CDK CLI installed: `npm install -g aws-cdk`
- Configuration set in `configuration.json`

## Deploy Everything

```bash
# Make script executable (first time only)
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

That's it! The script handles:
- ✅ Correct deployment order
- ✅ Configuration file generation
- ✅ Frontend build
- ✅ Circular dependency avoidance

## What Gets Deployed

1. **Storage Stack** - DynamoDB, S3 buckets, ECR registry
2. **Auth Stack** - Cognito User Pool
3. **API Stack** - API Gateway
4. **Frontend Stack** - CloudFront + S3 website
5. **Notification Stack** - SNS, SQS for notifications
6. **Worker Stack** - ECS Fargate tasks
7. **Routes Stack** - API routes and Lambda integrations

## Configuration Files

After deployment, these files are auto-generated:
- `frontend/src/amplifyconfiguration.json` - Cognito config
- `frontend/src/api-config.json` - API endpoint config

## Troubleshooting

### First deployment fails?

Make sure:
- AWS credentials are configured: `aws configure`
- You have permissions to create CloudFormation stacks
- `configuration.json` has valid values

### Need to regenerate config files?

```bash
npx ts-node scripts/write-config.ts <baseName>
```

### Want more control?

See [DEPLOYMENT.md](./DEPLOYMENT.md) for manual deployment steps.

## Clean Up

To delete all resources:

```bash
cdk destroy --all
```

⚠️ This will delete all data!
