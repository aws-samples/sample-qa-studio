#!/usr/bin/env node
import { App, Aspects } from 'aws-cdk-lib';
import { AwsSolutionsChecks, NagReportFormat } from 'cdk-nag';
import * as fs from 'fs';
import * as path from 'path';
import { NovaActQAStudioStorageStack } from '../lib/storage-stack';
import { NovaActQAStudioAuthStack } from '../lib/auth-stack';
import { NovaActQAStudioWorkerStack } from '../lib/worker-stack';
import { NovaActQAStudioFrontendStack } from '../lib/frontend-stack';
import { NovaActQAStudioApiStack } from '../lib/api-stack';
import { NovaActQAStudioLambdaStack } from '../lib/lambda-stack';
import { loadConfig, getStackEnv } from '../lib/config';
import { CfnNagSuppressions } from '../lib/cfn-nag-suppressions';
import { applyCdkNagSuppressions } from '../lib/cdk-nag-suppressions';

// Load and validate configuration with sane defaults
const config = loadConfig();
const {
  adminEmail, baseName, apiEndpoint, apiDeploymentStage, bedrockModelId, lambdaConcurrency, networkAssertionBodyMaxBytes,
  maxExecutionDurationMinutes, maxWizardSessionMinutes,
} = config;

// Read version from package.json
const packageJsonPath = path.join(__dirname, '..', 'package.json');
const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf-8'));
const version = packageJson.version;

const app = new App();

// Explicit account/region on every stack when vpcId is set (Vpc.fromLookup
// needs it; one env keeps cross-stack references valid). Otherwise undefined:
// environment-agnostic synthesis.
const stackEnv = getStackEnv(config);

if (!adminEmail) {
  throw new Error("adminEmail is required")
}

const storageStack = new NovaActQAStudioStorageStack(app, 'storage', {
  stackName: `${baseName}-storage`,
  env: stackEnv,
  baseName,
  lambdaConcurrency,
  networkAssertionBodyMaxBytes,
})

const oauthCallbackUrls = [
  ...(config.cliCallbackUrl ? [config.cliCallbackUrl] : []),
];

const authStack = new NovaActQAStudioAuthStack(app, 'auth', {
  stackName: `${baseName}-auth`,
  env: stackEnv,
  baseName,
  adminEmail,
  lambdaConcurrency,
  networkAssertionBodyMaxBytes,
  ...(oauthCallbackUrls.length > 0 && { callbackUrls: oauthCallbackUrls }),
})

// Worker stack - includes worker infrastructure and notifications
const workerStack = new NovaActQAStudioWorkerStack(app, 'worker', {
  stackName: `${baseName}-worker`,
  env: stackEnv,
  baseName,
  lambdaConcurrency,
  networkAssertionBodyMaxBytes,
  table: storageStack.table,
  tableReadPolicy: storageStack.tableReadPolicy,
  tableWritePolicy: storageStack.tableWritePolicy,
  novaActApiKeySecret: storageStack.novaActApiKeySecret,
  workerCredentialsSecret: authStack.workerCredentialsSecret,
  apiDeploymentStage,
  version,
  maxExecutionDurationMinutes,
  maxWizardSessionMinutes,
})

// Lambda stack - contains all Lambda function definitions
const lambdaStack = new NovaActQAStudioLambdaStack(app, 'lambdas', {
  stackName: `${baseName}-lambdas`,
  env: stackEnv,
  baseName,
  lambdaConcurrency,
  networkAssertionBodyMaxBytes,
  table: storageStack.table,
  userPool: authStack.userPool,
  artefactsBucket: workerStack.artefactsBucket,
  schedulerGroupName: workerStack.schedulerGroup.name!,
  tableReadPolicy: storageStack.tableReadPolicy,
  tableWritePolicy: storageStack.tableWritePolicy,
  tableFullAccessPolicy: storageStack.tableFullAccessPolicy,
  bedrockModelId,
  notificationTopicArn: workerStack.notificationTopicArn,
  executeUsecaseLambda: workerStack.executeUsecaseLambda,
  recordingQueueUrl: workerStack.recordingQueueUrl,
  recordingQueueArn: workerStack.recordingQueueArn,
  wizardEventBusName: workerStack.wizardEventBus.eventBusName,
  microvmImageArn: workerStack.microvmImageArn,
})

// API stack - includes API Gateway, Authorizer, and all routes
const apiStack = new NovaActQAStudioApiStack(app, 'api', {
  stackName: `${baseName}-api`,
  env: stackEnv,
  baseName,
  lambdaConcurrency,
  networkAssertionBodyMaxBytes,
  userPool: authStack.userPool,
  table: storageStack.table,
  workerClientId: authStack.workerM2MClient.userPoolClientId,
  apiDeploymentStage,
  lambdaStack: lambdaStack,
  addUserLambda: lambdaStack.addUserLambda,
  listUsersLambda: lambdaStack.listUsersLambda,
  getUserLambda: lambdaStack.getUserLambda,
  updateUserGroupsLambda: lambdaStack.updateUserGroupsLambda,
  subscribeUsecaseLambda: lambdaStack.subscribeUsecaseLambda,
  unsubscribeUsecaseLambda: lambdaStack.unsubscribeUsecaseLambda,
  getUsecaseSubscriptionLambda: lambdaStack.getUsecaseSubscriptionLambda,
  createScheduleLambda: workerStack.createScheduleLambda,
  getScheduleLambda: lambdaStack.getScheduleLambda,
  deleteScheduleLambda: lambdaStack.deleteScheduleLambda,
  executeUsecaseLambda: workerStack.executeUsecaseLambda,
  stopExecutionLambda: workerStack.stopExecutionLambda,
  generateS3UrlLambda: lambdaStack.generateS3UrlLambda,
  startWizardLambda: workerStack.startWizardLambda,
  addWizardStepLambda: workerStack.addWizardStepLambda,
  acceptWizardStepLambda: lambdaStack.acceptWizardStepLambda,
  rejectWizardStepLambda: lambdaStack.rejectWizardStepLambda,
  terminateWizardLambda: workerStack.terminateWizardLambda,
  sendRecordingCommandLambda: lambdaStack.sendRecordingCommandLambda,
  getRecordingDataLambda: lambdaStack.getRecordingDataLambda,
})

// Frontend stack must be created after API is set up
const frontendStack = new NovaActQAStudioFrontendStack(app, 'frontend', {
  stackName: `${baseName}-frontend`,
  env: stackEnv,
  apiEndpoint: apiEndpoint,
  baseName,
  lambdaConcurrency,
  networkAssertionBodyMaxBytes,
  apiId: apiStack.api.restApiId,
})

// Apply cfn_nag suppressions for CDK-managed resources across all stacks
Aspects.of(app).add(new CfnNagSuppressions());

// Apply cdk-nag AwsSolutions checks across all stacks
Aspects.of(app).add(new AwsSolutionsChecks({
  verbose: true,
  reports: true,
  reportFormats: [NagReportFormat.CSV, NagReportFormat.JSON],
}));

// Apply cdk-nag suppressions for known acceptable patterns
applyCdkNagSuppressions(app, {
  storageStack,
  authStack,
  workerStack,
  lambdaStack,
  apiStack,
  frontendStack,
});

app.synth();