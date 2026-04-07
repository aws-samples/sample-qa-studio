import * as cdk from 'aws-cdk-lib';
import { Aws } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Function } from 'aws-cdk-lib/aws-lambda';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { Table } from 'aws-cdk-lib/aws-dynamodb';
import { UserPool } from 'aws-cdk-lib/aws-cognito';
import { PolicyStatement, Effect, ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';

interface NovaActQAStudioLambdaStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  artefactsBucket: Bucket
  table: Table
  userPool: UserPool
  schedulerGroupName: string
  tableReadPolicy: ManagedPolicy
  tableWritePolicy: ManagedPolicy
  tableFullAccessPolicy: ManagedPolicy
  bedrockModelId: string
  notificationTopicArn: string
  executeUsecaseLambda: Function
  ecsClusterArn: string
  recordingQueueUrl: string
  recordingQueueArn: string
  wizardEventBusName: string
}

/**
 * Lambda Stack - Contains all Lambda function definitions for the API
 * 
 * This stack is separated from the route definitions to:
 * - Stay under CloudFormation's 500 resource limit
 * - Allow independent deployment of Lambda code changes
 * - Improve deployment velocity
 */
export class NovaActQAStudioLambdaStack extends NovaActQAStudioBaseStack {
  // Usecase Lambdas
  public readonly listUsecasesLambda: Function
  public readonly createUsecaseLambda: Function
  public readonly getUsecaseLambda: Function
  public readonly updateUsecaseLambda: Function
  public readonly deleteUsecaseLambda: Function
  public readonly exportUsecaseLambda: Function
  public readonly importUsecaseLambda: Function
  public readonly cloneUsecaseLambda: Function
  public readonly generateUsecaseLambda: Function

  // Step Lambdas
  public readonly createStepLambda: Function
  public readonly listStepsLambda: Function
  public readonly updateStepLambda: Function
  public readonly deleteStepLambda: Function
  public readonly reorderStepsLambda: Function

  // Execution Lambdas
  public readonly listExecutionsLambda: Function
  public readonly getExecutionLambda: Function
  public readonly deleteExecutionLambda: Function
  public readonly getExecutionStepLambda: Function
  public readonly listExecutionStepsLambda: Function
  public readonly getExecutionVariablesLambda: Function
  public readonly getLiveViewLambda: Function
  public readonly updateExecutionStatusLambda: Function
  public readonly updateExecutionStepStatusLambda: Function
  public readonly generateExecutionArtifactUrlLambda: Function
  public readonly generateStepArtifactUrlLambda: Function
  public readonly confirmArtifactUploadLambda: Function
  public readonly listExecutionArtifactsLambda: Function
  public readonly generateSuiteArtifactUrlLambda: Function
  public readonly listSuiteArtifactsLambda: Function
  public readonly getStepTraceLambda: Function

  // Variables, Hooks, Headers Lambdas
  public readonly createUsecaseVariablesLambda: Function
  public readonly getUsecaseVariablesLambda: Function
  public readonly createUsecaseHooksLambda: Function
  public readonly getUsercaseHooksLambda: Function
  public readonly createUsecaseHeadersLambda: Function
  public readonly getUsecaseHeadersLambda: Function

  // Secrets Lambdas
  public readonly createUsecaseSecretsLambda: Function
  public readonly getUsecaseSecretsLambda: Function
  public readonly getUsecaseSecretValueLambda: Function
  public readonly deleteUsecaseSecretsLambda: Function
  public readonly updateUsecaseSecretsLambda: Function

  // Recording Lambdas
  public readonly listRecordingBatchesLambda: Function
  public readonly getRecordingBatchLambda: Function
  public readonly listDownloadsLambda: Function
  public readonly downloadFileLambda: Function
  public readonly getVideoPlaybackLambda: Function

  // Template Lambdas
  public readonly createTemplateLambda: Function
  public readonly listTemplatesLambda: Function
  public readonly getTemplateLambda: Function
  public readonly updateTemplateLambda: Function
  public readonly deleteTemplateLambda: Function
  public readonly listTemplateStepsLambda: Function
  public readonly createTemplateStepLambda: Function
  public readonly updateTemplateStepLambda: Function
  public readonly deleteTemplateStepLambda: Function
  public readonly reorderTemplateStepsLambda: Function
  public readonly createTemplateVariablesLambda: Function
  public readonly getTemplateVariablesLambda: Function
  public readonly applyTemplateLambda: Function
  public readonly importTemplateLambda: Function
  public readonly checkTemplateUpdatesLambda: Function
  public readonly updateStepFromTemplateLambda: Function

  // Utility Lambdas
  public readonly listModelsLambda: Function
  public readonly listDeviceFarmDevicesLambda: Function
  public readonly requestRecordingDownloadLambda: Function

  // Notification Lambdas (API-facing only)
  public readonly subscribeUsecaseLambda: Function
  public readonly unsubscribeUsecaseLambda: Function
  public readonly getUsecaseSubscriptionLambda: Function

