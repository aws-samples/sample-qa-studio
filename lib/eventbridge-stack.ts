import { Construct } from 'constructs';
import { Table } from 'aws-cdk-lib/aws-dynamodb';
import { IEventBus, EventBus, Rule } from 'aws-cdk-lib/aws-events';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { Function } from 'aws-cdk-lib/aws-lambda';
import { ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';

interface NovaActQAStudioEventBridgeStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  table: Table
  tableWritePolicy: ManagedPolicy
}

export class NovaActQAStudioEventBridgeStack extends NovaActQAStudioBaseStack {
  public readonly eventBus: IEventBus
  public readonly updateUsecaseLastExecutionLambda: Function

  constructor(scope: Construct, id: string, props: NovaActQAStudioEventBridgeStackCreateProps) {
    super(scope, id, props);

    // Use default event bus (can be changed to custom bus if needed)
    this.eventBus = EventBus.fromEventBusName(this, 'default_event_bus', 'default');

    // Lambda to update usecase with latest execution info
    this.updateUsecaseLastExecutionLambda = this.createLambda({
      path: 'update_usecase_last_execution',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    // Grant write permissions to update usecase records
    this.updateUsecaseLastExecutionLambda.role?.addManagedPolicy(props.tableWritePolicy);

    // EventBridge rule to trigger Lambda on execution status changes
    const executionStatusRule = new Rule(this, 'execution_status_changed_rule', {
      ruleName: this.cdkName('execution-status-changed'),
      description: 'Triggers when execution status changes',
      eventBus: this.eventBus,
      eventPattern: {
        source: ['nova-act-qa-studio.execution'],
        detailType: ['nova-act-qa-studio.execution.status.changed']
      }
    });

    executionStatusRule.addTarget(new LambdaFunction(this.updateUsecaseLastExecutionLambda));

    this.log('eventBus', this.eventBus.eventBusName);
    this.log('executionStatusRule', executionStatusRule.ruleName);
  }
}
