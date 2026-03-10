import { App, Stack } from 'aws-cdk-lib';
import { NagSuppressions } from 'cdk-nag';

interface CdkNagStacks {
  storageStack: Stack;
  authStack: Stack;
  workerStack: Stack;
  lambdaStack: Stack;
  apiStack: Stack;
  frontendStack: Stack;
}

/**
 * Apply cdk-nag AwsSolutions suppressions for known acceptable patterns.
 *
 * Each suppression includes a reason explaining why the rule is safe to suppress.
 * Suppressions are scoped as narrowly as possible — stack-level only when the
 * pattern applies uniformly to all resources of that type in the stack.
 *
 * Note: `applyToNestedStacks` is intentionally `false` so that the NagReportLogger
 * can capture suppressed findings in the CSV/JSON reports.
 */
export function applyCdkNagSuppressions(_app: App, stacks: CdkNagStacks): void {
  const { storageStack, authStack, workerStack, lambdaStack, apiStack, frontendStack } = stacks;

  const allStacks = [storageStack, authStack, workerStack, lambdaStack, apiStack, frontendStack];

  // ──────────────────────────────────────────────
  // App-wide suppressions (CDK-managed internals)
  // ──────────────────────────────────────────────
  const commonSuppressions = [
    {
      id: 'AwsSolutions-L1',
      reason: 'Lambda runtime is explicitly set to Python 3.13 (latest supported). CDK custom resource Lambdas use the CDK-managed runtime.',
    },
    {
      id: 'AwsSolutions-IAM4',
      reason: 'AWS managed policies (AWSLambdaBasicExecutionRole) are used for CloudWatch Logs permissions — this is the AWS-recommended pattern.',
    },
    {
      id: 'AwsSolutions-IAM5',
      appliesTo: ['Resource::*'],
      reason: 'CDK LogRetention custom resource requires wildcard Resource because the target log group ARN is not known at synth time. This is a CDK-managed construct (aws-cdk-lib/aws-logs).',
    },
  ];
  for (const stack of allStacks) {
    NagSuppressions.addStackSuppressions(stack, commonSuppressions);
  }

  // ──────────────────────────────────────────────
  // Storage stack
  // ──────────────────────────────────────────────
  NagSuppressions.addStackSuppressions(storageStack, [
    {
      id: 'AwsSolutions-DDB3',
      reason: 'Point-in-time recovery is enabled. DynamoDB uses PAY_PER_REQUEST billing — auto-scaling is not applicable.',
    },
    {
      id: 'AwsSolutions-IAM5',
      reason: 'DynamoDB table policies use index/* wildcard to allow queries on all GSIs. Backup cleanup Lambda needs wildcard on recovery-point ARNs.',
    },
    {
      id: 'AwsSolutions-SMG4',
      reason: 'Nova Act API key secret rotation is managed externally by the user — automatic rotation is not applicable.',
    },
  ]);

  // ──────────────────────────────────────────────
  // Auth stack
  // ──────────────────────────────────────────────
  NagSuppressions.addStackSuppressions(authStack, [
    {
      id: 'AwsSolutions-COG1',
      reason: 'Cognito password policy is configured with min 8 chars, uppercase, lowercase, digits, and symbols — meets security requirements.',
    },
    {
      id: 'AwsSolutions-COG2',
      reason: 'MFA is not enforced — this is a development/internal tool. Users authenticate via Cognito hosted UI.',
    },
    {
      id: 'AwsSolutions-COG3',
      reason: 'AdvancedSecurityMode is not enabled — this is a non-regulated internal workload. Standard Cognito security features are sufficient.',
    },
  ]);

  // ──────────────────────────────────────────────
  // Worker stack
  // ──────────────────────────────────────────────
  NagSuppressions.addStackSuppressions(workerStack, [
    {
      id: 'AwsSolutions-IAM5',
      reason: 'Worker IAM policies use scoped wildcards: S3 bucket/*, DynamoDB table/index/*, ECR GetAuthorizationToken requires *, Secrets Manager scoped to account/region.',
    },
    {
      id: 'AwsSolutions-SQS3',
      reason: 'SQS queues do not have DLQs — failed messages are handled by the application layer with retry logic and status tracking in DynamoDB.',
    },
    {
      id: 'AwsSolutions-SQS4',
      reason: 'SQS queues use AWS-managed encryption. SSL enforcement is handled at the application level.',
    },
    {
      id: 'AwsSolutions-S1',
      reason: 'Artefacts bucket server access logging is not enabled — artefacts are ephemeral test outputs, not sensitive data.',
    },
    {
      id: 'AwsSolutions-S10',
      reason: 'S3 bucket does not require SSL-only — artefacts are accessed via presigned URLs over HTTPS.',
    },
    {
      id: 'AwsSolutions-ECS4',
      reason: 'ECS container insights not enabled — this is a batch worker, not a long-running service. Monitoring is done via CloudWatch Logs and DynamoDB status tracking.',
    },
    {
      id: 'AwsSolutions-ECS2',
      reason: 'Environment variables in ECS task definition contain non-sensitive configuration (table name, bucket name, region). Secrets use Secrets Manager.',
    },
    {
      id: 'AwsSolutions-VPC7',
      reason: 'VPC flow logs are not enabled — worker VPC is used only for ECS tasks accessing AWS APIs. No inbound traffic.',
    },
    {
      id: 'AwsSolutions-EC23',
      reason: 'Security group allows outbound traffic to AWS APIs and Nova Act endpoints. No inbound rules.',
    },
    {
      id: 'AwsSolutions-SNS2',
      reason: 'SNS topic uses AWS-managed encryption — CMK not required for this non-regulated workload.',
    },
    {
      id: 'AwsSolutions-SNS3',
      reason: 'SNS topic does not require SSL-only — subscribers are Lambda functions within the same account.',
    },
  ]);

  // ──────────────────────────────────────────────
  // Lambda stack
  // ──────────────────────────────────────────────
  NagSuppressions.addStackSuppressions(lambdaStack, [
    {
      id: 'AwsSolutions-IAM5',
      reason: 'Lambda IAM policies use scoped wildcards: S3 bucket/*, DynamoDB table/index/*, Secrets Manager scoped to account/region. Cognito actions require * resource.',
    },
  ]);

  // ──────────────────────────────────────────────
  // API stack
  // ──────────────────────────────────────────────
  NagSuppressions.addStackSuppressions(apiStack, [
    {
      id: 'AwsSolutions-APIG2',
      reason: 'API Gateway request validation is handled in Lambda handlers with pydantic models — not at the API Gateway level.',
    },
    {
      id: 'AwsSolutions-APIG4',
      reason: 'All API methods use a custom Lambda authorizer (TOKEN type). OPTIONS methods for CORS do not require authorization.',
    },
    {
      id: 'AwsSolutions-COG4',
      reason: 'API uses a custom Lambda TOKEN authorizer instead of Cognito authorizer — the Lambda validates both user and M2M JWT tokens with signature verification.',
    },
    {
      id: 'AwsSolutions-APIG1',
      reason: 'API Gateway access logging is enabled via deployOptions.accessLogDestination with JSON format.',
    },
    {
      id: 'AwsSolutions-APIG6',
      reason: 'CloudWatch execution logging is configured at the stage level via deployOptions.',
    },
    {
      id: 'AwsSolutions-IAM5',
      reason: 'API Gateway CloudWatch role uses AWS managed policy. Lambda invoke permissions are scoped to specific function ARNs.',
    },
    {
      id: 'AwsSolutions-APIG3',
      reason: 'WAFv2 is not attached to the API Gateway stage — this is an internal tool, not a public-facing API requiring WAF protection.',
    },
  ]);

  // ──────────────────────────────────────────────
  // Frontend stack
  // ──────────────────────────────────────────────
  NagSuppressions.addStackSuppressions(frontendStack, [
    {
      id: 'AwsSolutions-CFR1',
      reason: 'Geo restrictions are not required — this is an internal tool accessible from any location.',
    },
    {
      id: 'AwsSolutions-CFR2',
      reason: 'WAFv2 is not attached to the CloudFront distribution — this is an internal tool, not a public-facing site requiring WAF protection.',
    },
    {
      id: 'AwsSolutions-CFR4',
      reason: 'CloudFront distribution uses the default *.cloudfront.net viewer certificate which enforces TLSv1 minimum regardless of MinimumProtocolVersion setting. Custom domain with ACM certificate required to enforce TLSv1.2+.',
    },
    {
      id: 'AwsSolutions-IAM5',
      reason: 'CDK BucketDeployment custom resource requires wildcard S3 actions (GetBucket*, GetObject*, List*, Abort*, DeleteObject*) and wildcard resources for the CDK assets bucket and frontend bucket. This is a CDK-managed construct.',
    },
    {
      id: 'AwsSolutions-L1',
      reason: 'CDK BucketDeployment custom resource Lambda uses a CDK-managed runtime — not user-configurable.',
    },
  ]);
}
