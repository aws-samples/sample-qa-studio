/**
 * Worker stack: MicroVM image infrastructure, the only worker compute.
 *
 * Synthesizes the stacks offline (config from configuration.json.sample) and
 * asserts on the worker template: the AWS::Lambda::MicrovmImage and its props,
 * the image-level environment (no AWS_REGION, no secret values), the hooks,
 * the build/execution roles and that no ECS/ECR resource or grant is left.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { Template } from 'aws-cdk-lib/assertions';
import { Asset } from 'aws-cdk-lib/aws-s3-assets';
import { App, DockerIgnoreStrategy } from 'aws-cdk-lib';

jest.mock('../config', () => {
  const actual = jest.requireActual('../config');
  const sample = require('path').join(__dirname, '..', '..', 'configuration.json.sample');
  return { ...actual, loadConfig: () => actual.loadConfig(sample) };
});

import { synthStacks } from './synthStacks';
import { bundleWorkerImageContext, pruneExcludes, readDockerignorePatterns, REPO_ROOT } from '../worker-image-asset';
import { NovaActQAStudioWorkerStack } from '../worker-stack';

type Resources = Record<string, any>;

let worker: NovaActQAStudioWorkerStack;
let template: Template;
let json: { Resources: Resources; Outputs: Record<string, any> };
let image: any;

beforeAll(() => {
  worker = synthStacks().worker;
  template = Template.fromStack(worker);
  json = template.toJSON() as typeof json;
  const images = template.findResources('AWS::Lambda::MicrovmImage');
  image = Object.values(images)[0]?.Properties;
});

function envMap(): Record<string, any> {
  return Object.fromEntries(image.EnvironmentVariables.map((e: any) => [e.Key, e.Value]));
}

function roleTrust(roleLogicalId: string): any[] {
  return json.Resources[roleLogicalId].Properties.AssumeRolePolicyDocument.Statement;
}

/** Policy documents (inline Policy resources + the role's own Policies) attached to a role. */
function policyDocumentsOf(roleLogicalId: string): any[] {
  const docs: any[] = [];
  for (const res of Object.values(json.Resources)) {
    if (res.Type !== 'AWS::IAM::Policy') continue;
    const roles: any[] = res.Properties.Roles ?? [];
    if (roles.some((r) => r?.Ref === roleLogicalId)) docs.push(res.Properties.PolicyDocument);
  }
  for (const inline of json.Resources[roleLogicalId].Properties.Policies ?? []) docs.push(inline.PolicyDocument);
  return docs;
}

function allowedActions(roleLogicalId: string): string[] {
  return policyDocumentsOf(roleLogicalId)
    .flatMap((d) => d.Statement)
    .filter((s: any) => s.Effect === 'Allow')
    .flatMap((s: any) => [].concat(s.Action));
}

function statementsWithAction(roleLogicalId: string, action: string): any[] {
  return policyDocumentsOf(roleLogicalId)
    .flatMap((d) => d.Statement)
    .filter((s: any) => s.Effect === 'Allow' && [].concat(s.Action).includes(action as never));
}

function logicalIdOf(construct: any): string {
  return worker.getLogicalId(construct.node.defaultChild);
}

