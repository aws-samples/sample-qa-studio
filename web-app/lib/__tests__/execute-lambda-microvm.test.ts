/**
 * execute_usecase Lambda: MicroVM launch wiring.
 *
 * Synthesizes the stacks offline (config from configuration.json.sample) and
 * asserts the execute Lambda carries the MICROVM_* env vars (and no ECS env)
 * and the IAM statements RunMicrovm needs (RunMicrovm + GetMicrovmImage on the
 * image ARN, RunMicrovm on the account's microvm resources, PassRole on the VM
 * execution role restricted to lambda.amazonaws.com) in ONE policy resource.
 */
import { Template } from 'aws-cdk-lib/assertions';

jest.mock('../config', () => {
  const actual = jest.requireActual('../config');
  const sample = require('path').join(__dirname, '..', '..', 'configuration.json.sample');
  return { ...actual, loadConfig: () => actual.loadConfig(sample) };
});

import { synthStacks } from './synthStacks';
import { NovaActQAStudioWorkerStack } from '../worker-stack';

type Resources = Record<string, any>;

let worker: NovaActQAStudioWorkerStack;
let json: { Resources: Resources };
let executeFn: any;
let executeRoleId: string;

beforeAll(() => {
  worker = synthStacks().worker;
  json = Template.fromStack(worker).toJSON() as typeof json;
  executeFn = Object.values(json.Resources).find(
    (r) => r.Type === 'AWS::Lambda::Function' && r.Properties.Handler === 'execute_usecase.handler',
  );
  executeRoleId = executeFn.Properties.Role['Fn::GetAtt'][0];
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

describe('execute_usecase Lambda environment', () => {
  test('MAX_EXECUTION_DURATION_MINUTES follows the config (sample: 60)', () => {
    expect(executeFn.Properties.Environment.Variables.MAX_EXECUTION_DURATION_MINUTES).toEqual('60');
  });

  test('MICROVM_* point at the image, its active version, the execution role and the log group', () => {
    const env = executeFn.Properties.Environment.Variables;
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

  test('no ECS env var and no WORKER_RUNTIME flag', () => {
    const env = executeFn.Properties.Environment.Variables;
    for (const key of ['ECS_CLUSTER', 'ECS_TASK_DEFINITION', 'SUBNET_ID', 'SECURITY_GROUP_ID', 'LOG_GROUP_NAME', 'LOG_STREAM_PREFIX', 'WORKER_RUNTIME']) {
      expect(env[key]).toBeUndefined();
    }
  });

  test('the Lambda keeps only what the MicroVM launch reads (plus the base-stack default)', () => {
    expect(Object.keys(executeFn.Properties.Environment.Variables).sort()).toEqual([
      'DEFAULT_REGION', 'MAX_EXECUTION_DURATION_MINUTES', 'MICROVM_EXECUTION_ROLE_ARN', 'MICROVM_IMAGE_ARN',
      'MICROVM_IMAGE_VERSION', 'MICROVM_LOG_GROUP', 'NETWORK_ASSERTION_BODY_MAX_BYTES', 'S3_BUCKET_PREFIX', 'TABLE_NAME',
    ]);
  });
});

describe('execute_usecase Lambda IAM for RunMicrovm', () => {
  test('RunMicrovm + GetMicrovmImage on the image ARN', () => {
    const statements = statementsWithAction(json.Resources, executeRoleId, 'lambda:GetMicrovmImage');
    expect(statements).toHaveLength(1);
    expect([].concat(statements[0].Action).sort()).toEqual(['lambda:GetMicrovmImage', 'lambda:RunMicrovm']);
    expect(JSON.stringify(statements[0].Resource)).toContain('ImageArn');
  });

  test("RunMicrovm on the account's microvm resources (authorisation target unconfirmed by the spike)", () => {
    const statements = statementsWithAction(json.Resources, executeRoleId, 'lambda:RunMicrovm');
    const onMicrovms = statements.filter((s) => JSON.stringify(s.Resource).includes(':microvm/*'));
    expect(onMicrovms).toHaveLength(1);
    expect([].concat(onMicrovms[0].Action)).toEqual(['lambda:RunMicrovm']);
    const resourceText = JSON.stringify(onMicrovms[0].Resource);
    expect(resourceText).toContain('arn:aws:lambda:');
    expect(resourceText).toContain('AWS::Region');
    expect(resourceText).toContain('AWS::AccountId');
  });

  test('PassRole on the MicroVM execution role only, restricted to lambda.amazonaws.com', () => {
    const execRoleId = worker.getLogicalId(worker.microvmExecutionRole.node.defaultChild as any);
    const statements = statementsWithAction(json.Resources, executeRoleId, 'iam:PassRole')
      .filter((s) => JSON.stringify(s.Resource).includes(execRoleId));
    expect(statements).toHaveLength(1);
    expect([].concat(statements[0].Action)).toEqual(['iam:PassRole']);
    expect(statements[0].Resource).toEqual({ 'Fn::GetAtt': [execRoleId, 'Arn'] });
    expect(statements[0].Condition).toEqual({ StringEquals: { 'iam:PassedToService': 'lambda.amazonaws.com' } });
  });

  test('PassNetworkConnector on the Lambda-managed connectors (RunMicrovm passes NO_INGRESS + the default INTERNET_EGRESS)', () => {
    // Found in the phase-1 dev run: without it RunMicrovm is denied with
    // "not authorized to perform: lambda:PassNetworkConnector on resource:
    // arn:aws:lambda:<region>:aws:network-connector:aws-network-connector:INTERNET_EGRESS".
    const statements = statementsWithAction(json.Resources, executeRoleId, 'lambda:PassNetworkConnector');
    expect(statements).toHaveLength(1);
    expect([].concat(statements[0].Action)).toEqual(['lambda:PassNetworkConnector']);
    const resourceText = JSON.stringify(statements[0].Resource);
    expect(resourceText).toContain(':aws:network-connector:aws-network-connector:*');
    expect(resourceText).toContain('AWS::Region');
    expect(resourceText).not.toContain('AWS::AccountId');
  });

  test('all MicroVM statements live in one AWS::IAM::Policy resource', () => {
    const microvmPolicies = policiesOf(json.Resources, executeRoleId).filter((p) =>
      JSON.stringify(p.Properties.PolicyDocument).includes('lambda:RunMicrovm'),
    );
    expect(microvmPolicies).toHaveLength(1);
    const actions = microvmPolicies[0].Properties.PolicyDocument.Statement.flatMap((s: any) => [].concat(s.Action));
    expect(actions).toEqual(expect.arrayContaining(['lambda:RunMicrovm', 'lambda:GetMicrovmImage', 'lambda:PassNetworkConnector', 'iam:PassRole']));
  });

  test('no ECS grant is left (RunTask, PassRole on the task roles)', () => {
    expect(statementsWithAction(json.Resources, executeRoleId, 'ecs:RunTask')).toEqual([]);
    const passRole = statementsWithAction(json.Resources, executeRoleId, 'iam:PassRole');
    expect(passRole).toHaveLength(1);
    expect(JSON.stringify(passRole[0].Resource)).toContain(worker.getLogicalId(worker.microvmExecutionRole.node.defaultChild as any));
  });
});
