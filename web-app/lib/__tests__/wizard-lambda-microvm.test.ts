/**
 * Wizard Lambdas on the MicroVM runner (phase 2, task 11).
 *
 * Synthesizes the stacks offline (config from configuration.json.sample) and
 * asserts:
 * - start_wizard_session carries MICROVM_* + MAX_WIZARD_SESSION_MINUTES, no
 *   ECS env, and the RunMicrovm IAM set (RunMicrovm + GetMicrovmImage on the
 *   image ARN, RunMicrovm on the account's microvm resources,
 *   PassNetworkConnector on the managed connectors, PassRole on the VM
 *   execution role) in ONE policy resource — and no ecs:RunTask any more;
 * - terminate_wizard_session carries MICROVM_IMAGE_ARN and TerminateMicrovm +
 *   GetMicrovm on the image ARN and the microvm resources in ONE policy;
 * - both keep DynamoDB read/write (running_executions uses DeleteItem).
 */
import { App } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';

jest.mock('../config', () => {
  const actual = jest.requireActual('../config');
  const sample = require('path').join(__dirname, '..', '..', 'configuration.json.sample');
  return { ...actual, loadConfig: () => actual.loadConfig(sample) };
});

import { synthStacks } from './synthStacks';
import { NovaActQAStudioStorageStack } from '../storage-stack';
import { NovaActQAStudioAuthStack } from '../auth-stack';
import { NovaActQAStudioWorkerStack } from '../worker-stack';

type Resources = Record<string, any>;

let worker: NovaActQAStudioWorkerStack;
let json: { Resources: Resources };
let startFn: any;
let startRoleId: string;
let terminateFn: any;
let terminateRoleId: string;

function lambdaByHandler(resources: Resources, handler: string): any {
  return Object.values(resources).find(
    (r) => r.Type === 'AWS::Lambda::Function' && r.Properties.Handler === handler,
  );
}

beforeAll(() => {
  worker = synthStacks().worker;
  json = Template.fromStack(worker).toJSON() as typeof json;
  startFn = lambdaByHandler(json.Resources, 'start_wizard_session.handler');
  startRoleId = startFn.Properties.Role['Fn::GetAtt'][0];
  terminateFn = lambdaByHandler(json.Resources, 'terminate_wizard_session.handler');
  terminateRoleId = terminateFn.Properties.Role['Fn::GetAtt'][0];
});

/** AWS::IAM::Policy resources attached to the role. */
function policiesOf(resources: Resources, roleId: string): any[] {
  return Object.values(resources).filter(
    (r) => r.Type === 'AWS::IAM::Policy' && (r.Properties.Roles ?? []).some((x: any) => x?.Ref === roleId),
  );
}

function statementsWithAction(resources: Resources, roleId: string, action: string): any[] {
  return policiesOf(resources, roleId)
    .flatMap((p) => p.Properties.PolicyDocument.Statement)
    .filter((s: any) => s.Effect === 'Allow' && [].concat(s.Action).includes(action as never));
}

function allActions(resources: Resources, roleId: string): string[] {
  return policiesOf(resources, roleId)
    .flatMap((p) => p.Properties.PolicyDocument.Statement)
    .filter((s: any) => s.Effect === 'Allow')
    .flatMap((s: any) => [].concat(s.Action));
}

