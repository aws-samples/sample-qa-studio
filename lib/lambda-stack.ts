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
  public readonly deleteUsecaseSecretsLambda: Function
  public readonly updateUsecaseSecretsLambda: Function

  // Recording Lambdas
  public readonly listRecordingBatchesLambda: Function
  public readonly getRecordingBatchLambda: Function
  public readonly listDownloadsLambda: Function
  public readonly downloadFileLambda: Function

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

  // Worker-related Lambdas (moved from worker stack)
  public readonly generateS3UrlLambda: Function
  public readonly acceptWizardStepLambda: Function
  public readonly getScheduleLambda: Function
  public readonly deleteScheduleLambda: Function

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
      timeout: cdk.Duration.seconds(60),
      environment: {
        TABLE_NAME: props.table.tableName,
        BEDROCK_MODEL_ID: props.bedrockModelId || 'anthropic.claude-3-5-sonnet-20240620-v1:0'
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

    // Grant Cognito permissions for OAuth client management
    this.createOAuthClientLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:CreateUserPoolClient'
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

    // Grant DynamoDB permissions for OAuth client metadata
    this.createOAuthClientLambda.role?.addManagedPolicy(props.tableWritePolicy);
    this.listOAuthClientsLambda.role?.addManagedPolicy(props.tableReadPolicy);
    // Delete needs read (to check created_by), write, and delete permissions
    this.deleteOAuthClientLambda.role?.addManagedPolicy(props.tableFullAccessPolicy);

    // ========== Worker-related Lambdas ==========

    this.generateS3UrlLambda = this.createPythonLambda({
      path: 'generate_s3_url',
      environment: {
        BUCKET_NAME: props.artefactsBucket.bucketName,
        TABLE_NAME: props.table.tableName
      }
    });

    this.generateS3UrlLambda.role?.addManagedPolicy(props.tableReadPolicy)
    props.artefactsBucket.grantRead(this.generateS3UrlLambda)

    this.acceptWizardStepLambda = this.createPythonLambda({
      path: 'accept_wizard_step',
      environment: {
        TABLE_NAME: props.table.tableName,
      }
    });

    props.table.grantFullAccess(this.acceptWizardStepLambda);

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
      this.checkTemplateUpdatesLambda
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
      this.createTemplateVariablesLambda
    ]
    writeLambdas.forEach(lambda => lambda.role?.addManagedPolicy(props.tableWritePolicy))

    // Table Full Access Permissions
    const fullAccessLambdas = [
      this.deleteUsecaseLambda,
      this.deleteExecutionLambda,
      this.deleteStepLambda,
      this.deleteTemplateLambda,
      this.deleteTemplateStepLambda,
      this.cloneUsecaseLambda
    ]
    fullAccessLambdas.forEach(lambda => lambda.role?.addManagedPolicy(props.tableFullAccessPolicy))

    // Lambdas that need both read and write
    this.importTemplateLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.importTemplateLambda.role?.addManagedPolicy(props.tableWritePolicy)
    this.applyTemplateLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.applyTemplateLambda.role?.addManagedPolicy(props.tableWritePolicy)
    this.updateStepFromTemplateLambda.role?.addManagedPolicy(props.tableReadPolicy)
    this.updateStepFromTemplateLambda.role?.addManagedPolicy(props.tableWritePolicy)

    // S3 Bucket Permissions
    props.artefactsBucket.grantRead(this.listRecordingBatchesLambda)
    props.artefactsBucket.grantRead(this.getRecordingBatchLambda)
    props.artefactsBucket.grantRead(this.listDownloadsLambda)
    props.artefactsBucket.grantRead(this.downloadFileLambda)
    props.artefactsBucket.grantDelete(this.deleteExecutionLambda)
    props.artefactsBucket.grantRead(this.deleteExecutionLambda)

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

    // Secrets Manager Permissions
    // Note: Secrets Manager ARNs have a 6-character random suffix, so we use a wildcard pattern
    const secretsArnPattern = `arn:aws:secretsmanager:${Aws.REGION}:${Aws.ACCOUNT_ID}:secret:${props.baseName}*`;
    
    // CreateSecret requires * for resource
    this.createUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:CreateSecret', 'secretsmanager:TagResource'],
      resources: ['*']
    }))
    
    this.createUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:UpdateSecret'],
      resources: [secretsArnPattern]
    }))

    // ListSecrets requires * for resource
    this.getUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:ListSecrets'],
      resources: ['*']
    }))
    
    this.getUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:DescribeSecret'],
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

    // ListSecrets and CreateSecret require * for resource
    this.cloneUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:ListSecrets', 'secretsmanager:CreateSecret', 'secretsmanager:TagResource'],
      resources: ['*']
    }))

    // ListSecrets requires * for resource
    this.exportUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:ListSecrets'],
      resources: ['*']
    }))
    
    this.exportUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:DescribeSecret'],
      resources: [secretsArnPattern]
    }))

    // CreateSecret requires * for resource
    this.importUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:CreateSecret', 'secretsmanager:TagResource'],
      resources: ['*']
    }))
    
    this.importUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['secretsmanager:UpdateSecret'],
      resources: [secretsArnPattern]
    }))

    // Bedrock Permissions
    const bedrockArn = `arn:aws:bedrock:${Aws.REGION}::foundation-model/*`;
    
    this.generateUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
      resources: [bedrockArn]
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
      resources: ['*']
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
      resources: ['*']
    }))
  }
}
