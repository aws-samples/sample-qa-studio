import { IAspect, CfnResource } from 'aws-cdk-lib';
import { IConstruct } from 'constructs';

/**
 * CDK Aspect that adds cfn_nag suppressions to CDK-managed resources
 * that we cannot directly control (LogRetention, CustomResource handlers, etc.)
 */
export class CfnNagSuppressions implements IAspect {
  visit(node: IConstruct): void {
    if (node instanceof CfnResource) {
      // Suppress W89/W58/W92 on all Lambda functions (CDK custom resources)
      if (node.cfnResourceType === 'AWS::Lambda::Function') {
        this.addSuppressions(node, [
          { id: 'W89', reason: 'CDK-managed Lambda — VPC not required for AWS API access' },
          { id: 'W58', reason: 'CDK-managed Lambda — permissions handled by CDK' },
          { id: 'W92', reason: 'CDK-managed Lambda — reserved concurrency not needed for custom resources' },
        ]);
      }

      // Suppress W12 on IAM policies from LogRetention and CDK custom resources
      if (node.cfnResourceType === 'AWS::IAM::Policy') {
        const logicalId = node.logicalId;
        if (
          logicalId.includes('LogRetention') ||
          logicalId.includes('CustomResource') ||
          logicalId.includes('CustomS3AutoDelete') ||
          logicalId.includes('CustomCDKBucketDeployment') ||
          logicalId.includes('CDKECRDeployment') ||
          logicalId.includes('FrontendDeployment')
        ) {
          this.addSuppressions(node, [
            { id: 'W12', reason: 'CDK-managed custom resource policy — wildcard resource required by CDK internals' },
          ]);
        }
      }

      // Suppress W28 on resources with explicit names (intentional for cross-stack references)
      const w28Types = [
        'AWS::DynamoDB::Table',
        'AWS::IAM::Role',
        'AWS::IAM::ManagedPolicy',
      ];
      if (w28Types.includes(node.cfnResourceType)) {
        this.addSuppressions(node, [
          { id: 'W28', reason: 'Explicit name is intentional — used for cross-stack references and operational predictability' },
        ]);
      }

      // Suppress KMS-related warnings — AWS-managed encryption is sufficient for this workload
      const kmsReason = 'AWS-managed encryption is sufficient — CMK not required for this non-regulated workload';

      if (node.cfnResourceType === 'AWS::DynamoDB::Table') {
        this.addSuppressions(node, [{ id: 'W74', reason: kmsReason }]);
      }
      if (node.cfnResourceType === 'AWS::SecretsManager::Secret') {
        this.addSuppressions(node, [{ id: 'W77', reason: kmsReason }]);
      }
      if (node.cfnResourceType === 'AWS::Logs::LogGroup') {
        this.addSuppressions(node, [{ id: 'W84', reason: kmsReason }]);
      }
      if (node.cfnResourceType === 'AWS::SNS::Topic') {
        this.addSuppressions(node, [{ id: 'W47', reason: kmsReason }]);
      }
      if (node.cfnResourceType === 'AWS::SQS::Queue') {
        this.addSuppressions(node, [{ id: 'W48', reason: kmsReason }]);
      }
    }
  }

  private addSuppressions(node: CfnResource, rules: { id: string; reason: string }[]) {
    const existing = node.getMetadata('cfn_nag') as any;
    const existingRules = existing?.rules_to_suppress || [];
    const existingIds = new Set(existingRules.map((r: any) => r.id));
    const newRules = rules.filter(r => !existingIds.has(r.id));

    if (newRules.length > 0) {
      node.addMetadata('cfn_nag', {
        rules_to_suppress: [...existingRules, ...newRules],
      });
    }
  }
}
