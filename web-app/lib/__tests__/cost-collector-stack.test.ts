/**
 * Worker stack: the daily `cost_collector` Lambda (design:
 * .kiro/docs/cost-allocation/design.md, task 05).
 *
 * With `costAllocation.enabled` (sample config) the template carries the
 * function (15 min / 1024 MB, the env-var contract task 12's Python reads),
 * the EventBridge schedule with the configured expression, ONE inline policy
 * with exactly the IAM the committed handler needs, the table read + write
 * managed policies, and the `Errors` alarm wired to the stack's notification
 * topic. The run report is logged as a dict under the JSON log format, so two
 * metric filters on the function's log group publish `unmetered_usd` and
 * `billed_usd`, and a math-expression alarm fires when the unmetered share
 * exceeds half the bill. With `enabled: false` none of it exists and the stack
 * is byte-for-byte the pre-feature worker stack.
 *
 * Two config variants in one jest file: `mock`-prefixed variable in the
 * `jest.mock('../config')` factory plus `jest.isolateModules`
 * (worker-stack-vpc.test.ts pattern).
 */
import * as path from 'path';
import { Template } from 'aws-cdk-lib/assertions';

const mockConfigOverrides: { costAllocation?: Record<string, unknown> } = {};

jest.mock('../config', () => {
  const actual = jest.requireActual('../config');
  const sample = require('path').join(__dirname, '..', '..', 'configuration.json.sample');
  return {
    ...actual,
    loadConfig: () => {
      const base = actual.loadConfig(sample);
      return { ...base, costAllocation: { ...base.costAllocation, ...(mockConfigOverrides.costAllocation ?? {}) } };
    },
  };
});

type Resources = Record<string, any>;

function synthWorker(costAllocation?: Record<string, unknown>): { Resources: Resources; Outputs: Record<string, any> } {
  mockConfigOverrides.costAllocation = costAllocation;
  let json: any;
  jest.isolateModules(() => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { synthStacks } = require('./synthStacks');
    json = Template.fromStack(synthStacks().worker).toJSON();
  });
  return json;
}

const HANDLER = 'cost_collector.handler';
const SAMPLE = path.join(__dirname, '..', '..', 'configuration.json.sample');

function lambdaByHandler(resources: Resources, handler: string): [string, any] | undefined {
  return Object.entries(resources).find(([, r]) => r.Type === 'AWS::Lambda::Function' && r.Properties.Handler === handler);
}

/** Allow statements of every inline AWS::IAM::Policy attached to `roleId`. */
function inlinePolicies(resources: Resources, roleId: string): any[] {
  return Object.values<any>(resources).filter(
    (r) => r.Type === 'AWS::IAM::Policy' && (r.Properties.Roles ?? []).some((x: any) => x.Ref === roleId),
  );
}

function statementsOf(policy: any): { actions: string[]; resource: any; condition: any }[] {
  return (policy.Properties.PolicyDocument.Statement ?? [])
    .filter((s: any) => s.Effect === 'Allow')
    .map((s: any) => ({ actions: [].concat(s.Action).sort(), resource: s.Resource, condition: s.Condition }));
}

