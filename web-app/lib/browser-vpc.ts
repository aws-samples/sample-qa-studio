import { Annotations, CfnResource, Stack, Token } from 'aws-cdk-lib';
import { ISubnet, IVpc, SecurityGroup, Vpc } from 'aws-cdk-lib/aws-ec2';
import { NagSuppressions } from 'cdk-nag';
import { Construct } from 'constructs';

import { resolveAgentCoreAzNames } from './agentcore-az';

export interface BrowserVpcProps {
  /** Existing VPC the AgentCore browser ENIs go into (config `vpcId`). */
  vpcId: string;
  /** Explicit subnets (config `vpcSubnetIds`); `null` = every eligible private and isolated subnet. */
  vpcSubnetIds: string[] | null;
  /** Existing security group for the ENIs (config `workerSecurityGroupId`); `null` = create one. */
  workerSecurityGroupId: string | null;
  /** AgentCore-supported AZ names for a region. Injectable for tests; default calls the AWS CLI. */
  resolveAzNames?: (region: string) => string[];
}

/**
 * AgentCore browsers attached to an imported VPC (`networkMode: VPC`).
 *
 * Only the browser lives in the VPC: AgentCore creates its ENIs in the selected
 * subnets through its service-linked role; the worker MicroVM keeps calling
 * AgentCore over the public API. The customer's VPC is only read
 * (`Vpc.fromLookup`). The single exception is the browser security group,
 * created in the VPC when `workerSecurityGroupId` is not given (all outbound,
 * no inbound). No subnet, route table, NAT gateway, endpoint or rule of an
 * existing security group is created or changed.
 *
 * Subnet problems are reported as synth errors (annotations), not thrown: the
 * first synth pass runs against CDK's dummy VPC while the CLI fetches the
 * lookup context, and a throw there would abort before the real lookup.
 *
 * {@link environment} is the image-level env the CLI provisioner and the wizard
 * read (`AGENT_CORE_VPC`, `AC_VPC_ID`, `AC_SUBNET_IDS`, `AC_SECURITY_GROUP_ID`).
 */
export class BrowserVpc extends Construct {
  /** Subnets passed to `create_browser` as `vpcConfig.subnets`, in order. */
  public readonly subnetIds: string[];
  /** Security group passed as `vpcConfig.securityGroups[0]`. */
  public readonly securityGroupId: string;
  private readonly vpcId: string;

  constructor(scope: Construct, id: string, props: BrowserVpcProps) {
    super(scope, id);
    const stack = Stack.of(this);
    if (Token.isUnresolved(stack.region) || Token.isUnresolved(stack.account)) {
      throw new Error(
        'vpcId requires an explicit account/region on the stacks (Vpc.fromLookup). Run synth/deploy with ' +
          'AWS credentials for the target account so CDK_DEFAULT_ACCOUNT / CDK_DEFAULT_REGION are set.',
      );
    }

    // Messages and env use the configured ID: the first synth pass sees CDK's dummy VPC.
    this.vpcId = props.vpcId;
    const vpc = Vpc.fromLookup(this, 'existing_vpc', { vpcId: props.vpcId });
    const supportedAzNames = (props.resolveAzNames ?? resolveAgentCoreAzNames)(stack.region);

    this.subnetIds = props.vpcSubnetIds
      ? this.explicitSubnets(vpc, props.vpcSubnetIds, supportedAzNames)
      : this.eligibleSubnets(vpc, supportedAzNames);

    if (props.workerSecurityGroupId) {
      this.securityGroupId = SecurityGroup.fromSecurityGroupId(
        this, 'imported_security_group', props.workerSecurityGroupId,
      ).securityGroupId;
    } else {
      this.securityGroupId = this.createSecurityGroup(vpc).securityGroupId;
    }
  }

  /** Image-level env of the worker MicroVM (stack constants only). */
  get environment(): Record<string, string> {
    return {
      AGENT_CORE_VPC: 'true',
      AC_VPC_ID: this.vpcId,
      AC_SUBNET_IDS: this.subnetIds.join(','),
      AC_SECURITY_GROUP_ID: this.securityGroupId,
    };
  }

  /** Every private and isolated subnet in a supported AZ; public subnets are never picked automatically. */
  private eligibleSubnets(vpc: IVpc, supportedAzNames: string[]): string[] {
    const candidates = [...vpc.privateSubnets, ...vpc.isolatedSubnets];
    const eligible = candidates.filter((s) => supportedAzNames.includes(s.availabilityZone));
    if (eligible.length === 0) {
      const vpcAzs = [...new Set(candidates.map((s) => s.availabilityZone))].sort();
      this.error(
        `vpcId ${this.vpcId} has no private or isolated subnet in an AgentCore-supported Availability Zone. ` +
          `VPC private/isolated-subnet AZs: ${vpcAzs.join(', ') || '(none)'}. ` +
          `AgentCore-supported AZs in this region: ${formatAzs(supportedAzNames)}. ` +
          'Add a subnet in one of the supported AZs, or list the subnets to use in vpcSubnetIds.',
      );
    }
    return eligible.map((s) => s.subnetId);
  }

  /** Exactly the configured subnets (any type), each in the VPC and in a supported AZ. */
  private explicitSubnets(vpc: IVpc, subnetIds: string[], supportedAzNames: string[]): string[] {
    const byId = new Map<string, ISubnet>(
      [...vpc.publicSubnets, ...vpc.privateSubnets, ...vpc.isolatedSubnets].map((s) => [s.subnetId, s]),
    );
    for (const subnetId of subnetIds) {
      const found = byId.get(subnetId);
      if (!found) {
        this.error(
          `vpcSubnetIds entry ${subnetId} is not a subnet of vpcId ${this.vpcId} ` +
            `(subnets of the VPC: ${[...byId.keys()].join(', ') || '(none)'}).`,
        );
      } else if (!supportedAzNames.includes(found.availabilityZone)) {
        this.error(
          `vpcSubnetIds entry ${subnetId} is in Availability Zone ${found.availabilityZone}, which AgentCore ` +
            `does not support for VPC browsers. AgentCore-supported AZs in this region: ${formatAzs(supportedAzNames)}.`,
        );
      }
    }
    return [...subnetIds];
  }

  private createSecurityGroup(vpc: IVpc): SecurityGroup {
    const securityGroup = new SecurityGroup(this, 'security_group', {
      vpc,
      // ASCII only: EC2 rejects any non-ASCII GroupDescription at CREATE time.
      description: 'QA Studio AgentCore browser ENIs',
      allowAllOutbound: true,
    });
    const reason =
      'AgentCore browser ENIs need unrestricted egress to reach the websites under test inside the VPC; ' +
      'the group has no inbound rules.';
    (securityGroup.node.defaultChild as CfnResource).addMetadata('cfn_nag', {
      rules_to_suppress: [
        { id: 'W40', reason },
        { id: 'W5', reason },
      ],
    });
    NagSuppressions.addResourceSuppressions(securityGroup, [{ id: 'AwsSolutions-EC23', reason }]);
    return securityGroup;
  }

  private error(message: string): void {
    Annotations.of(this).addError(message);
  }
}

function formatAzs(names: string[]): string {
  return names.join(', ') || '(none in this account)';
}
