import * as fs from 'fs';
import * as path from 'path';

export interface NovaActQAStudioConfig {
  adminEmail: string;
  baseName: string;
  apiEndpoint: string;
  apiDeploymentStage: string;
  enabledRegions: string[];
  defaultRegion: string;
  bedrockModelId: string;
  dcvRelease: string;
  useNovaActGa: boolean;
  /** Full API Gateway URL for local development proxy (e.g. https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com) */
  apiGatewayUrl?: string;
  /** Enable extension-based authentication (Kiro extension OAuth callback) */
  enableExtensionAuthentication?: boolean;
  /** Callback URL for CLI OAuth flow (e.g. http://localhost:19847/callback) */
  cliCallbackUrl?: string;
  /** Reserved concurrent executions per Lambda function (default: 5) */
  lambdaConcurrency?: number;
  /** Maximum bytes accepted for a single network_assertion body / schema field
   * (applies to request template, response template, mock response, and
   * captured request/response bodies). Default 1_048_576 (1 MiB). */
  networkAssertionBodyMaxBytes?: number;
  /** Hard ceiling for one batch execution in minutes (1–480). Default 60. */
  maxExecutionDurationMinutes?: number;
  /** Hard ceiling for one wizard session in minutes (1–480). Default 240. */
  maxWizardSessionMinutes?: number;
  /** Existing VPC the AgentCore browsers attach to (`networkMode: VPC`). `null` = PUBLIC browsers, no EC2 resources. */
  vpcId: string | null;
  /** Subnets of `vpcId` for the browser ENIs. `null` = every private and isolated subnet in an AgentCore-supported AZ. */
  vpcSubnetIds: string[] | null;
  /** Existing security group for the browser ENIs. `null` = the stack creates one in `vpcId`. */
  workerSecurityGroupId: string | null;
  /** Daily Cost Explorer allocation per use case / application / overall (design: cost-allocation). */
  costAllocation: CostAllocationConfig;
}

/** MicroVM compute allocation, read by the `compute` cost source (`cost_sources/compute.py`). */
export interface CostAllocationComputeConfig {
  /** Allocate MicroVM compute (Cost Explorer `SERVICE = ceService`) in addition to Nova Act. */
  enabled: boolean;
  /** Cost Explorer `SERVICE` dimension value the MicroVMs bill under. */
  ceService: string;
  /**
   * `USAGE_TYPE` stems split by VM seconds. Matched client-side against the
   * usage type after stripping the CE region prefix (`EUC1-`, `EU-`, none in
   * us-east-1): CE `GetCostAndUsage` has no `STARTS_WITH` filter (spike).
   */
  ceComputeUsageTypePrefixes: string[];
  /** `USAGE_TYPE` stems split by launch count (same matching). */
  ceSnapshotUsageTypePrefixes: string[];
}

export interface CostAllocationConfig {
  /** Deploy the `cost_collector` Lambda, its schedule and alarms. */
  enabled: boolean;
  /** EventBridge schedule expression (`cron(...)` / `rate(...)`, UTC) of the daily run. */
  scheduleUtc: string;
  /** Days re-processed per scheduled run (D-1 ... D-lookbackDays); 1..COST_ALLOCATION_MAX_LOOKBACK_DAYS. */
  lookbackDays: number;
  /** Cost Explorer `SERVICE` dimension value of Nova Act (`NovaAct`, verified by the spike). */
  novaActServiceName: string;
  compute: CostAllocationComputeConfig;
}

/** Longest lookback the scheduled run may re-process; Cost Explorer revises a day for ~4 days (spike). */
export const COST_ALLOCATION_MAX_LOOKBACK_DAYS = 14;

export const DEFAULT_COST_ALLOCATION: Readonly<CostAllocationConfig> = Object.freeze({
  enabled: true,
  scheduleUtc: 'cron(0 6 * * ? *)',
  lookbackDays: 3,
  novaActServiceName: 'NovaAct',
  compute: Object.freeze({
    enabled: true,
    ceService: 'AWS Lambda',
    ceComputeUsageTypePrefixes: Object.freeze(['Lambda-MicroVM-vCPU-Second', 'Lambda-MicroVM-Memory-GB-Second']) as string[],
    ceSnapshotUsageTypePrefixes: Object.freeze([
      'Lambda-MicroVM-Snapshot-Read-GB',
      'Lambda-MicroVM-Snapshot-Storage-GB-Hour',
      'Lambda-MicroVM-Snapshot-Write-GB',
    ]) as string[],
  }),
});

