import { Duration, RemovalPolicy, Aws } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Table } from 'aws-cdk-lib/aws-dynamodb';
import { Bucket, HttpMethods } from 'aws-cdk-lib/aws-s3';
import { PolicyStatement, Policy, Effect, Role, ServicePrincipal } from 'aws-cdk-lib/aws-iam';
import { Queue } from 'aws-cdk-lib/aws-sqs';
import { CfnScheduleGroup } from 'aws-cdk-lib/aws-scheduler';
import { Repository } from 'aws-cdk-lib/aws-ecr';
import { OperatingSystemFamily, FargateTaskDefinition, Cluster, CpuArchitecture, ContainerImage, LogDrivers } from 'aws-cdk-lib/aws-ecs';
import { Vpc, IVpc, GatewayVpcEndpointAwsService, InterfaceVpcEndpointAwsService, SecurityGroup, ISecurityGroup } from 'aws-cdk-lib/aws-ec2';
import { Secret } from 'aws-cdk-lib/aws-secretsmanager';
import { Function } from 'aws-cdk-lib/aws-lambda';
import { SqsEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import { Platform, DockerImageAsset } from 'aws-cdk-lib/aws-ecr-assets';
import { ECRDeployment, DockerImageName } from 'cdk-ecr-deployment';
import { RetentionDays } from 'aws-cdk-lib/aws-logs';
import { ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { Rule, EventBus } from 'aws-cdk-lib/aws-events';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { Topic } from 'aws-cdk-lib/aws-sns';
import { AwsCustomResource, AwsCustomResourcePolicy, PhysicalResourceId } from 'aws-cdk-lib/custom-resources';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';
import { loadConfig } from './config';

const config = loadConfig();
const { defaultRegion, enabledRegions, vpcId, workerSecurityGroupId, createVpcEndpoints, agentCoreVPC } = config;

interface NovaActQAStudioWorkerStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  baseName: string
  table: Table
  novaActApiKeySecret: Secret
  tableReadPolicy: ManagedPolicy
  version: string
}

/**
 * NovaActQAStudioWorkerStack - Manages worker infrastructure for NovaAct QA Studio
 * 
 * Key Components:
 * - SQS Queue for work processing
 * - VPC with public/private subnets and VPC endpoints
 * - ECS Fargate cluster and task definition
 * - EventBridge Scheduler group for scheduling tasks
 * - ECR deployment pipeline
 * 
 * Readable Attributes:
 * - workerSecurityGroup: Security group for ECS tasks
 * - taskDefinition: Fargate task definition for worker containers  
 * - schedulerGroup: EventBridge scheduler group for managing schedules
 * 
 * Required Props:
 * - baseName: Base name for resource naming
 * - registry: ECR repository for worker container images
 * - table: DynamoDB table for data storage
 * - this.artefactsBucket: S3 bucket for artifacts
 * - novaActApiKeySecret: Secrets Manager secret for Nova Act API key
 * - notificationQueue: SQS queue for notifications
 */
export class NovaActQAStudioWorkerStack extends NovaActQAStudioBaseStack {
  public readonly workerSecurityGroup: ISecurityGroup
  public readonly artefactsBucket: Bucket
  public readonly taskDefinition: FargateTaskDefinition
  public readonly schedulerGroup: CfnScheduleGroup
  public readonly executionQueue: Queue
  public readonly cluster: Cluster
  public readonly vpc: IVpc
  public readonly subnetId: string
  public readonly wizardQueue: Queue
  public readonly wizardEventBus: EventBus
  public readonly agentCoreExecutionRole: Role
  public readonly schedulerRole: Role
  public readonly createScheduleLambda: Function
  public readonly executeUsecaseLambda: Function
  public readonly stopExecutionLambda: Function
  public readonly startWizardLambda: Function
  public readonly addWizardStepLambda: Function
  public readonly restartWizardLambda: Function
  public readonly terminateWizardLambda: Function
  public readonly notificationTopicArn: string
  private readonly regionalBucketArns: string[] = []

  constructor(scope: Construct, id: string, props: NovaActQAStudioWorkerStackCreateProps) {
    super(scope, id, props);

    const registry = new Repository(this, 'images_repository', {
      removalPolicy: RemovalPolicy.DESTROY,
      emptyOnDelete: true
    });
    this.artefactsBucket = new Bucket(this, 'artefacts', {
      bucketName: `${this.account}-${this.baseName}-artefacts-${this.region}`,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: true, // Required for cross-region replication
      cors: [
        {
          allowedMethods: [
            HttpMethods.GET,
            HttpMethods.HEAD
          ],
          allowedOrigins: ['*'],
          allowedHeaders: ['*'],
          exposedHeaders: [
            'ETag',
            'Content-Type',
            'Content-Length',
            'Content-Disposition'
          ],
          maxAge: 3000
        }
      ]
    });

    // Create cross-region buckets for enabled regions and collect all bucket ARNs
    this.regionalBucketArns = [
      this.artefactsBucket.bucketArn,
      ...enabledRegions
        .filter((region: string) => region !== defaultRegion)
        .map((region: string) => this.createCrossRegionBucket(region)),
    ];

    // Notification infrastructure
    const notificationQueue = new Queue(this, 'notification_queue', {
      queueName: this.cdkName('notifications'),
      visibilityTimeout: Duration.minutes(5),
      removalPolicy: RemovalPolicy.DESTROY
    });

    const notificationTopic = new Topic(this, 'notification_topic', {
      topicName: this.cdkName('notifications'),
      displayName: 'Usecase Execution Notifications'
    });
    
    // Export the topic ARN for use in lambda stack
    this.notificationTopicArn = notificationTopic.topicArn;

    const sendNotificationLambda = this.createPythonLambda({
      path: 'send_notification',
      environment: {
        TABLE_NAME: props.table.tableName,
        NOTIFICATION_QUEUE_URL: notificationQueue.queueUrl,
        SNS_TOPIC_ARN: notificationTopic.topicArn,
        FRONTEND_URL: '' // Will be set later after frontend stack is created
      }
    });

    sendNotificationLambda.role?.addManagedPolicy(props.tableReadPolicy);
    notificationQueue.grantConsumeMessages(sendNotificationLambda);
    notificationTopic.grantPublish(sendNotificationLambda);

    sendNotificationLambda.addEventSource(new SqsEventSource(notificationQueue, {
      batchSize: 1
    }));

    this.log('notificationQueue', notificationQueue.queueName)
    this.log('notificationTopic', notificationTopic.topicName)

    // EventBridge rule for execution status changes
    const eventBus = EventBus.fromEventBusName(this, 'default_event_bus', 'default');

    const updateUsecaseLastExecutionLambda = this.createPythonLambda({
      path: 'update_usecase_last_execution',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    // Grant both read and write permissions to update use case records
    updateUsecaseLastExecutionLambda.role?.addManagedPolicy(props.tableReadPolicy);
    updateUsecaseLastExecutionLambda.role?.addManagedPolicy(props.tableWritePolicy);

    const executionStatusRule = new Rule(this, 'execution_status_changed_rule', {
      ruleName: this.cdkName('execution-status-changed'),
      description: 'Triggers when execution status changes',
      eventBus: eventBus,
      eventPattern: {
        source: ['nova-act-qa-studio.execution'],
        detailType: ['nova-act-qa-studio.execution.status.changed']
      }
    });

    executionStatusRule.addTarget(new LambdaFunction(updateUsecaseLastExecutionLambda));

    this.log('executionStatusRule', executionStatusRule.ruleName);

    // TODO: Remove this as the local queue feature is not needed anymore
    this.executionQueue = new Queue(this, 'queue', {
      queueName: this.cdkName('workhorse'),
      visibilityTimeout: Duration.minutes(10),
      removalPolicy: RemovalPolicy.DESTROY
    });

    // Wizard mode queue (deprecated - will be replaced by EventBridge)
    this.wizardQueue = new Queue(this, 'wizard_queue', {
      queueName: this.cdkName('wizard-commands'),
      visibilityTimeout: Duration.seconds(30),
      removalPolicy: RemovalPolicy.DESTROY
    });

    // EventBridge Event Bus for wizard commands
    this.wizardEventBus = new EventBus(this, 'wizard_event_bus', {
      eventBusName: this.cdkName('wizard-events')
    });

    // VPC Configuration: Use existing VPC or create new one
    let shouldCreateVpcEndpoints: boolean;

    if (vpcId) {
      // Use existing VPC - automatically discovers subnets
      this.vpc = Vpc.fromLookup(this, 'existing-vpc', {
        vpcId: vpcId
      });

      // Validate that the VPC has private subnets with NAT Gateway routes for internet access
      if (this.vpc.privateSubnets.length === 0) {
        throw new Error(`Existing VPC ${vpcId} must have at least one private subnet with NAT Gateway for ECS tasks and AgentCore browsers`);
      }

      // Only create VPC endpoints if explicitly requested for existing VPC
      shouldCreateVpcEndpoints = createVpcEndpoints ?? false;
    } else {
      // Create new VPC with default configuration
      this.vpc = new Vpc(this, 'vpc', {
        vpcName: this.cdkName('vpc'),
        maxAzs: 2,
        natGateways: 2,
      });

      // Always create VPC endpoints for new VPC
      shouldCreateVpcEndpoints = true;
    }

    // Create VPC endpoints if needed
    if (shouldCreateVpcEndpoints) {
      this.vpc.addGatewayEndpoint('S3Endpoint', {
        service: GatewayVpcEndpointAwsService.S3
      });

      this.vpc.addInterfaceEndpoint('EcrDockerEndpoint', {
        service: InterfaceVpcEndpointAwsService.ECR_DOCKER
      });

      this.vpc.addInterfaceEndpoint('EcrEndpoint', {
        service: InterfaceVpcEndpointAwsService.ECR
      });

      this.vpc.addInterfaceEndpoint('CloudWatchLogsEndpoint', {
        service: InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS
      });

      this.vpc.addGatewayEndpoint('DynamoDbEndpoint', {
        service: GatewayVpcEndpointAwsService.DYNAMODB
      });
    }

    // Store subnet ID for Lambda access
    this.subnetId = this.vpc.privateSubnets[0].subnetId;

    // Security Group for ECS tasks: Use existing or create new
    if (workerSecurityGroupId) {
      // Import existing security group
      this.workerSecurityGroup = SecurityGroup.fromSecurityGroupId(
        this,
        'ImportedSecurityGroup',
        workerSecurityGroupId
      );
    } else {
      // Create new security group in the VPC (works for both new and existing VPC)
      this.workerSecurityGroup = new SecurityGroup(this, 'EcsTaskSecurityGroup', {
        vpc: this.vpc,
        description: 'Security group for ECS tasks',
        allowAllOutbound: true
      });
    }

    // ECS Cluster
    this.cluster = new Cluster(this, 'cluster', {
      vpc: this.vpc,
      clusterName: this.cdkName('cluster'),
    });

    // ECS Task Definition
    this.taskDefinition = new FargateTaskDefinition(this, 'task_definition', {
      memoryLimitMiB: 1024,
      cpu: 512,
      runtimePlatform: {
        operatingSystemFamily: OperatingSystemFamily.LINUX,
        cpuArchitecture: CpuArchitecture.ARM64
      },
      taskRole: new Role(this, 'TaskRole', {
        roleName: this.cdkName('task-role'),
        assumedBy: new ServicePrincipal('ecs-tasks.amazonaws.com'),
      }),
      executionRole: new Role(this, 'ExecutionRole', {
        roleName: this.cdkName('execution-role'),
        assumedBy: new ServicePrincipal('ecs-tasks.amazonaws.com'),
        managedPolicies: [
          ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy')
        ]
      }),
    });

    // Prepare base environment variables
    const baseEnvironment = {
      DYNAMO_TABLE: props.table.tableName,
      QUEUE_URL: this.executionQueue.queueUrl,
      S3_BUCKET: this.artefactsBucket.bucketName,
      NOVA_ACT_API_KEY_NAME: props.novaActApiKeySecret.secretName,
      NOTIFICATION_QUEUE_URL: notificationQueue.queueUrl,
      AWS_REGION: Aws.REGION,
      // Nova Act GA Service configuration
      USE_NOVA_ACT_GA: config.useNovaActGa.toString(),
      NOVA_ACT_REGION: 'us-east-1',
      NOVA_ACT_S3_BUCKET: `${this.account}-${this.baseName}-artefacts-us-east-1`,
    };

    // Add VPC environment variables if agentCoreVPC is enabled
    const containerEnvironment = agentCoreVPC ? {
      ...baseEnvironment,
      // VPC configuration for AgentCore browsers
      AGENT_CORE_VPC: 'true',
      AC_VPC_ID: this.vpc.vpcId,
      AC_SUBNET_ID: this.vpc.privateSubnets[0].subnetId,
      AC_SECURITY_GROUP_ID: this.workerSecurityGroup.securityGroupId,
    } : baseEnvironment;

    // Add container to task definition
    this.taskDefinition.addContainer('container', {
      image: ContainerImage.fromEcrRepository(registry, props.version),
      logging: LogDrivers.awsLogs({
        streamPrefix: this.cdkName('logs'),
        logRetention: RetentionDays.FIVE_DAYS,
      }),
      environment: containerEnvironment
    });

    // Grant permissions to task roles (must be after container is added)
    // TODO: Remove queue
    this.executionQueue.grantConsumeMessages(this.taskDefinition.taskRole);
    this.wizardQueue.grantConsumeMessages(this.taskDefinition.taskRole);
    props.table.grantFullAccess(this.taskDefinition.taskRole);
    this.artefactsBucket.grantReadWrite(this.taskDefinition.taskRole);
    notificationQueue.grantSendMessages(this.taskDefinition.taskRole);

    // Grant EventBridge PutEvents permission for execution status events
    this.taskDefinition.taskRole!.attachInlinePolicy(new Policy(this, 'task_role_eventbridge_policy', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['events:PutEvents'],
          resources: [`arn:aws:events:${Aws.REGION}:${Aws.ACCOUNT_ID}:event-bus/default`]
        })
      ]
    }));

    registry.grantPull(this.taskDefinition.executionRole!);
    registry.grantPull(this.taskDefinition.taskRole!);

    // Nova Act GA Service permissions (only if enabled)
    if (config.useNovaActGa) {
      this.taskDefinition.taskRole!.attachInlinePolicy(new Policy(this, 'nova_act_ga_policy', {
        statements: [
          // Nova Act workflow permissions
          new PolicyStatement({
            effect: Effect.ALLOW,
            actions: [
              'nova-act:CreateWorkflowDefinition',
              'nova-act:GetWorkflowDefinition',
              'nova-act:ListWorkflowDefinitions',
              'nova-act:DeleteWorkflowDefinition',
              'nova-act:CreateWorkflowRun',
              'nova-act:GetWorkflowRun',
              'nova-act:ListWorkflowRuns',
              'nova-act:UpdateWorkflowRun',
              'nova-act:CreateSession',
              'nova-act:GetSession',
              'nova-act:ListSessions',
              'nova-act:CreateAct',
              'nova-act:GetAct',
              'nova-act:ListActs',
              'nova-act:InvokeActStep',
              'nova-act:UpdateAct',
            ],
            resources: [`arn:aws:nova-act:us-east-1:${Aws.ACCOUNT_ID}:*`],
            conditions: {
              StringEquals: {
                'aws:RequestedRegion': 'us-east-1'
              }
            }
          }),
          // Service-linked role creation permission
          new PolicyStatement({
            effect: Effect.ALLOW,
            actions: ['iam:CreateServiceLinkedRole'],
            resources: [
              'arn:aws:iam::*:role/aws-service-role/nova-act.amazonaws.com/AWSServiceRoleForNovaAct'
            ],
            conditions: {
              StringLike: {
                'iam:AWSServiceName': 'nova-act.amazonaws.com'
              }
            }
          }),
          // S3 permissions for us-east-1 bucket
          new PolicyStatement({
            effect: Effect.ALLOW,
            actions: [
              's3:GetObject',
              's3:PutObject',
              's3:ListBucket',
              's3:DeleteObject'
            ],
            resources: [
              `arn:aws:s3:::${this.account}-${this.baseName}-artefacts-us-east-1`,
              `arn:aws:s3:::${this.account}-${this.baseName}-artefacts-us-east-1/*`
            ]
          })
        ]
      }));
    }

    // Add Secrets Manager permissions to execution role
    this.taskDefinition.executionRole!.attachInlinePolicy(new Policy(this, 'ecr_access_policy', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            'secretsmanager:GetSecretValue',
          ],
          resources: [
            `arn:aws:secretsmanager:${Aws.REGION}:${Aws.ACCOUNT_ID}:secret:*`,
          ]
        }),
      ]
    }));

    this.taskDefinition.executionRole!.attachInlinePolicy(new Policy(this, 'secrets_manager_policy', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            'secretsmanager:GetSecretValue',
            'secretsmanager:ListSecrets',
          ],
          resources: [`arn:aws:secretsmanager:${Aws.REGION}:${Aws.ACCOUNT_ID}:secret:*`]
        })
      ]
    }));

    this.taskDefinition.taskRole!.attachInlinePolicy(new Policy(this, 'task_role_secrets_manager_policy', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            'secretsmanager:GetSecretValue',
            'secretsmanager:ListSecrets',
          ],
          resources: [`arn:aws:secretsmanager:${Aws.REGION}:${Aws.ACCOUNT_ID}:secret:*`]
        })
      ]
    }));

    this.taskDefinition.taskRole!.attachInlinePolicy(new Policy(this, 'task_role_bedrock_agentscore', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            "bedrock-agentcore:CreateBrowser",
            "bedrock-agentcore:ListBrowsers",
            "bedrock-agentcore:GetBrowser",
            "bedrock-agentcore:DeleteBrowser",
            "bedrock-agentcore:StartBrowserSession",
            "bedrock-agentcore:ListBrowserSessions",
            "bedrock-agentcore:GetBrowserSession",
            "bedrock-agentcore:StopBrowserSession",
            "bedrock-agentcore:UpdateBrowserStream",
            "bedrock-agentcore:ConnectBrowserAutomationStream",
            "bedrock-agentcore:ConnectBrowserLiveViewStream",
          ],
          resources: [
            `arn:aws:bedrock-agentcore:${Aws.REGION}:${Aws.ACCOUNT_ID}:browser/*`,
            `arn:aws:bedrock-agentcore:${Aws.REGION}:${Aws.ACCOUNT_ID}:browser-custom/*`,
            `arn:aws:bedrock-agentcore:${Aws.REGION}:${Aws.ACCOUNT_ID}:browser-session/*`
          ]
        })
      ]
    }));

    this.schedulerGroup = new CfnScheduleGroup(this, 'schedule_group', {
      name: this.cdkName('schedules')
    });

    const workerImage = new DockerImageAsset(this, 'MyDockerImage', {
      directory: 'worker',
      platform: Platform.LINUX_ARM64
    });

    // Deploy with version tag only
    new ECRDeployment(this, 'container_deployment', {
      src: new DockerImageName(workerImage.imageUri),
      dest: new DockerImageName(`${Aws.ACCOUNT_ID}.dkr.ecr.${Aws.REGION}.amazonaws.com/${registry.repositoryName}:${props.version}`),
    });

    this.agentCoreExecutionRole = new Role(this, 'agent_core_execution_role', {
      roleName: this.cdkName('agent_core_execution_role'),
      assumedBy: new ServicePrincipal('bedrock-agentcore.amazonaws.com'),
    })

    // Grant S3 permissions for all regional buckets
    const s3Resources: string[] = [];
    this.regionalBucketArns.forEach(bucketArn => {
      s3Resources.push(bucketArn);
      s3Resources.push(`${bucketArn}/*`);
    });

    this.agentCoreExecutionRole.attachInlinePolicy(new Policy(this, 'agent_core_execution_role_s3', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            "s3:PutObject",
            "s3:ListMultipartUploadParts",
            "s3:AbortMultipartUpload"
          ],
          resources: s3Resources
        })
      ]
    }))

    // Allow task role to pass the AgentCore execution role to the browser service
    this.taskDefinition.taskRole!.attachInlinePolicy(new Policy(this, 'task_role_pass_agentcore_role', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['iam:PassRole'],
          resources: [this.agentCoreExecutionRole.roleArn]
        })
      ]
    }));

    this.schedulerRole = new Role(this, 'event_bridge_scheduler_role', {
      roleName: this.cdkName('scheduler-role'),
      assumedBy: new ServicePrincipal('scheduler.amazonaws.com'),
    });

    // Get the log group name and stream prefix from the task definition container
    const containerDefinition = this.taskDefinition.defaultContainer;
    const logGroupName = containerDefinition?.logDriverConfig?.options?.['awslogs-group'] || `/ecs/${this.cdkName('logs')}`;
    const logStreamPrefix = containerDefinition?.logDriverConfig?.options?.['awslogs-stream-prefix'] || this.cdkName('logs');

    this.executeUsecaseLambda = this.createPythonLambda({
      path: 'execute_usecase',
      environment: {
        QUEUE_URL: this.executionQueue.queueUrl,
        ECS_CLUSTER: this.cluster.clusterArn,
        ECS_TASK_DEFINITION: this.taskDefinition.taskDefinitionArn,
        SUBNET_ID: this.vpc.privateSubnets[0].subnetId,
        SECURITY_GROUP_ID: this.workerSecurityGroup.securityGroupId,
        TABLE_NAME: props.table.tableName,
        S3_BUCKET: this.artefactsBucket.bucketName,
        S3_BUCKET_PREFIX: `${this.account}-${this.baseName}-artefacts`,
        DEFAULT_REGION: defaultRegion,
        BEDROCK_EXECUTION_ROLE: this.agentCoreExecutionRole.roleArn,
        NOVA_ACT_API_KEY_NAME: props.novaActApiKeySecret.secretName,
        SECRETS_PREFIX: props.baseName,
        LOG_GROUP_NAME: logGroupName,
        LOG_STREAM_PREFIX: logStreamPrefix
      }
    });

    props.table.grantFullAccess(this.executeUsecaseLambda)

    // Grant scheduler role permission to invoke executeUsecaseLambda
    this.executeUsecaseLambda.grantInvoke(this.schedulerRole);

    // Stop Execution Lambda - stops running ECS tasks
    this.stopExecutionLambda = this.createPythonLambda({
      path: 'stop_execution',
      environment: {
        TABLE_NAME: props.table.tableName,
        ECS_CLUSTER: this.cluster.clusterArn
      }
    });

    props.table.grantFullAccess(this.stopExecutionLambda)

    // Grant ECS StopTask permissions to stopExecutionLambda
    this.stopExecutionLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'ecs:StopTask',
        'ecs:DescribeTasks'
      ],
      resources: [
        `arn:aws:ecs:${Aws.REGION}:${Aws.ACCOUNT_ID}:task/${this.cluster.clusterName}/*`
      ]
    }));

    this.createScheduleLambda = this.createPythonLambda({
      path: 'create_schedule',
      environment: {
        SCHEDULER_GROUP_NAME: this.schedulerGroup.name!,
        EXECUTE_USECASE_LAMBDA_ARN: this.executeUsecaseLambda.functionArn,
        SCHEDULER_TARGET_ROLE_ARN: this.schedulerRole.roleArn
      }
    });

    // Wizard mode Lambda functions
    this.startWizardLambda = this.createPythonLambda({
      path: 'start_wizard_session',
      environment: {
        TABLE_NAME: props.table.tableName,
        ECS_CLUSTER: this.cluster.clusterArn,
        ECS_TASK_DEFINITION: this.taskDefinition.taskDefinitionArn,
        SUBNET_ID: this.vpc.privateSubnets[0].subnetId,
        SECURITY_GROUP_ID: this.workerSecurityGroup.securityGroupId,
        WIZARD_QUEUE_URL: this.wizardQueue.queueUrl,
        S3_BUCKET: this.artefactsBucket.bucketName,
        BEDROCK_EXECUTION_ROLE: this.agentCoreExecutionRole.roleArn,
        NOVA_ACT_API_KEY_NAME: props.novaActApiKeySecret.secretName,
      }
    });

    this.addWizardStepLambda = this.createPythonLambda({
      path: 'add_wizard_step',
      environment: {
        TABLE_NAME: props.table.tableName,
        WIZARD_QUEUE_URL: this.wizardQueue.queueUrl,
        WIZARD_EVENT_BUS_NAME: this.wizardEventBus.eventBusName,
      }
    });

    this.restartWizardLambda = this.createPythonLambda({
      path: 'restart_wizard',
      environment: {
        WIZARD_QUEUE_URL: this.wizardQueue.queueUrl,
        WIZARD_EVENT_BUS_NAME: this.wizardEventBus.eventBusName,
      }
    });

    this.terminateWizardLambda = this.createPythonLambda({
      path: 'terminate_wizard_session',
      environment: {
        TABLE_NAME: props.table.tableName,
        WIZARD_QUEUE_URL: this.wizardQueue.queueUrl,
        WIZARD_EVENT_BUS_NAME: this.wizardEventBus.eventBusName,
      }
    });

    // EventBridge command processor Lambda
    const processWizardCommandLambda = this.createPythonLambda({
      path: 'process_wizard_command',
      environment: {
        TABLE_NAME: props.table.tableName,
      }
    });

    // EventBridge rule to process wizard commands
    new Rule(this, 'wizard_command_rule', {
      eventBus: this.wizardEventBus,
      eventPattern: {
        source: ['wizard.commands'],
        detailType: ['WizardCommand'],
      },
      targets: [new LambdaFunction(processWizardCommandLambda)],
    });

    // Grant permissions for wizard Lambdas
    props.table.grantFullAccess(this.startWizardLambda);
    props.table.grantFullAccess(this.addWizardStepLambda);
    props.table.grantFullAccess(this.terminateWizardLambda);
    props.table.grantFullAccess(processWizardCommandLambda);

    this.wizardQueue.grantSendMessages(this.startWizardLambda);
    this.wizardQueue.grantSendMessages(this.addWizardStepLambda);
    this.wizardQueue.grantSendMessages(this.restartWizardLambda);
    this.wizardQueue.grantSendMessages(this.terminateWizardLambda);

    // Grant EventBridge permissions
    this.wizardEventBus.grantPutEventsTo(this.addWizardStepLambda);
    this.wizardEventBus.grantPutEventsTo(this.restartWizardLambda);
    this.wizardEventBus.grantPutEventsTo(this.terminateWizardLambda);

    this.startWizardLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['ecs:RunTask', 'iam:PassRole'],
      resources: [
        this.taskDefinition.taskDefinitionArn,
        this.taskDefinition.taskRole.roleArn,
        this.taskDefinition.executionRole!.roleArn
      ]
    }));

    // Grant EventBridge Scheduler permissions
    this.createScheduleLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'scheduler:CreateSchedule',
        'scheduler:DeleteSchedule',
        'scheduler:GetSchedule'
      ],
      resources: [
        `arn:aws:scheduler:${Aws.REGION}:${Aws.ACCOUNT_ID}:schedule/${this.schedulerGroup.name}/*`
      ]
    }));

    // Grant permission to pass the scheduler role to EventBridge
    this.createScheduleLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['iam:PassRole'],
      resources: [this.schedulerRole.roleArn]
    }));

    // TODO: remove
    this.executionQueue.grantSendMessages(this.executeUsecaseLambda);

    // Grant ECS RunTask permissions to executeUsecaseLambda
    this.executeUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'ecs:RunTask',
        'iam:PassRole'
      ],
      resources: [
        this.taskDefinition.taskDefinitionArn,
        this.taskDefinition.taskRole.roleArn,
        this.taskDefinition.executionRole!.roleArn
      ]
    }));

    // Grant EventBridge permissions to executeUsecaseLambda
    this.executeUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['events:PutEvents'],
      resources: [`arn:aws:events:${Aws.REGION}:${Aws.ACCOUNT_ID}:event-bus/default`]
    }));

    // Task State Change Handler Lambda - monitors ECS task failures
    const taskStateChangeLambda = this.createPythonLambda({
      path: 'handle_task_state_change',
      codeDirectory: 'lambdas/events',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    props.table.grantFullAccess(taskStateChangeLambda);

    // EventBridge Rule to capture ECS task state changes
    const taskStateChangeRule = new Rule(this, 'TaskStateChangeRule', {
      eventPattern: {
        source: ['aws.ecs'],
        detailType: ['ECS Task State Change'],
        detail: {
          clusterArn: [this.cluster.clusterArn],
          lastStatus: ['STOPPED']
        }
      },
      description: 'Captures ECS task state changes for failure detection'
    });

    // Add Lambda as target for the EventBridge rule
    taskStateChangeRule.addTarget(new LambdaFunction(taskStateChangeLambda));

    this.log('clusterName', this.cluster.clusterName)
    this.log('taskDefinition', this.taskDefinition.taskDefinitionArn)
    this.log('schedulerGroup', this.schedulerGroup.name!)
    this.log('artefactsBucket', this.artefactsBucket.bucketName)
    this.log('registry', registry.repositoryName)
  }

  /**
   * Creates an S3 bucket in a different region using AwsCustomResource
   * This allows creating buckets in regions other than the stack's region
   * Configures cross-region replication to the default region bucket
   * 
   * @param region - AWS region where the bucket should be created
   * @returns The ARN of the created bucket
   */
  private createCrossRegionBucket(region: string): string {
    const bucketName = `${this.account}-${this.baseName}-artefacts-${region}`;
    const bucketArn = `arn:aws:s3:::${bucketName}`;

    // Create replication role
    const replicationRole = new Role(this, `ReplicationRole-${region}`, {
      roleName: `${this.baseName}-replication-role-${region}`,
      assumedBy: new ServicePrincipal('s3.amazonaws.com'),
      description: `Replication role for ${bucketName} to ${this.artefactsBucket.bucketName}`,
    });

    // Grant read permissions on source bucket
    replicationRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: [
          's3:GetReplicationConfiguration',
          's3:ListBucket',
          's3:GetObjectVersionForReplication',
          's3:GetObjectVersionAcl',
        ],
        resources: [bucketArn, `${bucketArn}/*`],
      })
    );

    // Grant write permissions on destination bucket
    this.artefactsBucket.grantWrite(replicationRole);
    replicationRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['s3:ReplicateObject', 's3:ReplicateDelete', 's3:ReplicateTags'],
        resources: [`${this.artefactsBucket.bucketArn}/*`],
      })
    );

    const createBucketParams: any = {
      Bucket: bucketName,
    };

    // us-east-1 doesn't support LocationConstraint
    if (region !== 'us-east-1') {
      createBucketParams.CreateBucketConfiguration = {
        LocationConstraint: region,
      };
    }

    // Create the bucket
    const bucketResource = new AwsCustomResource(this, `CrossRegionBucket-${region}`, {
      onCreate: {
        service: 'S3',
        action: 'createBucket',
        parameters: createBucketParams,
        region: region,
        physicalResourceId: PhysicalResourceId.of(bucketName),
      },
      onDelete: {
        service: 'S3',
        action: 'deleteBucket',
        parameters: {
          Bucket: bucketName,
        },
        region: region,
      },
      policy: AwsCustomResourcePolicy.fromSdkCalls({
        resources: [bucketArn, `${bucketArn}/*`],
      }),
    });

    // Enable versioning (required for replication)
    const versioningResource = new AwsCustomResource(this, `BucketVersioning-${region}`, {
      onCreate: {
        service: 'S3',
        action: 'putBucketVersioning',
        parameters: {
          Bucket: bucketName,
          VersioningConfiguration: {
            Status: 'Enabled',
          },
        },
        region: region,
        physicalResourceId: PhysicalResourceId.of(`${bucketName}-versioning`),
      },
      policy: AwsCustomResourcePolicy.fromStatements([
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['s3:PutBucketVersioning', 's3:GetBucketVersioning'],
          resources: [bucketArn],
        }),
      ]),
    });
    versioningResource.node.addDependency(bucketResource);

    // Configure replication
    const replicationResource = new AwsCustomResource(this, `BucketReplication-${region}`, {
      onCreate: {
        service: 'S3',
        action: 'putBucketReplication',
        parameters: {
          Bucket: bucketName,
          ReplicationConfiguration: {
            Role: replicationRole.roleArn,
            Rules: [
              {
                Id: `replicate-to-${defaultRegion}`,
                Status: 'Enabled',
                Priority: 1,
                Filter: {},
                Destination: {
                  Bucket: this.artefactsBucket.bucketArn,
                },
                DeleteMarkerReplication: {
                  Status: 'Enabled',
                },
              },
            ],
          },
        },
        region: region,
        physicalResourceId: PhysicalResourceId.of(`${bucketName}-replication`),
      },
      policy: AwsCustomResourcePolicy.fromStatements([
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            's3:PutReplicationConfiguration',
            's3:GetReplicationConfiguration',
          ],
          resources: [bucketArn],
        }),
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['iam:PassRole'],
          resources: [replicationRole.roleArn],
        }),
      ]),
    });
    replicationResource.node.addDependency(versioningResource);

    return bucketArn;
  }
}