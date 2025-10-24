import { Duration, RemovalPolicy, Fn } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Table } from 'aws-cdk-lib/aws-dynamodb';
import { SqsEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import { Queue } from 'aws-cdk-lib/aws-sqs';
import { Function } from 'aws-cdk-lib/aws-lambda';
import { Effect, ManagedPolicy, PolicyStatement } from 'aws-cdk-lib/aws-iam';
import { Topic } from 'aws-cdk-lib/aws-sns';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';

interface NovaActQAStudioNotificationStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  table: Table
  tableReadPolicy: ManagedPolicy
  tableFullAccessPolicy: ManagedPolicy
  distributionDomain: string
}

export class NovaActQAStudioNotificationStack extends NovaActQAStudioBaseStack {
  public readonly notificationQueue: Queue
  public readonly subscribeUsecaseLambda: Function
  public readonly unsubscribeUsecaseLambda: Function
  public readonly getUsecaseSubscriptionLambda: Function

  constructor(scope: Construct, id: string, props: NovaActQAStudioNotificationStackCreateProps) {
    super(scope, id, props);

    this.notificationQueue = new Queue(this, 'notification_queue', {
      queueName: this.cdkName('notifications'),
      visibilityTimeout: Duration.minutes(5),
      removalPolicy: RemovalPolicy.DESTROY
    });

    const notificationTopic = new Topic(this, 'notification_topic', {
      topicName: this.cdkName('notifications'),
      displayName: 'Usecase Execution Notifications'
    });

    const sendNotificationLambda = this.createLambda({
      path: 'send_notification',
      environment: {
        TABLE_NAME: props.table.tableName,
        NOTIFICATION_QUEUE_URL: this.notificationQueue.queueUrl,
        SNS_TOPIC_ARN: notificationTopic.topicArn,
        FRONTEND_URL: props.distributionDomain
      }
    });

    this.getUsecaseSubscriptionLambda = this.createLambda({
      path: 'get_usecase_subscription',
      environment: {
        TABLE_NAME: props.table.tableName,
      }
    });

    // Usecase Subscription Lambdas
    this.subscribeUsecaseLambda = this.createLambda({
      path: 'subscribe_usecase',
      environment: {
        TABLE_NAME: props.table.tableName,
        SNS_TOPIC_ARN: notificationTopic.topicArn
      }
    });

    this.unsubscribeUsecaseLambda = this.createLambda({
      path: 'unsubscribe_usecase',
      environment: {
        TABLE_NAME: props.table.tableName,
        SNS_TOPIC_ARN: notificationTopic.topicArn
      }
    });

    this.subscribeUsecaseLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.unsubscribeUsecaseLambda.role?.addManagedPolicy(props.tableFullAccessPolicy)
    sendNotificationLambda.role?.addManagedPolicy(props.tableReadPolicy)

    this.notificationQueue.grantConsumeMessages(sendNotificationLambda);
    notificationTopic.grantPublish(sendNotificationLambda);

    sendNotificationLambda.addEventSource(new SqsEventSource(this.notificationQueue, {
      batchSize: 1
    }));

    // Grant SNS permissions to subscribe Lambda for auto-subscribing users and managing filter policies
    notificationTopic.grantSubscribe(this.subscribeUsecaseLambda);
    this.subscribeUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'sns:ListSubscriptionsByTopic',
        'sns:GetSubscriptionAttributes',
        'sns:SetSubscriptionAttributes'
      ],
      resources: [
        notificationTopic.topicArn,
        `${notificationTopic.topicArn}:*`
      ]
    }));

    // Grant SNS permissions to unsubscribe Lambda for managing filter policies and unsubscribing users
    this.unsubscribeUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'sns:ListSubscriptionsByTopic',
        'sns:GetSubscriptionAttributes',
        'sns:SetSubscriptionAttributes',
        'sns:Unsubscribe'
      ],
      resources: [
        notificationTopic.topicArn,
        `${notificationTopic.topicArn}:*`
      ]
    }));

    this.log('notificationQueue', this.notificationQueue.queueName)
    this.log('notificationTopic', notificationTopic.topicName)
  }
}