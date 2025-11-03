import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { RestApi, LambdaIntegration, AuthorizationType, Method, Resource, IAuthorizer, Cors, IResource, Deployment, Stage } from 'aws-cdk-lib/aws-apigateway';
import { Function } from 'aws-cdk-lib/aws-lambda';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { Table } from 'aws-cdk-lib/aws-dynamodb';
import { PolicyStatement, Effect, ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';

interface NovaActQAStudioRouteStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  apiId: string
  apiDeploymentStage: string
  apiRootResourceId: string
  artefactsBucket: Bucket
  table: Table
  tableReadPolicy: ManagedPolicy,
  tableWritePolicy: ManagedPolicy,
  tableFullAccessPolicy: ManagedPolicy
  addUserLambda: Function,
  listUsersLambda: Function,
  removeUserLambda: Function,
  authorizer: IAuthorizer,
  createScheduleLambda: Function,
  deleteScheduleLambda: Function,
  getScheduleLambda: Function,
  executeUsecaseLambda: Function,
  subscribeUsecaseLambda: Function,
  unsubscribeUsecaseLambda: Function,
  getUsecaseSubscriptionLambda: Function,
  generateS3UrlLambda: Function
}

enum HttpMethod {
  GET = 'GET',
  POST = 'POST',
  PUT = 'PUT',
  DELETE = 'DELETE',
  PATCH = 'PATCH',
}

export class NovaActQAStudioRouteStack extends NovaActQAStudioBaseStack {
  private authorizer: IAuthorizer
  private table: Table
  private deployment: Deployment
  private routes: Method[] = []

  private addMethod(resource: Resource, method: HttpMethod, lambda: Function): Method {
    const resourceMethod = resource.addMethod(method, new LambdaIntegration(lambda), {
      authorizer: this.authorizer,
      authorizationType: AuthorizationType.COGNITO
    });

    this.routes.push(resourceMethod)

    return resourceMethod
  }

  private addResource(parentResource: IResource, name: string): Resource {
    const resource = parentResource.addResource(name);

    resource.addCorsPreflight({
      allowOrigins: Cors.ALL_ORIGINS,
      allowMethods: Cors.ALL_METHODS,
      allowHeaders: ['Content-Type', 'Authorization', 'X-Amz-Date', 'X-Api-Key', 'X-Amz-Security-Token']
    })

    return resource
  }

  private defaultCreateLambdaWithTable(path: string): Function {
    return this.createLambda({
      path: path,
      environment: {
        TABLE_NAME: this.table.tableName
      }
    });
  }

