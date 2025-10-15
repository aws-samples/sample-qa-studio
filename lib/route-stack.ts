import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { RestApi, LambdaIntegration, AuthorizationType, Method, Resource, IAuthorizer } from 'aws-cdk-lib/aws-apigateway';
import { Function } from 'aws-cdk-lib/aws-lambda';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { Table } from 'aws-cdk-lib/aws-dynamodb';
import { PolicyStatement, Effect, ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';

interface NovaActQAStudioRouteStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  apiId: string
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

  private addMethod(resource: Resource, method: HttpMethod, lambda: Function): Method {
    return resource.addMethod(method, new LambdaIntegration(lambda), {
      authorizer: this.authorizer,
      authorizationType: AuthorizationType.COGNITO
    });
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
    const usecases = apiInstance.root.addResource('usecases');
    this.addMethod(usecases, HttpMethod.GET, listUsecasesLambda)

    const usecase = apiInstance.root.addResource('usecase');
    this.addMethod(usecase, HttpMethod.POST, createUsecaseLambda)

    const usecaseId = usecase.addResource('{id}');
    this.addMethod(usecaseId, HttpMethod.GET, getUsecaseLambda)
    this.addMethod(usecaseId, HttpMethod.PATCH, updateUsecaseLambda)
    this.addMethod(usecaseId, HttpMethod.DELETE, deleteUsecaseLambda)

    const steps = usecaseId.addResource('steps');
    this.addMethod(steps, HttpMethod.POST, createStepLambda)
    this.addMethod(steps, HttpMethod.GET, listStepsLambda)

    // API Gateway execute endpoint
    const execute = usecaseId.addResource('execute');
    this.addMethod(execute, HttpMethod.POST, props.executeUsecaseLambda)

    // API Gateway variables endpoint
    const variables = usecaseId.addResource('variables');
    this.addMethod(variables, HttpMethod.POST, createUsecaseVariablesLambda)
    this.addMethod(variables, HttpMethod.GET, getUsecaseVariablesLambda)

    // API Gateway schedule endpoint
    const schedule = usecaseId.addResource('schedule');
    this.addMethod(schedule, HttpMethod.POST, props.createScheduleLambda)
    this.addMethod(schedule, HttpMethod.GET, props.getScheduleLambda)
    this.addMethod(schedule, HttpMethod.DELETE, props.deleteScheduleLambda)

    // API Gateway hooks endpoint
    const hooks = usecaseId.addResource('hooks');
    this.addMethod(hooks, HttpMethod.POST, createUsecaseHooksLambda)
    this.addMethod(hooks, HttpMethod.GET, getUsercaseHooksLambda)

    // API Gateway executions endpoints
    const executions = usecaseId.addResource('executions');
    this.addMethod(executions, HttpMethod.GET, listExecutionsLambda)

    const execution = executions.addResource('{executionId}');
    this.addMethod(execution, HttpMethod.DELETE, deleteExecutionLambda)
    this.addMethod(execution, HttpMethod.GET, getExecutionLambda)

    const executionSteps = execution.addResource('steps');
    this.addMethod(executionSteps, HttpMethod.GET, listExecutionStepsLambda)

    const executionStep = executionSteps.addResource('{stepId}');
    this.addMethod(executionStep, HttpMethod.GET, getExecutionStepLambda)

    // API Gateway execution variables endpoint
    const executionVariables = execution.addResource('variables');
    this.addMethod(executionVariables, HttpMethod.GET, getExecutionVariablesLambda)

    // API Gateway live view endpoint
    const liveView = execution.addResource('live-view');
    this.addMethod(liveView, HttpMethod.GET, getLiveViewLambda)

    // API Gateway step endpoints
    const step = steps.addResource('{stepId}');
    this.addMethod(step, HttpMethod.PATCH, updateStepLambda)
    this.addMethod(step, HttpMethod.DELETE, deleteStepLambda)

    // API Gateway reorder steps endpoint
    const reorderSteps = steps.addResource('reorder');
    this.addMethod(reorderSteps, HttpMethod.PATCH, reorderStepsLambda)

    // API Gateway endpoint for S3 URL generation
    const generateS3Url = apiInstance.root.addResource('generate-s3-url');
    this.addMethod(generateS3Url, HttpMethod.POST, props.generateS3UrlLambda)

    // API Gateway secrets endpoints
    const secrets = usecaseId.addResource('secrets');
    this.addMethod(secrets, HttpMethod.POST, createUsecaseSecretsLambda)
    this.addMethod(secrets, HttpMethod.GET, getUsecaseSecretsLambda)
    this.addMethod(secrets, HttpMethod.DELETE, deleteUsecaseSecretsLambda)
    this.addMethod(secrets, HttpMethod.PATCH, updateUsecaseSecretsLambda)

    // API Gateway headers endpoints
    const headers = usecaseId.addResource('headers');
    this.addMethod(headers, HttpMethod.GET, createUsecaseHeadersLambda)
    this.addMethod(headers, HttpMethod.POST, getUsecaseHeadersLambda)

    // API Gateway export/import endpoints
    const exportEndpoint = usecaseId.addResource('export');
    this.addMethod(exportEndpoint, HttpMethod.GET, exportUsecaseLambda)

    const importEndpoint = apiInstance.root.addResource('import');
    this.addMethod(importEndpoint, HttpMethod.POST, importUsecaseLambda)

    // API Gateway generate-usecase endpoint
    const generateUsecase = apiInstance.root.addResource('generate-usecase');
    this.addMethod(generateUsecase, HttpMethod.POST, generateUsecaseLambda)

    // API Gateway subscription endpoints
    const usecaseSubscription = usecaseId.addResource('subscription');
    this.addMethod(usecaseSubscription, HttpMethod.GET, props.getUsecaseSubscriptionLambda)
    this.addMethod(usecaseSubscription, HttpMethod.POST, props.subscribeUsecaseLambda)
    this.addMethod(usecaseSubscription, HttpMethod.DELETE, props.unsubscribeUsecaseLambda)

    // API Gateway user management endpoints
    const users = apiInstance.root.addResource('users');
    this.addMethod(users, HttpMethod.GET, props.listUsersLambda)
    this.addMethod(users, HttpMethod.POST, props.addUserLambda)
    this.addMethod(users, HttpMethod.DELETE, props.removeUserLambda)
  }
}
