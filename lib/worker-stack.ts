import { Duration, RemovalPolicy, Aws } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Table } from 'aws-cdk-lib/aws-dynamodb';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { PolicyStatement, Policy, Effect, Role, ServicePrincipal, PolicyDocument } from 'aws-cdk-lib/aws-iam';
import { Queue } from 'aws-cdk-lib/aws-sqs';
import { CfnScheduleGroup } from 'aws-cdk-lib/aws-scheduler';
import { Repository } from 'aws-cdk-lib/aws-ecr';
import { OperatingSystemFamily, FargateTaskDefinition, Cluster, CpuArchitecture, ContainerImage, LogDrivers } from 'aws-cdk-lib/aws-ecs';
import { Vpc, GatewayVpcEndpointAwsService, InterfaceVpcEndpointAwsService, SecurityGroup } from 'aws-cdk-lib/aws-ec2';
import { Secret } from 'aws-cdk-lib/aws-secretsmanager';
import { Function } from 'aws-cdk-lib/aws-lambda';
import { Platform, DockerImageAsset } from 'aws-cdk-lib/aws-ecr-assets';
import { ECRDeployment, DockerImageName } from 'cdk-ecr-deployment';
import { RetentionDays } from 'aws-cdk-lib/aws-logs';
import { ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';

interface NovaActQAStudioWorkerStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  baseName: string
  table: Table
  novaActApiKeySecret: Secret
  notificationQueue: Queue
  userAgentString: string,
  tableReadPolicy: ManagedPolicy,
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
  public readonly workerSecurityGroup: SecurityGroup
  public readonly artefactsBucket: Bucket
  public readonly taskDefinition: FargateTaskDefinition
  public readonly schedulerGroup: CfnScheduleGroup
  public readonly executionQueue: Queue
  public readonly cluster: Cluster
  public readonly createScheduleLambda: Function
  public readonly deleteScheduleLambda: Function
  public readonly getScheduleLambda: Function
  public readonly executeUsecaseLambda: Function
  public readonly generateS3UrlLambda: Function

  constructor(scope: Construct, id: string, props: NovaActQAStudioWorkerStackCreateProps) {
    super(scope, id, props);

    const registry = new Repository(this, 'images_repository', {
      removalPolicy: RemovalPolicy.DESTROY
    });
    this.artefactsBucket = new Bucket(this, 'artefacts', {
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // TODO: Remove this as the local queue feature is not needed anymore
    this.executionQueue = new Queue(this, 'queue', {
      queueName: this.cdkName('workhorse'),
      visibilityTimeout: Duration.minutes(10),
      removalPolicy: RemovalPolicy.DESTROY
    });

    const vpc = new Vpc(this, 'vpc', {
      vpcName: this.cdkName('vpc'),
      maxAzs: 2,
      natGateways: 2,
    });

    vpc.addGatewayEndpoint('S3Endpoint', {
      service: GatewayVpcEndpointAwsService.S3
    });

    vpc.addInterfaceEndpoint('EcrDockerEndpoint', {
      service: InterfaceVpcEndpointAwsService.ECR_DOCKER
    });

    vpc.addInterfaceEndpoint('EcrEndpoint', {
      service: InterfaceVpcEndpointAwsService.ECR
    });

    vpc.addInterfaceEndpoint('CloudWatchLogsEndpoint', {
      service: InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS
    });

    vpc.addGatewayEndpoint('DynamoDbEndpoint', {
      service: GatewayVpcEndpointAwsService.DYNAMODB
    });

    // Security Group for ECS tasks
    this.workerSecurityGroup = new SecurityGroup(this, 'EcsTaskSecurityGroup', {
      vpc,
      description: 'Security group for ECS tasks',
      allowAllOutbound: true
    });

    // ECS Cluster
    this.cluster = new Cluster(this, 'cluster', {
      vpc,
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
    });

    // Add container to task definition
    this.taskDefinition.addContainer('container', {
      image: ContainerImage.fromEcrRepository(registry, 'latest'),
      logging: LogDrivers.awsLogs({
        streamPrefix: this.cdkName('logs'),
        logRetention: RetentionDays.FIVE_DAYS,
      }),
      environment: {
        DYNAMO_TABLE: props.table.tableName,
        QUEUE_URL: this.executionQueue.queueUrl,
        BUCKET_NAME: this.artefactsBucket.bucketName,
        NOVA_ACT_API_KEY_NAME: props.novaActApiKeySecret.secretName,
        NOTIFICATION_QUEUE_URL: props.notificationQueue.queueUrl
      }
    });

    // Grant permissions to task roles (must be after container is added)
    // TODO: Remove queue
    this.executionQueue.grantConsumeMessages(this.taskDefinition.taskRole);
    props.table.grantFullAccess(this.taskDefinition.taskRole);
    this.artefactsBucket.grantReadWrite(this.taskDefinition.taskRole);
    props.notificationQueue.grantSendMessages(this.taskDefinition.taskRole);

    registry.grantPull(this.taskDefinition.executionRole!);
    registry.grantPull(this.taskDefinition.taskRole!);

    // Add ECR permissions to execution role
    this.taskDefinition.executionRole!.attachInlinePolicy(new Policy(this, 'ecr_access_policy', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            'secretsmanager:GetSecretValue',
            'ssm:GetParameters',
          ],
          resources: [
            "*",
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
          resources: [`*`]
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
          resources: [`*`]
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
            "*",
          ],
          resources: [`*`]
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

    new ECRDeployment(this, 'container_deployment', {
      src: new DockerImageName(workerImage.imageUri),
      dest: new DockerImageName(`${Aws.ACCOUNT_ID}.dkr.ecr.${Aws.REGION}.amazonaws.com/${registry.repositoryName}:latest`),
    });

    const agentCoreExecutionRole = new Role(this, 'agent_core_execution_role', {
      roleName: this.cdkName('agent_core_execution_role'),
      assumedBy: new ServicePrincipal('bedrock-agentcore.amazonaws.com'),
    })

    agentCoreExecutionRole.attachInlinePolicy(new Policy(this, 'agent_core_execution_role_s3', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            "s3:PutObject",
            "s3:ListMultipartUploadParts",
            "s3:AbortMultipartUpload"
          ],
          resources: [
            this.artefactsBucket.bucketArn,
            `${this.artefactsBucket.bucketArn}/*`
          ]
        })
      ]
    }))

    const schedulerRole = new Role(this, 'event_bridge_scheduler_role', {
      assumedBy: new ServicePrincipal('scheduler.amazonaws.com'),
      inlinePolicies: {
        LambdaInvokePolicy: new PolicyDocument({
          statements: [
            new PolicyStatement({
              effect: Effect.ALLOW,
              actions: ['lambda:InvokeFunction'],
              resources: ['*']
            })
          ]
        })
      }
    });

    this.executeUsecaseLambda = this.createLambda({
      path: 'execute_usecase',
      environment: {
        QUEUE_URL: this.executionQueue.queueUrl,
        ECS_CLUSTER: this.cluster.clusterArn,
        ECS_TASK_DEFINITION: this.taskDefinition.taskDefinitionArn,
        SUBNET_ID: vpc.publicSubnets[0].subnetId,
        SECURITY_GROUP_ID: this.workerSecurityGroup.securityGroupId,
        TABLE_NAME: props.table.tableName,
        S3_BUCKET: this.artefactsBucket.bucketName,
        BEDROCK_EXECUTION_ROLE: agentCoreExecutionRole.roleArn,
        NOVA_ACT_API_KEY_NAME: props.novaActApiKeySecret.secretName,
        SECRETS_PREFIX: props.baseName,
        USER_AGENT: props.userAgentString
      }
    });

    props.table.grantFullAccess(this.executeUsecaseLambda)

    this.createScheduleLambda = this.createLambda({
      path: 'create_schedule',
      environment: {
        SCHEDULER_GROUP_NAME: this.schedulerGroup.name!,
        EXECUTE_USECASE_LAMBDA_ARN: this.executeUsecaseLambda.functionArn,
        SCHEDULER_TARGET_ROLE_ARN: schedulerRole.roleArn
      }
    });

    this.getScheduleLambda = this.createLambda({
      path: 'get_schedule',
      environment: {
        SCHEDULER_GROUP_NAME: this.schedulerGroup.name!
      }
    });

    this.deleteScheduleLambda = this.createLambda({
      path: 'delete_schedule',
      environment: {
        SCHEDULER_GROUP_NAME: this.schedulerGroup.name!
      }
    });

    this.generateS3UrlLambda = this.createLambda({
      path: 'generate_s3_url',
      environment: {
        BUCKET_NAME: this.artefactsBucket.bucketName,
        TABLE_NAME: props.table.tableName
      }
    });

    this.generateS3UrlLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.artefactsBucket.grantRead(this.generateS3UrlLambda)

    // Grant EventBridge Scheduler permissions
    this.createScheduleLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'scheduler:CreateSchedule',
        'scheduler:DeleteSchedule',
        'scheduler:GetSchedule'
      ],
      resources: ['*']
    }));

    this.getScheduleLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['scheduler:GetSchedule'],
      resources: ['*']
    }));

    this.deleteScheduleLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['scheduler:DeleteSchedule'],
      resources: ['*']
    }));

    // Grant permission to pass the scheduler role to EventBridge
    this.createScheduleLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['iam:PassRole'],
      resources: [schedulerRole.roleArn]
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

    this.log('clusterName', this.cluster.clusterName)
    this.log('taskDefinition', this.taskDefinition.taskDefinitionArn)
    this.log('schedulerGroup', this.schedulerGroup.name!)
    this.log('artefactsBucket', this.artefactsBucket.bucketName)
    this.log('registry', registry.repositoryName)
  }
}