const COST_ALLOCATION_KEYS = ['enabled', 'scheduleUtc', 'lookbackDays', 'novaActServiceName', 'compute'] as const;
const COST_ALLOCATION_COMPUTE_KEYS = ['enabled', 'ceService', 'ceComputeUsageTypePrefixes', 'ceSnapshotUsageTypePrefixes'] as const;

/**
 * Keys that existed while the worker could run on ECS Fargate. The worker runs
 * on Lambda MicroVMs only now; a configuration that still sets one of them is
 * rejected (loudly, never silently ignored) so operators notice the change.
 */
export const REMOVED_CONFIG_KEYS = ['workerRuntime', 'dockerImageVersion'] as const;

const REMOVED_CONFIG_KEY_REASON = 'the worker runs on Lambda MicroVMs, without ECS';

/**
 * Keys that are still accepted but have no effect any more: `loadConfig()`
 * logs one warning per key and drops it from the typed config (no module may
 * read them). Key -> reason shown in the warning.
 */
export const DEPRECATED_CONFIG_KEYS: Readonly<Record<string, string>> = {
  agentCoreVPC: 'vpcId alone attaches the AgentCore browsers to the VPC',
  createVpcEndpoints: 'the stack creates no VPC endpoints; browsers use the routing of the vpcId subnets',
};

/** MicroVM platform ceiling: 8 h including suspended time. */
export const MAX_RUNTIME_MINUTES = 480;

const DEFAULT_CONFIG: Partial<NovaActQAStudioConfig> = {
  apiEndpoint: 'api',
  apiDeploymentStage: 'api',
  enabledRegions: ['us-east-1', 'us-west-2', 'ap-southeast-2', 'eu-central-1'],
  defaultRegion: 'us-east-1',
  bedrockModelId: 'us.amazon.nova-2-lite-v1:0',
  dcvRelease: 'https://d1uj6qtbmh3dt5.cloudfront.net/webclientsdk/nice-dcv-web-client-sdk-1.10.1-1011.zip',
  useNovaActGa: true,
  lambdaConcurrency: 5,
  networkAssertionBodyMaxBytes: 1_048_576,
  maxExecutionDurationMinutes: 60,
  maxWizardSessionMinutes: 240,
  vpcId: null,
  vpcSubnetIds: null,
  workerSecurityGroupId: null,
};

/**
 * Load and validate configuration from configuration.json
 * Applies sane defaults for optional fields
 * 
 * @param configPath - Path to configuration.json (defaults to ../configuration.json)
 * @returns Validated configuration object
 * @throws Error if required fields are missing or invalid
 */