describe('start_wizard_session Lambda environment', () => {
  test('MICROVM_* point at the image, its active version, the execution role and the log group', () => {
    const env = startFn.Properties.Environment.Variables;
    const imageId = Object.keys(Template.fromStack(worker).findResources('AWS::Lambda::MicrovmImage'))[0];
    expect(env.MICROVM_IMAGE_ARN).toEqual({ 'Fn::GetAtt': [imageId, 'ImageArn'] });
    expect(env.MICROVM_IMAGE_VERSION).toEqual({ 'Fn::GetAtt': [imageId, 'LatestActiveImageVersion'] });
    expect(env.MICROVM_EXECUTION_ROLE_ARN).toEqual({
      'Fn::GetAtt': [worker.getLogicalId(worker.microvmExecutionRole.node.defaultChild as any), 'Arn'],
    });
    expect(env.MICROVM_LOG_GROUP).toEqual({
      Ref: worker.getLogicalId(worker.microvmLogGroup.node.defaultChild as any),
    });
  });

  test('MAX_WIZARD_SESSION_MINUTES follows the config (sample default: 240)', () => {
    expect(startFn.Properties.Environment.Variables.MAX_WIZARD_SESSION_MINUTES).toEqual('240');
  });

  test('keeps the bucket prefix and default region the payload needs; the ECS env is gone', () => {
    const env = startFn.Properties.Environment.Variables;
    expect(env.TABLE_NAME).toBeDefined();
    expect(env.S3_BUCKET_PREFIX).toBeDefined();
    expect(env.DEFAULT_REGION).toBeDefined();
    for (const key of ['ECS_CLUSTER', 'ECS_TASK_DEFINITION', 'SUBNET_ID', 'SECURITY_GROUP_ID']) {
      expect(env[key]).toBeUndefined();
    }
  });

  test('has the same timeout as the execute Lambda (RunMicrovm retries sleep up to 15 s)', () => {
    expect(startFn.Properties.Timeout).toEqual(30);
  });

  test('maxWizardSessionMinutes on the stack props sets MAX_WIZARD_SESSION_MINUTES', () => {
    const app = new App();
    const common = { baseName: 'test', lambdaConcurrency: 5, networkAssertionBodyMaxBytes: 1_048_576 };
    const storage = new NovaActQAStudioStorageStack(app, 'storage', { ...common });
    const auth = new NovaActQAStudioAuthStack(app, 'auth', { ...common, adminEmail: 'admin@example.com' });
    const stack = new NovaActQAStudioWorkerStack(app, 'worker', {
      ...common,
      table: storage.table,
      tableReadPolicy: storage.tableReadPolicy,
      tableWritePolicy: storage.tableWritePolicy,
      novaActApiKeySecret: storage.novaActApiKeySecret,
      workerCredentialsSecret: auth.workerCredentialsSecret,
      apiDeploymentStage: 'api',
      version: '0.0.0',
      maxWizardSessionMinutes: 120,
    });
    const fn = lambdaByHandler(Template.fromStack(stack).toJSON().Resources as Resources, 'start_wizard_session.handler');
    expect(fn.Properties.Environment.Variables.MAX_WIZARD_SESSION_MINUTES).toEqual('120');
  });
});

describe('start_wizard_session Lambda IAM for RunMicrovm', () => {
  test('RunMicrovm + GetMicrovmImage on the image ARN', () => {
    const statements = statementsWithAction(json.Resources, startRoleId, 'lambda:GetMicrovmImage');
    expect(statements).toHaveLength(1);
    expect([].concat(statements[0].Action).sort()).toEqual(['lambda:GetMicrovmImage', 'lambda:RunMicrovm']);
    expect(JSON.stringify(statements[0].Resource)).toContain('ImageArn');
  });

  test("RunMicrovm on the account's microvm resources", () => {
    const statements = statementsWithAction(json.Resources, startRoleId, 'lambda:RunMicrovm');
    const onMicrovms = statements.filter((s) => JSON.stringify(s.Resource).includes(':microvm/*'));
    expect(onMicrovms).toHaveLength(1);
    expect([].concat(onMicrovms[0].Action)).toEqual(['lambda:RunMicrovm']);
    const resourceText = JSON.stringify(onMicrovms[0].Resource);
    expect(resourceText).toContain('AWS::Region');
    expect(resourceText).toContain('AWS::AccountId');
  });

  test('PassNetworkConnector on the Lambda-managed connectors only', () => {
    const statements = statementsWithAction(json.Resources, startRoleId, 'lambda:PassNetworkConnector');
    expect(statements).toHaveLength(1);
    expect([].concat(statements[0].Action)).toEqual(['lambda:PassNetworkConnector']);
    const resourceText = JSON.stringify(statements[0].Resource);
    expect(resourceText).toContain(':aws:network-connector:aws-network-connector:*');
    expect(resourceText).toContain('AWS::Region');
    expect(resourceText).not.toContain('AWS::AccountId');
  });

  test('PassRole on the MicroVM execution role only, restricted to lambda.amazonaws.com', () => {
    const execRoleId = worker.getLogicalId(worker.microvmExecutionRole.node.defaultChild as any);
    const statements = statementsWithAction(json.Resources, startRoleId, 'iam:PassRole');
    expect(statements).toHaveLength(1);
    expect([].concat(statements[0].Action)).toEqual(['iam:PassRole']);
    expect(statements[0].Resource).toEqual({ 'Fn::GetAtt': [execRoleId, 'Arn'] });
    expect(statements[0].Condition).toEqual({ StringEquals: { 'iam:PassedToService': 'lambda.amazonaws.com' } });
  });

  test('all MicroVM statements live in one AWS::IAM::Policy resource', () => {
    const microvmPolicies = policiesOf(json.Resources, startRoleId).filter((p) =>
      JSON.stringify(p.Properties.PolicyDocument).includes('lambda:RunMicrovm'),
    );
    expect(microvmPolicies).toHaveLength(1);
    const actions = microvmPolicies[0].Properties.PolicyDocument.Statement.flatMap((s: any) => [].concat(s.Action));
    expect(actions).toEqual(expect.arrayContaining(['lambda:RunMicrovm', 'lambda:GetMicrovmImage', 'lambda:PassNetworkConnector', 'iam:PassRole']));
  });

  test('no ECS grant is left (RunTask, PassRole on the task roles)', () => {
    const actions = allActions(json.Resources, startRoleId);
    expect(actions.filter((a) => a.startsWith('ecs:'))).toEqual([]);
    // the only PassRole target is the MicroVM execution role (the ECS task roles no longer exist)
    const passRole = statementsWithAction(json.Resources, startRoleId, 'iam:PassRole');
    expect(passRole).toHaveLength(1);
    expect(JSON.stringify(passRole[0].Resource)).toContain(
      worker.getLogicalId(worker.microvmExecutionRole.node.defaultChild as any),
    );
  });

  test('keeps DynamoDB read/write on the table (RUNNING_EXECUTIONS put, execution update)', () => {
    const actions = allActions(json.Resources, startRoleId);
    expect(actions).toEqual(expect.arrayContaining(['dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:GetItem']));
  });
});

