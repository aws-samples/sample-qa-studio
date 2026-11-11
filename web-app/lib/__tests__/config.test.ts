/**
 * Guard: the MicroVM runner config keys (`maxExecutionDurationMinutes`,
 * `maxWizardSessionMinutes`) have the documented defaults and `loadConfig()`
 * rejects wrong types and out-of-range values with a readable message instead
 * of letting them reach the stacks. The keys removed with the ECS runtime
 * (`workerRuntime`, `dockerImageVersion`) fail loudly instead of being ignored.
 * The AgentCore browser VPC keys (`vpcId`, `vpcSubnetIds`,
 * `workerSecurityGroupId`) are validated; `agentCoreVPC` / `createVpcEndpoints`
 * are deprecated (warning, ignored).
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import {
  COST_ALLOCATION_MAX_LOOKBACK_DAYS,
  DEFAULT_COST_ALLOCATION,
  DEPRECATED_CONFIG_KEYS,
  getStackEnv,
  loadConfig,
  REMOVED_CONFIG_KEYS,
} from '../config';

const REQUIRED = { adminEmail: 'ops@example.com', baseName: 'qa-studio' };

let tmpDir: string;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'qa-studio-config-'));
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

function writeConfig(overrides: Record<string, unknown>): string {
  const file = path.join(tmpDir, 'configuration.json');
  fs.writeFileSync(file, JSON.stringify({ ...REQUIRED, ...overrides }));
  return file;
}

describe('loadConfig: removed ECS-era keys are rejected', () => {
  it.each([
    ['workerRuntime', 'microvm'],
    ['workerRuntime', 'ecs'],
    ['dockerImageVersion', '0.1.1'],
    ['dockerImageVersion', null],
  ])('%s = %p fails with a pointer to the release notes', (key, value) => {
    expect(() => loadConfig(writeConfig({ [key]: value }))).toThrow(
      `Configuration error: ${key} was removed (the worker runs on Lambda MicroVMs, without ECS); see the release notes`,
    );
  });

  it('the loaded config carries none of the removed keys', () => {
    const config = loadConfig(writeConfig({})) as unknown as Record<string, unknown>;
    for (const key of ['workerRuntime', 'dockerImageVersion']) {
      expect(config).not.toHaveProperty(key);
    }
  });

  it('REMOVED_CONFIG_KEYS lists only the ECS runtime keys', () => {
    expect([...REMOVED_CONFIG_KEYS].sort()).toEqual(['dockerImageVersion', 'workerRuntime']);
  });
});

describe('loadConfig: AgentCore browser VPC keys', () => {
  const VPC = 'vpc-0123456789abcdef0';
  let warn: jest.SpyInstance;

  beforeEach(() => {
    warn = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
  });

  afterEach(() => {
    warn.mockRestore();
  });

  it('defaults vpcId, vpcSubnetIds and workerSecurityGroupId to null', () => {
    const config = loadConfig(writeConfig({}));
    expect(config.vpcId).toBeNull();
    expect(config.vpcSubnetIds).toBeNull();
    expect(config.workerSecurityGroupId).toBeNull();
    expect(warn).not.toHaveBeenCalled();
  });

  it('accepts a full VPC configuration, subnets in the given order', () => {
    const config = loadConfig(writeConfig({
      vpcId: VPC,
      vpcSubnetIds: ['subnet-b', 'subnet-a'],
      workerSecurityGroupId: 'sg-1',
    }));
    expect(config.vpcId).toBe(VPC);
    expect(config.vpcSubnetIds).toEqual(['subnet-b', 'subnet-a']);
    expect(config.workerSecurityGroupId).toBe('sg-1');
  });

  it('accepts vpcId alone (subnets and security group chosen by the stack)', () => {
    const config = loadConfig(writeConfig({ vpcId: VPC, vpcSubnetIds: null, workerSecurityGroupId: null }));
    expect(config.vpcId).toBe(VPC);
    expect(config.vpcSubnetIds).toBeNull();
    expect(config.workerSecurityGroupId).toBeNull();
  });

  it.each([['vpcx-1'], [''], ['subnet-1']])('rejects vpcId %p that does not start with "vpc-"', (value) => {
    expect(() => loadConfig(writeConfig({ vpcId: value }))).toThrow(
      `Configuration error: vpcId "${value}" must start with "vpc-"`,
    );
  });

  it.each([[42], [true], [['vpc-1']], [{}]])('rejects vpcId of the wrong type %p', (value) => {
    expect(() => loadConfig(writeConfig({ vpcId: value }))).toThrow(
      'Configuration error: vpcId must be a string or null',
    );
  });

  it.each([['sg'], ['vpc-1'], ['']])('rejects workerSecurityGroupId %p that does not start with "sg-"', (value) => {
    expect(() => loadConfig(writeConfig({ vpcId: VPC, workerSecurityGroupId: value }))).toThrow(
      `Configuration error: workerSecurityGroupId "${value}" must start with "sg-"`,
    );
  });

  it.each([[1], [false], [['sg-1']]])('rejects workerSecurityGroupId of the wrong type %p', (value) => {
    expect(() => loadConfig(writeConfig({ vpcId: VPC, workerSecurityGroupId: value }))).toThrow(
      'Configuration error: workerSecurityGroupId must be a string or null',
    );
  });

  it.each([
    ['a string', 'subnet-1'],
    ['an empty array', []],
    ['an object', { a: 'subnet-1' }],
  ])('rejects vpcSubnetIds as %s', (_label, value) => {
    expect(() => loadConfig(writeConfig({ vpcId: VPC, vpcSubnetIds: value }))).toThrow(
      'Configuration error: vpcSubnetIds must be null or a non-empty array of subnet IDs',
    );
  });

  it.each([[['subnet-1', 'sn-2']], [['subnet-1', 7]], [['']]])('rejects vpcSubnetIds entries %p not starting with "subnet-"', (value) => {
    expect(() => loadConfig(writeConfig({ vpcId: VPC, vpcSubnetIds: value }))).toThrow(
      /Configuration error: vpcSubnetIds entry .* must be a string starting with "subnet-"/,
    );
  });

  it('rejects duplicate vpcSubnetIds', () => {
    expect(() => loadConfig(writeConfig({ vpcId: VPC, vpcSubnetIds: ['subnet-1', 'subnet-2', 'subnet-1'] }))).toThrow(
      'Configuration error: vpcSubnetIds contains "subnet-1" more than once',
    );
  });

  it.each([
    ['vpcSubnetIds', ['subnet-1']],
    ['workerSecurityGroupId', 'sg-1'],
  ])('rejects %s without vpcId', (key, value) => {
    expect(() => loadConfig(writeConfig({ [key]: value }))).toThrow(
      `Configuration error: ${key} requires vpcId`,
    );
    expect(() => loadConfig(writeConfig({ vpcId: null, [key]: value }))).toThrow(
      `Configuration error: ${key} requires vpcId`,
    );
  });

  describe.each([
    ['agentCoreVPC', true],
    ['agentCoreVPC', null],
    ['createVpcEndpoints', true],
    ['createVpcEndpoints', false],
  ])('deprecated %s = %p', (key, value) => {
    it.each([[null], [VPC]])('warns once and is dropped from the config (vpcId %p)', (vpcId) => {
      const config = loadConfig(writeConfig({ vpcId, [key]: value })) as unknown as Record<string, unknown>;
      expect(config).not.toHaveProperty(key);
      expect(warn).toHaveBeenCalledTimes(1);
      expect(warn.mock.calls[0][0]).toMatch(
        new RegExp(`^Configuration warning: ${key} is deprecated and ignored \\(.+\\); see docs/configuration\\.md$`),
      );
    });
  });

  it('agentCoreVPC: false without vpcId only warns (browsers stay PUBLIC either way)', () => {
    expect(() => loadConfig(writeConfig({ agentCoreVPC: false }))).not.toThrow();
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it('warns once per deprecated key', () => {
    loadConfig(writeConfig({ agentCoreVPC: true, createVpcEndpoints: false }));
    expect(warn).toHaveBeenCalledTimes(2);
    expect(warn.mock.calls.map((c) => c[0]).join('\n')).toMatch(/agentCoreVPC[\s\S]*createVpcEndpoints/);
  });

  it('vpcId with agentCoreVPC: false is a contradiction and fails', () => {
    expect(() => loadConfig(writeConfig({ vpcId: VPC, agentCoreVPC: false }))).toThrow(
      'Configuration error: agentCoreVPC is deprecated; vpcId now attaches browsers to the VPC. Remove agentCoreVPC',
    );
  });

  it('DEPRECATED_CONFIG_KEYS has a reason for each deprecated key', () => {
    expect(Object.keys(DEPRECATED_CONFIG_KEYS).sort()).toEqual(['agentCoreVPC', 'createVpcEndpoints']);
    for (const reason of Object.values(DEPRECATED_CONFIG_KEYS)) expect(reason.length).toBeGreaterThan(10);
  });
});

describe('getStackEnv', () => {
  const saved = { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION };

  beforeEach(() => {
    process.env.CDK_DEFAULT_ACCOUNT = '111122223333';
    process.env.CDK_DEFAULT_REGION = 'eu-west-1';
  });

  afterEach(() => {
    for (const [name, value] of [['CDK_DEFAULT_ACCOUNT', saved.account], ['CDK_DEFAULT_REGION', saved.region]] as const) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  });

  it('is undefined without vpcId (env-agnostic synth)', () => {
    expect(getStackEnv(loadConfig(writeConfig({})))).toBeUndefined();
  });

  it('is the CLI account/region with vpcId (required by Vpc.fromLookup)', () => {
    expect(getStackEnv(loadConfig(writeConfig({ vpcId: 'vpc-1' })))).toEqual({
      account: '111122223333',
      region: 'eu-west-1',
    });
  });
});

describe('loadConfig: timeout keys', () => {
  describe.each([
    ['maxExecutionDurationMinutes', 60],
    ['maxWizardSessionMinutes', 240],
  ])('%s', (key, defaultValue) => {
    it(`defaults to ${defaultValue}`, () => {
      expect((loadConfig(writeConfig({})) as any)[key]).toBe(defaultValue);
    });

    it.each([1, 480, 90])('accepts %d (inside 1–480)', (value) => {
      expect((loadConfig(writeConfig({ [key]: value })) as any)[key]).toBe(value);
    });

    it.each([0, -1, 481, 10_000])('rejects %d as out of range with a readable error', (value) => {
      expect(() => loadConfig(writeConfig({ [key]: value }))).toThrow(
        new RegExp(`Configuration error: ${key} "${value}" must be an integer between 1 and 480`),
      );
    });

    it.each([1.5, '60', true, null, [60]])('rejects %p as wrong type with a readable error', (value) => {
      expect(() => loadConfig(writeConfig({ [key]: value }))).toThrow(
        new RegExp(`Configuration error: ${key} .* must be an integer between 1 and 480`),
      );
    });
  });

  it('the sample configuration loads with the documented defaults', () => {
    const sample = path.join(__dirname, '..', '..', 'configuration.json.sample');
    const config = loadConfig(sample);
    expect(config.maxExecutionDurationMinutes).toBe(60);
    expect(config.maxWizardSessionMinutes).toBe(240);
  });
});

/**
 * `costAllocation` (design: .kiro/docs/cost-allocation/design.md → Configuration).
 * The block is deep-merged with its defaults so an operator can set one key;
 * every key is type-checked and unknown keys fail (a typo would otherwise
 * silently fall back to the default).
 */
