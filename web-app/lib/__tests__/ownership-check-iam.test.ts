/**
 * IAM guards on the synthesized Lambda roles.
 *
 * 1. Every endpoint Lambda whose handler runs the team ownership check
 * (require_resource_access / authorize_resource / permissions_repo) must be
 * able to read the table. The resolvers do GetItem on the use case / app /
 * execution / override records (and Query for shared-access grants); without
 * TABLE_NAME and dynamodb:GetItem the check throws and the route returns 500.
 *
 * 2. Every Lambda that vends presigned S3 URLs must hold the S3 permission the
 * URL needs (a presigned URL carries the signer's rights). Without it S3
 * answers every PUT/GET on the URL with 403 while the endpoint returns 200.
 *
 * 3. Secrets Manager scoping (see below).
 *
 * 4. Every Lambda that can reach `GetMicrovm` (it imports
 * `execution_transitions`, whose terminal transition records the VM's
 * start/termination time, or calls `get_microvm` itself) must hold
 * `lambda:GetMicrovm` on the worker image ARN and the account's microvm
 * resources. The helper never raises, so a missing grant shows up only as a
 * WARNING and execution records without `microvm_started_at`.
 *
 * Synthesizes storage + auth + worker + lambdas the way bin/cdk.ts does
 * (offline, config from configuration.json.sample) and checks the templates.
 */
import * as fs from 'fs';
import * as path from 'path';
import { Template } from 'aws-cdk-lib/assertions';

jest.mock('../config', () => {
  const actual = jest.requireActual('../config');
  const sample = require('path').join(__dirname, '..', '..', 'configuration.json.sample');
  return { ...actual, loadConfig: () => actual.loadConfig(sample) };
});

import { synthStacks } from './synthStacks';

const ENDPOINTS_DIR = path.join(__dirname, '..', '..', 'lambdas', 'endpoints');
const OWNERSHIP_CHECK = /require_resource_access|authorize_resource|\bresource_auth\b|\bpermissions_repo\b/;

type Resources = Record<string, any>;

