/**
 * stop_execution Lambda: MicroVM terminate wiring.
 *
 * Synthesizes the stacks offline (config from configuration.json.sample) and
 * asserts the stop Lambda carries MICROVM_IMAGE_ARN and the IAM statements
 * TerminateMicrovm needs (TerminateMicrovm + GetMicrovm on the image ARN and
 * on the account's microvm resources) in ONE policy resource, and that the
 * ECS StopTask grant and env are gone.
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
let stopFn: any;
let stopRoleId: string;
let imageId: string;

beforeAll(() => {
  worker = synthStacks().worker;
  json = Template.fromStack(worker).toJSON() as typeof json;
  stopFn = Object.values(json.Resources).find(
    (r) => r.Type === 'AWS::Lambda::Function' && r.Properties.Handler === 'stop_execution.handler',
  );
  stopRoleId = stopFn.Properties.Role['Fn::GetAtt'][0];
  imageId = Object.keys(Template.fromStack(worker).findResources('AWS::Lambda::MicrovmImage'))[0];
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

describe('stop_execution Lambda environment', () => {
  test('MICROVM_IMAGE_ARN points at the worker image', () => {
    expect(stopFn.Properties.Environment.Variables.MICROVM_IMAGE_ARN).toEqual({ 'Fn::GetAtt': [imageId, 'ImageArn'] });
  });

  test('only TABLE_NAME and MICROVM_IMAGE_ARN (plus the base-stack default); no ECS env', () => {
    expect(Object.keys(stopFn.Properties.Environment.Variables).sort()).toEqual([
      'MICROVM_IMAGE_ARN', 'NETWORK_ASSERTION_BODY_MAX_BYTES', 'TABLE_NAME',
    ]);
  });
});

describe('stop_execution Lambda IAM for TerminateMicrovm', () => {
  test('TerminateMicrovm + GetMicrovm on the image ARN', () => {
    const statements = statementsWithAction(json.Resources, stopRoleId, 'lambda:TerminateMicrovm').filter((s) =>
      JSON.stringify(s.Resource).includes('ImageArn'),
    );
    expect(statements).toHaveLength(1);
    expect([].concat(statements[0].Action).sort()).toEqual(['lambda:GetMicrovm', 'lambda:TerminateMicrovm']);
    expect(JSON.stringify(statements[0].Resource)).toContain(imageId);
  });

  test("TerminateMicrovm + GetMicrovm on the account's microvm resources (authorisation target unconfirmed by the spike)", () => {
    const statements = statementsWithAction(json.Resources, stopRoleId, 'lambda:TerminateMicrovm').filter((s) =>
      JSON.stringify(s.Resource).includes(':microvm/*'),
    );
    expect(statements).toHaveLength(1);
    expect([].concat(statements[0].Action).sort()).toEqual(['lambda:GetMicrovm', 'lambda:TerminateMicrovm']);
    const resourceText = JSON.stringify(statements[0].Resource);
    expect(resourceText).toContain('arn:aws:lambda:');
    expect(resourceText).toContain('AWS::Region');
    expect(resourceText).toContain('AWS::AccountId');
  });

  test('no MicroVM action beyond Terminate/Get is granted', () => {
    const actions = policiesOf(json.Resources, stopRoleId)
      .flatMap((p) => p.Properties.PolicyDocument.Statement)
      .flatMap((s: any) => [].concat(s.Action) as string[])
      .filter((a) => a.startsWith('lambda:'));
    expect(new Set(actions)).toEqual(new Set(['lambda:TerminateMicrovm', 'lambda:GetMicrovm']));
  });

  test('all MicroVM statements live in one AWS::IAM::Policy resource', () => {
    const microvmPolicies = policiesOf(json.Resources, stopRoleId).filter((p) =>
      JSON.stringify(p.Properties.PolicyDocument).includes('lambda:TerminateMicrovm'),
    );
    expect(microvmPolicies).toHaveLength(1);
  });

  test('no ECS grant is left', () => {
    const actions = policiesOf(json.Resources, stopRoleId)
      .flatMap((p) => p.Properties.PolicyDocument.Statement)
      .flatMap((s: any) => [].concat(s.Action) as string[]);
    expect(actions.filter((a) => a.startsWith('ecs:'))).toEqual([]);
  });
});