  constructor(scope: Construct, id: string, props: NovaActQAStudioRouteStackCreateProps) {
    super(scope, id, props);
    this.authorizer = props.authorizer
    this.table = props.table

    const apiInstance = RestApi.fromRestApiAttributes(this, 'api_instance', {
      restApiId: props.apiId,
      rootResourceId: props.apiRootResourceId
    })

    // Lambda Functions
    const listUsecasesLambda = this.defaultCreateLambdaWithTable('list_usecases')
    const createUsecaseLambda = this.defaultCreateLambdaWithTable('create_usecase')
    const getUsecaseLambda = this.defaultCreateLambdaWithTable('get_usecase')
    const createStepLambda = this.defaultCreateLambdaWithTable('create_step')
    const listStepsLambda = this.defaultCreateLambdaWithTable('list_steps')
    const updateStepLambda = this.defaultCreateLambdaWithTable('update_step')
    const deleteStepLambda = this.defaultCreateLambdaWithTable('delete_step')
    const updateUsecaseLambda = this.defaultCreateLambdaWithTable('update_usecase')
    const listExecutionsLambda = this.defaultCreateLambdaWithTable('list_executions')
    const deleteUsecaseLambda = this.defaultCreateLambdaWithTable('delete_usecase')
    const deleteExecutionLambda = this.defaultCreateLambdaWithTable('delete_execution')
    const updateExecutionStepLambda = this.defaultCreateLambdaWithTable('update_execution_step')
    const getExecutionStepLambda = this.defaultCreateLambdaWithTable('get_execution_step')
    const getExecutionLambda = this.defaultCreateLambdaWithTable('get_execution')
    const listExecutionStepsLambda = this.defaultCreateLambdaWithTable('list_execution_steps')
    const createUsecaseVariablesLambda = this.defaultCreateLambdaWithTable('create_usecase_variables')
    const getUsecaseVariablesLambda = this.defaultCreateLambdaWithTable('get_usecase_variables')
    const createUsecaseHooksLambda = this.defaultCreateLambdaWithTable('create_usecase_hooks')
    const getUsercaseHooksLambda = this.defaultCreateLambdaWithTable('get_usecase_hooks')
    const createUsecaseHeadersLambda = this.defaultCreateLambdaWithTable('create_usecase_headers')
    const getUsecaseHeadersLambda = this.defaultCreateLambdaWithTable('get_usecase_headers')
    const reorderStepsLambda = this.defaultCreateLambdaWithTable('reorder_steps')
    const getExecutionVariablesLambda = this.defaultCreateLambdaWithTable('get_execution_variables')
    const getLiveViewLambda = this.defaultCreateLambdaWithTable('get_live_view')

    const createUsecaseSecretsLambda = this.createLambda({
      path: 'create_usecase_secrets',
      environment: {
        SECRET_PREFIX: props.baseName
      }
    });

    const getUsecaseSecretsLambda = this.createLambda({
      path: 'get_usecase_secrets',
      environment: {
        SECRET_PREFIX: props.baseName
      }
    });

    const deleteUsecaseSecretsLambda = this.createLambda({
      path: 'delete_usecase_secrets',
      environment: {
        SECRET_PREFIX: props.baseName
      }
    });

    const updateUsecaseSecretsLambda = this.createLambda({
      path: 'update_usecase_secrets',
      environment: {
        SECRET_PREFIX: props.baseName
      }
    });

    const exportUsecaseLambda = this.createLambda({
      memorySize: 256,
      path: 'export_usecase',
      timeout: cdk.Duration.seconds(30),
      environment: {
        TABLE_NAME: props.table.tableName,
      }
    });

    const importUsecaseLambda = this.createLambda({
      memorySize: 256,
      path: 'import_usecase',
      timeout: cdk.Duration.seconds(30),
      environment: {
        TABLE_NAME: props.table.tableName,
      }
    });

    const generateUsecaseLambda = this.createLambda({
      memorySize: 512,
      path: 'generate_usecase',
      timeout: cdk.Duration.seconds(60),
      environment: {
        TABLE_NAME: props.table.tableName,
        BEDROCK_MODEL_ID: 'eu.anthropic.claude-sonnet-4-20250514-v1:0',
        // BEDROCK_MODEL_ID: 'eu.amazon.nova-pro-v1:0',
        BEDROCK_REGION: 'eu-central-1'
      }
    });

    // Lambda for listing recording batches
    const listRecordingBatchesLambda = this.createLambda({
      path: 'list_recording_batches',
      environment: {
        BUCKET_NAME: props.artefactsBucket.bucketName,
        TABLE_NAME: props.table.tableName
      }
    });

    props.artefactsBucket.grantRead(listRecordingBatchesLambda)

    // Lambda for getting a specific recording batch
    const getRecordingBatchLambda = this.createLambda({
      path: 'get_recording_batch',
      timeout: cdk.Duration.seconds(30),
      memorySize: 1024,
      environment: {
        BUCKET_NAME: props.artefactsBucket.bucketName,
        TABLE_NAME: props.table.tableName
      }
    });

    props.artefactsBucket.grantRead(getRecordingBatchLambda);

    [listUsecasesLambda,
      getUsecaseLambda,
      listStepsLambda,
      listExecutionsLambda,
      getExecutionStepLambda,
      getExecutionLambda,
      listExecutionStepsLambda,
      getUsecaseVariablesLambda,
      getUsercaseHooksLambda,
      getExecutionVariablesLambda,
      getLiveViewLambda,
      exportUsecaseLambda,
      generateUsecaseLambda,
      getUsecaseHeadersLambda,
      props.getUsecaseSubscriptionLambda].forEach((lambda: Function) => {
        lambda.role?.addManagedPolicy(props.tableReadPolicy);
      });

    [createStepLambda,
      updateStepLambda,
      deleteStepLambda,
      reorderStepsLambda,
      createUsecaseLambda,
      updateUsecaseLambda,
      importUsecaseLambda,
      createUsecaseHooksLambda,
      updateExecutionStepLambda,
      createUsecaseHeadersLambda,
      createUsecaseVariablesLambda,
      props.subscribeUsecaseLambda].forEach((lambda: Function) => {
        lambda.role?.addManagedPolicy(props.tableWritePolicy);
      });

    [deleteUsecaseLambda,
      deleteExecutionLambda,
      deleteStepLambda,
      props.unsubscribeUsecaseLambda].forEach((lambda: Function) => {
        lambda.role?.addManagedPolicy(props.tableFullAccessPolicy);
      });

    // Grant Secrets Manager permissions
    createUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'secretsmanager:CreateSecret',
        'secretsmanager:UpdateSecret',
        'secretsmanager:TagResource'
      ],
      resources: ['*']
    }));

    getUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'secretsmanager:ListSecrets',
        'secretsmanager:DescribeSecret'
      ],
      resources: ['*']
    }));

    deleteUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'secretsmanager:DeleteSecret'
      ],
      resources: ['*']
    }));

    // Grant Secrets Manager permissions for export/import
    exportUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'secretsmanager:ListSecrets',
        'secretsmanager:DescribeSecret'
      ],
      resources: ['*']
    }));

    importUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'secretsmanager:CreateSecret',
        'secretsmanager:UpdateSecret',
        'secretsmanager:TagResource'
      ],
      resources: ['*']
    }));

    // Grant Bedrock permissions to generate_usecase Lambda
    generateUsecaseLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'bedrock:InvokeModel',
        'bedrock:InvokeModelWithResponseStream'
      ],
      resources: [
        "*"
      ]
    }));

    updateUsecaseSecretsLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'secretsmanager:UpdateSecret'
      ],
      resources: ['*']
    }));

    props.artefactsBucket.grantDelete(deleteExecutionLambda);
    props.artefactsBucket.grantRead(deleteExecutionLambda);

    // API Gateway endpoints
    const usecases = this.addResource(apiInstance.root, 'usecases')
    this.addMethod(usecases, HttpMethod.GET, listUsecasesLambda)

    const usecase = this.addResource(apiInstance.root, 'usecase')
    this.addMethod(usecase, HttpMethod.POST, createUsecaseLambda)

    const usecaseId = this.addResource(usecase, '{id}')
    this.addMethod(usecaseId, HttpMethod.GET, getUsecaseLambda)
    this.addMethod(usecaseId, HttpMethod.PATCH, updateUsecaseLambda)
    this.addMethod(usecaseId, HttpMethod.DELETE, deleteUsecaseLambda)

    const steps = this.addResource(usecaseId, 'steps');
    this.addMethod(steps, HttpMethod.POST, createStepLambda)
    this.addMethod(steps, HttpMethod.GET, listStepsLambda)

    // API Gateway execute endpoint
    const execute = this.addResource(usecaseId, 'execute');
    this.addMethod(execute, HttpMethod.POST, props.executeUsecaseLambda)

    // API Gateway variables endpoint
    const variables = this.addResource(usecaseId, 'variables');
    this.addMethod(variables, HttpMethod.POST, createUsecaseVariablesLambda)
    this.addMethod(variables, HttpMethod.GET, getUsecaseVariablesLambda)

    // API Gateway schedule endpoint
    const schedule = this.addResource(usecaseId, 'schedule');
    this.addMethod(schedule, HttpMethod.POST, props.createScheduleLambda)
    this.addMethod(schedule, HttpMethod.GET, props.getScheduleLambda)
    this.addMethod(schedule, HttpMethod.DELETE, props.deleteScheduleLambda)

    // API Gateway hooks endpoint
    const hooks = this.addResource(usecaseId, 'hooks');
    this.addMethod(hooks, HttpMethod.POST, createUsecaseHooksLambda)
    this.addMethod(hooks, HttpMethod.GET, getUsercaseHooksLambda)

    // API Gateway executions endpoints
    const executions = this.addResource(usecaseId, 'executions');
    this.addMethod(executions, HttpMethod.GET, listExecutionsLambda)

    const execution = this.addResource(executions, '{executionId}');
    this.addMethod(execution, HttpMethod.DELETE, deleteExecutionLambda)
    this.addMethod(execution, HttpMethod.GET, getExecutionLambda)

    const executionSteps = this.addResource(execution, 'steps');
    this.addMethod(executionSteps, HttpMethod.GET, listExecutionStepsLambda)

    const executionStep = this.addResource(executionSteps, '{stepId}');
    this.addMethod(executionStep, HttpMethod.GET, getExecutionStepLambda)

    // API Gateway execution variables endpoint
    const executionVariables = this.addResource(execution, 'variables');
    this.addMethod(executionVariables, HttpMethod.GET, getExecutionVariablesLambda)

    // API Gateway live view endpoint
    const liveView = this.addResource(execution, 'live-view');
    this.addMethod(liveView, HttpMethod.GET, getLiveViewLambda)

    // API Gateway step endpoints
    const step = this.addResource(steps, '{stepId}');
    this.addMethod(step, HttpMethod.PATCH, updateStepLambda)
    this.addMethod(step, HttpMethod.DELETE, deleteStepLambda)

    // API Gateway reorder steps endpoint
    const reorderSteps = this.addResource(steps, 'reorder');
    this.addMethod(reorderSteps, HttpMethod.PATCH, reorderStepsLambda)

    // API Gateway endpoint for S3 URL generation
    const generateS3Url = this.addResource(apiInstance.root, 'generate-s3-url');
    this.addMethod(generateS3Url, HttpMethod.POST, props.generateS3UrlLambda)

    // API Gateway endpoints for recording (nested under execution)
    // /usecase/{id}/executions/{executionId}/events - list batches
    const executionEvents = this.addResource(execution, 'events');
    this.addMethod(executionEvents, HttpMethod.GET, listRecordingBatchesLambda)

    // /usecase/{id}/executions/{executionId}/event/{batchId} - get specific batch
    const executionEvent = this.addResource(execution, 'event');
    const executionEventBatch = this.addResource(executionEvent, '{batchId}');
    this.addMethod(executionEventBatch, HttpMethod.GET, getRecordingBatchLambda)

    // API Gateway secrets endpoints
    const secrets = this.addResource(usecaseId, 'secrets');
    this.addMethod(secrets, HttpMethod.POST, createUsecaseSecretsLambda)
    this.addMethod(secrets, HttpMethod.GET, getUsecaseSecretsLambda)
    this.addMethod(secrets, HttpMethod.DELETE, deleteUsecaseSecretsLambda)
    this.addMethod(secrets, HttpMethod.PATCH, updateUsecaseSecretsLambda)

    // API Gateway headers endpoints
    const headers = this.addResource(usecaseId, 'headers');
    this.addMethod(headers, HttpMethod.POST, createUsecaseHeadersLambda)
    this.addMethod(headers, HttpMethod.GET, getUsecaseHeadersLambda)

    // API Gateway export/import endpoints
    const exportEndpoint = this.addResource(usecaseId, 'export');
    this.addMethod(exportEndpoint, HttpMethod.GET, exportUsecaseLambda)

    const importEndpoint = this.addResource(apiInstance.root, 'import');
    this.addMethod(importEndpoint, HttpMethod.POST, importUsecaseLambda)

    // API Gateway generate-usecase endpoint
    const generateUsecase = this.addResource(apiInstance.root, 'generate-usecase');
    this.addMethod(generateUsecase, HttpMethod.POST, generateUsecaseLambda)

    // API Gateway subscription endpoints
    const usecaseSubscription = this.addResource(usecaseId, 'subscription');
    this.addMethod(usecaseSubscription, HttpMethod.GET, props.getUsecaseSubscriptionLambda)
    this.addMethod(usecaseSubscription, HttpMethod.POST, props.subscribeUsecaseLambda)
    this.addMethod(usecaseSubscription, HttpMethod.DELETE, props.unsubscribeUsecaseLambda)

    // API Gateway user management endpoints
    const users = this.addResource(apiInstance.root, 'users');
    this.addMethod(users, HttpMethod.GET, props.listUsersLambda)
    this.addMethod(users, HttpMethod.POST, props.addUserLambda)
    const user = this.addResource(users, '{username}');
    this.addMethod(user, HttpMethod.DELETE, props.removeUserLambda)

    // Create a deployment to push changes to the API Gateway stage
    this.deployment = new Deployment(this, 'ApiDeployment', {
      api: apiInstance,
      description: `Deployment at ${new Date().toISOString()}`,
      stageName: props.apiDeploymentStage
    });

    this.routes.forEach((route: Method) => {
      this.deployment.node.addDependency(route);
    })

    this.deployment.addToLogicalId(new Date().toISOString())
  }
}
