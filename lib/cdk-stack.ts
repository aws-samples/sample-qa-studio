import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as scheduler from 'aws-cdk-lib/aws-scheduler';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as backup from 'aws-cdk-lib/aws-backup';

interface CreateLambdaProps {
  name: string,
  path: string,
  memorySize?: number,
  environment?: { [key: string]: string; },
  timeout?: cdk.Duration,
}

interface NovaActQAStudioCreateProps extends cdk.StackProps {
  baseName: string
}

export class NovaActQAStudio extends cdk.Stack {
  private baseName: string = ""

  private cdkName(name: string): string {
    const computedName = `${this.baseName}-${name.toLocaleLowerCase().replace("_", "-")}`
    // console.log(computedName)
    return computedName
  }

  private CreateLambda(props: CreateLambdaProps): lambda.Function {
    const fn = new lambda.Function(this, `lambda_${this.cdkName(props.name)}`, {
      functionName: this.cdkName(props.name),
      runtime: lambda.Runtime.PROVIDED_AL2023,
      architecture: lambda.Architecture.ARM_64,
      memorySize: props.memorySize || 128,
      code: lambda.Code.fromAsset(`lambda/cmd/${props.path}`),
      timeout: props.timeout || cdk.Duration.seconds(5),
      handler: 'import.handler',
      environment: props.environment,
      logRetention: 5
    });

    fn.addToRolePolicy(new cdk.aws_iam.PolicyStatement({
      actions: ['logs:CreateLogGroup',
        'logs:CreateLogStream',
        'logs:PutLogEvents'],
      resources: ['*'],
    }))

    return fn
  }

  constructor(scope: Construct, id: string, props: NovaActQAStudioCreateProps) {
    super(scope, id, props);
    this.baseName = props?.baseName

    const novaApiKey = new secretsmanager.Secret(this, 'NovaApiKey', {
      secretName: this.cdkName('nova-api-key')
    })

    // DynamoDB Table
    const table = new dynamodb.Table(this, 'Table', {
      tableName: this.cdkName('data_table'),
      partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'sk', type: dynamodb.AttributeType.STRING },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const backupVault = new backup.BackupVault(this, "dynamodb_backup_vault")
    const plan = new backup.BackupPlan(this, "dynamodb_backup_plan")
    plan.addRule(backup.BackupPlanRule.daily(backupVault))
    plan.addSelection("data_table", {
      resources: [backup.BackupResource.fromDynamoDbTable(table)]
    })

    // API Gateway
    const api = new apigateway.RestApi(this, 'Api', {
      restApiName: this.cdkName('service'),
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'Authorization', 'X-Amz-Date', 'X-Api-Key', 'X-Amz-Security-Token']
      }
    });

    new cdk.CfnOutput(this, 'apigateway domain', { 
      value: api.url
    });