describe('terminate_wizard_session Lambda', () => {
  test('carries MICROVM_IMAGE_ARN next to the command channel env', () => {
    const env = terminateFn.Properties.Environment.Variables;
    const imageId = Object.keys(Template.fromStack(worker).findResources('AWS::Lambda::MicrovmImage'))[0];
    expect(env.MICROVM_IMAGE_ARN).toEqual({ 'Fn::GetAtt': [imageId, 'ImageArn'] });
    expect(env.TABLE_NAME).toBeDefined();
    expect(env.WIZARD_QUEUE_URL).toBeDefined();
    expect(env.WIZARD_EVENT_BUS_NAME).toBeDefined();
  });

  test('TerminateMicrovm + GetMicrovm on the image ARN and on the microvm resources, in one policy', () => {
    const policies = policiesOf(json.Resources, terminateRoleId).filter((p) =>
      JSON.stringify(p.Properties.PolicyDocument).includes('lambda:TerminateMicrovm'),
    );
    expect(policies).toHaveLength(1);
    const statements = policies[0].Properties.PolicyDocument.Statement.filter((s: any) =>
      [].concat(s.Action).includes('lambda:TerminateMicrovm' as never),
    );
    expect(statements).toHaveLength(2);
    for (const s of statements) {
      expect([].concat(s.Action).sort()).toEqual(['lambda:GetMicrovm', 'lambda:TerminateMicrovm']);
    }
    const resources = statements.map((s: any) => JSON.stringify(s.Resource));
    expect(resources.some((r: string) => r.includes('ImageArn'))).toBe(true);
    expect(resources.some((r: string) => r.includes(':microvm/*'))).toBe(true);
  });

  test('never got RunMicrovm or any ECS action', () => {
    const actions = allActions(json.Resources, terminateRoleId);
    expect(actions).not.toContain('lambda:RunMicrovm');
    expect(actions.filter((a) => a.startsWith('ecs:'))).toEqual([]);
  });

  test('keeps DynamoDB read/write on the table (GetItem for microvm_id, DeleteItem for the tracking record)', () => {
    const actions = allActions(json.Resources, terminateRoleId);
    expect(actions).toEqual(expect.arrayContaining(['dynamodb:GetItem', 'dynamodb:UpdateItem', 'dynamodb:DeleteItem']));
  });
});
