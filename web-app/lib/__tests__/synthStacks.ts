/**
 * Build the application stacks the way bin/cdk.ts does, offline, for
 * structural tests. Test files must mock '../config' to read
 * configuration.json.sample before importing this module:
 *
 *   jest.mock('../config', () => { ... loadConfig: () => actual.loadConfig(sample) });
 */
import { App, Environment } from 'aws-cdk-lib';

import { NovaActQAStudioStorageStack } from '../storage-stack';
import { NovaActQAStudioAuthStack } from '../auth-stack';
import { NovaActQAStudioWorkerStack } from '../worker-stack';
import { NovaActQAStudioLambdaStack } from '../lambda-stack';
import { NovaActQAStudioApiStack } from '../api-stack';

export interface SynthOptions {
  /** Also build the API stack (lambdas/auth authorizer etc.). Default false. */
  withApi?: boolean;
  /** Explicit env for every stack, as bin/cdk.ts does via getStackEnv when vpcId is set. */
  env?: Environment;
  /** App context (e.g. a stubbed `vpc-provider:…` lookup result). */
  context?: Record<string, unknown>;
}

export function synthStacks({ withApi = false, env, context }: SynthOptions = {}) {
  const app = new App({ context });
  const common = { baseName: 'test', lambdaConcurrency: 5, networkAssertionBodyMaxBytes: 1_048_576, env };
  const storage = new NovaActQAStudioStorageStack(app, 'storage', { ...common });
  const auth = new NovaActQAStudioAuthStack(app, 'auth', { ...common, adminEmail: 'admin@example.com' });
  const worker = new NovaActQAStudioWorkerStack(app, 'worker', {
    ...common,
    table: storage.table,
    tableReadPolicy: storage.tableReadPolicy,
    tableWritePolicy: storage.tableWritePolicy,
    novaActApiKeySecret: storage.novaActApiKeySecret,
    workerCredentialsSecret: auth.workerCredentialsSecret,
    apiDeploymentStage: 'api',
    version: '0.0.0',
  });
  const lambdas = new NovaActQAStudioLambdaStack(app, 'lambdas', {
    ...common,
    table: storage.table,
    userPool: auth.userPool,
    artefactsBucket: worker.artefactsBucket,
    schedulerGroupName: worker.schedulerGroup.name!,
    tableReadPolicy: storage.tableReadPolicy,
    tableWritePolicy: storage.tableWritePolicy,
    tableFullAccessPolicy: storage.tableFullAccessPolicy,
    bedrockModelId: 'model',
    notificationTopicArn: worker.notificationTopicArn,
    executeUsecaseLambda: worker.executeUsecaseLambda,
    recordingQueueUrl: worker.recordingQueueUrl,
    recordingQueueArn: worker.recordingQueueArn,
    wizardEventBusName: worker.wizardEventBus.eventBusName,
    microvmImageArn: worker.microvmImageArn,
  });
  const api = withApi
    ? new NovaActQAStudioApiStack(app, 'api', {
        ...common,
        userPool: auth.userPool,
        table: storage.table,
        workerClientId: auth.workerM2MClient.userPoolClientId,
        apiDeploymentStage: 'api',
        lambdaStack: lambdas,
        addUserLambda: lambdas.addUserLambda,
        listUsersLambda: lambdas.listUsersLambda,
        getUserLambda: lambdas.getUserLambda,
        updateUserGroupsLambda: lambdas.updateUserGroupsLambda,
        subscribeUsecaseLambda: lambdas.subscribeUsecaseLambda,
        unsubscribeUsecaseLambda: lambdas.unsubscribeUsecaseLambda,
        getUsecaseSubscriptionLambda: lambdas.getUsecaseSubscriptionLambda,
        createScheduleLambda: worker.createScheduleLambda,
        getScheduleLambda: lambdas.getScheduleLambda,
        deleteScheduleLambda: lambdas.deleteScheduleLambda,
        executeUsecaseLambda: worker.executeUsecaseLambda,
        stopExecutionLambda: worker.stopExecutionLambda,
        generateS3UrlLambda: lambdas.generateS3UrlLambda,
        startWizardLambda: worker.startWizardLambda,
        addWizardStepLambda: worker.addWizardStepLambda,
        acceptWizardStepLambda: lambdas.acceptWizardStepLambda,
        rejectWizardStepLambda: lambdas.rejectWizardStepLambda,
        terminateWizardLambda: worker.terminateWizardLambda,
        sendRecordingCommandLambda: lambdas.sendRecordingCommandLambda,
        getRecordingDataLambda: lambdas.getRecordingDataLambda,
      })
    : undefined;
  return { app, storage, auth, worker, lambdas, api };
}