describe('loadConfig: costAllocation', () => {
  const costAllocation = (overrides: Record<string, unknown>) =>
    loadConfig(writeConfig({ costAllocation: overrides })).costAllocation;

  it('defaults match the design (NovaAct is the CE SERVICE value, not "Amazon Nova Act")', () => {
    expect(loadConfig(writeConfig({})).costAllocation).toEqual({
      enabled: true,
      scheduleUtc: 'cron(0 6 * * ? *)',
      lookbackDays: 3,
      novaActServiceName: 'NovaAct',
      compute: {
        enabled: true,
        ceService: 'AWS Lambda',
        ceComputeUsageTypePrefixes: ['Lambda-MicroVM-vCPU-Second', 'Lambda-MicroVM-Memory-GB-Second'],
        ceSnapshotUsageTypePrefixes: [
          'Lambda-MicroVM-Snapshot-Read-GB',
          'Lambda-MicroVM-Snapshot-Storage-GB-Hour',
          'Lambda-MicroVM-Snapshot-Write-GB',
        ],
      },
    });
    expect(DEFAULT_COST_ALLOCATION).toEqual(loadConfig(writeConfig({})).costAllocation);
    expect(COST_ALLOCATION_MAX_LOOKBACK_DAYS).toBe(14);
  });

  it('the sample configuration carries the block with the defaults', () => {
    const sample = path.join(__dirname, '..', '..', 'configuration.json.sample');
    const raw = JSON.parse(fs.readFileSync(sample, 'utf-8'));
    expect(raw.costAllocation).toEqual(DEFAULT_COST_ALLOCATION);
    expect(loadConfig(sample).costAllocation).toEqual(DEFAULT_COST_ALLOCATION);
  });

  it('a partial block keeps the defaults of the keys it does not set (deep merge incl. compute)', () => {
    const config = costAllocation({ lookbackDays: 5, compute: { enabled: false } });
    expect(config.lookbackDays).toBe(5);
    expect(config.compute.enabled).toBe(false);
    expect(config.scheduleUtc).toBe('cron(0 6 * * ? *)');
    expect(config.compute.ceService).toBe('AWS Lambda');
    expect(config.compute.ceComputeUsageTypePrefixes).toEqual(DEFAULT_COST_ALLOCATION.compute.ceComputeUsageTypePrefixes);
  });

  it('the defaults are not mutated by a loaded config', () => {
    costAllocation({ compute: { ceComputeUsageTypePrefixes: ['X'] } });
    expect(DEFAULT_COST_ALLOCATION.compute.ceComputeUsageTypePrefixes).toEqual([
      'Lambda-MicroVM-vCPU-Second',
      'Lambda-MicroVM-Memory-GB-Second',
    ]);
  });

  it.each([['a string', 'yes'], ['an array', []], ['null', null], ['a number', 1]])(
    'rejects costAllocation as %s',
    (_label, value) => {
      expect(() => loadConfig(writeConfig({ costAllocation: value }))).toThrow(
        'Configuration error: costAllocation must be an object',
      );
    },
  );

  it.each([['enabled', 'true'], ['enabled', 1], ['enabled', null]])('rejects costAllocation.%s = %p', (key, value) => {
    expect(() => costAllocation({ [key]: value })).toThrow(`Configuration error: costAllocation.${key} must be a boolean`);
  });

  it.each([['compute.enabled', 'true'], ['compute.enabled', 0]])('rejects costAllocation.%s = %p', (key, value) => {
    expect(() => costAllocation({ compute: { enabled: value } })).toThrow(
      `Configuration error: costAllocation.${key} must be a boolean`,
    );
  });

  it.each([1, 3, 14])('accepts lookbackDays %d', (value) => {
    expect(costAllocation({ lookbackDays: value }).lookbackDays).toBe(value);
  });

  it.each([0, -1, 15, 1.5, '3', null, true])('rejects lookbackDays %p', (value) => {
    expect(() => costAllocation({ lookbackDays: value })).toThrow(
      `Configuration error: costAllocation.lookbackDays ${JSON.stringify(value)} must be an integer between 1 and 14`,
    );
  });

  it.each(['cron(30 5 * * ? *)', 'rate(1 day)'])('accepts scheduleUtc %p', (value) => {
    expect(costAllocation({ scheduleUtc: value }).scheduleUtc).toBe(value);
  });

  it.each(['0 6 * * ? *', 'daily', '', 'CRON(0 6 * * ? *)', 42, null])('rejects scheduleUtc %p', (value) => {
    expect(() => costAllocation({ scheduleUtc: value })).toThrow(
      `Configuration error: costAllocation.scheduleUtc ${JSON.stringify(value)} must be an EventBridge schedule expression starting with "cron(" or "rate("`,
    );
  });

  it.each([
    ['novaActServiceName', '', 'costAllocation.novaActServiceName'],
    ['novaActServiceName', 7, 'costAllocation.novaActServiceName'],
    ['novaActServiceName', null, 'costAllocation.novaActServiceName'],
  ])('rejects %s = %p', (key, value, label) => {
    expect(() => costAllocation({ [key]: value })).toThrow(
      `Configuration error: ${label} must be a non-empty string`,
    );
  });

  it.each(['', 3, null, ['AWS Lambda']])('rejects compute.ceService = %p', (value) => {
    expect(() => costAllocation({ compute: { ceService: value } })).toThrow(
      'Configuration error: costAllocation.compute.ceService must be a non-empty string',
    );
  });

  describe.each(['ceComputeUsageTypePrefixes', 'ceSnapshotUsageTypePrefixes'])('compute.%s', (key) => {
    it('accepts a non-empty array of non-empty strings', () => {
      expect((costAllocation({ compute: { [key]: ['Lambda-MicroVM-X'] } }).compute as any)[key]).toEqual(['Lambda-MicroVM-X']);
    });

    it.each([[[]], ['Lambda-MicroVM-X'], [null], [{}]])('rejects %p (not a non-empty array)', (value) => {
      expect(() => costAllocation({ compute: { [key]: value } })).toThrow(
        `Configuration error: costAllocation.compute.${key} must be a non-empty array of strings`,
      );
    });

    it.each([[['']], [['ok', '']], [['ok', 1]], [[null]]])('rejects entries %p (empty or not a string)', (value) => {
      expect(() => costAllocation({ compute: { [key]: value } })).toThrow(
        new RegExp(`Configuration error: costAllocation\\.compute\\.${key} entry .* must be a non-empty string`),
      );
    });

    it('rejects duplicates', () => {
      expect(() => costAllocation({ compute: { [key]: ['A', 'B', 'A'] } })).toThrow(
        `Configuration error: costAllocation.compute.${key} contains "A" more than once`,
      );
    });
  });

  it('rejects unknown keys (typos would silently keep the default)', () => {
    expect(() => costAllocation({ lookbackdays: 5 })).toThrow(
      'Configuration error: costAllocation has unknown key "lookbackdays"; allowed: enabled, scheduleUtc, lookbackDays, novaActServiceName, compute',
    );
    expect(() => costAllocation({ compute: { ceservice: 'x' } })).toThrow(
      'Configuration error: costAllocation.compute has unknown key "ceservice"; allowed: enabled, ceService, ceComputeUsageTypePrefixes, ceSnapshotUsageTypePrefixes',
    );
  });

  it('rejects compute that is not an object', () => {
    expect(() => costAllocation({ compute: false })).toThrow('Configuration error: costAllocation.compute must be an object');
  });
});