describe('costAllocation.enabled (sample config)', () => {
  let json: ReturnType<typeof synthWorker>;
  let fnId: string;
  let fn: any;
  let roleId: string;

  beforeAll(() => {
    json = synthWorker();
    const found = lambdaByHandler(json.Resources, HANDLER);
    if (!found) throw new Error(`no Lambda with handler ${HANDLER}`);
    [fnId, fn] = found;
    roleId = fn.Properties.Role['Fn::GetAtt'][0];
  });

  test('the sample config enables the feature (this describe exercises the enabled path)', () => {
    const { loadConfig } = jest.requireActual('../config');
    expect(loadConfig(SAMPLE).costAllocation.enabled).toBe(true);
  });

  test('function: 15 min, 1024 MB, Python 3.13 on ARM, one per stack', () => {
    expect(fn.Properties.Timeout).toBe(900);
    expect(fn.Properties.MemorySize).toBe(1024);
    expect(fn.Properties.Runtime).toBe('python3.13');
    expect(fn.Properties.Architectures).toEqual(['arm64']);
    expect(fn.Properties.FunctionName).toBe('test-costcollector');
    expect(Object.values(json.Resources).filter((r: any) => r.Type === 'AWS::Lambda::Function' && r.Properties.Handler === HANDLER)).toHaveLength(1);
  });

  test('environment is exactly the contract the handler and the compute source read', () => {
    const env = fn.Properties.Environment.Variables;
    expect(Object.keys(env).sort()).toEqual([
      'COMPUTE_CE_COMPUTE_USAGE_TYPE_PREFIXES',
      'COMPUTE_CE_SERVICE',
      'COMPUTE_CE_SNAPSHOT_USAGE_TYPE_PREFIXES',
      'COMPUTE_COST_ENABLED',
      'LOOKBACK_DAYS',
      'NETWORK_ASSERTION_BODY_MAX_BYTES', // injected into every Lambda by createPythonLambda
      'NOVA_ACT_CE_SERVICE_NAME',
      'S3_BUCKET',
      'TABLE_NAME',
    ]);
    expect(env.LOOKBACK_DAYS).toBe('3');
    expect(env.NOVA_ACT_CE_SERVICE_NAME).toBe('NovaAct');
    expect(env.COMPUTE_COST_ENABLED).toBe('true');
    expect(env.COMPUTE_CE_SERVICE).toBe('AWS Lambda');
    expect(env.COMPUTE_CE_COMPUTE_USAGE_TYPE_PREFIXES).toBe('Lambda-MicroVM-vCPU-Second,Lambda-MicroVM-Memory-GB-Second');
    expect(env.COMPUTE_CE_SNAPSHOT_USAGE_TYPE_PREFIXES).toBe(
      'Lambda-MicroVM-Snapshot-Read-GB,Lambda-MicroVM-Snapshot-Storage-GB-Hour,Lambda-MicroVM-Snapshot-Write-GB',
    );
    // References, not literals: the table is imported from the storage stack, the bucket is stack-local.
    expect(JSON.stringify(env.TABLE_NAME)).toMatch(/Fn::ImportValue|Ref/);
    expect(JSON.stringify(env.S3_BUCKET)).toMatch(/Ref/);
  });

  test('config values flow into the environment', () => {
    const variant = synthWorker({
      lookbackDays: 7,
      novaActServiceName: 'Amazon Nova Act',
      compute: {
        enabled: false,
        ceService: 'Lambda',
        ceComputeUsageTypePrefixes: ['A', 'B'],
        ceSnapshotUsageTypePrefixes: ['C'],
      },
    });
    const env = lambdaByHandler(variant.Resources, HANDLER)![1].Properties.Environment.Variables;
    expect(env.LOOKBACK_DAYS).toBe('7');
    expect(env.NOVA_ACT_CE_SERVICE_NAME).toBe('Amazon Nova Act');
    expect(env.COMPUTE_COST_ENABLED).toBe('false');
    expect(env.COMPUTE_CE_SERVICE).toBe('Lambda');
    expect(env.COMPUTE_CE_COMPUTE_USAGE_TYPE_PREFIXES).toBe('A,B');
    expect(env.COMPUTE_CE_SNAPSHOT_USAGE_TYPE_PREFIXES).toBe('C');
  });

  test('schedule: one rule with the configured expression targeting the function', () => {
    const rules = Object.values<any>(json.Resources).filter(
      (r) => r.Type === 'AWS::Events::Rule' && JSON.stringify(r.Properties.Targets ?? []).includes(`"${fnId}"`),
    );
    expect(rules).toHaveLength(1);
    expect(rules[0].Properties.ScheduleExpression).toBe('cron(0 6 * * ? *)');
    expect(rules[0].Properties.State).toBe('ENABLED');
    expect(rules[0].Properties.Name).toBe('test-cost-collector');
    expect(rules[0].Properties.Description).toMatch(/^[\x20-\x7E]+$/); // ASCII only
    // EventBridge may invoke the function.
    const permissions = Object.values<any>(json.Resources).filter(
      (r) => r.Type === 'AWS::Lambda::Permission' && r.Properties.FunctionName?.['Fn::GetAtt']?.[0] === fnId,
    );
    expect(permissions).toHaveLength(1);
    expect(permissions[0].Properties.Principal).toBe('events.amazonaws.com');
  });

  test('a different scheduleUtc lands on the rule', () => {
    const variant = synthWorker({ scheduleUtc: 'rate(12 hours)' });
    const rule = Object.values<any>(variant.Resources).find((r) => r.Type === 'AWS::Events::Rule' && r.Properties.Name === 'test-cost-collector');
    expect(rule.Properties.ScheduleExpression).toBe('rate(12 hours)');
  });

  test('table access: the read and write managed policies from the storage stack, no full access', () => {
    const managed = (json.Resources[roleId].Properties.ManagedPolicyArns ?? []).map((a: any) => JSON.stringify(a));
    expect(managed.filter((a: string) => /TableReadPolicy|tableReadPolicy|table-read/i.test(a))).toHaveLength(1);
    expect(managed.filter((a: string) => /TableWritePolicy|tableWritePolicy|table-write/i.test(a))).toHaveLength(1);
    expect(managed.filter((a: string) => /FullAccess|full-access/i.test(a))).toHaveLength(0);
  });

  test('exactly one inline policy (createNewPoliciesWithAddToRolePolicy) with exactly the statements the handler needs', () => {
    const policies = inlinePolicies(json.Resources, roleId);
    expect(policies).toHaveLength(1);
    const statements = statementsOf(policies[0]);
    expect(statements).toHaveLength(4);

    const billing = statements.find((s) => s.actions.includes('ce:GetCostAndUsage'))!;
    expect(billing.actions).toEqual(['ce:GetCostAndUsage', 'nova-act:ListActs', 'nova-act:ListWorkflowDefinitions', 'pricing:GetProducts']);
    expect(billing.resource).toBe('*');

    const objects = statements.find((s) => s.actions.includes('s3:PutObject'))!;
    expect(objects.actions).toEqual(['s3:GetObject', 's3:PutObject']);
    const objectArn = JSON.stringify(objects.resource);
    expect(objectArn).toContain('/cost_allocation/*');
    expect(objectArn).toMatch(/Fn::GetAtt.*Arn/); // the stack's artefacts bucket, not a literal
    expect(objectArn).not.toContain('"*"');

    const list = statements.find((s) => s.actions.includes('s3:ListBucket'))!;
    expect(list.actions).toEqual(['s3:ListBucket']);
    expect(JSON.stringify(list.resource)).toMatch(/Fn::GetAtt.*Arn/);
    expect(JSON.stringify(list.resource)).not.toContain('/cost_allocation');
    expect(list.condition).toEqual({ StringLike: { 's3:prefix': 'cost_allocation/*' } });

    const invoke = statements.find((s) => s.actions.includes('lambda:InvokeFunction'))!;
    expect(invoke.actions).toEqual(['lambda:InvokeFunction']);
    // Own ARN built from the function name, never a Ref/GetAtt on the function (role <-> function cycle).
    const invokeArn = JSON.stringify(invoke.resource);
    expect(invokeArn).toContain(':function:test-costcollector');
    expect(invokeArn).not.toContain(fnId);
  });

  test('no statement grants anything beyond the four API families', () => {
    const actions = inlinePolicies(json.Resources, roleId).flatMap(statementsOf).flatMap((s) => s.actions);
    expect(actions.filter((a) => !/^(ce|pricing|nova-act|s3|lambda):/.test(a))).toEqual([]);
    expect(actions).not.toContain('s3:DeleteObject');
    expect(actions.filter((a) => a.endsWith('*'))).toEqual([]);
  });

  test('Errors alarm: sum >= 1 over one day, missing data not breaching, to the notification topic', () => {
    const alarms = Object.values<any>(json.Resources).filter(
      (r) => r.Type === 'AWS::CloudWatch::Alarm' && JSON.stringify(r.Properties.Dimensions ?? []).includes(`"${fnId}"`),
    );
    expect(alarms).toHaveLength(1);
    const alarm = alarms[0].Properties;
    expect(alarm.Namespace).toBe('AWS/Lambda');
    expect(alarm.MetricName).toBe('Errors');
    expect(alarm.Statistic).toBe('Sum');
    expect(alarm.Period).toBe(86400);
    expect(alarm.EvaluationPeriods).toBe(1);
    expect(alarm.Threshold).toBe(1);
    expect(alarm.ComparisonOperator).toBe('GreaterThanOrEqualToThreshold');
    expect(alarm.TreatMissingData).toBe('notBreaching');
    expect(alarm.AlarmName).toBe('test-cost-collector-errors');
    expect(alarm.AlarmDescription).toMatch(/^[\x20-\x7E]+$/);
    // Same topic the reconciled-executions alarm uses (the stack's notification topic).
    const topicIds = Object.keys(json.Resources).filter((id) => json.Resources[id].Type === 'AWS::SNS::Topic');
    expect(topicIds).toHaveLength(1);
    expect(alarm.AlarmActions).toEqual([{ Ref: topicIds[0] }]);
  });

  test('log retention is 5 days like every other Lambda of the stack', () => {
    const retention = Object.values<any>(json.Resources).find(
      (r) => r.Type === 'Custom::LogRetention' && JSON.stringify(r.Properties.LogGroupName).includes(`"${fnId}"`),
    );
    expect(retention.Properties.RetentionInDays).toBe(5);
  });

  test('JSON log format so the run report dict is emitted as a JSON object under message', () => {
    expect(fn.Properties.LoggingConfig).toEqual({ LogFormat: 'JSON' });
    // Opt-in for this function only: the other Lambdas keep the runtime default (TEXT).
    const others = Object.values<any>(json.Resources).filter(
      (r) => r.Type === 'AWS::Lambda::Function' && r.Properties.Handler !== HANDLER && r.Properties.LoggingConfig,
    );
    expect(others).toHaveLength(0);
  });

  test('metric filters: unmetered and billed USD from the cost_collector.run log line', () => {
    const retentionId = Object.keys(json.Resources).find(
      (id) => json.Resources[id].Type === 'Custom::LogRetention' && JSON.stringify(json.Resources[id].Properties.LogGroupName).includes(`"${fnId}"`),
    );
    const filters = Object.values<any>(json.Resources).filter((r) => r.Type === 'AWS::Logs::MetricFilter');
    expect(filters).toHaveLength(2);
    const byName = Object.fromEntries(filters.map((f) => [f.Properties.MetricTransformations[0].MetricName, f]));
    expect(Object.keys(byName).sort()).toEqual(['BilledUsd', 'UnmeteredUsd']);
    for (const [name, field] of [['UnmeteredUsd', '$.message.unmetered_usd'], ['BilledUsd', '$.message.billed_usd']]) {
      const f = byName[name];
      expect(f.Properties.FilterPattern).toBe('{ $.message.event = "cost_collector.run" }');
      expect(f.Properties.MetricTransformations).toHaveLength(1);
      expect(f.Properties.MetricTransformations[0].MetricNamespace).toBe('QAStudio/CostAllocation');
      expect(f.Properties.MetricTransformations[0].MetricValue).toBe(field);
      // The log group is created by the Custom::LogRetention resource (PutMetricFilter fails on a
      // missing group): the name must come from that resource, which orders the filter after it.
      expect(f.Properties.LogGroupName).toEqual({ 'Fn::GetAtt': [retentionId, 'LogGroupName'] });
    }
    // No IAM for metric filters.
    const filterIds = Object.keys(json.Resources).filter((id) => json.Resources[id].Type === 'AWS::Logs::MetricFilter');
    const policyText = JSON.stringify(Object.values<any>(json.Resources).filter((r) => r.Type === 'AWS::IAM::Policy'));
    for (const id of filterIds) expect(policyText).not.toContain(id);
  });

  test('unmetered alarm: IF(unmetered > 0.5 * billed) over one day, missing data not breaching, same topic', () => {
    const alarm = Object.values<any>(json.Resources).find(
      (r) => r.Type === 'AWS::CloudWatch::Alarm' && r.Properties.AlarmName === 'test-cost-collector-unmetered',
    );
    expect(alarm).toBeDefined();
    const p = alarm.Properties;
    expect(p.AlarmDescription).toMatch(/^[\x20-\x7E]+$/);
    expect(p.EvaluationPeriods).toBe(1);
    expect(p.Threshold).toBe(1);
    expect(p.ComparisonOperator).toBe('GreaterThanOrEqualToThreshold');
    expect(p.TreatMissingData).toBe('notBreaching');
    expect(p.Metrics).toHaveLength(3);
    const expression = p.Metrics.find((m: any) => m.Expression);
    expect(expression.Expression).toBe('IF(unmetered > 0.5 * billed, 1, 0)');
    expect(expression.ReturnData).toBe(true);
    const inputs = p.Metrics.filter((m: any) => m.MetricStat);
    expect(inputs.map((m: any) => m.Id).sort()).toEqual(['billed', 'unmetered']);
    for (const m of inputs) {
      expect(m.ReturnData).toBe(false);
      expect(m.MetricStat.Stat).toBe('Sum');
      expect(m.MetricStat.Period).toBe(86400);
      expect(m.MetricStat.Metric.Namespace).toBe('QAStudio/CostAllocation');
      expect(m.MetricStat.Metric.MetricName).toBe(m.Id === 'billed' ? 'BilledUsd' : 'UnmeteredUsd');
    }
    const topicIds = Object.keys(json.Resources).filter((id) => json.Resources[id].Type === 'AWS::SNS::Topic');
    expect(p.AlarmActions).toEqual([{ Ref: topicIds[0] }]);
  });

  test('adds a bounded number of resources to the worker stack', () => {
    const disabled = synthWorker({ enabled: false });
    const added = Object.keys(json.Resources).length - Object.keys(disabled.Resources).length;
    // function, role, inline policy, log retention, rule, permission, errors alarm,
    // two metric filters, unmetered alarm
    expect(added).toBe(10);
  });
});