describe('MicroVM code artifact', () => {
  test('.dockerignore patterns are read without comments or blank lines', () => {
    const patterns = readDockerignorePatterns();
    expect(patterns).toContain('*');
    expect(patterns).toContain('!web-app/worker/**');
    expect(patterns).toContain('!qa-studio-cli/**');
    expect(patterns.some((p) => p.startsWith('#') || p === '')).toBe(false);
  });

  test('pruned excludes only add directories the raw rules already ignore', () => {
    const raw = readDockerignorePatterns();
    const pruned = pruneExcludes(raw);
    const extra = pruned.slice(raw.length);
    expect(pruned.slice(0, raw.length)).toEqual(raw);
    expect(extra).toContain('web-app/node_modules');
    expect(extra).toContain('web-app/frontend');
    expect(extra.some((p) => p.startsWith('web-app/worker') || p.startsWith('qa-studio-cli'))).toBe(false);
    const rawStrategy = new DockerIgnoreStrategy(REPO_ROOT, raw);
    const prunedStrategy = new DockerIgnoreStrategy(REPO_ROOT, pruned);
    for (const dir of extra) {
      expect(rawStrategy.ignores(path.join(REPO_ROOT, dir))).toBe(true);
      expect(prunedStrategy.completelyIgnores(path.join(REPO_ROOT, dir))).toBe(true);
    }
    expect(prunedStrategy.ignores(path.join(REPO_ROOT, 'web-app', 'worker', 'supervisor.py'))).toBe(false);
    expect(prunedStrategy.ignores(path.join(REPO_ROOT, 'qa-studio-cli', 'setup.py'))).toBe(false);
  });

  test('bundled tree is the filtered repo root plus the Dockerfile at the root', () => {
    const out = fs.mkdtempSync(path.join(os.tmpdir(), 'worker-image-ctx-'));
    try {
      const started = Date.now();
      bundleWorkerImageContext(out, REPO_ROOT);
      expect(Date.now() - started).toBeLessThan(5_000); // pruned walk, not the whole repo
      for (const expected of ['Dockerfile', 'web-app/worker/supervisor.py', 'web-app/worker/Dockerfile', 'qa-studio-cli/setup.py', 'qa-studio-cli/qa_studio_cli']) {
        expect(fs.existsSync(path.join(out, expected))).toBe(true);
      }
      for (const unexpected of ['web-app/worker/entrypoint.sh', 'web-app/lib', 'web-app/lambdas', 'web-app/frontend', 'node_modules', 'web-app/node_modules', '.git', 'docs', 'web-app/worker/__pycache__', 'qa-studio-cli/qa_studio.egg-info']) {
        expect(fs.existsSync(path.join(out, unexpected))).toBe(false);
      }
      expect(fs.readFileSync(path.join(out, 'Dockerfile'), 'utf-8'))
        .toEqual(fs.readFileSync(path.join(REPO_ROOT, 'web-app', 'worker', 'Dockerfile'), 'utf-8'));
    } finally {
      fs.rmSync(out, { recursive: true, force: true });
    }
  });

  test('the staged S3 asset carries that tree and the image points at it', () => {
    const asset = worker.node.findChild('microvm_image_asset') as Asset;
    const stagedDir = path.resolve((worker.node.root as App).outdir, asset.assetPath);
    expect(fs.existsSync(path.join(stagedDir, 'Dockerfile'))).toBe(true);
    expect(fs.existsSync(path.join(stagedDir, 'web-app', 'worker', 'supervisor.py'))).toBe(true);
    expect(fs.existsSync(path.join(stagedDir, 'qa-studio-cli', 'setup.py'))).toBe(true);
    expect(fs.existsSync(path.join(stagedDir, 'web-app', 'lib'))).toBe(false);
    expect(fs.existsSync(path.join(stagedDir, 'node_modules'))).toBe(false);

    // codeArtifact.uri = s3://<bucket>/<key> built from the asset's bucket/key tokens
    const uri = JSON.stringify(image.CodeArtifact.Uri);
    expect(uri).toContain('s3://');
    expect(uri).toContain(asset.assetHash);
  });
});

