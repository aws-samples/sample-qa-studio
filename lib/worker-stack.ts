import { Duration, RemovalPolicy, Aws } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Table } from 'aws-cdk-lib/aws-dynamodb';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { PolicyStatement, Policy, Effect, Role, ServicePrincipal, PolicyDocument } from 'aws-cdk-lib/aws-iam';
import { Queue } from 'aws-cdk-lib/aws-sqs';
import { CfnScheduleGroup } from 'aws-cdk-lib/aws-scheduler';
import { Repository } from 'aws-cdk-lib/aws-ecr';
import { OperatingSystemFamily, FargateTaskDefinition, Cluster, CpuArchitecture, ContainerImage, LogDrivers } from 'aws-cdk-lib/aws-ecs';
import { Vpc, IVpc, GatewayVpcEndpointAwsService, InterfaceVpcEndpointAwsService, SecurityGroup, ISecurityGroup } from 'aws-cdk-lib/aws-ec2';
import { Secret } from 'aws-cdk-lib/aws-secretsmanager';
import { Function } from 'aws-cdk-lib/aws-lambda';
import { Platform, DockerImageAsset } from 'aws-cdk-lib/aws-ecr-assets';
import { ECRDeployment, DockerImageName } from 'cdk-ecr-deployment';
import { RetentionDays } from 'aws-cdk-lib/aws-logs';
import { ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { Rule } from 'aws-cdk-lib/aws-events';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { AwsCustomResource, AwsCustomResourcePolicy, PhysicalResourceId } from 'aws-cdk-lib/custom-resources';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';
import { loadConfig } from './config';

const config = loadConfig();
const { defaultRegion, enabledRegions, vpcId, workerSecurityGroupId, createVpcEndpoints } = config;

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
  public readonly workerSecurityGroup: ISecurityGroup
  public readonly artefactsBucket: Bucket
  public readonly taskDefinition: FargateTaskDefinition
  public readonly schedulerGroup: CfnScheduleGroup
  public readonly executionQueue: Queue
  public readonly cluster: Cluster
  public readonly createScheduleLambda: Function
  public readonly deleteScheduleLambda: Function
  public readonly getScheduleLambda: Function
  public readonly executeUsecaseLambda: Function
  public readonly stopExecutionLambda: Function
  public readonly generateS3UrlLambda: Function
  private readonly regionalBucketArns: string[] = []

  constructor(scope: Construct, id: string, props: NovaActQAStudioWorkerStackCreateProps) {
    super(scope, id, props);

    const registry = new Repository(this, 'images_repository', {
      removalPolicy: RemovalPolicy.DESTROY,
      emptyOnDelete: true
    });
    this.artefactsBucket = new Bucket(this, 'artefacts', {
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: true, // Required for cross-region replication
    });

    // Create cross-region buckets for enabled regions and collect all bucket ARNs
    this.regionalBucketArns = [
      this.artefactsBucket.bucketArn,
      ...enabledRegions
        .filter((region: string) => region !== defaultRegion)
        .map((region: string) => this.createCrossRegionBucket(region)),
    ];

    // TODO: Remove this as the local queue feature is not needed anymore
    this.executionQueue = new Queue(this, 'queue', {
      queueName: this.cdkName('workhorse'),
      visibilityTimeout: Duration.minutes(10),
      removalPolicy: RemovalPolicy.DESTROY
    });

    // VPC Configuration: Use existing VPC or create new one
    let vpc: IVpc;
    let shouldCreateVpcEndpoints: boolean;

    if (vpcId) {
      // Use existing VPC - automatically discovers subnets
      vpc = Vpc.fromLookup(this, 'existing-vpc', {
        vpcId: vpcId
      });

      // Validate that the VPC has public subnets
      if (vpc.publicSubnets.length === 0) {
        throw new Error(`Existing VPC ${vpcId} must have at least one public subnet for ECS tasks`);
      }

      // Only create VPC endpoints if explicitly requested for existing VPC
      shouldCreateVpcEndpoints = createVpcEndpoints ?? false;
    } else {
      // Create new VPC with default configuration
      vpc = new Vpc(this, 'vpc', {
        vpcName: this.cdkName('vpc'),
        maxAzs: 2,
        natGateways: 2,
      });

      // Always create VPC endpoints for new VPC
      shouldCreateVpcEndpoints = true;
    }

    // Create VPC endpoints if needed
    if (shouldCreateVpcEndpoints) {
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
    }

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
        vpc,
        description: 'Security group for ECS tasks',
        allowAllOutbound: true
      });
    }

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

    // Grant S3 permissions for all regional buckets
    const s3Resources: string[] = [];
    this.regionalBucketArns.forEach(bucketArn => {
      s3Resources.push(bucketArn);
      s3Resources.push(`${bucketArn}/*`);
    });

    agentCoreExecutionRole.attachInlinePolicy(new Policy(this, 'agent_core_execution_role_s3', {
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

    const schedulerRole = new Role(this, 'event_bridge_scheduler_role', {
      roleName: this.cdkName('scheduler-role'),
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

    // Get the log group name and stream prefix from the task definition container
    const containerDefinition = this.taskDefinition.defaultContainer;
    const logGroupName = containerDefinition?.logDriverConfig?.options?.['awslogs-group'] || `/ecs/${this.cdkName('logs')}`;
    const logStreamPrefix = containerDefinition?.logDriverConfig?.options?.['awslogs-stream-prefix'] || this.cdkName('logs');

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
        USER_AGENT: props.userAgentString,
        LOG_GROUP_NAME: logGroupName,
        LOG_STREAM_PREFIX: logStreamPrefix
      }
    });

    props.table.grantFullAccess(this.executeUsecaseLambda)

    // Stop Execution Lambda - stops running ECS tasks
    this.stopExecutionLambda = this.createLambda({
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
      resources: ['*'] // StopTask requires wildcard for task resources
    }));

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

    // Grant EventBridge permissions to executeUsecaseLambda
    this.executeUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['events:PutEvents'],
      resources: [`arn:aws:events:${Aws.REGION}:${Aws.ACCOUNT_ID}:event-bus/default`]
    }));

    // Task State Change Handler Lambda - monitors ECS task failures
    const taskStateChangeLambda = this.createLambda({
      path: 'handle_task_state_change',
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
    const bucketName = `${this.baseName}-artefacts-${region}`;
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
            'iam:PassRole',
          ],
          resources: [bucketArn, replicationRole.roleArn],
        }),
      ]),
    });
    replicationResource.node.addDependency(versioningResource);

    return bucketArn;
  }
}