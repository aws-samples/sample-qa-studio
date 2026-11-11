/**
 * Guard: `BrowserVpc` (AgentCore browsers in an imported VPC) only reads the
 * customer's VPC, selects subnets in AgentCore-supported AZs (auto: private +
 * isolated, never public; explicit: exactly `vpcSubnetIds`), imports or
 * creates the one security group and hands the runtime the `AC_*` env.
 *
 * The VPC lookup is served from a stubbed `vpc-provider` context entry and the
 * AZ resolver is injected, so no AWS access is needed. Assertions use the real
 * subnet IDs of the stub, so a dummy lookup (missing context) would fail them.
 */
import { App, Stack } from 'aws-cdk-lib';
import { Annotations, Match, Template } from 'aws-cdk-lib/assertions';

import { BrowserVpc, BrowserVpcProps } from '../browser-vpc';

const ACCOUNT = '111122223333';
const REGION = 'eu-west-1';
const VPC_ID = 'vpc-0abc';
const CONTEXT_KEY = `vpc-provider:account=${ACCOUNT}:filter.vpc-id=${VPC_ID}:region=${REGION}:returnAsymmetricSubnets=true`;

/** eu-west-1a/b supported, eu-west-1c not (stub of resolveAgentCoreAzNames). */
const SUPPORTED = ['eu-west-1a', 'eu-west-1b'];

const subnet = (subnetId: string, availabilityZone: string) => ({
  subnetId, availabilityZone, routeTableId: `rtb-${subnetId}`, cidr: '10.0.0.0/24',
});

const VPC_RESPONSE = {
  vpcId: VPC_ID,
  vpcCidrBlock: '10.0.0.0/16',
  ownerAccountId: ACCOUNT,
  availabilityZones: [],
  subnetGroups: [
    { name: 'Public', type: 'Public', subnets: [subnet('subnet-pub-a', 'eu-west-1a'), subnet('subnet-pub-c', 'eu-west-1c')] },
    { name: 'Private', type: 'Private', subnets: [subnet('subnet-priv-a', 'eu-west-1a'), subnet('subnet-priv-c', 'eu-west-1c')] },
    { name: 'Isolated', type: 'Isolated', subnets: [subnet('subnet-iso-b', 'eu-west-1b')] },
  ],
};

interface Built {
  stack: Stack;
  browserVpc: BrowserVpc;
  resolver: jest.Mock;
}

function build(props: Partial<BrowserVpcProps> = {}, vpcResponse: object = VPC_RESPONSE): Built {
  const app = new App({ context: { [CONTEXT_KEY]: vpcResponse } });
  const stack = new Stack(app, 'worker', { env: { account: ACCOUNT, region: REGION } });
  const resolver = jest.fn(() => SUPPORTED);
  const browserVpc = new BrowserVpc(stack, 'browser_vpc', {
    vpcId: VPC_ID,
    vpcSubnetIds: null,
    workerSecurityGroupId: null,
    resolveAzNames: resolver,
    ...props,
  });
  return { stack, browserVpc, resolver };
}

function errors(stack: Stack): string[] {
  return Annotations.fromStack(stack).findError('*', Match.anyValue()).map((e) => String(e.entry.data));
}

function resourceTypes(stack: Stack): string[] {
  return Object.values<any>(Template.fromStack(stack).toJSON().Resources ?? {}).map((r) => r.Type);
}

describe('subnet selection', () => {
  test('default: every private and isolated subnet in a supported AZ, never public', () => {
    const { stack, browserVpc, resolver } = build();
    expect(browserVpc.subnetIds).toEqual(['subnet-priv-a', 'subnet-iso-b']);
    expect(resolver).toHaveBeenCalledWith(REGION);
    expect(errors(stack)).toEqual([]);
  });

  test('default without any eligible subnet: actionable error naming the VPC AZs and the supported AZs', () => {
    const response = {
      ...VPC_RESPONSE,
      subnetGroups: [
        VPC_RESPONSE.subnetGroups[0], // public in a supported AZ: never picked automatically
        { name: 'Private', type: 'Private', subnets: [subnet('subnet-priv-c', 'eu-west-1c')] },
      ],
    };
    const { stack } = build({}, response);
    const [message] = errors(stack);
    expect(message).toContain(`vpcId ${VPC_ID} has no private or isolated subnet in an AgentCore-supported Availability Zone`);
    expect(message).toContain('private/isolated-subnet AZs: eu-west-1c');
    expect(message).toContain('AgentCore-supported AZs in this region: eu-west-1a, eu-west-1b');
    expect(message).toContain('vpcSubnetIds');
  });

  test('explicit vpcSubnetIds: exactly these, order kept, public allowed', () => {
    const { stack, browserVpc } = build({ vpcSubnetIds: ['subnet-iso-b', 'subnet-pub-a'] });
    expect(browserVpc.subnetIds).toEqual(['subnet-iso-b', 'subnet-pub-a']);
    expect(errors(stack)).toEqual([]);
  });

  test('explicit subnet that is not in the VPC fails naming the subnet', () => {
    const { stack } = build({ vpcSubnetIds: ['subnet-priv-a', 'subnet-elsewhere'] });
    expect(errors(stack)).toEqual([
      expect.stringContaining(`vpcSubnetIds entry subnet-elsewhere is not a subnet of vpcId ${VPC_ID}`),
    ]);
  });

  test('explicit subnet in an unsupported AZ fails naming subnet, AZ and supported AZs', () => {
    const { stack } = build({ vpcSubnetIds: ['subnet-priv-c'] });
    const [message] = errors(stack);
    expect(message).toContain('vpcSubnetIds entry subnet-priv-c is in Availability Zone eu-west-1c');
    expect(message).toContain('AgentCore-supported AZs in this region: eu-west-1a, eu-west-1b');
  });

  test('a resolver failure (no AWS CLI / credentials) surfaces at synth', () => {
    const app = new App({ context: { [CONTEXT_KEY]: VPC_RESPONSE } });
    const stack = new Stack(app, 'worker', { env: { account: ACCOUNT, region: REGION } });
    expect(() => new BrowserVpc(stack, 'browser_vpc', {
      vpcId: VPC_ID, vpcSubnetIds: null, workerSecurityGroupId: null,
      resolveAzNames: () => { throw new Error('aws CLI failed'); },
    })).toThrow('aws CLI failed');
  });

  test('first synth pass (lookup context missing) does not throw, so the CLI can fetch the context', () => {
    const app = new App();
    const stack = new Stack(app, 'worker', { env: { account: ACCOUNT, region: REGION } });
    expect(() => new BrowserVpc(stack, 'browser_vpc', {
      vpcId: VPC_ID, vpcSubnetIds: ['subnet-priv-a'], workerSecurityGroupId: null, resolveAzNames: () => SUPPORTED,
    })).not.toThrow();
    expect(app.synth().manifest.missing?.map((m) => m.key)).toEqual([CONTEXT_KEY]);
  });

  test('an environment-agnostic stack is rejected with a pointer to credentials', () => {
    const stack = new Stack(new App(), 'worker');
    expect(() => new BrowserVpc(stack, 'browser_vpc', {
      vpcId: VPC_ID, vpcSubnetIds: null, workerSecurityGroupId: null, resolveAzNames: () => SUPPORTED,
    })).toThrow(/vpcId requires an explicit account\/region/);
  });
});