export function loadConfig(configPath?: string): NovaActQAStudioConfig {
  const configFile = configPath || path.join(__dirname, '..', 'configuration.json');
  
  if (!fs.existsSync(configFile)) {
    throw new Error(`Configuration file not found: ${configFile}`);
  }

  const rawConfig = JSON.parse(fs.readFileSync(configFile, 'utf-8'));

  for (const key of REMOVED_CONFIG_KEYS) {
    if (key in rawConfig) {
      throw new Error(
        `Configuration error: ${key} was removed (${REMOVED_CONFIG_KEY_REASON}); see the release notes`,
      );
    }
  }
  
  // vpcId + agentCoreVPC: false asks for two contradicting things: vpcId now
  // attaches the browsers to the VPC, the old switch says "do not".
  if (rawConfig.vpcId != null && rawConfig.agentCoreVPC === false) {
    throw new Error(
      'Configuration error: agentCoreVPC is deprecated; vpcId now attaches browsers to the VPC. Remove agentCoreVPC',
    );
  }
  for (const [key, reason] of Object.entries(DEPRECATED_CONFIG_KEYS)) {
    if (key in rawConfig) {
      console.warn(`Configuration warning: ${key} is deprecated and ignored (${reason}); see docs/configuration.md`);
      delete rawConfig[key];
    }
  }

  // Merge with defaults
  const config: NovaActQAStudioConfig = {
    ...DEFAULT_CONFIG,
    ...rawConfig,
    costAllocation: mergeCostAllocation(rawConfig.costAllocation),
  } as NovaActQAStudioConfig;

  // Validate required fields
  if (!config.adminEmail) {
    throw new Error('Configuration error: adminEmail is required');
  }

  if (!config.baseName) {
    throw new Error('Configuration error: baseName is required');
  }

  // Validate email format
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(config.adminEmail)) {
    throw new Error(`Configuration error: adminEmail "${config.adminEmail}" is not a valid email address`);
  }

  // Validate baseName format (lowercase alphanumeric and hyphens only)
  const baseNameRegex = /^[a-z0-9-]+$/;
  if (!baseNameRegex.test(config.baseName)) {
    throw new Error(`Configuration error: baseName "${config.baseName}" must contain only lowercase letters, numbers, and hyphens`);
  }

  // Validate regions
  if (!config.enabledRegions || config.enabledRegions.length === 0) {
    throw new Error('Configuration error: enabledRegions must contain at least one region');
  }

  if (!config.enabledRegions.includes(config.defaultRegion)) {
    throw new Error(`Configuration error: defaultRegion "${config.defaultRegion}" must be included in enabledRegions`);
  }

  validateBrowserVpc(config);

  // Validate networkAssertionBodyMaxBytes — positive integer when present
  if (
    config.networkAssertionBodyMaxBytes !== undefined &&
    (!Number.isInteger(config.networkAssertionBodyMaxBytes) || config.networkAssertionBodyMaxBytes <= 0)
  ) {
    throw new Error(
      `Configuration error: networkAssertionBodyMaxBytes "${config.networkAssertionBodyMaxBytes}" must be a positive integer`,
    );
  }

  // Validate timeout ceilings — integer minutes within the MicroVM platform limit
  validateMinutes('maxExecutionDurationMinutes', config.maxExecutionDurationMinutes);
  validateMinutes('maxWizardSessionMinutes', config.maxWizardSessionMinutes);

  validateCostAllocation(config.costAllocation);

  return config;
}

/**
 * `costAllocation` deep-merged with its defaults (one level: the block and
 * `compute`), so an operator can set a single key. Shape errors are reported
 * by `validateCostAllocation`; this only merges what is an object.
 */
function mergeCostAllocation(raw: unknown): CostAllocationConfig {
  if (raw === undefined) return structuredClone(DEFAULT_COST_ALLOCATION);
  if (!isPlainObject(raw)) {
    throw new Error('Configuration error: costAllocation must be an object');
  }
  const compute = raw.compute;
  if (compute !== undefined && !isPlainObject(compute)) {
    throw new Error('Configuration error: costAllocation.compute must be an object');
  }
  return {
    ...structuredClone(DEFAULT_COST_ALLOCATION),
    ...raw,
    compute: { ...structuredClone(DEFAULT_COST_ALLOCATION.compute), ...(compute ?? {}) },
  } as CostAllocationConfig;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** `costAllocation`: known keys only, types, `lookbackDays` range, schedule expression syntax. */
function validateCostAllocation(block: CostAllocationConfig): void {
  rejectUnknownKeys('costAllocation', block, COST_ALLOCATION_KEYS);
  rejectUnknownKeys('costAllocation.compute', block.compute, COST_ALLOCATION_COMPUTE_KEYS);

  validateBoolean('costAllocation.enabled', block.enabled);
  validateBoolean('costAllocation.compute.enabled', block.compute.enabled);

  const lookback: unknown = block.lookbackDays;
  if (!Number.isInteger(lookback) || (lookback as number) < 1 || (lookback as number) > COST_ALLOCATION_MAX_LOOKBACK_DAYS) {
    throw new Error(
      `Configuration error: costAllocation.lookbackDays ${JSON.stringify(lookback)} must be an integer between 1 and ${COST_ALLOCATION_MAX_LOOKBACK_DAYS}`,
    );
  }

  const schedule: unknown = block.scheduleUtc;
  if (typeof schedule !== 'string' || !(schedule.startsWith('cron(') || schedule.startsWith('rate('))) {
    throw new Error(
      `Configuration error: costAllocation.scheduleUtc ${JSON.stringify(schedule)} must be an EventBridge schedule expression starting with "cron(" or "rate("`,
    );
  }

  validateNonEmptyString('costAllocation.novaActServiceName', block.novaActServiceName);
  validateNonEmptyString('costAllocation.compute.ceService', block.compute.ceService);
  validateStringList('costAllocation.compute.ceComputeUsageTypePrefixes', block.compute.ceComputeUsageTypePrefixes);
  validateStringList('costAllocation.compute.ceSnapshotUsageTypePrefixes', block.compute.ceSnapshotUsageTypePrefixes);
}

function rejectUnknownKeys(label: string, value: object, allowed: readonly string[]): void {
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) {
      throw new Error(`Configuration error: ${label} has unknown key "${key}"; allowed: ${allowed.join(', ')}`);
    }
  }
}

