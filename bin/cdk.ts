#!/usr/bin/env node
import { App } from 'aws-cdk-lib';
import * as fs from 'fs';
import * as path from 'path';
import { NovaActQAStudioStorageStack } from '../lib/storage-stack';
import { NovaActQAStudioAuthStack } from '../lib/auth-stack';
import { NovaActQAStudioWorkerStack } from '../lib/worker-stack';
import { NovaActQAStudioFrontendStack } from '../lib/frontend-stack';
import { NovaActQAStudioApiStack } from '../lib/api-stack';
import { NovaActQAStudioLambdaStack } from '../lib/lambda-stack';
import { loadConfig, getStackEnv } from '../lib/config';

// Load and validate configuration with sane defaults
const config = loadConfig();
const { adminEmail, baseName, apiEndpoint, apiDeploymentStage, bedrockModelId } = config;

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
  env: stackEnv,
})

const authStack = new NovaActQAStudioAuthStack(app, 'auth', {
  stackName: `${baseName}-auth`,
  baseName,
  adminEmail,
  env: stackEnv,
})

// Worker stack - includes worker infrastructure and notifications
const workerStack = new NovaActQAStudioWorkerStack(app, 'worker', {
  stackName: `${baseName}-worker`,
  baseName,
  env: stackEnv,
  table: storageStack.table,
  tableReadPolicy: storageStack.tableReadPolicy,
  novaActApiKeySecret: storageStack.novaActApiKeySecret,
  version,
})

// Lambda stack - contains all Lambda function definitions
const lambdaStack = new NovaActQAStudioLambdaStack(app, 'lambdas', {
  stackName: `${baseName}-lambdas`,
  baseName,
  table: storageStack.table,
  userPool: authStack.userPool,
  artefactsBucket: workerStack.artefactsBucket,
  schedulerGroupName: workerStack.schedulerGroup.name!,
  tableReadPolicy: storageStack.tableReadPolicy,
  tableWritePolicy: storageStack.tableWritePolicy,
  tableFullAccessPolicy: storageStack.tableFullAccessPolicy,
  bedrockModelId,
  notificationTopicArn: workerStack.notificationTopicArn,
  env: stackEnv,
})

// API stack - includes API Gateway, Authorizer, and all routes
const apiStack = new NovaActQAStudioApiStack(app, 'api', {
  stackName: `${baseName}-api`,
  baseName,
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
  restartWizardLambda: workerStack.restartWizardLambda,
  terminateWizardLambda: workerStack.terminateWizardLambda,
  env: stackEnv,
})

// Frontend stack must be created after API is set up
new NovaActQAStudioFrontendStack(app, 'frontend', {
  stackName: `${baseName}-frontend`,
  apiEndpoint: apiEndpoint,
  baseName,
  apiId: apiStack.api.restApiId,
  env: stackEnv,
})

app.synth();