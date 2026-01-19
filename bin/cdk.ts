#!/usr/bin/env node
import { App } from 'aws-cdk-lib';
import * as fs from 'fs';
import * as path from 'path';
import { NovaActQAStudioStorageStack } from '../lib/storage-stack';
import { NovaActQAStudioAuthStack } from '../lib/auth-stack';
import { NovaActQAStudioWorkerStack } from '../lib/worker-stack';
import { NovaActQAStudioNotificationStack } from '../lib/notification-stack';
import { NovaActQAStudioFrontendStack } from '../lib/frontend-stack';
import { NovaActQAStudioFrontendDeploymentStack } from '../lib/frontend-deployment';
import { NovaActQAStudioApiStack } from '../lib/api-stack';
import { NovaActQAStudioRouteStack } from '../lib/route-stack';
import { NovaActQAStudioEventBridgeStack } from '../lib/eventbridge-stack';
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

const apiStack = new NovaActQAStudioApiStack(app, 'api', {
  stackName: `${baseName}-api`,
  baseName,
  userPool: authStack.userPool,
  env: stackEnv,
})

// Frontend stack must be created after routes are set up
const frontendStack = new NovaActQAStudioFrontendStack(app, 'frontend', {
  stackName: `${baseName}-frontend`,
  apiEndpoint: apiEndpoint,
  baseName,
  apiId: apiStack.api.restApiId,
  env: stackEnv,
})

new NovaActQAStudioFrontendDeploymentStack(app, 'frontend_deployment', {
  stackName: `${baseName}-frontend-deployment`,
  baseName,
  distribution: frontendStack.distribution,  // Removed - not used
  frontendBucket: frontendStack.frontendBucket,
  env: stackEnv,
})

const notificationStack = new NovaActQAStudioNotificationStack(app, 'notification', {
  stackName: `${baseName}-notification`,
  baseName,
  table: storageStack.table,
  tableReadPolicy: storageStack.tableReadPolicy,
  tableFullAccessPolicy: storageStack.tableFullAccessPolicy,
  distributionDomain: `https://${frontendStack.distribution.domainName}`,
  env: stackEnv,
})

// Note: Notification stack reads frontend URL from SSM Parameter Store
// No explicit dependency needed - SSM lookup happens at synth time

const workerStack = new NovaActQAStudioWorkerStack(app, 'worker', {
  stackName: `${baseName}-worker`,
  baseName,
  env: stackEnv,
  table: storageStack.table,
  tableReadPolicy: storageStack.tableReadPolicy,
  novaActApiKeySecret: storageStack.novaActApiKeySecret,
  notificationQueue: notificationStack.notificationQueue,
  version,
})

// EventBridge stack for execution status events
new NovaActQAStudioEventBridgeStack(app, 'eventbridge', {
  stackName: `${baseName}-eventbridge`,
  baseName,
  table: storageStack.table,
  tableWritePolicy: storageStack.tableWritePolicy,
  env: stackEnv,
})

new NovaActQAStudioRouteStack(app, 'routes', {
  stackName: `${baseName}-routes`,
  apiDeploymentStage,
  baseName,
  apiId: apiStack.api.restApiId,
  apiRootResourceId: apiStack.api.restApiRootResourceId,
  table: storageStack.table,
  artefactsBucket: workerStack.artefactsBucket,
  authorizer: apiStack.authorizer,
  addUserLambda: authStack.addUserLambda,
  removeUserLambda: authStack.removeUserLambda,
  listUsersLambda: authStack.listUsersLambda,
  subscribeUsecaseLambda: notificationStack.subscribeUsecaseLambda,
  unsubscribeUsecaseLambda: notificationStack.unsubscribeUsecaseLambda,
  getUsecaseSubscriptionLambda: notificationStack.getUsecaseSubscriptionLambda,
  createScheduleLambda: workerStack.createScheduleLambda,
  getScheduleLambda: workerStack.getScheduleLambda,
  deleteScheduleLambda: workerStack.deleteScheduleLambda,
  executeUsecaseLambda: workerStack.executeUsecaseLambda,
  stopExecutionLambda: workerStack.stopExecutionLambda,
  tableReadPolicy: storageStack.tableReadPolicy,
  tableWritePolicy: storageStack.tableWritePolicy,
  tableFullAccessPolicy: storageStack.tableFullAccessPolicy,
  generateS3UrlLambda: workerStack.generateS3UrlLambda,
  startWizardLambda: workerStack.startWizardLambda,
  addWizardStepLambda: workerStack.addWizardStepLambda,
  acceptWizardStepLambda: workerStack.acceptWizardStepLambda,
  restartWizardLambda: workerStack.restartWizardLambda,
  terminateWizardLambda: workerStack.terminateWizardLambda,
  bedrockModelId,
  env: stackEnv,
})

// Note: Notification stack uses Fn.importValue() to get the frontend domain name
// CloudFormation will automatically handle the dependency through the import/export mechanism

app.synth();