/**
 * Guard: every endpoint Lambda whose handler runs the team ownership check
 * (require_resource_access / authorize_resource / permissions_repo) must be
 * able to read the table. The resolvers do GetItem on the use case / app /
 * execution / override records (and Query for shared-access grants); without
 * TABLE_NAME and dynamodb:GetItem the check throws and the route returns 500.
 *
 * Synthesizes storage + auth + worker + lambdas the way bin/cdk.ts does
 * (offline, config from configuration.json.sample) and checks the templates.
 */
import * as fs from 'fs';
import * as path from 'path';
import { App } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';

jest.mock('../config', () => {
  const actual = jest.requireActual('../config');
  const sample = require('path').join(__dirname, '..', '..', 'configuration.json.sample');
  return { ...actual, loadConfig: () => actual.loadConfig(sample) };
});

import { NovaActQAStudioStorageStack } from '../storage-stack';
import { NovaActQAStudioAuthStack } from '../auth-stack';
import { NovaActQAStudioWorkerStack } from '../worker-stack';
import { NovaActQAStudioLambdaStack } from '../lambda-stack';

const ENDPOINTS_DIR = path.join(__dirname, '..', '..', 'lambdas', 'endpoints');
const OWNERSHIP_CHECK = /require_resource_access|authorize_resource|\bresource_auth\b|\bpermissions_repo\b/;

type Resources = Record<string, any>;

function synth() {
  const app = new App();
  const common = { baseName: 'test', lambdaConcurrency: 5, networkAssertionBodyMaxBytes: 1_048_576 };
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
    ecsClusterArn: worker.cluster.clusterArn,
    recordingQueueUrl: worker.recordingQueueUrl,
    recordingQueueArn: worker.recordingQueueArn,
    wizardEventBusName: worker.wizardEventBus.eventBusName,
  });
  return {
    storage: Template.fromStack(storage).toJSON(),
    stacks: {
      worker: Template.fromStack(worker).toJSON(),
      lambdas: Template.fromStack(lambdas).toJSON(),
    },
  };
}

/** Handler source for `<module>.handler`, or undefined when not an endpoints handler. */
function handlerSource(handler: string): string | undefined {
  const module = handler.replace(/\.[^.]+$/, '').replace(/\./g, '/');
  for (const candidate of [`${module}.py`, path.join(module, 'handler.py')]) {
    const file = path.join(ENDPOINTS_DIR, candidate);
    if (fs.existsSync(file)) return fs.readFileSync(file, 'utf-8');
  }
  return undefined;
}

function actionsOf(document: any): string[] {
  return (document?.Statement ?? [])
    .filter((s: any) => s.Effect === 'Allow')
    .flatMap((s: any) => [].concat(s.Action));
}

/** Actions from storage-stack managed policies, keyed by the export name other stacks import. */
function importedPolicyActions(storage: any): Record<string, string[]> {
  const byExport: Record<string, string[]> = {};
  for (const output of Object.values<any>(storage.Outputs ?? {})) {
    const ref = output.Value?.Ref;
    const resource = ref && storage.Resources[ref];
    if (output.Export?.Name && resource?.Type === 'AWS::IAM::ManagedPolicy') {
      byExport[output.Export.Name] = actionsOf(resource.Properties.PolicyDocument);
    }
  }
  return byExport;
}

/** All actions a role is allowed: inline AWS::IAM::Policy + attached managed policies. */
function roleActions(resources: Resources, roleId: string, imported: Record<string, string[]>): string[] {
  const inline = Object.values<any>(resources)
    .filter(r => r.Type === 'AWS::IAM::Policy'
      && (r.Properties.Roles ?? []).some((x: any) => x.Ref === roleId))
    .flatMap(r => actionsOf(r.Properties.PolicyDocument));
  const managed = (resources[roleId].Properties.ManagedPolicyArns ?? []).flatMap((arn: any) => {
    if (arn['Fn::ImportValue']) return imported[arn['Fn::ImportValue']] ?? [];
    if (arn.Ref && resources[arn.Ref]?.Type === 'AWS::IAM::ManagedPolicy') {
      return actionsOf(resources[arn.Ref].Properties.PolicyDocument);
    }
    return [];
  });
  return [...inline, ...managed];
}

interface Checked { stack: string; handler: string; tableName: boolean; getItem: boolean }

function checkedLambdas(): Checked[] {
  const { storage, stacks } = synth();
  const imported = importedPolicyActions(storage);
  const checked: Checked[] = [];
  for (const [stack, template] of Object.entries(stacks)) {
    const resources: Resources = template.Resources;
    for (const fn of Object.values<any>(resources)) {
      if (fn.Type !== 'AWS::Lambda::Function') continue;
      const source = handlerSource(fn.Properties.Handler ?? '');
      if (!source || !OWNERSHIP_CHECK.test(source)) continue;
      const roleId = fn.Properties.Role?.['Fn::GetAtt']?.[0];
      checked.push({
        stack,
        handler: fn.Properties.Handler,
        tableName: Boolean(fn.Properties.Environment?.Variables?.TABLE_NAME),
        getItem: Boolean(roleId) && roleActions(resources, roleId, imported).includes('dynamodb:GetItem'),
      });
    }
  }
  return checked;
}

describe('Lambdas that run the team ownership check', () => {
  const checked = checkedLambdas();

  it('are found in both the lambdas and worker stacks', () => {
    const handlers = checked.map(c => `${c.stack}:${c.handler}`);
    // Sanity anchors: if these disappear, the handler mapping above broke.
    expect(handlers).toEqual(expect.arrayContaining([
      'lambdas:create_step.handler',
      'lambdas:get_usecase_secret_value.handler',
      'worker:create_schedule.handler',
      'worker:restart_wizard.handler',
    ]));
  });

  it('have TABLE_NAME in their environment', () => {
    expect(checked.filter(c => !c.tableName).map(c => `${c.stack}:${c.handler}`)).toEqual([]);
  });

  it('have a role that allows dynamodb:GetItem', () => {
    expect(checked.filter(c => !c.getItem).map(c => `${c.stack}:${c.handler}`)).toEqual([]);
  });
});
