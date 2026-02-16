import { Construct } from 'constructs';
import { CfnOutput, Duration as cdk_Duration } from 'aws-cdk-lib';
import * as cdk from 'aws-cdk-lib';
import { RestApi, TokenAuthorizer, EndpointType, LambdaIntegration, AuthorizationType, Method, Resource, IResource, Deployment, IdentitySource } from 'aws-cdk-lib/aws-apigateway';
import { UserPool } from 'aws-cdk-lib/aws-cognito';
import { Function } from 'aws-cdk-lib/aws-lambda';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';
import { NovaActQAStudioLambdaStack } from './lambda-stack';

enum HttpMethod {
  GET = 'GET',
  POST = 'POST',
  PUT = 'PUT',
  DELETE = 'DELETE',
  PATCH = 'PATCH',
}

interface NovaActQAStudioApiStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  userPool: UserPool
  apiDeploymentStage: string
  lambdaStack: NovaActQAStudioLambdaStack
  // Lambdas from other stacks (auth, worker)
  addUserLambda: Function
  listUsersLambda: Function
  removeUserLambda: Function
  getUserLambda: Function
  updateUserGroupsLambda: Function
  createScheduleLambda: Function
  deleteScheduleLambda: Function
  getScheduleLambda: Function
  executeUsecaseLambda: Function
  stopExecutionLambda: Function
  subscribeUsecaseLambda: Function
  unsubscribeUsecaseLambda: Function
  getUsecaseSubscriptionLambda: Function
  generateS3UrlLambda: Function
  startWizardLambda: Function
  addWizardStepLambda: Function
  acceptWizardStepLambda: Function
  restartWizardLambda: Function
  terminateWizardLambda: Function
}

export class NovaActQAStudioApiStack extends NovaActQAStudioBaseStack {
  public readonly api: RestApi
  public readonly authorizer: TokenAuthorizer
  public readonly authorizerLambda: Function
  private deployment: Deployment
  private routes: Method[] = []

  private addMethod(resource: Resource, method: HttpMethod, lambda: Function): Method {
    const resourceMethod = resource.addMethod(method, new LambdaIntegration(lambda), {
      authorizer: this.authorizer,
      authorizationType: AuthorizationType.CUSTOM
    });

    this.routes.push(resourceMethod)
    return resourceMethod
  }

  private addResource(parentResource: IResource, name: string): Resource {
    return parentResource.addResource(name);
  }