  // User Management Lambdas
  public readonly listUsersLambda: Function
  public readonly addUserLambda: Function
  public readonly removeUserLambda: Function
  public readonly getUserLambda: Function
  public readonly updateUserGroupsLambda: Function

  // OAuth Client Management Lambdas
  public readonly createOAuthClientLambda: Function
  public readonly listOAuthClientsLambda: Function
  public readonly deleteOAuthClientLambda: Function
  public readonly rotateClientSecretLambda: Function
  public readonly listScopesLambda: Function

  // Test Suite Management Lambdas
  public readonly createTestSuiteLambda: Function
  public readonly listTestSuitesLambda: Function
  public readonly getTestSuiteLambda: Function
  public readonly updateTestSuiteLambda: Function
  public readonly deleteTestSuiteLambda: Function
  public readonly addUsecasesToSuiteLambda: Function
  public readonly listSuiteUsecasesLambda: Function
  public readonly removeUsecaseFromSuiteLambda: Function
  public readonly executeTestSuiteLambda: Function
  public readonly listSuiteExecutionsLambda: Function
  public readonly getSuiteExecutionLambda: Function
  public readonly stopSuiteExecutionLambda: Function
  public readonly updateSuiteExecutionStatusLambda: Function
  public readonly updateSuiteScheduleLambda: Function

  // Worker-related Lambdas (moved from worker stack)
  public readonly generateS3UrlLambda: Function
  public readonly acceptWizardStepLambda: Function
  public readonly rejectWizardStepLambda: Function
  public readonly getScheduleLambda: Function
  public readonly deleteScheduleLambda: Function

  // Browser Recording Lambdas
  public readonly sendRecordingCommandLambda: Function
  public readonly getRecordingDataLambda: Function

