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
  vpcId: string | null;
  workerSecurityGroupId: string | null;
  createVpcEndpoints: boolean;
  useNovaActGa: boolean;
  agentCoreVPC: boolean;
  dockerImageVersion?: string;
  /** Full API Gateway URL for local development proxy (e.g. https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com) */
  apiGatewayUrl?: string;
  /** Enable extension-based authentication (Kiro extension OAuth callback) */
  enableExtensionAuthentication?: boolean;
  /** Callback URL for CLI OAuth flow (e.g. http://localhost:19847/callback) */
  cliCallbackUrl?: string;
  /** Reserved concurrent executions per Lambda function (default: 5) */
  lambdaConcurrency?: number;
}

const DEFAULT_CONFIG: Partial<NovaActQAStudioConfig> = {
  apiEndpoint: 'api',
  apiDeploymentStage: 'api',
  enabledRegions: ['us-east-1', 'us-west-2', 'ap-southeast-2', 'eu-central-1'],
  defaultRegion: 'us-east-1',
  bedrockModelId: 'us.amazon.nova-2-lite-v1:0',
  dcvRelease: 'https://d1uj6qtbmh3dt5.cloudfront.net/webclientsdk/nice-dcv-web-client-sdk-1.10.1-1011.zip',
  vpcId: null,
  workerSecurityGroupId: null,
  createVpcEndpoints: false,
  useNovaActGa: true,
  agentCoreVPC: false,
  lambdaConcurrency: 5,
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
  
  // Merge with defaults
  const config: NovaActQAStudioConfig = {
    ...DEFAULT_CONFIG,
    ...rawConfig,
  } as NovaActQAStudioConfig;

  // If dockerImageVersion is not specified, use package.json version
  if (!config.dockerImageVersion) {
    const packageJsonPath = path.join(__dirname, '..', 'package.json');
    const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf-8'));
    config.dockerImageVersion = packageJson.version;
  }

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

  // Validate VPC configuration
  if (config.vpcId && typeof config.vpcId !== 'string') {
    throw new Error('Configuration error: vpcId must be a string or null');
  }

  if (config.workerSecurityGroupId && typeof config.workerSecurityGroupId !== 'string') {
    throw new Error('Configuration error: workerSecurityGroupId must be a string or null');
  }

  // Validate VPC ID format if provided
  if (config.vpcId && !config.vpcId.startsWith('vpc-')) {
    throw new Error(`Configuration error: vpcId "${config.vpcId}" must start with "vpc-"`);
  }

  // Validate Security Group ID format if provided
  if (config.workerSecurityGroupId && !config.workerSecurityGroupId.startsWith('sg-')) {
    throw new Error(`Configuration error: workerSecurityGroupId "${config.workerSecurityGroupId}" must start with "sg-"`);
  }

  return config;
}

/**
 * Get environment configuration for CDK stacks
 * Returns explicit env when using existing VPC (required for Vpc.fromLookup)
 * Returns undefined for new VPC (allows environment-agnostic synthesis)
 * 
 * When using existing VPC, all stacks must have explicit env to avoid
 * cross-environment resource reference errors. This ensures all IAM roles
 * and resources can be properly referenced across stacks.
 */
export function getStackEnv(config: NovaActQAStudioConfig) {
  if (config.vpcId) {
    return {
      account: process.env.CDK_DEFAULT_ACCOUNT,
      region: process.env.CDK_DEFAULT_REGION,
    };
  }
  return undefined;
}
