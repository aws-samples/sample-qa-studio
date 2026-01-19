import { Names, RemovalPolicy } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Table, AttributeType } from 'aws-cdk-lib/aws-dynamodb';
import { BackupPlan, BackupVault, BackupPlanRule, BackupResource } from 'aws-cdk-lib/aws-backup';
import { Secret } from 'aws-cdk-lib/aws-secretsmanager';
import { ManagedPolicy, PolicyStatement, Effect } from 'aws-cdk-lib/aws-iam';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';

interface NovaActQAStudioStorageStackCreateProps extends NovaActQAStudioBaseStackCreateProps { }

/**
 * Key Components:
 * - DynamoDB Table: Main data storage with partition and sort keys
 * - Secrets Manager: Stores Nova Act API key
 * - Backup: Daily backups of DynamoDB table
 *
 * Readable Attributes:
 * - table.tableName: Name of the DynamoDB table
 * - novaActApiKeySecret.secretName: Name of API key secret
 *
 * Required Props:
 * - baseName: Base name for resource naming
 */
export class NovaActQAStudioStorageStack extends NovaActQAStudioBaseStack {
  public readonly table: Table
  public readonly novaActApiKeySecret: Secret
  public readonly tableReadPolicy: ManagedPolicy
  public readonly tableWritePolicy: ManagedPolicy
  public readonly tableFullAccessPolicy: ManagedPolicy

  constructor(scope: Construct, id: string, props: NovaActQAStudioStorageStackCreateProps) {
    super(scope, id, props);

    this.novaActApiKeySecret = new Secret(this, 'nova_api_key', {
      secretName: this.cdkName('nova_api_key'),
    })

    this.table = new Table(this, 'table', {
      tableName: this.cdkName('data'),
      partitionKey: {
        name: 'pk',
        type: AttributeType.STRING
      },
      sortKey: {
        name: 'sk',
        type: AttributeType.STRING
      },
      removalPolicy: RemovalPolicy.DESTROY,
    });

    const backupVault = new BackupVault(this, "dynamodb_backup_vault_5")
    const plan = new BackupPlan(this, "dynamodb_backup_plan_5")
    plan.addRule(BackupPlanRule.daily(backupVault))
    plan.addSelection("data", {
      resources: [BackupResource.fromDynamoDbTable(this.table)]
    })

    // Create managed policies for DynamoDB table access
    this.tableReadPolicy = new ManagedPolicy(this, 'TableReadPolicy', {
      managedPolicyName: this.cdkName('table-read-policy'),
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            'dynamodb:GetItem',
            'dynamodb:Query',
            'dynamodb:Scan',
            'dynamodb:BatchGetItem',
            'dynamodb:DescribeTable'
          ],
          resources: [
            this.table.tableArn,
            `${this.table.tableArn}/index/*`
          ]
        })
      ]
    });

    this.tableWritePolicy = new ManagedPolicy(this, 'TableWritePolicy', {
      managedPolicyName: this.cdkName('table-write-policy'),
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            'dynamodb:PutItem',
            'dynamodb:UpdateItem',
            'dynamodb:BatchWriteItem'
          ],
          resources: [
            this.table.tableArn,
            `${this.table.tableArn}/index/*`
          ]
        })
      ]
    });

    this.tableFullAccessPolicy = new ManagedPolicy(this, 'TableFullAccessPolicy', {
      managedPolicyName: this.cdkName('table-full-access-policy'),
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            'dynamodb:GetItem',
            'dynamodb:Query',
            'dynamodb:Scan',
            'dynamodb:BatchGetItem',
            'dynamodb:PutItem',
            'dynamodb:UpdateItem',
            'dynamodb:DeleteItem',
            'dynamodb:BatchWriteItem',
            'dynamodb:DescribeTable'
          ],
          resources: [
            this.table.tableArn,
            `${this.table.tableArn}/index/*`
          ]
        })
      ]
    });

    this.log('dynamodbTable', this.table.tableName)
    this.log('NovaActApiKeySecret', this.novaActApiKeySecret.secretName)
  }
}