    // S3 Bucket for artifacts
    const bucket = new s3.Bucket(this, 'artefacts', {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // S3 Bucket for frontend
    const frontendBucket = new s3.Bucket(this, 'FrontendBucket', {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // Origin Access Identity
    const oai = new cloudfront.OriginAccessIdentity(this, 'OAI', {
      comment: 'OAI for frontend'
    });

    // CloudFront Distribution
    const distribution = new cloudfront.Distribution(this, 'distribution', {
      defaultBehavior: {
        origin: new origins.S3Origin(frontendBucket, {
          originAccessIdentity: oai
        }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS
      },
      defaultRootObject: 'index.html',
      errorResponses: [
        {
          httpStatus: 404,
          responseHttpStatus: 200,
          responsePagePath: '/index.html'
        }
      ]
    });

    new cdk.CfnOutput(this, 'CloudFrontDistributionDomain', { 
      value: distribution.distributionDomainName
    });

    // Grant OAI access to S3 bucket
    frontendBucket.grantRead(oai);

    // Deploy frontend to S3
    new s3deploy.BucketDeployment(this, 'frontendDeployment', {
      sources: [s3deploy.Source.asset('./frontend/build')],
      destinationBucket: frontendBucket,
      distribution,
      distributionPaths: ['/*']
    });

    // SQS Queue
    const queue = new sqs.Queue(this, 'queue', {
      queueName: this.cdkName('workhorse'),
      visibilityTimeout: cdk.Duration.minutes(10),
      removalPolicy: cdk.RemovalPolicy.DESTROY
    });

    // Cognito User Pool
    const userPool = new cognito.UserPool(this, 'user_pool', {
      userPoolName: this.cdkName('user-pool'),
      signInAliases: { email: true },
      selfSignUpEnabled: false,
    });

    new cdk.CfnOutput(this, 'user pool id', { 
      value: userPool.userPoolId
    });

    // Cognito User Pool Client
    const userPoolClient = new cognito.UserPoolClient(this, 'user_pool_client', {
      userPoolClientName: this.cdkName('client'),
      userPool,
      generateSecret: false,
      authFlows: {
        userSrp: true,
        userPassword: true
      },
      oAuth: {
        flows: {
          authorizationCodeGrant: true,
          implicitCodeGrant: true
        },
        scopes: [
          cognito.OAuthScope.OPENID, 
          cognito.OAuthScope.EMAIL,
          cognito.OAuthScope.PROFILE
        ]
      }
    });

    new cdk.CfnOutput(this, 'user pool client id', {
      value: userPoolClient.userPoolClientId
    })

    // EventBridge Schedule Group
    const scheduleGroup = new scheduler.CfnScheduleGroup(this, 'schedule_group', {
      name: this.cdkName('schedules')
    });

    // ECR Repository
    const ecrRepository = new ecr.Repository(this, 'images_repository');

    new cdk.CfnOutput(this, 'EcrName', { 
      value: ecrRepository.repositoryName
    });

    const ecrUri = ecrRepository.repositoryUri
    const ecrHostname = ecrUri.split('/')[0]

    new cdk.CfnOutput(this, 'EcrUri', { 
      value: ecrUri
    });

    new cdk.CfnOutput(this, 'EcrHostname', { 
      value: ecrHostname
    });

    const agentCoreExecutionRole = new iam.Role(this, 'agent_core_execution_role', {
      roleName: this.cdkName('agent_core_execution_role'),
      assumedBy: new iam.ServicePrincipal('bedrock-agentcore.amazonaws.com'),
    })

    // agentCoreExecutionRole.attachInlinePolicy(new iam.Policy(this, 'agent_core_execution_role_assume_role', {
    //   statements: [
    //     new iam.PolicyStatement({
    //       effect: iam.Effect.ALLOW,
    //       principals: [
    //         new iam.ServicePrincipal("bedrock-agentcore.amazonaws.com")
    //       ],
    //       actions: [
    //         'sts:AssumeRole',
    //       ],
    //       resources: [
    //         "*",
    //       ]
    //     })
    //   ]
    // }))

    agentCoreExecutionRole.attachInlinePolicy(new iam.Policy(this, 'agent_core_execution_role_s3', {
      statements: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "s3:PutObject",
            "s3:ListMultipartUploadParts",
            "s3:AbortMultipartUpload"
          ],
          resources: [
            bucket.bucketArn,
            `${bucket.bucketArn}/*`
          ]
        })
      ]
    }))

    // VPC for ECS
    const vpc = new ec2.Vpc(this, 'vpc', {
      vpcName: this.cdkName('vpc'),
      maxAzs: 2,
      natGateways: 1,
    });

    // Get default security group and allow all outbound traffic
    const defaultSecurityGroup = ec2.SecurityGroup.fromSecurityGroupId(this, 'default_security_group', vpc.vpcDefaultSecurityGroup);
    defaultSecurityGroup.addEgressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.allTraffic(),
      'Allow all outbound traffic'
    );

