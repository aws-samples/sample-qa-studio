/**
 * Worker stack with `vpcId` set: the AgentCore browser VPC wiring reaches the
 * MicroVM image env, the stack adds at most one security group to the VPC and
 * nothing else changes in the image env.
 *
 * Config = configuration.json.sample + vpcId; the VPC lookup is served from a
 * stubbed `vpc-provider` context entry and the AZ resolver is mocked, so no AWS
 * access is needed. Subnet/SG branches are covered in browser-vpc.test.ts.
 */
import { Annotations, Match, Template } from 'aws-cdk-lib/assertions';

const ACCOUNT = '111122223333';
const REGION = 'eu-west-1';
const VPC_ID = 'vpc-0abc';

let mockVpcId: string | null = VPC_ID;

jest.mock('../config', () => {
  const actual = jest.requireActual('../config');
  const sample = require('path').join(__dirname, '..', '..', 'configuration.json.sample');
  return { ...actual, loadConfig: () => ({ ...actual.loadConfig(sample), vpcId: mockVpcId }) };
});

jest.mock('../agentcore-az', () => ({
  ...jest.requireActual('../agentcore-az'),
  resolveAgentCoreAzNames: jest.fn(() => ['eu-west-1a', 'eu-west-1b']),
}));

import { resolveAgentCoreAzNames } from '../agentcore-az';
import type { synthStacks as SynthStacks } from './synthStacks';

/** worker-stack.ts reads the config at module load: load a fresh module graph per variant. */
function synthWith(vpcId: string | null, options: Parameters<typeof SynthStacks>[0]) {
  mockVpcId = vpcId;
  let result!: ReturnType<typeof SynthStacks>;
  jest.isolateModules(() => {
    result = (require('./synthStacks') as { synthStacks: typeof SynthStacks }).synthStacks(options);
  });
  return result;
}

const subnet = (subnetId: string, availabilityZone: string) => ({
  subnetId, availabilityZone, routeTableId: `rtb-${subnetId}`, cidr: '10.0.0.0/24',
});

const CONTEXT = {
  [`vpc-provider:account=${ACCOUNT}:filter.vpc-id=${VPC_ID}:region=${REGION}:returnAsymmetricSubnets=true`]: {
    vpcId: VPC_ID,
    vpcCidrBlock: '10.0.0.0/16',
    ownerAccountId: ACCOUNT,
    availabilityZones: [],
    subnetGroups: [
      { name: 'Public', type: 'Public', subnets: [subnet('subnet-pub-a', 'eu-west-1a')] },
      { name: 'Private', type: 'Private', subnets: [subnet('subnet-priv-a', 'eu-west-1a'), subnet('subnet-priv-b', 'eu-west-1b')] },
    ],
  },
};

const withVpc = synthWith(VPC_ID, { env: { account: ACCOUNT, region: REGION }, context: CONTEXT });
const withoutVpc = synthWith(null, {});
const json = Template.fromStack(withVpc.worker).toJSON() as { Resources: Record<string, any> };

function imageEnv(resources: Record<string, any>): Record<string, any> {
  const image = Object.values<any>(resources).find((r) => r.Type === 'AWS::Lambda::MicrovmImage');
  return Object.fromEntries(image.Properties.EnvironmentVariables.map((e: any) => [e.Key, e.Value]));
}

test('the AZ resolver is asked for the stack region, and only on the vpcId path', () => {
  // One call across both variants: the PUBLIC synth never resolves AZs (env-agnostic).
  expect(resolveAgentCoreAzNames).toHaveBeenCalledTimes(1);
  expect(resolveAgentCoreAzNames).toHaveBeenCalledWith(REGION);
});

test('synth has no errors', () => {
  expect(Annotations.fromStack(withVpc.worker).findError('*', Match.anyValue())).toEqual([]);
});

test('image env carries AGENT_CORE_VPC and the AC_* values', () => {
  const env = imageEnv(json.Resources);
  expect(env.AGENT_CORE_VPC).toEqual('true');
  expect(env.AC_VPC_ID).toEqual(VPC_ID);
  expect(env.AC_SUBNET_IDS).toEqual('subnet-priv-a,subnet-priv-b');
  expect(env.AC_SECURITY_GROUP_ID).toEqual({ 'Fn::GetAtt': [expect.stringMatching(/^browservpcsecuritygroup/), 'GroupId'] });
  expect(Object.keys(env)).not.toContain('AC_SUBNET_ID');
});

test('nothing else in the image env changes: vpcId only adds the four keys', () => {
  const publicKeys = Object.keys(imageEnv(Template.fromStack(withoutVpc.worker).toJSON().Resources));
  const vpcKeys = Object.keys(imageEnv(json.Resources));
  expect(vpcKeys.filter((k) => !publicKeys.includes(k)).sort())
    .toEqual(['AC_SECURITY_GROUP_ID', 'AC_SUBNET_IDS', 'AC_VPC_ID', 'AGENT_CORE_VPC']);
  expect(publicKeys.filter((k) => !vpcKeys.includes(k))).toEqual([]);
});

test('the only EC2 resource is the one browser security group; no VPC, subnet, NAT, route or endpoint', () => {
  const ec2 = Object.values<any>(json.Resources).filter((r) => r.Type.startsWith('AWS::EC2::')).map((r) => r.Type);
  expect(ec2).toEqual(['AWS::EC2::SecurityGroup']);
});

test('every stack gets the explicit env', () => {
  for (const stack of [withVpc.storage, withVpc.auth, withVpc.worker, withVpc.lambdas]) {
    expect(stack.environment).toEqual(`aws://${ACCOUNT}/${REGION}`);
  }
});

test('no Lambda is attached to the VPC (only the browser is)', () => {
  for (const res of Object.values<any>(json.Resources)) {
    if (res.Type === 'AWS::Lambda::Function') expect(res.Properties.VpcConfig).toBeUndefined();
  }
});

test('no IAM grant on ec2:* is added (AgentCore uses its service-linked role)', () => {
  expect(JSON.stringify(json.Resources)).not.toMatch(/"ec2:/);
});
