import { Duration, RemovalPolicy, Aws, CfnResource } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Table } from 'aws-cdk-lib/aws-dynamodb';
import { Bucket, HttpMethods, BucketEncryption, ObjectOwnership } from 'aws-cdk-lib/aws-s3';
import { PolicyStatement, Policy, Effect, Role, IRole, ServicePrincipal } from 'aws-cdk-lib/aws-iam';
import { Queue } from 'aws-cdk-lib/aws-sqs';
import { CfnScheduleGroup } from 'aws-cdk-lib/aws-scheduler';
import { Secret } from 'aws-cdk-lib/aws-secretsmanager';
import { Function, CfnMicrovmImage, LoggingFormat } from 'aws-cdk-lib/aws-lambda';
import { SqsEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import { LogGroup, MetricFilter, RetentionDays } from 'aws-cdk-lib/aws-logs';
import { ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { Rule, EventBus, Schedule } from 'aws-cdk-lib/aws-events';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { Alarm, ComparisonOperator, MathExpression, Metric, TreatMissingData } from 'aws-cdk-lib/aws-cloudwatch';
import { SnsAction } from 'aws-cdk-lib/aws-cloudwatch-actions';
import { Topic } from 'aws-cdk-lib/aws-sns';
import { AwsCustomResource, AwsCustomResourcePolicy, PhysicalResourceId } from 'aws-cdk-lib/custom-resources';
import { NagSuppressions } from 'cdk-nag';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';
import { loadConfig } from './config';
import { WorkerImageAsset } from './worker-image-asset';
import { BrowserVpc } from './browser-vpc';

const config = loadConfig();
const { defaultRegion, enabledRegions } = config;

interface NovaActQAStudioWorkerStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  baseName: string
  table: Table
  novaActApiKeySecret: Secret
  /**
   * Secrets Manager secret carrying the worker OAuth M2M credentials
   * (JSON: client_id, client_secret).  Built in the auth stack by the
   * CLI-unified-runner refactor.
   */
  workerCredentialsSecret: Secret
  /**
   * API Gateway deployment stage (e.g. "api").  Combined with the stack's
   * own region + the api-stack's deployed RestApi id (looked up at runtime
   * via SSM) to form the CLI's QA_STUDIO_API_URL.  The stage name itself
   * is part of the URL path and lives in config, so we pass it in.
   */
  apiDeploymentStage: string
  tableReadPolicy: ManagedPolicy
  tableWritePolicy: ManagedPolicy
  /** Package version; recorded as the MicroVM image `Description`. */
  version: string
  /**
   * Hard ceiling of one batch execution in minutes (MicroVM
   * `maximumDurationInSeconds` / 60). Defaults to configuration.json
   * `maxExecutionDurationMinutes`.
   */
  maxExecutionDurationMinutes?: number
  /**
   * Hard ceiling of one wizard session in minutes (MicroVM
   * `maximumDurationInSeconds` / 60 of the session VM). Defaults to
   * configuration.json `maxWizardSessionMinutes`.
   */
  maxWizardSessionMinutes?: number
}

/**
 * Cost allocation tag on the worker MicroVM image (the only taggable MicroVM
 * object). Activate the key as a cost allocation tag in the payer account to
 * separate QA Studio's MicroVM spend from other MicroVM users of the account.
 */
export const MICROVM_IMAGE_COST_TAG = { key: 'application', value: 'qa-studio' } as const;

/**
 * Inputs of the worker runtime permission set that are stack-local values
 * (not members), see `attachWorkerRuntimePolicies`.
 */
interface WorkerRuntimePolicyContext {
  table: Table
  novaActApiKeySecret: Secret
  notificationQueue: Queue
  recordingQueue: Queue
}

/**
 * NovaActQAStudioWorkerStack - Manages worker infrastructure for QA Studio
 * 
 * Key Components:
 * - SQS Queue for work processing
 * - EventBridge Scheduler group for scheduling tasks
 * - Lambda MicroVM image (the only worker compute), its build/execution
 *   roles, log group and S3 code artifact
 * 
 * The worker MicroVM is never in a VPC; it egresses to the internet directly.
 * AgentCore browsers run in PUBLIC network mode unless config `vpcId` is set:
 * then `BrowserVpc` looks the VPC up, selects the browser subnets, imports or
 * creates the browser security group and adds `AGENT_CORE_VPC` / `AC_*` to the
 * image env (browser-vpc.ts). Without `vpcId` the stack has no EC2 resource.
 * 
 * Readable Attributes:
 * - schedulerGroup: EventBridge scheduler group for managing schedules
 * - microvmImageArn / microvmImageVersion: the worker MicroVM image and its
 *   latest ACTIVE version (what `RunMicrovm` takes)
 * - microvmExecutionRole: role the MicroVM assumes at runtime
 * - microvmLogGroup: image build + VM runtime logs
 * 
 * Required Props:
 * - baseName: Base name for resource naming
 * - table: DynamoDB table for data storage
 * - this.artefactsBucket: S3 bucket for artifacts
 * - novaActApiKeySecret: Secrets Manager secret for Nova Act API key
 * - notificationQueue: SQS queue for notifications
 */
export class NovaActQAStudioWorkerStack extends NovaActQAStudioBaseStack {
  public readonly artefactsBucket: Bucket
  public readonly schedulerGroup: CfnScheduleGroup
  public readonly wizardQueue: Queue
  public readonly recordingQueueUrl: string
  public readonly recordingQueueArn: string
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
  public readonly microvmImageArn: string
  public readonly microvmImageVersion: string
  public readonly microvmExecutionRole: Role
  public readonly microvmLogGroup: LogGroup
  private readonly regionalBucketArns: string[] = []

  constructor(scope: Construct, id: string, props: NovaActQAStudioWorkerStackCreateProps) {
    super(scope, id, props);

    // S3 access log bucket for artefacts
    const artefactsLogBucket = new Bucket(this, 'artefacts-logs', {
      bucketName: `${this.account}-${this.baseName}-artefacts-logs-${this.region}`,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      encryption: BucketEncryption.S3_MANAGED,
      objectOwnership: ObjectOwnership.BUCKET_OWNER_PREFERRED,
    });

    this.artefactsBucket = new Bucket(this, 'artefacts', {
      bucketName: `${this.account}-${this.baseName}-artefacts-${this.region}`,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: true, // Required for cross-region replication
      encryption: BucketEncryption.S3_MANAGED,
      serverAccessLogsBucket: artefactsLogBucket,
      serverAccessLogsPrefix: 'access-logs/',
      cors: [
        {
          allowedMethods: [
            HttpMethods.GET,
            HttpMethods.HEAD,
            HttpMethods.PUT,
            HttpMethods.POST
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
    // When Nova Act GA is enabled, us-east-1 is always needed (Nova Act requires a same-region bucket)
    const crossRegionTargets = new Set(
      enabledRegions.filter((region: string) => region !== defaultRegion)
    );
    if (config.useNovaActGa) {
      crossRegionTargets.add('us-east-1');
    }
    // Remove default region in case it was added by the Nova Act check
    crossRegionTargets.delete(defaultRegion);

    this.regionalBucketArns = [
      this.artefactsBucket.bucketArn,
      ...[...crossRegionTargets].map((region: string) => this.createCrossRegionBucket(region)),
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

    // Aggregation Lambda - publishes CloudWatch metrics + updates DynamoDB for dashboard
    const aggregateExecutionLambda = this.createPythonLambda({
      path: 'aggregate_execution',
      timeout: Duration.seconds(15),
      memorySize: 256,
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    aggregateExecutionLambda.role?.addManagedPolicy(props.tableReadPolicy);
    aggregateExecutionLambda.role?.addManagedPolicy(props.tableWritePolicy);

    aggregateExecutionLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['cloudwatch:PutMetricData'],
      resources: ['*']
    }));

    const aggregationRule = new Rule(this, 'aggregate_execution_rule', {
      ruleName: this.cdkName('aggregate-execution'),
      description: 'Triggers dashboard aggregation on terminal execution status',
      eventBus: eventBus,
      eventPattern: {
        source: ['nova-act-qa-studio.execution'],
        detailType: ['nova-act-qa-studio.execution.status.changed'],
        detail: {
          status: ['success', 'failed']
        }
      }
    });

    aggregationRule.addTarget(new LambdaFunction(aggregateExecutionLambda));

    this.log('aggregationRule', aggregationRule.ruleName);

    // Device Farm Recording Downloader — async pattern:
    // Worker sends delayed SQS message (5 min) after mobile execution completes.
    // Lambda picks it up and downloads the video from Device Farm → S3.
    // Retries up to 5 times (2 min apart), then gives up via DLQ.
    const recordingDlq = new Queue(this, 'recording_download_dlq', {
      queueName: this.cdkName('recording-downloads-dlq'),
      retentionPeriod: Duration.days(7),
      removalPolicy: RemovalPolicy.DESTROY,
    });

    const recordingQueue = new Queue(this, 'recording_download_queue', {
      queueName: this.cdkName('recording-downloads'),
      visibilityTimeout: Duration.minutes(3),
      removalPolicy: RemovalPolicy.DESTROY,
      deadLetterQueue: {
        queue: recordingDlq,
        maxReceiveCount: 10,
      },
    });

    const downloadRecordingLambda = this.createPythonLambda({
      path: 'download_device_farm_recording',
      timeout: Duration.minutes(2),
      memorySize: 512,
      environment: {
        S3_BUCKET: this.artefactsBucket.bucketName,
        DYNAMODB_TABLE_NAME: props.table.tableName,
      }
    });

    this.artefactsBucket.grantWrite(downloadRecordingLambda);
    downloadRecordingLambda.role?.addManagedPolicy(props.tableWritePolicy);
    downloadRecordingLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'devicefarm:GetRemoteAccessSession',
        'devicefarm:ListArtifacts',
      ],
      resources: ['*'],
    }));

    downloadRecordingLambda.addEventSource(new SqsEventSource(recordingQueue, {
      batchSize: 1,
    }));

    this.log('recordingQueue', recordingQueue.queueName);
    this.recordingQueueUrl = recordingQueue.queueUrl;
    this.recordingQueueArn = recordingQueue.queueArn;

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

    // Image-level environment of the worker MicroVM (stack constants only).
    const baseEnvironment = {
      DYNAMO_TABLE: props.table.tableName,
      S3_BUCKET: this.artefactsBucket.bucketName,
      NOVA_ACT_API_KEY_NAME: props.novaActApiKeySecret.secretName,
      NOTIFICATION_QUEUE_URL: notificationQueue.queueUrl,
      AWS_REGION: Aws.REGION,
      // Nova Act GA Service configuration
      USE_NOVA_ACT_GA: config.useNovaActGa.toString(),
      NOVA_ACT_REGION: 'us-east-1',
      NOVA_ACT_S3_BUCKET: `${this.account}-${this.baseName}-artefacts-us-east-1`,
      // Device Farm region for mobile testing (only available in us-west-2)
      DEVICE_FARM_REGION: 'us-west-2',
      // SQS queue for async Device Farm recording downloads
      RECORDING_QUEUE_URL: recordingQueue.queueUrl,
      // Maximum body size accepted by network_assertion steps — read at
      // worker boot.  See lib/config.ts networkAssertionBodyMaxBytes.
      NETWORK_ASSERTION_BODY_MAX_BYTES: this.networkAssertionBodyMaxBytes.toString(),
    };

    // CLI-unified-runner additions:
    //   QA_STUDIO_API_URL_SSM / QA_STUDIO_TOKEN_ENDPOINT_SSM — SSM parameter
    //     names the supervisor resolves inside /run (api-stack and auth-stack
    //     write the parameters; the MicroVM execution role gets read access
    //     in attachWorkerRuntimePolicies).
    // The M2M credentials themselves are fetched from Secrets Manager at
    // /run, never baked into the image.
    const runnerEnvironment = {
      ...baseEnvironment,
      QA_STUDIO_API_URL_SSM: `/qa-studio/${this.baseName}/api-url`,
      QA_STUDIO_API_STAGE: props.apiDeploymentStage,
      QA_STUDIO_TOKEN_ENDPOINT_SSM: `/qa-studio/${this.baseName}/cognito-token-endpoint`,
    };

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
            "s3:GetObject",
            "s3:GetObjectVersion",
            "s3:ListMultipartUploadParts",
            "s3:AbortMultipartUpload"
          ],
          resources: s3Resources
        })
      ]
    }))

    const runtimePolicyContext: WorkerRuntimePolicyContext = {
      table: props.table,
      novaActApiKeySecret: props.novaActApiKeySecret,
      notificationQueue,
      recordingQueue,
    };

    this.schedulerGroup = new CfnScheduleGroup(this, 'schedule_group', {
      name: this.cdkName('schedules')
    });

    // ── Lambda MicroVM image ──
    // Lambda builds the image from the zipped, .dockerignore-filtered repo root
    // (Dockerfile at the zip root, see worker-image-asset.ts) on the managed
    // AL2023 base; CloudFormation waits for the build (several minutes).
    // Build and VM runtime logs share one stack-owned log group; build logs
    // land in stream `<version>/<build-id>`.
    this.microvmLogGroup = new LogGroup(this, 'microvm_log_group', {
      logGroupName: `/qa-studio/${this.baseName}/microvm`,
      retention: RetentionDays.FIVE_DAYS,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    const microvmLogsWrite = new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['logs:CreateLogStream', 'logs:PutLogEvents', 'logs:DescribeLogStreams'],
      resources: [this.microvmLogGroup.logGroupArn],
    });

    const microvmImageAsset = new WorkerImageAsset(this, 'microvm_image_asset');

    // Both roles are assumed by the Lambda MicroVM service with session tags.
    const microvmPrincipal = () => new ServicePrincipal('lambda.amazonaws.com').withSessionTags();

    const microvmBuildRole = new Role(this, 'microvm_build_role', {
      roleName: this.cdkName('microvm-build-role'),
      assumedBy: microvmPrincipal(),
      description: 'Assumed by Lambda to build the worker MicroVM image: reads the S3 code artifact, writes build logs',
    });
    const microvmBuildPolicy = new Policy(this, 'microvm_build_role_policy', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['s3:GetObject'],
          resources: [microvmImageAsset.bucket.arnForObjects(microvmImageAsset.s3ObjectKey)],
        }),
        microvmLogsWrite,
      ],
    });
    microvmBuildRole.attachInlinePolicy(microvmBuildPolicy);

    // Runtime role of the VM: the worker permission set, plus the worker M2M
    // credentials secret (the supervisor resolves it at /run) and the VM
    // lifecycle calls the supervisor makes on itself.
    this.microvmExecutionRole = new Role(this, 'microvm_execution_role', {
      roleName: this.cdkName('microvm-execution-role'),
      assumedBy: microvmPrincipal(),
      description: 'Assumed by the worker MicroVM at runtime',
    });
    this.attachWorkerRuntimePolicies(this.microvmExecutionRole, (name) => `microvm_exec_${name}`, runtimePolicyContext);
    props.workerCredentialsSecret.grantRead(this.microvmExecutionRole);

    // Image-level env is baked into the snapshot: stack constants only, never
    // per-execution values or secret values. AWS_REGION is a reserved key the
    // platform injects at runtime (ValidationException if set here).
    const microvmEnvironment: Record<string, string> = {
      ...runnerEnvironment,
      BEDROCK_EXECUTION_ROLE: this.agentCoreExecutionRole.roleArn,
      WORKER_CREDENTIALS_SECRET_ARN: props.workerCredentialsSecret.secretArn,
      // supervisor.py BATCH_REQUIRED_IMAGE_ENV / WIZARD_REQUIRED_IMAGE_ENV: the
      // names execute_usecase.py / start_wizard_session.py pass per task today.
      DYNAMODB_TABLE_NAME: props.table.tableName,
      S3_BUCKET_PREFIX: `${this.account}-${this.baseName}-artefacts`,
      SECRETS_PREFIX: this.baseName,
      WIZARD_QUEUE_URL: this.wizardQueue.queueUrl,
      // Read by the runner engine; `true` is its default, pinned for visibility.
      ENABLE_TRAJECTORY_REPLAY: 'true',
      // VPC-attached AgentCore browsers (CLI provisioner + wizard), only with vpcId.
      ...this.browserVpcEnvironment(),
    };
    delete microvmEnvironment.AWS_REGION;

    const microvmImage = new CfnMicrovmImage(this, 'microvm_image', {
      // Name is replacement-on-change: derived from baseName only.
      name: `${this.baseName}-worker`,
      description: props.version,
      baseImageArn: `arn:aws:lambda:${Aws.REGION}:aws:microvm-image:al2023-1`,
      baseImageVersion: '2',
      buildRoleArn: microvmBuildRole.roleArn,
      codeArtifact: { uri: `s3://${microvmImageAsset.s3BucketName}/${microvmImageAsset.s3ObjectKey}` },
      // ARM_64 is the only accepted architecture; the Dockerfile builds LINUX_ARM64.
      cpuConfigurations: [{ architecture: 'ARM_64' }],
      resources: [{ minimumMemoryInMiB: 1024 }],
      additionalOsCapabilities: [],
      // Egress defaults to INTERNET_EGRESS; passing the connector ARN explicitly
      // is rejected by the platform (spike). Ingress is set per VM at launch.
      egressNetworkConnectors: [],
      environmentVariables: Object.entries(microvmEnvironment).map(([key, value]) => ({ key, value })),
      hooks: {
        port: 8080,
        microvmHooks: {
          run: 'ENABLED', runTimeoutInSeconds: 60,
          terminate: 'ENABLED', terminateTimeoutInSeconds: 60,
          suspend: 'DISABLED', resume: 'DISABLED',
        },
        microvmImageHooks: {
          ready: 'ENABLED', readyTimeoutInSeconds: 600,
          validate: 'ENABLED', validateTimeoutInSeconds: 120,
        },
      },
      logging: { cloudWatch: { logGroup: this.microvmLogGroup.logGroupName } },
      // Cost allocation (.kiro/docs/cost-allocation/design.md): MicroVMs have no ARN
      // and RunMicrovm takes no tags, so the image is the only taggable object. If
      // MicroVM line items inherit it, this tag separates QA Studio's MicroVM spend
      // from other MicroVM users in the account (activate `application` as a cost
      // allocation tag in the payer account). It can never tell use cases apart;
      // that split comes from the execution records (cost_sources/compute.py).
      tags: [{ key: MICROVM_IMAGE_COST_TAG.key, value: MICROVM_IMAGE_COST_TAG.value }],
    });
    // The build must not start before the build role can read the artifact.
    microvmImage.node.addDependency(microvmBuildPolicy);
    this.microvmImageArn = microvmImage.attrImageArn;
    this.microvmImageVersion = microvmImage.attrLatestActiveImageVersion;

    // The supervisor terminates its own VM when the child exits and the
    // reconciler/stop Lambdas look VMs up; VMs have no ARN of their own in the
    // API, so the image ARN is the resource they are scoped to.
    this.microvmExecutionRole.attachInlinePolicy(new Policy(this, 'microvm_exec_lifecycle_policy', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:TerminateMicrovm', 'lambda:GetMicrovm'],
          resources: [microvmImage.attrImageArn],
        }),
        microvmLogsWrite,
      ],
    }));

    this.log('microvmImageArn', this.microvmImageArn);
    this.log('microvmImageVersion', this.microvmImageVersion);
    this.log('microvmLogGroup', this.microvmLogGroup.logGroupName);

    this.schedulerRole = new Role(this, 'event_bridge_scheduler_role', {
      roleName: this.cdkName('scheduler-role'),
      assumedBy: new ServicePrincipal('scheduler.amazonaws.com'),
    });

    // MICROVM_* and MAX_EXECUTION_DURATION_MINUTES feed microvm_launch.launch_microvm.
    const maxExecutionDurationMinutes = props.maxExecutionDurationMinutes ?? config.maxExecutionDurationMinutes ?? 60;

    this.executeUsecaseLambda = this.createPythonLambda({
      path: 'execute_usecase',
      timeout: Duration.seconds(30),
      environment: {
        TABLE_NAME: props.table.tableName,
        S3_BUCKET_PREFIX: `${this.account}-${this.baseName}-artefacts`,
        DEFAULT_REGION: defaultRegion,
        MICROVM_IMAGE_ARN: this.microvmImageArn,
        MICROVM_IMAGE_VERSION: this.microvmImageVersion,
        MICROVM_EXECUTION_ROLE_ARN: this.microvmExecutionRole.roleArn,
        MICROVM_LOG_GROUP: this.microvmLogGroup.logGroupName,
        MAX_EXECUTION_DURATION_MINUTES: maxExecutionDurationMinutes.toString(),
      }
    });

    props.table.grantReadWriteData(this.executeUsecaseLambda)

    // RunMicrovm permissions. One Policy construct with every statement:
    // cdk.json sets createNewPoliciesWithAddToRolePolicy, so each
    // addToRolePolicy() would be its own AWS::IAM::Policy resource.
    this.executeUsecaseLambda.role!.attachInlinePolicy(new Policy(this, 'execute_usecase_microvm_policy', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:RunMicrovm', 'lambda:GetMicrovmImage'],
          resources: [this.microvmImageArn],
        }),
        // The spike could not confirm whether RunMicrovm is authorised against
        // the image ARN or the (not yet existing) VM; allow the account's
        // microvm resources in this region as well so the launch is not denied
        // on the second interpretation. Narrow once verified in phase-1 tests.
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:RunMicrovm'],
          resources: [`arn:aws:lambda:${Aws.REGION}:${Aws.ACCOUNT_ID}:microvm/*`],
        }),
        // RunMicrovm "passes" the Lambda-managed network connectors to the VM
        // (NO_INGRESS explicitly, INTERNET_EGRESS as the default) and IAM
        // authorises that like PassRole: without it the launch is denied with
        // "not authorized to perform: lambda:PassNetworkConnector on
        // arn:aws:lambda:<region>:aws:network-connector:aws-network-connector:INTERNET_EGRESS".
        // Only the AWS-managed connectors (account "aws"), never a customer VPC connector.
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:PassNetworkConnector'],
          resources: [`arn:aws:lambda:${Aws.REGION}:aws:network-connector:aws-network-connector:*`],
        }),
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['iam:PassRole'],
          resources: [this.microvmExecutionRole.roleArn],
          conditions: { StringEquals: { 'iam:PassedToService': 'lambda.amazonaws.com' } },
        }),
      ],
    }));

    // Grant scheduler role permission to invoke executeUsecaseLambda
    this.executeUsecaseLambda.grantInvoke(this.schedulerRole);

    // Stop Execution Lambda - terminates the execution's MicroVM
    this.stopExecutionLambda = this.createPythonLambda({
      path: 'stop_execution',
      environment: {
        TABLE_NAME: props.table.tableName,
        MICROVM_IMAGE_ARN: this.microvmImageArn,
      }
    });

    props.table.grantReadWriteData(this.stopExecutionLambda)

    // TerminateMicrovm permissions. One Policy construct with every statement:
    // cdk.json sets createNewPoliciesWithAddToRolePolicy, so each
    // addToRolePolicy() would be its own AWS::IAM::Policy resource.
    this.stopExecutionLambda.role!.attachInlinePolicy(new Policy(this, 'stop_execution_microvm_policy', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:TerminateMicrovm', 'lambda:GetMicrovm'],
          resources: [this.microvmImageArn],
        }),
        // The spike could not confirm whether TerminateMicrovm is authorised
        // against the image ARN or the VM; allow the account's microvm
        // resources in this region as well so the stop is not denied on the
        // second interpretation. Narrow once verified in phase-1 tests.
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:TerminateMicrovm', 'lambda:GetMicrovm'],
          resources: [`arn:aws:lambda:${Aws.REGION}:${Aws.ACCOUNT_ID}:microvm/*`],
        }),
      ],
    }));

    // Execution reconciler — every 5 minutes, queries RUNNING_EXECUTIONS, asks
    // GetMicrovm about each VM and marks executions whose VM is TERMINATED /
    // gone / past deadline as failed through the shared terminal transition.
    // Placed after the image + stop Lambda because it needs this.microvmImageArn.
    const reconcileExecutionsLambda = this.createPythonLambda({
      path: 'reconcile_executions',
      // ≤ ~50 tracking records × (GetMicrovm + GetItem [+ UpdateItem ×≤4 + PutEvents]).
      timeout: Duration.seconds(60),
      environment: {
        TABLE_NAME: props.table.tableName,
        MICROVM_IMAGE_ARN: this.microvmImageArn,
      },
    });

    reconcileExecutionsLambda.role?.addManagedPolicy(props.tableReadPolicy);
    reconcileExecutionsLambda.role?.addManagedPolicy(props.tableWritePolicy);

    // One Policy construct with every statement: cdk.json sets
    // createNewPoliciesWithAddToRolePolicy, so each addToRolePolicy() would be
    // its own AWS::IAM::Policy resource.
    reconcileExecutionsLambda.role!.attachInlinePolicy(new Policy(this, 'reconcile_executions_policy', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:GetMicrovm'],
          resources: [this.microvmImageArn],
        }),
        // The spike could not confirm whether GetMicrovm is authorised against
        // the image ARN or the VM; allow the account's microvm resources in
        // this region as well so the lookup is not denied on the second
        // interpretation. Narrow once verified in phase-1 tests.
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:GetMicrovm'],
          resources: [`arn:aws:lambda:${Aws.REGION}:${Aws.ACCOUNT_ID}:microvm/*`],
        }),
        // PutMetricData has no resource-level scoping; the namespace condition
        // is the narrowest grant available.
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['cloudwatch:PutMetricData'],
          resources: ['*'],
          conditions: { StringEquals: { 'cloudwatch:namespace': 'QAStudio/Worker' } },
        }),
        // The shared terminal transition publishes execution.status.changed.
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['events:PutEvents'],
          resources: [`arn:aws:events:${Aws.REGION}:${Aws.ACCOUNT_ID}:event-bus/default`],
        }),
      ],
    }));

    new Rule(this, 'reconcile_executions_rule', {
      ruleName: this.cdkName('reconcile-executions'),
      description: 'Reconciles executions whose MicroVM is TERMINATED, gone or past its deadline',
      schedule: Schedule.rate(Duration.minutes(5)),
      targets: [new LambdaFunction(reconcileExecutionsLambda)],
    });

    // Steady state is zero reconciled executions: any non-zero sum means the
    // supervisor or runner failed to report and is a bug signal.
    new Alarm(this, 'reconciled_executions_alarm', {
      alarmName: this.cdkName('reconciled-executions'),
      alarmDescription: 'An execution had to be reconciled because its MicroVM died or overran without reporting',
      metric: new Metric({
        namespace: 'QAStudio/Worker',
        metricName: 'ReconciledExecutions',
        statistic: 'Sum',
        period: Duration.minutes(5),
      }),
      threshold: 0,
      comparisonOperator: ComparisonOperator.GREATER_THAN_THRESHOLD,
      evaluationPeriods: 1,
      treatMissingData: TreatMissingData.NOT_BREACHING,
    }).addAlarmAction(new SnsAction(notificationTopic));

    if (config.costAllocation.enabled) {
      this.createCostCollector(props, notificationTopic);
    }

    this.createScheduleLambda = this.createPythonLambda({
      path: 'create_schedule',
      environment: {
        TABLE_NAME: props.table.tableName,
        SCHEDULER_GROUP_NAME: this.schedulerGroup.name!,
        EXECUTE_USECASE_LAMBDA_ARN: this.executeUsecaseLambda.functionArn,
        SCHEDULER_TARGET_ROLE_ARN: this.schedulerRole.roleArn
      }
    });

    // Wizard mode Lambda functions. The wizard worker runs on a MicroVM too
    // (phase 2): start_wizard_session launches it with RunPayload(mode='wizard')
    // and the session's own ceiling, MAX_WIZARD_SESSION_MINUTES.
    const maxWizardSessionMinutes = props.maxWizardSessionMinutes ?? config.maxWizardSessionMinutes ?? 240;

    this.startWizardLambda = this.createPythonLambda({
      path: 'start_wizard_session',
      // RunMicrovm retries ThrottlingException with up to 15 s of backoff (same as execute_usecase).
      timeout: Duration.seconds(30),
      environment: {
        TABLE_NAME: props.table.tableName,
        S3_BUCKET_PREFIX: `${this.account}-${this.baseName}-artefacts`,
        DEFAULT_REGION: defaultRegion,
        MICROVM_IMAGE_ARN: this.microvmImageArn,
        MICROVM_IMAGE_VERSION: this.microvmImageVersion,
        MICROVM_EXECUTION_ROLE_ARN: this.microvmExecutionRole.roleArn,
        MICROVM_LOG_GROUP: this.microvmLogGroup.logGroupName,
        MAX_WIZARD_SESSION_MINUTES: maxWizardSessionMinutes.toString(),
      }
    });

    // RunMicrovm permissions — same set as execute_usecase_microvm_policy, in
    // ONE Policy construct (cdk.json sets createNewPoliciesWithAddToRolePolicy).
    this.startWizardLambda.role!.attachInlinePolicy(new Policy(this, 'start_wizard_microvm_policy', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:RunMicrovm', 'lambda:GetMicrovmImage'],
          resources: [this.microvmImageArn],
        }),
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:RunMicrovm'],
          resources: [`arn:aws:lambda:${Aws.REGION}:${Aws.ACCOUNT_ID}:microvm/*`],
        }),
        // RunMicrovm passes the Lambda-managed network connectors (NO_INGRESS
        // explicitly, INTERNET_EGRESS as the default); denied without this.
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:PassNetworkConnector'],
          resources: [`arn:aws:lambda:${Aws.REGION}:aws:network-connector:aws-network-connector:*`],
        }),
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['iam:PassRole'],
          resources: [this.microvmExecutionRole.roleArn],
          conditions: { StringEquals: { 'iam:PassedToService': 'lambda.amazonaws.com' } },
        }),
      ],
    }));

    this.addWizardStepLambda = this.createPythonLambda({
      path: 'add_wizard_step',
      environment: {
        TABLE_NAME: props.table.tableName,
        WIZARD_QUEUE_URL: this.wizardQueue.queueUrl,
        WIZARD_EVENT_BUS_NAME: this.wizardEventBus.eventBusName,
      }
    });

    // Unrouted since W4 (POST /wizard/{id}/restart has no client). Kept for one
    // release only so its ARN stays exported for api stacks deployed before
    // the route was removed (CloudFormation refuses to delete an export that
    // is still imported); it can no longer reach the queue or bus. Remove in B9.
    this.restartWizardLambda = this.createPythonLambda({
      path: 'restart_wizard',
      environment: {
        TABLE_NAME: props.table.tableName,
        WIZARD_QUEUE_URL: this.wizardQueue.queueUrl,
        WIZARD_EVENT_BUS_NAME: this.wizardEventBus.eventBusName,
      }
    });

    this.exportValue(this.restartWizardLambda.functionArn);

    this.terminateWizardLambda = this.createPythonLambda({
      path: 'terminate_wizard_session',
      environment: {
        TABLE_NAME: props.table.tableName,
        WIZARD_QUEUE_URL: this.wizardQueue.queueUrl,
        WIZARD_EVENT_BUS_NAME: this.wizardEventBus.eventBusName,
        MICROVM_IMAGE_ARN: this.microvmImageArn,
      }
    });

    // TerminateMicrovm permissions — same set as stop_execution_microvm_policy,
    // in ONE Policy construct (cdk.json sets createNewPoliciesWithAddToRolePolicy).
    this.terminateWizardLambda.role!.attachInlinePolicy(new Policy(this, 'terminate_wizard_microvm_policy', {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:TerminateMicrovm', 'lambda:GetMicrovm'],
          resources: [this.microvmImageArn],
        }),
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:TerminateMicrovm', 'lambda:GetMicrovm'],
          resources: [`arn:aws:lambda:${Aws.REGION}:${Aws.ACCOUNT_ID}:microvm/*`],
        }),
      ],
    }));

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
    props.table.grantReadWriteData(this.startWizardLambda);
    props.table.grantReadWriteData(this.addWizardStepLambda);
    props.table.grantReadWriteData(this.terminateWizardLambda);
    props.table.grantReadWriteData(processWizardCommandLambda);

    // Need table read for the require_resource_access owner lookup (these
    // routes have no other table access). Guarded by
    // lib/__tests__/ownership-check-iam.test.ts.
    [this.createScheduleLambda, this.restartWizardLambda]
      .forEach(lambda => lambda.role?.addManagedPolicy(props.tableReadPolicy));

    this.wizardQueue.grantSendMessages(this.addWizardStepLambda);
    this.wizardQueue.grantSendMessages(this.terminateWizardLambda);

    // Grant EventBridge permissions
    this.wizardEventBus.grantPutEventsTo(this.addWizardStepLambda);
    this.wizardEventBus.grantPutEventsTo(this.terminateWizardLambda);

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

    // Grant EventBridge permissions to executeUsecaseLambda
    this.executeUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['events:PutEvents'],
      resources: [`arn:aws:events:${Aws.REGION}:${Aws.ACCOUNT_ID}:event-bus/default`]
    }));

    this.log('schedulerGroup', this.schedulerGroup.name!)
    this.log('artefactsBucket', this.artefactsBucket.bucketName)
  }

  /**
   * Daily cost allocation (design: .kiro/docs/cost-allocation/design.md).
   * One Lambda, `cost_collector`, runs on `costAllocation.scheduleUtc`,
   * allocates the Cost Explorer bill of the last `lookbackDays` days per use
   * case / application / overall, writes the NDJSON ledgers under
   * `cost_allocation/` in the artefacts bucket and the `USAGE#... / SUMMARY`
   * items. A manual invoke with `{"days": [...]}` or `{"from", "to"}`
   * re-processes or backfills; a range that does not fit in 15 minutes
   * continues by invoking this function again (hence `lambda:InvokeFunction`
   * on its own ARN, built from the name: a Ref on the function would make the
   * role depend on the function and the function on the role).
   *
   * Env-var contract (read by cost_collector.py and cost_sources/*.py):
   * TABLE_NAME, S3_BUCKET, LOOKBACK_DAYS, NOVA_ACT_CE_SERVICE_NAME,
   * COMPUTE_COST_ENABLED, COMPUTE_CE_SERVICE,
   * COMPUTE_CE_COMPUTE_USAGE_TYPE_PREFIXES, COMPUTE_CE_SNAPSHOT_USAGE_TYPE_PREFIXES
   * (the two lists comma-separated).
   *
   * Two alarms on the notification topic: `Errors` (the run did not finish) and
   * `unmetered` (the run finished but `unmetered_usd > 0.5 * billed_usd`, i.e.
   * allocation and bill disagree). The latter reads the structured
   * `cost_collector.run` log line: the function logs with the JSON log format,
   * so the dict the handler passes to the logger is the `message` object and two
   * metric filters lift `unmetered_usd` / `billed_usd` into `QAStudio/CostAllocation`.
   */
  private createCostCollector(props: NovaActQAStudioWorkerStackCreateProps, alarmTopic: Topic): void {
    const { costAllocation } = config;
    // Same derivation as createPythonLambda's functionName (base-stack.ts).
    const functionName = this.cdkName(this.snakeToPascal('cost_collector'));

    const costCollectorLambda = this.createPythonLambda({
      path: 'cost_collector',
      timeout: Duration.minutes(15),
      memorySize: 1024,
      loggingFormat: LoggingFormat.JSON,
      environment: {
        TABLE_NAME: props.table.tableName,
        S3_BUCKET: this.artefactsBucket.bucketName,
        LOOKBACK_DAYS: costAllocation.lookbackDays.toString(),
        NOVA_ACT_CE_SERVICE_NAME: costAllocation.novaActServiceName,
        COMPUTE_COST_ENABLED: costAllocation.compute.enabled.toString(),
        COMPUTE_CE_SERVICE: costAllocation.compute.ceService,
        COMPUTE_CE_COMPUTE_USAGE_TYPE_PREFIXES: costAllocation.compute.ceComputeUsageTypePrefixes.join(','),
        COMPUTE_CE_SNAPSHOT_USAGE_TYPE_PREFIXES: costAllocation.compute.ceSnapshotUsageTypePrefixes.join(','),
      },
    });

    // BatchGetItem on USECASE metadata (+ Query for the compute source) and PutItem on SUMMARY.
    costCollectorLambda.role?.addManagedPolicy(props.tableReadPolicy);
    costCollectorLambda.role?.addManagedPolicy(props.tableWritePolicy);

    // One Policy construct with every statement: cdk.json sets
    // createNewPoliciesWithAddToRolePolicy, so each addToRolePolicy() would be
    // its own AWS::IAM::Policy resource.
    const costCollectorPolicy = new Policy(this, 'cost_collector_policy', {
      statements: [
        // Read-only billing and Nova Act list APIs; none of them has a resource ARN.
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['ce:GetCostAndUsage', 'pricing:GetProducts', 'nova-act:ListWorkflowDefinitions', 'nova-act:ListActs'],
          resources: ['*'],
        }),
        // The ledgers: read-modify-write of one NDJSON file per dimension.
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['s3:GetObject', 's3:PutObject'],
          resources: [`${this.artefactsBucket.bucketArn}/cost_allocation/*`],
        }),
        // ListObjectsV2 on the ledger prefix only (zeroes out ledgers a re-run did not touch).
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['s3:ListBucket'],
          resources: [this.artefactsBucket.bucketArn],
          conditions: { StringLike: { 's3:prefix': 'cost_allocation/*' } },
        }),
        // Backfill continuation: asynchronous self-invocation with the remaining days.
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['lambda:InvokeFunction'],
          resources: [`arn:aws:lambda:${Aws.REGION}:${Aws.ACCOUNT_ID}:function:${functionName}`],
        }),
      ],
    });
    costCollectorLambda.role!.attachInlinePolicy(costCollectorPolicy);
    const wildcardReason = 'ce:GetCostAndUsage, pricing:GetProducts, nova-act:ListWorkflowDefinitions and nova-act:ListActs are read-only APIs without resource ARNs; the S3 and Lambda statements are scoped to the cost_allocation/ prefix and the function itself';
    NagSuppressions.addResourceSuppressions(costCollectorPolicy, [
      { id: 'AwsSolutions-IAM5', appliesTo: ['Resource::*'], reason: wildcardReason },
    ]);
    (costCollectorPolicy.node.defaultChild as CfnResource).addMetadata('cfn_nag', {
      rules_to_suppress: [{ id: 'W12', reason: wildcardReason }],
    });

    new Rule(this, 'cost_collector_rule', {
      ruleName: this.cdkName('cost-collector'),
      description: 'Runs the daily cost allocation collector (Cost Explorer bill per use case, application and overall)',
      schedule: Schedule.expression(costAllocation.scheduleUtc),
      targets: [new LambdaFunction(costCollectorLambda)],
    });

    // One run per day: any invocation error means the day's ledgers were not written.
    new Alarm(this, 'cost_collector_errors_alarm', {
      alarmName: this.cdkName('cost-collector-errors'),
      alarmDescription: 'The daily cost collector failed; the cost ledgers of the last run were not updated. Re-run: aws lambda invoke --function-name '
        + functionName + ' --payload {"days":["YYYY-MM-DD"]}',
      metric: costCollectorLambda.metricErrors({ statistic: 'Sum', period: Duration.days(1) }),
      threshold: 1,
      comparisonOperator: ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      evaluationPeriods: 1,
      treatMissingData: TreatMissingData.NOT_BREACHING,
    }).addAlarmAction(new SnsAction(alarmTopic));

    // unmetered_usd / billed_usd of the run report. fn.logGroup resolves to the
    // log group the Custom::LogRetention resource creates (Fn::GetAtt), so the
    // filters are ordered after the group exists.
    const runLineMetric = (id: string, metricName: string, field: string): Metric =>
      new MetricFilter(this, id, {
        logGroup: costCollectorLambda.logGroup,
        filterPattern: { logPatternString: '{ $.message.event = "cost_collector.run" }' },
        metricNamespace: 'QAStudio/CostAllocation',
        metricName,
        metricValue: `$.message.${field}`,
      }).metric({ statistic: 'Sum', period: Duration.days(1) });
    const unmetered = runLineMetric('cost_collector_unmetered_usd_filter', 'UnmeteredUsd', 'unmetered_usd');
    const billed = runLineMetric('cost_collector_billed_usd_filter', 'BilledUsd', 'billed_usd');

    new Alarm(this, 'cost_collector_unmetered_alarm', {
      alarmName: this.cdkName('cost-collector-unmetered'),
      alarmDescription: 'The daily cost collector finished but more than half of the bill had no usage to attribute it to (unmetered_usd > 0.5 * billed_usd): '
        + 'Cost Explorer and Nova Act / execution metering disagree. Compare billed_usd, allocated_usd and unmetered_usd in the '
        + 'cost_collector.run log line, check the sources, then re-run the day: aws lambda invoke --function-name '
        + functionName + ' --payload {"days":["YYYY-MM-DD"]}',
      metric: new MathExpression({
        expression: 'IF(unmetered > 0.5 * billed, 1, 0)',
        usingMetrics: { unmetered, billed },
        period: Duration.days(1),
      }),
      threshold: 1,
      comparisonOperator: ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      evaluationPeriods: 1,
      treatMissingData: TreatMissingData.NOT_BREACHING,
    }).addAlarmAction(new SnsAction(alarmTopic));

    this.log('costCollectorLambda', functionName);
  }

  /**
   * `AGENT_CORE_VPC` / `AC_*` image env when config `vpcId` is set (one
   * `Vpc.fromLookup`, at most one created security group); `{}` otherwise,
   * so deploys without `vpcId` have no EC2 resource and env-agnostic synth.
   */
  private browserVpcEnvironment(): Record<string, string> {
    if (!config.vpcId) return {};
    return new BrowserVpc(this, 'browser_vpc', {
      vpcId: config.vpcId,
      vpcSubnetIds: config.vpcSubnetIds,
      workerSecurityGroupId: config.workerSecurityGroupId,
    }).environment;
  }

  /**
   * Attach the worker runtime permission set to `role`: SSM runner params,
   * recording/notification/wizard queues, DynamoDB, regional artefact
   * buckets, EventBridge, Nova Act GA (if enabled), Secrets Manager (API key +
   * use case secrets), AgentCore browsers, Device Farm and PassRole on the
   * AgentCore execution role. Attached to the MicroVM execution role.
   *
   * Permissions stay split over several `Policy` constructs so no single
   * policy exceeds the inline-policy size limit; `id` maps the policy name
   * to a construct id.
   */
  private attachWorkerRuntimePolicies(role: IRole, id: (name: string) => string, ctx: WorkerRuntimePolicyContext): void {
    // SSM parameters the worker consults at start (API URL + Cognito token
    // endpoint). Both are written by other stacks: the api-stack writes the
    // api-url; the auth-stack writes the cognito-token-endpoint.
    role.attachInlinePolicy(new Policy(this, id('ssm_runner_params'), {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['ssm:GetParameter'],
          resources: [
            `arn:aws:ssm:${Aws.REGION}:${Aws.ACCOUNT_ID}:parameter/qa-studio/${this.baseName}/api-url`,
            `arn:aws:ssm:${Aws.REGION}:${Aws.ACCOUNT_ID}:parameter/qa-studio/${this.baseName}/cognito-token-endpoint`,
          ],
        }),
      ],
    }));

    // Recording queue: the worker enqueues Device Farm recording downloads.
    ctx.recordingQueue.grantSendMessages(role);

    // Separate policies keep each document small (SPCM < 25).
    // SQS permissions
    role.attachInlinePolicy(new Policy(this, id('sqs_policy'), {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            'sqs:ReceiveMessage', 'sqs:DeleteMessage', 'sqs:GetQueueAttributes',
            'sqs:GetQueueUrl', 'sqs:ChangeMessageVisibility',
          ],
          resources: [this.wizardQueue.queueArn],
        }),
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['sqs:SendMessage'],
          resources: [ctx.notificationQueue.queueArn],
        }),
      ],
    }));

    // DynamoDB permissions
    role.attachInlinePolicy(new Policy(this, id('dynamodb_policy'), {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            'dynamodb:BatchGetItem', 'dynamodb:BatchWriteItem',
            'dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem',
            'dynamodb:DeleteItem', 'dynamodb:Query', 'dynamodb:Scan',
          ],
          resources: [ctx.table.tableArn, `${ctx.table.tableArn}/index/*`],
        }),
      ],
    }));

    // S3 permissions
    role.attachInlinePolicy(new Policy(this, id('s3_policy'), {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            's3:GetObject*', 's3:GetBucket*', 's3:List*',
            's3:PutObject*', 's3:DeleteObject*', 's3:Abort*',
          ],
          // Every regional artefact bucket: runs and wizard sessions write to
          // the bucket of their executing region.
          resources: this.regionalBucketArns.flatMap((arn: string) => [arn, `${arn}/*`]),
        }),
      ],
    }));

    // EventBridge permissions
    role.attachInlinePolicy(new Policy(this, id('eventbridge_policy'), {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['events:PutEvents'],
          resources: [`arn:aws:events:${Aws.REGION}:${Aws.ACCOUNT_ID}:event-bus/default`]
        })
      ]
    }));


    // Nova Act GA Service permissions (only if enabled)
    if (config.useNovaActGa) {
      role.attachInlinePolicy(new Policy(this, id('nova_act_ga_policy'), {
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

    // Secrets Manager access: the Nova Act API key (used when
    // USE_NOVA_ACT_GA=false) and this deployment's use case secrets
    // (`${baseName}/usecase/...`). The trailing `*` covers the 6-character
    // random ARN suffix. The worker M2M credentials secret is NOT part of this
    // set: the MicroVM execution role gets an explicit grant (the supervisor
    // fetches it at /run).
    role.attachInlinePolicy(new Policy(this, id('secrets_manager_policy'), {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['secretsmanager:GetSecretValue'],
          resources: [
            ctx.novaActApiKeySecret.secretArn,
            `arn:aws:secretsmanager:${Aws.REGION}:${Aws.ACCOUNT_ID}:secret:${this.baseName}/usecase/*`,
          ]
        })
      ]
    }));
    role.attachInlinePolicy(new Policy(this, id('bedrock_agentscore'), {
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
          // The browser is created in the use case's executing region, which
          // can be any enabled region, not only the stack's region.
          resources: [...new Set([Aws.REGION, ...enabledRegions])].flatMap((region: string) => [
            `arn:aws:bedrock-agentcore:${region}:${Aws.ACCOUNT_ID}:browser/*`,
            `arn:aws:bedrock-agentcore:${region}:${Aws.ACCOUNT_ID}:browser-custom/*`,
            `arn:aws:bedrock-agentcore:${region}:${Aws.ACCOUNT_ID}:browser-session/*`,
          ])
        }),
        // Allow creation of the AgentCore network service-linked role. This is
        // required the first time an AgentCore browser is attached to a VPC —
        // AgentCore uses this SLR to manage the ENIs it places in your subnets.
        // Without it, CreateBrowser fails with:
        //   "Failed creating service linked role. Please verify that the calling
        //    role has sufficient permissions to create a service linked role."
        // Scoped to the AgentCore network service via the iam:AWSServiceName
        // condition, matching the nova-act SLR statement above.
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['iam:CreateServiceLinkedRole'],
          resources: [
            'arn:aws:iam::*:role/aws-service-role/network.bedrock-agentcore.amazonaws.com/*'
          ],
          conditions: {
            StringLike: {
              'iam:AWSServiceName': 'network.bedrock-agentcore.amazonaws.com'
            }
          }
        })
      ]
    }));

    // Device Farm permissions for mobile testing (Device Farm is only available in us-west-2).
    // The project is either supplied per use case / DEVICE_FARM_PROJECT_ARN or
    // auto-discovered (first project in the account, created if none exists),
    // so sessions, uploads and projects are scoped to this account's
    // us-west-2 resources rather than a single project ARN.
    const deviceFarmArn = (type: string, account: string = this.account) =>
      `arn:aws:devicefarm:us-west-2:${account}:${type}:*`;
    role.attachInlinePolicy(new Policy(this, id('device_farm'), {
      statements: [
        // No resource-level permissions for these actions ("*" required).
        // ListArtifacts is called with a session ARN, which is not one of its
        // supported resource types (job/run/suite/test).
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            'devicefarm:ListProjects',
            'devicefarm:CreateProject',
            'devicefarm:ListDevices',
            'devicefarm:ListArtifacts',
          ],
          resources: ['*'],
        }),
        // Public device catalog (devices have no account in their ARN).
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['devicefarm:GetDevice', 'devicefarm:CreateRemoteAccessSession'],
          resources: [deviceFarmArn('device', ''), deviceFarmArn('deviceinstance', '')],
        }),
        // Account-owned projects, uploads and sessions.
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: [
            'devicefarm:CreateRemoteAccessSession',
            'devicefarm:GetRemoteAccessSession',
            'devicefarm:StopRemoteAccessSession',
            'devicefarm:DeleteRemoteAccessSession',
            'devicefarm:CreateUpload',
            'devicefarm:GetUpload',
            'devicefarm:ListUploads',
          ],
          resources: [deviceFarmArn('project'), deviceFarmArn('upload'), deviceFarmArn('session')],
        }),
      ],
    }));

    // Allow the worker to pass the AgentCore execution role to the browser service
    role.attachInlinePolicy(new Policy(this, id('pass_agentcore_role'), {
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['iam:PassRole'],
          resources: [this.agentCoreExecutionRole.roleArn]
        })
      ]
    }));

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