describe('costAllocation.enabled = false', () => {
  let json: ReturnType<typeof synthWorker>;

  beforeAll(() => {
    json = synthWorker({ enabled: false });
  });

  test('no cost collector function, rule, alarm or policy', () => {
    expect(lambdaByHandler(json.Resources, HANDLER)).toBeUndefined();
    const text = JSON.stringify(json);
    expect(text).not.toContain('cost_collector');
    expect(text).not.toContain('cost-collector');
    expect(text).not.toContain('cost_allocation');
    expect(text).not.toContain('ce:GetCostAndUsage');
    expect(text).not.toContain('pricing:GetProducts');
    expect(text).not.toContain('QAStudio/CostAllocation');
    expect(Object.values<any>(json.Resources).filter((r) => r.Type === 'AWS::Logs::MetricFilter')).toHaveLength(0);
  });

  test('the rest of the stack is unchanged (the other Lambdas and the image are still there)', () => {
    expect(Object.values<any>(json.Resources).filter((r) => r.Type === 'AWS::Lambda::MicrovmImage')).toHaveLength(1);
    expect(lambdaByHandler(json.Resources, 'aggregate_execution.handler')).toBeDefined();
    expect(lambdaByHandler(json.Resources, 'reconcile_executions.handler')).toBeDefined();
  });
});
