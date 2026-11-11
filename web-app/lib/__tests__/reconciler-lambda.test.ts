/**
 * reconcile_executions Lambda: the scheduled MicroVM execution reconciler.
 *
 * Synthesizes the stacks offline (config from configuration.json.sample) and
 * asserts the worker stack carries the Lambda (env TABLE_NAME +
 * MICROVM_IMAGE_ARN, 60 s timeout), a rate(5 minutes) schedule Rule that
 * targets it, the ReconciledExecutions alarm (QAStudio/Worker, Sum > 0 over
 * one 5-minute period, NOT_BREACHING on missing data) wired to the
 * notification topic, and the IAM it needs (GetMicrovm on the image ARN and
 * the account's microvm resources, PutMetricData scoped to the namespace,
 * PutEvents on the default bus, table read + write managed policies) in ONE
 * inline policy resource.
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
let fnId: string;
let fn: any;
let roleId: string;
let imageId: string;

beforeAll(() => {
  worker = synthStacks().worker;
  json = Template.fromStack(worker).toJSON() as typeof json;
  [fnId, fn] = Object.entries(json.Resources).find(
    ([, r]) => r.Type === 'AWS::Lambda::Function' && r.Properties.Handler === 'reconcile_executions.handler',
  ) as [string, any];
  roleId = fn.Properties.Role['Fn::GetAtt'][0];
  imageId = Object.keys(Template.fromStack(worker).findResources('AWS::Lambda::MicrovmImage'))[0];
});

function policiesOf(roleLogicalId: string): any[] {
  return Object.values(json.Resources).filter(
    (r) => r.Type === 'AWS::IAM::Policy' && (r.Properties.Roles ?? []).some((x: any) => x?.Ref === roleLogicalId),
  );
}

function statementsWithAction(roleLogicalId: string, action: string): any[] {
  return policiesOf(roleLogicalId)
    .flatMap((p) => p.Properties.PolicyDocument.Statement)
    .filter((s: any) => s.Effect === 'Allow' && [].concat(s.Action).includes(action as never));
}

function refersTo(value: any, logicalId: string): boolean {
  return JSON.stringify(value).includes(`"${logicalId}"`);
}

describe('reconcile_executions Lambda', () => {
  test('exists with TABLE_NAME and MICROVM_IMAGE_ARN', () => {
    expect(fn).toBeDefined();
    const env = fn.Properties.Environment.Variables;
    expect(env.TABLE_NAME).toBeDefined();
    expect(env.MICROVM_IMAGE_ARN).toEqual({ 'Fn::GetAtt': [imageId, 'ImageArn'] });
  });

  test('has a 60 s timeout (≤ 50 GetMicrovm calls + DynamoDB writes per pass)', () => {
    expect(fn.Properties.Timeout).toEqual(60);
  });

  test('is not reachable through API Gateway (no API stack import of it)', () => {
    const outputs = (Template.fromStack(worker).toJSON() as any).Outputs ?? {};
    const exported = Object.values(outputs).filter((o: any) => o.Export && refersTo(o.Value, fnId));
    expect(exported).toHaveLength(0);
  });
});

describe('schedule', () => {
  let rule: any;
  beforeAll(() => {
    rule = Object.values(json.Resources).find(
      (r) => r.Type === 'AWS::Events::Rule' && r.Properties.ScheduleExpression !== undefined
        && (r.Properties.Targets ?? []).some((t: any) => refersTo(t.Arn, fnId)),
    );
  });

  test('a rate(5 minutes) rule targets the Lambda', () => {
    expect(rule).toBeDefined();
    expect(rule.Properties.ScheduleExpression).toEqual('rate(5 minutes)');
    expect(rule.Properties.State).toEqual('ENABLED');
    expect(rule.Properties.Name).toEqual('test-reconcile-executions');
    expect(rule.Properties.Targets).toHaveLength(1);
  });

  test('EventBridge may invoke the Lambda', () => {
    const permissions = Object.values(json.Resources).filter(
      (r) => r.Type === 'AWS::Lambda::Permission' && refersTo(r.Properties.FunctionName, fnId)
        && r.Properties.Principal === 'events.amazonaws.com',
    );
    expect(permissions).toHaveLength(1);
  });
});

describe('ReconciledExecutions alarm', () => {
  let alarm: any;
  beforeAll(() => {
    alarm = Object.values(json.Resources).find(
      (r) => r.Type === 'AWS::CloudWatch::Alarm' && r.Properties.MetricName === 'ReconciledExecutions',
    );
  });

  test('sums QAStudio/Worker ReconciledExecutions over one 5-minute period, > 0 breaches', () => {
    expect(alarm).toBeDefined();
    const p = alarm.Properties;
    expect(p.Namespace).toEqual('QAStudio/Worker');
    expect(p.Statistic).toEqual('Sum');
    expect(p.Period).toEqual(300);
    expect(p.Threshold).toEqual(0);
    expect(p.ComparisonOperator).toEqual('GreaterThanThreshold');
    expect(p.EvaluationPeriods).toEqual(1);
    expect(p.TreatMissingData).toEqual('notBreaching');
  });

  test('notifies the worker notification topic', () => {
    const topicId = Object.keys(Template.fromStack(worker).findResources('AWS::SNS::Topic', {
      Properties: { TopicName: 'test-notifications' },
    }))[0];
    expect(alarm.Properties.AlarmActions).toEqual([{ Ref: topicId }]);
  });
});

describe('IAM', () => {
  test('table read + write managed policies are attached', () => {
    const managed = json.Resources[roleId].Properties.ManagedPolicyArns ?? [];
    const text = JSON.stringify(managed);
    expect(text).toContain('ReadPolicy');
    expect(text).toContain('WritePolicy');
  });

  test('GetMicrovm on the image ARN and on the account microvm resources', () => {
    const statements = statementsWithAction(roleId, 'lambda:GetMicrovm');
    expect(statements).toHaveLength(2);
    const onImage = statements.find((s) => JSON.stringify(s.Resource).includes('ImageArn'));
    const onVms = statements.find((s) => JSON.stringify(s.Resource).includes(':microvm/*'));
    expect(onImage).toBeDefined();
    expect(JSON.stringify(onImage.Resource)).toContain(imageId);
    expect(onVms).toBeDefined();
    expect(JSON.stringify(onVms.Resource)).toContain('AWS::AccountId');
    for (const s of statements) expect([].concat(s.Action)).toEqual(['lambda:GetMicrovm']);
  });

  test('PutMetricData only in the QAStudio/Worker namespace', () => {
    const statements = statementsWithAction(roleId, 'cloudwatch:PutMetricData');
    expect(statements).toHaveLength(1);
    expect(statements[0].Resource).toEqual('*');
    expect(statements[0].Condition).toEqual({ StringEquals: { 'cloudwatch:namespace': 'QAStudio/Worker' } });
  });

  test('PutEvents on the default bus', () => {
    const statements = statementsWithAction(roleId, 'events:PutEvents');
    expect(statements).toHaveLength(1);
    expect(JSON.stringify(statements[0].Resource)).toContain(':event-bus/default');
  });

  test('no other lambda:/ecs:/s3: action is granted', () => {
    const actions = policiesOf(roleId)
      .flatMap((p) => p.Properties.PolicyDocument.Statement)
      .flatMap((s: any) => [].concat(s.Action) as string[])
      .filter((a) => /^(lambda|ecs|s3):/.test(a));
    expect(new Set(actions)).toEqual(new Set(['lambda:GetMicrovm']));
  });

  test('all custom statements live in one AWS::IAM::Policy resource', () => {
    expect(policiesOf(roleId)).toHaveLength(1);
  });
});

describe('is the only crash detector', () => {
  test('no ECS task-state-change rule remains', () => {
    const ecsRules = Object.values(json.Resources).filter(
      (r) => r.Type === 'AWS::Events::Rule'
        && JSON.stringify(r.Properties.EventPattern ?? {}).includes('aws.ecs'),
    );
    expect(ecsRules).toHaveLength(0);
  });

  test('no handle_task_state_change Lambda remains', () => {
    const handlers = Object.values(json.Resources)
      .filter((r) => r.Type === 'AWS::Lambda::Function')
      .map((r) => r.Properties.Handler as string);
    expect(handlers).not.toContain('handle_task_state_change.handler');
  });
});

describe('stack budget', () => {
  test('stays under the CloudFormation resource limit with headroom', () => {
    expect(Object.keys(json.Resources).length).toBeLessThan(480);
  });
});