describe('AWS::Lambda::MicrovmImage', () => {
  test('exactly one image with the spike-verified base props', () => {
    template.resourceCountIs('AWS::Lambda::MicrovmImage', 1);
    expect(image.Name).toEqual('test-worker');
    expect(image.Description).toEqual('0.0.0');
    expect(JSON.stringify(image.BaseImageArn)).toContain(':aws:microvm-image:al2023-1');
    expect(image.BaseImageVersion).toEqual('2');
    expect(image.CpuConfigurations).toEqual([{ Architecture: 'ARM_64' }]);
    expect(image.Resources).toEqual([{ MinimumMemoryInMiB: 1024 }]);
    expect(image.AdditionalOsCapabilities).toEqual([]);
    // The platform rejects every INTERNET_EGRESS spelling and defaults to internet egress.
    expect(image.EgressNetworkConnectors).toEqual([]);
  });

  test('image carries the cost allocation tag application=qa-studio (VMs themselves cannot be tagged)', () => {
    expect(image.Tags).toEqual([{ Key: 'application', Value: 'qa-studio' }]);
  });

  test('hooks on 8080 with run/terminate/ready/validate enabled', () => {
    expect(image.Hooks).toEqual({
      Port: 8080,
      MicrovmHooks: {
        Run: 'ENABLED', RunTimeoutInSeconds: 60,
        Terminate: 'ENABLED', TerminateTimeoutInSeconds: 60,
        Suspend: 'DISABLED', Resume: 'DISABLED',
      },
      MicrovmImageHooks: {
        Ready: 'ENABLED', ReadyTimeoutInSeconds: 600,
        Validate: 'ENABLED', ValidateTimeoutInSeconds: 120,
      },
    });
  });

  test('logs to the stack-owned 5-day log group', () => {
    const logGroupId = logicalIdOf(worker.microvmLogGroup);
    expect(json.Resources[logGroupId].Properties.RetentionInDays).toEqual(5);
    expect(json.Resources[logGroupId].Properties.LogGroupName).toEqual('/qa-studio/test/microvm');
    expect(image.Logging).toEqual({ CloudWatch: { LogGroup: { Ref: logGroupId } } });
  });

  test('image env carries what the supervisor needs, with no AWS_REGION, no WORKER_MODE and no secret values', () => {
    const env = envMap();
    const keys = Object.keys(env);
    expect(new Set(keys).size).toEqual(keys.length);
    expect(keys).not.toContain('AWS_REGION');
    // entrypoint.sh is gone; the supervisor is the image ENTRYPOINT
    expect(keys).not.toContain('WORKER_MODE');
    for (const required of [
      // supervisor.py CREDENTIAL_IMAGE_ENV
      'QA_STUDIO_API_URL_SSM', 'QA_STUDIO_TOKEN_ENDPOINT_SSM', 'WORKER_CREDENTIALS_SECRET_ARN',
      // supervisor.py BATCH_REQUIRED_IMAGE_ENV (minus AWS_REGION, injected by the platform)
      'DYNAMODB_TABLE_NAME', 'S3_BUCKET_PREFIX', 'SECRETS_PREFIX', 'NOVA_ACT_API_KEY_NAME', 'BEDROCK_EXECUTION_ROLE',
      // supervisor.py WIZARD_REQUIRED_IMAGE_ENV
      'WIZARD_QUEUE_URL',
      // worker constants
      'DYNAMO_TABLE', 'S3_BUCKET', 'NOTIFICATION_QUEUE_URL', 'USE_NOVA_ACT_GA', 'NOVA_ACT_REGION',
      'NOVA_ACT_S3_BUCKET', 'DEVICE_FARM_REGION', 'RECORDING_QUEUE_URL', 'NETWORK_ASSERTION_BODY_MAX_BYTES',
      'QA_STUDIO_API_STAGE', 'ENABLE_TRAJECTORY_REPLAY',
    ]) {
      expect(keys).toContain(required);
    }
    expect(env.QA_STUDIO_API_URL_SSM).toEqual('/qa-studio/test/api-url');
    expect(env.QA_STUDIO_TOKEN_ENDPOINT_SSM).toEqual('/qa-studio/test/cognito-token-endpoint');
    expect(env.SECRETS_PREFIX).toEqual('test');
    // Only the ARN of the credentials secret is baked in; the value is fetched at /run.
    expect(JSON.stringify(env.WORKER_CREDENTIALS_SECRET_ARN)).toMatch(/Ref|Fn::ImportValue/);
    // Secret-looking keys are references (ARN / secret name / SSM path), never values.
    const secretish = keys.filter((k) => /SECRET|TOKEN|PASSWORD|API_KEY|CLIENT_ID/.test(k)).sort();
    expect(secretish).toEqual(['NOVA_ACT_API_KEY_NAME', 'QA_STUDIO_TOKEN_ENDPOINT_SSM', 'SECRETS_PREFIX', 'WORKER_CREDENTIALS_SECRET_ARN']);
    // supervisor.py SENSITIVE_ENV_KEYS and the resolved credentials never appear at image level
    for (const forbidden of ['OAUTH_CLIENT_ID', 'OAUTH_CLIENT_SECRET', 'QA_STUDIO_EXECUTION_TOKEN', 'EXECUTION_TOKEN']) {
      expect(keys).not.toContain(forbidden);
    }
  });

  test('image description records the package version', () => {
    expect(image.Description).toEqual('0.0.0');
  });
});