    // Add VPC endpoints for ECR and CloudWatch
    vpc.addGatewayEndpoint('S3Endpoint', {
      service: ec2.GatewayVpcEndpointAwsService.S3
    });

    vpc.addInterfaceEndpoint('EcrDockerEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER
    });

    vpc.addInterfaceEndpoint('EcrEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.ECR
    });

    vpc.addInterfaceEndpoint('CloudWatchLogsEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS
    });

    vpc.addGatewayEndpoint('DynamoDbEndpoint', {
      service: ec2.GatewayVpcEndpointAwsService.DYNAMODB
    });

    // Security Group for ECS tasks
    // const ecsSecurityGroup = new ec2.SecurityGroup(this, 'EcsTaskSecurityGroup', {
    //   vpc,
    //   description: 'Security group for ECS tasks',
    //   allowAllOutbound: true
    // });

    // ECS Cluster
    const cluster = new ecs.Cluster(this, 'cluster', {
      vpc,
      clusterName: this.cdkName('cluster'),
    });

    // ECS Task Definition
    const taskDefinition = new ecs.FargateTaskDefinition(this, 'task_definition', {
      memoryLimitMiB: 1024,
      cpu: 512,
      runtimePlatform: {
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
        cpuArchitecture: ecs.CpuArchitecture.ARM64
      },
    });


    // Add container to task definition
    taskDefinition.addContainer('container', {
      image: ecs.ContainerImage.fromEcrRepository(ecrRepository, 'latest'),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: this.cdkName('logs'),
        logRetention: cdk.aws_logs.RetentionDays.FIVE_DAYS,
      }),
      environment: {
        DYNAMO_TABLE: table.tableName,
        QUEUE_URL: queue.queueUrl,
        BUCKET_NAME: bucket.bucketName,
        NOVA_ACT_API_KEY_NAME: novaApiKey.secretName
      }
    });

    // Grant permissions to task
    table.grantFullAccess(taskDefinition.taskRole);
    queue.grantConsumeMessages(taskDefinition.taskRole);
    bucket.grantReadWrite(taskDefinition.taskRole);
    ecrRepository.grantPull(taskDefinition.executionRole!);
    ecrRepository.grantPull(taskDefinition.taskRole!);

    // Add ECR permissions to execution role
    taskDefinition.executionRole!.attachInlinePolicy(new iam.Policy(this, 'ecr_access_policy', {
      statements: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'secretsmanager:GetSecretValue',
            'ssm:GetParameters',
            // 'bedrock-agentcore:*',
          ],
          resources: [
            "*",
          ]
        }),
      ]
    }));

    // Add Secrets Manager permissions to execution role
    taskDefinition.executionRole!.attachInlinePolicy(new iam.Policy(this, 'secrets_manager_policy', {
      statements: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'secretsmanager:GetSecretValue',
            'secretsmanager:ListSecrets',
          ],
          resources: [`*`]
        })
      ]
    }));

    taskDefinition.taskRole!.attachInlinePolicy(new iam.Policy(this, 'task_role_secrets_manager_policy', {
      statements: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'secretsmanager:GetSecretValue',
            'secretsmanager:ListSecrets',
          ],
          resources: [`*`]
        })
      ]
    }));

    taskDefinition.taskRole!.attachInlinePolicy(new iam.Policy(this, 'task_role_bedrock_agentscore', {
      statements: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
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

    // Lambda Functions
    const listUsecasesLambda = this.CreateLambda({
      path: 'list_usecases',
      name: 'ListUsecases',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const createUsecaseLambda = this.CreateLambda({
      path: 'create_usecase',
      name: 'CreateUsecase',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const getUsecaseLambda = this.CreateLambda({
      path: 'get_usecase',
      name: 'GetUsecase',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const createStepLambda = this.CreateLambda({
      path: 'create_step',
      name: 'CreateStep',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const listStepsLambda = this.CreateLambda({
      path: 'list_steps',
      name: 'ListSteps',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const executeUsecaseLambda = this.CreateLambda({
      path: 'execute_usecase',
      name: 'ExecuteUsecase',
      environment: {
        QUEUE_URL: queue.queueUrl,
        ECS_CLUSTER: cluster.clusterArn,
        ECS_TASK_DEFINITION: taskDefinition.taskDefinitionArn,
        SUBNET_ID: vpc.publicSubnets[0].subnetId,
        SECURITY_GROUP_ID: vpc.vpcDefaultSecurityGroup,
        TABLE_NAME: table.tableName,
        S3_BUCKET: bucket.bucketName,
        BEDROCK_EXECUTION_ROLE: agentCoreExecutionRole.roleArn,
        NOVA_ACT_API_KEY_NAME: novaApiKey.secretName,
        SECRETS_PREFIX: props.baseName,
        USER_AGENT: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
      }
    });

    const updateStepLambda = this.CreateLambda({
      path: 'update_step',
      name: 'UpdateStep',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const deleteStepLambda = this.CreateLambda({
      path: 'delete_step',
      name: 'DeleteStep',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const updateUsecaseLambda = this.CreateLambda({
      path: 'update_usecase',
      name: 'UpdateUsecase',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const listExecutionsLambda = this.CreateLambda({
      path: 'list_executions',
      name: 'ListExecutions',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const updateExecutionLambda = this.CreateLambda({
      path: 'update_execution',
      name: 'UpdateExecution',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const deleteUsecaseLambda = this.CreateLambda({
      path: 'delete_usecase',
      name: 'DeleteUsecase',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const deleteExecutionLambda = this.CreateLambda({
      path: 'delete_execution',
      name: 'DeleteExecution',
      environment: {
        TABLE_NAME: table.tableName,
        BUCKET_NAME: bucket.bucketName
      }
    });

    const updateExecutionStepLambda = this.CreateLambda({
      path: 'update_execution_step',
      name: 'UpdateExecutionStep',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const getExecutionStepLambda = this.CreateLambda({
      path: 'get_execution_step',
      name: 'GetExecutionStep',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const getExecutionLambda = this.CreateLambda({
      path: 'get_execution',
      name: 'GetExecution',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const listExecutionStepsLambda = this.CreateLambda({
      path: 'list_execution_steps',
      name: 'ListExecutionSteps',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const createUsecaseVariablesLambda = this.CreateLambda({
      path: 'create_usecase_variables',
      name: 'CreateUsecaseVariables',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const getUsecaseVariablesLambda = this.CreateLambda({
      path: 'get_usecase_variables',
      name: 'GetUsecaseVariables',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    // Create IAM role for EventBridge Scheduler
    const schedulerRole = new iam.Role(this, 'event_bridge_scheduler_role', {
      assumedBy: new iam.ServicePrincipal('scheduler.amazonaws.com'),
      inlinePolicies: {
        LambdaInvokePolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: ['lambda:InvokeFunction'],
              resources: ['*']
            })
          ]
        })
      }
    });

    const createScheduleLambda = this.CreateLambda({
      path: 'create_schedule',
      name: 'CreateSchedule',
      environment: {
        SCHEDULER_GROUP_NAME: scheduleGroup.name!,
        EXECUTE_USECASE_LAMBDA_ARN: executeUsecaseLambda.functionArn,
        SCHEDULER_TARGET_ROLE_ARN: schedulerRole.roleArn
      }
    });

    const getScheduleLambda = this.CreateLambda({
      path: 'get_schedule',
      name: 'GetSchedule',
      environment: {
        SCHEDULER_GROUP_NAME: scheduleGroup.name!
      }
    });

    const deleteScheduleLambda = this.CreateLambda({
      path: 'delete_schedule',
      name: 'DeleteSchedule',
      environment: {
        SCHEDULER_GROUP_NAME: scheduleGroup.name!
      }
    });

    const createUsecaseHooksLambda = this.CreateLambda({
      path: 'create_usecase_hooks',
      name: 'CreateUsecaseHooks',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const getUsercaseHooksLambda = this.CreateLambda({
      path: 'get_usecase_hooks',
      name: 'GetUsecaseHooks',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const generateS3UrlLambda = this.CreateLambda({
      path: 'generate_s3_url',
      name: 'GenerateS3Url',
      environment: {
        BUCKET_NAME: bucket.bucketName,
        TABLE_NAME: table.tableName
      }
    });

    const createUsecaseSecretsLambda = this.CreateLambda({
      path: 'create_usecase_secrets',
      name: 'CreateUsecaseSecrets',
      environment: {
        SECRET_PREFIX: props.baseName
      }
    });

    const getUsecaseSecretsLambda = this.CreateLambda({
      path: 'get_usecase_secrets',
      name: 'GetUsecaseSecrets',
      environment: {
        SECRET_PREFIX: props.baseName
      }
    });

    const deleteUsecaseSecretsLambda = this.CreateLambda({
      path: 'delete_usecase_secrets',
      name: 'DeleteUsecaseSecrets',
      environment: {
        SECRET_PREFIX: props.baseName
      }
    });

    const updateUsecaseSecretsLambda = this.CreateLambda({
      path: 'update_usecase_secrets',
      name: 'UpdateUsecaseSecrets',
      environment: {
        SECRET_PREFIX: props.baseName
      }
    });

    const reorderStepsLambda = this.CreateLambda({
      path: 'reorder_steps',
      name: 'ReorderSteps',
      environment: {
        TABLE_NAME: table.tableName
      }
    });

    const getExecutionVariablesLambda = this.CreateLambda({
      path: 'get_execution_variables',
      name: 'GetExecutionVariables',
      environment: {
        DYNAMODB_TABLE_NAME: table.tableName
      }
    });

    const exportUsecaseLambda = this.CreateLambda({
      memorySize: 256,
      path: 'export_usecase',
      name: 'ExportUsecase',
      timeout: cdk.Duration.seconds(30),
      environment: {
        TABLE_NAME: table.tableName,
      }
    });

    const importUsecaseLambda = this.CreateLambda({
      memorySize: 256,
      path: 'import_usecase',
      name: 'ImportUsecase',
      timeout: cdk.Duration.seconds(30),
      environment: {
        TABLE_NAME: table.tableName,
      }
    });

    const generateUsecaseLambda = this.CreateLambda({
      memorySize: 512,
      path: 'generate_usecase',
      name: 'GenerateUsecase',
      timeout: cdk.Duration.seconds(60),
      environment: {
        TABLE_NAME: table.tableName,
        BEDROCK_MODEL_ID: 'eu.anthropic.claude-sonnet-4-20250514-v1:0',
        // BEDROCK_MODEL_ID: 'eu.amazon.nova-pro-v1:0',
        BEDROCK_REGION: 'eu-central-1'
      }
    });

    // Grant Lambda permissions
    table.grantReadData(listUsecasesLambda);
    table.grantWriteData(createUsecaseLambda);
    table.grantReadData(getUsecaseLambda);
    table.grantWriteData(createStepLambda);
    table.grantReadData(listStepsLambda);
    table.grantWriteData(updateStepLambda);
    table.grantWriteData(deleteStepLambda);
    table.grantWriteData(updateUsecaseLambda);
    table.grantReadData(listExecutionsLambda);
    table.grantWriteData(updateExecutionLambda);
    table.grantWriteData(updateExecutionStepLambda);
    table.grantReadData(getExecutionStepLambda);
    table.grantReadData(getExecutionLambda);
    table.grantReadData(listExecutionStepsLambda);
    table.grantWriteData(createUsecaseVariablesLambda);
    table.grantReadData(getUsecaseVariablesLambda);
    table.grantWriteData(createUsecaseHooksLambda);
    table.grantReadData(getUsercaseHooksLambda);
    table.grantReadData(generateS3UrlLambda);
    table.grantWriteData(reorderStepsLambda);
    table.grantReadData(getExecutionVariablesLambda);
    table.grantReadData(exportUsecaseLambda);
    table.grantWriteData(importUsecaseLambda);
    table.grantReadData(generateUsecaseLambda);

    // Grant S3 permissions to generate_s3_url Lambda
    bucket.grantRead(generateS3UrlLambda);

    // Grant Secrets Manager permissions
    createUsecaseSecretsLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'secretsmanager:CreateSecret',
        'secretsmanager:UpdateSecret',
        'secretsmanager:TagResource'
      ],
      resources: ['*']
    }));

    getUsecaseSecretsLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'secretsmanager:ListSecrets',
        'secretsmanager:DescribeSecret'
      ],
      resources: ['*']
    }));

    deleteUsecaseSecretsLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'secretsmanager:DeleteSecret'
      ],
      resources: ['*']
    }));

    // Grant Secrets Manager permissions for export/import
    exportUsecaseLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'secretsmanager:ListSecrets',
        'secretsmanager:DescribeSecret'
      ],
      resources: ['*']
    }));

    importUsecaseLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'secretsmanager:CreateSecret',
        'secretsmanager:UpdateSecret',
        'secretsmanager:TagResource'
      ],
      resources: ['*']
    }));

    // Grant Bedrock permissions to generate_usecase Lambda
    generateUsecaseLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'bedrock:InvokeModel',
        'bedrock:InvokeModelWithResponseStream'
      ],
      resources: [
        "*"
      ]
    }));

    updateUsecaseSecretsLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'secretsmanager:UpdateSecret'
      ],
      resources: ['*']
    }));

    // Grant EventBridge Scheduler permissions
    createScheduleLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'scheduler:CreateSchedule',
        'scheduler:DeleteSchedule',
        'scheduler:GetSchedule'
      ],
      resources: ['*']
    }));

    getScheduleLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['scheduler:GetSchedule'],
      resources: ['*']
    }));

    deleteScheduleLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['scheduler:DeleteSchedule'],
      resources: ['*']
    }));

    // Grant permission to pass the scheduler role to EventBridge
    createScheduleLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['iam:PassRole'],
      resources: [schedulerRole.roleArn]
    }));

    table.grantFullAccess(deleteUsecaseLambda);
    table.grantFullAccess(deleteExecutionLambda);
    bucket.grantDelete(deleteExecutionLambda);
    bucket.grantRead(deleteExecutionLambda);
    table.grantFullAccess(executeUsecaseLambda);
    queue.grantSendMessages(executeUsecaseLambda);

    // Grant ECS RunTask permissions to executeUsecaseLambda
    executeUsecaseLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'ecs:RunTask',
        'iam:PassRole'
      ],
      resources: [
        taskDefinition.taskDefinitionArn,
        taskDefinition.taskRole.roleArn,
        taskDefinition.executionRole!.roleArn
      ]
    }));

    // Cognito Authorizer
    const authorizer = new apigateway.CognitoUserPoolsAuthorizer(this, 'authorizer', {
      cognitoUserPools: [userPool]
    });

    // API Gateway endpoints
    const usecases = api.root.addResource('usecases');
    usecases.addMethod('GET', new apigateway.LambdaIntegration(listUsecasesLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    const usecase = api.root.addResource('usecase');
    usecase.addMethod('POST', new apigateway.LambdaIntegration(createUsecaseLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    const usecaseId = usecase.addResource('{id}');
    usecaseId.addMethod('GET', new apigateway.LambdaIntegration(getUsecaseLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    usecaseId.addMethod('PATCH', new apigateway.LambdaIntegration(updateUsecaseLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    usecaseId.addMethod('DELETE', new apigateway.LambdaIntegration(deleteUsecaseLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    const steps = usecaseId.addResource('steps');
    steps.addMethod('POST', new apigateway.LambdaIntegration(createStepLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    steps.addMethod('GET', new apigateway.LambdaIntegration(listStepsLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    // API Gateway execute endpoint
    const execute = usecaseId.addResource('execute');
    execute.addMethod('POST', new apigateway.LambdaIntegration(executeUsecaseLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    // API Gateway variables endpoint
    const variables = usecaseId.addResource('variables');
    variables.addMethod('POST', new apigateway.LambdaIntegration(createUsecaseVariablesLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    variables.addMethod('GET', new apigateway.LambdaIntegration(getUsecaseVariablesLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    // API Gateway schedule endpoint
    const schedule = usecaseId.addResource('schedule');
    schedule.addMethod('POST', new apigateway.LambdaIntegration(createScheduleLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    schedule.addMethod('GET', new apigateway.LambdaIntegration(getScheduleLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    schedule.addMethod('DELETE', new apigateway.LambdaIntegration(deleteScheduleLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    // API Gateway hooks endpoint
    const hooks = usecaseId.addResource('hooks');
    hooks.addMethod('POST', new apigateway.LambdaIntegration(createUsecaseHooksLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    hooks.addMethod('GET', new apigateway.LambdaIntegration(getUsercaseHooksLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    // API Gateway executions endpoints
    const executions = usecaseId.addResource('executions');
    executions.addMethod('GET', new apigateway.LambdaIntegration(listExecutionsLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    const execution = executions.addResource('{executionId}');
    execution.addMethod('PATCH', new apigateway.LambdaIntegration(updateExecutionLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    execution.addMethod('DELETE', new apigateway.LambdaIntegration(deleteExecutionLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    execution.addMethod('GET', new apigateway.LambdaIntegration(getExecutionLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    const executionSteps = execution.addResource('steps');
    executionSteps.addMethod('GET', new apigateway.LambdaIntegration(listExecutionStepsLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    const executionStep = executionSteps.addResource('{stepId}');
    executionStep.addMethod('PATCH', new apigateway.LambdaIntegration(updateExecutionStepLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    executionStep.addMethod('GET', new apigateway.LambdaIntegration(getExecutionStepLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    // API Gateway execution variables endpoint
    const executionVariables = execution.addResource('variables');
    executionVariables.addMethod('GET', new apigateway.LambdaIntegration(getExecutionVariablesLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    // API Gateway step endpoints
    const step = steps.addResource('{stepId}');
    step.addMethod('PATCH', new apigateway.LambdaIntegration(updateStepLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    step.addMethod('DELETE', new apigateway.LambdaIntegration(deleteStepLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    // API Gateway reorder steps endpoint
    const reorderSteps = steps.addResource('reorder');
    reorderSteps.addMethod('PATCH', new apigateway.LambdaIntegration(reorderStepsLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    // API Gateway endpoint for S3 URL generation
    const generateS3Url = api.root.addResource('generate-s3-url');
    generateS3Url.addMethod('POST', new apigateway.LambdaIntegration(generateS3UrlLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    // API Gateway secrets endpoints
    const secrets = usecaseId.addResource('secrets');
    secrets.addMethod('POST', new apigateway.LambdaIntegration(createUsecaseSecretsLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    secrets.addMethod('GET', new apigateway.LambdaIntegration(getUsecaseSecretsLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    secrets.addMethod('DELETE', new apigateway.LambdaIntegration(deleteUsecaseSecretsLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
    secrets.addMethod('PATCH', new apigateway.LambdaIntegration(updateUsecaseSecretsLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    // API Gateway export/import endpoints
    const exportEndpoint = usecaseId.addResource('export');
    exportEndpoint.addMethod('GET', new apigateway.LambdaIntegration(exportUsecaseLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    const importEndpoint = api.root.addResource('import');
    importEndpoint.addMethod('POST', new apigateway.LambdaIntegration(importUsecaseLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });

    // API Gateway generate-usecase endpoint
    const generateUsecase = api.root.addResource('generate-usecase');
    generateUsecase.addMethod('POST', new apigateway.LambdaIntegration(generateUsecaseLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO
    });
  }
}