describe('security group', () => {
  test('unset workerSecurityGroupId: one new SG in the VPC, all outbound, no inbound, ASCII description', () => {
    const { stack, browserVpc } = build();
    const template = Template.fromStack(stack);
    template.resourceCountIs('AWS::EC2::SecurityGroup', 1);
    const sg = Object.values<any>(template.findResources('AWS::EC2::SecurityGroup'))[0];
    expect(sg.Properties.VpcId).toEqual(VPC_ID);
    expect(sg.Properties.GroupDescription).toEqual('QA Studio AgentCore browser ENIs');
    // eslint-disable-next-line no-control-regex
    expect(sg.Properties.GroupDescription).toMatch(/^[\x20-\x7e]+$/);
    expect(sg.Properties.SecurityGroupIngress).toBeUndefined();
    expect(sg.Properties.SecurityGroupEgress).toEqual([
      expect.objectContaining({ CidrIp: '0.0.0.0/0', IpProtocol: '-1' }),
    ]);
    template.resourceCountIs('AWS::EC2::SecurityGroupIngress', 0);
    expect(stack.resolve(browserVpc.securityGroupId)).toEqual({ 'Fn::GetAtt': [expect.any(String), 'GroupId'] });
  });

  test('created SG carries browser-specific cfn_nag and cdk-nag suppressions', () => {
    const { stack } = build();
    const sg = Object.values<any>(Template.fromStack(stack).findResources('AWS::EC2::SecurityGroup'))[0];
    const cfnNag = sg.Metadata.cfn_nag.rules_to_suppress.map((r: any) => r.id).sort();
    expect(cfnNag).toEqual(['W40', 'W5']);
    const cdkNag = sg.Metadata.cdk_nag.rules_to_suppress.map((r: any) => r.id);
    expect(cdkNag).toEqual(['AwsSolutions-EC23']);
    for (const rule of [...sg.Metadata.cfn_nag.rules_to_suppress, ...sg.Metadata.cdk_nag.rules_to_suppress]) {
      expect(rule.reason).toMatch(/AgentCore browser/);
    }
  });

  test('workerSecurityGroupId set: imported, nothing created', () => {
    const { stack, browserVpc } = build({ workerSecurityGroupId: 'sg-0def' });
    expect(browserVpc.securityGroupId).toEqual('sg-0def');
    expect(resourceTypes(stack)).toEqual([]);
  });
});

describe('the customer VPC is never modified', () => {
  test.each([
    ['created SG', {}],
    ['imported SG', { workerSecurityGroupId: 'sg-0def' }],
    ['explicit subnets', { vpcSubnetIds: ['subnet-pub-a'] }],
  ])('%s: no EC2 resource type other than AWS::EC2::SecurityGroup', (_label, props) => {
    const { stack } = build(props);
    const ec2 = resourceTypes(stack).filter((t) => t.startsWith('AWS::EC2::'));
    expect(ec2.filter((t) => t !== 'AWS::EC2::SecurityGroup')).toEqual([]);
    expect(resourceTypes(stack).filter((t) => !t.startsWith('AWS::EC2::'))).toEqual([]);
  });
});

describe('runtime environment', () => {
  test('AGENT_CORE_VPC / AC_* for the CLI and the wizard', () => {
    const { stack, browserVpc } = build({ workerSecurityGroupId: 'sg-0def' });
    expect(stack.resolve(browserVpc.environment)).toEqual({
      AGENT_CORE_VPC: 'true',
      AC_VPC_ID: VPC_ID,
      AC_SUBNET_IDS: 'subnet-priv-a,subnet-iso-b',
      AC_SECURITY_GROUP_ID: 'sg-0def',
    });
  });
});
