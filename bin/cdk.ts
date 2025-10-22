#!/usr/bin/env node
import { App } from 'aws-cdk-lib';
// import { NovaActQAStudio } from '../lib/cdk-stack';
import { NovaActQAStudioStorageStack } from '../lib/storage-stack';
import { NovaActQAStudioAuthStack } from '../lib/auth-stack';
import { NovaActQAStudioWorkerStack } from '../lib/worker-stack';
import { NovaActQAStudioNotificationStack } from '../lib/notification-stack';
import { NovaActQAStudioFrontendStack } from '../lib/frontend-stack';
import { NovaActQAStudioFrontendDeploymentStack } from '../lib/frontend-deployment';
import { NovaActQAStudioApiStack } from '../lib/api-stack';
import { NovaActQAStudioRouteStack } from '../lib/route-stack';
import { adminEmail, baseName, userAgentString } from '../configuration.json'

const app = new App();

if (!adminEmail) {
  throw new Error("adminEmail is required")
}

const storageStack = new NovaActQAStudioStorageStack(app, 'storage', {
  stackName: `${baseName}-storage`,
  baseName
})

const authStack = new NovaActQAStudioAuthStack(app, 'auth', {
  stackName: `${baseName}-auth`,
  baseName,
  adminEmail
})

const apiStack = new NovaActQAStudioApiStack(app, 'api', {
  stackName: `${baseName}-api`,
  baseName,
  userPool: authStack.userPool
})

// Frontend stack must be created after routes are set up
const frontendStack = new NovaActQAStudioFrontendStack(app, 'frontend', {
  stackName: `${baseName}-frontend`,
  baseName,
  apiId: apiStack.api.restApiId,
})

const frontendDeploymentStack = new NovaActQAStudioFrontendDeploymentStack(app, 'frontend_deployment', {
  stackName: `${baseName}-frontend-deployment`,
  baseName,
  distribution: frontendStack.distribution,
  frontendBucket: frontendStack.frontendBucket,
})

const notificationStack = new NovaActQAStudioNotificationStack(app, 'notification', {
  stackName: `${baseName}-notification`,
  baseName,
  table: storageStack.table,
  tableReadPolicy: storageStack.tableReadPolicy,
  tableFullAccessPolicy: storageStack.tableFullAccessPolicy,
  distributionDomain: `https://${frontendStack.distribution.domainName}`
})

// Note: Notification stack reads frontend URL from SSM Parameter Store
// No explicit dependency needed - SSM lookup happens at synth time

const workerStack = new NovaActQAStudioWorkerStack(app, 'worker', {
  stackName: `${baseName}-worker`,
  baseName,
  table: storageStack.table,
  tableReadPolicy: storageStack.tableReadPolicy,
  novaActApiKeySecret: storageStack.novaActApiKeySecret,
  notificationQueue: notificationStack.notificationQueue,
  userAgentString: userAgentString,
})

const routeStack = new NovaActQAStudioRouteStack(app, 'routes', {
  stackName: `${baseName}-routes`,
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
  tableReadPolicy: storageStack.tableReadPolicy,
  tableWritePolicy: storageStack.tableWritePolicy,
  tableFullAccessPolicy: storageStack.tableFullAccessPolicy,
  generateS3UrlLambda: workerStack.generateS3UrlLambda
})

// Note: Notification stack uses Fn.importValue() to get the frontend domain name
// CloudFormation will automatically handle the dependency through the import/export mechanism

app.synth();

// new NovaActQAStudio(app, 'NovaActQAStudio', {
//   baseName: baseName
// });