  constructor(scope: Construct, id: string, props: NovaActQAStudioLambdaStackCreateProps) {
    super(scope, id, props);

    // Usecase Lambdas
    this.listUsecasesLambda = this.createPythonLambda({
      path: 'list_usecases',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.createUsecaseLambda = this.createPythonLambda({
      path: 'create_usecase',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.getUsecaseLambda = this.createPythonLambda({
      path: 'get_usecase',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.updateUsecaseLambda = this.createPythonLambda({
      path: 'update_usecase',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.deleteUsecaseLambda = this.createPythonLambda({
      path: 'delete_usecase',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.exportUsecaseLambda = this.createPythonLambda({
      memorySize: 256,
      path: 'export_usecase',
      timeout: cdk.Duration.seconds(30),
      environment: {
        TABLE_NAME: props.table.tableName,
        SECRET_PREFIX: props.baseName
      }
    })

    this.importUsecaseLambda = this.createPythonLambda({
      memorySize: 256,
      path: 'import_usecase',
      timeout: cdk.Duration.seconds(30),
      environment: {
        TABLE_NAME: props.table.tableName,
        SECRET_PREFIX: props.baseName
      }
    })

    this.cloneUsecaseLambda = this.createPythonLambda({
      memorySize: 256,
      path: 'clone_usecase',
      timeout: cdk.Duration.seconds(30),
      environment: {
        TABLE_NAME: props.table.tableName,
        SECRET_PREFIX: props.baseName
      }
    })

    this.generateUsecaseLambda = this.createPythonLambda({
      memorySize: 512,
      path: 'generate_usecase',
      // Bedrock calls can take up to 120s for complex user journeys. The Lambda timeout
      // should match the API Gateway integration timeout. Default APIGW integration timeout
      // is 29s. If you increase the APIGW quota (see README step 3), update this to:
      // cdk.Duration.seconds(120)
      timeout: cdk.Duration.seconds(29),
      environment: {
        TABLE_NAME: props.table.tableName,
        BEDROCK_MODEL_ID: props.bedrockModelId,
        BUCKET_NAME: props.artefactsBucket.bucketName
      }
    })

    // Step Lambdas
    this.createStepLambda = this.createPythonLambda({
      path: 'create_step',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.listStepsLambda = this.createPythonLambda({
      path: 'list_steps',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.updateStepLambda = this.createPythonLambda({
      path: 'update_step',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.deleteStepLambda = this.createPythonLambda({
      path: 'delete_step',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.reorderStepsLambda = this.createPythonLambda({
      path: 'reorder_steps',
      environment: { TABLE_NAME: props.table.tableName }
    })

    // Execution Lambdas
    this.listExecutionsLambda = this.createPythonLambda({
      path: 'list_executions',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.getExecutionLambda = this.createPythonLambda({
      path: 'get_execution',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.deleteExecutionLambda = this.createPythonLambda({
      path: 'delete_execution',
      environment: {
        TABLE_NAME: props.table.tableName,
        BUCKET_NAME: props.artefactsBucket.bucketName
      }
    })

    this.getExecutionStepLambda = this.createPythonLambda({
      path: 'get_execution_step',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.listExecutionStepsLambda = this.createPythonLambda({
      path: 'list_execution_steps',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.getExecutionVariablesLambda = this.createPythonLambda({
      path: 'get_execution_variables',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.getLiveViewLambda = this.createPythonLambda({
      path: 'get_live_view',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.updateExecutionStatusLambda = this.createPythonLambda({
      path: 'update_execution_status',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.updateExecutionStepStatusLambda = this.createPythonLambda({
      path: 'update_execution_step_status',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.generateExecutionArtifactUrlLambda = this.createPythonLambda({
      path: 'generate_execution_artifact_url',
      environment: {
        TABLE_NAME: props.table.tableName,
        BUCKET_NAME: props.artefactsBucket.bucketName
      }
    })

    this.generateStepArtifactUrlLambda = this.createPythonLambda({
      path: 'generate_step_artifact_url',
      environment: {
        TABLE_NAME: props.table.tableName,
        BUCKET_NAME: props.artefactsBucket.bucketName
      }
    })

    this.confirmArtifactUploadLambda = this.createPythonLambda({
      path: 'confirm_artifact_upload',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    })

    this.listExecutionArtifactsLambda = this.createPythonLambda({
      path: 'list_execution_artifacts',
      environment: {
        TABLE_NAME: props.table.tableName,
        BUCKET_NAME: props.artefactsBucket.bucketName
      }
    })

    this.generateSuiteArtifactUrlLambda = this.createPythonLambda({
      path: 'generate_suite_artifact_url',
      environment: {
        TABLE_NAME: props.table.tableName,
        BUCKET_NAME: props.artefactsBucket.bucketName
      }
    })

    this.listSuiteArtifactsLambda = this.createPythonLambda({
      path: 'list_suite_artifacts',
      environment: {
        TABLE_NAME: props.table.tableName,
        BUCKET_NAME: props.artefactsBucket.bucketName
      }
    })

    this.getStepTraceLambda = this.createPythonLambda({
      path: 'get_step_trace',
      environment: {
        TABLE_NAME: props.table.tableName,
        BUCKET_NAME: props.artefactsBucket.bucketName
      }
    })

    // Variables, Hooks, Headers Lambdas
    this.createUsecaseVariablesLambda = this.createPythonLambda({
      path: 'create_usecase_variables',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.getUsecaseVariablesLambda = this.createPythonLambda({
      path: 'get_usecase_variables',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.createUsecaseHooksLambda = this.createPythonLambda({
      path: 'create_usecase_hooks',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.getUsercaseHooksLambda = this.createPythonLambda({
      path: 'get_usecase_hooks',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.createUsecaseHeadersLambda = this.createPythonLambda({
      path: 'create_usecase_headers',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.getUsecaseHeadersLambda = this.createPythonLambda({
      path: 'get_usecase_headers',
      environment: { TABLE_NAME: props.table.tableName }
    })

    // Secrets Lambdas
    this.createUsecaseSecretsLambda = this.createPythonLambda({
      path: 'create_usecase_secrets',
      environment: { SECRET_PREFIX: props.baseName }
    })

    this.getUsecaseSecretsLambda = this.createPythonLambda({
      path: 'get_usecase_secrets',
      environment: { SECRET_PREFIX: props.baseName }
    })

    this.getUsecaseSecretValueLambda = this.createPythonLambda({
      path: 'get_usecase_secret_value',
      environment: { SECRET_PREFIX: props.baseName }
    })

    this.deleteUsecaseSecretsLambda = this.createPythonLambda({
      path: 'delete_usecase_secrets',
      environment: { SECRET_PREFIX: props.baseName }
    })

    this.updateUsecaseSecretsLambda = this.createPythonLambda({
      path: 'update_usecase_secrets',
      environment: { SECRET_PREFIX: props.baseName }
    })

    // Recording Lambdas
    this.listRecordingBatchesLambda = this.createPythonLambda({
      path: 'list_recording_batches',
      environment: { BUCKET_NAME: props.artefactsBucket.bucketName }
    })

    this.getRecordingBatchLambda = this.createPythonLambda({
      path: 'get_recording_batch',
      timeout: cdk.Duration.seconds(30),
      memorySize: 1024,
      environment: { BUCKET_NAME: props.artefactsBucket.bucketName }
    })

    this.listDownloadsLambda = this.createPythonLambda({
      path: 'list_downloads',
      environment: { BUCKET_NAME: props.artefactsBucket.bucketName }
    })

    this.downloadFileLambda = this.createPythonLambda({
      path: 'download_file',
      environment: { BUCKET_NAME: props.artefactsBucket.bucketName }
    })

    this.getVideoPlaybackLambda = this.createPythonLambda({
      path: 'get_video_playback',
      environment: {
        TABLE_NAME: props.table.tableName,
        BUCKET_NAME: props.artefactsBucket.bucketName
      }
    })

    // Template Lambdas
    this.createTemplateLambda = this.createPythonLambda({
      path: 'create_template',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.listTemplatesLambda = this.createPythonLambda({
      path: 'list_templates',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.getTemplateLambda = this.createPythonLambda({
      path: 'get_template',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.updateTemplateLambda = this.createPythonLambda({
      path: 'update_template',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.deleteTemplateLambda = this.createPythonLambda({
      path: 'delete_template',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.listTemplateStepsLambda = this.createPythonLambda({
      path: 'list_template_steps',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.createTemplateStepLambda = this.createPythonLambda({
      path: 'create_template_step',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.updateTemplateStepLambda = this.createPythonLambda({
      path: 'update_template_step',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.deleteTemplateStepLambda = this.createPythonLambda({
      path: 'delete_template_step',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.reorderTemplateStepsLambda = this.createPythonLambda({
      path: 'reorder_template_steps',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.createTemplateVariablesLambda = this.createPythonLambda({
      path: 'create_template_variables',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.getTemplateVariablesLambda = this.createPythonLambda({
      path: 'get_template_variables',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.applyTemplateLambda = this.createPythonLambda({
      path: 'apply_template',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.importTemplateLambda = this.createPythonLambda({
      path: 'import_template',
      timeout: cdk.Duration.seconds(30),
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.checkTemplateUpdatesLambda = this.createPythonLambda({
      path: 'check_template_updates',
      environment: { TABLE_NAME: props.table.tableName }
    })

    this.updateStepFromTemplateLambda = this.createPythonLambda({
      path: 'update_step_from_template',
      environment: { TABLE_NAME: props.table.tableName }
    })

    // Utility Lambdas
    this.listModelsLambda = this.createPythonLambda({ path: 'list_models' })
    this.listDeviceFarmDevicesLambda = this.createPythonLambda({ path: 'list_device_farm_devices' })

    this.requestRecordingDownloadLambda = this.createPythonLambda({
      path: 'request_recording_download',
      environment: {
        RECORDING_QUEUE_URL: props.recordingQueueUrl,
      }
    })

    // Notification Lambdas (API-facing only)
    this.getUsecaseSubscriptionLambda = this.createPythonLambda({
      path: 'get_usecase_subscription',
      environment: {
        TABLE_NAME: props.table.tableName,
      }
    })

    this.subscribeUsecaseLambda = this.createPythonLambda({
      path: 'subscribe_usecase',
      environment: {
        TABLE_NAME: props.table.tableName,
        SNS_TOPIC_ARN: props.notificationTopicArn
      }
    })

    this.unsubscribeUsecaseLambda = this.createPythonLambda({
      path: 'unsubscribe_usecase',
      environment: {
        TABLE_NAME: props.table.tableName,
        SNS_TOPIC_ARN: props.notificationTopicArn
      }
    })

    // ========== User Management Lambdas ==========

    this.listUsersLambda = this.createPythonLambda({
      path: 'list_users',
      environment: {
        USER_POOL_ID: props.userPool.userPoolId
      }
    });

    this.addUserLambda = this.createPythonLambda({
      path: 'create_user',
      environment: {
        USER_POOL_ID: props.userPool.userPoolId
      }
    });

    this.removeUserLambda = this.createPythonLambda({
      path: 'delete_user',
      environment: {
        USER_POOL_ID: props.userPool.userPoolId
      }
    });

    // Grant Cognito permissions for user management
    this.listUsersLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:ListUsers'
      ],
      resources: [props.userPool.userPoolArn]
    }));

    this.addUserLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:AdminCreateUser',
        'cognito-idp:AdminSetUserPassword',
        'cognito-idp:AdminUpdateUserAttributes',
        'cognito-idp:AdminGetUser',
        'cognito-idp:AdminAddUserToGroup'
      ],
      resources: [props.userPool.userPoolArn]
    }));

    this.removeUserLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:AdminDeleteUser'
      ],
      resources: [props.userPool.userPoolArn]
    }));

    this.getUserLambda = this.createPythonLambda({
      path: 'get_user',
      environment: {
        USER_POOL_ID: props.userPool.userPoolId
      }
    });

    this.getUserLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:AdminGetUser',
        'cognito-idp:AdminListGroupsForUser'
      ],
      resources: [props.userPool.userPoolArn]
    }));

    this.updateUserGroupsLambda = this.createPythonLambda({
      path: 'update_user_groups',
      environment: {
        USER_POOL_ID: props.userPool.userPoolId
      }
    });

    this.updateUserGroupsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:AdminGetUser',
        'cognito-idp:AdminListGroupsForUser',
        'cognito-idp:AdminAddUserToGroup',
        'cognito-idp:AdminRemoveUserFromGroup'
      ],
      resources: [props.userPool.userPoolArn]
    }));

    // Update listUsersLambda to include group listing permission
    this.listUsersLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:AdminListGroupsForUser'
      ],
      resources: [props.userPool.userPoolArn]
    }));

    // OAuth Client Management Lambdas
    this.createOAuthClientLambda = this.createPythonLambda({
      path: 'create_oauth_client',
      environment: {
        USER_POOL_ID: props.userPool.userPoolId,
        RESOURCE_SERVER_IDENTIFIER: 'api',
        TABLE_NAME: props.table.tableName
      }
    });

    this.listOAuthClientsLambda = this.createPythonLambda({
      path: 'list_oauth_clients',
      environment: {
        USER_POOL_ID: props.userPool.userPoolId,
        TABLE_NAME: props.table.tableName
      }
    });

    this.deleteOAuthClientLambda = this.createPythonLambda({
      path: 'delete_oauth_client',
      environment: {
        USER_POOL_ID: props.userPool.userPoolId,
        TABLE_NAME: props.table.tableName
      }
    });

    this.rotateClientSecretLambda = this.createPythonLambda({
      path: 'rotate_client_secret',
      environment: {
        USER_POOL_ID: props.userPool.userPoolId,
        TABLE_NAME: props.table.tableName
      }
    });

    this.listScopesLambda = this.createPythonLambda({
      path: 'list_scopes',
      environment: {
        USER_POOL_ID: props.userPool.userPoolId,
        RESOURCE_SERVER_IDENTIFIER: 'api'
      }
    });

    // Grant Cognito permissions for OAuth client management
    this.createOAuthClientLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:CreateUserPoolClient',
        'cognito-idp:DescribeResourceServer'
      ],
      resources: [props.userPool.userPoolArn]
    }));

    this.listOAuthClientsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:ListUserPoolClients',
        'cognito-idp:DescribeUserPoolClient'
      ],
      resources: [props.userPool.userPoolArn]
    }));

    this.deleteOAuthClientLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:DeleteUserPoolClient'
      ],
      resources: [props.userPool.userPoolArn]
    }));

    this.rotateClientSecretLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:DescribeUserPoolClient',
        'cognito-idp:DeleteUserPoolClient',
        'cognito-idp:CreateUserPoolClient'
      ],
      resources: [props.userPool.userPoolArn]
    }));

    this.listScopesLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:DescribeResourceServer'
      ],
      resources: [props.userPool.userPoolArn]
    }));

    // Grant DynamoDB permissions for OAuth client metadata
    this.createOAuthClientLambda.role?.addManagedPolicy(props.tableWritePolicy);
    this.listOAuthClientsLambda.role?.addManagedPolicy(props.tableReadPolicy);
    // Delete needs read (to check created_by), write, and delete permissions
    this.deleteOAuthClientLambda.role?.addManagedPolicy(props.tableFullAccessPolicy);
    // Rotate needs read (to check created_by), write (to update metadata), and delete (to remove old metadata)
    this.rotateClientSecretLambda.role?.addManagedPolicy(props.tableFullAccessPolicy);

    // ========== Test Suite Management Lambdas ==========

    this.createTestSuiteLambda = this.createPythonLambda({
      path: 'create_test_suite',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    this.listTestSuitesLambda = this.createPythonLambda({
      path: 'list_test_suites',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    this.getTestSuiteLambda = this.createPythonLambda({
      path: 'get_test_suite',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    this.updateTestSuiteLambda = this.createPythonLambda({
      path: 'update_test_suite',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    this.deleteTestSuiteLambda = this.createPythonLambda({
      path: 'delete_test_suite',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    this.addUsecasesToSuiteLambda = this.createPythonLambda({
      path: 'add_usecases_to_suite',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    this.listSuiteUsecasesLambda = this.createPythonLambda({
      path: 'list_suite_usecases',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    this.removeUsecaseFromSuiteLambda = this.createPythonLambda({
      path: 'remove_usecase_from_suite',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    this.executeTestSuiteLambda = this.createPythonLambda({
      path: 'execute_test_suite',
      timeout: cdk.Duration.seconds(300), // 5 minutes for large suites
      memorySize: 512,
      environment: {
        TABLE_NAME: props.table.tableName,
        DEFAULT_REGION: this.region,
        EXECUTE_USECASE_LAMBDA_ARN: props.executeUsecaseLambda.functionArn
      }
    });

    this.listSuiteExecutionsLambda = this.createPythonLambda({
      path: 'list_suite_executions',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    this.getSuiteExecutionLambda = this.createPythonLambda({
      path: 'get_suite_execution',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    this.stopSuiteExecutionLambda = this.createPythonLambda({
      path: 'stop_suite_execution',
      environment: {
        TABLE_NAME: props.table.tableName,
        ECS_CLUSTER: props.ecsClusterArn
      }
    });

    this.updateSuiteExecutionStatusLambda = this.createPythonLambda({
      path: 'update_suite_execution_status',
      environment: {
        TABLE_NAME: props.table.tableName
      }
    });

    this.updateSuiteScheduleLambda = this.createPythonLambda({
      path: 'update_suite_schedule',
      environment: {
        TABLE_NAME: props.table.tableName,
        BASE_NAME: props.baseName,
        EXECUTE_SUITE_LAMBDA_ARN: this.executeTestSuiteLambda.functionArn
      }
    });

    // ========== Worker-related Lambdas ==========

    this.generateS3UrlLambda = this.createPythonLambda({
      path: 'generate_s3_url',
      environment: {
        BUCKET_NAME: props.artefactsBucket.bucketName,
        TABLE_NAME: props.table.tableName
      }
    });

    this.generateS3UrlLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.generateS3UrlLambda.role?.addManagedPolicy(props.tableWritePolicy)
    props.artefactsBucket.grantReadWrite(this.generateS3UrlLambda)

    this.acceptWizardStepLambda = this.createPythonLambda({
      path: 'accept_wizard_step',
      environment: {
        TABLE_NAME: props.table.tableName,
      }
    });

    props.table.grantReadWriteData(this.acceptWizardStepLambda);

    this.rejectWizardStepLambda = this.createPythonLambda({
      path: 'reject_wizard_step',
      environment: {
        TABLE_NAME: props.table.tableName,
      }
    });

    props.table.grantReadWriteData(this.rejectWizardStepLambda);

    this.getScheduleLambda = this.createPythonLambda({
      path: 'get_schedule',
      environment: {
        SCHEDULER_GROUP_NAME: props.schedulerGroupName
      }
    });

    this.getScheduleLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['scheduler:GetSchedule'],
      resources: [
        `arn:aws:scheduler:${Aws.REGION}:${Aws.ACCOUNT_ID}:schedule/${props.schedulerGroupName}/*`
      ]
    }));

    this.deleteScheduleLambda = this.createPythonLambda({
      path: 'delete_schedule',
      environment: {
        SCHEDULER_GROUP_NAME: props.schedulerGroupName
      }
    });

    this.deleteScheduleLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['scheduler:DeleteSchedule'],
      resources: [
        `arn:aws:scheduler:${Aws.REGION}:${Aws.ACCOUNT_ID}:schedule/${props.schedulerGroupName}/*`
      ]
    }));

    // ========== Browser Recording Lambdas ==========

    this.sendRecordingCommandLambda = this.createPythonLambda({
      path: 'send_recording_command',
      environment: {
        TABLE_NAME: props.table.tableName,
        WIZARD_EVENT_BUS_NAME: props.wizardEventBusName,
      }
    });

    this.getRecordingDataLambda = this.createPythonLambda({
      path: 'get_recording_data',
      environment: {
        TABLE_NAME: props.table.tableName,
        BUCKET_NAME: props.artefactsBucket.bucketName,
      }
    });

    // ========== IAM Permissions ==========

    // Table Read Permissions
    const readLambdas = [
      this.listUsecasesLambda,
      this.getUsecaseLambda,
      this.listStepsLambda,
      this.listExecutionsLambda,
      this.getExecutionStepLambda,
      this.getExecutionLambda,
      this.listExecutionStepsLambda,
      this.getUsecaseVariablesLambda,
      this.getUsercaseHooksLambda,
      this.getExecutionVariablesLambda,
      this.getLiveViewLambda,
      this.exportUsecaseLambda,
      this.generateUsecaseLambda,
      this.getUsecaseHeadersLambda,
      this.listTemplatesLambda,
      this.getTemplateLambda,
      this.listTemplateStepsLambda,
      this.getTemplateVariablesLambda,
      this.checkTemplateUpdatesLambda,
      this.listTestSuitesLambda,
      this.getTestSuiteLambda,
      this.listSuiteUsecasesLambda,
      this.listSuiteExecutionsLambda,
      this.getSuiteExecutionLambda,
      this.executeTestSuiteLambda,
      this.getVideoPlaybackLambda,
      this.generateSuiteArtifactUrlLambda,
      this.listSuiteArtifactsLambda,
      this.listExecutionArtifactsLambda,
      this.getStepTraceLambda,
      this.getRecordingDataLambda
    ]
    readLambdas.forEach(lambda => lambda.role?.addManagedPolicy(props.tableReadPolicy))

    // Table Write Permissions
    const writeLambdas = [
      this.createStepLambda,
      this.updateStepLambda,
      this.reorderStepsLambda,
      this.createUsecaseLambda,
      this.updateUsecaseLambda,
      this.importUsecaseLambda,
      this.createUsecaseHooksLambda,
      this.createUsecaseHeadersLambda,
      this.createUsecaseVariablesLambda,
      this.createTemplateLambda,
      this.updateTemplateLambda,
      this.createTemplateStepLambda,
      this.updateTemplateStepLambda,
      this.reorderTemplateStepsLambda,
      this.createTemplateVariablesLambda,
      this.createTestSuiteLambda,
      this.removeUsecaseFromSuiteLambda,
      this.updateSuiteScheduleLambda,
      this.executeTestSuiteLambda,
      this.stopSuiteExecutionLambda,
      this.updateSuiteExecutionStatusLambda,
      this.sendRecordingCommandLambda
    ]
    writeLambdas.forEach(lambda => lambda.role?.addManagedPolicy(props.tableWritePolicy))

    // Table Full Access Permissions
    const fullAccessLambdas = [
      this.deleteUsecaseLambda,
      this.deleteExecutionLambda,
      this.deleteStepLambda,
      this.deleteTemplateLambda,
      this.deleteTemplateStepLambda,
      this.cloneUsecaseLambda,
      this.deleteTestSuiteLambda
    ]
    fullAccessLambdas.forEach(lambda => lambda.role?.addManagedPolicy(props.tableFullAccessPolicy))

    // Lambdas that need both read and write
    this.importTemplateLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.importTemplateLambda.role?.addManagedPolicy(props.tableWritePolicy)
    this.applyTemplateLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.removeUsecaseFromSuiteLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.applyTemplateLambda.role?.addManagedPolicy(props.tableWritePolicy)
    this.updateStepFromTemplateLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.updateStepFromTemplateLambda.role?.addManagedPolicy(props.tableWritePolicy)
    this.addUsecasesToSuiteLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.addUsecasesToSuiteLambda.role?.addManagedPolicy(props.tableWritePolicy)
    this.updateTestSuiteLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.updateTestSuiteLambda.role?.addManagedPolicy(props.tableWritePolicy)
    this.updateSuiteExecutionStatusLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.updateSuiteExecutionStatusLambda.role?.addManagedPolicy(props.tableWritePolicy)
    this.updateExecutionStatusLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.updateExecutionStatusLambda.role?.addManagedPolicy(props.tableWritePolicy)
    this.updateExecutionStepStatusLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.updateExecutionStepStatusLambda.role?.addManagedPolicy(props.tableWritePolicy)
    this.generateExecutionArtifactUrlLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.generateExecutionArtifactUrlLambda.role?.addManagedPolicy(props.tableWritePolicy)
    this.generateStepArtifactUrlLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.generateStepArtifactUrlLambda.role?.addManagedPolicy(props.tableWritePolicy)
    this.confirmArtifactUploadLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.confirmArtifactUploadLambda.role?.addManagedPolicy(props.tableWritePolicy)

    // S3 Bucket Permissions
    props.artefactsBucket.grantRead(this.listRecordingBatchesLambda)
    props.artefactsBucket.grantRead(this.getRecordingBatchLambda)
    props.artefactsBucket.grantPut(this.generateExecutionArtifactUrlLambda)
    props.artefactsBucket.grantPut(this.generateStepArtifactUrlLambda)
    props.artefactsBucket.grantRead(this.listDownloadsLambda)
    props.artefactsBucket.grantRead(this.downloadFileLambda)
    props.artefactsBucket.grantRead(this.getVideoPlaybackLambda)
    props.artefactsBucket.grantDelete(this.deleteExecutionLambda)
    props.artefactsBucket.grantRead(this.deleteExecutionLambda)
    props.artefactsBucket.grantPut(this.generateSuiteArtifactUrlLambda)
    props.artefactsBucket.grantRead(this.listSuiteArtifactsLambda)
    props.artefactsBucket.grantRead(this.listExecutionArtifactsLambda)
    props.artefactsBucket.grantRead(this.getStepTraceLambda)
    props.artefactsBucket.grantRead(this.getRecordingDataLambda)
    props.artefactsBucket.grantRead(this.generateUsecaseLambda)

    // Nova Act Permissions
    const novaActArn = `arn:aws:nova-act:${Aws.REGION}:${Aws.ACCOUNT_ID}:*`;
    
    this.deleteUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['nova-act:DeleteWorkflowDefinition', 'nova-act:GetWorkflowDefinition'],
      resources: [novaActArn]
    }))

    // ListModels is a list operation that requires * for resource
    this.listModelsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['nova-act:ListModels'],
      resources: ['*']
    }))

    // Device Farm ListDevices permission (Device Farm only in us-west-2)
    this.listDeviceFarmDevicesLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['devicefarm:ListDevices'],
      resources: ['*']
    }))

    // Recording download request — SQS send permission (scoped to recording queue)
    this.requestRecordingDownloadLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['sqs:SendMessage'],
      resources: [props.recordingQueueArn]
    }))

    // Secrets Manager Permissions
    // Note: Secrets Manager ARNs have a 6-character random suffix, so we use a wildcard pattern
    const secretsArnPattern = `arn:aws:secretsmanager:${Aws.REGION}:${Aws.ACCOUNT_ID}:secret:${props.baseName}*`;
    
    // CreateSecret requires * for resource (ARN unknown before creation), scoped to account
    this.createUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:CreateSecret', 'secretsmanager:TagResource'],
      resources: [`arn:aws:secretsmanager:${Aws.REGION}:${Aws.ACCOUNT_ID}:secret:*`]
    }))
    
    this.createUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:UpdateSecret'],
      resources: [secretsArnPattern]
    }))

    // ListSecrets requires * for resource (list operation), scoped to account
    this.getUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:ListSecrets'],
      resources: [`arn:aws:secretsmanager:${Aws.REGION}:${Aws.ACCOUNT_ID}:secret:*`]
    }))
    
    this.getUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:DescribeSecret'],
      resources: [secretsArnPattern]
    }))

    this.getUsecaseSecretValueLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:GetSecretValue'],
      resources: [secretsArnPattern]
    }))

    this.deleteUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:DeleteSecret'],
      resources: [secretsArnPattern]
    }))

    this.updateUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:UpdateSecret'],
      resources: [secretsArnPattern]
    }))

    // ListSecrets and CreateSecret require * for resource, scoped to account
    this.cloneUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:ListSecrets', 'secretsmanager:CreateSecret', 'secretsmanager:TagResource'],
      resources: [`arn:aws:secretsmanager:${Aws.REGION}:${Aws.ACCOUNT_ID}:secret:*`]
    }))

    // ListSecrets requires * for resource, scoped to account
    this.exportUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:ListSecrets'],
      resources: [`arn:aws:secretsmanager:${Aws.REGION}:${Aws.ACCOUNT_ID}:secret:*`]
    }))
    
    this.exportUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:DescribeSecret'],
      resources: [secretsArnPattern]
    }))

    // EventBridge permissions for execute_test_suite Lambda
    this.executeTestSuiteLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['events:PutEvents'],
      resources: [`arn:aws:events:${Aws.REGION}:${Aws.ACCOUNT_ID}:event-bus/default`]
    }))

    // EventBridge permissions for update_execution_status Lambda
    this.updateExecutionStatusLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['events:PutEvents'],
      resources: [`arn:aws:events:${Aws.REGION}:${Aws.ACCOUNT_ID}:event-bus/default`]
    }))

    // EventBridge permissions for send_recording_command Lambda (wizard event bus)
    this.sendRecordingCommandLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['events:PutEvents'],
      resources: [`arn:aws:events:${Aws.REGION}:${Aws.ACCOUNT_ID}:event-bus/${props.wizardEventBusName}`]
    }))

    // CloudWatch metrics permissions for execute_test_suite Lambda
    this.executeTestSuiteLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['cloudwatch:PutMetricData'],
      resources: ['*']
    }))

    // CreateSecret requires * for resource, scoped to account
    this.importUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:CreateSecret', 'secretsmanager:TagResource'],
      resources: [`arn:aws:secretsmanager:${Aws.REGION}:${Aws.ACCOUNT_ID}:secret:*`]
    }))
    
    this.importUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:UpdateSecret'],
      resources: [secretsArnPattern]
    }))

    // Bedrock Permissions (wildcard region for cross-region inference profiles)
    this.generateUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
      resources: [
        `arn:aws:bedrock:*::foundation-model/*`,
        `arn:aws:bedrock:*:${Aws.ACCOUNT_ID}:inference-profile/*`,
      ]
    }))

    // Notification Lambda Permissions (API-facing only)
    this.getUsecaseSubscriptionLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.subscribeUsecaseLambda.role?.addManagedPolicy(props.tableWritePolicy)
    this.unsubscribeUsecaseLambda.role?.addManagedPolicy(props.tableFullAccessPolicy)

    // SNS permissions for notification Lambdas
    // Topic-level actions
    this.subscribeUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'sns:Subscribe',
        'sns:ListSubscriptionsByTopic',
      ],
      resources: [props.notificationTopicArn]
    }))
    
    // Subscription-level actions (subscriptions have different ARN format)
    this.subscribeUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'sns:GetSubscriptionAttributes',
        'sns:SetSubscriptionAttributes'
      ],
      resources: [`arn:aws:sns:${Aws.REGION}:${Aws.ACCOUNT_ID}:*`]
    }))

    // Topic-level actions
    this.unsubscribeUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'sns:ListSubscriptionsByTopic',
      ],
      resources: [props.notificationTopicArn]
    }))
    
    // Subscription-level actions (subscriptions have different ARN format)
    this.unsubscribeUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'sns:GetSubscriptionAttributes',
        'sns:SetSubscriptionAttributes',
        'sns:Unsubscribe'
      ],
      resources: [`arn:aws:sns:${Aws.REGION}:${Aws.ACCOUNT_ID}:*`]
    }))

    // ========== Test Suite Execution Permissions ==========

    // Grant execute_suite Lambda permission to invoke execute_usecase Lambda
    props.executeUsecaseLambda.grantInvoke(this.executeTestSuiteLambda);

    // Grant stop_suite_execution Lambda permission to stop ECS tasks
    this.stopSuiteExecutionLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['ecs:StopTask'],
      resources: [`arn:aws:ecs:${Aws.REGION}:${Aws.ACCOUNT_ID}:task/*`],
      conditions: {
        'ArnEquals': {
          'ecs:cluster': props.ecsClusterArn
        }
      }
    }));

    // Grant update_suite_schedule Lambda permission to manage EventBridge rules
    this.updateSuiteScheduleLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'events:PutRule',
        'events:PutTargets',
        'events:EnableRule',
        'events:DisableRule'
      ],
      resources: [
        `arn:aws:events:${Aws.REGION}:${Aws.ACCOUNT_ID}:rule/${props.baseName}-suite-*`
      ]
    }));

    // Grant update_suite_schedule Lambda permission to add Lambda targets to EventBridge rules
    this.updateSuiteScheduleLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['lambda:AddPermission', 'lambda:RemovePermission'],
      resources: [this.executeTestSuiteLambda.functionArn]
    }));

    // Grant EventBridge permission to invoke execute_suite Lambda
    // This allows EventBridge rules with the naming pattern {baseName}-suite-{suite_id} to trigger the Lambda
    this.executeTestSuiteLambda.addPermission('EventBridgeInvoke', {
      principal: new cdk.aws_iam.ServicePrincipal('events.amazonaws.com'),
      sourceArn: `arn:aws:events:${Aws.REGION}:${Aws.ACCOUNT_ID}:rule/${props.baseName}-suite-*`
    });
  }
}