describe('MicroVM roles', () => {
  test('build role is assumable by lambda.amazonaws.com with TagSession and can read the artifact + write build logs', () => {
    const buildRoleId = json.Resources[Object.keys(template.findResources('AWS::Lambda::MicrovmImage'))[0]]
      .Properties.BuildRoleArn['Fn::GetAtt'][0];
    const trust = roleTrust(buildRoleId);
    expect(trust).toEqual([
      expect.objectContaining({
        Action: expect.arrayContaining(['sts:AssumeRole', 'sts:TagSession']),
        Principal: { Service: 'lambda.amazonaws.com' },
      }),
    ]);
    const actions = allowedActions(buildRoleId);
    expect(actions).toContain('s3:GetObject');
    expect(actions).toEqual(expect.arrayContaining(['logs:CreateLogStream', 'logs:PutLogEvents', 'logs:DescribeLogStreams']));
    // no secrets / table / agentcore access on the build role
    expect(actions.some((a) => /^(secretsmanager|dynamodb|bedrock-agentcore|devicefarm):/.test(a))).toBe(false);
  });

  test('execution role trusts lambda.amazonaws.com, can terminate its own VM and read the credentials secret', () => {
    const execRoleId = logicalIdOf(worker.microvmExecutionRole);
    expect(roleTrust(execRoleId)).toEqual([
      expect.objectContaining({
        Action: expect.arrayContaining(['sts:AssumeRole', 'sts:TagSession']),
        Principal: { Service: 'lambda.amazonaws.com' },
      }),
    ]);
    const terminate = statementsWithAction(execRoleId, 'lambda:TerminateMicrovm');
    expect(terminate).toHaveLength(1);
    expect(JSON.stringify(terminate[0].Resource)).toContain('ImageArn');
    expect(allowedActions(execRoleId)).toContain('lambda:GetMicrovm');
    expect(allowedActions(execRoleId)).toContain('secretsmanager:GetSecretValue');
    expect(allowedActions(execRoleId)).toContain('logs:PutLogEvents');
  });

  test('execution role carries the worker runtime permission set and no ECR/ECS action', () => {
    const execRoleId = logicalIdOf(worker.microvmExecutionRole);
    const execActions = new Set(allowedActions(execRoleId));
    expect([...execActions].filter((a) => /^(ecr|ecs):/.test(a))).toEqual([]);
    for (const required of [
      'ssm:GetParameter', 'dynamodb:Query', 's3:PutObject*', 'events:PutEvents', 'sqs:SendMessage',
      'bedrock-agentcore:CreateBrowser', 'devicefarm:CreateRemoteAccessSession', 'iam:PassRole',
    ]) {
      expect(execActions.has(required)).toBe(true);
    }
  });

  test('no single policy document exceeds the inline-policy size budget', () => {
    for (const res of Object.values(json.Resources)) {
      if (res.Type !== 'AWS::IAM::Policy') continue;
      expect(JSON.stringify(res.Properties.PolicyDocument).length).toBeLessThan(6144);
    }
  });
});