function validateBoolean(label: string, value: unknown): void {
  if (typeof value !== 'boolean') {
    throw new Error(`Configuration error: ${label} must be a boolean`);
  }
}

function validateNonEmptyString(label: string, value: unknown): void {
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`Configuration error: ${label} must be a non-empty string`);
  }
}

/** Non-empty array of unique, non-empty strings. */
function validateStringList(label: string, value: unknown): void {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`Configuration error: ${label} must be a non-empty array of strings`);
  }
  const seen = new Set<string>();
  for (const entry of value) {
    if (typeof entry !== 'string' || entry.length === 0) {
      throw new Error(`Configuration error: ${label} entry ${JSON.stringify(entry)} must be a non-empty string`);
    }
    if (seen.has(entry)) {
      throw new Error(`Configuration error: ${label} contains "${entry}" more than once`);
    }
    seen.add(entry);
  }
}

function validateMinutes(key: string, value: unknown): void {
  if (!Number.isInteger(value) || (value as number) < 1 || (value as number) > MAX_RUNTIME_MINUTES) {
    throw new Error(
      `Configuration error: ${key} "${value}" must be an integer between 1 and ${MAX_RUNTIME_MINUTES}`,
    );
  }
}

/** `vpcId` / `vpcSubnetIds` / `workerSecurityGroupId`: types, ID prefixes, dependencies. */
function validateBrowserVpc(config: NovaActQAStudioConfig): void {
  validateOptionalId('vpcId', config.vpcId, 'vpc-');
  validateOptionalId('workerSecurityGroupId', config.workerSecurityGroupId, 'sg-');

  const subnets: unknown = config.vpcSubnetIds;
  if (subnets !== null) {
    if (!Array.isArray(subnets) || subnets.length === 0) {
      throw new Error('Configuration error: vpcSubnetIds must be null or a non-empty array of subnet IDs');
    }
    const seen = new Set<string>();
    for (const entry of subnets) {
      if (typeof entry !== 'string' || !entry.startsWith('subnet-')) {
        throw new Error(`Configuration error: vpcSubnetIds entry ${JSON.stringify(entry)} must be a string starting with "subnet-"`);
      }
      if (seen.has(entry)) {
        throw new Error(`Configuration error: vpcSubnetIds contains "${entry}" more than once`);
      }
      seen.add(entry);
    }
  }

  if (config.vpcId === null) {
    for (const key of ['vpcSubnetIds', 'workerSecurityGroupId'] as const) {
      if (config[key] !== null) {
        throw new Error(`Configuration error: ${key} requires vpcId`);
      }
    }
  }
}

function validateOptionalId(key: string, value: unknown, prefix: string): void {
  if (value === null) return;
  if (typeof value !== 'string') {
    throw new Error(`Configuration error: ${key} must be a string or null`);
  }
  if (!value.startsWith(prefix)) {
    throw new Error(`Configuration error: ${key} "${value}" must start with "${prefix}"`);
  }
}

/**
 * Environment for every CDK stack.
 *
 * With `vpcId` set the worker stack calls `Vpc.fromLookup`, which needs an
 * explicit account/region; all stacks then get the same explicit env so
 * cross-stack references stay in one environment. Without `vpcId` it returns
 * `undefined` and synthesis stays environment-agnostic.
 */
export function getStackEnv(config: NovaActQAStudioConfig): { account?: string; region?: string } | undefined {
  if (config.vpcId) {
    return {
      account: process.env.CDK_DEFAULT_ACCOUNT,
      region: process.env.CDK_DEFAULT_REGION,
    };
  }
  return undefined;
}