  constructor(scope: Construct, id: string, props: NovaActQAStudioApiStackCreateProps) {
    super(scope, id, props);

    this.api = new RestApi(this, 'Api', {
      restApiName: this.cdkName('service'),
      endpointTypes: [
        EndpointType.REGIONAL
      ],
      deploy: false  // We'll create our own deployment with custom stage name
    });
    
    // Create Lambda Authorizer
    this.authorizerLambda = this.createPythonLambda({
      path: 'authorizer',
      codeDirectory: 'lambdas/auth',
      environment: {
        USER_POOL_ID: props.userPool.userPoolId
      }
    });
    
    // Lambda Token Authorizer (supports both user and M2M tokens)
    this.authorizer = new TokenAuthorizer(this, 'authorizer', {
      handler: this.authorizerLambda,
      identitySource: IdentitySource.header('Authorization'),
      resultsCacheTtl: cdk.Duration.minutes(5)
    });

    const l = props.lambdaStack // Shorthand for cleaner code

    // ========== API Gateway Route Definitions ==========

    // /usecases - List all usecases
    const usecases = this.addResource(this.api.root, 'usecases')
    this.addMethod(usecases, HttpMethod.GET, l.listUsecasesLambda)

    // /models - List available models
    const models = this.addResource(this.api.root, 'models')
    this.addMethod(models, HttpMethod.GET, l.listModelsLambda)

    // /usecase - Create usecase
    const usecase = this.addResource(this.api.root, 'usecase')
    this.addMethod(usecase, HttpMethod.POST, l.createUsecaseLambda)

    // /usecase/{id} - Get, update, delete usecase
    const usecaseId = this.addResource(usecase, '{id}')
    this.addMethod(usecaseId, HttpMethod.GET, l.getUsecaseLambda)
    this.addMethod(usecaseId, HttpMethod.PATCH, l.updateUsecaseLambda)
    this.addMethod(usecaseId, HttpMethod.DELETE, l.deleteUsecaseLambda)

    // /usecase/{id}/steps - Create and list steps
    const steps = this.addResource(usecaseId, 'steps')
    this.addMethod(steps, HttpMethod.POST, l.createStepLambda)
    this.addMethod(steps, HttpMethod.GET, l.listStepsLambda)

    // /usecase/{id}/steps/{stepId} - Update and delete step
    const step = this.addResource(steps, '{stepId}')
    this.addMethod(step, HttpMethod.PATCH, l.updateStepLambda)
    this.addMethod(step, HttpMethod.DELETE, l.deleteStepLambda)

    // /usecase/{id}/steps/reorder - Reorder steps
    const reorderSteps = this.addResource(steps, 'reorder')
    this.addMethod(reorderSteps, HttpMethod.PATCH, l.reorderStepsLambda)

    // /usecase/{id}/steps/{stepId}/update-from-template - Update step from template
    const updateFromTemplate = this.addResource(step, 'update-from-template')
    this.addMethod(updateFromTemplate, HttpMethod.POST, l.updateStepFromTemplateLambda)

    // /usecase/{id}/execute - Execute usecase
    const execute = this.addResource(usecaseId, 'execute')
    this.addMethod(execute, HttpMethod.POST, props.executeUsecaseLambda)

    // /usecase/{id}/variables - Create and get variables
    const variables = this.addResource(usecaseId, 'variables')
    this.addMethod(variables, HttpMethod.POST, l.createUsecaseVariablesLambda)
    this.addMethod(variables, HttpMethod.GET, l.getUsecaseVariablesLambda)

    // /usecase/{id}/schedule - Schedule management
    const schedule = this.addResource(usecaseId, 'schedule')
    this.addMethod(schedule, HttpMethod.POST, props.createScheduleLambda)
    this.addMethod(schedule, HttpMethod.GET, props.getScheduleLambda)
    this.addMethod(schedule, HttpMethod.DELETE, props.deleteScheduleLambda)

    // /usecase/{id}/hooks - Create and get hooks
    const hooks = this.addResource(usecaseId, 'hooks')
    this.addMethod(hooks, HttpMethod.POST, l.createUsecaseHooksLambda)
    this.addMethod(hooks, HttpMethod.GET, l.getUsercaseHooksLambda)

    // /usecase/{id}/headers - Create and get headers
    const headers = this.addResource(usecaseId, 'headers')
    this.addMethod(headers, HttpMethod.POST, l.createUsecaseHeadersLambda)
    this.addMethod(headers, HttpMethod.GET, l.getUsecaseHeadersLambda)

    // /usecase/{id}/secrets - Secrets management
    const secrets = this.addResource(usecaseId, 'secrets')
    this.addMethod(secrets, HttpMethod.POST, l.createUsecaseSecretsLambda)
    this.addMethod(secrets, HttpMethod.GET, l.getUsecaseSecretsLambda)
    this.addMethod(secrets, HttpMethod.DELETE, l.deleteUsecaseSecretsLambda)
    this.addMethod(secrets, HttpMethod.PATCH, l.updateUsecaseSecretsLambda)

    // /usecase/{id}/export - Export usecase
    const exportEndpoint = this.addResource(usecaseId, 'export')
    this.addMethod(exportEndpoint, HttpMethod.GET, l.exportUsecaseLambda)

    // /usecase/{id}/clone - Clone usecase
    const cloneEndpoint = this.addResource(usecaseId, 'clone')
    this.addMethod(cloneEndpoint, HttpMethod.POST, l.cloneUsecaseLambda)

    // /usecase/{id}/subscription - Subscription management
    const usecaseSubscription = this.addResource(usecaseId, 'subscription')
    this.addMethod(usecaseSubscription, HttpMethod.GET, props.getUsecaseSubscriptionLambda)
    this.addMethod(usecaseSubscription, HttpMethod.POST, props.subscribeUsecaseLambda)
    this.addMethod(usecaseSubscription, HttpMethod.DELETE, props.unsubscribeUsecaseLambda)

    // /usecase/{id}/import-template - Import template into usecase
    const importTemplate = this.addResource(usecaseId, 'import-template')
    this.addMethod(importTemplate, HttpMethod.POST, l.importTemplateLambda)

    // /usecase/{id}/template-updates - Check for template updates
    const templateUpdates = this.addResource(usecaseId, 'template-updates')
    this.addMethod(templateUpdates, HttpMethod.GET, l.checkTemplateUpdatesLambda)

    // /usecase/{id}/executions - List executions
    const executions = this.addResource(usecaseId, 'executions')
    this.addMethod(executions, HttpMethod.GET, l.listExecutionsLambda)

    // /usecase/{id}/executions/{executionId} - Get and delete execution
    const execution = this.addResource(executions, '{executionId}')
    this.addMethod(execution, HttpMethod.DELETE, l.deleteExecutionLambda)
    this.addMethod(execution, HttpMethod.GET, l.getExecutionLambda)

    // /usecase/{id}/executions/{executionId}/stop - Stop execution
    const stopExecution = this.addResource(execution, 'stop')
    this.addMethod(stopExecution, HttpMethod.POST, props.stopExecutionLambda)

    // /usecase/{id}/executions/{executionId}/steps - List execution steps
    const executionSteps = this.addResource(execution, 'steps')
    this.addMethod(executionSteps, HttpMethod.GET, l.listExecutionStepsLambda)

    // /usecase/{id}/executions/{executionId}/steps/{stepId} - Get execution step
    const executionStep = this.addResource(executionSteps, '{stepId}')
    this.addMethod(executionStep, HttpMethod.GET, l.getExecutionStepLambda)

    // /usecase/{id}/executions/{executionId}/variables - Get execution variables
    const executionVariables = this.addResource(execution, 'variables')
    this.addMethod(executionVariables, HttpMethod.GET, l.getExecutionVariablesLambda)

    // /usecase/{id}/executions/{executionId}/live-view - Get live view
    const liveView = this.addResource(execution, 'live-view')
    this.addMethod(liveView, HttpMethod.GET, l.getLiveViewLambda)

    // /usecase/{id}/executions/{executionId}/downloads - List downloads
    const downloads = this.addResource(execution, 'downloads')
    this.addMethod(downloads, HttpMethod.GET, l.listDownloadsLambda)

    // /usecase/{id}/executions/{executionId}/downloads/{fileName} - Download file
    const downloadFile = this.addResource(downloads, '{fileName}')
    this.addMethod(downloadFile, HttpMethod.GET, l.downloadFileLambda)

    // /usecase/{id}/executions/{executionId}/events - List recording batches
    const executionEvents = this.addResource(execution, 'events')
    this.addMethod(executionEvents, HttpMethod.GET, l.listRecordingBatchesLambda)

    // /usecase/{id}/executions/{executionId}/event/{batchId} - Get recording batch
    const executionEvent = this.addResource(execution, 'event')
    const executionEventBatch = this.addResource(executionEvent, '{batchId}')
    this.addMethod(executionEventBatch, HttpMethod.GET, l.getRecordingBatchLambda)

    // /import - Import usecase
    const importEndpoint = this.addResource(this.api.root, 'import')
    this.addMethod(importEndpoint, HttpMethod.POST, l.importUsecaseLambda)

    // /generate-usecase - Generate usecase with AI
    const generateUsecase = this.addResource(this.api.root, 'generate-usecase')
    this.addMethod(generateUsecase, HttpMethod.POST, l.generateUsecaseLambda)

    // /generate-s3-url - Generate S3 presigned URL
    const generateS3Url = this.addResource(this.api.root, 'generate-s3-url')
    this.addMethod(generateS3Url, HttpMethod.POST, props.generateS3UrlLambda)

    // /wizard - Wizard endpoints
    const wizard = this.addResource(this.api.root, 'wizard')
    const wizardStart = this.addResource(wizard, 'start')
    this.addMethod(wizardStart, HttpMethod.POST, props.startWizardLambda)

    const wizardSession = this.addResource(wizard, '{sessionId}')
    const wizardStep = this.addResource(wizardSession, 'step')
    this.addMethod(wizardStep, HttpMethod.POST, props.addWizardStepLambda)

    const wizardAccept = this.addResource(wizardSession, 'accept')
    const wizardAcceptStep = this.addResource(wizardAccept, '{stepId}')
    const wizardAcceptStepUsecase = this.addResource(wizardAcceptStep, '{usecaseId}')
    this.addMethod(wizardAcceptStepUsecase, HttpMethod.POST, props.acceptWizardStepLambda)

    const wizardRestart = this.addResource(wizardSession, 'restart')
    this.addMethod(wizardRestart, HttpMethod.POST, props.restartWizardLambda)

    const wizardTerminate = this.addResource(wizardSession, 'terminate')
    const wizardTerminateUsecase = this.addResource(wizardTerminate, '{usecaseId}')
    this.addMethod(wizardTerminateUsecase, HttpMethod.POST, props.terminateWizardLambda)

    // /users - User management
    const users = this.addResource(this.api.root, 'users')
    this.addMethod(users, HttpMethod.GET, props.listUsersLambda)
    this.addMethod(users, HttpMethod.POST, props.addUserLambda)

    const user = this.addResource(users, '{username}')
    this.addMethod(user, HttpMethod.GET, props.getUserLambda)
    this.addMethod(user, HttpMethod.DELETE, props.removeUserLambda)

    const userGroups = this.addResource(user, 'groups')
    this.addMethod(userGroups, HttpMethod.PUT, props.updateUserGroupsLambda)

    // /oauth-clients - OAuth client management
    const oauthClients = this.addResource(this.api.root, 'oauth-clients')
    this.addMethod(oauthClients, HttpMethod.GET, l.listOAuthClientsLambda)
    this.addMethod(oauthClients, HttpMethod.POST, l.createOAuthClientLambda)

    const oauthClient = this.addResource(oauthClients, '{clientId}')
    this.addMethod(oauthClient, HttpMethod.DELETE, l.deleteOAuthClientLambda)

    // /scopes - List available OAuth scopes (public endpoint, no auth)
    const scopes = this.addResource(this.api.root, 'scopes')
    const scopesMethod = scopes.addMethod(HttpMethod.GET, new LambdaIntegration(l.listScopesLambda), {
      authorizationType: AuthorizationType.NONE
    });
    this.routes.push(scopesMethod)

    // /templates - Template management
    const templates = this.addResource(this.api.root, 'templates')
    this.addMethod(templates, HttpMethod.GET, l.listTemplatesLambda)
    this.addMethod(templates, HttpMethod.POST, l.createTemplateLambda)

    // /templates/{id} - Get, update, delete template
    const template = this.addResource(templates, '{id}')
    this.addMethod(template, HttpMethod.GET, l.getTemplateLambda)
    this.addMethod(template, HttpMethod.PATCH, l.updateTemplateLambda)
    this.addMethod(template, HttpMethod.DELETE, l.deleteTemplateLambda)

    // /templates/{id}/steps - Template steps
    const templateSteps = this.addResource(template, 'steps')
    this.addMethod(templateSteps, HttpMethod.GET, l.listTemplateStepsLambda)
    this.addMethod(templateSteps, HttpMethod.POST, l.createTemplateStepLambda)

    // /templates/{id}/steps/reorder - Reorder template steps
    const reorderTemplateSteps = this.addResource(templateSteps, 'reorder')
    this.addMethod(reorderTemplateSteps, HttpMethod.PATCH, l.reorderTemplateStepsLambda)

    // /templates/{id}/steps/{stepId} - Update and delete template step
    const templateStep = this.addResource(templateSteps, '{stepId}')
    this.addMethod(templateStep, HttpMethod.PATCH, l.updateTemplateStepLambda)
    this.addMethod(templateStep, HttpMethod.DELETE, l.deleteTemplateStepLambda)

    // /templates/{id}/variables - Template variables
    const templateVariables = this.addResource(template, 'variables')
    this.addMethod(templateVariables, HttpMethod.GET, l.getTemplateVariablesLambda)
    this.addMethod(templateVariables, HttpMethod.POST, l.createTemplateVariablesLambda)

    // /templates/{id}/apply - Apply template to create usecase
    const applyTemplate = this.addResource(template, 'apply')
    this.addMethod(applyTemplate, HttpMethod.POST, l.applyTemplateLambda)

    // /test-suites - Test suite management
    const testSuites = this.addResource(this.api.root, 'test-suites')
    this.addMethod(testSuites, HttpMethod.GET, l.listTestSuitesLambda)
    this.addMethod(testSuites, HttpMethod.POST, l.createTestSuiteLambda)

    // /test-suites/{suite_id} - Get, update, delete test suite
    const testSuite = this.addResource(testSuites, '{suite_id}')
    this.addMethod(testSuite, HttpMethod.GET, l.getTestSuiteLambda)
    this.addMethod(testSuite, HttpMethod.PUT, l.updateTestSuiteLambda)
    this.addMethod(testSuite, HttpMethod.DELETE, l.deleteTestSuiteLambda)

    // /test-suites/{suite_id}/usecases - Add and list use cases in suite
    const suiteUsecases = this.addResource(testSuite, 'usecases')
    this.addMethod(suiteUsecases, HttpMethod.GET, l.listSuiteUsecasesLambda)
    this.addMethod(suiteUsecases, HttpMethod.POST, l.addUsecasesToSuiteLambda)

    // /test-suites/{suite_id}/usecases/{usecase_id} - Remove use case from suite
    const suiteUsecase = this.addResource(suiteUsecases, '{usecase_id}')
    this.addMethod(suiteUsecase, HttpMethod.DELETE, l.removeUsecaseFromSuiteLambda)

    // /test-suites/{suite_id}/execute - Execute test suite
    const executeSuite = this.addResource(testSuite, 'execute')
    this.addMethod(executeSuite, HttpMethod.POST, l.executeTestSuiteLambda)

    // /test-suites/{suite_id}/executions - List suite executions
    const suiteExecutions = this.addResource(testSuite, 'executions')
    this.addMethod(suiteExecutions, HttpMethod.GET, l.listSuiteExecutionsLambda)

    // /test-suites/{suite_id}/executions/{execution_id} - Get suite execution
    const suiteExecution = this.addResource(suiteExecutions, '{execution_id}')
    this.addMethod(suiteExecution, HttpMethod.GET, l.getSuiteExecutionLambda)

    // /test-suites/{suite_id}/schedule - Configure suite schedule
    const suiteSchedule = this.addResource(testSuite, 'schedule')
    this.addMethod(suiteSchedule, HttpMethod.PUT, l.updateSuiteScheduleLambda)

    // Create API Gateway deployment
    this.deployment = new Deployment(this, 'ApiDeployment', {
      api: this.api,
      description: `Deployment at ${new Date().toISOString()}`,
      stageName: props.apiDeploymentStage
    })

    this.routes.forEach((route: Method) => {
      this.deployment.node.addDependency(route)
    })

    this.deployment.addToLogicalId(new Date().toISOString())

    // Construct API URL manually since deploy: false
    const apiUrl = `https://${this.api.restApiId}.execute-api.${this.region}.amazonaws.com/${props.apiDeploymentStage}/`;
    
    this.log('apigatewayDomain', apiUrl)

    // Export API URL for post-deployment config generation
    new CfnOutput(this, 'ApiUrlOutput', {
      value: apiUrl,
      description: 'API Gateway URL',
      exportName: `${props.baseName}-api-url`
    });
  }
}