function synth() {
  const { storage, worker, lambdas } = synthStacks();
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

/** Handler source plus the shared modules that sign URLs on its behalf. */
function signingSource(source: string): string {
  return /\bartifact_upload\b/.test(source)
    ? source + fs.readFileSync(path.join(ENDPOINTS_DIR, 'artifact_upload.py'), 'utf-8')
    : source;
}

interface Presigner { stack: string; handler: string; missing: string[] }

/** Lambdas whose code presigns put_object / get_object, with the S3 actions their role lacks. */
function presigningLambdas(): Presigner[] {
  const { storage, stacks } = synthesized;
  const imported = importedPolicyActions(storage);
  const found: Presigner[] = [];
  for (const [stack, template] of Object.entries(stacks)) {
    const resources: Resources = template.Resources;
    for (const fn of Object.values<any>(resources)) {
      if (fn.Type !== 'AWS::Lambda::Function') continue;
      const handlerCode = handlerSource(fn.Properties.Handler ?? '');
      if (!handlerCode) continue;
      const source = signingSource(handlerCode);
      if (!source.includes('generate_presigned_url')) continue;
      const roleId = fn.Properties.Role?.['Fn::GetAtt']?.[0];
      const actions = roleId ? roleActions(resources, roleId, imported) : [];
      const missing: string[] = [];
      if (/['"]put_object['"]/.test(source) && !actions.includes('s3:PutObject')) missing.push('s3:PutObject');
      if (/['"]get_object['"]/.test(source) && !actions.some(a => a === 's3:GetObject' || a === 's3:GetObject*')) {
        missing.push('s3:GetObject');
      }
      found.push({ stack, handler: fn.Properties.Handler, missing });
    }
  }
  return found;
}

const synthesized = synth();

function checkedLambdas(): Checked[] {
  const { storage, stacks } = synthesized;
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

describe('Lambdas that vend presigned S3 URLs', () => {
  const presigners = presigningLambdas();

  it('are found', () => {
    expect(presigners.map(p => p.handler)).toEqual(expect.arrayContaining([
      'create_trajectory_upload_url.handler',
      'get_trajectory_download_url.handler',
      'generate_step_artifact_url.handler',
    ]));
  });

  it('have the S3 permission their URLs need', () => {
    expect(presigners.filter(p => p.missing.length).map(p => `${p.stack}:${p.handler} ${p.missing.join(',')}`))
      .toEqual([]);
  });
});

/**
 * 3. Secrets Manager scoping. Use-case secrets live under `${baseName}/usecase/*`,
 * application secrets under `${baseName}/application/*` (secret_names.py). The
 * application router is the only writer of application secrets; use-case secret
 * Lambdas must never gain write actions on the application path.
 */
const SECRET_WRITE_ACTIONS = [
  'secretsmanager:CreateSecret',
  'secretsmanager:TagResource',
  'secretsmanager:UpdateSecret',
  'secretsmanager:DeleteSecret',
];
const USECASE_SECRET_HANDLERS = [
  'create_usecase_secrets.handler',
  'update_usecase_secrets.handler',
  'delete_usecase_secrets.handler',
  'get_usecase_secrets.handler',
  'get_usecase_secret_value.handler',
];

function lambdaByHandler(resources: Resources, handler: string): any {
  const fn = Object.values<any>(resources)
    .find(r => r.Type === 'AWS::Lambda::Function' && r.Properties.Handler === handler);
  if (!fn) throw new Error(`No Lambda with handler ${handler}`);
  return fn;
}

/**
 * Allow statements of the role's inline policies; `resourceText` is the JSON of
 * `Resource`, `conditions` the statement's `Condition` block (`undefined` without one).
 */
function roleStatements(resources: Resources, roleId: string):
  { actions: string[]; resourceText: string; conditions?: Record<string, any> }[] {
  return Object.values<any>(resources)
    .filter(r => r.Type === 'AWS::IAM::Policy'
      && (r.Properties.Roles ?? []).some((x: any) => x.Ref === roleId))
    .flatMap(r => r.Properties.PolicyDocument?.Statement ?? [])
    .filter((s: any) => s.Effect === 'Allow')
    .map((s: any) => ({
      actions: [].concat(s.Action) as string[],
      resourceText: JSON.stringify(s.Resource),
      conditions: s.Condition,
    }));
}

/** Secrets Manager actions a Lambda holds on resources whose ARN text matches `pathMarker`. */
function secretActionsOn(resources: Resources, handler: string, pathMarker: string): string[] {
  const fn = lambdaByHandler(resources, handler);
  const roleId = fn.Properties.Role?.['Fn::GetAtt']?.[0];
  return roleStatements(resources, roleId)
    .filter(s => s.resourceText.includes(pathMarker))
    .flatMap(s => s.actions)
    .filter(a => a.startsWith('secretsmanager:'))
    .sort();
}

describe('Secrets Manager scoping', () => {
  const { lambdas } = synthesized.stacks;
  const ROUTER = 'application_router.handler';

  it('application router has SECRET_PREFIX (names must match the IAM path)', () => {
    const fn = lambdaByHandler(lambdas.Resources, ROUTER);
    expect(fn.Properties.Environment?.Variables?.SECRET_PREFIX).toBeDefined();
  });

  it('application router manages exactly the application secret path', () => {
    expect(secretActionsOn(lambdas.Resources, ROUTER, '/application/*')).toEqual([
      'secretsmanager:CreateSecret',
      'secretsmanager:DeleteSecret',
      'secretsmanager:DescribeSecret',
      'secretsmanager:TagResource',
      'secretsmanager:UpdateSecret',
    ]);
    expect(secretActionsOn(lambdas.Resources, ROUTER, '"*"')).toEqual(['secretsmanager:ListSecrets']);
  });

  it('application router has no access to use-case secrets', () => {
    expect(secretActionsOn(lambdas.Resources, ROUTER, '/usecase/*')).toEqual([]);
  });

  it.each(USECASE_SECRET_HANDLERS)('%s never writes application secrets', handler => {
    const onApplication = secretActionsOn(lambdas.Resources, handler, '/application/*');
    expect(onApplication.filter(a => SECRET_WRITE_ACTIONS.includes(a))).toEqual([]);
  });

  // The use-case list / value routes fall back to the owning application's
  // secrets (inherited keys, value fallback): read-only on the application path.
  it.each([
    ['get_usecase_secrets.handler', ['secretsmanager:DescribeSecret']],
    ['get_usecase_secret_value.handler', ['secretsmanager:GetSecretValue']],
  ])('%s reads application secrets with exactly %j', (handler, expected) => {
    expect(secretActionsOn(lambdas.Resources, handler, '/application/*')).toEqual(expected);
  });

  it.each([
    'create_usecase_secrets.handler',
    'update_usecase_secrets.handler',
    'delete_usecase_secrets.handler',
  ])('%s has no access to application secrets', handler => {
    expect(secretActionsOn(lambdas.Resources, handler, '/application/*')).toEqual([]);
  });
});

/**
 * 4. GetMicrovm. `execution_transitions.record_microvm_runtime` runs on every
 * terminal transition; the Lambdas that reach it are the status API
 * (`update_execution_status`), the reconciler, `stop_execution` and
 * `terminate_wizard_session`.
 */
const GET_MICROVM_CALLER = /\bexecution_transitions\b|get_microvm\(/;

interface MicrovmReader { stack: string; handler: string; onImage: boolean; onVms: boolean }

function getMicrovmReaders(): MicrovmReader[] {
  const found: MicrovmReader[] = [];
  for (const [stack, template] of Object.entries(synthesized.stacks)) {
    const resources: Resources = template.Resources;
    for (const fn of Object.values<any>(resources)) {
      if (fn.Type !== 'AWS::Lambda::Function') continue;
      const source = handlerSource(fn.Properties.Handler ?? '');
      if (!source || !GET_MICROVM_CALLER.test(source)) continue;
      const roleId = fn.Properties.Role?.['Fn::GetAtt']?.[0];
      const statements = roleId
        ? roleStatements(resources, roleId).filter(s => s.actions.includes('lambda:GetMicrovm'))
        : [];
      found.push({
        stack,
        handler: fn.Properties.Handler,
        onImage: statements.some(s => s.resourceText.includes('ImageArn')),
        onVms: statements.some(s => s.resourceText.includes(':microvm/*')),
      });
    }
  }
  return found;
}

describe('Lambdas that can reach GetMicrovm', () => {
  const readers = getMicrovmReaders();

  it('are the terminal-transition Lambdas in both stacks', () => {
    expect(readers.map(r => `${r.stack}:${r.handler}`).sort()).toEqual([
      'lambdas:update_execution_status.handler',
      'worker:reconcile_executions.handler',
      'worker:stop_execution.handler',
      'worker:terminate_wizard_session.handler',
    ]);
  });

  it('hold lambda:GetMicrovm on the worker image ARN', () => {
    expect(readers.filter(r => !r.onImage).map(r => `${r.stack}:${r.handler}`)).toEqual([]);
  });

  it("hold lambda:GetMicrovm on the account's microvm resources", () => {
    expect(readers.filter(r => !r.onVms).map(r => `${r.stack}:${r.handler}`)).toEqual([]);
  });
});

/**
 * 5. Cost ledger reads. The cost routes (`/applications/{id}/costs`,
 * `/usecase/{id}/costs`) return the last 30 rows of the dimension's S3 ledger
 * under `cost_allocation/` (cost_ledger.read_tail). The application router is
 * the only endpoint Lambda that reads the ledger; a missing grant surfaces only
 * as a 500 in a deployed environment, so the template is the guard. The bucket
 * is resolved from `BUCKET_NAME` (cost_ledger.get_ledger_bucket).
 *
 * A dimension without usage has no ledger file yet. Without `s3:ListBucket`, S3
 * answers `GetObject` on a missing key with 403 AccessDenied instead of 404
 * NoSuchKey, and `cost_ledger.read` (which maps only NoSuchKey to "empty") turns
 * that into a 500. The router therefore also lists, but only under the
 * `cost_allocation/` prefix (the statement the cost collector has).
 */
describe('Cost ledger reads', () => {
  const { lambdas } = synthesized.stacks;
  const ROUTER = 'application_router.handler';

  function s3StatementsOf(handler: string) {
    const fn = lambdaByHandler(lambdas.Resources, handler);
    const roleId = fn.Properties.Role?.['Fn::GetAtt']?.[0];
    return roleStatements(lambdas.Resources, roleId).filter(s => s.actions.some(a => a.startsWith('s3:')));
  }

  it('application router has BUCKET_NAME in its environment', () => {
    const fn = lambdaByHandler(lambdas.Resources, ROUTER);
    expect(fn.Properties.Environment?.Variables?.BUCKET_NAME).toBeDefined();
  });

  it('application router has exactly two S3 statements: GetObject and ListBucket', () => {
    const statements = s3StatementsOf(ROUTER);
    expect(statements.map(s => s.actions)).toEqual([['s3:GetObject'], ['s3:ListBucket']]);
  });

  it('application router may GetObject exactly the cost_allocation/ prefix of the artefacts bucket', () => {
    const [getObject] = s3StatementsOf(ROUTER).filter(s => s.actions.includes('s3:GetObject'));
    expect(getObject.resourceText).toContain('/cost_allocation/*');
    expect(getObject.resourceText).not.toContain('"*"');
    expect(getObject.conditions).toBeUndefined();
  });

  it('application router may ListBucket the artefacts bucket only under the cost_allocation/ prefix', () => {
    const [listBucket] = s3StatementsOf(ROUTER).filter(s => s.actions.includes('s3:ListBucket'));
    // Bucket ARN, not an object ARN: ListBucket is a bucket-level action.
    expect(listBucket.resourceText).toContain('Arn');
    expect(listBucket.resourceText).not.toContain('/');
    expect(listBucket.resourceText).not.toContain('"*"');
    expect(listBucket.conditions).toEqual({ StringLike: { 's3:prefix': 'cost_allocation/*' } });
  });

  it('application router has no S3 write actions', () => {
    const writes = s3StatementsOf(ROUTER).flatMap(s => s.actions)
      .filter(a => !['s3:GetObject', 's3:ListBucket'].includes(a));
    expect(writes).toEqual([]);
  });

  it('the cost grant lives in the router\'s single inline policy (resource ceiling)', () => {
    const fn = lambdaByHandler(lambdas.Resources, ROUTER);
    const roleId = fn.Properties.Role?.['Fn::GetAtt']?.[0];
    const inlinePolicies = Object.values<any>(lambdas.Resources)
      .filter(r => r.Type === 'AWS::IAM::Policy' && (r.Properties.Roles ?? []).some((x: any) => x.Ref === roleId));
    expect(inlinePolicies).toHaveLength(1);
  });
});