describe('ECS compute removed', () => {
  test('no cluster, task definition, ECR repository or ECR deployment is left', () => {
    template.resourceCountIs('AWS::ECS::Cluster', 0);
    template.resourceCountIs('AWS::ECS::TaskDefinition', 0);
    template.resourceCountIs('AWS::ECR::Repository', 0);
    expect(Object.values(json.Resources).filter((r: any) => r.Type.startsWith('AWS::ECS::') || r.Type.startsWith('AWS::ECR::'))).toEqual([]);
    expect(Object.keys(json.Resources).filter((id) => /ECRDeployment|containerdeployment|TaskRole|ExecutionRole[0-9A-F]/.test(id))).toEqual([]);
  });

  test('no role in the stack is assumable by ecs-tasks.amazonaws.com and no policy grants ecs:/ecr:', () => {
    for (const res of Object.values(json.Resources)) {
      if (res.Type === 'AWS::IAM::Role') {
        expect(JSON.stringify(res.Properties.AssumeRolePolicyDocument)).not.toContain('ecs-tasks.amazonaws.com');
      }
      if (res.Type === 'AWS::IAM::Policy' || res.Type === 'AWS::IAM::Role') {
        expect(JSON.stringify(res.Properties)).not.toMatch(/"ec[sr]:/);
      }
    }
  });

  test('no Lambda carries ECS env vars', () => {
    for (const res of Object.values(json.Resources)) {
      if (res.Type !== 'AWS::Lambda::Function') continue;
      const keys = Object.keys(res.Properties.Environment?.Variables ?? {});
      expect(keys.filter((k) => /^(ECS_|WORKER_RUNTIME|LOG_GROUP_NAME|LOG_STREAM_PREFIX|SUBNET_ID|SECURITY_GROUP_ID)/.test(k))).toEqual([]);
    }
  });

  test('the cluster ARN export is gone', () => {
    expect(Object.keys(json.Outputs).filter((id) => /cluster/i.test(id))).toEqual([]);
  });

  test('outputs expose the image ARN and version', () => {
    const outputs = Object.values(json.Outputs).map((o: any) => JSON.stringify(o.Value));
    expect(outputs.some((v) => v.includes('ImageArn'))).toBe(true);
    expect(outputs.some((v) => v.includes('LatestActiveImageVersion'))).toBe(true);
  });

  test('stays under the CloudFormation resource limit with headroom', () => {
    expect(Object.keys(json.Resources).length).toBeLessThan(480);
  });
});

describe('without vpcId (default): PUBLIC browsers, no VPC footprint', () => {
  test('no EC2 resource (VPC, subnets, NAT gateways, security group, endpoints)', () => {
    expect(Object.values(json.Resources).filter((r: any) => r.Type.startsWith('AWS::EC2::')).map((r: any) => r.Type)).toEqual([]);
  });

  test('image env carries no AgentCore VPC settings', () => {
    const keys = Object.keys(envMap());
    expect(keys.filter((k) => /^(AGENT_CORE_VPC|AC_)/.test(k))).toEqual([]);
  });

  test('no Lambda is attached to a VPC', () => {
    for (const res of Object.values(json.Resources)) {
      if (res.Type !== 'AWS::Lambda::Function') continue;
      expect(res.Properties.VpcConfig).toBeUndefined();
    }
  });

  test('the stack exposes no vpc / security group / subnet members', () => {
    expect(worker).not.toHaveProperty('vpc');
    expect(worker).not.toHaveProperty('workerSecurityGroup');
    expect(worker).not.toHaveProperty('subnetId');
    expect(worker.node.tryFindChild('browser_vpc')).toBeUndefined();
  });

  test('synthesis stays environment-agnostic', () => {
    expect(worker.environment).toEqual('aws://unknown-account/unknown-region');
  });
});
