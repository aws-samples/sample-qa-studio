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
const { adminEmail, baseName, apiEndpoint, apiDeploymentStage, bedrockModelId, lambdaConcurrency } = config;

// Read version from package.json
const packageJsonPath = path.join(__dirname, '..', 'package.json');
const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf-8'));
const version = packageJson.version;

const app = new App();

// Get stack environment (explicit env needed when using existing VPC)
const stackEnv = getStackEnv(config);

if (!adminEmail) {
  throw new Error("adminEmail is required")
}

const storageStack = new NovaActQAStudioStorageStack(app, 'storage', {
  stackName: `${baseName}-storage`,
  baseName,
  lambdaConcurrency,
  env: stackEnv,
})

const oauthCallbackUrls = [
  ...(config.cliCallbackUrl ? [config.cliCallbackUrl] : []),
];

const authStack = new NovaActQAStudioAuthStack(app, 'auth', {
  stackName: `${baseName}-auth`,
  baseName,
  adminEmail,
  lambdaConcurrency,
  ...(oauthCallbackUrls.length > 0 && { callbackUrls: oauthCallbackUrls }),
  env: stackEnv,
})

// Worker stack - includes worker infrastructure and notifications
const workerStack = new NovaActQAStudioWorkerStack(app, 'worker', {
  stackName: `${baseName}-worker`,
  baseName,
  lambdaConcurrency,
  env: stackEnv,
  table: storageStack.table,
  tableReadPolicy: storageStack.tableReadPolicy,
  tableWritePolicy: storageStack.tableWritePolicy,
  novaActApiKeySecret: storageStack.novaActApiKeySecret,
  version,
})

// Lambda stack - contains all Lambda function definitions
const lambdaStack = new NovaActQAStudioLambdaStack(app, 'lambdas', {
  stackName: `${baseName}-lambdas`,
  baseName,
  lambdaConcurrency,
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
  ecsClusterArn: workerStack.cluster.clusterArn,
  env: stackEnv,
})

// API stack - includes API Gateway, Authorizer, and all routes
const apiStack = new NovaActQAStudioApiStack(app, 'api', {
  stackName: `${baseName}-api`,
  baseName,
  lambdaConcurrency,
  userPool: authStack.userPool,
  apiDeploymentStage,
  lambdaStack: lambdaStack,
  addUserLambda: lambdaStack.addUserLambda,
  removeUserLambda: lambdaStack.removeUserLambda,
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
  restartWizardLambda: workerStack.restartWizardLambda,
  terminateWizardLambda: workerStack.terminateWizardLambda,
  env: stackEnv,
})

// Frontend stack must be created after API is set up
const frontendStack = new NovaActQAStudioFrontendStack(app, 'frontend', {
  stackName: `${baseName}-frontend`,
  apiEndpoint: apiEndpoint,
  baseName,
  lambdaConcurrency,
  apiId: apiStack.api.restApiId,
  env: stackEnv,
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