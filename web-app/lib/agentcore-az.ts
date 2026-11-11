import { execFileSync } from 'child_process';

/**
 * AgentCore VPC support is limited to specific Availability Zones per region.
 * If a VPC-attached AgentCore browser is placed in an unsupported AZ, the
 * CreateBrowser call fails at resource-creation time.
 *
 * The list below is keyed by AWS region and holds the supported **AZ IDs**
 * (e.g. "use1-az1"). AZ IDs are stable and account-independent, unlike AZ
 * *names* (e.g. "us-east-1a") which map to different physical zones per
 * account. We therefore pin the supported set by ID and resolve the
 * account-specific ID -> name mapping at synth time (see
 * {@link resolveAgentCoreAzNames}).
 *
 * Source (keep in sync when AWS expands support):
 * https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html
 */
export const AGENTCORE_SUPPORTED_AZ_IDS: Record<string, string[]> = {
  'us-east-1': ['use1-az1', 'use1-az2', 'use1-az4'],
  'us-east-2': ['use2-az1', 'use2-az2', 'use2-az3'],
  'us-west-1': ['usw1-az1', 'usw1-az3'],
  'us-west-2': ['usw2-az1', 'usw2-az2', 'usw2-az3'],
  'ap-southeast-5': ['apse5-az1', 'apse5-az2', 'apse5-az3'],
  'ap-south-1': ['aps1-az1', 'aps1-az2', 'aps1-az3'],
  'ap-south-2': ['aps2-az1', 'aps2-az2', 'aps2-az3'],
  'ap-northeast-2': ['apne2-az1', 'apne2-az2', 'apne2-az3'],
  'ap-southeast-1': ['apse1-az1', 'apse1-az2', 'apse1-az3'],
  'ap-southeast-2': ['apse2-az1', 'apse2-az2', 'apse2-az3'],
  'ap-southeast-7': ['apse7-az1', 'apse7-az2', 'apse7-az3'],
  'ap-northeast-1': ['apne1-az1', 'apne1-az2', 'apne1-az4'],
  'ca-central-1': ['cac1-az1', 'cac1-az2', 'cac1-az4'],
  'eu-central-1': ['euc1-az1', 'euc1-az2', 'euc1-az3'],
  'eu-west-1': ['euw1-az1', 'euw1-az2', 'euw1-az3'],
  'eu-west-2': ['euw2-az1', 'euw2-az2', 'euw2-az3'],
  'eu-south-1': ['eus1-az1', 'eus1-az2', 'eus1-az3'],
  'eu-west-3': ['euw3-az1', 'euw3-az2', 'euw3-az3'],
  'eu-south-2': ['eus2-az1', 'eus2-az2', 'eus2-az3'],
  'eu-north-1': ['eun1-az1', 'eun1-az2', 'eun1-az3'],
  'sa-east-1': ['sae1-az1', 'sae1-az2', 'sae1-az3'],
  'us-gov-west-1': ['usgw1-az1', 'usgw1-az2', 'usgw1-az3'],
};

export const AGENTCORE_VPC_DOC_URL =
  'https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html';

/** One `[ZoneName, ZoneId]` pair as returned by `describe-availability-zones`. */
export type AzNameIdPair = [string, string];

/** Returns the raw JSON of `aws ec2 describe-availability-zones` for a region. */
export type DescribeAzs = (region: string) => string;

/** Default {@link DescribeAzs}: the AWS CLI with the synth-time credentials. */
export const describeAzsWithAwsCli: DescribeAzs = (region) =>
  execFileSync(
    'aws',
    [
      'ec2', 'describe-availability-zones',
      '--region', region,
      '--query', 'AvailabilityZones[].[ZoneName,ZoneId]',
      '--output', 'json',
    ],
    { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] },
  );

/**
 * Resolve the Availability Zone **names** (e.g. "us-east-1a") in the given
 * region that AgentCore supports for VPC connectivity, for the AWS account
 * whose credentials are active during synth.
 *
 * Used when `vpcId` is set: the worker stack only passes subnets of the
 * imported VPC that live in one of these zones to the browser.
 *
 * Because the AZ name <-> ID mapping is account-specific, the default
 * `describeAzs` calls `ec2:DescribeAvailabilityZones` via the AWS CLI at
 * synth time. Synth therefore needs AWS credentials and the AWS CLI whenever
 * `vpcId` is set; deploys without `vpcId` never call this and keep
 * env-agnostic synthesis.
 *
 * May return an empty list (the account has none of the supported zones);
 * the caller's subnet check reports that with the VPC's own zones.
 *
 * @throws if the region has no known supported AZs, or the lookup fails.
 */
export function resolveAgentCoreAzNames(
  region: string,
  describeAzs: DescribeAzs = describeAzsWithAwsCli,
): string[] {
  const supportedIds = AGENTCORE_SUPPORTED_AZ_IDS[region];
  if (!supportedIds || supportedIds.length === 0) {
    throw new Error(
      `vpcId is set but region "${region}" has no known AgentCore-` +
        `supported Availability Zones in this stack's table. If AWS now supports ` +
        `AgentCore VPC in this region, add its AZ IDs to AGENTCORE_SUPPORTED_AZ_IDS ` +
        `(web-app/lib/agentcore-az.ts) from ${AGENTCORE_VPC_DOC_URL}.`,
    );
  }

  let raw: string;
  try {
    raw = describeAzs(region);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(
      `vpcId is set, which requires resolving AgentCore-supported ` +
        `Availability Zones for region "${region}" at synth time, but ` +
        `"aws ec2 describe-availability-zones" failed. Ensure the AWS CLI is ` +
        `installed and credentials for the target account/region are available ` +
        `during synth/deploy. Underlying error: ${message}`,
    );
  }

  let pairs: AzNameIdPair[];
  try {
    pairs = JSON.parse(raw);
    if (!Array.isArray(pairs)) throw new Error('expected a JSON array');
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(
      `Failed to parse "aws ec2 describe-availability-zones" output while ` +
        `resolving AgentCore AZs for region "${region}": ${message}`,
    );
  }

  return pairs
    .filter(([, zoneId]) => supportedIds.includes(zoneId))
    .map(([zoneName]) => zoneName)
    .sort();
}
